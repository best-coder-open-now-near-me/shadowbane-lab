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
    TerrainAlphaTile,
    TerrainTileAddress,
    index_terrain_alpha_maps,
)
from shadowbane_lab.world_data.world import (
    WorldDefinition,
    WorldDefinitionFormatError,
    ZonePlacement,
    load_world_definition,
    parse_world_definition,
)

__all__ = [
    "CacheArchive",
    "CacheArchiveFormatError",
    "CacheArchiveHeader",
    "CacheResourceEntry",
    "TerrainAlphaFormatError",
    "TerrainAlphaMap",
    "TerrainAlphaTile",
    "TerrainTileAddress",
    "WorldDefinition",
    "WorldDefinitionFormatError",
    "ZonePlacement",
    "index_terrain_alpha_maps",
    "load_world_definition",
    "parse_world_definition",
]
