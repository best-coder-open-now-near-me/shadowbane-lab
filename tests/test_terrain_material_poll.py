from __future__ import annotations

import hashlib
import json
import struct
import tempfile
from pathlib import Path

import pytest

from shadowbane_lab.client_observation.native_health import NativeMemoryRegion
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    TerrainBranchProfile,
    TerrainEdgeBranch,
)
from shadowbane_lab.diagnostics.terrain_material_poll import (
    OWNER_SIZE,
    SHADER_SIZE,
    TERRAIN_OBJECT_SIZE,
    TEXTURE_BACKING_SIZE,
    TEXTURE_OBJECT_SIZE,
    TerrainMaterialCompatibilityError,
    TerrainMaterialProfile,
    capture_terrain_material_poll,
)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += max(seconds, 0.01)


def _profile(extension: bytes) -> TerrainMaterialProfile:
    branch = TerrainBranchProfile(
        profile_id="branch-test",
        executable_sha256="ab" * 32,
        extension_sha256=hashlib.sha256(extension).hexdigest(),
        branches=tuple(
            TerrainEdgeBranch(role, f"edge_{index}", 0x1000 + index * 0x100, b"\x90", 1 << index)
            for index, role in enumerate(
                ("inbound_entry", "inbound_complete", "outbound_entry", "outbound_complete")
            )
        ),
    )
    return TerrainMaterialProfile(
        profile_id="material-test",
        branch_profile=branch,
        draw_rva=0x2000,
        draw_signature=b"\x55\x8b\xec",
        shader_global_rva=0x3000,
        shader_vtable_rva=0x4000,
        texture_vtable_rva=0x5000,
    )


class FakeBackend:
    pid = 77
    executable_name = "sb.exe"
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4
    process_creation_filetime_utc = 123456

    def __init__(self, root: Path, profile: TerrainMaterialProfile) -> None:
        self.executable_path = root / "sb.exe"
        self.memory: dict[int, bytes] = {
            self.base_address + branch.rva: branch.signature
            for branch in profile.branch_profile.branches
        }
        self.memory[self.base_address + profile.draw_rva] = profile.draw_signature
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
        return NativeMemoryRegion(address, 1, 1, 0)

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
    struct.pack_into("<II", raw, 0x38, width, height)
    struct.pack_into("<I", raw, 0x44, binding)
    struct.pack_into("<II", raw, 0xFC, 0x0DE1, format_value)
    return bytes(raw)


def _install_scene(backend: FakeBackend, profile: TerrainMaterialProfile) -> None:
    shader = backend.base_address + profile.shader_global_rva
    owner, source = 0x601000, 0x602000
    base, color, source_mask, gpu_mask = 0x710000, 0x711000, 0x712000, 0x713000
    base_backing, color_backing, source_backing, gpu_backing = (
        0x720000,
        0x721000,
        0x722000,
        0x723000,
    )
    shader_raw = bytearray(SHADER_SIZE)
    struct.pack_into(
        "<II", shader_raw, 0, backend.base_address + profile.shader_vtable_rva, 0x603000
    )
    struct.pack_into("<I", shader_raw, 0x10, owner)
    backend.memory[shader] = bytes(shader_raw)
    owner_raw = bytearray(OWNER_SIZE)
    struct.pack_into("<I", owner_raw, 0x10, source)
    backend.memory[owner] = bytes(owner_raw)
    source_raw = bytearray(TERRAIN_OBJECT_SIZE)
    for offset, vector, pointer in (
        (0x150, 0x700000, color),
        (0x15C, 0x700100, gpu_mask),
        (0x168, 0x700200, source_mask),
    ):
        struct.pack_into("<III", source_raw, offset, vector, vector + 4, vector + 4)
        backend.memory[vector] = struct.pack("<I", pointer)
    struct.pack_into("<I", source_raw, 0x1A4, base)
    source_raw[0x1AC] = 15
    backend.memory[source] = bytes(source_raw)
    backend.memory[base] = _texture(profile, resource=10, group=20, backing=base_backing)
    backend.memory[color] = _texture(profile, resource=11, group=21, backing=color_backing)
    backend.memory[source_mask] = _texture(
        profile, resource=12, group=22, backing=source_backing, flags=0x10
    )
    backend.memory[gpu_mask] = _texture(profile, resource=0, group=0, backing=gpu_backing)
    backend.memory[base_backing] = _backing(256, 256, 1243, 0x1907)
    backend.memory[color_backing] = _backing(256, 256, 1247, 0x1907)
    backend.memory[source_backing] = _backing(64, 64, 1257, 0x1906)
    backend.memory[gpu_backing] = _backing(64, 64, 1260, 0x1906)


def test_polls_stable_global_without_debugger_and_links_texture_ownership() -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    clock = Clock()
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / "wonderbane-extension.dll").write_bytes(extension)
        backend = FakeBackend(root, profile)
        _install_scene(backend, profile)
        output = root / "material-poll.json"

        result = capture_terrain_material_poll(
            backend,
            output,
            expected_creation_filetime=backend.process_creation_filetime_utc,
            duration_seconds=0.1,
            poll_interval_seconds=0.01,
            profile=profile,
            monotonic=clock,
            sleep=clock.sleep,
        )

        saved = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "captured"
    assert saved["unique_source_count"] == 1
    source = saved["snapshots"][0]["source"]
    assert source["base"]["token"]["archive_group"] == 20
    assert source["base"]["backing"]["binding"] == 1243
    assert source["layers"][0]["color"]["token"]["archive_resource"] == 11
    assert source["layers"][0]["source_mask"]["flags"] == 0x10
    assert source["layers"][0]["gpu_mask"]["token"]["generated_or_unattributed"] is True
    assert saved["scope"]["debugger_attached"] is False
    assert saved["scope"]["process_memory_writes"] is False


def test_draw_signature_drift_fails_before_poll_or_output() -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    clock = Clock()
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / "wonderbane-extension.dll").write_bytes(extension)
        backend = FakeBackend(root, profile)
        _install_scene(backend, profile)
        backend.memory[backend.base_address + profile.draw_rva] = b"\x90" * 3
        output = root / "material-poll.json"

        with pytest.raises(TerrainMaterialCompatibilityError, match="draw entry"):
            capture_terrain_material_poll(
                backend,
                output,
                expected_creation_filetime=backend.process_creation_filetime_utc,
                duration_seconds=0.1,
                profile=profile,
                monotonic=clock,
                sleep=clock.sleep,
            )

        assert not output.exists()


def test_existing_output_is_never_replaced() -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    clock = Clock()
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / "wonderbane-extension.dll").write_bytes(extension)
        backend = FakeBackend(root, profile)
        _install_scene(backend, profile)
        output = root / "material-poll.json"
        output.write_text("keep", encoding="utf-8")

        with pytest.raises(FileExistsError, match="refusing to replace"):
            capture_terrain_material_poll(
                backend,
                output,
                expected_creation_filetime=backend.process_creation_filetime_utc,
                duration_seconds=0.1,
                profile=profile,
                monotonic=clock,
                sleep=clock.sleep,
            )

        assert output.read_text(encoding="utf-8") == "keep"


def _capture(backend: FakeBackend, root: Path, profile: TerrainMaterialProfile) -> dict:
    clock = Clock()
    return capture_terrain_material_poll(
        backend,
        root / "material-poll.json",
        expected_creation_filetime=backend.process_creation_filetime_utc,
        duration_seconds=0.1,
        poll_interval_seconds=0.01,
        profile=profile,
        monotonic=clock,
        sleep=clock.sleep,
    )


def test_unknown_texture_class_is_not_cast_to_reviewed_layout(tmp_path: Path) -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    (tmp_path / "wonderbane-extension.dll").write_bytes(extension)
    backend = FakeBackend(tmp_path, profile)
    _install_scene(backend, profile)
    # Only the vtable word is readable; layout reads would fail this sample.
    backend.memory[0x711000] = struct.pack("<I", 0x499999)
    result = _capture(backend, tmp_path, profile)
    color = result["snapshots"][0]["source"]["layers"][0]["color"]
    assert color["reviewed_color_texture"] is False
    assert "token" not in color
    assert "backing" not in color


def test_idle_shader_is_reported_without_inventing_terrain(tmp_path: Path) -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    (tmp_path / "wonderbane-extension.dll").write_bytes(extension)
    backend = FakeBackend(tmp_path, profile)
    _install_scene(backend, profile)
    address = backend.base_address + profile.shader_global_rva
    raw = bytearray(backend.memory[address])
    struct.pack_into("<I", raw, 0x10, 0)
    backend.memory[address] = bytes(raw)
    result = _capture(backend, tmp_path, profile)
    assert result["status"] == "captured_no_stable_terrain_activity"
    assert result["idle_poll_count"] == result["poll_count"]
    assert result["snapshots"] == []


def test_changing_source_is_discarded(tmp_path: Path) -> None:
    class ChangingBackend(FakeBackend):
        reads = 0

        def read_block(self, address: int, size: int) -> bytes:
            raw = super().read_block(address, size)
            if address == 0x602000 and size == TERRAIN_OBJECT_SIZE:
                self.reads += 1
                changed = bytearray(raw)
                changed[0x1AD] = self.reads % 2
                return bytes(changed)
            return raw

    extension = b"reviewed extension"
    profile = _profile(extension)
    (tmp_path / "wonderbane-extension.dll").write_bytes(extension)
    backend = ChangingBackend(tmp_path, profile)
    _install_scene(backend, profile)
    result = _capture(backend, tmp_path, profile)
    assert result["status"] == "captured_no_stable_terrain_activity"
    assert result["discarded_unstable_poll_count"] == result["poll_count"]
    assert result["snapshots"] == []


def test_oversized_vector_is_rejected_before_reading_entries(tmp_path: Path) -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    (tmp_path / "wonderbane-extension.dll").write_bytes(extension)
    backend = FakeBackend(tmp_path, profile)
    _install_scene(backend, profile)
    raw = bytearray(backend.memory[0x602000])
    struct.pack_into("<III", raw, 0x150, 0x700000, 0x700084, 0x700084)
    backend.memory[0x602000] = bytes(raw)
    result = _capture(backend, tmp_path, profile)
    assert result["snapshots"] == []
    assert "color texture vector bounds were invalid" in result["warnings"]


def test_post_capture_signature_drift_prevents_publication(tmp_path: Path) -> None:
    extension = b"reviewed extension"
    profile = _profile(extension)
    (tmp_path / "wonderbane-extension.dll").write_bytes(extension)
    backend = FakeBackend(tmp_path, profile)
    _install_scene(backend, profile)
    clock = Clock()

    def drift_after_sample(seconds: float) -> None:
        backend.memory[backend.base_address + profile.draw_rva] = b"\x90" * 3
        clock.sleep(seconds)

    output = tmp_path / "material-poll.json"
    with pytest.raises(TerrainMaterialCompatibilityError, match="draw entry"):
        capture_terrain_material_poll(
            backend,
            output,
            expected_creation_filetime=backend.process_creation_filetime_utc,
            duration_seconds=0.1,
            poll_interval_seconds=0.1,
            profile=profile,
            monotonic=clock,
            sleep=drift_after_sample,
        )
    assert not output.exists()
