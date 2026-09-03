from __future__ import annotations

import hashlib
import json
import struct
import tempfile
from pathlib import Path

import pytest

from shadowbane_lab.client_observation.native_health import NativeMemoryRegion
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogDebugHit,
)
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    TerrainBranchProfile,
    TerrainEdgeBranch,
)
from shadowbane_lab.diagnostics.terrain_material_snapshot import (
    TERRAIN_OBJECT_SIZE,
    TEXTURE_BACKING_SIZE,
    TEXTURE_OBJECT_SIZE,
    TerrainMaterialCompatibilityError,
    TerrainMaterialProfile,
    capture_terrain_material_snapshot,
)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _profile(extension: bytes) -> TerrainMaterialProfile:
    branches = TerrainBranchProfile(
        profile_id="branch-test",
        executable_sha256="ab" * 32,
        extension_sha256=hashlib.sha256(extension).hexdigest(),
        branches=tuple(
            TerrainEdgeBranch(role, f"edge_{index}", 0x1000 + index * 0x100, b"\x90", 1 << index)
            for index, role in enumerate(
                (
                    "inbound_entry",
                    "inbound_complete",
                    "outbound_entry",
                    "outbound_complete",
                )
            )
        ),
    )
    return TerrainMaterialProfile(
        profile_id="material-test",
        branch_profile=branches,
        draw_rva=0x2000,
        draw_signature=b"\x55\x8b\xec",
        shader_vtable_rva=0x3000,
        texture_vtable_rva=0x4000,
    )


class FakeBackend:
    pid = 77
    executable_name = "sb.exe"
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4
    process_creation_filetime_utc = 123456

    def __init__(self, root: Path, profile: TerrainMaterialProfile, clock: Clock) -> None:
        self.executable_path = root / "sb.exe"
        self.memory: dict[int, bytes] = {
            self.base_address + branch.rva: branch.signature
            for branch in profile.branch_profile.branches
        }
        self.memory[self.base_address + profile.draw_rva] = profile.draw_signature
        self.clock = clock
        self.hits: list[NativeVendorDialogDebugHit] = []
        self.attached: dict[str, int] | None = None
        self.continued: list[tuple[str, bool]] = []
        self.closed = False

    def read_block(self, address: int, size: int) -> bytes:
        for start, value in self.memory.items():
            if start <= address and address + size <= start + len(value):
                offset = address - start
                return value[offset : offset + size]
        raise OSError(f"unmapped test read at {address:#x}")

    def query_region(self, address: int) -> NativeMemoryRegion:
        for start, value in self.memory.items():
            if start <= address < start + len(value):
                return NativeMemoryRegion(start, len(value), 4, 0x20000)
        return NativeMemoryRegion(address, 0, 1, 0)

    def attach(self, breakpoints: dict[str, int]) -> None:
        self.attached = dict(breakpoints)

    def wait_for_hit(self, timeout_ms: int) -> NativeVendorDialogDebugHit | None:
        if self.hits:
            self.clock.value += 0.001
            return self.hits.pop(0)
        self.clock.value += timeout_ms / 1000
        return None

    def continue_hit(
        self,
        hit: NativeVendorDialogDebugHit,
        *,
        disable_role: bool = False,
    ) -> None:
        self.continued.append((hit.role, disable_role))

    def close(self) -> None:
        self.closed = True


def _texture(
    profile: TerrainMaterialProfile,
    *,
    resource: int,
    group: int,
    backing: int,
    flags: int = 0,
) -> bytes:
    raw = bytearray(TEXTURE_OBJECT_SIZE)
    struct.pack_into("<I", raw, 0, FakeBackend.base_address + profile.texture_vtable_rva)
    struct.pack_into("<II", raw, 0x10, resource, group)
    raw[0x1C] = flags
    struct.pack_into("<I", raw, 0x5C, backing)
    return bytes(raw)


def _backing(width: int, height: int, binding: int, format_value: int) -> bytes:
    raw = bytearray(TEXTURE_BACKING_SIZE)
    struct.pack_into("<III", raw, 0x38, width, height, 0)
    struct.pack_into("<I", raw, 0x44, binding)
    struct.pack_into("<II", raw, 0xFC, 0x0DE1, format_value)
    return bytes(raw)


def _install_scene(backend: FakeBackend, profile: TerrainMaterialProfile) -> int:
    shader_address = 0x600000
    owner_address = 0x601000
    source_address = 0x602000
    base_address = 0x710000
    color_address = 0x711000
    source_mask_address = 0x712000
    gpu_mask_address = 0x713000
    base_backing = 0x720000
    color_backing = 0x721000
    source_backing = 0x722000
    gpu_backing = 0x723000

    shader = bytearray(0x34)
    struct.pack_into("<II", shader, 0, backend.base_address + profile.shader_vtable_rva, 0x603000)
    struct.pack_into("<I", shader, 0x10, owner_address)
    backend.memory[shader_address] = bytes(shader)
    owner = bytearray(0x14)
    struct.pack_into("<I", owner, 0x10, source_address)
    backend.memory[owner_address] = bytes(owner)

    vectors = (
        (0x150, 0x700000, color_address),
        (0x15C, 0x700100, gpu_mask_address),
        (0x168, 0x700200, source_mask_address),
    )
    source = bytearray(TERRAIN_OBJECT_SIZE)
    for offset, vector_address, pointer in vectors:
        struct.pack_into(
            "<III", source, offset, vector_address, vector_address + 4, vector_address + 4
        )
        backend.memory[vector_address] = struct.pack("<I", pointer)
    struct.pack_into("<I", source, 0x1A4, base_address)
    source[0x1AC] = 15
    backend.memory[source_address] = bytes(source)

    backend.memory[base_address] = _texture(profile, resource=10, group=20, backing=base_backing)
    backend.memory[color_address] = _texture(profile, resource=11, group=21, backing=color_backing)
    backend.memory[source_mask_address] = _texture(
        profile, resource=12, group=22, backing=source_backing, flags=0x10
    )
    backend.memory[gpu_mask_address] = _texture(
        profile, resource=0, group=0, backing=gpu_backing, flags=1
    )
    backend.memory[base_backing] = _backing(256, 256, 1243, 0x1907)
    backend.memory[color_backing] = _backing(256, 256, 1247, 0x1907)
    backend.memory[source_backing] = _backing(64, 64, 1257, 0x1906)
    backend.memory[gpu_backing] = _backing(64, 64, 1260, 0x1906)
    return shader_address


def _hit(profile: TerrainMaterialProfile, shader_address: int) -> NativeVendorDialogDebugHit:
    address = FakeBackend.base_address + profile.draw_rva
    return NativeVendorDialogDebugHit(
        role="inbound_entry",
        process_id=FakeBackend.pid,
        thread_id=9,
        instruction_address=address,
        registers={"ecx": shader_address, "eip": address},
    )


def test_captures_one_visible_sequence_and_links_texture_ownership() -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    clock = Clock()
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / "wonderbane-extension.dll").write_bytes(extension)
        backend = FakeBackend(root, profile, clock)
        shader_address = _install_scene(backend, profile)
        backend.hits = [_hit(profile, shader_address), _hit(profile, shader_address)]
        output = root / "snapshot.json"

        result = capture_terrain_material_snapshot(
            backend,
            output,
            expected_creation_filetime=backend.process_creation_filetime_utc,
            timeout_seconds=2,
            profile=profile,
            monotonic=clock,
        )

        saved = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "captured_frame"
    assert saved["event_count"] == 2
    assert saved["unique_source_count"] == 1
    assert saved["direction_completion_histogram"] == {"15": 1}
    source = saved["snapshots"][0]["source"]
    assert source["layer_vector_counts_agree"] is True
    assert source["base"]["token"]["archive_group"] == 20
    assert source["base"]["backing"]["binding"] == 1243
    assert source["layers"][0]["color"]["token"]["archive_resource"] == 11
    assert source["layers"][0]["source_mask"]["flags"] == 0x10
    assert source["layers"][0]["gpu_mask"]["token"]["generated_or_unattributed"] is True
    assert source["layers"][0]["gpu_mask"]["backing"]["format"] == "0x00001906"
    assert backend.continued == [("inbound_entry", False), ("inbound_entry", False)]
    assert backend.closed is True
    assert saved["scope"]["client_data_writes"] is False


def test_draw_signature_drift_fails_before_attach() -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    clock = Clock()
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / "wonderbane-extension.dll").write_bytes(extension)
        backend = FakeBackend(root, profile, clock)
        backend.memory[backend.base_address + profile.draw_rva] = b"\x90" * 3

        with pytest.raises(TerrainMaterialCompatibilityError, match="draw entry"):
            capture_terrain_material_snapshot(
                backend,
                root / "snapshot.json",
                expected_creation_filetime=backend.process_creation_filetime_utc,
                timeout_seconds=1,
                profile=profile,
                monotonic=clock,
            )

    assert backend.attached is None
    assert backend.closed is False
