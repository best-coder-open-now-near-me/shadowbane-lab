import unittest

from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.protocol import Relation
from shadowbane_lab.pve import (
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
    PvEPhase,
    PvETargetAuthorityEvidence,
    PvETargetAuthorityExclusion,
    PvETargetCharacterKind,
    PvETargetRejectionReason,
    StaticPvETargetAuthorityEvaluator,
    evaluate_pve_target_authority,
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


def _target(token: str | None, health: float = 10.0) -> NativeTargetHealthObservation:
    if token is None:
        return NativeTargetHealthObservation(target_present=False)
    return NativeTargetHealthObservation(
        target_present=True,
        current_health=health,
        maximum_health=10.0,
        target_token=token,
    )


def _identity(
    token: str | None,
    *,
    trainer: bool = False,
    arc_character: bool = True,
) -> NativeTargetIdentityObservation:
    if token is None:
        return NativeTargetIdentityObservation(target_present=False)
    return NativeTargetIdentityObservation(
        target_present=True,
        arc_character=arc_character,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=trainer,
        minion=False,
        target_token=token,
    )


def _character(token: str) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token,
        current_health=10.0,
        maximum_health=10.0,
        lt=105.0,
        lg=200.0,
        altitude=10.0,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
    )


def _observation(
    now_ms: int,
    token: str | None,
    *,
    identity: NativeTargetIdentityObservation | None = None,
    population: NativeCharacterPopulationObservation | None = None,
) -> PvEObservation:
    player_position = None
    target_position = None
    if population is not None:
        player_position = NativePlayerPositionObservation(100.0, 200.0, 10.0)
        target_position = (
            NativeTargetPositionObservation(target_present=False)
            if token is None
            else NativeTargetPositionObservation(
                target_present=True,
                lt=105.0,
                lg=200.0,
                altitude=10.0,
                target_token=token,
            )
        )
    return PvEObservation(
        now_ms=now_ms,
        target=_target(token),
        player=_player(),
        target_identity=_identity(token) if identity is None else identity,
        player_position=player_position,
        target_position=target_position,
        population=population,
    )


def _evidence(
    token: str,
    *,
    relation: Relation | None = Relation.ENEMY,
    character_kind: PvETargetCharacterKind = PvETargetCharacterKind.NPC,
    same_party: bool | None = False,
    friendly_owned: bool | None = False,
    attackable: bool | None = True,
    target_object_key: NativeObjectKey | None = None,
    local_player_object_key: NativeObjectKey | None = None,
) -> PvETargetAuthorityEvidence:
    return PvETargetAuthorityEvidence(
        target_token=token,
        source_revision=7,
        target_object_key=target_object_key or NativeObjectKey(10, 7001),
        local_player_object_key=local_player_object_key or NativeObjectKey(10, 42),
        character_kind=character_kind,
        relation=relation,
        same_party=same_party,
        friendly_owned=friendly_owned,
        attackable=attackable,
        evidence_sources=(
            "native_object_identity",
            "native_character_kind",
            "native_relation_snapshot",
            "native_party_projection",
            "native_ownership_projection",
            "native_attackability",
        ),
    )


class TimedAuthorityEvaluator:
    def evaluate(self, observation: PvEObservation):
        evidence = None
        if observation.target.target_present:
            assert observation.target.target_token is not None
            evidence = _evidence(
                observation.target.target_token,
                relation=(
                    Relation.ENEMY if observation.now_ms < 200 else Relation.NEUTRAL
                ),
            )
        return evaluate_pve_target_authority(observation, evidence)


class PvETargetAuthorityTests(unittest.TestCase):
    def test_complete_positive_proof_is_accepted_and_serialized(self) -> None:
        decision = evaluate_pve_target_authority(
            _observation(100, "mob"),
            _evidence("mob"),
        )

        self.assertTrue(decision.accepted)
        self.assertEqual("verified_hostile_npc", decision.summary_reason)
        payload = decision.as_dict()
        self.assertEqual("enemy", payload["relation"])
        self.assertEqual("npc", payload["character_kind"])
        self.assertEqual({"object_type": 10, "object_uuid": 7001}, payload["target_object_key"])
        self.assertEqual([], payload["exclusions"])

    def test_missing_authority_evidence_is_explicit_and_fail_closed(self) -> None:
        decision = evaluate_pve_target_authority(_observation(100, "mob"), None)

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.AUTHORITY_EVIDENCE_UNAVAILABLE,
            decision.exclusions,
        )
        self.assertEqual(
            "authority_evidence_unavailable",
            decision.summary_reason,
        )

    def test_party_and_neutral_facts_are_both_preserved(self) -> None:
        decision = evaluate_pve_target_authority(
            _observation(100, "mob"),
            _evidence("mob", relation=Relation.NEUTRAL, same_party=True),
        )

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.RELATION_NOT_ENEMY,
            decision.exclusions,
        )
        self.assertIn(PvETargetAuthorityExclusion.PARTY_MEMBER, decision.exclusions)

    def test_protected_native_role_cannot_be_overridden_by_hostile_evidence(self) -> None:
        decision = evaluate_pve_target_authority(
            _observation(100, "trainer", identity=_identity("trainer", trainer=True)),
            _evidence("trainer"),
        )

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.PROTECTED_SERVICE_ROLE,
            decision.exclusions,
        )

    def test_strict_controller_requires_an_evaluator(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a target_authority_evaluator"):
            PvEController(
                PvEControllerConfig(),
                require_verified_target_authority=True,
            )

    def test_strict_controller_attacks_only_complete_positive_proof(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=StaticPvETargetAuthorityEvaluator(
                (_evidence("mob"),)
            ),
            require_verified_target_authority=True,
        )

        acquire = controller.step(_observation(0, None))
        attack = controller.step(_observation(100, "mob"))

        self.assertEqual(PvEIntent.ACQUIRE_NEXT_MOB, acquire.intent)
        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        self.assertEqual(PvEPhase.ENGAGED, attack.phase)
        assert controller.latest_target_authority is not None
        self.assertTrue(controller.latest_target_authority.accepted)

    def test_strict_controller_cycles_unverified_direct_target(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=StaticPvETargetAuthorityEvaluator(
                (_evidence("mob", relation=Relation.NEUTRAL),)
            ),
            require_verified_target_authority=True,
        )
        controller.step(_observation(0, None))

        rejected = controller.step(_observation(100, "mob"))

        self.assertEqual(PvEPhase.SEEKING, rejected.phase)
        self.assertNotEqual(PvEIntent.ATTACK_SELECTED_TARGET, rejected.intent)
        assert controller.latest_target_authority is not None
        self.assertIn(
            PvETargetAuthorityExclusion.RELATION_NOT_ENEMY,
            controller.latest_target_authority.exclusions,
        )

    def test_population_rejection_retains_authority_exclusions(self) -> None:
        population = NativeCharacterPopulationObservation(
            characters=(_character("mob"),),
            selected_target_token="mob",
            player_action_target_token=None,
            scan_generation=9,
            rejected_candidates=0,
        )
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                use_native_population=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=StaticPvETargetAuthorityEvaluator(
                (_evidence("mob", relation=Relation.NEUTRAL),)
            ),
            require_verified_target_authority=True,
        )

        decision = controller.step(_observation(0, "mob", population=population))

        self.assertEqual(PvEPhase.SEEKING, decision.phase)
        self.assertNotEqual(PvEIntent.ATTACK_SELECTED_TARGET, decision.intent)
        rejection = controller.target_rejections[-1]
        self.assertEqual(
            PvETargetRejectionReason.TARGET_AUTHORITY_REJECTED,
            rejection.reason,
        )
        self.assertIn("relation_not_enemy", rejection.authority_exclusions)

    def test_engaged_target_losing_authority_stops_before_more_input(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=TimedAuthorityEvaluator(),
            require_verified_target_authority=True,
        )
        controller.step(_observation(0, None))
        controller.step(_observation(100, "mob"))

        stopped = controller.step(_observation(200, "mob"))

        self.assertEqual(PvEPhase.STOPPED, stopped.phase)
        self.assertEqual(
            "engaged_target_became_attack_ineligible",
            stopped.terminal_reason,
        )
        self.assertIsNone(stopped.intent)

    def test_authority_evaluator_is_opt_in_for_existing_profiles(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=StaticPvETargetAuthorityEvaluator(
                (_evidence("mob", relation=Relation.NEUTRAL),)
            ),
        )
        controller.step(_observation(0, None))

        attack = controller.step(_observation(100, "mob"))

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        self.assertEqual(PvEPhase.ENGAGED, attack.phase)
        assert controller.latest_target_authority is not None
        self.assertFalse(controller.latest_target_authority.accepted)


if __name__ == "__main__":
    unittest.main()
