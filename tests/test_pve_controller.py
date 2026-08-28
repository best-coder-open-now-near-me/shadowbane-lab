import unittest

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCombatEvent,
    NativeCombatEventKind,
    NativeCombatLogEntry,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionObservation,
    NativeTargetActionPhase,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetIdentityReadError,
    NativeTargetPositionObservation,
)
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve import (
    CombatLogSource,
    EmptyCombatLogSource,
    PvEApproachConfig,
    PvEApproachController,
    PvECampLease,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEKillConfirmation,
    PvEObservation,
    PvEPhase,
    PvERunner,
)
from shadowbane_lab.travel import SparseNavigationMap, TravelControllerConfig, TravelManeuver


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
    current_stamina: float = 100.0,
    maximum_stamina: float = 100.0,
) -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(
        current_health,
        maximum_health,
        current_mana,
        maximum_mana,
        current_stamina,
        maximum_stamina,
    )


def _player_position(
    lt: float = 100.0,
    lg: float = 200.0,
) -> NativePlayerPositionObservation:
    return NativePlayerPositionObservation(lt, lg, 10.0)


def _target_position(
    token: str | None,
    lt: float = 103.0,
    lg: float = 204.0,
) -> NativeTargetPositionObservation:
    if token is None:
        return NativeTargetPositionObservation(target_present=False)
    return NativeTargetPositionObservation(
        target_present=True,
        lt=lt,
        lg=lg,
        altitude=22.0,
        target_token=token,
    )


def _target_action(
    token: str | None,
    *,
    phase: NativeTargetActionPhase = NativeTargetActionPhase.IDLE,
    sequence: int = 0,
    targeting_player: bool = True,
) -> NativeTargetActionObservation:
    if token is None:
        return NativeTargetActionObservation(target_present=False)
    return NativeTargetActionObservation(
        target_present=True,
        phase=phase,
        target_token=token,
        targeting_player=targeting_player,
        motion_id=21 if phase is NativeTargetActionPhase.IDLE else 106,
        action_pending=phase is NativeTargetActionPhase.QUEUED,
        impact_frame=19 if phase is NativeTargetActionPhase.IMPACT else None,
        action_sequence=sequence,
    )


def _player_action(
    *,
    phase: NativeTargetActionPhase = NativeTargetActionPhase.IDLE,
    sequence: int = 0,
    motion_sequence: int = 0,
    targeting_selected: bool = True,
) -> NativePlayerActionObservation:
    return NativePlayerActionObservation(
        phase=phase,
        targeting_selected=targeting_selected,
        motion_id=21 if phase is NativeTargetActionPhase.IDLE else 106,
        action_pending=phase is NativeTargetActionPhase.QUEUED,
        impact_frame=19 if phase is NativeTargetActionPhase.IMPACT else None,
        action_sequence=sequence,
        motion_sequence=motion_sequence,
    )


def _target_identity(
    token: str | None,
    *,
    merchant: bool = False,
    shopkeeper: bool = False,
    banker: bool = False,
    trainer: bool = False,
    minion: bool = False,
) -> NativeTargetIdentityObservation:
    if token is None:
        return NativeTargetIdentityObservation(target_present=False)
    return NativeTargetIdentityObservation(
        target_present=True,
        arc_character=True,
        merchant=merchant,
        shopkeeper=shopkeeper,
        banker=banker,
        trainer=trainer,
        minion=minion,
        target_token=token,
    )


def _observation(
    now_ms: int,
    target: NativeTargetHealthObservation,
    *events: NativeCombatEvent,
    player: NativePlayerVitalsObservation | None = None,
    target_action: NativeTargetActionObservation | None = None,
    player_action: NativePlayerActionObservation | None = None,
    target_identity: NativeTargetIdentityObservation | None = None,
    player_position: NativePlayerPositionObservation | None = None,
    target_position: NativeTargetPositionObservation | None = None,
) -> PvEObservation:
    return PvEObservation(
        now_ms=now_ms,
        target=target,
        player=_player() if player is None else player,
        combat_events=events,
        player_position=player_position,
        target_position=target_position,
        target_action=target_action,
        player_action=player_action,
        target_identity=target_identity,
    )


class PvEControllerTests(unittest.TestCase):
    def test_continuous_configuration_requires_a_valid_camp_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a camp_radius"):
            PvEControllerConfig(continuous=True)
        with self.assertRaisesRegex(ValueError, "below camp_radius"):
            PvEControllerConfig(
                continuous=True,
                camp_radius=10.0,
                camp_return_radius=10.0,
            )

    def test_continuous_run_captures_starting_camp_and_rejects_outside_target(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                continuous=True,
                camp_radius=50.0,
                maximum_session_ms=1,
            )
        )
        initial = controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position(None),
            )
        )
        outside = controller.step(
            _observation(
                100,
                _target("far-mob"),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position("far-mob", 151.0, 200.0),
            )
        )
        rescan = controller.step(
            _observation(
                5_100,
                _target("far-mob"),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position("far-mob", 151.0, 200.0),
            )
        )
        inside = controller.step(
            _observation(
                5_200,
                _target("camp-mob"),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position("camp-mob", 120.0, 200.0),
            )
        )

        self.assertEqual((100.0, 200.0), (initial.camp.anchor_lt, initial.camp.anchor_lg))
        self.assertEqual(50.0, initial.camp.radius)
        self.assertFalse(outside.target_inside_camp)
        self.assertIsNone(outside.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, rescan.intent)
        self.assertTrue(inside.target_inside_camp)
        self.assertEqual(PvEPhase.ENGAGED, inside.phase)

    def test_continuous_empty_camp_returns_to_anchor_then_rescans(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                continuous=True,
                camp_radius=50.0,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=100,
                stale_selection_cycle_delay_ms=100,
                target_sample_interval_ms=100,
                camp_idle_ms=500,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position(None),
            )
        )
        returning = controller.step(
            _observation(
                100,
                _absent(),
                player_position=_player_position(140.0, 200.0),
                target_position=_target_position(None),
            )
        )
        arrived = controller.step(
            _observation(
                200,
                _absent(),
                player_position=_player_position(105.0, 200.0),
                target_position=_target_position(None),
            )
        )
        rescan = controller.step(
            _observation(
                600,
                _absent(),
                player_position=_player_position(105.0, 200.0),
                target_position=_target_position(None),
            )
        )

        self.assertEqual(PvEPhase.CAMP_IDLE, returning.phase)
        self.assertTrue(returning.return_to_camp)
        self.assertFalse(arrived.return_to_camp)
        self.assertEqual(PvEPhase.SEEKING, rescan.phase)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, rescan.intent)

    def test_continuous_kill_limit_is_telemetry_not_a_terminal_bound(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                continuous=True,
                camp_radius=50.0,
                maximum_kills=1,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        controller.step(
            _observation(
                100,
                _target("mob"),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )
        killed = controller.step(
            _observation(
                200,
                _target("mob", current=0.0),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )

        self.assertEqual(1, killed.kills)
        self.assertEqual(PvEPhase.POST_KILL, killed.phase)
        self.assertFalse(killed.terminal)

    def test_continuous_stalled_target_exclusion_expires_after_camp_idle(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                continuous=True,
                camp_radius=50.0,
                camp_idle_ms=500,
                failed_target_cooldown_ms=500,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        controller.step(
            _observation(
                100,
                _target("mob"),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )
        abandoned = controller.step(
            _observation(
                2_600,
                _target("mob"),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )
        idle = controller.step(
            _observation(
                2_700,
                _target("mob"),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )
        controller.step(
            _observation(
                3_200,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        retried = controller.step(
            _observation(
                3_300,
                _target("mob"),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )

        self.assertEqual(PvEPhase.SEEKING, abandoned.phase)
        self.assertEqual(PvEPhase.CAMP_IDLE, idle.phase)
        self.assertEqual(PvEPhase.ENGAGED, retried.phase)
        self.assertFalse(retried.terminal)

    def test_spatial_observation_derives_coherent_target_ranges(self) -> None:
        observation = PvEObservation(
            now_ms=0,
            target=_target("mob"),
            player=_player(),
            player_position=_player_position(),
            target_position=_target_position("mob"),
        )

        self.assertEqual(5.0, observation.target_planar_distance)
        self.assertEqual(12.0, observation.target_altitude_delta)
        self.assertEqual(13.0, observation.target_spatial_distance)

        with self.assertRaisesRegex(ValueError, "different targets"):
            PvEObservation(
                now_ms=0,
                target=_target("mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("other-mob"),
            )

    def test_crossing_melee_radius_reissues_attack_after_approach(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                melee_approach_radius=20.0,
            )
        )
        controller.step(
            PvEObservation(
                now_ms=0,
                target=_absent(),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        engaged = controller.step(
            PvEObservation(
                now_ms=100,
                target=_target("mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("mob", 200.0, 200.0),
            )
        )
        arrived = controller.step(
            PvEObservation(
                now_ms=200,
                target=_target("mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("mob", 110.0, 200.0),
            )
        )

        self.assertIsNone(engaged.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, arrived.intent)

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

    def test_interrupt_configuration_requires_a_power_and_positive_target_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "power activation"):
            PvEControllerConfig(
                interrupt_intent=PvEIntent.ATTACK_SELECTED_TARGET,
                maximum_interrupts_per_target=1,
            )
        with self.assertRaisesRegex(ValueError, "positive per-target limit"):
            PvEControllerConfig(interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH)
        with self.assertRaisesRegex(ValueError, "require an interrupt_intent"):
            PvEControllerConfig(interrupt_cooldown_ms=2_000)

    def test_recovery_configuration_is_bounded_by_safety_and_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "below the player safety threshold"):
            PvEControllerConfig(
                minimum_player_health_fraction=0.5,
                minimum_recovery_health_fraction=0.4,
            )
        with self.assertRaisesRegex(ValueError, "post-kill delay"):
            PvEControllerConfig(post_kill_delay_ms=1_000, recovery_timeout_ms=999)

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
        self.assertEqual(
            PvEKillConfirmation.NATIVE_COMBAT_EVENT,
            complete.kill_confirmation,
        )

    def test_exact_native_zero_health_confirms_kill_without_combat_text(self) -> None:
        controller = PvEController(PvEControllerConfig(maximum_kills=1))
        controller.step(_observation(0, _absent()))
        controller.step(_observation(100, _target("mob")))

        complete = controller.step(_observation(200, _target("mob", current=0)))

        self.assertEqual(PvEPhase.COMPLETE, complete.phase)
        self.assertEqual("kill_limit_reached", complete.terminal_reason)
        self.assertEqual(1, complete.kills)
        self.assertEqual(
            PvEKillConfirmation.NATIVE_HEALTH_ZERO,
            complete.kill_confirmation,
        )

    def test_dead_acquisition_candidate_is_never_attacked(self) -> None:
        controller = PvEController(
            PvEControllerConfig(acquisition_retry_ms=100, acquisition_timeout_ms=1_000)
        )
        controller.step(_observation(0, _absent()))

        waiting = controller.step(_observation(50, _target("corpse", current=0)))
        cycle = controller.step(_observation(100, _target("corpse", current=0)))

        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)

    def test_protected_trainer_is_cycled_and_never_attacked(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                target_sample_interval_ms=100,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
            )
        )
        initial = controller.step(
            _observation(0, _absent(), target_identity=_target_identity(None))
        )
        cycle = controller.step(
            _observation(
                100,
                _target("trainer"),
                target_identity=_target_identity("trainer", trainer=True),
            )
        )
        waiting = controller.step(
            _observation(
                150,
                _target("trainer"),
                target_identity=_target_identity("trainer", trainer=True),
            )
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, initial.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)
        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEPhase.SEEKING, waiting.phase)

    def test_required_missing_identity_never_engages(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                target_sample_interval_ms=100,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
            )
        )
        controller.step(_observation(0, _absent()))

        decision = controller.step(_observation(100, _target("unknown")))

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, decision.intent)
        self.assertEqual(PvEPhase.SEEKING, decision.phase)

    def test_nearest_valid_target_is_selected_after_protected_candidate(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                nearest_target_sample_count=2,
                target_sample_interval_ms=100,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
            )
        )

        def spatial(
            now_ms: int,
            token: str | None,
            *,
            trainer: bool = False,
            lt: float = 103.0,
        ) -> PvEObservation:
            return PvEObservation(
                now_ms=now_ms,
                target=_absent() if token is None else _target(token),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position(token, lt, 200.0),
                target_identity=_target_identity(token, trainer=trainer),
            )

        controller.step(spatial(0, None))
        protected = controller.step(spatial(100, "trainer", trainer=True))
        selected = controller.step(spatial(200, "mob", lt=108.0))

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, protected.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, selected.intent)
        self.assertEqual(PvEPhase.ENGAGED, selected.phase)

    def test_nearest_target_sampling_cycles_back_from_far_candidate(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                nearest_target_sample_count=2,
                target_sample_interval_ms=100,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
            )
        )

        def spatial(
            now_ms: int,
            target: NativeTargetHealthObservation,
            position: NativeTargetPositionObservation,
        ) -> PvEObservation:
            return PvEObservation(
                now_ms=now_ms,
                target=target,
                player=_player(),
                player_position=_player_position(),
                target_position=position,
            )

        initial = controller.step(spatial(0, _absent(), _target_position(None)))
        close_sample = controller.step(
            spatial(100, _target("close"), _target_position("close", 105.0, 200.0))
        )
        far_sample = controller.step(
            spatial(200, _target("far"), _target_position("far", 200.0, 200.0))
        )
        selected = controller.step(
            spatial(300, _target("close"), _target_position("close", 105.0, 200.0))
        )

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, initial.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, close_sample.intent)
        self.assertEqual(PvEIntent.ACQUIRE_PREVIOUS_MOB, far_sample.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, selected.intent)
        self.assertEqual(PvEPhase.ENGAGED, selected.phase)

    def test_nearest_target_sampling_accepts_only_candidate_after_one_cycle(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                nearest_target_sample_count=6,
                target_sample_interval_ms=100,
                acquisition_retry_ms=1_000,
                acquisition_timeout_ms=2_000,
            )
        )

        def mob_observation(now_ms: int) -> PvEObservation:
            return PvEObservation(
                now_ms=now_ms,
                target=_target("only-mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("only-mob"),
            )

        controller.step(
            PvEObservation(
                now_ms=0,
                target=_absent(),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        cycle = controller.step(mob_observation(100))
        selected = controller.step(mob_observation(200))

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, selected.intent)
        self.assertEqual(PvEPhase.ENGAGED, selected.phase)

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

    def test_stalled_engagement_cycles_once_and_requires_a_different_target(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                stalled_progress_ms=100,
                engagement_timeout_ms=1_000,
                maximum_reengage_attempts=0,
                maximum_stalled_retargets=1,
                accept_automatic_targets=True,
                automatic_target_requires_combat_event=True,
            )
        )
        controller.step(_observation(0, _absent()))
        controller.step(_observation(10, _target("blocked-mob")))

        cycle = controller.step(_observation(110, _target("blocked-mob")))
        stale_hit = controller.step(
            _observation(
                120,
                _target("blocked-mob"),
                _event(NativeCombatEventKind.PLAYER_HIT_TARGET),
            )
        )
        replacement = controller.step(_observation(130, _target("reachable-mob")))
        stopped = controller.step(_observation(230, _target("reachable-mob")))

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)
        self.assertEqual(PvEPhase.SEEKING, stale_hit.phase)
        self.assertIsNone(stale_hit.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, replacement.intent)
        self.assertEqual("engagement_stalled", stopped.terminal_reason)

    def test_stalled_targets_remain_excluded_during_bounded_retargeting(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                stalled_progress_ms=100,
                engagement_timeout_ms=1_000,
                maximum_reengage_attempts=0,
                maximum_stalled_retargets=2,
            )
        )
        controller.step(_observation(0, _absent()))
        controller.step(_observation(10, _target("blocked-a")))

        first_cycle = controller.step(_observation(110, _target("blocked-a")))
        second_attack = controller.step(_observation(120, _target("blocked-b")))
        second_cycle = controller.step(_observation(220, _target("blocked-b")))
        rejected_old_target = controller.step(_observation(230, _target("blocked-a")))
        reachable_attack = controller.step(_observation(240, _target("reachable")))

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, first_cycle.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, second_attack.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, second_cycle.intent)
        self.assertEqual(PvEPhase.SEEKING, rejected_old_target.phase)
        self.assertIsNone(rejected_old_target.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, reachable_attack.intent)
        self.assertEqual(PvEPhase.ENGAGED, reachable_attack.phase)

    def test_missing_attack_animation_fast_cycles_a_quiet_melee_target(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                maximum_stalled_retargets=1,
                quiet_melee_timeout_ms=2_500,
                missing_attack_animation_timeout_ms=1_500,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        attack = controller.step(
            _observation(
                100,
                _target("quiet-crab"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("quiet-crab", 106.0, 200.0),
            )
        )
        waiting = controller.step(
            _observation(
                1_599,
                _target("quiet-crab"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("quiet-crab", 106.0, 200.0),
            )
        )
        cycle = controller.step(
            _observation(
                1_600,
                _target("quiet-crab"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("quiet-crab", 106.0, 200.0),
            )
        )

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)
        self.assertEqual(PvEPhase.SEEKING, cycle.phase)

    def test_observed_attack_animation_uses_full_quiet_melee_timeout(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                maximum_stalled_retargets=1,
                quiet_melee_timeout_ms=2_500,
                missing_attack_animation_timeout_ms=1_500,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        controller.step(
            _observation(
                100,
                _target("animated-crab"),
                player_action=_player_action(sequence=8),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )
        controller.step(
            _observation(
                200,
                _target("animated-crab"),
                player_action=_player_action(
                    phase=NativeTargetActionPhase.IMPACT,
                    sequence=8,
                    motion_sequence=1,
                ),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )
        waiting = controller.step(
            _observation(
                1_600,
                _target("animated-crab"),
                player_action=_player_action(sequence=8, motion_sequence=1),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )
        cycle = controller.step(
            _observation(
                2_600,
                _target("animated-crab"),
                player_action=_player_action(sequence=8, motion_sequence=1),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )

        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, cycle.intent)

    def test_incoming_hits_without_outgoing_damage_request_reposition(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                incoming_reposition_grace_ms=1_500,
                incoming_reposition_window_ms=3_000,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        controller.step(
            _observation(
                100,
                _target("bugged-mob"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("bugged-mob", 106.0, 200.0),
            )
        )
        controller.step(
            _observation(
                1_000,
                _target("bugged-mob"),
                player=_player(current_health=90.0),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("bugged-mob", 106.0, 200.0),
            )
        )
        reposition = controller.step(
            _observation(
                1_600,
                _target("bugged-mob"),
                player=_player(current_health=90.0),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("bugged-mob", 106.0, 200.0),
            )
        )

        self.assertTrue(reposition.reposition_requested)
        self.assertIsNone(reposition.intent)

    def test_outgoing_damage_suppresses_reposition_for_same_incoming_hit(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                incoming_reposition_grace_ms=1_500,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        controller.step(
            _observation(
                100,
                _target("trading-mob"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("trading-mob", 106.0, 200.0),
            )
        )
        trading = controller.step(
            _observation(
                1_600,
                _target("trading-mob", current=9.0),
                player=_player(current_health=90.0),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("trading-mob", 106.0, 200.0),
            )
        )

        self.assertFalse(trading.reposition_requested)

    def test_lingering_player_animation_does_not_block_reposition(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                incoming_reposition_grace_ms=1_500,
            )
        )
        controller.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        controller.step(
            _observation(
                100,
                _target("busy-player"),
                player_action=_player_action(sequence=3),
                player_position=_player_position(),
                target_position=_target_position("busy-player", 106.0, 200.0),
            )
        )
        busy = controller.step(
            _observation(
                1_600,
                _target("busy-player"),
                player=_player(current_health=90.0),
                player_action=_player_action(
                    phase=NativeTargetActionPhase.WINDUP,
                    sequence=4,
                ),
                player_position=_player_position(),
                target_position=_target_position("busy-player", 106.0, 200.0),
            )
        )

        self.assertTrue(busy.reposition_requested)

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

    def test_post_kill_waits_for_all_recovery_floors_before_reacquiring(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=2,
                post_kill_delay_ms=100,
                recovery_timeout_ms=1_000,
                minimum_recovery_health_fraction=0.75,
                minimum_recovery_mana_fraction=0.5,
                minimum_recovery_stamina_fraction=0.5,
            )
        )
        controller.step(_observation(0, _absent()))
        controller.step(_observation(10, _target("mob")))
        killed = controller.step(_observation(20, _target("mob", current=0)))

        waiting = controller.step(
            _observation(
                120,
                _absent(),
                player=_player(
                    current_health=70,
                    current_mana=20,
                    current_stamina=40,
                ),
            )
        )
        acquire = controller.step(
            _observation(
                220,
                _absent(),
                player=_player(
                    current_health=80,
                    current_mana=30,
                    current_stamina=60,
                ),
            )
        )

        self.assertEqual(PvEPhase.POST_KILL, killed.phase)
        self.assertEqual(PvEKillConfirmation.NATIVE_HEALTH_ZERO, killed.kill_confirmation)
        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, acquire.intent)

    def test_post_kill_recovery_timeout_stops_instead_of_farming_depleted(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=2,
                post_kill_delay_ms=100,
                recovery_timeout_ms=500,
                minimum_recovery_mana_fraction=0.5,
            )
        )
        controller.step(_observation(0, _absent()))
        controller.step(_observation(10, _target("mob")))
        controller.step(_observation(20, _target("mob", current=0)))

        stopped = controller.step(
            _observation(
                520,
                _absent(),
                player=_player(current_mana=20),
            )
        )

        self.assertEqual(PvEPhase.STOPPED, stopped.phase)
        self.assertEqual("post_kill_recovery_timeout", stopped.terminal_reason)

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

    def test_proc_assassin_interrupts_one_native_attack_once_per_target(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH,
                interrupt_mana_cost=55.0,
                interrupt_cooldown_ms=2_000,
                maximum_interrupts_per_target=1,
                automatic_attack_expected=True,
            )
        )
        player = _player(current_mana=100.0, maximum_mana=100.0)
        controller.step(_observation(0, _target("mob"), player=player))

        interrupt = controller.step(
            _observation(
                100,
                _target("mob"),
                player=player,
                target_action=_target_action(
                    "mob",
                    phase=NativeTargetActionPhase.QUEUED,
                    sequence=1,
                ),
            )
        )
        same_attack = controller.step(
            _observation(
                200,
                _target("mob"),
                player=player,
                target_action=_target_action(
                    "mob",
                    phase=NativeTargetActionPhase.WINDUP,
                    sequence=1,
                ),
            )
        )
        next_attack = controller.step(
            _observation(
                3_000,
                _target("mob"),
                player=player,
                target_action=_target_action(
                    "mob",
                    phase=NativeTargetActionPhase.QUEUED,
                    sequence=2,
                ),
            )
        )

        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, interrupt.intent)
        self.assertIsNone(same_attack.intent)
        self.assertIsNone(next_attack.intent)

    def test_interrupt_waits_for_mana_without_consuming_the_attack_window(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH,
                interrupt_mana_cost=55.0,
                maximum_interrupts_per_target=1,
                automatic_attack_expected=True,
            )
        )
        low_mana = _player(current_mana=54.0, maximum_mana=100.0)
        enough_mana = _player(current_mana=55.0, maximum_mana=100.0)
        controller.step(_observation(0, _target("mob"), player=low_mana))
        action = _target_action(
            "mob",
            phase=NativeTargetActionPhase.QUEUED,
            sequence=1,
        )

        waiting = controller.step(
            _observation(100, _target("mob"), player=low_mana, target_action=action)
        )
        interrupt = controller.step(
            _observation(200, _target("mob"), player=enough_mana, target_action=action)
        )

        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, interrupt.intent)

    def test_interrupt_ignores_attack_aimed_at_another_actor(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH,
                maximum_interrupts_per_target=1,
                automatic_attack_expected=True,
            )
        )
        controller.step(_observation(0, _target("mob")))

        decision = controller.step(
            _observation(
                100,
                _target("mob"),
                target_action=_target_action(
                    "mob",
                    phase=NativeTargetActionPhase.QUEUED,
                    sequence=1,
                    targeting_player=False,
                ),
            )
        )

        self.assertIsNone(decision.intent)

    def test_interrupt_cooldown_does_not_consume_a_still_open_action_window(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH,
                interrupt_cooldown_ms=2_000,
                maximum_interrupts_per_target=2,
                automatic_attack_expected=True,
            )
        )
        controller.step(_observation(0, _target("mob")))
        first = controller.step(
            _observation(
                100,
                _target("mob"),
                target_action=_target_action(
                    "mob",
                    phase=NativeTargetActionPhase.QUEUED,
                    sequence=1,
                ),
            )
        )
        second_action = _target_action(
            "mob",
            phase=NativeTargetActionPhase.QUEUED,
            sequence=2,
        )

        cooling_down = controller.step(
            _observation(1_000, _target("mob"), target_action=second_action)
        )
        ready = controller.step(
            _observation(2_100, _target("mob"), target_action=second_action)
        )

        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, first.intent)
        self.assertIsNone(cooling_down.intent)
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, ready.intent)

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


class PvEApproachControllerTests(unittest.TestCase):
    def test_camp_return_uses_anchor_as_an_immediate_astar_destination(self) -> None:
        approach = PvEApproachController()
        camp = PvECampLease(100.0, 200.0, radius=50.0, return_radius=12.0)

        moving = approach.step(
            _observation(
                0,
                _absent(),
                player_position=_player_position(140.0, 200.0),
                target_position=_target_position(None),
            ),
            phase=PvEPhase.CAMP_IDLE,
            camp=camp,
            return_to_camp=True,
        )
        arrived = approach.step(
            _observation(
                100,
                _absent(),
                player_position=_player_position(105.0, 200.0),
                target_position=_target_position(None),
            ),
            phase=PvEPhase.CAMP_IDLE,
            camp=camp,
            return_to_camp=True,
        )

        self.assertEqual("moving", moving.status.value)
        self.assertEqual(40.0, moving.decision.distance_remaining)
        self.assertLess(moving.decision.minimap_direction.x, 0.0)
        self.assertEqual("arrived", arrived.status.value)
        self.assertTrue(arrived.decision.terminal)

    def test_reposition_request_tightens_range_and_uses_position_feedback(self) -> None:
        approach = PvEApproachController(
            PvEApproachConfig(
                arrival_radius=20.0,
                reposition_arrival_radius=3.0,
            )
        )

        def observe(
            now_ms: int,
            *,
            player_lt: float,
            reposition_requested: bool = False,
        ):
            return approach.step(
                PvEObservation(
                    now_ms=now_ms,
                    target=_target("bugged-mob"),
                    player=_player(),
                    player_position=_player_position(player_lt, 200.0),
                    target_position=_target_position("bugged-mob", 106.0, 200.0),
                ),
                phase=PvEPhase.ENGAGED,
                reposition_requested=reposition_requested,
            )

        self.assertEqual("arrived", observe(0, player_lt=100.0).status.value)

        moving = observe(100, player_lt=100.0, reposition_requested=True)
        arrived = observe(200, player_lt=104.0)

        self.assertEqual("moving", moving.status.value)
        self.assertEqual(TravelManeuver.DIRECT, moving.decision.maneuver)
        self.assertEqual("arrived", arrived.status.value)
        self.assertTrue(arrived.decision.terminal)

    def test_stalled_native_chase_replans_with_astar_before_blind_escape(self) -> None:
        navigation = SparseNavigationMap()
        approach = PvEApproachController(
            PvEApproachConfig(
                native_progress_grace_ms=100,
                travel=TravelControllerConfig(
                    maximum_session_ms=5_000,
                    click_interval_ms=100,
                    maximum_clicks=20,
                    minimum_progress=5.0,
                    maximum_no_progress_clicks=2,
                ),
            ),
            navigation_map=navigation,
        )

        def observe(now_ms: int):
            return approach.step(
                PvEObservation(
                    now_ms=now_ms,
                    target=_target("turtle"),
                    player=_player(),
                    player_position=_player_position(),
                    target_position=_target_position("turtle", 200.0, 200.0),
                ),
                phase=PvEPhase.ENGAGED,
            )

        self.assertEqual("idle", observe(0).status.value)
        self.assertEqual(TravelManeuver.DIRECT, observe(100).decision.maneuver)
        self.assertEqual(TravelManeuver.DIRECT, observe(200).decision.maneuver)

        replanned = observe(300)

        self.assertEqual("moving", replanned.status.value)
        self.assertEqual(TravelManeuver.DIRECT, replanned.decision.maneuver)
        self.assertGreater(len(navigation.blocked), 0)


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


class SequencePlayerPositionSource:
    def __init__(self, values: tuple[NativePlayerPositionObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativePlayerPositionObservation:
        return self.values.pop(0)


class SequenceTargetPositionSource:
    def __init__(self, values: tuple[NativeTargetPositionObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetPositionObservation:
        return self.values.pop(0)


class SequenceTargetActionSource:
    def __init__(self, values: tuple[NativeTargetActionObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetActionObservation:
        return self.values.pop(0)


class SequencePlayerActionSource:
    def __init__(self, values: tuple[NativePlayerActionObservation, ...]) -> None:
        self.values = list(values)

    def observe_player(self) -> NativePlayerActionObservation:
        return self.values.pop(0)


class SequenceTargetIdentitySource:
    def __init__(self, values: tuple[NativeTargetIdentityObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetIdentityObservation:
        return self.values.pop(0)


class FailingSequenceTargetIdentitySource:
    def __init__(
        self,
        values: tuple[NativeTargetIdentityObservation | NativeTargetIdentityReadError, ...],
    ) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetIdentityObservation:
        value = self.values.pop(0)
        if isinstance(value, NativeTargetIdentityReadError):
            raise value
        return value


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


class StopRacingPvEDispatcher:
    def __init__(self, stop: EventEmergencyStop) -> None:
        self.stop = stop

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        self.stop.trip()
        return DispatchResult(
            adapter_name="pve-test",
            correlation_id=f"pve-test:{sequence}",
            accepted=False,
            reason="emergency stop is set",
        )


class RecordingMovementDispatcher:
    def __init__(self) -> None:
        self.decisions = []
        self.stop_decisions = []

    def dispatch(self, decision) -> DispatchResult:
        self.decisions.append(decision)
        return DispatchResult(
            adapter_name="movement-test",
            correlation_id=f"movement-test:{decision.decision_id}",
            accepted=True,
        )

    def stop_movement(self, decision) -> DispatchResult:
        self.stop_decisions.append(decision)
        return DispatchResult(
            adapter_name="movement-test",
            correlation_id=f"movement-test:{decision.decision_id}:stop",
            accepted=True,
        )


class AdvancingClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class PvERunnerTests(unittest.TestCase):
    def test_stop_racing_with_dispatch_is_a_clean_emergency_stop(self) -> None:
        clock = AdvancingClock()
        stop = EventEmergencyStop()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=SequenceHealthSource((_absent(),)),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),)),
            combat_log_reader=SequenceCombatLogSource(((),)),
            dispatcher=StopRacingPvEDispatcher(stop),
            stop_signal=stop,
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("emergency_stop", result.terminal_reason)
        self.assertFalse(result.trace[0].input_accepted)

    def test_runner_journals_every_step_while_retaining_only_a_bounded_tail(self) -> None:
        clock = AdvancingClock()
        journaled = []
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource(
                (_absent(), _target("mob"), _target("mob", current=0.0))
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
            combat_log_reader=SequenceCombatLogSource(((),) * 3),
            dispatcher=RecordingPvEDispatcher(),
            stop_signal=EventEmergencyStop(),
            maximum_retained_trace_steps=2,
            trace_sink=journaled.append,
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(3, result.total_steps)
        self.assertTrue(result.trace_truncated)
        self.assertEqual([1, 2], [step.decision.decision_id for step in result.trace])
        self.assertEqual([0, 1, 2], [step.decision.decision_id for step in journaled])

    def test_state_combat_source_never_invents_text_events(self) -> None:
        source = EmptyCombatLogSource()

        self.assertEqual((), source.read_new_entries())
        self.assertIsInstance(source, CombatLogSource)

    def test_runner_samples_and_traces_player_animation_before_attack(self) -> None:
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource(
                (_absent(), _target("mob"), _target("mob", current=0))
            ),
            player_action_reader=SequencePlayerActionSource(
                (
                    _player_action(sequence=4),
                    _player_action(
                        phase=NativeTargetActionPhase.WINDUP,
                        sequence=5,
                    ),
                )
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
            combat_log_reader=SequenceCombatLogSource(((),) * 3),
            dispatcher=RecordingPvEDispatcher(),
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        acquired_action = result.trace[1].as_dict()["player"]["action"]
        combat_action = result.trace[2].as_dict()["player"]["action"]
        self.assertEqual(4, acquired_action["action_sequence"])
        self.assertEqual("windup", combat_action["phase"])
        self.assertTrue(combat_action["action_active"])

    def test_runner_cycles_protected_identity_and_traces_valid_target(self) -> None:
        clock = AdvancingClock()
        dispatcher = RecordingPvEDispatcher()
        runner = PvERunner(
            controller=PvEController(
                PvEControllerConfig(
                    maximum_kills=1,
                    require_target_identity=True,
                    target_sample_interval_ms=100,
                    acquisition_retry_ms=100,
                )
            ),
            health_reader=SequenceHealthSource(
                (
                    _absent(),
                    _target("trainer"),
                    _target("mob"),
                    _target("mob", current=0),
                )
            ),
            target_identity_reader=SequenceTargetIdentitySource(
                (
                    _target_identity(None),
                    _target_identity("trainer", trainer=True),
                    _target_identity("mob"),
                    _target_identity("mob"),
                )
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 4),
            combat_log_reader=SequenceCombatLogSource(((),) * 4),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(
            [
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ATTACK_SELECTED_TARGET,
            ],
            dispatcher.intents,
        )
        trainer_identity = result.trace[1].as_dict()["target"]["identity"]
        self.assertEqual(["trainer"], trainer_identity["protected_roles"])
        self.assertFalse(trainer_identity["attack_eligible"])

    def test_runner_skips_unclassifiable_target_and_continues_bounded_scan(self) -> None:
        clock = AdvancingClock()
        dispatcher = RecordingPvEDispatcher()
        runner = PvERunner(
            controller=PvEController(
                PvEControllerConfig(
                    maximum_kills=1,
                    require_target_identity=True,
                    target_sample_interval_ms=100,
                    acquisition_retry_ms=100,
                )
            ),
            health_reader=SequenceHealthSource(
                (
                    _absent(),
                    _target("unreadable"),
                    _target("mob"),
                    _target("mob", current=0),
                )
            ),
            target_identity_reader=FailingSequenceTargetIdentitySource(
                (
                    _target_identity(None),
                    NativeTargetIdentityReadError("unmapped sparse-data bucket table"),
                    _target_identity("mob"),
                    _target_identity("mob"),
                )
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 4),
            combat_log_reader=SequenceCombatLogSource(((),) * 4),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(
            [
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ATTACK_SELECTED_TARGET,
            ],
            dispatcher.intents,
        )
        unreadable_identity = result.trace[1].as_dict()["target"]["identity"]
        self.assertFalse(unreadable_identity["classification_available"])
        self.assertIn("unmapped sparse-data", unreadable_identity["classification_error"])
        self.assertFalse(unreadable_identity["attack_eligible"])

    def test_runner_cycles_past_zero_pool_selection_with_stale_position(self) -> None:
        clock = AdvancingClock()
        dispatcher = RecordingPvEDispatcher()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource(
                (_absent(), _target("mob"), _target("mob", current=0))
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
            player_position_reader=SequencePlayerPositionSource((_player_position(),) * 3),
            target_position_reader=SequenceTargetPositionSource(
                (
                    _target_position("stale-corpse"),
                    _target_position("mob"),
                    _target_position("mob"),
                )
            ),
            combat_log_reader=SequenceCombatLogSource(((),) * 3),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(1, result.kills)
        self.assertFalse(result.trace[0].target_present)
        self.assertFalse(result.trace[0].target_position.target_present)
        self.assertEqual(
            [PvEIntent.ACQUIRE_NEXT_MOB, PvEIntent.ATTACK_SELECTED_TARGET],
            dispatcher.intents,
        )

    def test_runner_dispatches_astar_approach_then_attacks_on_arrival(self) -> None:
        clock = AdvancingClock()
        combat_dispatcher = RecordingPvEDispatcher()
        movement_dispatcher = RecordingMovementDispatcher()
        runner = PvERunner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource(
                (
                    _absent(),
                    _target("turtle"),
                    _target("turtle"),
                    _target("turtle"),
                    _target("turtle", current=0),
                )
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 5),
            player_position_reader=SequencePlayerPositionSource((_player_position(),) * 5),
            target_position_reader=SequenceTargetPositionSource(
                (
                    _target_position(None),
                    _target_position("turtle", 200.0, 200.0),
                    _target_position("turtle", 200.0, 200.0),
                    _target_position("turtle", 110.0, 200.0),
                    _target_position("turtle", 110.0, 200.0),
                )
            ),
            combat_log_reader=SequenceCombatLogSource(((),) * 5),
            dispatcher=combat_dispatcher,
            approach_controller=PvEApproachController(
                PvEApproachConfig(
                    native_progress_grace_ms=100,
                    travel=TravelControllerConfig(
                        maximum_session_ms=5_000,
                        click_interval_ms=100,
                        maximum_clicks=10,
                        minimum_progress=5.0,
                    ),
                )
            ),
            movement_dispatcher=movement_dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(1, len(movement_dispatcher.decisions))
        self.assertEqual(1, len(movement_dispatcher.stop_decisions))
        self.assertEqual(
            [
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ATTACK_SELECTED_TARGET,
                PvEIntent.ATTACK_SELECTED_TARGET,
            ],
            combat_dispatcher.intents,
        )
        movement_steps = [step for step in result.trace if step.approach_decision is not None]
        self.assertEqual("moving", movement_steps[0].approach_status)
        self.assertTrue(movement_steps[0].approach_input_accepted)
        self.assertEqual("arrived", movement_steps[1].approach_status)
        self.assertTrue(movement_steps[1].movement_stop_accepted)
        self.assertEqual("direct", movement_steps[0].as_dict()["approach"]["maneuver"])

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
            player_position_reader=SequencePlayerPositionSource((_player_position(),) * 4),
            target_position_reader=SequenceTargetPositionSource(
                (
                    _target_position(None),
                    _target_position("mob"),
                    _target_position("mob"),
                    _target_position(None),
                )
            ),
            target_action_reader=SequenceTargetActionSource(
                (
                    _target_action(
                        "mob",
                        phase=NativeTargetActionPhase.WINDUP,
                        sequence=1,
                    ),
                    _target_action(None),
                )
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
        hit_step = result.trace[2]
        self.assertEqual(50.0, hit_step.player_current_mana)
        self.assertEqual(100.0, hit_step.player_current_stamina)
        self.assertEqual(5.0, hit_step.target_planar_distance)
        self.assertEqual(12.0, hit_step.target_altitude_delta)
        self.assertEqual(13.0, hit_step.target_spatial_distance)
        self.assertEqual(NativeCombatEventKind.PLAYER_HIT_TARGET, hit_step.combat_events[0].kind)
        trace_payload = hit_step.as_dict()
        self.assertEqual(5.0, trace_payload["target"]["planar_distance"])
        self.assertEqual("player_hit_target", trace_payload["combat_events"][0]["kind"])
        self.assertEqual("windup", trace_payload["target"]["action"]["phase"])
        self.assertEqual(
            PvEKillConfirmation.NATIVE_COMBAT_EVENT,
            result.trace[-1].decision.kill_confirmation,
        )
        self.assertEqual(
            "native_combat_event",
            result.trace[-1].as_dict()["kill_confirmation"],
        )

    def test_runner_farms_two_native_health_kills_after_resource_recovery(self) -> None:
        health = SequenceHealthSource(
            (
                _absent(),
                _target("mob-1"),
                _target("mob-1", current=0),
                _absent(),
                _absent(),
                _target("mob-2"),
                _target("mob-2", current=0),
            )
        )
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = PvERunner(
            controller=PvEController(
                PvEControllerConfig(
                    maximum_kills=2,
                    post_kill_delay_ms=100,
                    recovery_timeout_ms=1_000,
                    minimum_recovery_health_fraction=0.75,
                    minimum_recovery_mana_fraction=0.5,
                    minimum_recovery_stamina_fraction=0.5,
                )
            ),
            health_reader=health,
            player_vitals_reader=SequencePlayerVitalsSource(
                (
                    _player(),
                    _player(),
                    _player(current_health=70, current_mana=20, current_stamina=40),
                    _player(current_health=70, current_mana=20, current_stamina=40),
                    _player(current_health=80, current_mana=30, current_stamina=60),
                    _player(current_health=80, current_mana=30, current_stamina=60),
                    _player(current_health=80, current_mana=30, current_stamina=60),
                )
            ),
            combat_log_reader=SequenceCombatLogSource(((),) * 7),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(2, result.kills)
        self.assertEqual(
            [
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ATTACK_SELECTED_TARGET,
                PvEIntent.ACQUIRE_NEXT_MOB,
                PvEIntent.ATTACK_SELECTED_TARGET,
            ],
            dispatcher.intents,
        )
        self.assertEqual(PvEPhase.POST_KILL, result.trace[3].decision.phase)
        confirmations = tuple(
            step.decision.kill_confirmation
            for step in result.trace
            if step.decision.kill_confirmation is not None
        )
        self.assertEqual(
            (
                PvEKillConfirmation.NATIVE_HEALTH_ZERO,
                PvEKillConfirmation.NATIVE_HEALTH_ZERO,
            ),
            confirmations,
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
