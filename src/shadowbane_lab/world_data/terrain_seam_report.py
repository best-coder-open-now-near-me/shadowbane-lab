"""Map-level and archive-level output records for TerrainAlpha seam evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.world_data.terrain_seam_provenance import (
    TerrainTileProvenance,
    ZoneCorrelationIssue,
    ZoneTerrainUsage,
)
from shadowbane_lab.world_data.terrain_seam_statistics import (
    TerrainCornerRecord,
    TerrainSeamRecord,
)
from shadowbane_lab.world_data.terrain_seam_support import (
    TERRAIN_SEAM_AUDIT_SCHEMA_VERSION,
    _algorithm_description,
    _json_sha256,
    _source_identity,
)


@dataclass(frozen=True, slots=True)
class TerrainMapSeamAudit:
    group_id: int
    map_id: int
    width_tiles: int
    height_tiles: int
    status: str
    tile_width: int | None
    tile_height: int | None
    roles: tuple[str, ...]
    zone_references: tuple[ZoneTerrainUsage, ...]
    missing_tiles: tuple[tuple[int, int], ...]
    issues: tuple[str, ...]
    tiles: tuple[TerrainTileProvenance, ...]
    seams: tuple[TerrainSeamRecord, ...]
    corners: tuple[TerrainCornerRecord, ...]

    @property
    def summary(self) -> dict[str, int]:
        x_seams = sum(item.axis == "x" for item in self.seams)
        y_seams = sum(item.axis == "y" for item in self.seams)
        diagnostic_scores = [item.diagnostic_score for item in self.seams]
        diagnostic_scores.extend(item.spread for item in self.corners)
        return {
            "seam_count": len(self.seams),
            "x_seam_count": x_seams,
            "y_seam_count": y_seams,
            "corner_count": len(self.corners),
            "nonzero_border_seam_count": sum(
                item.border_delta.nonzero_count > 0 for item in self.seams
            ),
            "max_border_absolute": max(
                (item.border_delta.absolute_maximum for item in self.seams),
                default=0,
            ),
            "max_border_absolute_p95": max(
                (item.border_delta.absolute_p95 for item in self.seams),
                default=0,
            ),
            "max_gradient_discontinuity_absolute": max(
                (item.gradient_discontinuity.absolute_maximum for item in self.seams),
                default=0,
            ),
            "max_gradient_discontinuity_absolute_p95": max(
                (item.gradient_discontinuity.absolute_p95 for item in self.seams),
                default=0,
            ),
            "max_corner_spread": max((item.spread for item in self.corners), default=0),
            "diagnostic_score": max(diagnostic_scores, default=0),
        }

    @property
    def analysis_sha256(self) -> str:
        return _json_sha256(self.as_dict())

    def index_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "map_id": self.map_id,
            "width_tiles": self.width_tiles,
            "height_tiles": self.height_tiles,
            "status": self.status,
            "tile_width": self.tile_width,
            "tile_height": self.tile_height,
            "roles": list(self.roles),
            "zone_references": [item.as_dict() for item in self.zone_references],
            "missing_tile_count": len(self.missing_tiles),
            "issue_count": len(self.issues),
            "summary": self.summary,
            "detail_content_sha256": self.analysis_sha256,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "map_id": self.map_id,
            "width_tiles": self.width_tiles,
            "height_tiles": self.height_tiles,
            "status": self.status,
            "tile_width": self.tile_width,
            "tile_height": self.tile_height,
            "roles": list(self.roles),
            "zone_references": [item.as_dict() for item in self.zone_references],
            "missing_tiles": [list(item) for item in self.missing_tiles],
            "issues": list(self.issues),
            "tiles": [item.as_dict() for item in self.tiles],
            "seams": [item.as_dict() for item in self.seams],
            "corners": [item.as_dict() for item in self.corners],
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class TerrainSeamAuditReport:
    created_at_utc: str
    terrain_source: dict[str, object]
    zone_source: dict[str, object] | None
    zone_templates_scanned: int
    valid_zone_map_references: int
    zone_correlation_issues: tuple[ZoneCorrelationIssue, ...]
    omitted_zone_correlation_issue_count: int
    maps: tuple[TerrainMapSeamAudit, ...]

    @property
    def summary(self) -> dict[str, object]:
        role_counts: defaultdict[str, int] = defaultdict(int)
        for terrain_map in self.maps:
            for role in terrain_map.roles:
                role_counts[role] += 1
        top_seams = sorted(
            (
                {
                    "map_group_id": terrain_map.group_id,
                    "map_id": terrain_map.map_id,
                    "axis": seam.axis,
                    "first_tile": list(seam.first_tile),
                    "second_tile": list(seam.second_tile),
                    "diagnostic_score": seam.diagnostic_score,
                    "border_absolute_p95": seam.border_delta.absolute_p95,
                    "gradient_discontinuity_absolute_p95": (
                        seam.gradient_discontinuity.absolute_p95
                    ),
                }
                for terrain_map in self.maps
                for seam in terrain_map.seams
            ),
            key=lambda item: (
                -int(item["diagnostic_score"]),
                int(item["map_group_id"]),
                int(item["map_id"]),
                str(item["axis"]),
                tuple(item["first_tile"]),
            ),
        )[:25]
        top_corners = sorted(
            (
                {
                    "map_group_id": terrain_map.group_id,
                    "map_id": terrain_map.map_id,
                    "junction": [corner.junction_x, corner.junction_y],
                    "spread": corner.spread,
                }
                for terrain_map in self.maps
                for corner in terrain_map.corners
            ),
            key=lambda item: (
                -int(item["spread"]),
                int(item["map_group_id"]),
                int(item["map_id"]),
                tuple(item["junction"]),
            ),
        )[:25]
        return {
            "map_count": len(self.maps),
            "complete_map_count": sum(item.status == "complete" for item in self.maps),
            "incomplete_map_count": sum(item.status == "incomplete" for item in self.maps),
            "unanalysable_map_count": sum(
                item.status not in {"complete", "incomplete"} for item in self.maps
            ),
            "tile_count": sum(len(item.tiles) for item in self.maps),
            "seam_count": sum(len(item.seams) for item in self.maps),
            "corner_count": sum(len(item.corners) for item in self.maps),
            "role_map_counts": dict(sorted(role_counts.items())),
            "max_diagnostic_score": max(
                (item.summary["diagnostic_score"] for item in self.maps),
                default=0,
            ),
            "top_seams": top_seams,
            "top_corners": top_corners,
        }

    @property
    def analysis_sha256(self) -> str:
        algorithm = _algorithm_description()
        zone_correlation = self._zone_correlation_dict()
        identity_sources = {
            "terrain_alpha": _source_identity(self.terrain_source),
        }
        if self.zone_source is not None:
            identity_sources["c_zone"] = _source_identity(self.zone_source)
        return _json_sha256(
            {
                "schema_version": TERRAIN_SEAM_AUDIT_SCHEMA_VERSION,
                "algorithm": algorithm,
                "sources": identity_sources,
                "zone_correlation": zone_correlation,
                "summary": self.summary,
                "maps": [item.index_dict() for item in self.maps],
            }
        )

    def as_dict(
        self,
        *,
        map_artifacts: Mapping[tuple[int, int], Mapping[str, object]] | None = None,
    ) -> dict[str, object]:
        sources: dict[str, object] = {"terrain_alpha": self.terrain_source}
        if self.zone_source is not None:
            sources["c_zone"] = self.zone_source
        artifacts = {} if map_artifacts is None else dict(map_artifacts)
        maps = []
        for terrain_map in self.maps:
            item = terrain_map.index_dict()
            artifact = artifacts.get((terrain_map.group_id, terrain_map.map_id))
            if artifact is not None:
                item.update(artifact)
            maps.append(item)
        return {
            "schema_version": TERRAIN_SEAM_AUDIT_SCHEMA_VERSION,
            "created_at_utc": self.created_at_utc,
            "analysis_sha256": self.analysis_sha256,
            "algorithm": _algorithm_description(),
            "sources": sources,
            "zone_correlation": self._zone_correlation_dict(),
            "summary": self.summary,
            "maps": maps,
        }

    def _zone_correlation_dict(self) -> dict[str, object]:
        return {
            "enabled": self.zone_source is not None,
            "templates_scanned": self.zone_templates_scanned,
            "valid_map_references": self.valid_zone_map_references,
            "issues": [item.as_dict() for item in self.zone_correlation_issues],
            "omitted_issue_count": self.omitted_zone_correlation_issue_count,
        }


@dataclass(frozen=True, slots=True)
class TerrainSeamAuditBundle:
    destination_directory: Path
    report_path: Path
    report_sha256: str
    map_detail_paths: tuple[Path, ...]
    heatmap_paths: tuple[Path, ...]




__all__ = [
    "TerrainMapSeamAudit",
    "TerrainSeamAuditBundle",
    "TerrainSeamAuditReport",
]
