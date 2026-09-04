"""Exact source and CZone provenance for TerrainAlpha seam evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerrainTileProvenance:
    tile_x: int
    tile_y: int
    entry_index: int
    group_id: int
    resource_id: int
    data_offset: int
    uncompressed_size: int
    stored_size: int
    payload_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "tile": [self.tile_x, self.tile_y],
            "entry_index": self.entry_index,
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "data_offset": self.data_offset,
            "uncompressed_size": self.uncompressed_size,
            "stored_size": self.stored_size,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class ZoneTerrainUsage:
    template_group_id: int
    template_id: int
    layer_index: int
    role: str
    first_reference_offset: int
    tile_reference_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "template_group_id": self.template_group_id,
            "template_id": self.template_id,
            "layer_index": self.layer_index,
            "role": self.role,
            "first_reference_offset": self.first_reference_offset,
            "tile_reference_count": self.tile_reference_count,
        }


@dataclass(frozen=True, slots=True)
class ZoneCorrelationIssue:
    template_group_id: int
    template_id: int
    map_group_id: int
    map_id: int
    kind: str
    matched_tile_count: int
    expected_tile_count: int
    duplicate_reference_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "template_group_id": self.template_group_id,
            "template_id": self.template_id,
            "map_group_id": self.map_group_id,
            "map_id": self.map_id,
            "kind": self.kind,
            "matched_tile_count": self.matched_tile_count,
            "expected_tile_count": self.expected_tile_count,
            "duplicate_reference_count": self.duplicate_reference_count,
        }




__all__ = [
    "TerrainTileProvenance",
    "ZoneCorrelationIssue",
    "ZoneTerrainUsage",
]
