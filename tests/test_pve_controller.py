import unittest

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCombatEvent,
    NativeCombatEventKind,
    NativeCombatLogEntry,
    NativeTargetHealthObservation,
)
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve import (
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
    PvEPhase,
    PvERunner,
)


def _absent() -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(target_present=False)


def _target(
    token: str,
    current: float = 10.0,
    maximum: float = 10.0,
) -> NativeTargetHealthObservation:
    return NativeTargetHealthObservation(
        target_present=True,
        current_health=current,
        maximum_health=maximum,
        target_token=token,
    )


def _event(kind: NativeCombatEventKind, sequence: int = 0) -> NativeCombatEvent:
    return NativeCombatEvent(
        sequence=sequence,
        timestamp="5:02:20",
        kind=kind,
        message=kind.value,
        target_name="the Frost Walker",
    )


def _observation(
    now_ms: int,
    target: NativeTargetHealthObservation,
    *events: NativeCombatEvent,
) -> PvEObservation:
    return PvEObservation(now_ms=now_ms, target=target, combat_events=events)


class PvEControllerTests(unittest.TestCase):
    def test_acquires_a_different_mobile_then_attacks_and_confirms_kill(self) -> None:
        controller = PvEController(PvEControllerConfig(maximum_kills=1))

        acquire = controller.step(_observation(0, _target("statue", 100_000, 100_000)))
        unchanged = controller.step(_observation(100, _target("statue", 100_000, 100_000)))
        attack = controller.step(_observation(200, _target("frost-walker")))
        progress = controller.step(_observation(300, _target("frost-walker", current=6)))
        complete = controller.step(
            _observation(
                400,
                _absent(),
                _event(NativeCombatEventKind.TARGET_KILLED),
            )
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, acquire.intent)
        self.assertIsNone(unchanged.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        self.assertEqual(PvEPhase.ENGAGED, progress.phase)
        self.assertEqual(PvEPhase.COMPLETE, complete.phase)
        self.assertEqual("kill_limit_reached", complete.terminal_reason)
        self.assertEqual(1, complete.kills)

    def test_unexpected_selection_change_during_combat_stops(self) -> None:
        controller = PvEController(PvEControllerConfig())
        controller.step(_observation(0, _absent()))
        controller.step(_observation(100, _target("first")))

        stopped = controller.step(_observation(200, _target("second")))

        self.assertEqual(PvEPhase.STOPPED, stopped.phase)
        self.assertEqual("selected_target_changed_during_engagement", stopped.terminal_reason)

    def test_player_death_record_stops_from_any_active_phase(self) -> None:
        controller = PvEController(PvEControllerConfig())
        controller.step(_observation(0, _absent()))

        stopped = controller.step(
            _observation(
                100,
                _absent(),
                _event(NativeCombatEventKind.PLAYER_KILLED),
            )
        )

        self.assertEqual("player_death_observed", stopped.terminal_reason)

    def test_stalled_engagement_retries_only_bounded_number_of_times(self) -> None:
        config = PvEControllerConfig(
            stalled_progress_ms=100,
            engagement_timeout_ms=1_000,
            maximum_reengage_attempts=1,
        )
        controller = PvEController(config)
        controller.step(_observation(0, _absent()))
        controller.step(_observation(10, _target("mob")))

        retry = controller.step(_observation(110, _target("mob")))
        stopped = controller.step(_observation(210, _target("mob")))

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, retry.intent)
        self.assertEqual("engagement_stalled", stopped.terminal_reason)

    def test_two_kill_limit_reacquires_after_post_kill_delay(self) -> None:
        controller = PvEController(
            PvEControllerConfig(maximum_kills=2, post_kill_delay_ms=100)
        )
        controller.step(_observation(0, _absent()))
        controller.step(_observation(10, _target("mob-1")))
        post_kill = controller.step(
            _observation(
                20,
                _absent(),
                _event(NativeCombatEventKind.TARGET_KILLED),
            )
        )
        waiting = controller.step(_observation(100, _absent()))
        acquire = controller.step(_observation(120, _absent()))
        attack = controller.step(_observation(130, _target("mob-2")))

        self.assertEqual(PvEPhase.POST_KILL, post_kill.phase)
        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, acquire.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)


class SequenceHealthSource:
    def __init__(self, values: tuple[NativeTargetHealthObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetHealthObservation:
        return self.values.pop(0)


class SequenceCombatLogSource:
    def __init__(self, values: tuple[tuple[NativeCombatLogEntry, ...], ...]) -> None:
        self.values = list(values)

    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        return self.values.pop(0)


class RecordingPvEDispatcher:
    def __init__(self, *, accepted: bool = True, raises: bool = False) -> None:
        self.accepted = accepted
        self.raises = raises
        self.intents: list[PvEIntent] = []

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        self.intents.append(intent)
        if self.raises:
            raise OSError("input backend failed for test")
        return DispatchResult(
            adapter_name="pve-test",
            correlation_id=f"pve-test:{sequence}",
            accepted=self.accepted,
            reason=None if self.accepted else "rejected for test",
        )


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class PvERunnerTests(unittest.TestCase):
    def test_runner_completes_one_native_observation_driven_kill(self) -> None:
        health = SequenceHealthSource(
            (
                _absent(),
                _target("mob"),
                _target("mob", current=5),
                _absent(),
            )
        )
        combat = SequenceCombatLogSource(
            (
                (),
                (),
                (
                    NativeCombatLogEntry(
                        sequence=0,
                        timestamp="5:02:19",
                        message="You hit the Frost Walker for 5 points of damage!",
                    ),
                ),
                (
                    NativeCombatLogEntry(
                        sequence=1,
                        timestamp="5:02:20",
                        message="[Combat] Info: You have killed the Frost Walker!",
                    ),
                ),
            )
        )
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=health,
            combat_log_reader=combat,
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(1, result.kills)
        self.assertEqual(
            [PvEIntent.ACQUIRE_NEXT_MOB, PvEIntent.ATTACK_SELECTED_TARGET],
            dispatcher.intents,
        )

    def test_runner_stops_immediately_when_guarded_input_is_rejected(self) -> None:
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=SequenceHealthSource((_absent(),)),
            combat_log_reader=SequenceCombatLogSource(((),)),
            dispatcher=RecordingPvEDispatcher(accepted=False),
            stop_signal=EventEmergencyStop(),
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("guarded_input_rejected", result.terminal_reason)
        self.assertFalse(result.trace[0].input_accepted)

    def test_runner_stops_when_input_dispatch_raises(self) -> None:
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=SequenceHealthSource((_absent(),)),
            combat_log_reader=SequenceCombatLogSource(((),)),
            dispatcher=RecordingPvEDispatcher(raises=True),
            stop_signal=EventEmergencyStop(),
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("input_failure:OSError", result.terminal_reason)
        self.assertFalse(result.trace[0].input_accepted)


if __name__ == "__main__":
    unittest.main()
