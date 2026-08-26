import unittest

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCombatEvent,
    NativeCombatEventKind,
    NativeCombatLogEntry,
    NativePlayerVitalsObservation,
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


def _player(
    current_health: float = 100.0,
    maximum_health: float = 100.0,
    current_mana: float = 50.0,
    maximum_mana: float = 50.0,
) -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(
        current_health,
        maximum_health,
        current_mana,
        maximum_mana,
        100.0,
        100.0,
    )


def _observation(
    now_ms: int,
    target: NativeTargetHealthObservation,
    *events: NativeCombatEvent,
    player: NativePlayerVitalsObservation | None = None,
) -> PvEObservation:
    return PvEObservation(
        now_ms=now_ms,
        target=target,
        player=_player() if player is None else player,
        combat_events=events,
    )


class PvEControllerTests(unittest.TestCase):
    def test_opener_configuration_rejects_non_power_and_unbounded_mana_cost(self) -> None:
        with self.assertRaisesRegex(ValueError, "power activation"):
            PvEControllerConfig(opening_intent=PvEIntent.ACQUIRE_NEXT_MOB)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            PvEControllerConfig(
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=float("nan"),
            )
        with self.assertRaisesRegex(ValueError, "requires an opening_intent"):
            PvEControllerConfig(opening_mana_cost=55.0)

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

    def test_low_native_player_health_stops_before_input(self) -> None:
        controller = PvEController(
            PvEControllerConfig(minimum_player_health_fraction=0.5)
        )

        stopped = controller.step(
            _observation(0, _absent(), player=_player(50.0, 100.0))
        )

        self.assertEqual("player_health_safety_threshold", stopped.terminal_reason)
        self.assertIsNone(stopped.intent)

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

    def test_proc_assassin_accepts_auto_target_and_opens_without_redundant_attack(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                opening_followup_delay_ms=100,
                automatic_attack_expected=True,
                stalled_progress_ms=500,
            )
        )
        player = _player(current_mana=100.0, maximum_mana=100.0)

        opener = controller.step(_observation(0, _target("auto-mob"), player=player))
        opening = controller.step(_observation(50, _target("auto-mob", 9), player=player))
        engaged = controller.step(_observation(100, _target("auto-mob", 9), player=player))
        fallback = controller.step(_observation(600, _target("auto-mob", 9), player=player))

        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, opener.intent)
        self.assertEqual(PvEPhase.OPENING, opening.phase)
        self.assertIsNone(opening.intent)
        self.assertEqual(PvEPhase.ENGAGED, engaged.phase)
        self.assertIsNone(engaged.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, fallback.intent)

    def test_uncommanded_auto_target_waits_for_native_player_hit_confirmation(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                automatic_target_requires_combat_event=True,
            )
        )
        player = _player(current_mana=100.0, maximum_mana=100.0)

        waiting = controller.step(_observation(0, _target("auto-mob"), player=player))
        still_waiting = controller.step(
            _observation(100, _target("auto-mob"), player=player)
        )
        confirmed = controller.step(
            _observation(
                200,
                _target("auto-mob", current=9),
                _event(NativeCombatEventKind.PLAYER_HIT_TARGET),
                player=player,
            )
        )

        self.assertIsNone(waiting.intent)
        self.assertIsNone(still_waiting.intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, confirmed.intent)

    def test_stale_uncommanded_selection_cycles_then_accepts_different_mob(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                automatic_target_requires_combat_event=True,
                stale_selection_cycle_delay_ms=1_000,
            )
        )
        player = _player(current_mana=100.0, maximum_mana=100.0)

        waiting = controller.step(_observation(0, _target("stale-mob"), player=player))
        still_waiting = controller.step(
            _observation(999, _target("stale-mob"), player=player)
        )
        cycle = controller.step(_observation(1_000, _target("stale-mob"), player=player))
        opener = controller.step(_observation(1_100, _target("new-mob"), player=player))

        self.assertIsNone(waiting.intent)
        self.assertIsNone(still_waiting.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, opener.intent)

    def test_proc_assassin_skips_opener_when_native_mana_is_too_low(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                automatic_attack_expected=True,
            )
        )

        decision = controller.step(
            _observation(
                0,
                _target("auto-mob"),
                player=_player(current_mana=54.0, maximum_mana=100.0),
            )
        )

        self.assertEqual(PvEPhase.ENGAGED, decision.phase)
        self.assertIsNone(decision.intent)

    def test_proc_assassin_opens_automatic_replacement_after_confirmed_kill(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=2,
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                opening_followup_delay_ms=100,
                automatic_attack_expected=True,
                post_kill_delay_ms=100,
            )
        )
        player = _player(current_mana=100.0, maximum_mana=100.0)
        controller.step(_observation(0, _target("mob-1"), player=player))
        controller.step(_observation(100, _target("mob-1"), player=player))
        post_kill = controller.step(
            _observation(
                200,
                _target("mob-2"),
                _event(NativeCombatEventKind.TARGET_KILLED),
                player=player,
            )
        )

        replacement_opener = controller.step(
            _observation(300, _target("mob-2"), player=player)
        )

        self.assertEqual(PvEPhase.POST_KILL, post_kill.phase)
        self.assertEqual(PvEPhase.OPENING, replacement_opener.phase)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, replacement_opener.intent)

    def test_selection_change_during_opener_stops(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
            )
        )
        player = _player(current_mana=100.0, maximum_mana=100.0)
        controller.step(_observation(0, _target("first"), player=player))

        stopped = controller.step(_observation(100, _target("second"), player=player))

        self.assertEqual(PvEPhase.STOPPED, stopped.phase)
        self.assertEqual("selected_target_changed_during_opener", stopped.terminal_reason)

    def test_required_intents_include_configured_opener_and_stall_fallback(self) -> None:
        controller = PvEController(
            PvEControllerConfig(opening_intent=PvEIntent.CAST_SHADOW_TOUCH)
        )

        self.assertEqual(
            frozenset(
                {
                    PvEIntent.ACQUIRE_NEXT_MOB,
                    PvEIntent.CAST_SHADOW_TOUCH,
                    PvEIntent.ATTACK_SELECTED_TARGET,
                }
            ),
            controller.required_intents,
        )


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


class SequencePlayerVitalsSource:
    def __init__(self, values: tuple[NativePlayerVitalsObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativePlayerVitalsObservation:
        return self.values.pop(0)


class ConstantHealthSource:
    def __init__(self, value: NativeTargetHealthObservation) -> None:
        self.value = value

    def observe(self) -> NativeTargetHealthObservation:
        return self.value


class ConstantCombatLogSource:
    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        return ()


class FlakyPlayerVitalsSource:
    def __init__(self, failures: int) -> None:
        self.failures = failures

    def observe(self) -> NativePlayerVitalsObservation:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("torn player-vitals sample")
        return _player()


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
            player_vitals_reader=SequencePlayerVitalsSource(
                (_player(), _player(), _player(), _player())
            ),
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
            player_vitals_reader=SequencePlayerVitalsSource((_player(),)),
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
            player_vitals_reader=SequencePlayerVitalsSource((_player(),)),
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

    def test_runner_pauses_input_and_recovers_after_transient_observation_failures(self) -> None:
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(
                PvEControllerConfig(
                    maximum_session_ms=500,
                    acquisition_retry_ms=100,
                    acquisition_timeout_ms=400,
                    stale_selection_cycle_delay_ms=100,
                )
            ),
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=FlakyPlayerVitalsSource(2),
            combat_log_reader=ConstantCombatLogSource(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            maximum_consecutive_observation_failures=3,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual("mob_acquisition_timeout", result.terminal_reason)
        self.assertGreaterEqual(len(dispatcher.intents), 1)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, dispatcher.intents[0])

    def test_runner_stops_after_bounded_consecutive_observation_failures(self) -> None:
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=FlakyPlayerVitalsSource(3),
            combat_log_reader=ConstantCombatLogSource(),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            maximum_consecutive_observation_failures=3,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual((), tuple(dispatcher.intents))
        self.assertIn("observation_failure:RuntimeError", result.terminal_reason)
        self.assertIn("torn player-vitals sample", result.terminal_reason)


if __name__ == "__main__":
    unittest.main()
