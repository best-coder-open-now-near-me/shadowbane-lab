"""Bounded proof of whether the repaired terrain edge-copy branches execute."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from shadowbane_lab.client_observation.native_health import NativeMemoryRegion
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogDebugHit,
    WindowsVendorDialogDebugBackend,
)

SCHEMA_VERSION = 1
MINIMUM_USER_ADDRESS = 0x10000
MAXIMUM_USER_ADDRESS = 0x7FFEFFFF
MAXIMUM_HIT_EVENTS = 128
TERRAIN_OBJECT_SIZE = 0x1AE
EXPECTED_EXECUTABLE_SHA256 = (
    "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8"
)
EXPECTED_EXTENSION_SHA256 = (
    "01e4297798c3c2ca4212d997f0793b8a4af0bb98d429f31d9e07a9dc029f42a4"
)


class TerrainBranchCompatibilityError(RuntimeError):
    """Raised before attachment when the target is not the exact reviewed build."""


class TerrainBranchCaptureError(RuntimeError):
    """Raised when an attached capture cannot remain bounded and attributable."""


@dataclass(frozen=True, slots=True)
class TerrainEdgeBranch:
    role: str
    label: str
    rva: int
    signature: bytes
    direction_bit: int


@dataclass(frozen=True, slots=True)
class TerrainBranchProfile:
    profile_id: str
    executable_sha256: str
    extension_sha256: str
    branches: tuple[TerrainEdgeBranch, ...]

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        for value, name in (
            (self.executable_sha256, "executable_sha256"),
            (self.extension_sha256, "extension_sha256"),
        ):
            digest = value.casefold()
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(f"{name} must be a hexadecimal SHA-256")
        roles = tuple(branch.role for branch in self.branches)
        if roles != (
            "inbound_entry",
            "inbound_complete",
            "outbound_entry",
            "outbound_complete",
        ):
            raise ValueError("profile must define the four debugger transport roles in order")
        if len({branch.rva for branch in self.branches}) != 4:
            raise ValueError("terrain branch RVAs must be unique")
        if any(branch.rva <= 0 or not branch.signature for branch in self.branches):
            raise ValueError("terrain branches require positive RVAs and signatures")


PROFILE = TerrainBranchProfile(
    profile_id="wonderbane-a9a5-terrain-edge-copy-v1",
    executable_sha256=EXPECTED_EXECUTABLE_SHA256,
    extension_sha256=EXPECTED_EXTENSION_SHA256,
    branches=(
        TerrainEdgeBranch("inbound_entry", "edge_0", 0x4AB14A, bytes.fromhex("eb68"), 0x01),
        TerrainEdgeBranch(
            "inbound_complete", "edge_1", 0x4AB80E, bytes.fromhex("e97a000000"), 0x02
        ),
        TerrainEdgeBranch(
            "outbound_entry", "edge_2", 0x4ABE59, bytes.fromhex("e90f010000"), 0x04
        ),
        TerrainEdgeBranch(
            "outbound_complete", "edge_3", 0x4AC60C, bytes.fromhex("e984000000"), 0x08
        ),
    ),
)


class TerrainBranchBackend(Protocol):
    pid: int
    executable_name: str
    executable_path: Path
    executable_sha256: str
    base_address: int
    pointer_size: int
    process_creation_filetime_utc: int

    def read_block(self, address: int, size: int) -> bytes: ...

    def query_region(self, address: int) -> NativeMemoryRegion: ...

    def attach(self, breakpoints: Mapping[str, int]) -> None: ...

    def wait_for_hit(self, timeout_ms: int) -> NativeVendorDialogDebugHit | None: ...

    def continue_hit(
        self,
        hit: NativeVendorDialogDebugHit,
        *,
        disable_role: bool = False,
    ) -> None: ...

    def close(self) -> None: ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _hex32(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08x}"


def _readable_object_region(region: NativeMemoryRegion, address: int, size: int) -> bool:
    return (
        address >= region.base_address
        and address + size <= region.base_address + region.size
        and not region.protection & 0x100
        and not region.protection & 0x01
    )


def _vector(raw: bytes, offset: int) -> dict[str, object]:
    begin, end = struct.unpack_from("<II", raw, offset)
    valid = (
        begin <= end
        and begin % 4 == 0
        and end % 4 == 0
        and (end - begin) // 4 <= 4096
    )
    return {
        "begin": _hex32(begin),
        "end": _hex32(end),
        "count": (end - begin) // 4 if valid else None,
        "bounds_valid": valid,
    }


def _terrain_object_snapshot(
    backend: TerrainBranchBackend,
    address: int,
) -> tuple[dict[str, object] | None, str | None]:
    if (
        address < MINIMUM_USER_ADDRESS
        or address % 4
        or address + TERRAIN_OBJECT_SIZE > MAXIMUM_USER_ADDRESS
    ):
        return None, "EBX was outside the aligned 32-bit user range"
    try:
        region = backend.query_region(address)
        if not _readable_object_region(region, address, TERRAIN_OBJECT_SIZE):
            return None, "EBX object did not fit one readable committed region"
        raw = backend.read_block(address, TERRAIN_OBJECT_SIZE)
    except Exception as error:
        return None, f"bounded terrain-object read failed: {type(error).__name__}"
    if len(raw) != TERRAIN_OBJECT_SIZE:
        return None, "bounded terrain-object read was partial"
    return {
        "address": _hex32(address),
        "color_textures": _vector(raw, 0x150),
        "gpu_mask_copies": _vector(raw, 0x15C),
        "source_alpha_masks": _vector(raw, 0x168),
        "base_reference": _hex32(struct.unpack_from("<I", raw, 0x1A4)[0]),
        "direction_completion_bits": raw[0x1AC],
        "dirty_flag_before_repaired_jump": raw[0x1AD],
    }, None


def _validate_target(
    backend: TerrainBranchBackend,
    profile: TerrainBranchProfile,
    expected_creation_filetime: int,
) -> dict[str, str]:
    if backend.executable_name.casefold() != "sb.exe":
        raise TerrainBranchCompatibilityError(
            f"expected sb.exe, found {backend.executable_name}"
        )
    if backend.executable_sha256.casefold() != profile.executable_sha256.casefold():
        raise TerrainBranchCompatibilityError(
            "running executable SHA-256 is not the reviewed build"
        )
    if backend.pointer_size != 4 or backend.base_address <= 0:
        raise TerrainBranchCompatibilityError("target is not the reviewed 32-bit image layout")
    if backend.process_creation_filetime_utc != expected_creation_filetime:
        raise TerrainBranchCompatibilityError(
            "process creation time does not match the requested lifetime"
        )
    extension_path = backend.executable_path.parent / "wonderbane-extension.dll"
    try:
        extension_sha256 = _sha256(extension_path)
    except OSError as error:
        raise TerrainBranchCompatibilityError("could not read the sibling extension DLL") from error
    if extension_sha256.casefold() != profile.extension_sha256.casefold():
        raise TerrainBranchCompatibilityError(
            "extension DLL SHA-256 is not the reviewed 1.6.13 build"
        )
    signatures: dict[str, str] = {}
    for branch in profile.branches:
        address = backend.base_address + branch.rva
        try:
            actual = backend.read_block(address, len(branch.signature))
        except Exception as error:
            raise TerrainBranchCompatibilityError(
                f"could not verify {branch.label} repaired instruction"
            ) from error
        if actual != branch.signature:
            raise TerrainBranchCompatibilityError(
                f"{branch.label} repaired instruction does not match"
            )
        signatures[branch.label] = actual.hex()
    return signatures


def capture_terrain_branch_hits(
    backend: TerrainBranchBackend,
    output_path: Path,
    *,
    expected_creation_filetime: int,
    timeout_seconds: float = 15.0,
    input_mode: str = "none",
    profile: TerrainBranchProfile = PROFILE,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Capture at most one retained observation per repaired edge-copy branch."""
    if not 1 <= timeout_seconds <= 30:
        raise ValueError("timeout_seconds must be between 1 and 30")
    if input_mode not in {"none", "operator-keyboard"}:
        raise ValueError("input_mode must be none or operator-keyboard")
    if output_path.exists():
        raise FileExistsError(f"refusing to replace existing capture: {output_path}")
    signatures_before = _validate_target(backend, profile, expected_creation_filetime)
    branches_by_role = {branch.role: branch for branch in profile.branches}
    breakpoint_addresses = {
        branch.role: backend.base_address + branch.rva for branch in profile.branches
    }
    started_utc = _utc_now()
    started = monotonic()
    observations: dict[str, dict[str, object]] = {}
    event_count = 0
    signatures_after: dict[str, str] = {}
    capture_error: BaseException | None = None
    try:
        backend.attach(breakpoint_addresses)
        deadline = started + timeout_seconds
        while len(observations) < len(profile.branches):
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            hit = backend.wait_for_hit(min(250, max(1, int(remaining * 1000))))
            if hit is None:
                continue
            event_count += 1
            if event_count > MAXIMUM_HIT_EVENTS:
                raise TerrainBranchCaptureError("terrain branch event limit was exceeded")
            branch = branches_by_role.get(hit.role)
            try:
                if branch is None:
                    raise TerrainBranchCaptureError("debugger reported an unknown branch role")
                expected_address = breakpoint_addresses[hit.role]
                if hit.process_id != backend.pid or hit.instruction_address != expected_address:
                    raise TerrainBranchCaptureError(
                        "debugger hit was not attributable to this target"
                    )
                if hit.role not in observations:
                    terrain_object, warning = _terrain_object_snapshot(
                        backend, int(hit.registers.get("ebx", 0))
                    )
                    observations[hit.role] = {
                        "label": branch.label,
                        "direction_bit": branch.direction_bit,
                        "timestamp_utc": _utc_now(),
                        "elapsed_ms": round((monotonic() - started) * 1000, 3),
                        "thread_id": hit.thread_id,
                        "instruction_address": _hex32(hit.instruction_address),
                        "terrain_object": terrain_object,
                        "read_warning": warning,
                    }
            finally:
                backend.continue_hit(hit, disable_role=True)
        for branch in profile.branches:
            actual = backend.read_block(
                backend.base_address + branch.rva, len(branch.signature)
            )
            signatures_after[branch.label] = actual.hex()
    except BaseException as error:
        capture_error = error
        raise
    finally:
        try:
            backend.close()
        except BaseException:
            if capture_error is None:
                raise
    elapsed = monotonic() - started
    ordered = [
        observations[branch.role]
        for branch in profile.branches
        if branch.role in observations
    ]
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "captured"
            if len(ordered) == 4
            else "captured_no_branch_activity"
            if not ordered
            else "captured_partial"
        ),
        "profile_id": profile.profile_id,
        "started_at_utc": started_utc,
        "completed_at_utc": _utc_now(),
        "elapsed_seconds": round(elapsed, 3),
        "process_id": backend.pid,
        "process_creation_filetime_utc": backend.process_creation_filetime_utc,
        "executable_path": str(backend.executable_path),
        "executable_sha256": backend.executable_sha256,
        "extension_sha256": profile.extension_sha256,
        "image_base": _hex32(backend.base_address),
        "hit_event_count": event_count,
        "unique_branch_count": len(ordered),
        "observations": ordered,
        "repaired_signatures_before": signatures_before,
        "repaired_signatures_while_attached": signatures_after,
        "scope": {
            "client_code_writes": False,
            "client_data_writes": False,
            "memory_scans": False,
            "pixels_read": False,
            "texture_bytes_read": False,
            "thread_debug_registers_temporarily_modified": True,
            "retained_observations_one_per_role": True,
            "breakpoint_role_disabled_on_each_hit": True,
            "game_input": input_mode,
        },
        "interpretation": (
            "A hit proves only that the matching-material edge-copy completion branch executed; "
            "zero hits do not attribute the visible seam to another path without a movement run."
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
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--input-mode", choices=("none", "operator-keyboard"), default="none"
    )
    arguments = parser.parse_args(argv)
    backend: WindowsVendorDialogDebugBackend | None = None
    try:
        if os.name != "nt":
            raise RuntimeError("terrain branch capture must run inside the Windows client VM")
        backend = WindowsVendorDialogDebugBackend.open_unique(
            "sb.exe", process_id=arguments.pid
        )
        result = capture_terrain_branch_hits(
            backend,
            arguments.output,
            expected_creation_filetime=arguments.creation_filetime,
            timeout_seconds=arguments.timeout,
            input_mode=arguments.input_mode,
        )
        print(json.dumps({
            "status": result["status"],
            "output": str(arguments.output),
            "unique_branch_count": result["unique_branch_count"],
            "hit_event_count": result["hit_event_count"],
        }, allow_nan=False))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        if backend is not None:
            try:
                backend.close()
            except RuntimeError:
                pass
        print(json.dumps({"status": "not_captured", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
