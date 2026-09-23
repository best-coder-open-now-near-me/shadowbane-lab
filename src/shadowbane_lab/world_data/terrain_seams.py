"""Read-only diagnostics for borders between Shadowbane TerrainAlpha tiles."""

from shadowbane_lab.world_data.terrain_seam_io import (
    audit_terrain_archive,
    audit_terrain_map,
    write_terrain_seam_audit_bundle,
    write_terrain_seam_heatmap,
)
from shadowbane_lab.world_data.terrain_seam_provenance import (
    TerrainTileProvenance,
    ZoneCorrelationIssue,
    ZoneTerrainUsage,
)
from shadowbane_lab.world_data.terrain_seam_report import (
    TerrainMapSeamAudit,
    TerrainSeamAuditBundle,
    TerrainSeamAuditReport,
)
from shadowbane_lab.world_data.terrain_seam_statistics import (
    DifferenceStatistics,
    GradientSideStatistics,
    TerrainCornerRecord,
    TerrainSeamRecord,
)
from shadowbane_lab.world_data.terrain_seam_support import (
    TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME,
    TERRAIN_SEAM_AUDIT_SCHEMA_VERSION,
    TerrainSeamAuditError,
)

__all__ = [
    "DifferenceStatistics",
    "GradientSideStatistics",
    "TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME",
    "TERRAIN_SEAM_AUDIT_SCHEMA_VERSION",
    "TerrainCornerRecord",
    "TerrainMapSeamAudit",
    "TerrainSeamAuditBundle",
    "TerrainSeamAuditError",
    "TerrainSeamAuditReport",
    "TerrainSeamRecord",
    "TerrainTileProvenance",
    "ZoneCorrelationIssue",
    "ZoneTerrainUsage",
    "audit_terrain_archive",
    "audit_terrain_map",
    "write_terrain_seam_audit_bundle",
    "write_terrain_seam_heatmap",
]
