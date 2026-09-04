from __future__ import annotations

import base64
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
        backing_vtable_rva=0x6000,
        pixel_accessor_rva=0x7000,
        pixel_accessor_signature=b"reviewed accessor",
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
        self.memory[self.base_address + profile.pixel_accessor_rva] = (
            profile.pixel_accessor_signature
        )
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


def _capture(
    backend: FakeBackend, root: Path, profile: TerrainMaterialProfile, **options: object
) -> dict:
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
        **options,
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


def _install_alpha(backend: FakeBackend, profile: TerrainMaterialProfile) -> bytes:
    pixels = bytes(range(256)) * 16
    for backing, pointer in ((0x722000, 0x800000), (0x723000, 0x810000)):
        raw = bytearray(backend.memory[backing])
        struct.pack_into("<I", raw, 0, backend.base_address + profile.backing_vtable_rva)
        struct.pack_into("<I", raw, 0x40, 1)
        struct.pack_into("<I", raw, 0x5C, pointer)
        backend.memory[backing] = bytes(raw)
        backend.memory[pointer] = pixels
    return pixels


@pytest.fixture
def alpha_scene(tmp_path: Path) -> tuple[FakeBackend, TerrainMaterialProfile, bytes]:
    extension = b"reviewed extension"
    profile = _profile(extension)
    (tmp_path / "wonderbane-extension.dll").write_bytes(extension)
    backend = FakeBackend(tmp_path, profile)
    _install_scene(backend, profile)
    return backend, profile, _install_alpha(backend, profile)


def test_resident_alpha_is_opt_in_and_never_reads_color_bytes(tmp_path, alpha_scene):
    backend, profile, pixels = alpha_scene
    result = _capture(backend, tmp_path, profile, include_resident_alpha=True)
    source = result["snapshots"][0]["source"]
    for role in ("source_mask", "gpu_mask"):
        alpha = source["layers"][0][role]["resident_alpha"]
        assert alpha["state"] == "captured"
        assert base64.b64decode(alpha["bytes_base64"]) == pixels
        assert alpha["sha256"] == hashlib.sha256(pixels).hexdigest()
        assert alpha["byte_count"] == 4096
    assert "resident_alpha" not in source["base"]
    assert "resident_alpha" not in source["layers"][0]["color"]
    assert result["scope"]["gpu_readback"] is False
    assert result["scope"]["color_texture_bytes_read"] is False
    assert result["scope"]["pixels_read"] is True
    assert result["signatures_after"]["pixel_accessor"] == profile.pixel_accessor_signature.hex()


def test_default_does_not_read_resident_alpha(tmp_path, alpha_scene):
    backend, profile, _ = alpha_scene
    del backend.memory[0x800000]
    del backend.memory[0x810000]
    result = _capture(backend, tmp_path, profile)
    assert result["unique_snapshot_count"] == 1
    assert result["scope"]["pixels_read"] is False
    assert result["limits"]["alpha_read_bytes_reserved"] == 0
    mask = result["snapshots"][0]["source"]["layers"][0]["source_mask"]
    assert "resident_alpha" not in mask


@pytest.mark.parametrize(
    ("offset", "value", "state"),
    [
        (0, 0x499999, "unreviewed_backing_class"),
        (0x38, 256, "unsupported_alpha_layout"),
        (0x3C, 128, "unsupported_alpha_layout"),
        (0x40, 4, "unsupported_alpha_layout"),
        (0xFC, 0, "unsupported_alpha_layout"),
        (0x100, 0x1907, "unsupported_alpha_layout"),
        (0x5C, 0, "not_resident"),
    ],
)
def test_unsupported_or_absent_alpha_is_not_read(tmp_path, alpha_scene, offset, value, state):
    backend, profile, _ = alpha_scene
    raw = bytearray(backend.memory[0x722000])
    struct.pack_into("<I", raw, offset, value)
    backend.memory[0x722000] = bytes(raw)
    del backend.memory[0x800000]  # Any pixel dereference would discard the sample.
    result = _capture(backend, tmp_path, profile, include_resident_alpha=True)
    alpha = result["snapshots"][0]["source"]["layers"][0]["source_mask"]["resident_alpha"]
    assert alpha["state"] == state
    assert "bytes_base64" not in alpha


def test_alpha_byte_budget_includes_repeated_polls(tmp_path, alpha_scene, monkeypatch):
    import shadowbane_lab.diagnostics.terrain_material_poll as module

    backend, profile, _ = alpha_scene
    monkeypatch.setattr(module, "MAXIMUM_ALPHA_READ_BYTES", 8192)
    result = _capture(backend, tmp_path, profile, include_resident_alpha=True)
    assert result["limits"]["alpha_read_bytes_reserved"] == 8192
    layers = result["snapshots"][0]["source"]["layers"]
    assert layers[0]["source_mask"]["resident_alpha"]["state"] == "captured"
    assert layers[0]["gpu_mask"]["resident_alpha"]["state"] == "capture_byte_budget_exhausted"


def test_unstable_pixels_are_discarded_and_still_consume_budget(
    tmp_path, alpha_scene, monkeypatch
):
    import shadowbane_lab.diagnostics.terrain_material_poll as module

    backend, profile, _ = alpha_scene
    read = backend.read_block
    calls = 0

    def changing_pixels(address, size):
        nonlocal calls
        raw = read(address, size)
        if address == 0x800000:
            calls += 1
            return bytes([calls % 2]) + raw[1:]
        return raw

    backend.read_block = changing_pixels
    monkeypatch.setattr(module, "MAXIMUM_ALPHA_READ_BYTES", 8192)
    result = _capture(backend, tmp_path, profile, include_resident_alpha=True)
    assert result["discarded_unstable_poll_count"] == 1
    assert result["limits"]["alpha_read_bytes_reserved"] == 8192
    assert "resident alpha pixels changed during the sample" in result["warnings"]
    for snapshot in result["snapshots"]:
        alpha = snapshot["source"]["layers"][0]["source_mask"]["resident_alpha"]
        assert alpha["state"] == "capture_byte_budget_exhausted"


def test_resident_alpha_signature_drift_refuses_publication(tmp_path, alpha_scene):
    backend, profile, _ = alpha_scene
    backend.memory[backend.base_address + profile.pixel_accessor_rva] = b"x" * len(
        profile.pixel_accessor_signature
    )
    with pytest.raises(TerrainMaterialCompatibilityError, match="alpha accessor"):
        _capture(backend, tmp_path, profile, include_resident_alpha=True)
    assert not (tmp_path / "material-poll.json").exists()


def test_mesh_option_preserves_root_checks_and_publishes_layout_gates(tmp_path, alpha_scene):
    from shadowbane_lab.diagnostics.terrain_mesh_snapshot import LAYOUT_SIGNATURES

    backend, profile, _ = alpha_scene
    for rva, signature in LAYOUT_SIGNATURES:
        backend.memory[backend.base_address + rva] = signature
    backend.memory[0x603000] = struct.pack("<I", 0xDEAD)  # unreviewed mesh wrapper
    result = _capture(backend, tmp_path, profile, include_mesh=True)
    assert result["snapshots"][0]["mesh"]["state"] == "unreviewed_mesh_wrapper"
    assert len(result["signatures_after"]["mesh_layout_signatures"]) == 4
    assert result["scope"]["mesh_requested"] is True
    assert result["limits"]["mesh_read_bytes_reserved"] == 0


def test_mesh_signature_drift_refuses_publication(tmp_path, alpha_scene):
    from shadowbane_lab.diagnostics.terrain_mesh_snapshot import LAYOUT_SIGNATURES

    backend, profile, _ = alpha_scene
    for rva, signature in LAYOUT_SIGNATURES:
        backend.memory[backend.base_address + rva] = signature
    rva, signature = LAYOUT_SIGNATURES[-1]
    backend.memory[backend.base_address + rva] = b"x" * len(signature)
    with pytest.raises(TerrainMaterialCompatibilityError, match="mesh layout"):
        _capture(backend, tmp_path, profile, include_mesh=True)
    assert not (tmp_path / "material-poll.json").exists()


def test_staged_ownership_allows_root_advance_only_after_association(tmp_path, alpha_scene):
    from shadowbane_lab.diagnostics.terrain_material_poll import TERRAIN_SOURCE_VTABLE_RVA

    backend, profile, _ = alpha_scene
    raw = bytearray(backend.memory[0x602000])
    struct.pack_into("<I", raw, 0, backend.base_address + TERRAIN_SOURCE_VTABLE_RVA)
    backend.memory[0x602000] = bytes(raw)
    read = backend.read_block
    source_reads = 0

    def advance_after_anchor(address, size):
        nonlocal source_reads
        if address == 0x602000:
            source_reads += 1
            if source_reads == 2:
                owner = bytearray(backend.memory[0x601000])
                struct.pack_into("<I", owner, 0x10, 0)
                backend.memory[0x601000] = bytes(owner)
        return read(address, size)

    backend.read_block = advance_after_anchor
    result = _capture(backend, tmp_path, profile, staged_ownership=True)
    assert result["unique_source_count"] == 1
    assert result["snapshots"][0]["ownership_consistency"] == "staged-root-and-graph"
    assert result["scope"]["frame_complete"] is False
    assert result["idle_poll_count"] > 0


def test_staged_ownership_refuses_unreviewed_source(tmp_path, alpha_scene):
    backend, profile, _ = alpha_scene
    result = _capture(backend, tmp_path, profile, staged_ownership=True)
    assert result["snapshots"] == []
    assert "unreviewed staged terrain source class" in result["warnings"]


def test_staged_ownership_still_rejects_root_change_during_association(tmp_path, alpha_scene):
    from shadowbane_lab.diagnostics.terrain_material_poll import TERRAIN_SOURCE_VTABLE_RVA

    backend, profile, _ = alpha_scene
    raw = bytearray(backend.memory[0x602000])
    struct.pack_into("<I", raw, 0, backend.base_address + TERRAIN_SOURCE_VTABLE_RVA)
    backend.memory[0x602000] = bytes(raw)
    read = backend.read_block

    def changing_root(address, size):
        result = read(address, size)
        if address == 0x602000:
            owner = bytearray(backend.memory[0x601000])
            owner[0] ^= 1
            backend.memory[0x601000] = bytes(owner)
        return result

    backend.read_block = changing_root
    result = _capture(backend, tmp_path, profile, staged_ownership=True)
    assert result["snapshots"] == []
    assert "terrain shader owner changed during the sample" in result["warnings"]


def test_world_context_is_opt_in(tmp_path, alpha_scene, monkeypatch):
    import shadowbane_lab.diagnostics.terrain_material_poll as module

    def forbidden(*args, **kwargs):
        pytest.fail("context reader should not run without opt-in")

    monkeypatch.setattr(module, "observe_terrain_world_context", forbidden)
    backend, profile, _ = alpha_scene
    result = _capture(backend, tmp_path, profile)
    assert "world_context" not in result
    assert result["scope"]["world_context_requested"] is False


def test_world_context_brackets_poll_on_same_handle(tmp_path, alpha_scene, monkeypatch):
    import shadowbane_lab.diagnostics.terrain_material_poll as module

    backend, profile, _ = alpha_scene
    calls = []

    def observe(process, *, expected_creation_filetime):
        assert process is backend
        assert expected_creation_filetime == backend.process_creation_filetime_utc
        calls.append(len(calls))
        return {"status": "captured", "sample": len(calls)}

    monkeypatch.setattr(module, "observe_terrain_world_context", observe)
    result = _capture(backend, tmp_path, profile, include_world_context=True)
    assert calls == [0, 1]
    assert result["world_context"]["before_poll"]["sample"] == 1
    assert result["world_context"]["after_poll"]["sample"] == 2
    assert result["scope"]["world_context_requested"] is True
    assert result["unique_source_count"] == 1


def test_world_context_identity_failure_does_not_publish(tmp_path, alpha_scene, monkeypatch):
    import shadowbane_lab.diagnostics.terrain_material_poll as module
    from shadowbane_lab.diagnostics.terrain_world_context import TerrainWorldContextIdentityError

    backend, profile, _ = alpha_scene
    calls = 0

    def observe(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TerrainWorldContextIdentityError("lifetime changed")
        return {"status": "captured"}

    monkeypatch.setattr(module, "observe_terrain_world_context", observe)
    with pytest.raises(TerrainWorldContextIdentityError):
        _capture(backend, tmp_path, profile, include_world_context=True)
    assert not (tmp_path / "material-poll.json").exists()
