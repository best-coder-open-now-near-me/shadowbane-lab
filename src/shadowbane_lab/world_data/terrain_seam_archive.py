"""Read-only archive entry points for the TerrainAlpha seam audit."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.terrain import TerrainAlphaMap, index_terrain_alpha_maps
from shadowbane_lab.world_data.terrain_seam_analysis import audit_map, index_zone_usage
from shadowbane_lab.world_data.terrain_seam_provenance import ZoneTerrainUsage
from shadowbane_lab.world_data.terrain_seam_report import (
    TerrainMapSeamAudit,
    TerrainSeamAuditReport,
)
from shadowbane_lab.world_data.terrain_seam_support import (
    TerrainSeamAuditError,
    _archive_source,
    _canonical_timestamp,
    _require_regular_file,
    _sha256_file,
)


def audit_terrain_archive(
    terrain_alpha_path: str | Path,
    *,
    zone_cache_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> TerrainSeamAuditReport:
    """Audit every adjacent tile border without modifying either source archive."""

    terrain_path = _require_regular_file(terrain_alpha_path, "terrain_alpha_path")
    zone_path = (
        None
        if zone_cache_path is None
        else _require_regular_file(zone_cache_path, "zone_cache_path")
    )
    terrain_before = _sha256_file(terrain_path)
    zone_before = None if zone_path is None else _sha256_file(zone_path)

    with CacheArchive(terrain_path) as terrain_archive:
        terrain_maps = index_terrain_alpha_maps(terrain_archive)
        if zone_path is None:
            zone_index = index_zone_usage(None, ())
            zone_source = None
        else:
            with CacheArchive(zone_path) as zone_archive:
                zone_index = index_zone_usage(zone_archive, terrain_maps)
                zone_source = _archive_source(
                    zone_archive,
                    zone_path,
                    zone_before or "",
                )
        audits = tuple(
            audit_map(
                terrain_archive,
                terrain_map,
                zone_index.by_map.get((terrain_map.group_id, terrain_map.map_id), ()),
            )
            for terrain_map in terrain_maps
        )
        terrain_source = _archive_source(terrain_archive, terrain_path, terrain_before)

    if _sha256_file(terrain_path) != terrain_before:
        raise TerrainSeamAuditError("TerrainAlpha archive changed while it was audited")
    if zone_path is not None and _sha256_file(zone_path) != zone_before:
        raise TerrainSeamAuditError("CZone archive changed while it was audited")

    return TerrainSeamAuditReport(
        created_at_utc=_canonical_timestamp(created_at),
        terrain_source=terrain_source,
        zone_source=zone_source,
        zone_templates_scanned=zone_index.template_count,
        valid_zone_map_references=zone_index.valid_reference_count,
        zone_correlation_issues=zone_index.issues,
        omitted_zone_correlation_issue_count=zone_index.omitted_issue_count,
        maps=audits,
    )


def audit_terrain_map(
    archive: CacheArchive,
    terrain_map: TerrainAlphaMap,
    *,
    zone_references: Sequence[ZoneTerrainUsage] = (),
) -> TerrainMapSeamAudit:
    """Audit one indexed map; useful for focused tests and later live correlation."""

    if not isinstance(archive, CacheArchive):
        raise ValueError("archive must be CacheArchive")
    if not isinstance(terrain_map, TerrainAlphaMap):
        raise ValueError("terrain_map must be TerrainAlphaMap")
    references = tuple(zone_references)
    if any(not isinstance(item, ZoneTerrainUsage) for item in references):
        raise ValueError("zone_references contains an unsupported value")
    return audit_map(archive, terrain_map, references)




__all__ = ["audit_terrain_archive", "audit_terrain_map"]
