"""Poll reviewed terrain material ownership without attaching a debugger."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from shadowbane_lab.client_observation.native_health import (
    NativeMemoryRegion,
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    PROFILE as TERRAIN_BRANCH_PROFILE,
)
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    TerrainBranchProfile,
    _hex32,
    _utc_now,
    _validate_target,
)
from shadowbane_lab.diagnostics.terrain_mesh_snapshot import (
    LAYOUT_SIGNATURES,
    MAXIMUM_MESH_READ_BYTES,
    WRAPPER_SIZE,
    WRAPPER_VTABLE_RVA,
    MeshReadBudget,
    TerrainMeshCaptureError,
    capture_mesh_snapshot,
)

SCHEMA_VERSION = 4
MINIMUM_USER_ADDRESS = 0x10000
MAXIMUM_USER_ADDRESS = 0x7FFEFFFF
SHADER_SIZE = 0x34
OWNER_SIZE = 0x14
TERRAIN_OBJECT_SIZE = 0x1AE
TEXTURE_OBJECT_SIZE = 0x60
TEXTURE_BACKING_SIZE = 0x104
MAXIMUM_LAYERS = 32
MAXIMUM_SNAPSHOTS = 64
MAXIMUM_POLLS = 20_000
MAXIMUM_ALPHA_READ_BYTES = 16 * 1024 * 1024
TERRAIN_SOURCE_VTABLE_RVA = 0x1149F88


class TerrainMaterialCompatibilityError(RuntimeError):
    """Raised when the target is not the exact reviewed terrain layout."""


class TerrainMaterialCaptureError(RuntimeError):
    """Raised when one bounded process-memory read cannot be trusted."""


class _IdleSample(RuntimeError):
    pass


class _UnstableSample(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TerrainMaterialProfile:
    profile_id: str
    branch_profile: TerrainBranchProfile
    draw_rva: int
    draw_signature: bytes
    shader_global_rva: int
    shader_vtable_rva: int
    texture_vtable_rva: int
    backing_vtable_rva: int
    pixel_accessor_rva: int
    pixel_accessor_signature: bytes

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        if min(
            self.draw_rva,
            self.shader_global_rva,
            self.shader_vtable_rva,
            self.texture_vtable_rva,
            self.backing_vtable_rva,
            self.pixel_accessor_rva,
        ) <= 0:
            raise ValueError("reviewed terrain RVAs must be positive")
        if not self.draw_signature or not self.pixel_accessor_signature:
            raise ValueError("reviewed code signatures must not be empty")


PROFILE = TerrainMaterialProfile(
    profile_id="wonderbane-a9a5-terrain-material-poll-v1",
    branch_profile=TERRAIN_BRANCH_PROFILE,
    draw_rva=0x4F1660,
    draw_signature=bytes.fromhex("558bec515356"),
    shader_global_rva=0x1388228,
    shader_vtable_rva=0x11625A4,
    texture_vtable_rva=0x114A39C,
    backing_vtable_rva=0x11490F0,
    pixel_accessor_rva=0x18D920,
    pixel_accessor_signature=bytes.fromhex(
        "568bf18b465c85c0750f8b860401000085c07405e80d95e8ff"
        "8b465cc786f4000000ffffffff5ec3"
    ),
)


@dataclass(slots=True)
class _AlphaReadBudget:
    bytes_reserved: int = 0

    def reserve_pair(self, size: int) -> bool:
        if self.bytes_reserved + 2 * size > MAXIMUM_ALPHA_READ_BYTES:
            return False
        # Failed/concurrently changing reads still consume their reservation.
        self.bytes_reserved += 2 * size
        return True


class TerrainMaterialBackend(Protocol):
    pid: int
    executable_name: str
    executable_path: Path
    executable_sha256: str
    base_address: int
    pointer_size: int
    process_creation_filetime_utc: int

    def read_block(self, address: int, size: int) -> bytes: ...

    def query_region(self, address: int) -> NativeMemoryRegion: ...

    def close(self) -> None: ...


def _readable_region(region: NativeMemoryRegion, address: int, size: int) -> bool:
    return (
        address >= region.base_address
        and address + size <= region.base_address + region.size
        and not region.protection & 0x100
        and not region.protection & 0x01
    )


def _read_exact(
    backend: TerrainMaterialBackend,
    address: int,
    size: int,
    label: str,
) -> bytes:
    if address < MINIMUM_USER_ADDRESS or address + size > MAXIMUM_USER_ADDRESS or size <= 0:
        raise TerrainMaterialCaptureError(f"{label} was outside the 32-bit user range")
    try:
        region = backend.query_region(address)
        if not _readable_region(region, address, size):
            raise TerrainMaterialCaptureError(f"{label} did not fit one readable region")
        raw = backend.read_block(address, size)
    except TerrainMaterialCaptureError:
        raise
    except Exception as error:
        raise TerrainMaterialCaptureError(
            f"{label} read failed: {type(error).__name__}"
        ) from error
    if len(raw) != size:
        raise TerrainMaterialCaptureError(f"{label} read was partial")
    return raw


def _vector_bounds(raw: bytes, offset: int, label: str) -> tuple[int, int, dict[str, object]]:
    begin, end, capacity = struct.unpack_from("<III", raw, offset)
    valid = (
        begin <= end <= capacity
        and begin % 4 == 0
        and end % 4 == 0
        and capacity % 4 == 0
        and (end - begin) // 4 <= MAXIMUM_LAYERS
    )
    result: dict[str, object] = {
        "begin": _hex32(begin),
        "end": _hex32(end),
        "capacity": _hex32(capacity),
        "count": (end - begin) // 4 if valid else None,
        "bounds_valid": valid,
    }
    if not valid:
        raise TerrainMaterialCaptureError(f"{label} bounds were invalid")
    return begin, end, result


def _read_pointer_vector(
    backend: TerrainMaterialBackend,
    raw: bytes,
    offset: int,
    label: str,
) -> tuple[list[int], dict[str, object], bytes]:
    begin, end, result = _vector_bounds(raw, offset, label)
    entries = b"" if begin == end else _read_exact(backend, begin, end - begin, label)
    pointers = list(struct.unpack(f"<{len(entries) // 4}I", entries)) if entries else []
    result["pointers"] = [_hex32(value) for value in pointers]
    return pointers, result, entries


def _resident_alpha_snapshot(
    backend: TerrainMaterialBackend,
    backing_raw: bytes,
    profile: TerrainMaterialProfile,
    budget: _AlphaReadBudget,
) -> dict[str, object]:
    vtable = struct.unpack_from("<I", backing_raw, 0)[0]
    if vtable != backend.base_address + profile.backing_vtable_rva:
        return {"state": "unreviewed_backing_class", "vtable": _hex32(vtable)}
    width, height, channels = struct.unpack_from("<III", backing_raw, 0x38)
    target, format_value = struct.unpack_from("<II", backing_raw, 0xFC)
    if (
        width not in (64, 128)
        or height != width
        or channels != 1
        or target != 0x0DE1
        or format_value != 0x1906
    ):
        return {"state": "unsupported_alpha_layout"}
    pointer = struct.unpack_from("<I", backing_raw, 0x5C)[0]
    if not pointer:
        return {"state": "not_resident"}
    size = width * height
    if not budget.reserve_pair(size):
        return {"state": "capture_byte_budget_exhausted"}
    raw = _read_exact(backend, pointer, size, "resident alpha pixels")
    if _read_exact(backend, pointer, size, "resident alpha pixels") != raw:
        raise _UnstableSample("resident alpha pixels changed during the sample")
    return {
        "state": "captured",
        "storage": "resident_cpu_alpha8",
        "pointer": _hex32(pointer),
        "width": width,
        "height": height,
        "byte_count": size,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes_base64": base64.b64encode(raw).decode("ascii"),
        "orientation": "raw_memory_order_not_screen_axes",
    }


def _texture_snapshot(
    backend: TerrainMaterialBackend,
    address: int,
    profile: TerrainMaterialProfile,
    alpha_budget: _AlphaReadBudget | None = None,
) -> dict[str, object] | None:
    if not address:
        return None
    vtable_raw = _read_exact(backend, address, 4, "texture vtable")
    vtable = struct.unpack("<I", vtable_raw)[0]
    if vtable != backend.base_address + profile.texture_vtable_rva:
        return {
            "address": _hex32(address),
            "vtable": _hex32(vtable),
            "reviewed_color_texture": False,
            "read_warning": "unreviewed texture class; no layout fields interpreted",
        }
    raw = _read_exact(backend, address, TEXTURE_OBJECT_SIZE, "texture object")
    if raw[:4] != vtable_raw:
        raise _UnstableSample("texture class changed during the sample")
    resource, group = struct.unpack_from("<II", raw, 0x10)
    backing = struct.unpack_from("<I", raw, 0x5C)[0]
    result: dict[str, object] = {
        "address": _hex32(address),
        "vtable": _hex32(vtable),
        "reviewed_color_texture": True,
        "token": {
            "archive_group": group,
            "archive_resource": resource,
            "in_memory_hex": raw[0x10:0x18].hex(),
            "generated_or_unattributed": resource == 0 and group == 0,
        },
        "flags": raw[0x1C],
        "backing_address": _hex32(backing),
    }
    backing_raw = b""
    if backing:
        backing_raw = _read_exact(backend, backing, TEXTURE_BACKING_SIZE, "texture backing")
        result["backing"] = {
            "width": struct.unpack_from("<I", backing_raw, 0x38)[0],
            "height": struct.unpack_from("<I", backing_raw, 0x3C)[0],
            "binding": struct.unpack_from("<I", backing_raw, 0x44)[0],
            "target": _hex32(struct.unpack_from("<I", backing_raw, 0xFC)[0]),
            "format": _hex32(struct.unpack_from("<I", backing_raw, 0x100)[0]),
        }
        if alpha_budget is not None:
            result["resident_alpha"] = _resident_alpha_snapshot(
                backend, backing_raw, profile, alpha_budget
            )
    else:
        result["backing"] = None
        if alpha_budget is not None:
            result["resident_alpha"] = {"state": "backing_not_resident"}
    if _read_exact(backend, address, TEXTURE_OBJECT_SIZE, "texture object") != raw:
        raise _UnstableSample("texture object changed during the sample")
    if backing and _read_exact(
        backend, backing, TEXTURE_BACKING_SIZE, "texture backing"
    ) != backing_raw:
        raise _UnstableSample("texture backing changed during the sample")
    return result


def _source_snapshot(
    backend: TerrainMaterialBackend,
    address: int,
    profile: TerrainMaterialProfile,
    alpha_budget: _AlphaReadBudget | None = None,
) -> dict[str, object]:
    raw = _read_exact(backend, address, TERRAIN_OBJECT_SIZE, "terrain source")
    vectors = (
        (0x150, "color texture vector"),
        (0x15C, "GPU mask vector"),
        (0x168, "source mask vector"),
    )
    parsed = [_read_pointer_vector(backend, raw, offset, label) for offset, label in vectors]
    color_pointers, colors, _ = parsed[0]
    gpu_pointers, gpu_masks, _ = parsed[1]
    source_pointers, source_masks, _ = parsed[2]
    if not (len(color_pointers) == len(gpu_pointers) == len(source_pointers)):
        raise TerrainMaterialCaptureError("terrain layer vector counts did not agree")
    layers = []
    for index in range(len(color_pointers)):
        layers.append(
            {
                "index": index,
                "color": _texture_snapshot(backend, color_pointers[index], profile),
                "source_mask": _texture_snapshot(
                    backend, source_pointers[index], profile, alpha_budget
                ),
                "gpu_mask": _texture_snapshot(
                    backend, gpu_pointers[index], profile, alpha_budget
                ),
            }
        )
    base_reference = struct.unpack_from("<I", raw, 0x1A4)[0]
    rotation = struct.unpack_from("<f", raw, 0x1A8)[0]
    if not math.isfinite(rotation):
        raise TerrainMaterialCaptureError("terrain mask rotation was non-finite")
    result = {
        "address": _hex32(address),
        "base": _texture_snapshot(backend, base_reference, profile),
        "color_textures": colors,
        "gpu_mask_copies": gpu_masks,
        "source_alpha_masks": source_masks,
        "layer_vector_counts_agree": True,
        "layers": layers,
        "direction_completion_bits": raw[0x1AC],
        "dirty_flag": raw[0x1AD],
        "mask_rotation_degrees": rotation,
    }
    if _read_exact(backend, address, TERRAIN_OBJECT_SIZE, "terrain source") != raw:
        raise _UnstableSample("terrain source changed during the sample")
    for (offset, label), (_, _, entries) in zip(vectors, parsed, strict=True):
        begin, end, _ = _vector_bounds(raw, offset, label)
        reread = b"" if begin == end else _read_exact(backend, begin, end - begin, label)
        if reread != entries:
            raise _UnstableSample(f"{label} changed during the sample")
    return result


def _shader_snapshot(
    backend: TerrainMaterialBackend,
    profile: TerrainMaterialProfile,
    alpha_budget: _AlphaReadBudget | None = None,
    mesh_budget: MeshReadBudget | None = None,
    staged_ownership: bool = False,
) -> dict[str, object]:
    address = backend.base_address + profile.shader_global_rva
    raw = _read_exact(backend, address, SHADER_SIZE, "terrain shader")
    vtable, mesh_pointer = struct.unpack_from("<II", raw, 0)
    expected_vtable = backend.base_address + profile.shader_vtable_rva
    if vtable != expected_vtable:
        raise TerrainMaterialCompatibilityError("terrain shader vtable did not match")
    owner_pointer = struct.unpack_from("<I", raw, 0x10)[0]
    if not owner_pointer:
        raise _IdleSample("terrain shader has no current owner")
    owner_raw = _read_exact(backend, owner_pointer, OWNER_SIZE, "shader owner")
    source_pointer = struct.unpack_from("<I", owner_raw, 0x10)[0]
    if not source_pointer:
        raise _IdleSample("terrain shader owner has no current source")

    def validate_root() -> None:
        if _read_exact(backend, owner_pointer, OWNER_SIZE, "shader owner") != owner_raw:
            raise _UnstableSample("terrain shader owner changed during the sample")
        if _read_exact(backend, address, SHADER_SIZE, "terrain shader") != raw:
            raise _UnstableSample("terrain shader changed during the sample")

    source_anchor = wrapper_anchor = b""
    if staged_ownership:
        # Bracket the association while it is current, then bracket its data
        # separately. This does not pin objects or assert current draw ownership.
        source_anchor = _read_exact(
            backend, source_pointer, TERRAIN_OBJECT_SIZE, "terrain source anchor"
        )
        if struct.unpack_from("<I", source_anchor)[0] != (
            backend.base_address + TERRAIN_SOURCE_VTABLE_RVA
        ):
            raise TerrainMaterialCaptureError("unreviewed staged terrain source class")
        if mesh_budget is not None and mesh_pointer:
            wrapper_anchor = _read_exact(backend, mesh_pointer, 4, "mesh wrapper anchor")
            if struct.unpack("<I", wrapper_anchor)[0] == (
                backend.base_address + WRAPPER_VTABLE_RVA
            ):
                wrapper_anchor = _read_exact(
                    backend, mesh_pointer, WRAPPER_SIZE, "mesh wrapper anchor"
                )
        validate_root()
    source = _source_snapshot(backend, source_pointer, profile, alpha_budget)
    mesh = None
    if mesh_budget is not None:
        mesh = capture_mesh_snapshot(
            lambda pointer, size, label: _read_exact(backend, pointer, size, label),
            mesh_pointer,
            backend.base_address,
            mesh_budget,
        )
    if staged_ownership:
        if _read_exact(
            backend, source_pointer, TERRAIN_OBJECT_SIZE, "terrain source anchor"
        ) != source_anchor:
            raise _UnstableSample("terrain source changed after root association")
        if wrapper_anchor and _read_exact(
            backend, mesh_pointer, len(wrapper_anchor), "mesh wrapper anchor"
        ) != wrapper_anchor:
            raise _UnstableSample("terrain mesh wrapper changed after root association")
    else:
        validate_root()
    result = {
        "shader_address": _hex32(address),
        "vtable": _hex32(vtable),
        "mesh_pointer": _hex32(mesh_pointer),
        "owner_pointer": _hex32(owner_pointer),
        "source_pointer": _hex32(source_pointer),
        "source": source,
        "ownership_consistency": "staged-root-and-graph" if staged_ownership else "whole-read",
    }
    if mesh is not None:
        result["mesh"] = mesh
    return result


def _validate_snapshot_target(
    backend: TerrainMaterialBackend,
    profile: TerrainMaterialProfile,
    expected_creation_filetime: int,
    include_resident_alpha: bool = False,
    include_mesh: bool = False,
) -> dict[str, object]:
    repaired = _validate_target(backend, profile.branch_profile, expected_creation_filetime)
    actual = backend.read_block(
        backend.base_address + profile.draw_rva, len(profile.draw_signature)
    )
    if actual != profile.draw_signature:
        raise TerrainMaterialCompatibilityError(
            "terrain shader draw entry does not match the reviewed build"
        )
    shader_raw = _read_exact(
        backend,
        backend.base_address + profile.shader_global_rva,
        SHADER_SIZE,
        "terrain shader",
    )
    vtable = struct.unpack_from("<I", shader_raw, 0)[0]
    if vtable != backend.base_address + profile.shader_vtable_rva:
        raise TerrainMaterialCompatibilityError("terrain shader global is not reviewed")
    result = {
        "draw_entry": actual.hex(),
        "shader_vtable": _hex32(vtable),
        "repaired_branches": repaired,
    }
    if include_resident_alpha:
        actual_accessor = backend.read_block(
            backend.base_address + profile.pixel_accessor_rva,
            len(profile.pixel_accessor_signature),
        )
        if actual_accessor != profile.pixel_accessor_signature:
            raise TerrainMaterialCompatibilityError(
                "resident alpha accessor does not match the reviewed build"
            )
        result["pixel_accessor"] = actual_accessor.hex()
    if include_mesh:
        for rva, signature in LAYOUT_SIGNATURES:
            if backend.read_block(backend.base_address + rva, len(signature)) != signature:
                raise TerrainMaterialCompatibilityError("terrain mesh layout signature changed")
        result["mesh_layout_signatures"] = {
            _hex32(rva): signature.hex() for rva, signature in LAYOUT_SIGNATURES
        }
    return result


def capture_terrain_material_poll(
    backend: TerrainMaterialBackend,
    output_path: Path,
    *,
    expected_creation_filetime: int,
    duration_seconds: float = 5.0,
    poll_interval_seconds: float = 0.002,
    include_resident_alpha: bool = False,
    include_mesh: bool = False,
    profile: TerrainMaterialProfile = PROFILE,
    staged_ownership: bool = False,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Retain stable unique source graphs from one reviewed terrain shader."""
    if not 0.1 <= duration_seconds <= 15:
        raise ValueError("duration_seconds must be between 0.1 and 15")
    if not 0 <= poll_interval_seconds <= 0.1:
        raise ValueError("poll_interval_seconds must be between 0 and 0.1")
    if output_path.exists():
        raise FileExistsError(f"refusing to replace existing capture: {output_path}")
    signatures_before = _validate_snapshot_target(
        backend, profile, expected_creation_filetime, include_resident_alpha, include_mesh
    )
    alpha_budget = _AlphaReadBudget() if include_resident_alpha else None
    mesh_budget = MeshReadBudget() if include_mesh else None
    started = monotonic()
    started_utc = _utc_now()
    snapshots: list[dict[str, object]] = []
    fingerprints: set[str] = set()
    polls = idle = discarded = 0
    warnings: list[str] = []
    deadline = started + duration_seconds
    while monotonic() < deadline and polls < MAXIMUM_POLLS and len(snapshots) < MAXIMUM_SNAPSHOTS:
        polls += 1
        try:
            snapshot = _shader_snapshot(
                backend, profile, alpha_budget, mesh_budget, staged_ownership
            )
        except _IdleSample:
            idle += 1
        except (TerrainMaterialCaptureError, TerrainMeshCaptureError, _UnstableSample) as error:
            discarded += 1
            message = str(error)
            if message not in warnings and len(warnings) < 8:
                warnings.append(message)
        else:
            identity = {"source": snapshot["source"]}
            if include_mesh:
                identity["mesh"] = snapshot["mesh"]
            canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
            fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if fingerprint not in fingerprints:
                fingerprints.add(fingerprint)
                snapshot["ordinal"] = len(snapshots) + 1
                snapshot["fingerprint_sha256"] = fingerprint
                snapshot["observed_elapsed_ms"] = round((monotonic() - started) * 1000, 3)
                snapshots.append(snapshot)
        sleep(poll_interval_seconds)
    signatures_after = _validate_snapshot_target(
        backend, profile, expected_creation_filetime, include_resident_alpha, include_mesh
    )
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": "captured" if snapshots else "captured_no_stable_terrain_activity",
        "profile_id": profile.profile_id,
        "started_at_utc": started_utc,
        "completed_at_utc": _utc_now(),
        "elapsed_seconds": round(monotonic() - started, 3),
        "process_id": backend.pid,
        "process_creation_filetime_utc": backend.process_creation_filetime_utc,
        "executable_path": str(backend.executable_path),
        "executable_sha256": backend.executable_sha256,
        "extension_sha256": profile.branch_profile.extension_sha256,
        "image_base": _hex32(backend.base_address),
        "poll_count": polls,
        "stable_poll_count": polls - idle - discarded,
        "idle_poll_count": idle,
        "discarded_unstable_poll_count": discarded,
        "unique_source_count": len({snapshot["source_pointer"] for snapshot in snapshots}),
        "unique_snapshot_count": len(snapshots),
        "warnings": warnings,
        "snapshots": snapshots,
        "signatures_before": signatures_before,
        "signatures_after": signatures_after,
        "limits": {
            "requested_duration_seconds": duration_seconds,
            "requested_poll_interval_seconds": poll_interval_seconds,
            "poll_limit_reached": polls == MAXIMUM_POLLS,
            "snapshot_limit_reached": len(snapshots) == MAXIMUM_SNAPSHOTS,
            "alpha_read_bytes_reserved": alpha_budget.bytes_reserved if alpha_budget else 0,
            "maximum_alpha_read_bytes": MAXIMUM_ALPHA_READ_BYTES,
            "mesh_read_bytes_reserved": mesh_budget.bytes_reserved if mesh_budget else 0,
            "maximum_mesh_read_bytes": MAXIMUM_MESH_READ_BYTES,
        },
        "scope": {
            "process_memory_reads": True,
            "process_memory_writes": False,
            "memory_scans": False,
            "debugger_attached": False,
            "thread_suspend_or_debug_register_changes": False,
            "client_functions_called": False,
            "resident_alpha_requested": include_resident_alpha,
            "mesh_requested": include_mesh,
            "staged_ownership": staged_ownership,
            "pixels_read": bool(alpha_budget and alpha_budget.bytes_reserved),
            "texture_bytes_read": bool(alpha_budget and alpha_budget.bytes_reserved),
            "gpu_readback": False,
            "color_texture_bytes_read": False,
            "game_input": False,
            "maximum_polls": MAXIMUM_POLLS,
            "maximum_unique_snapshots": MAXIMUM_SNAPSHOTS,
            "frame_complete": False,
        },
        "interpretation": (
            "Stable double-checked snapshots link the reviewed terrain shader source graph to "
            "base, layer, source-mask, and generated-mask texture identities. They do not "
            "identify a screen pixel, prove complete frame coverage, exclude all concurrent "
            "ABA changes, or authorize cache mutation. Optional alpha bytes are only "
            "already-resident CPU masks, including CPU copies belonging to GPU-facing "
            "textures; they do not verify GPU storage or prove an upload happened."
            " Staged ownership brackets the root association before the graph read; "
            "that root may advance to another draw before data collection completes. "
            "Neither mode pins object lifetimes or excludes every ABA change."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, indent=2, sort_keys=True, allow_nan=False)
        destination.write("\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation-filetime", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--interval-ms", type=float, default=2.0)
    parser.add_argument("--include-resident-alpha", action="store_true")
    parser.add_argument("--include-mesh", action="store_true")
    parser.add_argument("--staged-ownership", action="store_true")
    options = parser.parse_args(argv)
    process = None
    try:
        process = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", options.pid)
        result = capture_terrain_material_poll(
            process,
            options.output,
            expected_creation_filetime=options.creation_filetime,
            duration_seconds=options.duration,
            poll_interval_seconds=options.interval_ms / 1000,
            include_resident_alpha=options.include_resident_alpha,
            include_mesh=options.include_mesh,
            staged_ownership=options.staged_ownership,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error))
        return 1
    finally:
        if process is not None:
            process.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TerrainMaterialCaptureError",
    "TerrainMaterialCompatibilityError",
    "TerrainMaterialProfile",
    "capture_terrain_material_poll",
]
