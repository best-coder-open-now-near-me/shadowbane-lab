"""A native parent handoff never acknowledges an unsubmitted travel proposal."""
from dataclasses import replace

import pytest
from test_coordinate_parent_session import native as native

from shadowbane_lab.client_extension import movement_wire as wire
from shadowbane_lab.client_extension.movement_dispatcher import NativeMovementTravelDispatcher
from shadowbane_lab.client_extension.movement_session import NativeMovementCleanupPending
from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.protocol import DispatchResult, Vector2
from shadowbane_lab.travel.adaptive import AStarTravelController
from shadowbane_lab.travel.controller import TravelController
from shadowbane_lab.travel.model import (
    TravelControllerConfig,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
)
from shadowbane_lab.travel.pathfinding import (
    NavigationCell,
    NavigationCostGrid,
    NavigationMapSnapshot,
    NavigationPlanningWindow,
    SparseNavigationMap,
)
from shadowbane_lab.travel.runtime import TravelDispatchDeferred, TravelRunner


def observation(t, x=5, y=5, health=100):
    return TravelObservation(
        t, NativePlayerPositionObservation(x, y, 0),
        NativePlayerVitalsObservation(health, 100, 100, 100, 100, 100),
    )


def config(**options):
    return TravelControllerConfig(**{
        "click_interval_ms": 100, "maximum_no_progress_clicks": 1,
        "maximum_session_ms": 2000, **options,
    })


def controller(**options):
    return TravelController(TravelPlan("defer", (TravelDestination(205, 5, 5),)),
                            config(**options))


class Navigation:
    def __init__(self):
        self.map = SparseNavigationMap(cell_size=10)
        self.reads = 0

    def observe(self, _position):
        self.reads += 1
        return NavigationMapSnapshot("scene:1", self.map)


def adaptive(**options):
    source = Navigation()
    return AStarTravelController(TravelDestination(205, 5, 5), config(**options), source), source


class Client:
    def __init__(self, positions=(5,), *, pending_until=0, race=False, stop_at=None,
                 escape_result=None, preflight_error=None):
        self.now = 0.0
        self.positions = iter(positions)
        self.position = 5
        self.pending_until = pending_until
        self.race = race
        self.stop_at = stop_at
        self.escape_result = escape_result
        self.preflight_error = preflight_error
        self.attempted = []
        self.accepted = []
        self.stops = []
        self.reads = 0

    def observe(self):
        self.reads += 1
        self.position = next(self.positions, self.position)
        return observation(0, self.position).position

    def is_set(self):
        return self.stop_at is not None and self.now >= self.stop_at

    def prepare_dispatch(self):
        if self.preflight_error is not None:
            raise self.preflight_error
        if self.now < self.pending_until:
            raise TravelDispatchDeferred("parent cleanup pending")

    def dispatch(self, decision):
        self.attempted.append(decision)
        if self.race:
            self.race = False
            raise TravelDispatchDeferred("parent changed after observation")
        if decision.maneuver is not TravelManeuver.DIRECT and self.escape_result is not None:
            if isinstance(self.escape_result, Exception):
                raise self.escape_result
            return DispatchResult("test", str(decision.decision_id), False, "refused")
        self.accepted.append(decision)
        return DispatchResult("test", str(decision.decision_id), True)

    def stop_movement(self, decision):
        self.stops.append(decision)
        return DispatchResult("test", "stop", True)

    def sleep(self, duration):
        self.now = round(self.now + duration, 6)


class Vitals:
    def observe(self):
        return observation(0).player


def run(travel, client, dispatcher=None):
    return TravelRunner(
        controller=travel, position_reader=client, player_vitals_reader=Vitals(),
        dispatcher=dispatcher or client, stop_signal=client, poll_interval_ms=100,
        clock=lambda: client.now, sleeper=client.sleep,
    ).run()


@pytest.mark.parametrize("kind", ["direct", "astar"])
def test_race_resamples_position_without_spending_only_attempt_or_reusing_decision_id(kind):
    travel = controller(maximum_clicks=1) if kind == "direct" else adaptive(maximum_clicks=1)[0]
    client = Client((5, 25), race=True, stop_at=0.2)
    result = run(travel, client)
    assert result.terminal_reason == "emergency_stop"
    assert result.clicks == 1
    assert len(client.attempted) == 2 and len(client.accepted) == 1
    assert client.accepted[0].click_destination == Vector2(75, 5)
    assert client.attempted[1].decision_id > client.attempted[0].decision_id
    waiting = result.trace[0]
    assert waiting.input_accepted is None and waiting.decision.click_count == 0
    assert waiting.decision.click_destination is None
    assert waiting.input_reason is None
    assert len(client.stops) == 1


def test_preflight_wait_does_not_plan_until_ready_or_reset_original_deadline():
    travel, source = adaptive(maximum_session_ms=500)
    client = Client(pending_until=0.4)
    result = run(travel, client)
    assert source.reads == 1
    assert len(client.accepted) == 1
    assert client.accepted[0].now_ms == 400
    assert result.terminal_reason == "session_timeout"
    assert result.trace[-1].decision.now_ms == 500


@pytest.mark.parametrize("kind", ["direct", "astar"])
@pytest.mark.parametrize("ending", ["timeout", "cancel"])
def test_pending_cannot_outlive_session_or_requested_cancel(kind, ending):
    travel = controller(maximum_session_ms=300) if kind == "direct" else adaptive(
        maximum_session_ms=300)[0]
    client = Client(pending_until=10, stop_at=0.2 if ending == "cancel" else None)
    result = run(travel, client)
    assert result.terminal_reason == ("emergency_stop" if ending == "cancel" else "session_timeout")
    assert result.clicks == 0 and not client.attempted and not client.stops
    assert client.now <= 0.3


def test_pending_still_observes_low_health():
    travel = controller()
    assert travel.observe_deferred(observation(0, health=1)).terminal_reason == "low_player_health"


def test_rejected_shortcut_does_not_consume_hint_but_observed_passage_survives():
    grid = NavigationCostGrid(10, NavigationCell(-2, -2), NavigationCell(30, 30))
    travel = TravelController(
        TravelPlan("corner", (TravelDestination(45, 5, 5), TravelDestination(45, 85, 5))),
        config(click_interval_ms=2000),
        shortcut_clear=lambda start, path: grid.shortcut_clear(
            (start.x, start.y), tuple((p.x, p.y) for p in path)),
    )
    first = travel.propose(observation(0))
    travel.acknowledge_dispatch(first)
    turn = travel.propose(observation(400, 25))
    assert turn.waypoint_index == 1 and turn.click_destination == Vector2(45, 25)
    waiting = travel.defer_dispatch(turn, observation(400, 25))
    assert waiting.waypoint_index == 0 and waiting.click_count == 1
    again = travel.propose(observation(500, 25))
    assert again.waypoint_index == 0 and again.click_destination == Vector2(45, 5)
    travel.acknowledge_dispatch(again)

    # Actual motion past the intermediate remains observed, even if submission races.
    passed = travel.propose(observation(600, 50))
    assert passed.waypoint_index == 1
    travel.defer_dispatch(passed, observation(600, 50))
    next_step = travel.propose(observation(700, 55))
    assert next_step.waypoint_index == 1
    travel.acknowledge_dispatch(next_step)


def test_preflight_pause_keeps_actual_swept_waypoint_passage():
    travel = TravelController(
        TravelPlan("pass", (TravelDestination(105, 5, 5), TravelDestination(205, 5, 5))),
        config(),
    )
    first = travel.propose(observation(0, 95))
    travel.acknowledge_dispatch(first)
    assert travel.observe_deferred(observation(100, 115)).waypoint_index == 1
    resumed = travel.propose(observation(200, 120))
    assert resumed.waypoint_index == 1 and resumed.maneuver is TravelManeuver.DIRECT
    travel.acknowledge_dispatch(resumed)


def test_escape_proposal_learns_only_after_acceptance_not_during_native_pause():
    travel, source = adaptive()
    first = travel.propose(observation(0))
    travel.acknowledge_dispatch(first)
    escape = travel.propose(observation(100))
    assert escape.maneuver is TravelManeuver.ESCAPE_BACKTRACK
    assert not source.map.learned_blocked
    waiting = travel.defer_dispatch(escape, observation(100))
    assert waiting.click_count == 1 and not source.map.learned_blocked
    travel.observe_deferred(observation(500))
    resumed = travel.propose(observation(900))
    assert resumed.maneuver is TravelManeuver.DIRECT  # known pause is not a collision
    travel.acknowledge_dispatch(resumed)
    real_stall = travel.propose(observation(1000))
    assert real_stall.maneuver is TravelManeuver.ESCAPE_BACKTRACK
    assert not source.map.learned_blocked
    travel.acknowledge_dispatch(real_stall)
    assert source.map.learned_blocked


@pytest.mark.parametrize("failure", [False, RuntimeError("native failed")])
def test_rejected_or_exceptional_escape_terminates_without_learning_unsubmitted_command(failure):
    travel, source = adaptive()
    client = Client(escape_result=failure)
    result = run(travel, client)
    assert result.terminal_reason == (
        "input_failure:RuntimeError" if isinstance(failure, Exception) else "guarded_input_rejected"
    )
    assert result.clicks == 1 and len(client.attempted) == 2 and len(client.stops) == 1
    assert not source.map.learned_blocked
    assert result.trace[-2].input_accepted is False


def test_nonpending_preflight_failure_is_terminal_not_retried_as_observation_failure():
    client = Client(preflight_error=RuntimeError("grant revoked"))
    result = run(controller(), client)
    assert result.terminal_reason == "input_failure:RuntimeError"
    assert client.reads == 1 and not client.attempted


def test_proposal_acknowledgement_is_exact_and_clock_does_not_rewind_after_defer():
    travel = controller()
    first = travel.propose(observation(100))
    with pytest.raises(RuntimeError, match="match"):
        travel.acknowledge_dispatch(replace(first, decision_id=first.decision_id + 1))
    with pytest.raises(RuntimeError, match="resolved"):
        travel.propose(observation(200))
    travel.defer_dispatch(first, observation(100))
    with pytest.raises(ValueError, match="backwards"):
        travel.propose(observation(99))
    next_step = travel.propose(observation(200))
    assert next_step.decision_id > first.decision_id and next_step.click_count == 1
    travel.acknowledge_dispatch(next_step)


def test_observed_horizon_during_pause_is_not_global_arrival():
    source = Navigation()
    source.observe = lambda _: NavigationMapSnapshot(
        "horizon:1", source.map, NavigationPlanningWindow(5, 5, 100, 50),
    )
    travel = AStarTravelController(TravelDestination(500, 5, 5), config(), source)
    first = travel.propose(observation(0))
    travel.acknowledge_dispatch(first)
    assert travel.route_mode == "astar_horizon"
    frontier = travel.active_plan.destinations[-1]
    waiting = travel.observe_deferred(observation(100, frontier.lt, frontier.lg))
    assert waiting.phase is TravelPhase.TRAVELING
    assert waiting.arrival_destination is None and waiting.terminal_reason is None
    continued = travel.propose(observation(200, frontier.lt, frontier.lg))
    assert continued.phase is TravelPhase.TRAVELING
    assert continued.click_destination is not None and travel.replan_count == 1
    travel.acknowledge_dispatch(continued)


def test_real_native_session_and_dispatcher_race_defers_only_unentered_destination(native):
    grant = native.acquire()
    native.destination_race = wire.Outcome.STALE
    dispatcher = NativeMovementTravelDispatcher(native.session, grant)
    result = run(controller(maximum_clicks=1), Client((5, 25), stop_at=0.2), dispatcher)
    assert result.terminal_reason == "emergency_stop" and result.clicks == 1
    assert result.trace[0].input_accepted is None
    assert result.trace[0].decision.click_destination is None
    moves = [command for command in native.commands if command.kind is wire.Verb.DESTINATION]
    assert len(moves) == 2
    assert moves[0].payload.expected != moves[1].payload.expected
    assert moves[1].payload.destination == (75, 0, -5)
    assert moves[0].payload.request_key != moves[1].payload.request_key
    assert sum(command.kind is wire.Verb.ACQUIRE_COORDINATE for command in native.commands) == 1
    assert sum(step.input_accepted is True for step in result.trace) == 1


def test_real_dispatcher_generic_cleanup_failure_is_not_a_deferred_handoff(native, monkeypatch):
    grant = native.acquire()

    def ordinary_cleanup(*_args):
        raise NativeMovementCleanupPending("ordinary cleanup remains guarded")

    monkeypatch.setattr(native.session, "move", ordinary_cleanup)
    result = run(controller(), Client(), NativeMovementTravelDispatcher(native.session, grant))
    assert result.terminal_reason == "guarded_input_rejected" and result.clicks == 0
    assert result.trace[0].input_accepted is False
    assert result.trace[0].input_reason == "native_movement_cleanup_pending"
