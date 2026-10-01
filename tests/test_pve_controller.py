import unittest
from dataclasses import replace
from zlib import crc32

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativeCombatEvent,
    NativeCombatEventKind,
    NativeCombatLogEntry,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetIdentityReadError,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import NativeCharacterKind
from shadowbane_lab.navigation_inspector.events import PlanEvent
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve import (
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
from shadowbane_lab.pve.model import (
    PvECombatAcknowledgement,
    PvECombatCleanupResult,
    PvECombatDisposition,
    PvECombatKind,
)
from shadowbane_lab.pve.native_combat import NativeCombatUpdate
from shadowbane_lab.travel import (
    AStarRouteNotFound,
    SparseNavigationMap,
    TravelControllerConfig,
    TravelManeuver,
    WeightedAStarPlanner,
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


def _target_action(token, *, initiation_state=5, event_index=0,
                   animation_frame=None, targeting_player=True):
    if token is None:
        return NativeTargetActionObservation(target_present=False)
    return NativeTargetActionObservation(
        target_present=True, target_token=token, targeting_player=targeting_player,
        motion_id=106, animation_event_index=event_index, animation_frame=animation_frame,
        initiation_state=initiation_state, power_protocol_ids=(), mode=2, action_state=2)


def _player_action(*, initiation_state=5, event_index=0, animation_frame=None,
                   targeting_selected=None, token="mob", mode=1, action_state=1,
                   power_protocol_ids=()):
    if targeting_selected is None:
        targeting_selected = False
    return NativePlayerActionObservation(
        targeting_selected=targeting_selected, selected_target_token=token,
        action_target_token=token if targeting_selected else None, motion_id=106,
        animation_event_index=event_index, animation_frame=animation_frame,
        initiation_state=initiation_state, power_protocol_ids=power_protocol_ids,
        mode=mode, action_state=action_state)


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


def _population(
    selected: str | None,
    *characters: NativeCharacterObservation,
    action_target: str | None = None,
) -> NativeCharacterPopulationObservation:
    return NativeCharacterPopulationObservation(
        characters=characters,
        selected_target_token=selected,
        player_action_target_token=action_target,
        scan_generation=1,
        rejected_candidates=0,
    )


def _character(
    token: str,
    *,
    lt: float,
    lg: float = 200.0,
    health: float = 10.0,
    trainer: bool = False,
) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token,
        current_health=health,
        maximum_health=max(10.0, health),
        lt=lt,
        lg=lg,
        altitude=10.0,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=trainer,
        minion=False,
        object_key=NativeObjectKey(crc32(token.encode()) or 1, 53),
        character_kind=NativeCharacterKind.NPC,
    )


def _native_observation(**values) -> PvEObservation:
    target = values["target"]
    if values.get("player_position") is None and values.get("target_position") is None:
        values["player_position"] = _player_position()
        values["target_position"] = _target_position(target.target_token)
    if values.get("player_action") is None:
        values["player_action"] = _player_action(token=target.target_token)
    if values.get("population") is None:
        position = values.get("target_position")
        identity = values.get("target_identity")
        characters = ()
        if target.target_present:
            character = _character(
                target.target_token, health=target.current_health,
                lt=103.0 if position is None or not position.target_present else position.lt,
                lg=204.0 if position is None or not position.target_present else position.lg,
            )
            character = replace(character, maximum_health=target.maximum_health)
            if identity is not None:
                character = replace(character, **{name: getattr(identity, name) for name in (
                    "merchant", "shopkeeper", "banker", "trainer", "minion"
                )})
            characters = (character,)
        action = values.get("player_action")
        values["population"] = _population(target.target_token, *characters,
            action_target=None if action is None else action.action_target_token)
    return PvEObservation(**values)


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
    population: NativeCharacterPopulationObservation | None = None,
) -> PvEObservation:
    if player_action is not None and player_action.selected_target_token == "mob":
        player_action = replace(player_action, selected_target_token=target.target_token,
            action_target_token=target.target_token if player_action.targeting_selected else None,
            targeting_selected=player_action.targeting_selected and target.target_token is not None)
    return _native_observation(
        now_ms=now_ms,
        target=target,
        player=_player() if player is None else player,
        combat_events=events,
        player_position=player_position,
        target_position=target_position,
        target_action=target_action,
        player_action=player_action,
        target_identity=target_identity,
        population=population,
    )


def _accepted_step(controller, observation):
    """Policy scenarios with a positively correlated, successful native consumer.

    Pending/negative/uncertain admission has separate explicit proposal tests.
    """
    decision = controller.step(observation)
    proposal = decision.combat_proposal
    if proposal is not None:
        bound = proposal.kind is PvECombatKind.BIND
        controller.acknowledge_combat(proposal, PvECombatAcknowledgement(
            PvECombatDisposition.BOUND if bound else PvECombatDisposition.QUEUED,
            None if bound else True, True,
        ), now_ms=observation.now_ms)
    return decision


class PvEControllerTests(unittest.TestCase):
    def test_native_population_ranks_every_loaded_mob_before_selection(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
            )
        )
        turtle = _character("turtle", lt=105.0)
        crab = _character("crab", lt=115.0)
        trainer = _character("trainer", lt=101.0, trainer=True, health=750.0)
        characters = (trainer, crab, turtle)

        initial = _accepted_step(controller,
            _observation(
                0,
                _target("trainer", 750.0, 750.0),
                target_identity=_target_identity("trainer", trainer=True),
                player_position=_player_position(),
                target_position=_target_position("trainer", 101.0, 200.0),
                population=_population("trainer", *characters),
            )
        )
        skipped = _accepted_step(controller,
            _observation(
                100,
                _target("crab"),
                target_identity=_target_identity("crab"),
                player_position=_player_position(),
                target_position=_target_position("crab", 115.0, 200.0),
                population=_population("crab", *characters),
            )
        )
        selected = _accepted_step(controller,
            _observation(
                200,
                _target("turtle"),
                target_identity=_target_identity("turtle"),
                player_position=_player_position(),
                target_position=_target_position("turtle", 105.0, 200.0),
                population=_population("turtle", *characters),
            )
        )

        self.assertEqual("turtle", initial.combat_proposal.target_token)
        self.assertEqual(PvECombatKind.ATTACK, initial.combat_proposal.kind)
        self.assertIsNone(skipped.combat_proposal)
        self.assertEqual("turtle", skipped.tracked_target.token)
        self.assertIsNone(selected.combat_proposal)
        self.assertEqual(PvEPhase.ENGAGED, selected.phase)


    def test_native_population_retains_candidate_regardless_of_selection_cycle(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
            )
        )
        turtle = _character("turtle", lt=105.0)
        crab = _character("crab", lt=110.0)
        trainer = _character("trainer", lt=101.0, trainer=True, health=750.0)
        characters = (trainer, turtle, crab)

        _accepted_step(controller,
            _observation(
                0,
                _target("trainer", 750.0, 750.0),
                target_identity=_target_identity("trainer", trainer=True),
                player_position=_player_position(),
                target_position=_target_position("trainer", 101.0, 200.0),
                population=_population("trainer", *characters),
            )
        )
        _accepted_step(controller,
            _observation(
                100,
                _target("crab"),
                target_identity=_target_identity("crab"),
                player_position=_player_position(),
                target_position=_target_position("crab", 110.0, 200.0),
                population=_population("crab", *characters),
            )
        )
        wrapped = _accepted_step(controller,
            _observation(
                200,
                _target("trainer", 750.0, 750.0),
                target_identity=_target_identity("trainer", trainer=True),
                player_position=_player_position(),
                target_position=_target_position("trainer", 101.0, 200.0),
                population=_population("trainer", *characters),
            )
        )
        engaged = _accepted_step(controller,
            _observation(
                300,
                _target("crab"),
                target_identity=_target_identity("crab"),
                player_position=_player_position(),
                target_position=_target_position("crab", 110.0, 200.0),
                population=_population("crab", *characters),
            )
        )
        self.assertEqual("turtle", wrapped.tracked_target.token)
        self.assertIsNone(wrapped.combat_proposal)
        self.assertEqual("turtle", engaged.tracked_target.token)
        self.assertEqual(PvEPhase.ENGAGED, engaged.phase)


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
        initial = _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position(None),
            )
        )
        outside = _accepted_step(controller,
            _observation(
                100,
                _target("far-mob"),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position("far-mob", 151.0, 200.0),
            )
        )
        rescan = _accepted_step(controller,
            _observation(
                5_100,
                _target("far-mob"),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position("far-mob", 151.0, 200.0),
            )
        )
        inside = _accepted_step(controller,
            _observation(
                10_100,
                _target("camp-mob"),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position("camp-mob", 120.0, 200.0),
            )
        )

        self.assertEqual((100.0, 200.0), (initial.camp.anchor_lt, initial.camp.anchor_lg))
        self.assertEqual(50.0, initial.camp.radius)
        self.assertFalse(outside.target_inside_camp)
        self.assertIsNone(outside.intent)
        self.assertIsNone(rescan.combat_proposal)
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
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(100.0, 200.0),
                target_position=_target_position(None),
            )
        )
        near_anchor = _accepted_step(controller,
            _observation(
                100,
                _absent(),
                player_position=_player_position(125.0, 200.0),
                target_position=_target_position(None),
            )
        )
        returning = _accepted_step(controller,
            _observation(
                200,
                _absent(),
                player_position=_player_position(140.0, 200.0),
                target_position=_target_position(None),
            )
        )
        arrived = _accepted_step(controller,
            _observation(
                300,
                _absent(),
                player_position=_player_position(105.0, 200.0),
                target_position=_target_position(None),
            )
        )
        rescan = _accepted_step(controller,
            _observation(
                700,
                _absent(),
                player_position=_player_position(105.0, 200.0),
                target_position=_target_position(None),
            )
        )

        self.assertEqual(30.0, near_anchor.camp.return_trigger_radius)
        self.assertFalse(near_anchor.return_to_camp)
        self.assertEqual(PvEPhase.CAMP_IDLE, returning.phase)
        self.assertTrue(returning.return_to_camp)
        self.assertFalse(arrived.return_to_camp)
        self.assertEqual(PvEPhase.CAMP_IDLE, rescan.phase)
        self.assertIsNone(rescan.combat_proposal)

    def test_continuous_kill_limit_is_telemetry_not_a_terminal_bound(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                continuous=True, camp_idle_ms=1,
                camp_radius=50.0,
                maximum_kills=1,
            )
        )
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        _accepted_step(controller,
            _observation(
                100,
                _target("mob"),
                player_position=_player_position(),
                target_position=_target_position("mob"),
            )
        )
        killed = _accepted_step(controller,
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
        controller = PvEController(PvEControllerConfig(continuous=True, camp_radius=50,
            camp_idle_ms=1, failed_target_cooldown_ms=500))
        def frame(now, token):
            return _observation(now, _absent() if token is None else _target(token),
                player_position=_player_position(), target_position=_target_position(token))
        _accepted_step(controller, frame(0, None))
        _accepted_step(controller, frame(100, "mob"))
        abandoned = _accepted_step(controller, frame(2600, "mob"))
        self.assertEqual(PvEPhase.DISENGAGING, abandoned.phase)
        controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(abandoned.cleanup_request))
        self.assertIsNone(_accepted_step(controller, frame(2700, "mob")).intent)
        rejected = _accepted_step(controller, frame(2800, "mob"))
        self.assertNotEqual(PvEIntent.ATTACK_SELECTED_TARGET, rejected.intent)
        _accepted_step(controller, frame(3300, None))
        retried = _accepted_step(controller, frame(3400, "mob"))
        self.assertEqual(PvEPhase.ENGAGED, retried.phase)


    def test_spatial_observation_derives_coherent_target_ranges(self) -> None:
        observation = _native_observation(
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
            _native_observation(
                now_ms=0,
                target=_target("mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("other-mob"),
            )

    def test_explicit_far_target_starts_native_chase_and_reissues_at_arrival(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                melee_approach_radius=20.0,
            )
        )
        _accepted_step(controller,
            _native_observation(
                now_ms=0,
                target=_absent(),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        engaged = _accepted_step(controller,
            _native_observation(
                now_ms=100,
                target=_target("mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("mob", 200.0, 200.0),
            )
        )
        arrived = _accepted_step(controller,
            _native_observation(
                now_ms=200,
                target=_target("mob"),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position("mob", 110.0, 200.0),
            )
        )

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, engaged.intent)
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

        acquire = _accepted_step(controller, _observation(0, _target("statue", 100_000, 100_000),
            target_identity=_target_identity("statue", trainer=True)))
        unchanged = _accepted_step(controller,
            _observation(100, _target("statue", 100_000, 100_000),
            target_identity=_target_identity("statue", trainer=True)))
        attack = _accepted_step(controller, _observation(200, _target("frost-walker")))
        progress = _accepted_step(controller, _observation(300, _target("frost-walker", current=6)))
        complete = _accepted_step(controller,
            _observation(
                400,
                _target("frost-walker", current=0),
                _event(NativeCombatEventKind.TARGET_KILLED),
            )
        )

        self.assertIsNone(acquire.combat_proposal)
        self.assertIsNone(unchanged.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        self.assertEqual(PvEPhase.ENGAGED, progress.phase)
        self.assertEqual(PvEPhase.COMPLETE, complete.phase)
        self.assertEqual("kill_limit_reached", complete.terminal_reason)
        self.assertEqual(1, complete.kills)
        self.assertEqual(
            PvEKillConfirmation.NATIVE_HEALTH_ZERO,
            complete.kill_confirmation,
        )

    def test_exact_native_zero_health_confirms_kill_without_combat_text(self) -> None:
        controller = PvEController(PvEControllerConfig(maximum_kills=1))
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(100, _target("mob")))

        complete = _accepted_step(controller, _observation(200, _target("mob", current=0)))

        self.assertEqual(PvEPhase.COMPLETE, complete.phase)
        self.assertEqual("kill_limit_reached", complete.terminal_reason)
        self.assertEqual(1, complete.kills)
        self.assertEqual(
            PvEKillConfirmation.NATIVE_HEALTH_ZERO,
            complete.kill_confirmation,
        )

    def test_health_zero_kill_requires_engaged_token_across_combat_modes(self) -> None:
        for opening in (False, True):
            for continuous in (False, True):
                for same_target in (False, True):
                    with self.subTest(
                        opening=opening, continuous=continuous, same_target=same_target,
                    ):
                        controller = PvEController(PvEControllerConfig(
                            maximum_kills=1,
                            continuous=continuous, camp_idle_ms=1,
                            camp_radius=100.0 if continuous else None,
                            opening_intent=PvEIntent.CAST_SHADOW_TOUCH if opening else None,
                        ))
                        _accepted_step(controller, _observation(
                            0, _absent(), player_position=_player_position(),
                            target_position=_target_position(None),
                        ))
                        engaged = _accepted_step(controller, _observation(
                            100, _target("mob"), player_position=_player_position(),
                            target_position=_target_position("mob"),
                        ))
                        self.assertEqual(
                            PvEPhase.OPENING if opening else PvEPhase.ENGAGED,
                            engaged.phase,
                        )

                        decision = _accepted_step(controller, _observation(
                            200, _target("mob" if same_target else "unrelated-corpse", current=0),
                            player_position=_player_position(),
                            target_position=_target_position(
                                "mob" if same_target else "unrelated-corpse",
                            ),
                        ))

                        if same_target:
                            self.assertEqual(1, decision.kills)
                            self.assertEqual(
                                PvEKillConfirmation.NATIVE_HEALTH_ZERO, decision.kill_confirmation,
                            )
                            self.assertEqual(
                                PvEPhase.POST_KILL if continuous else PvEPhase.COMPLETE,
                                decision.phase,
                            )
                        else:
                            self.assertEqual(0, decision.kills)
                            self.assertIsNone(decision.kill_confirmation)
                            self.assertEqual(
                                PvEPhase.OPENING if opening else PvEPhase.ENGAGED,
                                decision.phase,
                            )
                            self.assertIsNone(decision.intent)
                            self.assertIsNone(decision.terminal_reason)

    def test_dead_acquisition_candidate_is_never_attacked(self) -> None:
        controller = PvEController(
            PvEControllerConfig(acquisition_retry_ms=100, acquisition_timeout_ms=1_000)
        )
        _accepted_step(controller, _observation(0, _absent()))

        waiting = _accepted_step(controller, _observation(50, _target("corpse", current=0)))
        cycle = _accepted_step(controller, _observation(100, _target("corpse", current=0)))

        self.assertIsNone(waiting.intent)
        self.assertIsNone(cycle.combat_proposal)

    def test_protected_trainer_is_never_admitted(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                target_sample_interval_ms=100,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
            )
        )
        initial = _accepted_step(controller,
            _observation(0, _absent(), target_identity=_target_identity(None))
        )
        cycle = _accepted_step(controller,
            _observation(
                100,
                _target("trainer"),
                target_identity=_target_identity("trainer", trainer=True),
            )
        )
        waiting = _accepted_step(controller,
            _observation(
                150,
                _target("trainer"),
                target_identity=_target_identity("trainer", trainer=True),
            )
        )

        self.assertIsNone(initial.combat_proposal)
        self.assertIsNone(cycle.combat_proposal)
        self.assertIsNone(waiting.intent)
        self.assertEqual(PvEPhase.SEEKING, waiting.phase)

    def test_canonical_population_identity_does_not_require_selected_identity(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                target_sample_interval_ms=100,
                acquisition_retry_ms=100,
                acquisition_timeout_ms=1_000,
            )
        )
        _accepted_step(controller, _observation(0, _absent()))

        decision = _accepted_step(controller, _observation(100, _target("unknown")))

        self.assertEqual(PvECombatKind.ATTACK, decision.combat_proposal.kind)
        self.assertEqual(PvEPhase.ENGAGED, decision.phase)

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
            return _native_observation(
                now_ms=now_ms,
                target=_absent() if token is None else _target(token),
                player=_player(),
                player_position=_player_position(),
                target_position=_target_position(token, lt, 200.0),
                target_identity=_target_identity(token, trainer=trainer),
            )

        _accepted_step(controller, spatial(0, None))
        protected = _accepted_step(controller, spatial(100, "trainer", trainer=True))
        selected = _accepted_step(controller, spatial(200, "mob", lt=108.0))

        self.assertIsNone(protected.combat_proposal)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, selected.intent)
        self.assertEqual(PvEPhase.ENGAGED, selected.phase)



    def test_unexpected_selection_change_during_combat_stops(self) -> None:
        controller = PvEController(PvEControllerConfig())
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(100, _target("first")))
        old = _character("first", lt=103)
        decision = _accepted_step(controller, _observation(200, _target("second"),
            population=_population("second", old, _character("second", lt=120))))
        self.assertEqual(PvEPhase.ENGAGED, decision.phase)
        self.assertEqual("first", decision.tracked_target.token)
        self.assertIsNone(decision.intent)
        self.assertIsNone(decision.cleanup_request)


    def test_player_death_record_stops_from_any_active_phase(self) -> None:
        for engaged in (False, True):
            with self.subTest(engaged=engaged):
                controller = PvEController(PvEControllerConfig())
                _accepted_step(controller, _observation(0, _absent()))
                if engaged:
                    _accepted_step(controller, _observation(10, _target("mob")))
                ignored = _accepted_step(controller, _observation(20, _target("mob"),
                    _event(NativeCombatEventKind.PLAYER_KILLED)))
                self.assertFalse(ignored.terminal)
                stopped = _accepted_step(controller, _observation(30, _target("mob"),
                    player=_player(current_health=0)))
                self.assertEqual("player_death_observed", stopped.terminal_reason)
                self.assertIsNotNone(stopped.cleanup_request)


    def test_low_native_player_health_stops_before_input(self) -> None:
        controller = PvEController(PvEControllerConfig(minimum_player_health_fraction=0.5))

        stopped = _accepted_step(controller,
            _observation(0, _absent(), player=_player(50.0, 100.0)))

        self.assertEqual("player_health_safety_threshold", stopped.terminal_reason)
        self.assertIsNone(stopped.intent)

    def test_stalled_engagement_retries_only_bounded_number_of_times(self) -> None:
        config = PvEControllerConfig(
            stalled_progress_ms=100,
            engagement_timeout_ms=1_000,
            maximum_reengage_attempts=1,
        )
        controller = PvEController(config)
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(10, _target("mob")))

        retry = _accepted_step(controller, _observation(110, _target("mob")))
        stopped = _accepted_step(controller, _observation(210, _target("mob")))

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, retry.intent)
        self.assertEqual("engagement_stalled", stopped.terminal_reason)

    def test_stalled_engagement_cycles_once_and_requires_a_different_target(self) -> None:
        controller = PvEController(PvEControllerConfig(stalled_progress_ms=100,
            engagement_timeout_ms=1000, maximum_reengage_attempts=0, maximum_stalled_retargets=1))
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(10, _target("blocked-mob")))
        cleanup = _accepted_step(controller, _observation(110, _target("blocked-mob")))
        self.assertEqual(PvEPhase.DISENGAGING, cleanup.phase)
        self.assertIsNone(cleanup.intent)
        stale = _accepted_step(controller, _observation(120, _target("reachable-mob"),
            _event(NativeCombatEventKind.PLAYER_HIT_TARGET)))
        self.assertEqual(cleanup.cleanup_request, stale.cleanup_request)
        self.assertIsNone(stale.intent)
        controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup.cleanup_request))
        fresh = _accepted_step(controller, _observation(130, _target("reachable-mob")))
        self.assertEqual(PvEPhase.SEEKING, fresh.phase)
        self.assertIsNone(fresh.intent)
        _accepted_step(controller, _observation(140, _absent()))
        replacement = _accepted_step(controller, _observation(150, _target("reachable-mob")))
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, replacement.intent)
        stopped = _accepted_step(controller, _observation(250, _target("reachable-mob")))
        self.assertEqual("engagement_stalled", stopped.terminal_reason)
        self.assertIsNotNone(stopped.cleanup_request)


    def test_stalled_targets_remain_excluded_during_bounded_retargeting(self) -> None:
        controller = PvEController(PvEControllerConfig(stalled_progress_ms=100,
            engagement_timeout_ms=1000, maximum_reengage_attempts=0, maximum_stalled_retargets=2))
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(10, _target("blocked-a")))
        for now, old, new in ((110, "blocked-a", "blocked-b"), (250, "blocked-b", "reachable")):
            cleanup = _accepted_step(controller, _observation(now, _target(old)))
            self.assertEqual(PvEPhase.DISENGAGING, cleanup.phase)
            controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup.cleanup_request))
            _accepted_step(controller, _observation(now+10, _absent()))
            rejected = _accepted_step(controller, _observation(now+20, _target("blocked-a")))
            self.assertNotEqual(PvEIntent.ATTACK_SELECTED_TARGET, rejected.intent)
            attack = _accepted_step(controller, _observation(now+30, _target(new)))
            self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)


    def test_animation_absence_does_not_shorten_native_health_progress_timeout(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                maximum_stalled_retargets=1,
                quiet_melee_timeout_ms=2_500,
            )
        )
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        attack = _accepted_step(controller,
            _observation(
                100,
                _target("quiet-crab"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("quiet-crab", 106.0, 200.0),
            )
        )
        waiting = _accepted_step(controller,
            _observation(
                2_599,
                _target("quiet-crab"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("quiet-crab", 106.0, 200.0),
            )
        )
        cycle = _accepted_step(controller,
            _observation(
                2_600,
                _target("quiet-crab"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("quiet-crab", 106.0, 200.0),
            )
        )

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        self.assertIsNone(waiting.intent)
        self.assertIsNone(cycle.intent)
        self.assertEqual(PvEPhase.DISENGAGING, cycle.phase)

    def test_observed_attack_animation_uses_full_quiet_melee_timeout(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                maximum_stalled_retargets=1,
                quiet_melee_timeout_ms=2_500,
            )
        )
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        _accepted_step(controller,
            _observation(
                100,
                _target("animated-crab"),
                player_action=_player_action(token="animated-crab", event_index=8),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )
        _accepted_step(controller,
            _observation(
                200,
                _target("animated-crab"),
                player_action=_player_action(token="animated-crab",
                    animation_frame=19,
                    event_index=8,
                ),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )
        waiting = _accepted_step(controller,
            _observation(
                1_600,
                _target("animated-crab"),
                player_action=_player_action(token="animated-crab", event_index=8,),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )
        cycle = _accepted_step(controller,
            _observation(
                2_600,
                _target("animated-crab"),
                player_action=_player_action(token="animated-crab", event_index=8,),
                player_position=_player_position(),
                target_position=_target_position("animated-crab", 106.0, 200.0),
            )
        )

        self.assertIsNone(waiting.intent)
        self.assertIsNone(cycle.intent)

    def test_incoming_hits_without_outgoing_damage_request_reposition(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                automatic_attack_expected=True,
                incoming_reposition_grace_ms=1_500,
                incoming_reposition_window_ms=3_000,
            )
        )
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        _accepted_step(controller,
            _observation(
                100,
                _target("bugged-mob"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("bugged-mob", 106.0, 200.0),
            )
        )
        _accepted_step(controller,
            _observation(
                1_000,
                _target("bugged-mob"),
                player=_player(current_health=90.0),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("bugged-mob", 106.0, 200.0),
            )
        )
        reposition = _accepted_step(controller,
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
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        _accepted_step(controller,
            _observation(
                100,
                _target("trading-mob"),
                player_action=_player_action(),
                player_position=_player_position(),
                target_position=_target_position("trading-mob", 106.0, 200.0),
            )
        )
        trading = _accepted_step(controller,
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
        _accepted_step(controller,
            _observation(
                0,
                _absent(),
                player_position=_player_position(),
                target_position=_target_position(None),
            )
        )
        _accepted_step(controller,
            _observation(
                100,
                _target("busy-player"),
                player_action=_player_action(event_index=3),
                player_position=_player_position(),
                target_position=_target_position("busy-player", 106.0, 200.0),
            )
        )
        busy = _accepted_step(controller,
            _observation(
                1_600,
                _target("busy-player"),
                player=_player(current_health=90.0),
                player_action=_player_action(
                    event_index=4,
                ),
                player_position=_player_position(),
                target_position=_target_position("busy-player", 106.0, 200.0),
            )
        )

        self.assertTrue(busy.reposition_requested)

    def test_two_kill_limit_reacquires_after_post_kill_delay(self) -> None:
        controller = PvEController(PvEControllerConfig(maximum_kills=2, post_kill_delay_ms=100))
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(10, _target("mob-1")))
        killed = _accepted_step(controller, _observation(20, _target("mob-1", current=0)))
        self.assertEqual(PvEPhase.POST_KILL, killed.phase)
        self.assertIsNone(_accepted_step(controller, _observation(100, _absent())).cleanup_request)
        cleanup = _accepted_step(controller, _observation(120, _absent()))
        self.assertEqual(PvEPhase.DISENGAGING, cleanup.phase)
        controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup.cleanup_request))
        self.assertIsNone(_accepted_step(controller, _observation(130, _absent())).intent)
        acquire = _accepted_step(controller, _observation(140, _absent()))
        attack = _accepted_step(controller, _observation(150, _target("mob-2")))
        self.assertIsNone(acquire.combat_proposal)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)


    def test_post_kill_waits_for_all_recovery_floors_before_reacquiring(self) -> None:
        for player in (_player(current_health=70), _player(current_mana=20),
                       _player(current_stamina=40)):
            controller = PvEController(PvEControllerConfig(maximum_kills=2, post_kill_delay_ms=100,
                minimum_recovery_health_fraction=.75, minimum_recovery_mana_fraction=.5,
                minimum_recovery_stamina_fraction=.5))
            _accepted_step(controller, _observation(0, _absent()))
            _accepted_step(controller, _observation(10, _target("mob")))
            _accepted_step(controller, _observation(20, _target("mob", current=0)))
            cleanup = _accepted_step(controller, _observation(120, _absent(), player=player))
            controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup.cleanup_request))
            waiting = _accepted_step(controller, _observation(130, _absent(), player=player))
            self.assertEqual(PvEPhase.RECOVERING, waiting.phase)
            self.assertIsNone(waiting.intent)
            self.assertIsNone(_accepted_step(controller, _observation(140, _absent())).intent)
            self.assertIsNone(
                _accepted_step(controller, _observation(150, _absent())).combat_proposal)


    def test_post_kill_recovery_timeout_stops_instead_of_farming_depleted(self) -> None:
        controller = PvEController(PvEControllerConfig(maximum_kills=2, post_kill_delay_ms=100,
            recovery_timeout_ms=500, minimum_recovery_mana_fraction=.5))
        _accepted_step(controller, _observation(0, _absent()))
        _accepted_step(controller, _observation(10, _target("mob")))
        _accepted_step(controller, _observation(20, _target("mob", current=0)))
        cleanup = _accepted_step(controller, _observation(120, _absent()))
        controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup.cleanup_request))
        stopped = _accepted_step(controller,
            _observation(620, _absent(), player=_player(current_mana=20)))
        self.assertEqual(PvEPhase.STOPPED, stopped.phase)
        self.assertEqual("combat_recovery_timeout", stopped.terminal_reason)


    def test_opener_queue_ack_schedules_attack_and_bounded_stall_fallback(self) -> None:
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

        opener = _accepted_step(controller, _observation(0, _target("auto-mob"), player=player))
        opening = _accepted_step(controller,
            _observation(50, _target("auto-mob", 9), player=player))
        engaged = _accepted_step(controller,
            _observation(100, _target("auto-mob", 9), player=player))
        fallback = _accepted_step(controller,
            _observation(600, _target("auto-mob", 9), player=player))

        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, opener.intent)
        self.assertEqual(PvEPhase.OPENING, opening.phase)
        self.assertIsNone(opening.intent)
        self.assertEqual(PvEPhase.ENGAGED, engaged.phase)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, engaged.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, fallback.intent)

    def test_unknown_busy_action_ignores_hit_text_and_waits_for_native_completion(self):
        controller = PvEController(PvEControllerConfig(
            opening_intent=PvEIntent.CAST_SHADOW_TOUCH))
        busy = _player_action(initiation_state=6, targeting_selected=False)
        waiting = _accepted_step(controller, _observation(0, _target("mob"), player_action=busy))
        still_waiting = _accepted_step(controller, _observation(100, _target("mob"),
            _event(NativeCombatEventKind.PLAYER_HIT_TARGET), player_action=busy))
        self.assertIsNone(waiting.combat_proposal)
        self.assertIsNone(still_waiting.combat_proposal)
        _accepted_step(controller, _observation(200, _target("mob")))
        ready = _accepted_step(controller, _observation(201, _target("mob")))
        self.assertEqual(PvECombatKind.CAST, ready.combat_proposal.kind)



    def test_existing_native_target_is_adopted_without_opener_or_selection_cycle(self):
        controller = PvEController(PvEControllerConfig(
            opening_intent=PvEIntent.CAST_SHADOW_TOUCH))
        busy = _player_action(initiation_state=6, targeting_selected=True)
        adopted = _accepted_step(controller, _observation(0, _target("mob"), player_action=busy))
        self.assertEqual(PvECombatKind.BIND, adopted.combat_proposal.kind)
        self.assertTrue(adopted.combat_proposal.adopted_existing_action)
        self.assertIsNone(adopted.intent)
        self.assertIsNone(adopted.cleanup_request)
        self.assertIsNone(_accepted_step(controller,
            _observation(100, _target("mob"), player_action=busy)).combat_proposal)



    def test_proc_assassin_skips_opener_when_native_mana_is_too_low(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                opening_mana_cost=55.0,
                automatic_attack_expected=True,
            )
        )

        decision = _accepted_step(controller,
            _observation(
                0,
                _target("auto-mob"),
                player=_player(current_mana=54.0, maximum_mana=100.0),
            )
        )

        self.assertEqual(PvEPhase.ENGAGED, decision.phase)
        self.assertEqual(PvECombatKind.ATTACK, decision.combat_proposal.kind)

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
        _accepted_step(controller, _observation(0, _target("mob"), player=player))

        interrupt = _accepted_step(controller,
            _observation(
                100,
                _target("mob"),
                player=player,
                target_action=_target_action(
                    "mob",
                    initiation_state=6,
                    event_index=1,
                ),
            )
        )
        same_attack = _accepted_step(controller,
            _observation(
                200,
                _target("mob"),
                player=player,
                target_action=_target_action(
                    "mob",
                    event_index=1,
                ),
            )
        )
        next_attack = _accepted_step(controller,
            _observation(
                3_000,
                _target("mob"),
                player=player,
                target_action=_target_action(
                    "mob",
                    initiation_state=6,
                    event_index=2,
                ),
            )
        )

        self.assertIsNone(interrupt.intent)
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
        _accepted_step(controller, _observation(0, _target("mob"), player=low_mana))
        action = _target_action(
            "mob",
            initiation_state=6,
            event_index=1,
        )

        waiting = _accepted_step(controller,
            _observation(100, _target("mob"), player=low_mana, target_action=action)
        )
        interrupt = _accepted_step(controller,
            _observation(200, _target("mob"), player=enough_mana, target_action=action)
        )

        self.assertIsNone(waiting.intent)
        self.assertIsNone(interrupt.intent)

    def test_interrupt_ignores_attack_aimed_at_another_actor(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                accept_automatic_targets=True,
                interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH,
                maximum_interrupts_per_target=1,
                automatic_attack_expected=True,
            )
        )
        _accepted_step(controller, _observation(0, _target("mob")))

        decision = _accepted_step(controller,
            _observation(
                100,
                _target("mob"),
                target_action=_target_action(
                    "mob",
                    initiation_state=6,
                    event_index=1,
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
        _accepted_step(controller, _observation(0, _target("mob")))
        first = _accepted_step(controller,
            _observation(
                100,
                _target("mob"),
                target_action=_target_action(
                    "mob",
                    initiation_state=6,
                    event_index=1,
                ),
            )
        )
        second_action = _target_action(
            "mob",
            initiation_state=6,
            event_index=2,
        )

        cooling_down = _accepted_step(controller,
            _observation(1_000, _target("mob"), target_action=second_action)
        )
        ready = _accepted_step(controller,
            _observation(2_100, _target("mob"), target_action=second_action))

        self.assertIsNone(first.intent)
        self.assertIsNone(cooling_down.intent)
        self.assertIsNone(ready.intent)

    def test_proc_assassin_opens_automatic_replacement_after_confirmed_kill(self) -> None:
        controller = PvEController(PvEControllerConfig(maximum_kills=2,
            accept_automatic_targets=True, opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
            opening_followup_delay_ms=100, post_kill_delay_ms=100))
        _accepted_step(controller, _observation(0, _target("mob-1")))
        killed = _accepted_step(controller, _observation(100, _target("mob-2"),
            population=_population("mob-2", _character("mob-1", lt=103, health=0),
                                   _character("mob-2", lt=104))))
        self.assertEqual(PvEPhase.POST_KILL, killed.phase)
        cleanup = _accepted_step(controller, _observation(200, _target("mob-2")))
        self.assertIsNone(cleanup.intent)
        controller.acknowledge_cleanup(ConfirmedCleanup().cleanup(cleanup.cleanup_request))
        _accepted_step(controller, _observation(210, _absent()))
        _accepted_step(controller, _observation(220, _absent()))
        opener = _accepted_step(controller, _observation(230, _target("mob-3")))
        self.assertEqual(PvEIntent.CAST_SHADOW_TOUCH, opener.intent)


    def test_selection_change_during_opener_preserves_explicit_attack_target(self) -> None:
        controller = PvEController(PvEControllerConfig(accept_automatic_targets=True,
            opening_intent=PvEIntent.CAST_SHADOW_TOUCH, opening_followup_delay_ms=100))
        _accepted_step(controller, _observation(0, _target("first")))
        decision = _accepted_step(controller, _observation(100, _target("second"),
            population=_population("second", _character("first", lt=103),
                                   _character("second", lt=120))))
        self.assertEqual(PvEPhase.ENGAGED, decision.phase)
        self.assertEqual("first", decision.tracked_target.token)
        self.assertEqual("first", decision.combat_proposal.target_token)
        self.assertIsNone(decision.cleanup_request)


    def test_required_intents_include_configured_opener_and_stall_fallback(self) -> None:
        controller = PvEController(PvEControllerConfig(opening_intent=PvEIntent.CAST_SHADOW_TOUCH))

        self.assertEqual(
            frozenset(
                {
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
                _native_observation(
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

    def test_stalled_native_chase_backtracks_before_astar_replan(self) -> None:
        navigation = SparseNavigationMap()
        events = []
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
            planner=WeightedAStarPlanner(observer=events.append),
        )

        def observe(now_ms: int):
            return approach.step(
                _native_observation(
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

        backtrack = observe(300)
        replanned = observe(400)

        self.assertEqual("moving", backtrack.status.value)
        self.assertEqual(TravelManeuver.ESCAPE_BACKTRACK, backtrack.decision.maneuver)
        assert backtrack.decision.click_destination is not None
        self.assertEqual(90.0, backtrack.decision.click_destination.x)
        self.assertEqual(200.0, backtrack.decision.click_destination.y)
        self.assertGreater(len(navigation.blocked), 0)
        self.assertEqual("moving", replanned.status.value)
        self.assertEqual(TravelManeuver.DIRECT, replanned.decision.maneuver)
        plans = [event for event in events if isinstance(event, PlanEvent)]
        self.assertEqual(10.0, plans[-1].cell_size)
        self.assertEqual(1, plans[-1].planner_clearance_cells)

    def test_initial_astar_no_route_becomes_recoverable_approach_failure(self) -> None:
        class NoRoutePlanner(WeightedAStarPlanner):
            def plan(self, *_args, **_kwargs):
                raise AStarRouteNotFound("test route is blocked")

        approach = PvEApproachController(
            PvEApproachConfig(native_progress_grace_ms=100),
            planner=NoRoutePlanner(),
        )
        observation = _native_observation(
            now_ms=0,
            target=_target("turtle"),
            player=_player(),
            player_position=_player_position(),
            target_position=_target_position("turtle", 200.0, 200.0),
        )

        self.assertEqual(
            "idle",
            approach.step(observation, phase=PvEPhase.ENGAGED).status.value,
        )
        failed = approach.step(
            _native_observation(
                now_ms=100,
                target=observation.target,
                player=observation.player,
                player_position=observation.player_position,
                target_position=observation.target_position,
            ),
            phase=PvEPhase.ENGAGED,
        )

        self.assertEqual("failed", failed.status.value)
        self.assertEqual("stopped", failed.decision.phase.value)
        self.assertEqual(0, failed.decision.click_count)
        self.assertIn("astar_route_not_found", failed.decision.terminal_reason)


class ConfirmedCleanup:
    def cleanup(self, request):
        return PvECombatCleanupResult(request, True, "11111111-1111-4111-8111-111111111111")


class FixtureIdleActionSource:
    def __init__(self, health):
        self.health = health

    def observe_player(self):
        return _player_action(token=self.health.last.target_token)


class FixturePopulationSource:
    def __init__(self, health, position=None, action=None, controller=None, identity=None):
        self.identity = identity
        self.health, self.position = health, position
        self.action, self.controller = action, controller

    def observe(self):
        target = self.health.last
        position = None
        if self.position is not None and getattr(self.position, "values", None):
            position = self.position.values[0]
        if not target.target_present and position is not None:
            position = _target_position(None)
        action = None
        if (self.action is not None and self.controller.player_action_observation_active
                and getattr(self.action, "values", None)):
            action = self.action.values[0]
        identity = None if self.identity is None else self.identity.values[0]
        frame = _native_observation(now_ms=0, target=target, player=_player(),
            target_identity=(identity if isinstance(identity, NativeTargetIdentityObservation)
                             else None),
            player_action=action,
            target_position=position,
            player_position=None if position is None else _player_position()).population
        if isinstance(identity, NativeTargetIdentityReadError):
            frame = replace(frame, characters=tuple(
                replace(character, character_kind=NativeCharacterKind.UNKNOWN)
                for character in frame.characters))
        return frame


class FixtureTargetPositionSource:
    def __init__(self, health):
        self.health = health

    def observe(self):
        return _target_position(self.health.last.target_token)


class FixturePlayerPositionSource:
    def observe(self):
        return _player_position()


def _runner(**values):
    values.setdefault("player_position_reader", FixturePlayerPositionSource())
    values.setdefault("target_position_reader",
                      FixtureTargetPositionSource(values["health_reader"]))
    values.setdefault("player_action_reader", FixtureIdleActionSource(values["health_reader"]))
    values.setdefault("population_reader", FixturePopulationSource(
        values["health_reader"], values.get("target_position_reader"),
        values.get("player_action_reader"), values["controller"],
        values.get("target_identity_reader")))
    values.setdefault("combat_cleanup", ConfirmedCleanup())
    return PvERunner(**values)


class SequenceHealthSource:
    def __init__(self, values: tuple[NativeTargetHealthObservation, ...]) -> None:
        self.values = list(values)

    def observe(self) -> NativeTargetHealthObservation:
        self.last = self.values.pop(0)
        return self.last


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
        self.value = self.last = value

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
        self.intents = []
        self.proposals = []

    def advance(self, proposal, observation):
        self.proposals.append(proposal)
        self.intents.append({PvECombatKind.ATTACK: PvEIntent.ATTACK_SELECTED_TARGET,
                             PvECombatKind.CAST: PvEIntent.CAST_SHADOW_TOUCH,
                             PvECombatKind.BIND: None}[proposal.kind])
        if self.raises:
            raise OSError("native backend failed for test")
        bound = proposal.kind is PvECombatKind.BIND
        return NativeCombatUpdate(PvECombatAcknowledgement(
            (PvECombatDisposition.BOUND if bound else PvECombatDisposition.QUEUED)
            if self.accepted else PvECombatDisposition.REJECTED,
            None if bound else self.accepted, True,
        ))


class StopRacingPvEDispatcher(RecordingPvEDispatcher):
    def __init__(self, stop: EventEmergencyStop) -> None:
        super().__init__(accepted=False)
        self.stop = stop

    def advance(self, proposal, observation):
        self.stop.trip()
        return super().advance(proposal, observation)


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
    def test_uncertain_native_action_keeps_exact_proposal_until_acknowledged(self) -> None:
        class UncertainThenQueued(RecordingPvEDispatcher):
            def advance(self, proposal, observation):
                if not self.proposals:
                    self.proposals.append(proposal)
                    return NativeCombatUpdate(PvECombatAcknowledgement(
                        PvECombatDisposition.UNCERTAIN, None, True,
                    ))
                return super().advance(proposal, observation)

        dispatcher = UncertainThenQueued()
        controller = PvEController(PvEControllerConfig(maximum_kills=1))
        clock = AdvancingClock()
        result = _runner(
            controller=controller,
            health_reader=SequenceHealthSource((
                _target("mob"), _target("mob"), _target("mob", current=0),
            )),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
            dispatcher=dispatcher, stop_signal=EventEmergencyStop(),
            poll_interval_ms=100, clock=clock, sleeper=clock.sleep,
        ).run()
        self.assertEqual(PvEPhase.COMPLETE, result.final_phase)
        self.assertEqual(2, len(dispatcher.proposals))
        self.assertIs(dispatcher.proposals[0], dispatcher.proposals[1])
        self.assertIsNone(controller.pending_combat_proposal)
        self.assertEqual([False, True], [step.input_accepted for step in result.trace[:2]])
        self.assertEqual(["uncertain", "queued"], [
            step.as_dict()["native_combat"]["disposition"] for step in result.trace[:2]
        ])
        self.assertTrue(result.trace[-1].combat_cleanup.confirmed)

    def test_stop_racing_with_dispatch_is_a_clean_emergency_stop(self) -> None:
        clock = AdvancingClock()
        stop = EventEmergencyStop()
        runner = _runner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=ConstantHealthSource(_target("mob")),
            player_vitals_reader=FlakyPlayerVitalsSource(0),
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
        runner = _runner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource(
                (_absent(), _target("mob"), _target("mob", current=0.0))
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
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

    def test_runner_samples_and_traces_player_animation_before_attack(self) -> None:
        clock = AdvancingClock()
        runner = _runner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource(
                (_absent(), _target("mob"), _target("mob", current=0))
            ),
            player_action_reader=SequencePlayerActionSource(
                (
                    _player_action(token=None),
                    _player_action(event_index=4),
                    _player_action(
                        event_index=5,
                    ),
                )
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
            dispatcher=RecordingPvEDispatcher(),
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        acquired_action = result.trace[1].as_dict()["player"]["action"]
        combat_action = result.trace[2].as_dict()["player"]["action"]
        self.assertEqual(4, acquired_action["animation_event_index"])
        self.assertEqual(5, combat_action["animation_event_index"])
        self.assertNotIn("phase", combat_action)

    def test_runner_cycles_protected_identity_and_traces_valid_target(self) -> None:
        clock = AdvancingClock()
        dispatcher = RecordingPvEDispatcher()
        runner = _runner(
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
        runner = _runner(
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
        runner = _runner(
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
            [PvEIntent.ATTACK_SELECTED_TARGET],
            dispatcher.intents,
        )

    def test_runner_preserves_combat_actions_while_verifying_approach_arrival(self) -> None:
        clock = AdvancingClock()
        combat_dispatcher = RecordingPvEDispatcher()
        movement_dispatcher = RecordingMovementDispatcher()
        runner = _runner(
            controller=PvEController(
                PvEControllerConfig(
                    maximum_kills=1,
                    opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
                    opening_followup_delay_ms=200,
                )
            ),
            health_reader=SequenceHealthSource(
                (
                    _absent(),
                    _target("turtle"),
                    _target("turtle"),
                    *[_target("turtle")] * 11,
                    _target("turtle", current=0),
                )
            ),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 15),
            player_position_reader=SequencePlayerPositionSource((_player_position(),) * 15),
            target_position_reader=SequenceTargetPositionSource(
                (
                    _target_position(None),
                    *[_target_position("turtle", 200.0, 200.0)] * 4,
                    *[_target_position("turtle", 110.0, 200.0)] * 10,
                )
            ),
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

        self.assertEqual(PvEPhase.COMPLETE, result.final_phase, result.terminal_reason)
        self.assertEqual(1, len(movement_dispatcher.decisions))
        self.assertEqual(0, len(movement_dispatcher.stop_decisions))
        self.assertEqual(
            [
                PvEIntent.CAST_SHADOW_TOUCH,
                PvEIntent.ATTACK_SELECTED_TARGET,
                PvEIntent.ATTACK_SELECTED_TARGET,
            ],
            combat_dispatcher.intents,
        )
        movement_steps = [step for step in result.trace if step.approach_decision is not None]
        self.assertEqual("moving", movement_steps[0].approach_status)
        self.assertTrue(movement_steps[0].approach_input_accepted)
        self.assertEqual("arrived", movement_steps[1].approach_status)
        self.assertIsNone(movement_steps[1].movement_stop_accepted)
        self.assertIsNone(movement_steps[1].movement_arrival_confirmed)
        self.assertTrue(any(step.movement_arrival_confirmed for step in movement_steps))
        attacks = [
            step for step in result.trace if step.input_accepted
            and step.decision.intent is PvEIntent.ATTACK_SELECTED_TARGET
        ]
        self.assertEqual([300, 500], [step.decision.now_ms for step in attacks])
        self.assertEqual("direct", movement_steps[0].as_dict()["approach"]["maneuver"])

    def test_runner_records_unrelated_corpse_as_target_change_not_kill(self) -> None:
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        journal_steps = []
        result = _runner(
            controller=PvEController(PvEControllerConfig(maximum_kills=1)),
            health_reader=SequenceHealthSource((
                _absent(), _target("mob"), _target("unrelated-corpse", current=0),
            )),
            player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 3),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            trace_sink=lambda step: journal_steps.append(step.as_dict()),
            poll_interval_ms=100,
            clock=clock,
            sleeper=clock.sleep,
        ).run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertTrue(result.terminal_reason.startswith("observation_failure:"))
        self.assertEqual(0, result.kills)
        self.assertEqual(
            [PvEIntent.ATTACK_SELECTED_TARGET], dispatcher.intents,
        )
        self.assertEqual(journal_steps, [step.as_dict() for step in result.trace])
        terminal = journal_steps[-1]
        cleaned = [step for step in result.trace if step.combat_cleanup is not None]
        self.assertEqual(1, len(cleaned))
        self.assertEqual("mob", cleaned[0].combat_cleanup.request.target_token)
        self.assertTrue(cleaned[0].combat_cleanup.confirmed)
        self.assertEqual(0, terminal["kills"])
        self.assertIsNone(terminal["kill_confirmation"])
        self.assertIsNone(terminal["intent"])

    def test_runner_completes_one_native_observation_driven_kill(self) -> None:
        health = SequenceHealthSource(
            (
                _absent(),
                _target("mob"),
                _target("mob", current=5),
                _target("mob", current=0),
            )
        )
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = _runner(
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
                    _target_position("mob"),
                )
            ),
            target_action_reader=SequenceTargetActionSource(
                (
                    _target_action(
                        "mob",
                        event_index=1,
                    ),
                    _target_action("mob"),
                )
            ),
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
            [PvEIntent.ATTACK_SELECTED_TARGET],
            dispatcher.intents,
        )
        hit_step = result.trace[2]
        self.assertEqual(50.0, hit_step.player_current_mana)
        self.assertEqual(100.0, hit_step.player_current_stamina)
        self.assertEqual(5.0, hit_step.target_planar_distance)
        self.assertEqual(12.0, hit_step.target_altitude_delta)
        self.assertEqual(13.0, hit_step.target_spatial_distance)
        self.assertEqual((), hit_step.combat_events)
        trace_payload = hit_step.as_dict()
        self.assertEqual(5.0, trace_payload["target"]["planar_distance"])
        self.assertEqual([], trace_payload["combat_events"])
        self.assertEqual(1, trace_payload["target"]["action"]["animation_event_index"])
        self.assertEqual(
            PvEKillConfirmation.NATIVE_HEALTH_ZERO,
            result.trace[-1].decision.kill_confirmation,
        )
        self.assertEqual(
            "native_health_zero",
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
                _absent(),
                _target("mob-2"),
                _target("mob-2", current=0),
            )
        )
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = _runner(
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
                    _player(current_health=80, current_mana=30, current_stamina=60),
                )
            ),
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
                PvEIntent.ATTACK_SELECTED_TARGET,
                PvEIntent.ATTACK_SELECTED_TARGET,
            ],
            dispatcher.intents,
        )
        self.assertEqual(PvEPhase.DISENGAGING, result.trace[3].decision.phase)
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

    def test_runner_cleans_up_once_when_native_action_is_rejected(self) -> None:
        clock = AdvancingClock()
        dispatcher = RecordingPvEDispatcher(accepted=False)
        runner = _runner(
            controller=PvEController(PvEControllerConfig(maximum_session_ms=250)),
            health_reader=ConstantHealthSource(_target("mob")),
            player_vitals_reader=FlakyPlayerVitalsSource(0),
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("maximum_session_elapsed", result.terminal_reason)
        self.assertEqual(1, len(dispatcher.proposals))
        cleanup = [step.combat_cleanup for step in result.trace
                   if step.combat_cleanup is not None]
        self.assertEqual(1, len(cleanup))
        self.assertTrue(cleanup[0].confirmed)
        self.assertEqual("native_combat_rejected", cleanup[0].request.reason)
        self.assertFalse(result.trace[0].input_accepted)

    def test_runner_stops_when_native_action_adapter_raises(self) -> None:
        clock = AdvancingClock()
        runner = _runner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=ConstantHealthSource(_target("mob")),
            player_vitals_reader=FlakyPlayerVitalsSource(0),
            dispatcher=RecordingPvEDispatcher(raises=True),
            stop_signal=EventEmergencyStop(),
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual(PvEPhase.STOPPED, result.final_phase)
        self.assertEqual("observation_failure:OSError:native backend failed for test",
                         result.terminal_reason)
        self.assertTrue(result.trace[-1].combat_cleanup.confirmed)

    def test_runner_pauses_input_and_recovers_after_transient_observation_failures(self) -> None:
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = _runner(
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
            dispatcher=dispatcher,
            stop_signal=EventEmergencyStop(),
            poll_interval_ms=100,
            maximum_consecutive_observation_failures=3,
            clock=clock,
            sleeper=clock.sleep,
        )

        result = runner.run()

        self.assertEqual("mob_acquisition_timeout", result.terminal_reason)
        self.assertEqual([], dispatcher.proposals)
        self.assertGreaterEqual(len(result.trace), 2)
        self.assertGreaterEqual(result.trace[0].decision.now_ms, 200)

    def test_runner_stops_after_bounded_consecutive_observation_failures(self) -> None:
        dispatcher = RecordingPvEDispatcher()
        clock = AdvancingClock()
        runner = _runner(
            controller=PvEController(PvEControllerConfig()),
            health_reader=ConstantHealthSource(_absent()),
            player_vitals_reader=FlakyPlayerVitalsSource(3),
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
