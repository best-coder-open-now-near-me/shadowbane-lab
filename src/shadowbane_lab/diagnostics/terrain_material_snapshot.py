"""Capture one bounded frame of terrain material ownership from a reviewed client."""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from shadowbane_lab.client_observation.native_health import (
    NativeMemoryRegion,
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogDetachError,
    WindowsVendorDialogDebugBackend,
)
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    PROFILE as TERRAIN_BRANCH_PROFILE,
)
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    TerrainBranchBackend,
    TerrainBranchProfile,
    _hex32,
    _remote_debugger_present,
    _utc_now,
    _validate_target,
)

SCHEMA_VERSION = 1
MINIMUM_USER_ADDRESS = 0x10000
MAXIMUM_USER_ADDRESS = 0x7FFEFFFF
SHADER_SIZE = 0x34
OWNER_SIZE = 0x14
TERRAIN_OBJECT_SIZE = 0x1AE
TEXTURE_OBJECT_SIZE = 0x60
TEXTURE_BACKING_SIZE = 0x104
MAXIMUM_LAYERS = 32
MAXIMUM_SNAPSHOTS = 64
MAXIMUM_HIT_EVENTS = 128
BREAKPOINT_ROLES = (
    "inbound_entry",
    "inbound_complete",
    "outbound_entry",
    "outbound_complete",
)


class TerrainMaterialCompatibilityError(RuntimeError):
    """Raised before attachment when the target is not the reviewed layout."""


class TerrainMaterialCaptureError(RuntimeError):
    """Raised when the bounded snapshot cannot remain attributable."""


@dataclass(frozen=True, slots=True)
class TerrainMaterialProfile:
    profile_id: str
    branch_profile: TerrainBranchProfile
    draw_rva: int
    draw_signature: bytes
    shader_vtable_rva: int
    texture_vtable_rva: int

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        if min(self.draw_rva, self.shader_vtable_rva, self.texture_vtable_rva) <= 0:
            raise ValueError("reviewed terrain RVAs must be positive")
        if not self.draw_signature:
            raise ValueError("draw_signature must not be empty")


PROFILE = TerrainMaterialProfile(
    profile_id="wonderbane-a9a5-terrain-material-snapshot-v1",
    branch_profile=TERRAIN_BRANCH_PROFILE,
    draw_rva=0x4F1660,
    draw_signature=bytes.fromhex("558bec515356"),
    shader_vtable_rva=0x11625A4,
    texture_vtable_rva=0x114A39C,
)


class TerrainMaterialBackend(TerrainBranchBackend, Protocol):
    pass


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
    region = backend.query_region(address)
    if not _readable_region(region, address, size):
        raise TerrainMaterialCaptureError(f"{label} did not fit one readable region")
    raw = backend.read_block(address, size)
    if len(raw) != size:
        raise TerrainMaterialCaptureError(f"{label} read was partial")
    return raw


def _pointer_vector(
    backend: TerrainMaterialBackend,
    raw: bytes,
    offset: int,
    label: str,
) -> tuple[list[int], dict[str, object]]:
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
        result["read_warning"] = f"{label} bounds were invalid or exceeded the layer limit"
        return [], result
    if begin == end:
        return [], result
    try:
        entries = _read_exact(backend, begin, end - begin, f"{label} entries")
    except TerrainMaterialCaptureError as error:
        result["read_warning"] = str(error)
        return [], result
    pointers = list(struct.unpack(f"<{len(entries) // 4}I", entries))
    result["pointers"] = [_hex32(value) for value in pointers]
    return pointers, result


def _texture_snapshot(
    backend: TerrainMaterialBackend,
    address: int,
    profile: TerrainMaterialProfile,
) -> dict[str, object] | None:
    if not address:
        return None
    result: dict[str, object] = {"address": _hex32(address)}
    try:
        raw = _read_exact(backend, address, TEXTURE_OBJECT_SIZE, "texture object")
    except TerrainMaterialCaptureError as error:
        result["read_warning"] = str(error)
        return result
    vtable = struct.unpack_from("<I", raw, 0)[0]
    expected_vtable = backend.base_address + profile.texture_vtable_rva
    resource, group = struct.unpack_from("<II", raw, 0x10)
    backing = struct.unpack_from("<I", raw, 0x5C)[0]
    result.update(
        {
            "vtable": _hex32(vtable),
            "reviewed_color_texture": vtable == expected_vtable,
            "token": {
                "archive_group": group,
                "archive_resource": resource,
                "in_memory_hex": raw[0x10:0x18].hex(),
                "generated_or_unattributed": resource == 0 and group == 0,
            },
            "flags": raw[0x1C],
            "backing_address": _hex32(backing),
        }
    )
    if not backing:
        result["backing"] = None
        return result
    try:
        backing_raw = _read_exact(backend, backing, TEXTURE_BACKING_SIZE, "texture backing")
    except TerrainMaterialCaptureError as error:
        result["backing"] = {"read_warning": str(error)}
        return result
    result["backing"] = {
        "width": struct.unpack_from("<I", backing_raw, 0x38)[0],
        "height": struct.unpack_from("<I", backing_raw, 0x3C)[0],
        "binding": struct.unpack_from("<I", backing_raw, 0x44)[0],
        "target": _hex32(struct.unpack_from("<I", backing_raw, 0xFC)[0]),
        "format": _hex32(struct.unpack_from("<I", backing_raw, 0x100)[0]),
    }
    return result


def _terrain_source_snapshot(
    backend: TerrainMaterialBackend,
    address: int,
    profile: TerrainMaterialProfile,
) -> dict[str, object]:
    raw = _read_exact(backend, address, TERRAIN_OBJECT_SIZE, "terrain source")
    color_pointers, colors = _pointer_vector(backend, raw, 0x150, "color texture vector")
    gpu_pointers, gpu_masks = _pointer_vector(backend, raw, 0x15C, "GPU mask vector")
    source_pointers, source_masks = _pointer_vector(backend, raw, 0x168, "source mask vector")
    layer_count = max(len(color_pointers), len(gpu_pointers), len(source_pointers))
    layers = []
    for index in range(layer_count):
        layers.append(
            {
                "index": index,
                "color": _texture_snapshot(
                    backend,
                    color_pointers[index] if index < len(color_pointers) else 0,
                    profile,
                ),
                "source_mask": _texture_snapshot(
                    backend,
                    source_pointers[index] if index < len(source_pointers) else 0,
                    profile,
                ),
                "gpu_mask": _texture_snapshot(
                    backend,
                    gpu_pointers[index] if index < len(gpu_pointers) else 0,
                    profile,
                ),
            }
        )
    base_reference = struct.unpack_from("<I", raw, 0x1A4)[0]
    return {
        "address": _hex32(address),
        "base": _texture_snapshot(backend, base_reference, profile),
        "color_textures": colors,
        "gpu_mask_copies": gpu_masks,
        "source_alpha_masks": source_masks,
        "layer_vector_counts_agree": (
            len(color_pointers) == len(gpu_pointers) == len(source_pointers)
        ),
        "layers": layers,
        "direction_completion_bits": raw[0x1AC],
        "dirty_flag": raw[0x1AD],
    }


def _shader_snapshot(
    backend: TerrainMaterialBackend,
    address: int,
    profile: TerrainMaterialProfile,
) -> dict[str, object]:
    raw = _read_exact(backend, address, SHADER_SIZE, "terrain shader")
    vtable, mesh_pointer = struct.unpack_from("<II", raw, 0)
    owner_pointer = struct.unpack_from("<I", raw, 0x10)[0]
    expected_vtable = backend.base_address + profile.shader_vtable_rva
    result: dict[str, object] = {
        "address": _hex32(address),
        "vtable": _hex32(vtable),
        "reviewed_custom_terrain_shader": vtable == expected_vtable,
        "mesh_pointer": _hex32(mesh_pointer),
        "owner_pointer": _hex32(owner_pointer),
    }
    if vtable != expected_vtable:
        result["read_warning"] = "shader vtable did not match the reviewed class"
        return result
    owner_raw = _read_exact(backend, owner_pointer, OWNER_SIZE, "shader owner")
    source_pointer = struct.unpack_from("<I", owner_raw, 0x10)[0]
    result["source_pointer"] = _hex32(source_pointer)
    result["source"] = _terrain_source_snapshot(backend, source_pointer, profile)
    return result


def _validate_snapshot_target(
    backend: TerrainMaterialBackend,
    profile: TerrainMaterialProfile,
    expected_creation_filetime: int,
) -> dict[str, object]:
    repaired = _validate_target(backend, profile.branch_profile, expected_creation_filetime)
    actual = backend.read_block(
        backend.base_address + profile.draw_rva, len(profile.draw_signature)
    )
    if actual != profile.draw_signature:
        raise TerrainMaterialCompatibilityError(
            "terrain shader draw entry does not match the reviewed build"
        )
    return {"draw_entry": actual.hex(), "repaired_branches": repaired}


def _breakpoints(address: int) -> dict[str, int]:
    # The debugger transport owns four x86 debug registers. Pointing all four at
    # one reviewed entry keeps this diagnostic single-site.
    return {role: address for role in BREAKPOINT_ROLES}


def capture_terrain_material_snapshot(
    backend: TerrainMaterialBackend,
    output_path: Path,
    *,
    expected_creation_filetime: int,
    timeout_seconds: float = 5.0,
    profile: TerrainMaterialProfile = PROFILE,
    monotonic: Callable[[], float] = time.monotonic,
    allow_process_exit_detach: bool = False,
) -> dict[str, object]:
    """Capture unique visible terrain sources until the shader sequence wraps."""
    if not 1 <= timeout_seconds <= 15:
        raise ValueError("timeout_seconds must be between 1 and 15")
    if output_path.exists():
        raise FileExistsError(f"refusing to replace existing capture: {output_path}")
    signatures_before = _validate_snapshot_target(backend, profile, expected_creation_filetime)
    draw_address = backend.base_address + profile.draw_rva
    started = monotonic()
    started_utc = _utc_now()
    snapshots: list[dict[str, object]] = []
    seen_sources: set[str] = set()
    event_count = 0
    frame_wrapped = False
    capture_error: BaseException | None = None
    explicit_detach_error: str | None = None
    try:
        backend.attach(_breakpoints(draw_address))
        deadline = started + timeout_seconds
        while not frame_wrapped and len(snapshots) < MAXIMUM_SNAPSHOTS:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            hit = backend.wait_for_hit(min(250, max(1, int(remaining * 1000))))
            if hit is None:
                continue
            event_count += 1
            if event_count > MAXIMUM_HIT_EVENTS:
                raise TerrainMaterialCaptureError("terrain draw event limit was exceeded")
            try:
                if hit.process_id != backend.pid or hit.instruction_address != draw_address:
                    raise TerrainMaterialCaptureError(
                        "debugger hit was not attributable to the reviewed terrain draw"
                    )
                shader = _shader_snapshot(backend, int(hit.registers.get("ecx", 0)), profile)
                source_key = shader.get("source_pointer")
                if isinstance(source_key, str) and source_key in seen_sources:
                    frame_wrapped = True
                else:
                    if isinstance(source_key, str):
                        seen_sources.add(source_key)
                    shader["ordinal"] = len(snapshots) + 1
                    shader["thread_id"] = hit.thread_id
                    shader["timestamp_utc"] = _utc_now()
                    snapshots.append(shader)
            finally:
                backend.continue_hit(hit, disable_role=False)
        signatures_while_attached = _validate_snapshot_target(
            backend, profile, expected_creation_filetime
        )
    except BaseException as error:
        capture_error = error
        raise
    finally:
        try:
            backend.close()
        except NativeVendorDialogDetachError as error:
            if capture_error is None and allow_process_exit_detach:
                explicit_detach_error = str(error)
            elif capture_error is None:
                raise
        except BaseException:
            if capture_error is None:
                raise
    direction_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}
    for shader in snapshots:
        source = shader.get("source")
        if not isinstance(source, Mapping):
            continue
        direction = str(source.get("direction_completion_bits"))
        direction_counts[direction] = direction_counts.get(direction, 0) + 1
        layers = source.get("layers")
        count = len(layers) if isinstance(layers, list) else 0
        layer_counts[str(count)] = layer_counts.get(str(count), 0) + 1
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "captured_frame"
            if frame_wrapped and snapshots
            else "captured_partial"
            if snapshots
            else "captured_no_terrain_activity"
        ),
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
        "event_count": event_count,
        "unique_source_count": len(seen_sources),
        "frame_wrapped": frame_wrapped,
        "direction_completion_histogram": direction_counts,
        "layer_count_histogram": layer_counts,
        "snapshots": snapshots,
        "signatures_before": signatures_before,
        "signatures_while_attached": signatures_while_attached,
        "cleanup": {
            "debug_register_clear_completed": True,
            "explicit_detach_succeeded": explicit_detach_error is None,
            "process_exit_detach_required": explicit_detach_error is not None,
            "explicit_detach_error": explicit_detach_error,
        },
        "scope": {
            "client_code_writes": False,
            "client_data_writes": False,
            "memory_scans": False,
            "pixels_read": False,
            "texture_bytes_read": False,
            "thread_debug_registers_temporarily_modified": True,
            "retained_unique_sources_only": True,
            "maximum_source_snapshots": MAXIMUM_SNAPSHOTS,
        },
        "interpretation": (
            "This links the reviewed terrain shader's visible source objects to base, color, "
            "source-mask, and generated-mask texture identities. It does not identify a screen "
            "pixel or authorize cache mutation."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as destination:
        json.dump(result, destination, indent=2, sort_keys=True, allow_nan=False)
        destination.write("\n")
    return result


def _read_worker_result(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise TerrainMaterialCaptureError("debugger worker result is missing or oversized")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise TerrainMaterialCaptureError("debugger worker result has the wrong schema")
    return payload


def _supervised_capture(
    *,
    process_id: int,
    creation_filetime: int,
    output_path: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    if output_path.exists():
        raise FileExistsError(f"refusing to replace existing capture: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending = output_path.with_name(f".{output_path.name}.{uuid4().hex}.debugger-worker")
    command = [
        sys.executable,
        "-m",
        "shadowbane_lab.diagnostics.terrain_material_snapshot",
        "--worker",
        "--pid",
        str(process_id),
        "--creation-filetime",
        str(creation_filetime),
        "--output",
        str(pending),
        "--timeout",
        str(timeout_seconds),
    ]
    try:
        worker = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 20,
        )
        if worker.returncode != 0:
            detail = worker.stdout.strip() or worker.stderr.strip() or "no worker detail"
            raise TerrainMaterialCaptureError(f"debugger worker failed: {detail}")
        result = _read_worker_result(pending)
        if (
            result.get("process_id") != process_id
            or result.get("process_creation_filetime_utc") != creation_filetime
        ):
            raise TerrainMaterialCaptureError("debugger worker result lifetime does not match")
        process = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", process_id)
        try:
            signatures = _validate_snapshot_target(process, PROFILE, creation_filetime)
            if _remote_debugger_present(process_id):
                raise TerrainMaterialCaptureError(
                    "debugger remained attached after its worker exited"
                )
        finally:
            process.close()
        cleanup = result.get("cleanup")
        if (
            not isinstance(cleanup, dict)
            or cleanup.get("debug_register_clear_completed") is not True
        ):
            raise TerrainMaterialCaptureError("debugger worker did not confirm register cleanup")
        cleanup["debugger_worker_exited"] = True
        cleanup["post_exit_debugger_present"] = False
        cleanup["post_exit_signatures"] = signatures
        with output_path.open("x", encoding="utf-8") as destination:
            json.dump(result, destination, indent=2, sort_keys=True, allow_nan=False)
            destination.write("\n")
        return result
    finally:
        pending.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--creation-filetime", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args(argv)
    try:
        if options.worker:
            backend = WindowsVendorDialogDebugBackend.open_unique("sb.exe", process_id=options.pid)
            result = capture_terrain_material_snapshot(
                backend,
                options.output,
                expected_creation_filetime=options.creation_filetime,
                timeout_seconds=options.timeout,
                allow_process_exit_detach=True,
            )
        else:
            result = _supervised_capture(
                process_id=options.pid,
                creation_filetime=options.creation_filetime,
                output_path=options.output,
                timeout_seconds=options.timeout,
            )
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TerrainMaterialCaptureError",
    "TerrainMaterialCompatibilityError",
    "TerrainMaterialProfile",
    "capture_terrain_material_snapshot",
]
