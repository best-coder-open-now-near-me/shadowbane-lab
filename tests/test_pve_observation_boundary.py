import unittest

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCombatLogEntry,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve import (
    NativePvEObservationSource,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservationCoherenceError,
    PvEPhase,
    PvERunner,
)
from shadowbane_lab.pve.approach import PvEApproachController


def _absent() -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(target_present=False)


def _target(token: str, health: float = 10.0) -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(
        target_present=True,
        current_health=health,
        maximum_health=10.0,
        target_token=token,
    )


def _player() -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(
        current_health=100.0,
        maximum_health=100.0,
        current_mana=50.0,
        maximum_mana=50.0,
        current_stamina=100.0,
        maximum_stamina=100.0,
    )


class ProcessSequenceHealthSource:
    process_id = 4321

    def __init__(self, values: tuple[NativeTargetHealthObservation, ...]) -> None:
        self.values = list(values)
        self.calls = 0

    def observe(self) -> NativeTargetHealthObservation:
        self.calls += 1
        return self.values.pop(0)


class ConstantHealthSource:
    def __init__(self, value: NativeTargetHealthObservation) -> None:
        self.value = value
        self.calls = 0

    def observe(self) -> NativeTargetHealthObservation:
        self.calls += 1
        return self.value


class ConstantVitalsSource:
    def __init__(
        self,
        value: NativePlayerVitalsObservation,
        *,
        process_id: int | None = None,
    ) -> None:
        self.value = value
        if process_id is not None:
            self.process_id = process_id

    def observe(self) -> NativePlayerVitalsObservation:
        return self.value


class ConstantPlayerPositionSource:
    def observe(self) -> NativePlayerPositionObservation:
        return NativePlayerPositionObservation(100.0, 200.0, 10.0)


class ConstantAbsentTargetPositionSource:
    def observe(self) -> NativeTargetPositionObservation:
        return NativeTargetPositionObservation(target_present=False)


class CountingCombatLogSource:
    def __init__(self) -> None:
        self.calls = 0

    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        self.calls += 1
        return ()


class RecordingPvEDispatcher:
    def __init__(self) -> None:
        self.intents: list[PvEIntent] = []

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        self.intents.append(intent)
        return DispatchResult(
            adapter_name="test",
            correlation_id=f"test:{sequence}",
            accepted=True,
        )


class RecordingMovementDispatcher:
    def __init__(self) -> None:
        self.dispatched = 0
        self.stopped = 0

    def dispatch(self, decision) -> DispatchResult:
        self.dispatched += 1
        return DispatchResult(
            adapter_name="movement-test",
            correlation_id=f"movement:{decision.decision_id}",
            accepted=True,
        )

    def stop_movement(self, decision) -> DispatchResult:
        self.stopped += 1
        return DispatchResult(
            adapter_name="movement-test",
            correlation_id=f"movement:{decision.decision_id}:stop",
            accepted=True,
        )


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class ExplodingController(PvEController):
    def __init__(self) -> None:
        super().__init__(PvEControllerConfig())
        self.step_calls = 0

    def step(self, observation):
        self.step_calls += 1
        raise RuntimeError("controller exploded")


class ExplodingApproach(PvEApproachController):
    def step(self, *_args, **_kwargs):
        raise RuntimeError("planner exploded")


class NativePvEObservationSourceTests(unittest.TestCase):
    def test_process_backed_selection_change_rejects_frame_before_consuming_events(self) -> None:
        health = ProcessSequenceHealthSource((_target("first"), _target("second")))
        combat = CountingCombatLogSource()
        source = NativePvEObservationSource(
            health_reader=health,
            player_vitals_reader=ConstantVitalsSource(_player(), process_id=4321),
            combat_log_reader=combat,
        )

        with self.assertRaisesRegex(
            PvEObservationCoherenceError,
            "selected target changed",
        ):
            source.observe(
                now_ms=0,
                target_action_active=False,
                player_action_active=False,
            )

        self.assertTrue(source.selection_boundary_enabled)
        self.assertEqual(2, health.calls)
        self.assertEqual(0, combat.calls)

    def test_process_backed_frame_uses_latest_health_for_stable_selection(self) -> None:
        health = ProcessSequenceHealthSource((_target("mob", 10.0), _target("mob", 7.0)))
        combat = CountingCombatLogSource()
        source = NativePvEObservationSource(
            health_reader=health,
            player_vitals_reader=ConstantVitalsSource(_player(), process_id=4321),
            combat_log_reader=combat,
        )

        observation = source.observe(
            now_ms=100,
            target_action_active=False,
            player_action_active=False,
        )

        self.assertEqual("mob", observation.target.target_token)
        self.assertEqual(7.0, observation.target.current_health)
        self.assertEqual(1, combat.calls)

    def test_tape_source_remains_single_read_and_is_treated_as_atomic(self) -> None:
        health = ConstantHealthSource(_absent())
        source = NativePvEObservationSource(
            health_reader=health,
            player_vitals_reader=ConstantVitalsSource(_player()),
            combat_log_reader=CountingCombatLogSource(),
        )

        observation = source.observe(
            now_ms=0,
            target_action_active=False,
            player_action_active=False,
        )

        self.assertFalse(source.selection_boundary_enabled)
        self.assertFalse(observation.target.target_present)
        self.assertEqual(1, health.calls)

    def test_process_identity_mismatch_is_rejected_before_sampling(self) -> None:
        with self.assertRaisesRegex(ValueError, "different processes"):
            NativePvEObservationSource(
                health_reader=ProcessSequenceHealthSource((_absent(),)),
                player_vitals_reader=ConstantVitalsSource(_player(), process_id=9876),
                combat_log_reader=CountingCombatLogSource(),
            )


class GuardedPvERunnerTests(unittest.TestCase):
    def test_coherence_failures_retry_then_stop_without_input(self) -> None:
        health = ProcessSequenceHealthSource(
            (
                _target("first"),
                _target("second"),
                _target("first"),
                _target("second"),
            )
        )
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=health,
            player_vitals_reader=ConstantVitalsSource(_player(), process_id=4321),
            combat_log_reader=CountingCombatLogSource(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            maximum_consecutive_observation_failures=2,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertIn(
            "observation_coherence_failure:PvEObservationCoherenceError",
            result.terminal_reason,
        )
        self.assertEqual(4, health.calls)
        self.assertEqual([], dispatcher.intents)

    def test_controller_exception_is_not_retried_as_observation_failure(self) -> None:
        controller = ExplodingController()
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=controller,
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=ConstantVitalsSource(_player()),
            combat_log_reader=CountingCombatLogSource(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            maximum_consecutive_observation_failures=3,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(1, controller.step_calls)
        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertIn("decision_failure:RuntimeError:controller exploded", result.terminal_reason)
        self.assertNotIn("observation_failure", result.terminal_reason)
        self.assertEqual([], dispatcher.intents)

    def test_approach_exception_stops_before_semantic_input(self) -> None:
        dispatcher = RecordingPvEDispatcher()
        movement = RecordingMovementDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=ConstantVitalsSource(_player()),
            player_position_reader=ConstantPlayerPositionSource(),
            target_position_reader=ConstantAbsentTargetPositionSource(),
            combat_log_reader=CountingCombatLogSource(),
            dispatcher=dispatcher,
            approach_controller=ExplodingApproach(),
            movement_dispatcher=movement,
            stop_signal=EventEmergencyStop(),
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertIn("approach_failure:RuntimeError:planner exploded", result.terminal_reason)
        self.assertEqual([], dispatcher.intents)
        self.assertEqual(0, movement.dispatched)
        self.assertEqual(0, movement.stopped)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, result.trace[0].decision.intent)
        self.assertIsNone(result.trace[0].input_accepted)


if __name__ == "__main__":
    unittest.main()
