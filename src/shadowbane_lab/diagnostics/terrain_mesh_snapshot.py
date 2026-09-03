"""Bounded read-only ArcSinglePolyMesh/ArcMesh geometry for the reviewed client."""

from __future__ import annotations

import base64
import hashlib
import math
import struct
from collections.abc import Callable
from dataclasses import dataclass

ReadBlock = Callable[[int, int, str], bytes]
MAXIMUM_MESH_READ_BYTES = 16 * 1024 * 1024
MAXIMUM_VERTICES = 4096
MAXIMUM_INDICES = 24576
WRAPPER_SIZE = 0x18
MESH_SIZE = 0xFC
WRAPPER_VTABLE_RVA = 0x11498A0
MESH_VTABLE_RVA = 0x114965C
TRIANGLE_ACTION_VTABLE_RVA = 0x11495A8
LAYOUT_SIGNATURES = (
    (0x1B6790, bytes.fromhex("558bec8bc18b481485c9741d8a501084d2740d8a401150e8f0abe5ff")),
    (0x4E90F8, bytes.fromhex("8b4664506a0068061400006a03")),
    (0x4E91A3, bytes.fromhex("8b4670506a0068061400006a02")),
    (0x1A0740, bytes.fromhex("558bec8b45088b88940000008b90980000002bd151d1fa6803140000526a04")),
)


class TerrainMeshCaptureError(RuntimeError):
    """The candidate geometry could not be interpreted consistently."""


@dataclass(slots=True)
class MeshReadBudget:
    bytes_reserved: int = 0

    def reserve(self, size: int) -> bool:
        if self.bytes_reserved + 2 * size > MAXIMUM_MESH_READ_BYTES:
            return False
        self.bytes_reserved += 2 * size
        return True


def _vector(raw: bytes, offset: int, stride: int, maximum: int) -> tuple[int, int]:
    begin, end, capacity = struct.unpack_from("<III", raw, offset)
    if not (
        0x10000 <= begin <= end <= capacity <= 0x7FFEFFFF
        and begin % (2 if stride == 2 else 4) == 0
        and (end - begin) % stride == 0
        and (capacity - begin) % stride == 0
        and 0 < (end - begin) // stride <= maximum
    ):
        raise TerrainMeshCaptureError("terrain mesh vector bounds/layout were invalid")
    return begin, end - begin


def _buffer_record(raw: bytes, components: int, scalar: str) -> dict[str, object]:
    return {
        "bytes_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_count": len(raw),
        "components": components,
        "scalar": scalar,
    }


def capture_mesh_snapshot(
    read: ReadBlock,
    wrapper: int,
    image_base: int,
    budget: MeshReadBudget,
) -> dict[str, object]:
    """Read mesh data, not GL state; no method invocation or implicit rendering."""
    if not wrapper:
        return {"state": "no_mesh_wrapper"}
    vtable = struct.unpack("<I", read(wrapper, 4, "mesh wrapper class"))[0]
    if vtable != image_base + WRAPPER_VTABLE_RVA:
        return {"state": "unreviewed_mesh_wrapper", "vtable": f"0x{vtable:08x}"}
    owner_raw = read(wrapper, WRAPPER_SIZE, "mesh wrapper")
    if struct.unpack_from("<I", owner_raw)[0] != vtable:
        raise TerrainMeshCaptureError("terrain mesh wrapper class changed")
    if owner_raw[0x10]:
        return {"state": "cached_draw_path_not_attributed"}
    mesh = struct.unpack_from("<I", owner_raw, 0x14)[0]
    if not mesh:
        return {"state": "no_mesh"}
    expected = image_base + MESH_VTABLE_RVA
    if struct.unpack("<I", read(mesh, 4, "mesh class"))[0] != expected:
        return {"state": "unreviewed_mesh_class"}
    raw = read(mesh, MESH_SIZE, "mesh header")
    if struct.unpack_from("<I", raw)[0] != expected:
        raise TerrainMeshCaptureError("terrain mesh class changed")
    action = struct.unpack_from("<I", raw, 0xF8)[0]
    action_raw = read(action, 4, "mesh draw action")
    if struct.unpack("<I", action_raw)[0] != image_base + TRIANGLE_ACTION_VTABLE_RVA:
        return {"state": "unreviewed_mesh_draw_action"}
    vectors = (
        _vector(raw, 0x64, 12, MAXIMUM_VERTICES),
        _vector(raw, 0x70, 8, MAXIMUM_VERTICES),
        _vector(raw, 0x94, 2, MAXIMUM_INDICES),
    )
    count = vectors[0][1] // 12
    if vectors[1][1] // 8 != count or vectors[2][1] % 6:
        raise TerrainMeshCaptureError("terrain mesh attribute/topology counts disagreed")
    if not budget.reserve(sum(size for _, size in vectors)):
        return {"state": "capture_mesh_byte_budget_exhausted"}
    payloads = [read(pointer, size, "terrain mesh buffer") for pointer, size in vectors]
    for payload, (pointer, size) in zip(payloads, vectors, strict=True):
        if read(pointer, size, "terrain mesh buffer") != payload:
            raise TerrainMeshCaptureError("terrain mesh buffer changed")
    if read(mesh, MESH_SIZE, "mesh header") != raw:
        raise TerrainMeshCaptureError("terrain mesh header changed")
    if read(action, 4, "mesh draw action") != action_raw:
        raise TerrainMeshCaptureError("terrain mesh draw action changed")
    if read(wrapper, WRAPPER_SIZE, "mesh wrapper") != owner_raw:
        raise TerrainMeshCaptureError("terrain mesh wrapper changed")
    floats = [struct.unpack(f"<{len(p) // 4}f", p) for p in payloads[:2]]
    if not all(math.isfinite(value) for values in floats for value in values):
        raise TerrainMeshCaptureError("terrain mesh contains non-finite coordinates")
    indices = struct.unpack(f"<{len(payloads[2]) // 2}H", payloads[2])
    if max(indices) >= count:
        raise TerrainMeshCaptureError("terrain mesh index exceeds vertex count")
    return {
        "state": "captured",
        "wrapper_address": f"0x{wrapper:08x}",
        "mesh_address": f"0x{mesh:08x}",
        "vertex_count": count,
        "index_count": len(indices),
        "topology": "triangles",
        "positions": _buffer_record(payloads[0], 3, "little_endian_float32"),
        "uv": _buffer_record(payloads[1], 2, "little_endian_float32"),
        "indices": _buffer_record(payloads[2], 1, "little_endian_uint16"),
        "position_bounds": [
            [min(floats[0][axis::3]), max(floats[0][axis::3])] for axis in range(3)
        ],
        "uv_bounds": [[min(floats[1][axis::2]), max(floats[1][axis::2])] for axis in range(2)],
        "interpretation": (
            "Resident mesh arrays for the reviewed un-cached triangle path. These are not "
            "observed GL array bindings, an atomic frame, or a verified screen projection. "
            "UVs are before per-unit texture matrices."
        ),
    }
