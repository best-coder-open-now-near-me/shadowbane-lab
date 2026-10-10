"""Re-sample inferred terrain, never erase confirmed obstruction evidence."""

from dataclasses import replace

import pytest

from shadowbane_lab.client_observation import NativeZoneGeometry
from shadowbane_lab.travel.model import TravelDestination
from shadowbane_lab.travel.pathfinding import (
    AStarRouteNotFound,
    NavigationCell,
    SparseNavigationMap,
    WeightedAStarConfig,
    WeightedAStarPlanner,
)
from shadowbane_lab.travel.terrain import TerrainNavigationConfig, seed_height_raster_navigation
from shadowbane_lab.world_data import TerrainAlphaRaster

GEOMETRY = NativeZoneGeometry(
    minimum_local_x=-100,
    minimum_local_z=-100,
    maximum_local_x=100,
    maximum_local_z=100,
    rotation_w=1,
    rotation_x=0,
    rotation_y=0,
    rotation_z=0,
    absolute_center_x=0,
    absolute_center_z=0,
    local_center_x=0,
    local_center_z=0,
    radius_x=100,
    radius_z=100,
)
CONFIG = WeightedAStarConfig(planning_margin_cells=2)
DESTINATION = TravelDestination(75, 15, 3)


def seeded(*, wall=False, maximum_seed_cells=50000):
    # A sharp ridge crosses the left part of the occupied coarse cell. The
    # character is on the flat right side, connected to the destination.
    row = bytes(200 if x <= 8 else (0 if wall and 45 <= x <= 55 else 100) for x in range(-100, 101))
    raster = TerrainAlphaRaster(7, 1, 201, 201, row * 201)
    navigation = SparseNavigationMap(cell_size=20)
    seed = seed_height_raster_navigation(
        navigation,
        geometry=GEOMETRY,
        raster=raster,
        zone_depth=0,
        template_group_id=0,
        template_id=3019,
        config=TerrainNavigationConfig(
            minimum_traversable_sample=1, maximum_seed_cells=maximum_seed_cells
        ),
    )
    return navigation, seed


def plan(navigation):
    return WeightedAStarPlanner(CONFIG).plan(
        navigation,
        start_lt=15,
        start_lg=15,
        destination=DESTINATION,
    )


def test_initial_failed_coarse_route_resamples_actual_raster_without_mutating_map():
    navigation, seed = seeded()
    original = navigation.blocked
    assert NavigationCell(0, 0) in seed.blocked_cells
    # The conservative fine view alone still repeats the coarse false positive.
    with pytest.raises(AStarRouteNotFound):
        WeightedAStarPlanner(CONFIG)._plan(
            navigation,
            start_lt=15,
            start_lg=15,
            destination=DESTINATION,
        )
    route = plan(navigation)
    assert route.destinations[-1] == DESTINATION
    assert navigation.blocked == original
    assert navigation.cell_size == 20
    assert len(navigation._terrain_sources) == 1


def test_actual_blocked_terrain_band_stays_blocked_at_fine_resolution():
    navigation, _ = seeded(wall=True)
    with pytest.raises(AStarRouteNotFound):
        plan(navigation)


@pytest.mark.parametrize("learned", [False, True])
def test_explicit_and_learned_walls_survive_terrain_resampling(learned):
    navigation, _ = seeded()
    mark = navigation.mark_learned_blocked if learned else navigation.mark_blocked
    for y in range(-10, 11):
        mark(NavigationCell(2, y))
    original = navigation.blocked
    with pytest.raises(AStarRouteNotFound):
        plan(navigation)
    assert navigation.blocked == original


def test_sampling_budget_failure_preserves_original_evidence():
    navigation, _ = seeded(maximum_seed_cells=150)
    original = navigation.blocked
    with pytest.raises(AStarRouteNotFound, match="bounded navigation seed size"):
        plan(navigation)
    assert navigation.blocked == original


def test_terrain_costs_and_explicit_costs_survive_both_refinement_views():
    navigation, _ = seeded()
    cell = NavigationCell(3, 0)
    navigation.set_cost(cell, 9)
    navigation.set_terrain_cost(cell, 4)
    conservative = navigation.refined_navigation_map()
    sampled = navigation.refined_navigation_map(terrain_bounds=(-20, -20, 100, 60))
    for view in (navigation, conservative, sampled):
        grid = view.local_grid(view.cell_for(15, 15), view.cell_for(75, 15), CONFIG)
        assert grid.traversal_cost(view.cell_for(65, 5)) == 9


def test_nonintersecting_retained_zone_cannot_corrupt_local_sampling():
    navigation, _ = seeded()
    other = replace(GEOMETRY, absolute_center_x=10000)
    seed_height_raster_navigation(
        navigation,
        geometry=other,
        raster=TerrainAlphaRaster(8, 1, 201, 201, bytes([100]) * 40401),
        zone_depth=0,
        template_group_id=0,
        template_id=3020,
    )
    assert plan(navigation).destinations[-1] == DESTINATION
