"""Project active client height fields into the global A* cost map."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, hypot, isfinite
from pathlib import Path
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_observation import (
    NativeCurrentZoneObservation,
    NativePlayerPositionObservation,
    NativeZoneGeometry,
)
from shadowbane_lab.travel.pathfinding import (
    NavigationCell,
    NavigationMapSnapshot,
    SparseNavigationMap,
)
from shadowbane_lab.world_data import (
    CacheArchive,
    ObjectNavigationResolver,
    TerrainAlphaMap,
    TerrainAlphaRaster,
    ZoneNavigationMetadata,
    ZoneResourceKey,
    ZoneTerrainCorrelation,
    correlate_zone_terrain,
    index_terrain_alpha_maps,
    parse_zone_navigation_metadata,
    read_terrain_alpha_map,
)


@dataclass(frozen=True, slots=True)
class TerrainNavigationConfig:
    cell_size: float = 20.0
    blocked_sample_delta: int = 64
    minimum_traversable_sample: int | None = None
    maximum_traversal_cost: float = 5.0
    water_traversal_cost: float = 12.0
    maximum_object_density_cost: float = 8.0
    seed_radius: float = 1_200.0
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
            isinstance(self.water_traversal_cost, bool)
            or not isinstance(self.water_traversal_cost, (int, float))
            or not isfinite(self.water_traversal_cost)
            or self.water_traversal_cost < 1
        ):
            raise ValueError("water_traversal_cost must be finite and at least one")
        if (
            isinstance(self.maximum_object_density_cost, bool)
            or not isinstance(self.maximum_object_density_cost, (int, float))
            or not isfinite(self.maximum_object_density_cost)
            or self.maximum_object_density_cost < 1
        ):
            raise ValueError(
                "maximum_object_density_cost must be finite and at least one"
            )
        if (
            isinstance(self.seed_radius, bool)
            or not isinstance(self.seed_radius, (int, float))
            or not isfinite(self.seed_radius)
            or self.seed_radius <= 0
        ):
            raise ValueError("seed_radius must be finite and positive")
        if (
            isinstance(self.maximum_seed_cells, bool)
            or not isinstance(self.maximum_seed_cells, int)
            or self.maximum_seed_cells <= 0
        ):
            raise ValueError("maximum_seed_cells must be positive")


@dataclass(frozen=True, slots=True)
class TerrainObjectDensityLayer:
    layer_index: int
    raster: TerrainAlphaRaster
    object_keys: tuple[ZoneResourceKey, ...]
    population_capacity: int
    maximum_horizontal_radius: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.layer_index, bool)
            or not isinstance(self.layer_index, int)
            or self.layer_index <= 0
        ):
            raise ValueError("object-density layer_index must be positive")
        if not isinstance(self.raster, TerrainAlphaRaster):
            raise ValueError("object-density raster must be TerrainAlphaRaster")
        if not self.object_keys or any(
            not isinstance(key, ZoneResourceKey) for key in self.object_keys
        ):
            raise ValueError("object-density layer requires object keys")
        if len(self.object_keys) != len(set(self.object_keys)):
            raise ValueError("object-density object keys must be unique")
        if (
            isinstance(self.population_capacity, bool)
            or not isinstance(self.population_capacity, int)
            or self.population_capacity <= 0
        ):
            raise ValueError("object-density population capacity must be positive")
        if (
            isinstance(self.maximum_horizontal_radius, bool)
            or not isinstance(self.maximum_horizontal_radius, (int, float))
            or not isfinite(self.maximum_horizontal_radius)
            or self.maximum_horizontal_radius <= 0
        ):
            raise ValueError("object-density collision radius must be positive")


@dataclass(frozen=True, slots=True)
class TerrainObjectDensityLayerSeed:
    layer_index: int
    terrain_group_id: int
    terrain_map_id: int
    object_count: int
    population_capacity: int
    maximum_horizontal_radius: float


@dataclass(frozen=True, slots=True)
class TerrainNavigationSeed:
    zone_depth: int
    template_group_id: int
    template_id: int
    terrain_group_id: int
    terrain_map_id: int
    raster_width: int
    raster_height: int
    window_center_lt: float | None
    window_center_lg: float | None
    window_radius: float | None
    sampled_cells: int
    blocked_cells: frozenset[NavigationCell]
    water_cells: frozenset[NavigationCell]
    object_density_cells: frozenset[NavigationCell]
    object_density_layers: tuple[TerrainObjectDensityLayerSeed, ...]
    water_sample_threshold: float | None
    costs: tuple[tuple[NavigationCell, float], ...]


@dataclass(frozen=True, slots=True)
class ActiveZoneTerrainNavigation:
    navigation_map: SparseNavigationMap
    seed: TerrainNavigationSeed | None


@runtime_checkable
class CurrentZoneSource(Protocol):
    def observe(self) -> NativeCurrentZoneObservation: ...


class ActiveZoneTerrainNavigationSource:
    """Refresh terrain costs as a long route moves or crosses zone ownership."""

    def __init__(
        self,
        cache_directory: str | Path,
        zone_reader: CurrentZoneSource,
        config: TerrainNavigationConfig | None = None,
        *,
        refresh_distance_fraction: float = 0.5,
        navigation_map: SparseNavigationMap | None = None,
    ) -> None:
        if not isinstance(zone_reader, CurrentZoneSource):
            raise ValueError("zone_reader must implement CurrentZoneSource")
        if (
            isinstance(refresh_distance_fraction, bool)
            or not isinstance(refresh_distance_fraction, (int, float))
            or not isfinite(refresh_distance_fraction)
            or not 0 < refresh_distance_fraction <= 1
        ):
            raise ValueError("refresh_distance_fraction must be in (0, 1]")
        self._cache_directory = Path(cache_directory)
        self._zone_reader = zone_reader
        self._config = config or TerrainNavigationConfig()
        if navigation_map is not None and not isinstance(
            navigation_map, SparseNavigationMap
        ):
            raise ValueError("navigation_map must be SparseNavigationMap")
        if (
            navigation_map is not None
            and navigation_map.cell_size != self._config.cell_size
        ):
            raise ValueError("navigation_map and terrain config cell sizes must match")
        self._refresh_distance = (
            self._config.seed_radius * float(refresh_distance_fraction)
        )
        self._navigation_map = navigation_map or SparseNavigationMap(
            cell_size=self._config.cell_size
        )
        self._snapshot: NavigationMapSnapshot | None = None
        self._zone_token: str | None = None
        self._center: tuple[float, float] | None = None
        self._refresh_count = 0
        self._last_zone_name: str | None = None
        self._last_seed: TerrainNavigationSeed | None = None

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def last_zone_name(self) -> str | None:
        return self._last_zone_name

    @property
    def last_seed(self) -> TerrainNavigationSeed | None:
        return self._last_seed

    def observe(
        self,
        position: NativePlayerPositionObservation,
    ) -> NavigationMapSnapshot:
        if not isinstance(position, NativePlayerPositionObservation):
            raise ValueError("position must be NativePlayerPositionObservation")
        zone = self._zone_reader.observe()
        if self._snapshot is not None and not self._refresh_required(zone, position):
            return self._snapshot
        active = load_active_zone_terrain_navigation(
            self._cache_directory,
            zone,
            position,
            self._config,
            navigation_map=self._navigation_map,
        )
        self._refresh_count += 1
        self._zone_token = zone.zone_token
        self._center = (position.lt, position.lg)
        self._last_zone_name = zone.name
        self._last_seed = active.seed
        self._snapshot = NavigationMapSnapshot(
            token=f"{zone.zone_token}:{self._refresh_count}",
            navigation_map=active.navigation_map,
        )
        return self._snapshot

    def _refresh_required(
        self,
        zone: NativeCurrentZoneObservation,
        position: NativePlayerPositionObservation,
    ) -> bool:
        if zone.zone_token != self._zone_token or self._center is None:
            return True
        return (
            hypot(position.lt - self._center[0], position.lg - self._center[1])
            >= self._refresh_distance
        )


def load_active_zone_terrain_navigation(
    cache_directory: str | Path,
    observation: NativeCurrentZoneObservation,
    origin: NativePlayerPositionObservation,
    config: TerrainNavigationConfig | None = None,
    *,
    navigation_map: SparseNavigationMap | None = None,
) -> ActiveZoneTerrainNavigation:
    """Load the nearest active height layer and seed one sparse global A* map."""

    if not isinstance(observation, NativeCurrentZoneObservation):
        raise ValueError("observation must be NativeCurrentZoneObservation")
    if not isinstance(origin, NativePlayerPositionObservation):
        raise ValueError("origin must be NativePlayerPositionObservation")
    resolved = config or TerrainNavigationConfig()
    if navigation_map is None:
        navigation_map = SparseNavigationMap(cell_size=resolved.cell_size)
    elif not isinstance(navigation_map, SparseNavigationMap):
        raise ValueError("navigation_map must be a SparseNavigationMap")
    elif navigation_map.cell_size != resolved.cell_size:
        raise ValueError("navigation_map and terrain config cell sizes must match")
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
            metadata = parse_zone_navigation_metadata(
                zones.read_resource(correlation.zone_entry)
            )
            object_density_layers = _load_object_density_layers(
                cache_root,
                terrain,
                indexed,
                correlation,
                metadata,
            )
            seed = seed_height_raster_navigation(
                navigation_map,
                geometry=identity.geometry,
                raster=raster,
                zone_depth=identity.depth,
                template_group_id=identity.template_group_id,
                template_id=identity.template_id,
                window_center_lt=origin.lt,
                window_center_lg=origin.lg,
                water_sample_threshold=metadata.local_water_sample_threshold(),
                object_density_layers=object_density_layers,
                config=resolved,
            )
            return ActiveZoneTerrainNavigation(navigation_map, seed)
    return ActiveZoneTerrainNavigation(navigation_map, None)


def _load_object_density_layers(
    cache_root: Path,
    terrain: CacheArchive,
    indexed_terrain: dict[tuple[int, int], TerrainAlphaMap],
    correlation: ZoneTerrainCorrelation,
    metadata: ZoneNavigationMetadata,
) -> tuple[TerrainObjectDensityLayer, ...]:
    object_path = cache_root / "CObjects.cache"
    render_path = cache_root / "Render.cache"
    mesh_path = cache_root / "Mesh.cache"
    if not all(path.is_file() for path in (object_path, render_path, mesh_path)):
        return ()

    populations_by_layer: dict[int, list[tuple[ZoneResourceKey, int, float]]] = {}
    with (
        CacheArchive(object_path) as objects,
        CacheArchive(render_path) as renders,
        CacheArchive(mesh_path) as meshes,
    ):
        resolver = ObjectNavigationResolver(objects, renders, meshes)
        for population in metadata.terrain_object_populations:
            layer_index = population.population_layer_index(
                metadata.terrain_generation
            )
            if layer_index is None:
                continue
            profile = resolver.resolve(population.object_key)
            if not profile.collides or profile.horizontal_radius is None:
                continue
            populations_by_layer.setdefault(layer_index, []).append(
                (
                    population.object_key,
                    population.maximum_population,
                    profile.horizontal_radius,
                )
            )

    maps_by_layer = {item.layer_index: item for item in correlation.maps}
    layers = []
    for layer_index, populations in sorted(populations_by_layer.items()):
        try:
            terrain_reference = maps_by_layer[layer_index]
        except KeyError as exc:
            raise ValueError(
                f"object-density layer {layer_index} has no correlated terrain map"
            ) from exc
        raster = read_terrain_alpha_map(
            terrain,
            indexed_terrain[
                (terrain_reference.group_id, terrain_reference.map_id)
            ],
        )
        layers.append(
            TerrainObjectDensityLayer(
                layer_index=layer_index,
                raster=raster,
                object_keys=tuple(
                    item[0]
                    for item in sorted(
                        populations,
                        key=lambda item: (
                            item[0].group_id,
                            item[0].resource_id,
                        ),
                    )
                ),
                population_capacity=sum(item[1] for item in populations),
                maximum_horizontal_radius=max(item[2] for item in populations),
            )
        )
    return tuple(layers)


def seed_height_raster_navigation(
    navigation_map: SparseNavigationMap,
    *,
    geometry: NativeZoneGeometry,
    raster: TerrainAlphaRaster,
    zone_depth: int,
    template_group_id: int,
    template_id: int,
    window_center_lt: float | None = None,
    window_center_lg: float | None = None,
    water_sample_threshold: float | None = None,
    object_density_layers: tuple[TerrainObjectDensityLayer, ...] = (),
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
    if (window_center_lt is None) != (window_center_lg is None):
        raise ValueError("terrain navigation window center requires both LT and LG")
    for value in (window_center_lt, window_center_lg):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
        ):
            raise ValueError("terrain navigation window center must be finite")
    if water_sample_threshold is not None and (
        isinstance(water_sample_threshold, bool)
        or not isinstance(water_sample_threshold, (int, float))
        or not isfinite(water_sample_threshold)
    ):
        raise ValueError("water sample threshold must be finite")
    if any(
        not isinstance(layer, TerrainObjectDensityLayer)
        for layer in object_density_layers
    ):
        raise ValueError(
            "object_density_layers must contain TerrainObjectDensityLayer values"
        )
    layer_indexes = tuple(layer.layer_index for layer in object_density_layers)
    if len(layer_indexes) != len(set(layer_indexes)):
        raise ValueError("object-density layer indexes must be unique")

    corners = [
        _local_to_world(geometry, x, z)
        for x in (geometry.minimum_local_x, geometry.maximum_local_x)
        for z in (geometry.minimum_local_z, geometry.maximum_local_z)
    ]
    minimum_x = floor(min(point[0] for point in corners) / resolved.cell_size)
    maximum_x = floor(max(point[0] for point in corners) / resolved.cell_size)
    minimum_y = floor(min(point[1] for point in corners) / resolved.cell_size)
    maximum_y = floor(max(point[1] for point in corners) / resolved.cell_size)
    if window_center_lt is not None and window_center_lg is not None:
        minimum_x = max(
            minimum_x,
            floor((window_center_lt - resolved.seed_radius) / resolved.cell_size),
        )
        maximum_x = min(
            maximum_x,
            floor((window_center_lt + resolved.seed_radius) / resolved.cell_size),
        )
        minimum_y = max(
            minimum_y,
            floor((window_center_lg - resolved.seed_radius) / resolved.cell_size),
        )
        maximum_y = min(
            maximum_y,
            floor((window_center_lg + resolved.seed_radius) / resolved.cell_size),
        )
    if minimum_x > maximum_x or minimum_y > maximum_y:
        raise ValueError("terrain navigation window does not intersect the active zone")
    candidate_count = (maximum_x - minimum_x + 1) * (maximum_y - minimum_y + 1)
    if candidate_count > resolved.maximum_seed_cells:
        raise ValueError("active terrain exceeds the bounded navigation seed size")

    blocked: set[NavigationCell] = set()
    water: set[NavigationCell] = set()
    object_density: set[NavigationCell] = set()
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
            local_samples = []
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
                    local_samples.append(local)
            sampled_cells += 1
            samples = [
                _sample_local(raster, geometry, *local) for local in local_samples
            ]
            center_sample = samples[0]
            sample_delta = max(samples) - min(samples)
            object_density_sample = max(
                (
                    _sample_local(layer.raster, geometry, *local)
                    for layer in object_density_layers
                    for local in local_samples
                ),
                default=0,
            )
            if object_density_sample > 0:
                object_density.add(cell)
            underwater = (
                water_sample_threshold is not None
                and center_sample < water_sample_threshold
            )
            if underwater:
                water.add(cell)
            below_floor = (
                resolved.minimum_traversable_sample is not None
                and center_sample < resolved.minimum_traversable_sample
            )
            if below_floor or sample_delta >= resolved.blocked_sample_delta:
                navigation_map.mark_blocked(cell)
                blocked.add(cell)
                continue
            cost = 1.0
            if sample_delta != 0 and resolved.maximum_traversal_cost != 1:
                cost = 1 + (
                    sample_delta
                    / resolved.blocked_sample_delta
                    * (resolved.maximum_traversal_cost - 1)
                )
            if underwater:
                cost = max(cost, resolved.water_traversal_cost)
            if object_density_sample > 0:
                cost = max(
                    cost,
                    1
                    + object_density_sample
                    / 255.0
                    * (resolved.maximum_object_density_cost - 1),
                )
            if cost > 1:
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
        window_center_lt=window_center_lt,
        window_center_lg=window_center_lg,
        window_radius=(resolved.seed_radius if window_center_lt is not None else None),
        sampled_cells=sampled_cells,
        blocked_cells=frozenset(blocked),
        water_cells=frozenset(water),
        object_density_cells=frozenset(object_density),
        object_density_layers=tuple(
            TerrainObjectDensityLayerSeed(
                layer_index=layer.layer_index,
                terrain_group_id=layer.raster.group_id,
                terrain_map_id=layer.raster.map_id,
                object_count=len(layer.object_keys),
                population_capacity=layer.population_capacity,
                maximum_horizontal_radius=layer.maximum_horizontal_radius,
            )
            for layer in object_density_layers
        ),
        water_sample_threshold=water_sample_threshold,
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
