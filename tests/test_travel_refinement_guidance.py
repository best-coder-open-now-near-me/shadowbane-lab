"""Geometric recovery regressions for coarse-route guided local refinement."""

from math import hypot

import pytest
from test_adaptive_travel import StaticNavigationSource, _observation

from shadowbane_lab.travel import (
    AStarRouteNotFound,
    AStarTravelController,
    NavigationCell,
    SparseNavigationMap,
    TravelControllerConfig,
    TravelDestination,
    TravelManeuver,
    TravelPhase,
    WeightedAStarPlanner,
)


def concavity(navigation, *, costly=False):
    # A long pocket opens west, while the goal lies east. A short eastward
    # fine route looks clear but heads deeper into the known dead end.
    cells = {NavigationCell(x, y) for x in range(-5, 16) for y in (-5, 5)}
    cells.update(NavigationCell(15, y) for y in range(-5, 6))
    for cell in cells:
        if costly:
            navigation.set_cost(cell, 100.0)
        else:
            navigation.mark_blocked(cell)


def recovering_controller(navigation, planner=None):
    controller = AStarTravelController(
        TravelDestination(305, 5, 75),
        TravelControllerConfig(
            click_interval_ms=100, minimum_progress=5, maximum_no_progress_clicks=1
        ),
        StaticNavigationSource(navigation),
        planner=planner,
    )
    first = controller.propose(_observation(0, 5, 5))
    controller.acknowledge_dispatch(first)
    backup = controller.propose(_observation(100, 5, 5))
    assert backup.maneuver is TravelManeuver.ESCAPE_BACKTRACK
    controller.acknowledge_dispatch(backup)
    return controller


@pytest.mark.parametrize("costly", [False, True])
def test_recovery_keeps_known_detour_instead_of_entering_long_pocket(costly):
    navigation = SparseNavigationMap(cell_size=10)
    controller = recovering_controller(navigation)
    learned = navigation.refined_learned_blocked
    concavity(navigation, costly=costly)
    decision = controller.propose(_observation(200, -5, 5))
    controller.acknowledge_dispatch(decision)
    assert decision.phase is TravelPhase.TRAVELING
    assert decision.maneuver is TravelManeuver.DIRECT
    assert controller.route_mode == "astar_refined_local"
    endpoint = controller.active_plan.destinations[-1]
    assert endpoint.lt < -5  # the selected coarse detour leaves the pocket west
    assert hypot(endpoint.lt + 5, endpoint.lg - 5) <= 60.000001
    assert decision.click_destination.x < -5
    assert navigation.refined_learned_blocked == learned

    # Reaching the bounded fine endpoint must continue the coarse route, even
    # though the global goal has a much larger arrival radius.
    now = 300
    for waypoint in controller.active_plan.destinations:
        decision = controller.propose(_observation(now, waypoint.lt, waypoint.lg))
        controller.acknowledge_dispatch(decision)
        now += 100
    assert decision.phase is TravelPhase.TRAVELING
    assert controller.replan_count == 1
    assert controller._itinerary.destinations[-1] == TravelDestination(305, 5, 75)
    assert controller.route_mode == "astar_refined_local"
    assert navigation.refined_learned_blocked == learned


def test_unreachable_fine_route_keeps_original_coarse_detour():
    class CoarseOnly(WeightedAStarPlanner):
        def plan_refined(self, *args, **kwargs):
            raise AStarRouteNotFound("fine corridor unavailable")

    navigation = SparseNavigationMap(cell_size=10)
    planner = CoarseOnly()
    controller = recovering_controller(navigation, planner)
    concavity(navigation)
    expected = planner.plan(
        navigation, start_lt=-5, start_lg=5, destination=TravelDestination(305, 5, 75)
    )
    decision = controller.propose(_observation(200, -5, 5))
    controller.acknowledge_dispatch(decision)
    assert controller.active_plan.destinations == expected.destinations
    assert controller.route_mode == "astar_final"
    assert decision.phase is TravelPhase.TRAVELING


def test_unobstructed_refinement_keeps_actual_final_destination():
    navigation = SparseNavigationMap(cell_size=10)
    goal = TravelDestination(45, 5, 5)
    controller = AStarTravelController(
        goal, TravelControllerConfig(), StaticNavigationSource(navigation)
    )
    observation = _observation(0, 5, 5)
    controller.step(observation)
    follower, reaches_goal, mode = controller._plan(
        observation,
        reason="learned_obstacle",
        allow_partial_fallback=True,
    )
    assert reaches_goal
    assert mode == "astar_refined_final"
    assert follower.plan.destinations == (goal,)
