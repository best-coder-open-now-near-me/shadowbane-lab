import unittest

from shadowbane_lab.client_input import (
    EventEmergencyStop,
    MouseButton,
    WindowBounds,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.protocol import DispatchResult, Vector2
from shadowbane_lab.travel import (
    TravelController,
    TravelControllerConfig,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
    TravelRunner,
    parse_go_command,
)


def _position(lt: float, lg: float) -> NativePlayerPositionObservation:
    return NativePlayerPositionObservation(lt, lg, 100, 5)


def _vitals(health: float = 100) -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(health, 100, 50, 50, 100, 100)


def _observation(now_ms: int, lt: float, lg: float, health: float = 100) -> TravelObservation:
    return TravelObservation(now_ms, _position(lt, lg), _vitals(health))


class GoCommandTests(unittest.TestCase):
    def test_parses_space_and_comma_forms(self) -> None:
        spaced = parse_go_command("go 120000 60000")
        comma = parse_go_command("/go 120000, 60000 50")

        self.assertEqual(TravelDestination(120000, 60000, 75), spaced.destinations[0])
        self.assertEqual(TravelDestination(120000, 60000, 50), comma.destinations[0])

    def test_rejects_ambiguous_commands(self) -> None:
        with self.assertRaisesRegex(ValueError, "go LT LG"):
            parse_go_command("go there")


class TravelCalibrationTests(unittest.TestCase):
    def test_bundled_template_resolves_measured_minimap_geometry(self) -> None:
        profile = load_calibration("configs/wonderbane-travel.template.json")
        bounds = WindowBounds(0, 0, 1920, 955)

        center = bounds.resolve(profile.movement.center)

        self.assertFalse(profile.live_input_enabled)
        self.assertEqual(MouseButton.RIGHT, profile.movement.button)
        self.assertEqual((1812, 107), (center.x, center.y))
        self.assertAlmostEqual(82, profile.movement.horizontal_radius * 1919)
        self.assertAlmostEqual(82, profile.movement.vertical_radius * 954)


class TravelControllerTests(unittest.TestCase):
    def test_dispatches_world_delta_with_inverted_minimap_y(self) -> None:
        controller = TravelController(
            parse_go_command("go 1100 2200"),
            TravelControllerConfig(click_interval_ms=1000),
        )

        decision = controller.step(_observation(0, 1000, 2000))

        self.assertEqual(TravelPhase.TRAVELING, decision.phase)
        self.assertEqual(Vector2(100, -200), decision.minimap_direction)
        self.assertEqual(1, decision.click_count)

    def test_completes_inside_arrival_radius_without_input(self) -> None:
        controller = TravelController(parse_go_command("go 1000 2000 50"))

        decision = controller.step(_observation(0, 1030, 2020))

        self.assertEqual(TravelPhase.COMPLETE, decision.phase)
        self.assertEqual("destination_reached", decision.terminal_reason)
        self.assertIsNone(decision.minimap_direction)

    def test_stops_after_bounded_no_progress_checkpoints(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 5000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=3,
                maximum_escape_sequences=0,
            ),
        )

        self.assertIsNotNone(controller.step(_observation(0, 1000, 1000)).minimap_direction)
        self.assertIsNotNone(controller.step(_observation(1000, 1000, 1000)).minimap_direction)
        self.assertIsNotNone(controller.step(_observation(2000, 1000, 1000)).minimap_direction)
        stopped = controller.step(_observation(3000, 1000, 1000))

        self.assertEqual(TravelPhase.STOPPED, stopped.phase)
        self.assertEqual("no_progress", stopped.terminal_reason)
        self.assertEqual(3, stopped.click_count)

    def test_no_progress_runs_bounded_reverse_zig_zag_then_resumes_direct(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 5000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=2,
                maximum_escape_sequences=2,
                escape_clicks_per_sequence=3,
                escape_lateral_ratio=0.75,
            ),
        )

        direct = controller.step(_observation(0, 1000, 1000))
        controller.step(_observation(1000, 1000, 1000))
        escape_one = controller.step(_observation(2000, 1000, 1000))
        escape_two = controller.step(_observation(3000, 1000, 1000))
        escape_three = controller.step(_observation(4000, 1000, 1000))
        reacquired = controller.step(_observation(5000, 1000, 1000))

        self.assertEqual(TravelManeuver.DIRECT, direct.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BACK_LEFT, escape_one.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BACK_RIGHT, escape_two.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BACK_LEFT, escape_three.maneuver)
        self.assertEqual(TravelManeuver.DIRECT, reacquired.maneuver)
        forward = direct.minimap_direction
        assert forward is not None
        for escape in (escape_one, escape_two, escape_three):
            direction = escape.minimap_direction
            assert direction is not None
            self.assertLess(forward.x * direction.x + forward.y * direction.y, 0)

    def test_stops_after_escape_budget_is_exhausted(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 5000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=1,
                maximum_escape_sequences=1,
                escape_clicks_per_sequence=1,
            ),
        )

        controller.step(_observation(0, 1000, 1000))
        escape = controller.step(_observation(1000, 1000, 1000))
        controller.step(_observation(2000, 1000, 1000))
        stopped = controller.step(_observation(3000, 1000, 1000))

        self.assertIn(
            escape.maneuver,
            (TravelManeuver.ESCAPE_BACK_LEFT, TravelManeuver.ESCAPE_BACK_RIGHT),
        )
        self.assertEqual(TravelPhase.STOPPED, stopped.phase)
        self.assertEqual("no_progress_after_escape", stopped.terminal_reason)

    def test_progress_resets_no_progress_counter(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 5000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=2,
            ),
        )

        controller.step(_observation(0, 1000, 1000))
        controller.step(_observation(1000, 1000, 1000))
        moving = controller.step(_observation(2000, 1100, 1100))
        next_stall = controller.step(_observation(3000, 1100, 1100))

        self.assertFalse(moving.terminal)
        self.assertFalse(next_stall.terminal)

    def test_stops_before_clicking_when_health_is_low(self) -> None:
        controller = TravelController(parse_go_command("go 5000 5000"))

        stopped = controller.step(_observation(0, 1000, 1000, health=49))

        self.assertEqual("low_player_health", stopped.terminal_reason)
        self.assertEqual(0, stopped.click_count)

    def test_advances_waypoint_then_completes_final_destination(self) -> None:
        controller = TravelController(
            TravelPlan(
                "two-waypoints",
                (
                    TravelDestination(1000, 1000, 25),
                    TravelDestination(2000, 2000, 25),
                ),
            )
        )

        next_leg = controller.step(_observation(0, 1000, 1000))
        complete = controller.step(_observation(1000, 2000, 2000))

        self.assertEqual(1, next_leg.waypoint_index)
        self.assertIsNotNone(next_leg.minimap_direction)
        self.assertEqual(TravelPhase.COMPLETE, complete.phase)


class SequencePositionReader:
    def __init__(self, positions: list[NativePlayerPositionObservation]) -> None:
        self.positions = positions

    def observe(self) -> NativePlayerPositionObservation:
        return self.positions.pop(0)


class ConstantVitalsReader:
    def observe(self) -> NativePlayerVitalsObservation:
        return _vitals()


class RecordingTravelDispatcher:
    def __init__(self) -> None:
        self.decisions = []

    def dispatch(self, decision):
        self.decisions.append(decision)
        return DispatchResult(
            adapter_name="recording-travel",
            correlation_id=str(decision.decision_id),
            accepted=True,
        )


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, duration: float) -> None:
        self.value += duration


class TravelRunnerTests(unittest.TestCase):
    def test_runner_closes_feedback_loop_until_destination(self) -> None:
        clock = FakeClock()
        dispatcher = RecordingTravelDispatcher()
        controller = TravelController(
            parse_go_command("go 1300 1000 25"),
            TravelControllerConfig(click_interval_ms=200, minimum_progress=25),
        )
        runner = TravelRunner(
            controller=controller,
            position_reader=SequencePositionReader(
                [
                    _position(1000, 1000),
                    _position(1100, 1000),
                    _position(1200, 1000),
                    _position(1300, 1000),
                ]
            ),
            player_vitals_reader=ConstantVitalsReader(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=200,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(TravelPhase.COMPLETE, result.final_phase)
        self.assertEqual("destination_reached", result.terminal_reason)
        self.assertEqual(3, result.clicks)
        self.assertEqual(3, len(dispatcher.decisions))
        self.assertEqual(1300, result.final_position.lt)

    def test_runner_stops_on_rejected_guarded_input(self) -> None:
        class RejectingDispatcher:
            def dispatch(self, decision):
                return DispatchResult(
                    adapter_name="rejecting-travel",
                    correlation_id=str(decision.decision_id),
                    accepted=False,
                    reason="focus changed",
                )

        clock = FakeClock()
        result = TravelRunner(
            controller=TravelController(parse_go_command("go 2000 2000")),
            position_reader=SequencePositionReader([_position(1000, 1000)]),
            player_vitals_reader=ConstantVitalsReader(),
            dispatcher=RejectingDispatcher(),
            stop_signal=EventEmergencyStop(),
            clock=clock,
            sleeper=clock.sleep,
        ).run()

        self.assertEqual(TravelPhase.STOPPED, result.final_phase)
        self.assertEqual("guarded_input_rejected", result.terminal_reason)


if __name__ == "__main__":
    unittest.main()
