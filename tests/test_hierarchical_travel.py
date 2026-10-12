"""Production fine-leg routing reuses the accepted subgrid with a retained guide."""

from dataclasses import replace

import pytest
from test_adaptive_travel import StaticNavigationSource, _observation
from test_travel_refinement_guidance import concavity

from shadowbane_lab.travel import (
    AStarRouteNotFound,
    AStarTravelController,
    NavigationCell,
    NavigationMapSnapshot,
    SparseNavigationMap,
    TravelControllerConfig,
    TravelDestination,
    TravelPhase,
    WeightedAStarPlanner,
)


class RecordingPlanner(WeightedAStarPlanner):
    def __init__(self):
        super().__init__()
        self.coarse_calls = 0
        self.fine_routes = []

    def plan(self, *args, **kwargs):
        self.coarse_calls += 1
        return super().plan(*args, **kwargs)

    def plan_refined(self, *args, **kwargs):
        route = super().plan_refined(*args, **kwargs)
        self.fine_routes.append(route)
        return route


def controller(navigation, goal, *, planner=None, maximum_replans=1):
    return AStarTravelController(
        goal, TravelControllerConfig(click_interval_ms=100, maximum_clicks=100),
        StaticNavigationSource(navigation), planner=planner, maximum_replans=maximum_replans,
    )


def accepted(travel, now, lt, lg):
    result = travel.propose(_observation(now, lt, lg))
    travel.acknowledge_dispatch(result)
    return result


@pytest.mark.parametrize("costly", [False, True])
def test_first_fine_leg_retains_concave_detour_and_every_remaining_turn(costly):
    navigation = SparseNavigationMap(cell_size=10)
    concavity(navigation, costly=costly)
    planner = RecordingPlanner()
    travel = controller(navigation, TravelDestination(305, 5, 5), planner=planner)
    first = accepted(travel, 0, 5, 5)
    guide = travel._itinerary
    assert planner.coarse_calls == 1 and len(planner.fine_routes) == 1
    assert planner.fine_routes[0].grid.cell_size == 5
    assert first.click_destination.x < 5  # leave the pocket, despite an eastward goal
    now = 100
    visited = []
    while not first.terminal and now < 10000:
        for point in travel.active_plan.destinations:
            visited.append((point.lt, point.lg))
            first = accepted(travel, now, point.lt, point.lg)
            now += 100
            if first.terminal:
                break
        assert travel._itinerary is guide
    assert first.phase is TravelPhase.COMPLETE
    assert any(lt < -50 for lt, _ in visited)
    assert any(abs(lg) > 50 for _, lg in visited)
    assert planner.coarse_calls == 1 and len(planner.fine_routes) > 2
    assert travel.replan_count == 0
    assert first.arrival_destination == TravelDestination(305, 5, 5)


def test_many_successful_fine_slices_do_not_spend_recovery_budget_or_rebuild_coarse():
    planner = RecordingPlanner()
    travel = controller(SparseNavigationMap(cell_size=10), TravelDestination(1805, 5, 5),
                        planner=planner)
    decision = accepted(travel, 0, 5, 5)
    for now in range(100, 6000, 100):
        assert decision.phase is TravelPhase.TRAVELING
        point = travel.active_plan.destinations[-1]
        decision = accepted(travel, now, point.lt, point.lg)
        if decision.terminal:
            break
    assert decision.phase is TravelPhase.COMPLETE
    assert len(planner.fine_routes) > 12 and planner.coarse_calls == 1
    assert travel.replan_count == 0 and travel.direct_fallback_count == 0


def test_leg_boundary_defer_restores_suffix_and_does_not_consume_attempt():
    planner = RecordingPlanner()
    travel = controller(SparseNavigationMap(cell_size=10), TravelDestination(205, 5, 5),
                        planner=planner)
    first = accepted(travel, 0, 5, 5)
    committed_plan, guide = travel.active_plan, travel._itinerary
    point = committed_plan.destinations[-1]
    observation = _observation(100, point.lt, point.lg)
    proposal = travel.propose(observation)
    assert travel.active_plan != committed_plan and proposal.click_destination is not None
    travel.defer_dispatch(proposal, observation)
    assert travel.active_plan is committed_plan and travel._itinerary is guide
    assert travel._attempt_count == first.click_count and travel.replan_count == 0
    waiting = travel.observe_deferred(_observation(200, point.lt, point.lg))
    assert waiting.phase is TravelPhase.TRAVELING and waiting.arrival_destination is None
    retry = accepted(travel, 300, point.lt, point.lg)
    assert retry.decision_id > proposal.decision_id
    assert retry.click_destination.x > point.lt and retry.click_count == first.click_count + 1
    assert planner.coarse_calls == 1 and travel._itinerary is guide


def test_reached_coarse_bend_defer_does_not_skip_next_mandatory_bend():
    navigation = SparseNavigationMap(cell_size=10)
    concavity(navigation)
    travel = controller(navigation, TravelDestination(305, 5, 5))
    accepted(travel, 0, 5, 5)
    guide = travel._itinerary
    bend = guide.destinations[0]
    proposal = travel.propose(_observation(100, bend.lt, bend.lg))
    assert travel._itinerary_index == 1
    travel.defer_dispatch(proposal, _observation(100, bend.lt, bend.lg))
    assert travel._itinerary_index == 0
    retry = accepted(travel, 200, bend.lt, bend.lg)
    assert travel._itinerary_index == 1 and travel._itinerary is guide
    assert retry.phase is TravelPhase.TRAVELING


def test_initial_fine_route_uses_persisted_child_precision_without_changing_map():
    navigation = SparseNavigationMap(cell_size=20)
    navigation.mark_refined_learned_blocked(NavigationCell(3, 0), NavigationCell(6, 0))
    planner = RecordingPlanner()
    travel = controller(navigation, TravelDestination(205, 5, 5), planner=planner)
    coarse, fine = navigation.learned_blocked, navigation.refined_learned_blocked
    first = accepted(travel, 0, 5, 5)
    assert first.phase is TravelPhase.TRAVELING
    assert len(planner.fine_routes) == 1 and planner.fine_routes[0].grid.cell_size == 10
    assert NavigationCell(6, 0) in planner.fine_routes[0].grid.blocked
    assert navigation.learned_blocked == coarse and navigation.refined_learned_blocked == fine


def test_fine_failure_preserves_original_coarse_suffix_and_grid():
    class Unavailable(RecordingPlanner):
        def plan_refined(self, *args, **kwargs):
            raise AStarRouteNotFound("bounded fine grid unavailable")

    navigation = SparseNavigationMap(cell_size=10)
    concavity(navigation)
    travel = controller(navigation, TravelDestination(305, 5, 5), planner=Unavailable())
    first = accepted(travel, 0, 5, 5)
    assert first.click_destination.x < 5
    assert travel.active_plan.destinations == travel._itinerary.destinations
    assert travel.route_mode == "astar_final" and travel.direct_fallback_count == 0


def test_terrain_identity_change_replaces_guide_without_losing_learned_evidence():
    navigation = SparseNavigationMap(cell_size=10)
    navigation.mark_refined_learned_blocked(NavigationCell(9, 1), NavigationCell(18, 2))
    planner = RecordingPlanner()
    travel = controller(navigation, TravelDestination(305, 5, 5), planner=planner)
    accepted(travel, 0, 5, 5)
    old = travel._itinerary
    travel._navigation_source.snapshot = NavigationMapSnapshot("static:2", navigation)
    accepted(travel, 100, 25, 5)
    assert travel._itinerary is not old and planner.coarse_calls == 2
    assert navigation.refined_learned_blocked == frozenset({NavigationCell(18, 2)})


def test_true_final_arrival_uses_original_region_even_with_blocked_goal():
    navigation = SparseNavigationMap(cell_size=10)
    navigation.mark_blocked(NavigationCell(10, 0))
    goal = TravelDestination(105, 5, 25)
    travel = controller(navigation, goal)
    first = accepted(travel, 0, 5, 5)
    assert first.phase is TravelPhase.TRAVELING
    # Physical position inside the actual goal region is sufficient, independent
    # of a planner-selected alternate endpoint or a stale intermediate hint.
    arrived = travel.observe_deferred(_observation(100, 85, 5))
    assert arrived.phase is TravelPhase.COMPLETE and arrived.arrival_destination == goal
    assert arrived.distance_remaining == 20


def test_fine_continuation_preserves_original_session_deadline():
    travel = controller(SparseNavigationMap(cell_size=10), TravelDestination(205, 5, 5))
    travel._config = replace(travel._config, maximum_session_ms=250)
    accepted(travel, 0, 5, 5)
    for now in (100, 200):
        point = travel.active_plan.destinations[-1]
        accepted(travel, now, point.lt, point.lg)
    result = travel.observe_deferred(_observation(250, 125, 5))
    assert result.terminal_reason == "session_timeout" and travel.replan_count == 0


@pytest.mark.parametrize("frontier", [False, True])
def test_swept_local_frontier_passage_does_not_weaken_true_final_arrival(frontier):
    from shadowbane_lab.travel import TravelController, TravelPlan

    travel = TravelController(
        TravelPlan("passage", (TravelDestination(65, 5, 5),)),
        TravelControllerConfig(click_interval_ms=100), final_is_frontier=frontier,
    )
    first = travel.propose(_observation(0, 5, 5))
    travel.acknowledge_dispatch(first)
    passed = travel.propose(_observation(100, 85, 5))
    assert (passed.phase is TravelPhase.COMPLETE) is frontier
    travel.defer_dispatch(passed, _observation(100, 85, 5))
    next_observation = travel.observe_deferred(_observation(200, 85, 5))
    assert (next_observation.phase is TravelPhase.COMPLETE) is frontier


def test_already_reached_replacement_frontier_never_claims_global_arrival_or_loops():
    class ReachedFrontier(RecordingPlanner):
        def plan_refined(self, *args, **kwargs):
            route = super().plan_refined(*args, **kwargs)
            return replace(route, destinations=(TravelDestination(
                kwargs["start_lt"], kwargs["start_lg"], 5,
            ),))

    planner = ReachedFrontier()
    travel = controller(SparseNavigationMap(cell_size=10), TravelDestination(205, 5, 5),
                        planner=planner)
    decision = accepted(travel, 0, 5, 5)
    assert decision.phase is TravelPhase.TRAVELING and decision.arrival_destination is None
    assert len(planner.fine_routes) == 2  # bounded work, no spin on a reached frontier
    assert travel.replan_count == 0
