"""Project active client height fields into the global A* cost map."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from pathlib import Path

from shadowbane_lab.client_observation import (
    NativeCurrentZoneObservation,
    NativeZoneGeometry,
)
from shadowbane_lab.travel.pathfinding import NavigationCell, SparseNavigationMap
from shadowbane_lab.world_data import (
    CacheArchive,
    TerrainAlphaRaster,
    correlate_zone_terrain,
    index_terrain_alpha_maps,
    read_terrain_alpha_map,
)


@dataclass(frozen=True, slots=True)
class TerrainNavigationConfig:
    cell_size: float = 20.0
    blocked_sample_delta: int = 64
    minimum_traversable_sample: int | None = None
    maximum_traversal_cost: float = 5.0
    maximum_seed_cells: int = 50_000

    def __post_init__(self) -> None:
        if (
            isinstance(self.cell_size, bool)
            or not isinstance(self.cell_size, (int, float))
            or not isfinite(self.cell_size)
            or self.cell_size <= 0
        ):
            raise ValueError("terrain navigation cell_size must be finite and positive")
        if (
            isinstance(self.blocked_sample_delta, bool)
            or not isinstance(self.blocked_sample_delta, int)
            or not 1 <= self.blocked_sample_delta <= 255
        ):
            raise ValueError("blocked_sample_delta must be in [1, 255]")
        if self.minimum_traversable_sample is not None and (
            isinstance(self.minimum_traversable_sample, bool)
            or not isinstance(self.minimum_traversable_sample, int)
            or not 0 <= self.minimum_traversable_sample <= 255
        ):
            raise ValueError("minimum_traversable_sample must be in [0, 255]")
        if (
            isinstance(self.maximum_traversal_cost, bool)
            or not isinstance(self.maximum_traversal_cost, (int, float))
            or not isfinite(self.maximum_traversal_cost)
            or self.maximum_traversal_cost < 1
        ):
            raise ValueError("maximum_traversal_cost must be finite and at least one")
        if (
            isinstance(self.maximum_seed_cells, bool)
            or not isinstance(self.maximum_seed_cells, int)
            or self.maximum_seed_cells <= 0
        ):
            raise ValueError("maximum_seed_cells must be positive")


@dataclass(frozen=True, slots=True)
class TerrainNavigationSeed:
    zone_depth: int
    template_group_id: int
    template_id: int
    terrain_group_id: int
    terrain_map_id: int
    raster_width: int
    raster_height: int
    sampled_cells: int
    blocked_cells: frozenset[NavigationCell]
    costs: tuple[tuple[NavigationCell, float], ...]


@dataclass(frozen=True, slots=True)
class ActiveZoneTerrainNavigation:
    navigation_map: SparseNavigationMap
    seed: TerrainNavigationSeed | None


def load_active_zone_terrain_navigation(
    cache_directory: str | Path,
    observation: NativeCurrentZoneObservation,
    config: TerrainNavigationConfig | None = None,
) -> ActiveZoneTerrainNavigation:
    """Load the nearest active height layer and seed one sparse global A* map."""

    if not isinstance(observation, NativeCurrentZoneObservation):
        raise ValueError("observation must be NativeCurrentZoneObservation")
    resolved = config or TerrainNavigationConfig()
    navigation_map = SparseNavigationMap(cell_size=resolved.cell_size)
    cache_root = Path(cache_directory)
    with (
        CacheArchive(cache_root / "CZone.cache") as zones,
        CacheArchive(cache_root / "TerrainAlpha.cache") as terrain,
    ):
        indexed = {
            (item.group_id, item.map_id): item
            for item in index_terrain_alpha_maps(terrain)
        }
        for identity in observation.chain:
            if not identity.cache_resolvable:
                continue
            correlation = correlate_zone_terrain(
                zones,
                terrain,
                identity.template_group_id,
                identity.template_id,
            )
            height_map = correlation.height_map
            if height_map is None:
                continue
            raster = read_terrain_alpha_map(
                terrain,
                indexed[(height_map.group_id, height_map.map_id)],
            )
            seed = seed_height_raster_navigation(
                navigation_map,
                geometry=identity.geometry,
                raster=raster,
                zone_depth=identity.depth,
                template_group_id=identity.template_group_id,
                template_id=identity.template_id,
                config=resolved,
            )
            return ActiveZoneTerrainNavigation(navigation_map, seed)
    return ActiveZoneTerrainNavigation(navigation_map, None)


def seed_height_raster_navigation(
    navigation_map: SparseNavigationMap,
    *,
    geometry: NativeZoneGeometry,
    raster: TerrainAlphaRaster,
    zone_depth: int,
    template_group_id: int,
    template_id: int,
    config: TerrainNavigationConfig | None = None,
) -> TerrainNavigationSeed:
    if not isinstance(navigation_map, SparseNavigationMap):
        raise ValueError("navigation_map must be SparseNavigationMap")
    if not isinstance(geometry, NativeZoneGeometry):
        raise ValueError("geometry must be NativeZoneGeometry")
    if not isinstance(raster, TerrainAlphaRaster):
        raise ValueError("raster must be TerrainAlphaRaster")
    resolved = config or TerrainNavigationConfig(cell_size=navigation_map.cell_size)
    if resolved.cell_size != navigation_map.cell_size:
        raise ValueError("terrain config and navigation map cell sizes must match")

    corners = [
        _local_to_world(geometry, x, z)
        for x in (geometry.minimum_local_x, geometry.maximum_local_x)
        for z in (geometry.minimum_local_z, geometry.maximum_local_z)
    ]
    minimum_x = floor(min(point[0] for point in corners) / resolved.cell_size)
    maximum_x = floor(max(point[0] for point in corners) / resolved.cell_size)
    minimum_y = floor(min(point[1] for point in corners) / resolved.cell_size)
    maximum_y = floor(max(point[1] for point in corners) / resolved.cell_size)
    candidate_count = (maximum_x - minimum_x + 1) * (maximum_y - minimum_y + 1)
    if candidate_count > resolved.maximum_seed_cells:
        raise ValueError("active terrain exceeds the bounded navigation seed size")

    blocked: set[NavigationCell] = set()
    costs: dict[NavigationCell, float] = {}
    sampled_cells = 0
    half = resolved.cell_size * 0.45
    for x in range(minimum_x, maximum_x + 1):
        for y in range(minimum_y, maximum_y + 1):
            cell = NavigationCell(x, y)
            center_lt, center_lg = navigation_map.center(cell)
            local_center = _world_to_local(geometry, center_lt, center_lg)
            if not _inside(geometry, *local_center):
                continue
            samples = []
            for delta_lt, delta_lg in (
                (0.0, 0.0),
                (-half, -half),
                (-half, half),
                (half, -half),
                (half, half),
            ):
                local = _world_to_local(
                    geometry,
                    center_lt + delta_lt,
                    center_lg + delta_lg,
                )
                if _inside(geometry, *local):
                    samples.append(_sample_local(raster, geometry, *local))
            sampled_cells += 1
            center_sample = samples[0]
            sample_delta = max(samples) - min(samples)
            below_floor = (
                resolved.minimum_traversable_sample is not None
                and center_sample < resolved.minimum_traversable_sample
            )
            if below_floor or sample_delta >= resolved.blocked_sample_delta:
                navigation_map.mark_blocked(cell)
                blocked.add(cell)
                continue
            if sample_delta == 0 or resolved.maximum_traversal_cost == 1:
                continue
            cost = 1 + (
                sample_delta
                / resolved.blocked_sample_delta
                * (resolved.maximum_traversal_cost - 1)
            )
            navigation_map.set_cost(cell, cost)
            costs[cell] = cost
    return TerrainNavigationSeed(
        zone_depth=zone_depth,
        template_group_id=template_group_id,
        template_id=template_id,
        terrain_group_id=raster.group_id,
        terrain_map_id=raster.map_id,
        raster_width=raster.width,
        raster_height=raster.height,
        sampled_cells=sampled_cells,
        blocked_cells=frozenset(blocked),
        costs=tuple(sorted(costs.items())),
    )


def _inside(geometry: NativeZoneGeometry, local_x: float, local_z: float) -> bool:
    return (
        geometry.minimum_local_x <= local_x <= geometry.maximum_local_x
        and geometry.minimum_local_z <= local_z <= geometry.maximum_local_z
    )


def _sample_local(
    raster: TerrainAlphaRaster,
    geometry: NativeZoneGeometry,
    local_x: float,
    local_z: float,
) -> int:
    normalized_x = (local_x - geometry.minimum_local_x) / (
        geometry.maximum_local_x - geometry.minimum_local_x
    )
    normalized_z = (local_z - geometry.minimum_local_z) / (
        geometry.maximum_local_z - geometry.minimum_local_z
    )
    x = min(raster.width - 1, max(0, round(normalized_x * (raster.width - 1))))
    y = min(raster.height - 1, max(0, round(normalized_z * (raster.height - 1))))
    return raster.sample(x, y)


def _world_to_local(
    geometry: NativeZoneGeometry,
    lt: float,
    lg: float,
) -> tuple[float, float]:
    vector = (
        lt - geometry.absolute_center_x,
        0.0,
        -lg - geometry.absolute_center_z,
    )
    rotated = _rotate(
        vector,
        (
            geometry.rotation_w,
            -geometry.rotation_x,
            -geometry.rotation_y,
            -geometry.rotation_z,
        ),
    )
    return (
        geometry.local_center_x + rotated[0],
        geometry.local_center_z + rotated[2],
    )


def _local_to_world(
    geometry: NativeZoneGeometry,
    local_x: float,
    local_z: float,
) -> tuple[float, float]:
    rotated = _rotate(
        (
            local_x - geometry.local_center_x,
            0.0,
            local_z - geometry.local_center_z,
        ),
        (
            geometry.rotation_w,
            geometry.rotation_x,
            geometry.rotation_y,
            geometry.rotation_z,
        ),
    )
    return (
        geometry.absolute_center_x + rotated[0],
        -(geometry.absolute_center_z + rotated[2]),
    )


def _rotate(
    vector: tuple[float, float, float],
    quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    w, x, y, z = quaternion
    u = (x, y, z)
    dot_uv = sum(left * right for left, right in zip(u, vector, strict=True))
    dot_uu = sum(value * value for value in u)
    cross = (
        u[1] * vector[2] - u[2] * vector[1],
        u[2] * vector[0] - u[0] * vector[2],
        u[0] * vector[1] - u[1] * vector[0],
    )
    return tuple(
        2 * dot_uv * u[index]
        + (w * w - dot_uu) * vector[index]
        + 2 * w * cross[index]
        for index in range(3)
    )
