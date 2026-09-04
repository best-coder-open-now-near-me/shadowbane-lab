"""Fail-closed CZone role correlation for TerrainAlpha maps."""

from __future__ import annotations

import struct
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.terrain import TerrainAlphaMap
from shadowbane_lab.world_data.terrain_seam_provenance import (
    ZoneCorrelationIssue,
    ZoneTerrainUsage,
)
from shadowbane_lab.world_data.terrain_seam_support import (
    MAX_ZONE_CORRELATION_ISSUES,
    TerrainSeamAuditError,
)


@dataclass(frozen=True, slots=True)
class _ZoneUsageIndex:
    by_map: dict[tuple[int, int], tuple[ZoneTerrainUsage, ...]]
    issues: tuple[ZoneCorrelationIssue, ...]
    omitted_issue_count: int
    template_count: int
    valid_reference_count: int



def _index_zone_usage(
    zone_archive: CacheArchive | None,
    terrain_maps: Sequence[TerrainAlphaMap],
) -> _ZoneUsageIndex:
    if zone_archive is None:
        return _ZoneUsageIndex({}, (), 0, 0, 0)
    expected_ids: dict[tuple[int, int], frozenset[int]] = {}
    expected_tile_counts: dict[tuple[int, int], int] = {}
    complete_maps: dict[tuple[int, int], bool] = {}
    resource_index: dict[bytes, tuple[tuple[int, int], int]] = {}
    for terrain_map in terrain_maps:
        map_key = (terrain_map.group_id, terrain_map.map_id)
        expected_ids[map_key] = frozenset(
            entry.resource_id for _, entry in terrain_map.entries
        )
        expected_tile_counts[map_key] = (
            terrain_map.width_tiles * terrain_map.height_tiles
        )
        complete_maps[map_key] = terrain_map.is_complete
        for _, entry in terrain_map.entries:
            packed_key = struct.pack("<II", entry.group_id, entry.resource_id)
            if packed_key in resource_index:
                raise TerrainSeamAuditError(
                    "TerrainAlpha archive contains a duplicate resource key"
                )
            resource_index[packed_key] = (map_key, entry.resource_id)

    usages: defaultdict[tuple[int, int], list[ZoneTerrainUsage]] = defaultdict(list)
    issues: list[ZoneCorrelationIssue] = []
    omitted_issues = 0
    valid_reference_count = 0
    ordered_zone_entries = sorted(
        zone_archive.entries,
        key=lambda entry: (entry.group_id, entry.resource_id, entry.index),
    )
    for zone_entry in ordered_zone_entries:
        payload = zone_archive.read_resource(zone_entry)
        matches: defaultdict[
            tuple[int, int], defaultdict[int, list[int]]
        ] = defaultdict(lambda: defaultdict(list))
        for offset in range(max(0, len(payload) - 7)):
            match = resource_index.get(payload[offset : offset + 8])
            if match is None:
                continue
            map_key, resource_id = match
            matches[map_key][resource_id].append(offset)
        valid: list[tuple[int, tuple[int, int]]] = []
        template_has_issue = False
        for map_key, resource_offsets in sorted(matches.items()):
            expected = expected_ids[map_key]
            matched = frozenset(resource_offsets)
            duplicate_count = sum(
                max(0, len(offsets) - 1) for offsets in resource_offsets.values()
            )
            if complete_maps[map_key] and matched == expected and duplicate_count == 0:
                first_offset = min(offsets[0] for offsets in resource_offsets.values())
                valid.append((first_offset, map_key))
                continue
            template_has_issue = True
            if not complete_maps[map_key]:
                kind = "incomplete-source-map"
            elif duplicate_count > 0:
                kind = "duplicate-resource-reference"
            else:
                kind = "partial-map-reference"
            issue = ZoneCorrelationIssue(
                template_group_id=zone_entry.group_id,
                template_id=zone_entry.resource_id,
                map_group_id=map_key[0],
                map_id=map_key[1],
                kind=kind,
                matched_tile_count=len(matched),
                expected_tile_count=expected_tile_counts[map_key],
                duplicate_reference_count=duplicate_count,
            )
            if len(issues) < MAX_ZONE_CORRELATION_ISSUES:
                issues.append(issue)
            else:
                omitted_issues += 1
        if template_has_issue:
            continue
        for layer_index, (first_offset, map_key) in enumerate(sorted(valid)):
            role = "height" if layer_index == 0 else "material"
            usage = ZoneTerrainUsage(
                template_group_id=zone_entry.group_id,
                template_id=zone_entry.resource_id,
                layer_index=layer_index,
                role=role,
                first_reference_offset=first_offset,
                tile_reference_count=len(expected_ids[map_key]),
            )
            usages[map_key].append(usage)
            valid_reference_count += 1
    return _ZoneUsageIndex(
        by_map={
            key: tuple(
                sorted(
                    value,
                    key=lambda item: (
                        item.template_group_id,
                        item.template_id,
                        item.layer_index,
                    ),
                )
            )
            for key, value in usages.items()
        },
        issues=tuple(issues),
        omitted_issue_count=omitted_issues,
        template_count=len(ordered_zone_entries),
        valid_reference_count=valid_reference_count,
    )





__all__ = ["ZoneUsageIndex", "index_zone_usage"]


ZoneUsageIndex = _ZoneUsageIndex
index_zone_usage = _index_zone_usage
