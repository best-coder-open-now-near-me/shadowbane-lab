"""World-coordinate corridor checks use the actual immutable planning grid."""

from math import inf, nan

import pytest

from shadowbane_lab.travel.model import TravelDestination
from shadowbane_lab.travel.pathfinding import (
    NavigationCell,
    NavigationCostGrid,
    SparseNavigationMap,
    WeightedAStarConfig,
    WeightedAStarPlanner,
)


def grid(*blocked, costs=()):
    return NavigationCostGrid(
        1.0, NavigationCell(-2, -2), NavigationCell(5, 5),
        blocked=frozenset(NavigationCell(*cell) for cell in blocked),
        costs=tuple((NavigationCell(*cell), cost) for cell, cost in costs),
    )


def test_actual_subcell_segment_visits_cells_not_just_endpoint_centers():
    # The shallow line enters (1, 0) before crossing Y=1 inside that cell.
    blocked = grid((1, 0))
    assert not blocked.segment_clear(0.1, 0.9, 2.9, 1.1)
    assert not blocked.segment_clear(2.9, 1.1, 0.1, 0.9)
    assert blocked.segment_clear(0.1, 1.1, 2.9, 1.1)


@pytest.mark.parametrize("wall", [(1, 0), (0, 1)])
def test_diagonal_corner_contact_cannot_cut_a_wall(wall):
    corridor = grid(wall)
    assert not corridor.segment_clear(0.5, 0.5, 1.5, 1.5)
    assert not corridor.segment_clear(1.5, 1.5, 0.5, 0.5)


@pytest.mark.parametrize("wall", [(1, 0), (1, 1)])
def test_travel_along_cell_boundary_checks_both_sides(wall):
    assert not grid(wall).segment_clear(0.5, 1, 2.5, 1)
    assert not grid((wall[1], wall[0])).segment_clear(1, 0.5, 1, 2.5)


def test_endpoint_contact_and_zero_length_are_not_wall_bypasses():
    corridor = grid((1, 1))
    assert not corridor.segment_clear(0.5, 0.5, 1, 1)
    assert not corridor.segment_clear(1, 1, 1, 1)
    assert corridor.segment_cost(0.5, 0.5, 0.5, 0.5) == 0


@pytest.mark.parametrize("endpoint", [(nan, 1), (inf, 1), (1, -inf), (6, 1), (-3, 1)])
def test_invalid_or_uncovered_endpoints_are_not_clear(endpoint):
    assert not grid().segment_clear(0.5, 0.5, *endpoint)


def test_cost_integrates_world_distance_and_is_symmetric():
    corridor = grid(costs=(((1, 0), 3.0),))
    assert corridor.segment_cost(0.5, 0.5, 2.5, 0.5) == pytest.approx(4.0)
    assert corridor.segment_cost(2.5, 0.5, 0.5, 0.5) == pytest.approx(4.0)
    assert corridor.segment_cost(-1.5, -1.5, -0.5, -0.5) == pytest.approx(2 ** 0.5)


def test_shortcut_retains_density_cost_and_structural_detour():
    path = ((0.5, 2.5), (2.5, 2.5), (2.5, 0.5))
    assert grid().shortcut_clear((0.5, 0.5), path)
    assert not grid(costs=(((1, 0), 10.0),)).shortcut_clear((0.5, 0.5), path)
    assert not grid((1, 0)).shortcut_clear((0.5, 0.5), path)
    assert not grid().shortcut_clear((0.5, 0.5), ())


def test_grid_preserves_all_blocker_layers_and_remains_a_snapshot():
    navigation = SparseNavigationMap(cell_size=1)
    navigation.mark_blocked(NavigationCell(1, 0))
    navigation.mark_learned_blocked(NavigationCell(2, 0))
    navigation.mark_terrain_blocked(NavigationCell(3, 0))
    snapshot = navigation.local_grid(
        NavigationCell(0, 0), NavigationCell(4, 0),
        WeightedAStarConfig(obstacle_clearance_cells=0),
    )
    for x in (1, 2, 3):
        assert not snapshot.segment_clear(x + 0.25, 0.5, x + 0.75, 0.5)
    navigation.mark_blocked(NavigationCell(4, 0))
    assert snapshot.segment_clear(4.25, 0.5, 4.75, 0.5)


def test_plans_retain_actual_grid_including_refined_resolution():
    navigation = SparseNavigationMap(cell_size=20)
    planner = WeightedAStarPlanner(WeightedAStarConfig(obstacle_clearance_cells=0))
    options = dict(start_lt=5, start_lg=5, destination=TravelDestination(95, 5, 5))
    coarse = planner.plan(navigation, **options)
    refined = planner.plan_refined(navigation, **options)
    assert coarse.grid.cell_size == 20
    assert refined.grid.cell_size == 10
    assert coarse.grid.segment_clear(5, 5, 95, 5)
    assert refined.grid.segment_clear(5, 5, 95, 5)
    frontier = planner.plan_reachable_frontier(navigation, **options)
    assert frontier.grid.cell_size == 20
