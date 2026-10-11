"""Continuous native destinations without weakening arrival or obstacle routing."""
from itertools import pairwise
from math import hypot

import pytest

from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.protocol import DispatchResult, Vector2
from shadowbane_lab.travel.controller import TravelController
from shadowbane_lab.travel.model import (
    TravelControllerConfig,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
)
from shadowbane_lab.travel.pathfinding import NavigationCell, NavigationCostGrid
from shadowbane_lab.travel.runtime import TravelRunner


def observation(t, x, y=5):
    return TravelObservation(t, NativePlayerPositionObservation(x, y, 0), vitals())


def vitals():
    return NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100)


def controller(*destinations, corridor=None, **options):
    return TravelController(
        TravelPlan("continuous", destinations or (TravelDestination(1005, 5, 5),)),
        TravelControllerConfig(click_interval_ms=2000, minimum_progress=8,
                               maximum_no_progress_clicks=2, **options),
        shortcut_clear=corridor,
    )


def test_extends_moving_endpoint_before_fixed_interval_without_reissuing_unchanged_target():
    travel = controller()
    first = travel.step(observation(0, 5))
    assert first.click_destination == Vector2(55, 5)
    assert travel.step(observation(200, 5)).click_destination is None  # solver still pending
    renewed = travel.step(observation(600, 35))
    assert renewed.click_destination == Vector2(85, 5)
    assert renewed.now_ms < 2000
    assert travel.step(observation(650, 38)).click_destination is None


def test_reached_clipped_endpoint_does_not_wait_for_periodic_retry():
    travel = controller()
    travel.step(observation(0, 5))
    renewed = travel.step(observation(1200, 55))
    assert renewed.click_destination == Vector2(105, 5)
    assert renewed.phase is TravelPhase.TRAVELING


def test_frequent_refresh_does_not_reset_actual_stall_sampling_window():
    travel = controller()
    for t in range(0, 2200, 200):
        assert travel.step(observation(t, 5 + t * 0.05)).maneuver in (None, TravelManeuver.DIRECT)
    stalled = [travel.step(observation(t, 105)) for t in range(2200, 6200, 200)]
    assert all(d.maneuver in (None, TravelManeuver.DIRECT) for d in stalled[:-1])
    assert stalled[-1].now_ms == 6000
    assert stalled[-1].maneuver is TravelManeuver.ESCAPE_BACKTRACK


def test_swept_intermediate_passage_advances_but_swept_final_does_not_arrive():
    travel = controller(TravelDestination(105, 5, 5), TravelDestination(205, 5, 5))
    travel.step(observation(0, 95))
    passed = travel.step(observation(200, 115))
    assert passed.waypoint_index == 1
    assert passed.click_destination.x > 115
    final = travel.step(observation(1000, 215))
    assert final.phase is TravelPhase.TRAVELING
    assert travel.step(observation(1200, 205)).phase is TravelPhase.COMPLETE


def test_passing_beside_waypoint_does_not_consume_it():
    travel = controller(TravelDestination(105, 5, 5), TravelDestination(205, 5, 5))
    travel.step(observation(0, 95, 20))
    assert travel.step(observation(200, 115, 20)).waypoint_index == 0


def corridor(blocked=(), costs=()):
    grid = NavigationCostGrid(10, NavigationCell(-2, -2), NavigationCell(20, 20),
                              frozenset(NavigationCell(*c) for c in blocked),
                              tuple((NavigationCell(*c), v) for c, v in costs))
    return lambda start, path: grid.shortcut_clear(
        (start.x, start.y), tuple((point.x, point.y) for point in path))


@pytest.mark.parametrize("gate", [None, corridor(blocked=((3, 1),)),
                                  corridor(costs=(((3, 1), 100),))])
def test_lookahead_cannot_skip_unqualified_or_blocked_or_costly_corner(gate):
    travel = controller(TravelDestination(45, 5, 5), TravelDestination(45, 85, 5),
                        corridor=gate)
    travel.step(observation(0, 5))
    turn = travel.step(observation(400, 25))
    assert turn.waypoint_index == 0
    assert turn.click_destination is None or turn.click_destination == Vector2(45, 5)


def test_clear_cost_preserving_lookahead_hands_off_before_intermediate_radius():
    travel = controller(TravelDestination(45, 5, 5), TravelDestination(45, 85, 5),
                        corridor=corridor())
    travel.step(observation(0, 5))
    turn = travel.step(observation(400, 25))
    assert turn.waypoint_index == 1
    assert turn.click_destination == Vector2(45, 25)
    assert hypot(turn.click_destination.x - 25, turn.click_destination.y - 5) <= 50
    assert turn.phase is TravelPhase.TRAVELING


class MovingClient:
    """Native point-move model: runs to accepted endpoint, then actually stops."""
    def __init__(self):
        self.now = 0.0
        self.x = 5.0
        self.target = self.x
        self.commands = []
        self.premature_stops = []

    def observe(self):
        return NativePlayerPositionObservation(self.x, 5, 0)

    def is_set(self):
        return False

    def sleep(self, seconds):
        self.now += seconds
        self.x = min(self.target, self.x + 50 * seconds)
        if self.x == self.target and self.x < 300:
            self.premature_stops.append(self.now)

    def dispatch(self, decision):
        assert decision.click_destination is not None
        self.target = decision.click_destination.x
        self.commands.append(decision)
        return DispatchResult("native-model", str(decision.decision_id), True, None)

    def stop_movement(self, decision):
        return DispatchResult("native-model", str(decision.decision_id), True, None)


class Vitals:
    def observe(self):
        return vitals()


def test_real_runner_renews_while_moving_and_independently_confirms_final_arrival():
    client = MovingClient()
    result = TravelRunner(
        controller=controller(TravelDestination(305, 5, 5)),
        position_reader=client, player_vitals_reader=Vitals(), dispatcher=client,
        stop_signal=client, clock=lambda: client.now, sleeper=client.sleep,
    ).run()
    assert result.final_phase is TravelPhase.COMPLETE
    assert result.arrival_confirmed is True
    assert client.premature_stops == []
    assert len(client.commands) > 4  # cannot be the old 2s/50-unit stepping
    assert all(b.now_ms - a.now_ms >= 200 for a, b in pairwise(client.commands))
    assert all(d.maneuver is TravelManeuver.DIRECT for d in client.commands)
    assert result.final_position.lt >= 300


def test_partial_handoff_cannot_be_replaced_by_unchecked_far_corner_target():
    gate = corridor(blocked=((3, 3),))
    travel = controller(TravelDestination(45, 5, 5), TravelDestination(45, 85, 5),
                        corridor=gate)
    travel.step(observation(0, 5))
    initial = travel.step(observation(400, 25))
    assert initial.click_destination == Vector2(45, 25)
    # Before reaching that candidate, a far next-leg ray crosses the wall.
    repeated = travel.step(observation(2400, 26, 6))
    assert repeated.click_destination == initial.click_destination
    assert gate(Vector2(26, 6), (repeated.click_destination,))
    beyond_corner = travel.step(observation(2600, 45, 25))
    assert beyond_corner.click_destination == Vector2(45, 75)
    assert gate(Vector2(45, 25), (beyond_corner.click_destination,))


def test_progress_refresh_does_not_exhaust_existing_24_attempt_budget():
    travel = controller(TravelDestination(10005, 5, 5), maximum_clicks=24)
    moves = []
    for t in range(0, 20000, 200):
        decision = travel.step(observation(t, 5 + t * 0.05))
        assert not decision.terminal
        if decision.click_destination is not None:
            moves.append(decision)
    assert len(moves) > 24
    assert sum(not d.progress_refresh for d in moves) == 1
    # Holding position still enters the original timed stall recovery.
    stopped_progress = [travel.step(observation(t, 995)) for t in range(20000, 24400, 200)]
    assert any(d.maneuver is TravelManeuver.ESCAPE_BACKTRACK for d in stopped_progress)


def test_stationary_periodic_attempts_keep_the_original_budget():
    travel = controller(maximum_clicks=2)
    assert not travel.step(observation(0, 5)).progress_refresh
    assert not travel.step(observation(2000, 5)).progress_refresh
    assert travel.step(observation(2200, 5)).terminal_reason == "maximum_clicks"


def test_final_arrival_radius_does_not_discard_partial_handoff_cost_evidence():
    gate = corridor(costs=(((3, 3), 100),))
    travel = controller(TravelDestination(45, 5, 5), TravelDestination(45, 85, 75),
                        corridor=gate)
    travel.step(observation(0, 5))
    initial = travel.step(observation(400, 25))
    assert initial.click_destination == Vector2(45, 25)
    # The final 75-unit arrival radius is not a routing-hint passage tolerance.
    repeated = travel.step(observation(2400, 26, 6))
    assert repeated.phase is TravelPhase.TRAVELING
    assert repeated.click_destination == initial.click_destination
