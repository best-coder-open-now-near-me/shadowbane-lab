import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from shadowbane_lab.client_input import (
    EventEmergencyStop,
    MouseButton,
    WindowBounds,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeRunegateObservation,
    NativeRunegateRegistryObservation,
)
from shadowbane_lab.protocol import DispatchResult, Vector2
from shadowbane_lab.travel import (
    NamedTravelDestinationError,
    TravelController,
    TravelControllerConfig,
    TravelDestination,
    TravelDestinationStateError,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
    TravelRunner,
    build_world_destination_catalog,
    load_world_destination_catalog,
    parse_go_command,
    parse_named_go_command,
    resolve_travel_destination,
)
from shadowbane_lab.world_data import parse_world_definition


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

    def test_bare_go_reuses_previous_destination(self) -> None:
        previous = TravelDestination(120000, 60000, 50)

        repeated = parse_go_command("/go", previous_destination=previous)

        self.assertEqual((previous,), repeated.destinations)

    def test_bare_go_requires_previous_destination(self) -> None:
        with self.assertRaisesRegex(ValueError, "previous destination"):
            parse_go_command("go")

    def test_named_command_preserves_words_for_catalog_resolution(self) -> None:
        self.assertEqual(
            "oblivion gate",
            parse_named_go_command(" /go   oblivion gate "),
        )
        with self.assertRaisesRegex(NamedTravelDestinationError, "go NAME"):
            parse_named_go_command("/go 120000 60000")


class NamedWorldDestinationTests(unittest.TestCase):
    def test_composes_worlddef_centers_and_selects_nearest_oblivion_runegate(self) -> None:
        world = parse_world_definition(
            """
            WORLDNAME= Aerynth
            WORLDNUM= 1
            LENGTH= 512
            WIDTH= 384
            <BEGINZONE> 1
                CENTX= 65536
                CENTZ= -49152
                YROT= 0
                <BEGINZONE> 200
                    CENTX= -12288
                    CENTZ= -12288
                    YROT= 0
                    <BEGINZONE> 11006
                        # ZONE_#NAME= "Runegate"
                        CENTX= -6528
                        CENTZ= 7808
                    <ENDZONE>
                    <BEGINZONE> 11007
                        # ZONE_#NAME= "Runegate 1"
                        CENTX= 16000
                        CENTZ= 4992
                    <ENDZONE>
                <ENDZONE>
            <ENDZONE>
            """
        )
        catalog = build_world_destination_catalog(world)

        resolved = catalog.resolve(
            "oblivion gate",
            origin=_position(47_000, 53_500),
        )

        self.assertEqual("Aerynth", catalog.world_name)
        self.assertEqual(2, resolved.candidate_count)
        self.assertEqual("Runegate", resolved.matched_name)
        self.assertEqual(11006, resolved.template_id)
        self.assertEqual(TravelDestination(46_720, 53_632), resolved.destination)

    def test_catalog_indexes_humanized_zone_load_names_and_fails_closed(self) -> None:
        world = parse_world_definition(
            """
            WORLDNAME= Aerynth
            WORLDNUM= 1
            LENGTH= 512
            WIDTH= 384
            <BEGINZONE> 1
                CENTX= 65536
                CENTZ= -49152
                <BEGINZONE> 3000
                    CENTX= 1000
                    CENTZ= -2000
                    ZONELOADFILE= BlackDrakeSwamp.cfg
                <ENDZONE>
            <ENDZONE>
            """
        )
        catalog = build_world_destination_catalog(world)

        resolved = catalog.resolve(
            "black drake swamp",
            origin=_position(0, 0),
        )

        self.assertEqual(TravelDestination(66_536, 51_152), resolved.destination)
        with self.assertRaisesRegex(NamedTravelDestinationError, "unknown"):
            catalog.resolve("definitely nowhere", origin=_position(0, 0))

    def test_server_confirmed_overlay_adds_emulator_runegate(self) -> None:
        world_text = """
            WORLDNAME= Aerynth
            WORLDNUM= 1
            LENGTH= 512
            WIDTH= 384
            <BEGINZONE> 1
                CENTX= 65536
                CENTZ= -49152
                <BEGINZONE> 11006
                    # ZONE_#NAME= "Runegate"
                    CENTX= -18816
                    CENTZ= -4480
                <ENDZONE>
            <ENDZONE>
        """
        overlay = {
            "schema_version": 1,
            "world_name": "Aerynth",
            "destinations": [
                {
                    "names": ["Runegate Sea Dog's Rest"],
                    "lt": 88980,
                    "lg": 45020,
                    "arrival_radius": 75,
                    "source": "wonderbane_server_confirmed",
                }
            ],
        }
        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "WorldDef.cfg"
            overlay_path = Path(directory) / "destinations.json"
            world_path.write_text(world_text, encoding="utf-8")
            overlay_path.write_text(json.dumps(overlay), encoding="utf-8")

            catalog = load_world_destination_catalog(
                world_path,
                overrides_path=overlay_path,
            )
            resolved = catalog.resolve(
                "runegate",
                origin=_position(88_900, 45_100),
            )

        self.assertEqual(2, resolved.candidate_count)
        self.assertEqual("Runegate Sea Dog's Rest", resolved.matched_name)
        self.assertIsNone(resolved.template_id)
        self.assertEqual("wonderbane_server_confirmed", resolved.source)
        self.assertEqual(TravelDestination(88_980, 45_020), resolved.destination)

    def test_server_registry_replaces_static_runegates_and_deduplicates_override(self) -> None:
        world = parse_world_definition(
            """
            WORLDNAME= Aerynth
            WORLDNUM= 1
            LENGTH= 512
            WIDTH= 384
            <BEGINZONE> 1
                CENTX= 65536
                CENTZ= -49152
                <BEGINZONE> 11006
                    # ZONE_#NAME= "Runegate"
                    CENTX= -18816
                    CENTZ= -4480
                <ENDZONE>
            <ENDZONE>
            """
        )
        static = build_world_destination_catalog(world)
        confirmed = static.entries + (
            static.entries[0].__class__(
                names=("Runegate Sea Dog's Rest", "Sea Dog's Rest Runegate"),
                template_id=None,
                destination=TravelDestination(88_980, 45_020),
                source="wonderbane_server_confirmed",
            ),
        )
        catalog = static.__class__(world, confirmed)
        registry = NativeRunegateRegistryObservation(
            runegates=(
                NativeRunegateObservation(
                    object_type=7,
                    object_uuid=401,
                    zone_name="Sea Dog's Rest",
                    lt=101_000,
                    lg=61_000,
                    altitude=132,
                ),
                NativeRunegateObservation(
                    object_type=7,
                    object_uuid=402,
                    zone_name="Tyranth",
                    lt=46_720,
                    lg=53_632,
                    altitude=144,
                ),
            ),
            registry_token="ab" * 12,
        )

        resolved_catalog = catalog.with_authoritative_runegates(registry)
        sea_dog = resolved_catalog.resolve(
            "runegate",
            origin=_position(88_900, 45_100),
        )
        exact_sea_dog = resolved_catalog.resolve(
            "sea dogs rest runegate",
            origin=_position(0, 0),
        )

        self.assertEqual(2, sea_dog.candidate_count)
        self.assertEqual("Runegate Sea Dog's Rest", sea_dog.matched_name)
        self.assertEqual("wonderbane_server_confirmed", sea_dog.source)
        self.assertEqual(TravelDestination(88_980, 45_020), sea_dog.destination)
        self.assertEqual(1, exact_sea_dog.candidate_count)
        self.assertEqual("wonderbane_server_confirmed", exact_sea_dog.source)
        self.assertEqual(TravelDestination(88_980, 45_020), exact_sea_dog.destination)


class TravelDestinationStateTests(unittest.TestCase):
    def test_explicit_destination_is_remembered_for_bare_go(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "last-destination.json"

            explicit = resolve_travel_destination(
                state_path,
                lt=120000,
                lg=60000,
                radius=50,
            )
            repeated = resolve_travel_destination(
                state_path,
                lt=None,
                lg=None,
                radius=None,
            )

        self.assertEqual(TravelDestination(120000, 60000, 50), explicit)
        self.assertEqual(explicit, repeated)

    def test_bare_go_without_state_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "missing.json"

            with self.assertRaisesRegex(
                TravelDestinationStateError,
                "go LT LG first",
            ):
                resolve_travel_destination(
                    state_path,
                    lt=None,
                    lg=None,
                    radius=None,
                )

    def test_rejects_partial_explicit_coordinates(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(TravelDestinationStateError, "supplied together"):
                resolve_travel_destination(
                    Path(directory) / "last-destination.json",
                    lt=120000,
                    lg=None,
                    radius=None,
                )


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

    def test_no_progress_runs_committed_detour_then_resumes_direct(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 1000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=1,
                maximum_escape_sequences=2,
                escape_backup_lateral_ratio=0.75,
            ),
        )

        direct = controller.step(_observation(0, 1000, 1000))
        back_left = controller.step(_observation(1000, 1000, 1000))
        back_right = controller.step(_observation(2000, 800, 1000))
        sweep_left = controller.step(_observation(3000, 700, 1000))
        bypass_left = controller.step(_observation(4000, 700, 650))
        reacquired = controller.step(_observation(5000, 850, 650))

        self.assertEqual(TravelManeuver.DIRECT, direct.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BACK_LEFT, back_left.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BACK_RIGHT, back_right.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_SWEEP_LEFT, sweep_left.maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BYPASS_LEFT, bypass_left.maneuver)
        self.assertEqual(TravelManeuver.DIRECT, reacquired.maneuver)
        forward = direct.minimap_direction
        assert forward is not None
        for escape in (back_left, back_right):
            direction = escape.minimap_direction
            assert direction is not None
            self.assertLess(forward.x * direction.x + forward.y * direction.y, 0)
        bypass_direction = bypass_left.minimap_direction
        assert bypass_direction is not None
        self.assertGreater(
            forward.x * bypass_direction.x + forward.y * bypass_direction.y,
            0,
        )

    def test_stops_after_escape_budget_is_exhausted(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 5000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=1,
                maximum_escape_sequences=1,
                maximum_escape_phase_no_motion_clicks=1,
                maximum_escape_side_switches=0,
            ),
        )

        controller.step(_observation(0, 1000, 1000))
        back = controller.step(_observation(1000, 1000, 1000))
        sweep = controller.step(_observation(2000, 1000, 1000))
        bypass = controller.step(_observation(3000, 1000, 1000))
        stopped = controller.step(_observation(4000, 1000, 1000))

        self.assertIn(
            back.maneuver,
            (TravelManeuver.ESCAPE_BACK_LEFT, TravelManeuver.ESCAPE_BACK_RIGHT),
        )
        self.assertIn(
            sweep.maneuver,
            (TravelManeuver.ESCAPE_SWEEP_LEFT, TravelManeuver.ESCAPE_SWEEP_RIGHT),
        )
        self.assertIn(
            bypass.maneuver,
            (TravelManeuver.ESCAPE_BYPASS_LEFT, TravelManeuver.ESCAPE_BYPASS_RIGHT),
        )
        self.assertEqual(TravelPhase.STOPPED, stopped.phase)
        self.assertEqual("no_progress_after_escape", stopped.terminal_reason)

    def test_no_motion_switches_sweep_side_then_starts_next_escape(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 1000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=1,
                maximum_escape_sequences=2,
                maximum_escape_phase_no_motion_clicks=1,
                maximum_escape_side_switches=1,
            ),
        )

        decisions = [controller.step(_observation(0, 1000, 1000))]
        decisions.extend(
            controller.step(_observation(now_ms, 1000, 1000))
            for now_ms in range(1000, 6_000, 1000)
        )

        self.assertEqual(TravelManeuver.ESCAPE_BACK_LEFT, decisions[1].maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_SWEEP_LEFT, decisions[2].maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_SWEEP_RIGHT, decisions[3].maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BYPASS_RIGHT, decisions[4].maneuver)
        self.assertEqual(TravelManeuver.ESCAPE_BACK_RIGHT, decisions[5].maneuver)

    def test_manual_progress_reacquires_direct_during_escape(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 1000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=1,
                maximum_escape_phase_no_motion_clicks=1,
                escape_reacquire_progress=100,
            ),
        )

        controller.step(_observation(0, 1000, 1000))
        controller.step(_observation(1000, 1000, 1000))
        sweep = controller.step(_observation(2000, 1000, 1000))
        direct = controller.step(_observation(3000, 1150, 1000))

        self.assertEqual(TravelManeuver.ESCAPE_SWEEP_LEFT, sweep.maneuver)
        self.assertEqual(TravelManeuver.DIRECT, direct.maneuver)

    def test_sustained_direct_progress_resets_escape_budget(self) -> None:
        controller = TravelController(
            parse_go_command("go 5000 1000"),
            TravelControllerConfig(
                click_interval_ms=1000,
                minimum_progress=25,
                maximum_no_progress_clicks=1,
                maximum_escape_sequences=1,
                escape_reacquire_progress=100,
                escape_budget_reset_progress=1000,
            ),
        )

        controller.step(_observation(0, 1000, 1000))
        controller.step(_observation(1000, 1000, 1000))
        controller.step(_observation(2000, 1150, 1000))
        controller.step(_observation(3000, 2200, 1000))
        new_escape = controller.step(_observation(4000, 2200, 1000))

        self.assertEqual(TravelManeuver.ESCAPE_BACK_LEFT, new_escape.maneuver)

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
        self.stop_decisions = []

    def dispatch(self, decision):
        self.decisions.append(decision)
        return DispatchResult(
            adapter_name="recording-travel",
            correlation_id=str(decision.decision_id),
            accepted=True,
        )

    def stop_movement(self, decision):
        self.stop_decisions.append(decision)
        return DispatchResult(
            adapter_name="recording-travel",
            correlation_id=f"{decision.decision_id}:stop",
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
        self.assertEqual(1, len(dispatcher.stop_decisions))
        self.assertTrue(result.stop_input_accepted)
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

            def stop_movement(self, decision):
                raise AssertionError("no stop input follows a rejected movement input")

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

    def test_runner_fails_closed_when_terminal_stop_input_is_rejected(self) -> None:
        class StopRejectingDispatcher(RecordingTravelDispatcher):
            def stop_movement(self, decision):
                self.stop_decisions.append(decision)
                return DispatchResult(
                    adapter_name="recording-travel",
                    correlation_id=f"{decision.decision_id}:stop",
                    accepted=False,
                    reason="focus changed",
                )

        clock = FakeClock()
        dispatcher = StopRejectingDispatcher()
        result = TravelRunner(
            controller=TravelController(
                parse_go_command("go 1100 1000 25"),
                TravelControllerConfig(click_interval_ms=200, minimum_progress=25),
            ),
            position_reader=SequencePositionReader(
                [_position(1000, 1000), _position(1100, 1000)]
            ),
            player_vitals_reader=ConstantVitalsReader(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=200,
            clock=clock,
            sleeper=clock.sleep,
        ).run()

        self.assertEqual(TravelPhase.STOPPED, result.final_phase)
        self.assertEqual("movement_stop_rejected", result.terminal_reason)
        self.assertFalse(result.stop_input_accepted)
        self.assertEqual("focus changed", result.stop_input_reason)


if __name__ == "__main__":
    unittest.main()
