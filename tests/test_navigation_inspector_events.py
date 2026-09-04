"""Exercise diagnostic capture through the production planner/controllers."""

from dataclasses import FrozenInstanceError

import pytest

from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.navigation_inspector.events import MotionEvent, PlanEvent
from shadowbane_lab.travel import (
    AStarRouteNotFound,
    AStarTravelController,
    NavigationCell,
    NavigationMapSnapshot,
    SparseNavigationMap,
    TravelController,
    TravelControllerConfig,
    TravelDestination,
    TravelObservation,
    TravelPlan,
    WeightedAStarConfig,
    WeightedAStarPlanner,
)


def observation(now_ms=0, lt=5.0, lg=5.0):
    return TravelObservation(
        now_ms,
        NativePlayerPositionObservation(lt, lg, 7.0),
        NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100),
    )


def broken_observer(_event):
    raise OSError("diagnostic transport unavailable")


def test_raw_search_and_actual_destination_survive_smoothing():
    events = []
    navigation = SparseNavigationMap(cell_size=10.0)
    goal = TravelDestination(97.0, 5.0, 6.0)
    route = WeightedAStarPlanner(observer=events.append).plan(
        navigation,
        start_lt=5.0,
        start_lg=5.0,
        destination=goal,
    )
    event = events[0]
    assert isinstance(event, PlanEvent)
    assert len(event.raw_path) > len(event.smoothed_path) == len(route.cells) == 2
    assert event.raw_path[0] == (5.0, 5.0)
    assert event.destinations == tuple((p.lt, p.lg, p.arrival_radius) for p in route.destinations)
    assert event.destinations[-1] == (97.0, 5.0, 6.0)
    assert event.mode == "complete"
    with pytest.raises(FrozenInstanceError):
        event.mode = "failed"


def test_map_evidence_does_not_double_inflate_or_merge_learned_cells():
    events = []
    navigation = SparseNavigationMap(cell_size=10.0)
    navigation.mark_blocked(NavigationCell(3, 0))
    navigation.mark_learned_blocked(NavigationCell(5, 0))
    WeightedAStarPlanner(observer=events.append).plan(
        navigation,
        start_lt=5.0,
        start_lg=5.0,
        destination=TravelDestination(95.0, 5.0, 5.0),
    )
    event = events[0]
    assert event.physical_blocked == ((3, 0),)
    assert event.learned_blocked == ((5, 0),)
    assert event.planner_clearance_cells == 1
    navigation.mark_blocked(NavigationCell(4, 4))
    assert event.physical_blocked == ((3, 0),)


def test_observer_failure_preserves_route_and_search_failure():
    navigation = SparseNavigationMap(cell_size=10.0)
    args = dict(start_lt=5.0, start_lg=5.0, destination=TravelDestination(195.0, 5.0))
    assert WeightedAStarPlanner().plan(navigation, **args) == WeightedAStarPlanner(
        observer=broken_observer,
    ).plan(navigation, **args)
    config = WeightedAStarConfig(maximum_expansions=1)
    failures = []
    for observer in (None, broken_observer):
        with pytest.raises(AStarRouteNotFound) as error:
            WeightedAStarPlanner(config, observer=observer).plan(navigation, **args)
        failures.append(str(error.value))
    assert failures[0] == failures[1]


def test_failed_route_clears_previous_success_and_frontier_is_distinct():
    events = []
    navigation = SparseNavigationMap(cell_size=10.0)
    args = dict(start_lt=5.0, start_lg=5.0, destination=TravelDestination(995.0, 5.0))
    planner = WeightedAStarPlanner(
        WeightedAStarConfig(maximum_expansions=4), observer=events.append
    )
    with pytest.raises(AStarRouteNotFound):
        planner.plan(navigation, **args)
    assert events[-1].mode == "failed"
    assert events[-1].raw_path == events[-1].destinations == ()
    assert events[-1].failure_reason
    route = planner.plan_reachable_frontier(navigation, **args)
    assert events[-1].mode == "frontier"
    assert events[-1].destinations[-1][:2] == (route.destinations[-1].lt, route.destinations[-1].lg)


def test_controller_events_describe_real_stall_and_preserve_decisions():
    events = []
    plan = TravelPlan("inspector-test", (TravelDestination(95.0, 5.0, 5.0),))
    config = TravelControllerConfig(click_interval_ms=100, maximum_no_progress_clicks=1)
    controllers = [
        TravelController(plan, config, observer=sink)
        for sink in (None, events.append, broken_observer)
    ]
    for sample in (observation(0), observation(100), observation(200)):
        decisions = [controller.step(sample) for controller in controllers]
        assert decisions[0] == decisions[1] == decisions[2]
    names = [e.event for e in events]
    assert "start" in names and "stall" in names and "escape_planned" in names
    commands = [e for e in events if e.event == "command_requested"]
    assert commands and all(e.position == (5.0, 5.0, 7.0) for e in commands)
    assert all(e.direction is not None for e in commands)
    assert all(e.destination == (95.0, 5.0, 5.0) for e in commands)


def test_adaptive_replanning_keeps_the_same_observer_on_replacement_controller():
    events = []
    navigation = SparseNavigationMap(cell_size=10.0)

    class Source:
        def observe(self, _position):
            return NavigationMapSnapshot("zone:1", navigation)

    controller = AStarTravelController(
        TravelDestination(95.0, 5.0, 5.0),
        TravelControllerConfig(click_interval_ms=100, maximum_no_progress_clicks=1),
        Source(),
        planner=WeightedAStarPlanner(observer=events.append),
    )
    controller.step(observation(0))
    controller.step(observation(100))
    plans = [e for e in events if isinstance(e, PlanEvent)]
    motions = [e for e in events if isinstance(e, MotionEvent)]
    assert len(plans) == 2
    assert plans[-1].learned_blocked
    assert any("learned_obstacle" in e.plan_id for e in motions)
    assert any(e.event == "stall" for e in motions)


def test_arrival_and_cancellation_emit_once_with_actual_position():
    for finish, expected in (("arrive", "completion"), ("stop", "cancelled")):
        events = []
        controller = TravelController(
            TravelPlan("dynamic", (TravelDestination(95.0, 5.0, 5.0),)),
            observer=events.append,
        )
        sample = observation(100, 95.0, 5.0)
        if finish == "arrive":
            controller.arrive(sample)
        else:
            controller.stop("user_stop", sample)
        controller.step(sample)
        assert [e.event for e in events] == [expected]
        assert events[0].position == (95.0, 5.0, 7.0)
