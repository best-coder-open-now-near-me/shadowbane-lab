"""Typed views over Shadowbane's spatial TerrainAlpha resources."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from shadowbane_lab.world_data.cache import CacheArchive, CacheResourceEntry

_TERRAIN_HEADER = struct.Struct("<IIIII2BI")


class TerrainAlphaFormatError(ValueError):
    """Raised when a TerrainAlpha resource is not structurally valid."""


@dataclass(frozen=True, slots=True)
class TerrainTileAddress:
    group_id: int
    map_id: int
    tile_x: int
    tile_y: int

    @classmethod
    def from_entry(cls, entry: CacheResourceEntry) -> TerrainTileAddress:
        packed_position = entry.resource_id & 0x00FF_FFFF
        column = packed_position % 1_000
        if column == 0:
            raise TerrainAlphaFormatError(
                f"terrain resource 0x{entry.resource_id:08X} has an invalid packed column"
            )
        return cls(
            group_id=entry.group_id,
            map_id=entry.resource_id >> 24,
            tile_x=packed_position // 1_000,
            tile_y=column - 1,
        )


@dataclass(frozen=True, slots=True)
class TerrainAlphaTile:
    width: int
    height: int
    field_3: int
    field_4: int
    field_5: int
    flag_1: int
    flag_2: int
    samples: bytes

    @classmethod
    def parse(cls, payload: bytes) -> TerrainAlphaTile:
        if len(payload) < _TERRAIN_HEADER.size:
            raise TerrainAlphaFormatError("terrain resource is smaller than its 26-byte header")
        width, height, field_3, field_4, field_5, flag_1, flag_2, data_size = (
            _TERRAIN_HEADER.unpack_from(payload)
        )
        expected_size = _TERRAIN_HEADER.size + data_size
        if expected_size != len(payload):
            raise TerrainAlphaFormatError(
                f"terrain resource contains {len(payload)} bytes; expected {expected_size}"
            )
        if width <= 0 or height <= 0 or width * height != data_size:
            raise TerrainAlphaFormatError(
                f"terrain dimensions {width}x{height} do not match {data_size} samples"
            )
        return cls(
            width=width,
            height=height,
            field_3=field_3,
            field_4=field_4,
            field_5=field_5,
            flag_1=flag_1,
            flag_2=flag_2,
            samples=payload[_TERRAIN_HEADER.size :],
        )

    def sample(self, x: int, y: int) -> int:
        """Return a raw sample in the resource's stored row-major coordinates."""

        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError("terrain sample is outside the tile")
        return self.samples[y * self.width + x]


@dataclass(frozen=True, slots=True)
class TerrainAlphaMap:
    group_id: int
    map_id: int
    width_tiles: int
    height_tiles: int
    entries: tuple[tuple[TerrainTileAddress, CacheResourceEntry], ...]

    @property
    def is_complete(self) -> bool:
        return len(self.entries) == self.width_tiles * self.height_tiles


def index_terrain_alpha_maps(archive: CacheArchive) -> tuple[TerrainAlphaMap, ...]:
    grouped: dict[tuple[int, int], list[tuple[TerrainTileAddress, CacheResourceEntry]]] = {}
    for entry in archive.entries:
        address = TerrainTileAddress.from_entry(entry)
        grouped.setdefault((address.group_id, address.map_id), []).append((address, entry))

    maps = []
    for (group_id, map_id), items in sorted(grouped.items()):
        addresses = [address for address, _ in items]
        positions = {(address.tile_x, address.tile_y) for address in addresses}
        if len(positions) != len(items):
            raise TerrainAlphaFormatError(
                f"terrain map {group_id}:{map_id} has duplicate tile coordinates"
            )
        maps.append(
            TerrainAlphaMap(
                group_id=group_id,
                map_id=map_id,
                width_tiles=max(address.tile_x for address in addresses) + 1,
                height_tiles=max(address.tile_y for address in addresses) + 1,
                entries=tuple(sorted(items, key=lambda item: (item[0].tile_x, item[0].tile_y))),
            )
        )
    return tuple(maps)
