"""Structured, read-only access to Shadowbane world assets."""

from shadowbane_lab.world_data.cache import (
    CacheArchive,
    CacheArchiveFormatError,
    CacheArchiveHeader,
    CacheResourceEntry,
)
from shadowbane_lab.world_data.terrain import (
    TerrainAlphaFormatError,
    TerrainAlphaMap,
    TerrainAlphaRaster,
    TerrainAlphaTile,
    TerrainTileAddress,
    index_terrain_alpha_maps,
    read_terrain_alpha_map,
)
from shadowbane_lab.world_data.world import (
    WorldDefinition,
    WorldDefinitionFormatError,
    ZonePlacement,
    load_world_definition,
    parse_world_definition,
)
from shadowbane_lab.world_data.zone import (
    ZoneTerrainCorrelation,
    ZoneTerrainCorrelationError,
    ZoneTerrainMapReference,
    correlate_zone_terrain,
)

__all__ = [
    "CacheArchive",
    "CacheArchiveFormatError",
    "CacheArchiveHeader",
    "CacheResourceEntry",
    "TerrainAlphaFormatError",
    "TerrainAlphaMap",
    "TerrainAlphaRaster",
    "TerrainAlphaTile",
    "TerrainTileAddress",
    "WorldDefinition",
    "WorldDefinitionFormatError",
    "ZonePlacement",
    "ZoneTerrainCorrelation",
    "ZoneTerrainCorrelationError",
    "ZoneTerrainMapReference",
    "correlate_zone_terrain",
    "index_terrain_alpha_maps",
    "read_terrain_alpha_map",
    "load_world_definition",
    "parse_world_definition",
]
