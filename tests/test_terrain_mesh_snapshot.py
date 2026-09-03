from __future__ import annotations

import base64
import struct

import pytest

from shadowbane_lab.diagnostics.terrain_mesh_snapshot import (
    MESH_SIZE,
    MESH_VTABLE_RVA,
    TRIANGLE_ACTION_VTABLE_RVA,
    WRAPPER_SIZE,
    WRAPPER_VTABLE_RVA,
    MeshReadBudget,
    TerrainMeshCaptureError,
    capture_mesh_snapshot,
)


class Memory:
    base = 0x400000
    wrapper = 0x600000
    mesh = 0x610000

    def __init__(self):
        wrapper = bytearray(WRAPPER_SIZE)
        struct.pack_into("<I", wrapper, 0, self.base + WRAPPER_VTABLE_RVA)
        struct.pack_into("<I", wrapper, 0x14, self.mesh)
        mesh = bytearray(MESH_SIZE)
        struct.pack_into("<I", mesh, 0, self.base + MESH_VTABLE_RVA)
        struct.pack_into("<I", mesh, 0xF8, 0x620000)
        for offset, pointer, size in ((0x64, 0x700000, 36), (0x70, 0x710000, 24),
                                      (0x94, 0x720000, 6)):
            struct.pack_into("<III", mesh, offset, pointer, pointer + size, pointer + size)
        self.blocks = {
            self.wrapper: bytes(wrapper), self.mesh: bytes(mesh),
            0x620000: struct.pack("<I", self.base + TRIANGLE_ACTION_VTABLE_RVA),
            0x700000: struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, 1),
            0x710000: struct.pack("<6f", 0, 0, 1, 0, 0, 1),
            0x720000: struct.pack("<3H", 0, 1, 2),
        }
        self.calls = []

    def read(self, address, size, label):
        self.calls.append((address, size))
        return self.blocks[address][:size]

    def change(self, address, offset, value):
        raw = bytearray(self.blocks[address])
        struct.pack_into("<I", raw, offset, value)
        self.blocks[address] = bytes(raw)

    def capture(self, budget=None):
        return capture_mesh_snapshot(self.read, self.wrapper, self.base, budget or MeshReadBudget())


def test_exact_triangle_geometry_is_retained_losslessly():
    m = Memory()
    result = m.capture()
    assert result["state"] == "captured"
    assert result["vertex_count"] == result["index_count"] == 3
    assert result["position_bounds"] == [[0, 1], [0, 0], [0, 1]]
    for key, address in (("positions", 0x700000), ("uv", 0x710000), ("indices", 0x720000)):
        assert base64.b64decode(result[key]["bytes_base64"]) == m.blocks[address]
        assert sum(a == address for a, _ in m.calls) == 2


@pytest.mark.parametrize(("address", "offset", "value", "state"), [
    (0x600000, 0, 0xDEAD, "unreviewed_mesh_wrapper"),
    (0x600000, 0x10, 1, "cached_draw_path_not_attributed"),
    (0x600000, 0x14, 0, "no_mesh"),
    (0x610000, 0, 0xDEAD, "unreviewed_mesh_class"),
    (0x620000, 0, 0xDEAD, "unreviewed_mesh_draw_action"),
])
def test_unreviewed_paths_do_not_read_geometry(address, offset, value, state):
    m = Memory()
    m.change(address, offset, value)
    assert m.capture()["state"] == state
    assert not any(a >= 0x700000 for a, _ in m.calls)


@pytest.mark.parametrize(("offset", "value"), [
    (0x64, 0), (0x68, 0x700003), (0x68, 0x700000 + 12 * 4097),
    (0x6C, 0x700001), (0x74, 0x710010), (0x98, 0x720004),
])
def test_bad_vectors_are_rejected_before_geometry_reads(offset, value):
    m = Memory()
    m.change(m.mesh, offset, value)
    with pytest.raises(TerrainMeshCaptureError):
        m.capture()
    assert not any(a >= 0x700000 for a, _ in m.calls)


def test_invalid_index_is_rejected():
    m = Memory()
    m.blocks[0x720000] = struct.pack("<3H", 0, 1, 3)
    with pytest.raises(TerrainMeshCaptureError, match="index exceeds"):
        m.capture()


def test_nonfinite_uv_is_rejected():
    m = Memory()
    m.change(0x710000, 0, 0x7FC00000)
    with pytest.raises(TerrainMeshCaptureError, match="non-finite"):
        m.capture()


@pytest.mark.parametrize("changing", [0x600000, 0x610000, 0x620000, 0x700000, 0x710000])
def test_mutations_are_rejected(changing):
    m = Memory()
    read = m.read
    count = 0

    def mutate(address, size, label):
        nonlocal count
        raw = read(address, size, label)
        if address == changing and (size != 4 or changing == 0x620000):
            count += 1
            if count == 2:
                return raw[:-1] + bytes([raw[-1] ^ 1])
        return raw

    with pytest.raises(TerrainMeshCaptureError, match="changed"):
        capture_mesh_snapshot(mutate, m.wrapper, m.base, MeshReadBudget())


def test_byte_budget_covers_both_consistency_reads(monkeypatch):
    import shadowbane_lab.diagnostics.terrain_mesh_snapshot as module

    m = Memory()
    budget = MeshReadBudget()
    monkeypatch.setattr(module, "MAXIMUM_MESH_READ_BYTES", 132)
    assert m.capture(budget)["state"] == "captured"
    assert budget.bytes_reserved == 132
    m.calls.clear()
    assert m.capture(budget)["state"] == "capture_mesh_byte_budget_exhausted"
    assert not any(a >= 0x700000 for a, _ in m.calls)
