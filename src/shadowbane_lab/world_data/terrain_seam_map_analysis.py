"""Per-map border and corner analysis for TerrainAlpha tiles."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.terrain import TerrainAlphaMap, TerrainAlphaTile
from shadowbane_lab.world_data.terrain_seam_provenance import (
    TerrainTileProvenance,
    ZoneTerrainUsage,
)
from shadowbane_lab.world_data.terrain_seam_report import TerrainMapSeamAudit
from shadowbane_lab.world_data.terrain_seam_statistics import (
    DifferenceStatistics,
    GradientSideStatistics,
    TerrainCornerRecord,
    TerrainSeamRecord,
)


@dataclass(frozen=True, slots=True)
class _ParsedTile:
    tile: TerrainAlphaTile
    provenance: TerrainTileProvenance



def _audit_map(
    archive: CacheArchive,
    terrain_map: TerrainAlphaMap,
    zone_references: Sequence[ZoneTerrainUsage],
) -> TerrainMapSeamAudit:
    parsed: dict[tuple[int, int], _ParsedTile] = {}
    dimensions: set[tuple[int, int]] = set()
    for address, entry in terrain_map.entries:
        payload = archive.read_resource(entry)
        tile = TerrainAlphaTile.parse(payload)
        dimensions.add((tile.width, tile.height))
        provenance = TerrainTileProvenance(
            tile_x=address.tile_x,
            tile_y=address.tile_y,
            entry_index=entry.index,
            group_id=entry.group_id,
            resource_id=entry.resource_id,
            data_offset=entry.data_offset,
            uncompressed_size=entry.uncompressed_size,
            stored_size=entry.stored_size,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )
        parsed[(address.tile_x, address.tile_y)] = _ParsedTile(tile, provenance)

    expected = {
        (tile_x, tile_y)
        for tile_x in range(terrain_map.width_tiles)
        for tile_y in range(terrain_map.height_tiles)
    }
    missing = tuple(sorted(expected - parsed.keys()))
    roles = tuple(
        sorted(
            {item.role for item in zone_references} or {"unclassified"},
            key=lambda item: (item != "height", item != "material", item),
        )
    )
    references = tuple(
        sorted(
            zone_references,
            key=lambda item: (
                item.template_group_id,
                item.template_id,
                item.layer_index,
                item.first_reference_offset,
            ),
        )
    )
    provenance = tuple(
        item.provenance
        for _, item in sorted(parsed.items(), key=lambda pair: pair[0])
    )
    if len(dimensions) != 1:
        return TerrainMapSeamAudit(
            group_id=terrain_map.group_id,
            map_id=terrain_map.map_id,
            width_tiles=terrain_map.width_tiles,
            height_tiles=terrain_map.height_tiles,
            status="mixed-tile-dimensions",
            tile_width=None,
            tile_height=None,
            roles=roles,
            zone_references=references,
            missing_tiles=missing,
            issues=("map contains more than one tile sample dimension",),
            tiles=provenance,
            seams=(),
            corners=(),
        )
    tile_width, tile_height = next(iter(dimensions))
    if tile_width < 2 or tile_height < 2:
        return TerrainMapSeamAudit(
            group_id=terrain_map.group_id,
            map_id=terrain_map.map_id,
            width_tiles=terrain_map.width_tiles,
            height_tiles=terrain_map.height_tiles,
            status="insufficient-tile-dimensions",
            tile_width=tile_width,
            tile_height=tile_height,
            roles=roles,
            zone_references=references,
            missing_tiles=missing,
            issues=("tile dimensions do not provide an inward gradient sample",),
            tiles=provenance,
            seams=(),
            corners=(),
        )

    seams: list[TerrainSeamRecord] = []
    for tile_y in range(terrain_map.height_tiles):
        for tile_x in range(terrain_map.width_tiles - 1):
            first = parsed.get((tile_x, tile_y))
            second = parsed.get((tile_x + 1, tile_y))
            if first is not None and second is not None:
                seams.append(
                    _x_seam(
                        (tile_x, tile_y),
                        first.tile,
                        (tile_x + 1, tile_y),
                        second.tile,
                    )
                )
    for tile_y in range(terrain_map.height_tiles - 1):
        for tile_x in range(terrain_map.width_tiles):
            first = parsed.get((tile_x, tile_y))
            second = parsed.get((tile_x, tile_y + 1))
            if first is not None and second is not None:
                seams.append(
                    _y_seam(
                        (tile_x, tile_y),
                        first.tile,
                        (tile_x, tile_y + 1),
                        second.tile,
                    )
                )
    corners: list[TerrainCornerRecord] = []
    for tile_y in range(terrain_map.height_tiles - 1):
        for tile_x in range(terrain_map.width_tiles - 1):
            lower_left = parsed.get((tile_x, tile_y))
            lower_right = parsed.get((tile_x + 1, tile_y))
            upper_left = parsed.get((tile_x, tile_y + 1))
            upper_right = parsed.get((tile_x + 1, tile_y + 1))
            if all(
                item is not None
                for item in (lower_left, lower_right, upper_left, upper_right)
            ):
                assert lower_left is not None
                assert lower_right is not None
                assert upper_left is not None
                assert upper_right is not None
                corners.append(
                    TerrainCornerRecord(
                        junction_x=tile_x + 1,
                        junction_y=tile_y + 1,
                        lower_left_tile=(tile_x, tile_y),
                        lower_right_tile=(tile_x + 1, tile_y),
                        upper_left_tile=(tile_x, tile_y + 1),
                        upper_right_tile=(tile_x + 1, tile_y + 1),
                        lower_left_value=lower_left.tile.sample(
                            tile_width - 1,
                            tile_height - 1,
                        ),
                        lower_right_value=lower_right.tile.sample(0, tile_height - 1),
                        upper_left_value=upper_left.tile.sample(tile_width - 1, 0),
                        upper_right_value=upper_right.tile.sample(0, 0),
                    )
                )
    status = "complete" if not missing else "incomplete"
    issues = () if not missing else (f"map is missing {len(missing)} tile positions",)
    return TerrainMapSeamAudit(
        group_id=terrain_map.group_id,
        map_id=terrain_map.map_id,
        width_tiles=terrain_map.width_tiles,
        height_tiles=terrain_map.height_tiles,
        status=status,
        tile_width=tile_width,
        tile_height=tile_height,
        roles=roles,
        zone_references=references,
        missing_tiles=missing,
        issues=issues,
        tiles=provenance,
        seams=tuple(seams),
        corners=tuple(corners),
    )


def _x_seam(
    first_coordinate: tuple[int, int],
    first: TerrainAlphaTile,
    second_coordinate: tuple[int, int],
    second: TerrainAlphaTile,
) -> TerrainSeamRecord:
    border: list[int] = []
    first_inward: list[int] = []
    second_inward: list[int] = []
    discontinuity: list[int] = []
    for row in range(first.height):
        first_edge = first.sample(first.width - 1, row)
        second_edge = second.sample(0, row)
        first_gradient = first_edge - first.sample(first.width - 2, row)
        second_gradient = second_edge - second.sample(1, row)
        border.append(second_edge - first_edge)
        first_inward.append(first_gradient)
        second_inward.append(second_gradient)
        discontinuity.append(first_gradient + second_gradient)
    return TerrainSeamRecord(
        axis="x",
        first_tile=first_coordinate,
        second_tile=second_coordinate,
        border_delta=DifferenceStatistics.from_values(border),
        first_inward_gradient=GradientSideStatistics.from_values(first_inward),
        second_inward_gradient=GradientSideStatistics.from_values(second_inward),
        gradient_discontinuity=DifferenceStatistics.from_values(discontinuity),
    )


def _y_seam(
    first_coordinate: tuple[int, int],
    first: TerrainAlphaTile,
    second_coordinate: tuple[int, int],
    second: TerrainAlphaTile,
) -> TerrainSeamRecord:
    border: list[int] = []
    first_inward: list[int] = []
    second_inward: list[int] = []
    discontinuity: list[int] = []
    for column in range(first.width):
        first_edge = first.sample(column, first.height - 1)
        second_edge = second.sample(column, 0)
        first_gradient = first_edge - first.sample(column, first.height - 2)
        second_gradient = second_edge - second.sample(column, 1)
        border.append(second_edge - first_edge)
        first_inward.append(first_gradient)
        second_inward.append(second_gradient)
        discontinuity.append(first_gradient + second_gradient)
    return TerrainSeamRecord(
        axis="y",
        first_tile=first_coordinate,
        second_tile=second_coordinate,
        border_delta=DifferenceStatistics.from_values(border),
        first_inward_gradient=GradientSideStatistics.from_values(first_inward),
        second_inward_gradient=GradientSideStatistics.from_values(second_inward),
        gradient_discontinuity=DifferenceStatistics.from_values(discontinuity),
    )




__all__ = ["audit_map"]


audit_map = _audit_map
