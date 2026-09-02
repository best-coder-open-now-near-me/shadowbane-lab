import unittest

from shadowbane_lab.client_observation import (
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
)
from shadowbane_lab.client_observation.native_object import (
    NativeEntityBinding,
    NativeEntityIdentityMap,
    NativeObjectKey,
)
from shadowbane_lab.pve import (
    PvEAuthorityCharacterRecord,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
    PvETargetAuthorityExclusion,
    PvETargetAuthoritySnapshot,
    PvETargetCharacterKind,
    SnapshotPvETargetAuthorityEvaluator,
)
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    OwnershipEdge,
    legacy_team_affiliations,
)

_PLAYER_KEY = NativeObjectKey(10, 42)
_MOB_KEY = NativeObjectKey(20, 7001)


def _observation(now_ms: int, token: str | None) -> PvEObservation:
    target = (
        NativeTargetHealthObservation(target_present=False)
        if token is None
        else NativeTargetHealthObservation(
            target_present=True,
            current_health=10.0,
            maximum_health=10.0,
            target_token=token,
        )
    )
    identity = (
        NativeTargetIdentityObservation(target_present=False)
        if token is None
        else NativeTargetIdentityObservation(
            target_present=True,
            arc_character=True,
            merchant=False,
            shopkeeper=False,
            banker=False,
            trainer=False,
            minion=False,
            target_token=token,
        )
    )
    return PvEObservation(
        now_ms=now_ms,
        target=target,
        player=NativePlayerVitalsObservation(
            current_health=100.0,
            maximum_health=100.0,
            current_mana=50.0,
            maximum_mana=50.0,
            current_stamina=100.0,
            maximum_stamina=100.0,
        ),
        target_identity=identity,
    )


def _identities(*, include_mob: bool = True) -> NativeEntityIdentityMap:
    bindings = [NativeEntityBinding(_PLAYER_KEY, "player")]
    if include_mob:
        bindings.append(NativeEntityBinding(_MOB_KEY, "mob"))
    return NativeEntityIdentityMap(tuple(bindings))


def _record(
    *,
    kind: PvETargetCharacterKind = PvETargetCharacterKind.NPC,
    attackable: bool | None = True,
) -> PvEAuthorityCharacterRecord:
    return PvEAuthorityCharacterRecord(
        target_token="mob-token",
        object_key=_MOB_KEY,
        character_kind=kind,
        attackable=attackable,
        evidence_sources=("native_character_record",),
    )


def _opposing_sides(*extra: GroupMembership) -> AffiliationSnapshot:
    base = legacy_team_affiliations(
        {"player": "players", "mob": "monsters"},
        revision=11,
    )
    return AffiliationSnapshot(
        revision=base.revision,
        memberships=(*base.memberships, *extra),
        relation_overrides=base.relation_overrides,
    )


def _snapshot(
    *,
    identities: NativeEntityIdentityMap | None = None,
    affiliations: AffiliationSnapshot | None = None,
    record: PvEAuthorityCharacterRecord | None = None,
    party_complete: bool = True,
    ownership_complete: bool = True,
    relation_complete: bool = True,
) -> PvETargetAuthoritySnapshot:
    return PvETargetAuthoritySnapshot(
        revision=19,
        local_player_object_key=_PLAYER_KEY,
        identities=_identities() if identities is None else identities,
        affiliations=_opposing_sides() if affiliations is None else affiliations,
        characters=(_record() if record is None else record,),
        party_complete=party_complete,
        ownership_complete=ownership_complete,
        relation_complete=relation_complete,
        evidence_sources=("coherent_native_authority_snapshot",),
    )


class SnapshotPvETargetAuthorityTests(unittest.TestCase):
    def test_exact_identity_and_opposing_side_snapshot_accepts_hostile_npc(self) -> None:
        evaluator = SnapshotPvETargetAuthorityEvaluator(_snapshot())

        decision = evaluator.evaluate(_observation(100, "mob-token"))

        self.assertTrue(decision.accepted)
        self.assertEqual("verified_hostile_npc", decision.summary_reason)
        self.assertIn("native_entity_identity_map", decision.evidence_sources)
        self.assertIn(
            "complete_relation_affiliation_snapshot",
            decision.evidence_sources,
        )

    def test_same_party_is_rejected_even_when_relation_override_is_enemy(self) -> None:
        party = GroupKey(GroupKind.PARTY, "party-1")
        affiliations = _opposing_sides(
            GroupMembership("player", party),
            GroupMembership("mob", party),
        )
        evaluator = SnapshotPvETargetAuthorityEvaluator(
            _snapshot(affiliations=affiliations)
        )

        decision = evaluator.evaluate(_observation(100, "mob-token"))

        self.assertFalse(decision.accepted)
        self.assertIn(PvETargetAuthorityExclusion.PARTY_MEMBER, decision.exclusions)
        self.assertEqual("enemy", decision.relation.value)

    def test_incomplete_party_snapshot_never_defaults_to_not_grouped(self) -> None:
        evaluator = SnapshotPvETargetAuthorityEvaluator(
            _snapshot(party_complete=False)
        )

        decision = evaluator.evaluate(_observation(100, "mob-token"))

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.PARTY_STATUS_UNAVAILABLE,
            decision.exclusions,
        )

    def test_missing_entity_binding_withholds_relation_and_affiliation_claims(self) -> None:
        evaluator = SnapshotPvETargetAuthorityEvaluator(
            _snapshot(identities=_identities(include_mob=False))
        )

        decision = evaluator.evaluate(_observation(100, "mob-token"))

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.RELATION_UNAVAILABLE,
            decision.exclusions,
        )
        self.assertIn(
            PvETargetAuthorityExclusion.PARTY_STATUS_UNAVAILABLE,
            decision.exclusions,
        )
        self.assertIn(
            PvETargetAuthorityExclusion.OWNERSHIP_STATUS_UNAVAILABLE,
            decision.exclusions,
        )

    def test_owned_target_is_rejected_as_friendly(self) -> None:
        affiliations = AffiliationSnapshot(
            revision=11,
            ownership_edges=(OwnershipEdge("player", "mob"),),
        )
        evaluator = SnapshotPvETargetAuthorityEvaluator(
            _snapshot(affiliations=affiliations)
        )

        decision = evaluator.evaluate(_observation(100, "mob-token"))

        self.assertFalse(decision.accepted)
        self.assertIn(PvETargetAuthorityExclusion.FRIENDLY_OWNED, decision.exclusions)
        self.assertIn(
            PvETargetAuthorityExclusion.RELATION_NOT_ENEMY,
            decision.exclusions,
        )

    def test_player_character_record_is_never_admitted(self) -> None:
        evaluator = SnapshotPvETargetAuthorityEvaluator(
            _snapshot(record=_record(kind=PvETargetCharacterKind.PLAYER))
        )

        decision = evaluator.evaluate(_observation(100, "mob-token"))

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.CHARACTER_KIND_NOT_NPC,
            decision.exclusions,
        )

    def test_snapshot_evaluator_satisfies_strict_controller_contract(self) -> None:
        controller = PvEController(
            PvEControllerConfig(
                require_target_identity=True,
                acquisition_retry_ms=100,
                target_sample_interval_ms=100,
                acquisition_timeout_ms=1_000,
            ),
            target_authority_evaluator=SnapshotPvETargetAuthorityEvaluator(
                _snapshot()
            ),
            require_verified_target_authority=True,
        )
        controller.step(_observation(0, None))

        attack = controller.step(_observation(100, "mob-token"))

        self.assertEqual(PvEIntent.ATTACK_SELECTED_TARGET, attack.intent)
        assert controller.latest_target_authority is not None
        self.assertTrue(controller.latest_target_authority.accepted)

    def test_snapshot_serialization_preserves_completeness_and_bindings(self) -> None:
        payload = _snapshot().as_dict()

        self.assertEqual(19, payload["revision"])
        self.assertEqual(
            {"party": True, "ownership": True, "relation": True},
            payload["completeness"],
        )
        self.assertEqual(2, len(payload["identity_bindings"]))
        self.assertEqual("npc", payload["characters"][0]["character_kind"])


if __name__ == "__main__":
    unittest.main()
