"""Read the reviewed ArcMapHud projection; never call or write client code.

Reviewed image: wonderbane-ef43784b and its verified native-layout derivatives.
Screen-to-world: RVA 0x661010, scale getter 0x574ed0, center getter 0x661440.
The latter uses the same player pointer/getter as native_position. Child control
0x4a supplies the map rectangle when present; its coordinates are parent-local.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from math import hypot, isfinite

from shadowbane_lab.client_observation.build_compatibility import native_layout_is_compatible
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory

_REVIEWED_SHA = "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13"
_OBJECT_VTABLE = 0x116DA48
_CONTROL_VTABLE = 0x116DA0C
_RECT_GETTER = 0x8DDC  # content-control slot +0x1c -> 0x56c3e0; copies this+4
_BASE_SCALE_RVA = 0x11661A4


class NativeMinimapError(RuntimeError):
    """No unique, stable, supported minimap projection is available."""


@dataclass(frozen=True, slots=True)
class NativeMinimapObservation:
    left: int
    top: int
    right: int
    bottom: int
    pixels_per_world_unit: float

    def __post_init__(self):
        if any(type(v) is not int for v in (self.left, self.top, self.right, self.bottom)):
            raise ValueError("minimap rectangle must contain integers")
        if not (16 <= self.right - self.left <= 8192 and 16 <= self.bottom - self.top <= 8192):
            raise ValueError("minimap rectangle is invalid")
        if not isfinite(self.pixels_per_world_unit) or self.pixels_per_world_unit <= 0:
            raise ValueError("minimap scale must be positive and finite")

    @property
    def center(self):
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def destination_pixel(self, *, lt, lg, player_lt, player_lg, radius_x, radius_y):
        """Preserve distance, shortening only destinations outside the click envelope."""
        if not all(isfinite(v) for v in (lt, lg, player_lt, player_lg, radius_x, radius_y)):
            raise NativeMinimapError("destination projection requires finite coordinates")
        if radius_x <= 0 or radius_y <= 0:
            raise NativeMinimapError("destination click envelope must be positive")
        cx, cy = self.center
        rx = min(radius_x, (self.right - self.left) / 2 - 2)
        ry = min(radius_y, (self.bottom - self.top) / 2 - 2)
        dx = (lt - player_lt) * self.pixels_per_world_unit
        dy = (player_lg - lg) * self.pixels_per_world_unit
        scale = max(1.0, hypot(dx / rx, dy / ry))
        return (round(cx + dx / scale), round(cy + dy / scale))


class NativeMinimapReader:
    def __init__(self, process):
        if (
            process.executable_name.casefold() != "sb.exe"
            or process.pointer_size != 4
            or not native_layout_is_compatible(_REVIEWED_SHA, process.executable_sha256)
        ):
            raise NativeMinimapError("unsupported minimap executable identity")
        self._process = process
        self._address = None
        self._closed = False
        base = process.base_address
        # Verify the projection/position/scale dispatch slots and immutable scale.
        for slot, target in ((0x14C, 0x10A87), (0x154, 0x87EC), (0x158, 0x20478)):
            if self._u32(base + _OBJECT_VTABLE + slot) != base + target:
                raise NativeMinimapError("reviewed minimap dispatch table changed")
        if self._read(base + _BASE_SCALE_RVA, 4) != struct.pack("<f", 0.13):
            raise NativeMinimapError("reviewed minimap base scale changed")

    @property
    def process_id(self):
        return self._process.pid

    def _read(self, address, size):
        if not (0x10000 <= address and address + size <= 0x7FFF0000 and size <= 4096):
            raise NativeMinimapError("minimap read is outside bounded user memory")
        try:
            data = self._process.read_block(address, size)
        except Exception as error:
            raise NativeMinimapError("minimap memory is unavailable") from error
        if len(data) != size:
            raise NativeMinimapError("partial minimap read")
        return data

    def _u32(self, address):
        return struct.unpack("<I", self._read(address, 4))[0]

    def _snapshot(self, address):
        base = self._process.base_address
        b = self._read(address, 0x380)
        if struct.unpack_from("<2I", b) != (base + _OBJECT_VTABLE, base + _CONTROL_VTABLE):
            raise NativeMinimapError("minimap owner changed")
        if b[0xD0] != 0:
            raise NativeMinimapError("minimap is hidden")
        parent = struct.unpack_from("<4i", b, 8)
        zoom = struct.unpack_from("<f", b, 0x37C)[0]
        if not isfinite(zoom) or not 0.01 <= zoom <= 100:
            raise NativeMinimapError("minimap zoom is invalid")
        start, end = struct.unpack_from("<2I", b, 0x54)
        if not 0 <= end - start <= 256 * 4 or (end - start) % 4:
            raise NativeMinimapError("minimap child list is invalid")
        child_rects = []
        children = self._read(start, end - start) if end > start else b""
        for (pointer,) in struct.iter_unpack("<I", children):
            if not pointer:
                continue
            child = self._read(pointer, 0x2F4)
            if struct.unpack_from("<I", child, 0x2F0)[0] == 0x4A:
                vtable = struct.unpack_from("<I", child)[0]
                if self._u32(vtable + 0x1C) != base + _RECT_GETTER:
                    raise NativeMinimapError("unsupported minimap child rectangle getter")
                child_rects.append(struct.unpack_from("<4i", child, 4))
        if len(child_rects) > 1:
            raise NativeMinimapError("ambiguous minimap content rectangle")
        rect = parent
        if child_rects:
            left, top, right, bottom = child_rects[0]
            if (
                not 0 <= left < right <= parent[2] - parent[0]
                or not 0 <= top < bottom <= parent[3] - parent[1]
            ):
                raise NativeMinimapError("minimap content leaves its parent")
            rect = (parent[0] + left, parent[1] + top, parent[0] + right, parent[1] + bottom)
        try:
            result = NativeMinimapObservation(
                *rect, struct.unpack("<f", struct.pack("<f", 0.13))[0] * zoom
            )
        except ValueError as error:
            raise NativeMinimapError(str(error)) from error
        return result, parent, start, end, children, tuple(child_rects), zoom

    def observe(self):
        if self._closed:
            raise NativeMinimapError("minimap reader is closed")
        if self._address is None:
            needle = struct.pack("<I", self._process.base_address + _OBJECT_VTABLE)
            hits = self._process.find_all(
                (needle,),
                memory_type=0x20000,
                protection=4,
                maximum_results_per_needle=16,
                maximum_address=0x7FFEFFFF,
            )[needle]
            if len(hits) >= 16:
                raise NativeMinimapError("minimap scan exceeded its candidate bound")
            candidates = []
            for address in hits:
                try:
                    self._snapshot(address)
                except NativeMinimapError:
                    continue
                candidates.append(address)
            if len(candidates) != 1:
                raise NativeMinimapError(f"expected one visible minimap, found {len(candidates)}")
            self._address = candidates[0]
        try:
            for _ in range(3):
                first = self._snapshot(self._address)
                if first == self._snapshot(self._address):
                    return first[0]
        except NativeMinimapError:
            self._address = None
            raise
        raise NativeMinimapError("minimap projection changed during every read")

    def close(self):
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def open_windows_native_minimap_reader(*, process_id):
    process = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", process_id)
    try:
        return NativeMinimapReader(process)
    except Exception:
        process.close()
        raise
