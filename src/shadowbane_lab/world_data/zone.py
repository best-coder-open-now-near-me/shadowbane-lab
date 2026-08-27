"""Correlate CZone templates with their exact TerrainAlpha resource maps."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from shadowbane_lab.world_data.cache import CacheArchive, CacheResourceEntry
from shadowbane_lab.world_data.terrain import TerrainAlphaMap, index_terrain_alpha_maps


class ZoneTerrainCorrelationError(ValueError):
    """Raised when a zone template cannot be joined safely to terrain resources."""


@dataclass(frozen=True, slots=True)
class ZoneTerrainMapReference:
    """One complete TerrainAlpha map referenced by a CZone template."""

    group_id: int
    map_id: int
    width_tiles: int
    height_tiles: int
    tile_count: int


@dataclass(frozen=True, slots=True)
class ZoneTerrainCorrelation:
    """Validated terrain-map references for one CZone cache resource."""

    template_group_id: int
    template_id: int
    zone_entry: CacheResourceEntry
    maps: tuple[ZoneTerrainMapReference, ...]

    @property
    def tile_reference_count(self) -> int:
        return sum(item.tile_count for item in self.maps)


def correlate_zone_terrain(
    zone_archive: CacheArchive,
    terrain_archive: CacheArchive,
    template_group_id: int,
    template_id: int,
) -> ZoneTerrainCorrelation:
    """Join a CZone key to every complete TerrainAlpha map embedded in its payload."""

    _require_uint32(template_group_id, "template_group_id")
    _require_uint32(template_id, "template_id")
    matches = tuple(
        entry
        for entry in zone_archive.entries
        if entry.group_id == template_group_id and entry.resource_id == template_id
    )
    if not matches:
        raise ZoneTerrainCorrelationError(
            f"CZone template {template_group_id}:{template_id} does not exist"
        )
    if len(matches) != 1:
        raise ZoneTerrainCorrelationError(
            f"CZone template {template_group_id}:{template_id} is ambiguous"
        )

    terrain_maps = index_terrain_alpha_maps(terrain_archive)
    key_index: dict[bytes, tuple[TerrainAlphaMap, CacheResourceEntry]] = {}
    for terrain_map in terrain_maps:
        for _, entry in terrain_map.entries:
            key = struct.pack("<II", entry.group_id, entry.resource_id)
            if key in key_index:
                raise ZoneTerrainCorrelationError(
                    "TerrainAlpha archive contains a duplicate resource key"
                )
            key_index[key] = (terrain_map, entry)

    zone_entry = matches[0]
    payload = zone_archive.read_resource(zone_entry)
    referenced: dict[tuple[int, int], dict[int, CacheResourceEntry]] = {}
    for offset in range(max(0, len(payload) - 7)):
        match = key_index.get(payload[offset : offset + 8])
        if match is None:
            continue
        terrain_map, entry = match
        map_key = (terrain_map.group_id, terrain_map.map_id)
        map_entries = referenced.setdefault(map_key, {})
        if entry.resource_id in map_entries:
            raise ZoneTerrainCorrelationError(
                f"CZone template {template_group_id}:{template_id} repeats TerrainAlpha "
                f"resource {entry.group_id}:{entry.resource_id}"
            )
        map_entries[entry.resource_id] = entry

    results = []
    maps_by_key = {(item.group_id, item.map_id): item for item in terrain_maps}
    for map_key, actual_entries in sorted(referenced.items()):
        terrain_map = maps_by_key[map_key]
        expected_ids = {entry.resource_id for _, entry in terrain_map.entries}
        actual_ids = set(actual_entries)
        if actual_ids != expected_ids:
            missing = len(expected_ids - actual_ids)
            raise ZoneTerrainCorrelationError(
                f"CZone template {template_group_id}:{template_id} references only part of "
                f"TerrainAlpha map {terrain_map.group_id}:{terrain_map.map_id} "
                f"({missing} tiles missing)"
            )
        results.append(
            ZoneTerrainMapReference(
                group_id=terrain_map.group_id,
                map_id=terrain_map.map_id,
                width_tiles=terrain_map.width_tiles,
                height_tiles=terrain_map.height_tiles,
                tile_count=len(terrain_map.entries),
            )
        )

    return ZoneTerrainCorrelation(
        template_group_id=template_group_id,
        template_id=template_id,
        zone_entry=zone_entry,
        maps=tuple(results),
    )


def _require_uint32(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF_FFFF:
        raise ValueError(f"{field_name} must be an unsigned 32-bit integer")
