import unittest

from shadowbane_lab.protocol import EntityKind, Relation, Vector2
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    OwnershipEdge,
    RelationOverride,
    RelationResolver,
    RelationSubject,
    legacy_team_affiliations,
)
from shadowbane_lab.sim.targeting import (
    AliveRequirement,
    TargetCandidate,
    TargetOrder,
    TargetResolver,
    TargetSelectorSpec,
    VisibilityRequirement,
)


def _candidate(
    entity_id: str,
    x: float,
    *,
    kind: EntityKind = EntityKind.ACTOR,
    alive: bool = True,
    visible: bool = True,
    line_of_sight: bool = True,
) -> TargetCandidate:
    return TargetCandidate(
        entity_id=entity_id,
        kind=kind,
        position=Vector2(x, 0.0),
        alive=alive,
        visible_to_actor=visible,
        line_of_sight=line_of_sight,
    )


class PartyTargetingTests(unittest.TestCase):
    def test_party_only_heal_excludes_friendly_outsider(self) -> None:
        red = GroupKey(GroupKind.SCENARIO_SIDE, "side:red")
        blue = GroupKey(GroupKind.SCENARIO_SIDE, "side:blue")
        party_one = GroupKey(GroupKind.PARTY, "party:red-1")
        party_two = GroupKey(GroupKind.PARTY, "party:red-2")
        snapshot = AffiliationSnapshot(
            memberships=(
                GroupMembership("healer", red),
                GroupMembership("healer", party_one),
                GroupMembership("tank", red),
                GroupMembership("tank", party_one),
                GroupMembership("scout", red),
                GroupMembership("scout", party_two),
                GroupMembership("enemy", blue),
            ),
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_group(red),
                    RelationSubject.for_group(blue),
                    Relation.ENEMY,
                ),
            ),
        )
        resolver = TargetResolver(RelationResolver(snapshot))
        result = resolver.resolve(
            _candidate("healer", 0.0),
            (
                _candidate("scout", 4.0),
                _candidate("enemy", 3.0),
                _candidate("tank", 5.0),
            ),
            TargetSelectorSpec(
                entity_kinds=(EntityKind.ACTOR,),
                allowed_relations=(Relation.SELF, Relation.ALLY),
                require_same_party=True,
                maximum_range=20.0,
            ),
        )

        self.assertEqual(("tank",), result.accepted_entity_ids)
        decisions = {decision.entity_id: decision for decision in result.decisions}
        self.assertEqual(("not_same_party",), decisions["scout"].exclusion_reasons)
        self.assertEqual(
            ("not_same_party", "relation_not_allowed"),
            decisions["enemy"].exclusion_reasons,
        )
        self.assertTrue(decisions["tank"].relation_facts.same_party)

    def test_hostile_selector_uses_declared_opposing_side(self) -> None:
        snapshot = legacy_team_affiliations(
            {
                "actor": "red",
                "enemy": "blue",
                "neutral": None,
            }
        )
        result = TargetResolver(RelationResolver(snapshot)).resolve(
            _candidate("actor", 0.0),
            (_candidate("neutral", 2.0), _candidate("enemy", 4.0)),
            TargetSelectorSpec(
                allowed_relations=(Relation.ENEMY,),
                require_opposing_scenario_side=True,
            ),
        )

        self.assertEqual(("enemy",), result.accepted_entity_ids)
        neutral = next(decision for decision in result.decisions if decision.entity_id == "neutral")
        self.assertEqual(
            ("not_opposing_scenario_side", "relation_not_allowed"),
            neutral.exclusion_reasons,
        )


class OwnershipTargetingTests(unittest.TestCase):
    def test_owner_family_selector_accepts_pet_and_rejects_unrelated_actor(self) -> None:
        snapshot = AffiliationSnapshot(ownership_edges=(OwnershipEdge("summoner", "pet"),))
        result = TargetResolver(RelationResolver(snapshot)).resolve(
            _candidate("summoner", 0.0),
            (
                _candidate("stranger", 1.0),
                _candidate("pet", 2.0, kind=EntityKind.PET),
            ),
            TargetSelectorSpec(
                entity_kinds=(EntityKind.PET, EntityKind.ACTOR),
                allowed_relations=(Relation.ALLY,),
                require_same_ownership_family=True,
            ),
        )

        self.assertEqual(("pet",), result.accepted_entity_ids)
        stranger = next(
            decision for decision in result.decisions if decision.entity_id == "stranger"
        )
        self.assertEqual(
            ("not_same_ownership_family", "relation_not_allowed"),
            stranger.exclusion_reasons,
        )

    def test_direct_owner_requirement_is_directional(self) -> None:
        snapshot = AffiliationSnapshot(ownership_edges=(OwnershipEdge("summoner", "pet"),))
        resolver = TargetResolver(RelationResolver(snapshot))
        owner_to_pet = resolver.resolve(
            _candidate("summoner", 0.0),
            (_candidate("pet", 1.0, kind=EntityKind.PET),),
            TargetSelectorSpec(require_actor_owns_target=True),
        )
        pet_to_owner = resolver.resolve(
            _candidate("pet", 1.0, kind=EntityKind.PET),
            (_candidate("summoner", 0.0),),
            TargetSelectorSpec(require_actor_owns_target=True),
        )

        self.assertEqual(("pet",), owner_to_pet.accepted_entity_ids)
        self.assertEqual((), pet_to_owner.accepted_entity_ids)
        self.assertEqual(
            ("actor_does_not_own_target",),
            pet_to_owner.decisions[0].exclusion_reasons,
        )


class OverrideTargetingTests(unittest.TestCase):
    def test_explicit_neutrality_is_available_to_selector(self) -> None:
        snapshot = AffiliationSnapshot(
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_entity("actor"),
                    RelationSubject.for_entity("visitor"),
                    Relation.NEUTRAL,
                ),
            )
        )
        result = TargetResolver(RelationResolver(snapshot)).resolve(
            _candidate("actor", 0.0),
            (_candidate("visitor", 1.0),),
            TargetSelectorSpec(allowed_relations=(Relation.NEUTRAL,)),
        )

        self.assertEqual(("visitor",), result.accepted_entity_ids)
        self.assertTrue(result.decisions[0].relation_facts.explicit_neutrality)


class DeterministicResolutionTests(unittest.TestCase):
    def test_distance_order_and_target_cap_are_deterministic(self) -> None:
        snapshot = legacy_team_affiliations(
            {
                "actor": "red",
                "alpha": "blue",
                "bravo": "blue",
                "charlie": "blue",
            }
        )
        result = TargetResolver(RelationResolver(snapshot)).resolve(
            _candidate("actor", 0.0),
            (
                _candidate("charlie", 8.0),
                _candidate("bravo", 3.0),
                _candidate("alpha", 3.0),
            ),
            TargetSelectorSpec(
                allowed_relations=(Relation.ENEMY,),
                maximum_targets=2,
                order=TargetOrder.DISTANCE_THEN_ENTITY_ID,
            ),
        )

        self.assertEqual(
            ("alpha", "bravo", "charlie"),
            tuple(decision.entity_id for decision in result.decisions),
        )
        self.assertEqual(("alpha", "bravo"), result.accepted_entity_ids)
        self.assertEqual(
            ("target_cap_exceeded",),
            result.decisions[2].exclusion_reasons,
        )
        self.assertEqual((("target_cap_exceeded", 1),), result.rejection_counts)

    def test_diagnostics_cover_kind_life_visibility_range_and_los(self) -> None:
        snapshot = legacy_team_affiliations(
            {
                "actor": "red",
                "wrong_kind": "blue",
                "dead": "blue",
                "hidden": "blue",
                "far": "blue",
                "blocked": "blue",
            }
        )
        result = TargetResolver(RelationResolver(snapshot)).resolve(
            _candidate("actor", 0.0),
            (
                _candidate("wrong_kind", 1.0, kind=EntityKind.STRUCTURE),
                _candidate("dead", 2.0, alive=False),
                _candidate("hidden", 3.0, visible=False),
                _candidate("far", 30.0),
                _candidate("blocked", 4.0, line_of_sight=False),
            ),
            TargetSelectorSpec(
                entity_kinds=(EntityKind.ACTOR,),
                allowed_relations=(Relation.ENEMY,),
                alive_requirement=AliveRequirement.ALIVE,
                visibility_requirement=VisibilityRequirement.VISIBLE,
                maximum_range=10.0,
                requires_line_of_sight=True,
            ),
        )
        reasons = {decision.entity_id: decision.exclusion_reasons for decision in result.decisions}

        self.assertEqual(("entity_kind_not_allowed",), reasons["wrong_kind"])
        self.assertEqual(("target_not_alive",), reasons["dead"])
        self.assertEqual(("not_visible",), reasons["hidden"])
        self.assertEqual(("outside_maximum_range",), reasons["far"])
        self.assertEqual(("line_of_sight_blocked",), reasons["blocked"])
        self.assertEqual(1, result.affiliation_revision)


class TargetSelectorValidationTests(unittest.TestCase):
    def test_contradictory_affiliation_requirements_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "same_party"):
            TargetSelectorSpec(require_same_party=True, forbid_same_party=True)
        with self.assertRaisesRegex(ValueError, "same and an opposing"):
            TargetSelectorSpec(
                require_same_scenario_side=True,
                require_opposing_scenario_side=True,
            )
        with self.assertRaisesRegex(ValueError, "mutual ownership"):
            TargetSelectorSpec(
                require_actor_owns_target=True,
                require_target_owns_actor=True,
            )


if __name__ == "__main__":
    unittest.main()
