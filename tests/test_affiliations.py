import unittest

from shadowbane_lab.protocol import Relation
from shadowbane_lab.sim.affiliations import (
    AffiliationConfigurationError,
    AffiliationConflictError,
    AffiliationSnapshot,
    DefaultRelationPolicy,
    GroupKey,
    GroupKind,
    GroupMembership,
    OwnershipEdge,
    RelationOverride,
    RelationResolver,
    RelationSubject,
    legacy_team_affiliations,
)


class AffiliationFactsTests(unittest.TestCase):
    def test_same_side_and_party_are_independent_facts(self) -> None:
        side = GroupKey(GroupKind.SCENARIO_SIDE, "side:red")
        party_one = GroupKey(GroupKind.PARTY, "party:red-1")
        party_two = GroupKey(GroupKind.PARTY, "party:red-2")
        snapshot = AffiliationSnapshot(
            memberships=(
                GroupMembership("healer", side),
                GroupMembership("healer", party_one),
                GroupMembership("tank", side),
                GroupMembership("tank", party_one),
                GroupMembership("scout", side),
                GroupMembership("scout", party_two),
            )
        )
        resolver = RelationResolver(snapshot)

        tank = resolver.facts_between("healer", "tank")
        scout = resolver.facts_between("healer", "scout")

        self.assertTrue(tank.same_party)
        self.assertTrue(tank.same_scenario_side)
        self.assertFalse(scout.same_party)
        self.assertTrue(scout.same_scenario_side)
        self.assertEqual(Relation.ALLY, resolver.coarse_relation("healer", "scout"))

    def test_ownership_is_directed_transitive_and_cycle_safe(self) -> None:
        snapshot = AffiliationSnapshot(
            ownership_edges=(
                OwnershipEdge("summoner", "pet"),
                OwnershipEdge("pet", "pet_spell"),
                OwnershipEdge("summoner", "second_pet"),
            )
        )
        resolver = RelationResolver(snapshot)

        descendant = resolver.facts_between("summoner", "pet_spell")
        siblings = resolver.facts_between("pet", "second_pet")

        self.assertTrue(descendant.left_owns_right)
        self.assertFalse(descendant.right_owns_left)
        self.assertTrue(descendant.same_ownership_family)
        self.assertTrue(siblings.same_owner)
        self.assertTrue(siblings.same_ownership_family)
        self.assertEqual(
            Relation.ALLY,
            resolver.coarse_relation("summoner", "pet_spell"),
        )

        with self.assertRaisesRegex(AffiliationConfigurationError, "cycle"):
            AffiliationSnapshot(
                ownership_edges=(
                    OwnershipEdge("one", "two"),
                    OwnershipEdge("two", "one"),
                )
            )

    def test_policy_does_not_assume_guild_or_nation_friendship(self) -> None:
        guild = GroupKey(GroupKind.GUILD, "guild:one")
        nation = GroupKey(GroupKind.NATION, "nation:one")
        snapshot = AffiliationSnapshot(
            memberships=(
                GroupMembership("left", guild),
                GroupMembership("right", guild),
                GroupMembership("left", nation),
                GroupMembership("right", nation),
            )
        )
        resolver = RelationResolver(snapshot)
        facts = resolver.facts_between("left", "right")

        self.assertTrue(facts.same_guild)
        self.assertTrue(facts.same_nation)
        self.assertEqual(Relation.NEUTRAL, resolver.coarse_relation("left", "right"))
        self.assertEqual(
            Relation.ALLY,
            resolver.coarse_relation(
                "left",
                "right",
                DefaultRelationPolicy(same_nation_is_ally=True),
            ),
        )


class RelationOverrideTests(unittest.TestCase):
    def test_more_specific_overrides_take_precedence(self) -> None:
        red = GroupKey(GroupKind.SCENARIO_SIDE, "side:red")
        blue = GroupKey(GroupKind.SCENARIO_SIDE, "side:blue")
        snapshot = AffiliationSnapshot(
            memberships=(
                GroupMembership("red_player", red),
                GroupMembership("blue_player", blue),
                GroupMembership("blue_friend", blue),
            ),
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_group(red),
                    RelationSubject.for_group(blue),
                    Relation.ENEMY,
                ),
                RelationOverride(
                    RelationSubject.for_entity("red_player"),
                    RelationSubject.for_group(blue),
                    Relation.NEUTRAL,
                ),
                RelationOverride(
                    RelationSubject.for_entity("red_player"),
                    RelationSubject.for_entity("blue_friend"),
                    Relation.ALLY,
                ),
            ),
        )
        resolver = RelationResolver(snapshot)

        neutral = resolver.facts_between("red_player", "blue_player")
        ally = resolver.facts_between("red_player", "blue_friend")

        self.assertTrue(neutral.explicit_neutrality)
        self.assertEqual(3, neutral.override_precedence)
        self.assertEqual(Relation.NEUTRAL, resolver.coarse_relation("red_player", "blue_player"))
        self.assertEqual(4, ally.override_precedence)
        self.assertEqual(Relation.ALLY, resolver.coarse_relation("red_player", "blue_friend"))

    def test_equal_precedence_conflicts_fail_snapshot_compilation(self) -> None:
        red = GroupKey(GroupKind.SCENARIO_SIDE, "side:red")
        guild = GroupKey(GroupKind.GUILD, "guild:blue")

        with self.assertRaisesRegex(AffiliationConflictError, "equally specific"):
            AffiliationSnapshot(
                memberships=(
                    GroupMembership("left", red),
                    GroupMembership("right", guild),
                ),
                relation_overrides=(
                    RelationOverride(
                        RelationSubject.for_group(red),
                        RelationSubject.for_group(guild),
                        Relation.ALLY,
                    ),
                    RelationOverride(
                        RelationSubject.for_group(red),
                        RelationSubject.for_group(guild),
                        Relation.ENEMY,
                        symmetric=False,
                    ),
                ),
            )

    def test_directed_override_applies_only_in_declared_direction(self) -> None:
        snapshot = AffiliationSnapshot(
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_entity("guard"),
                    RelationSubject.for_entity("intruder"),
                    Relation.ENEMY,
                    symmetric=False,
                ),
            )
        )
        resolver = RelationResolver(snapshot)

        self.assertEqual(Relation.ENEMY, resolver.coarse_relation("guard", "intruder"))
        self.assertEqual(Relation.NEUTRAL, resolver.coarse_relation("intruder", "guard"))


class AffiliationValidationTests(unittest.TestCase):
    def test_one_entity_cannot_join_two_groups_of_same_kind(self) -> None:
        with self.assertRaisesRegex(AffiliationConfigurationError, "same kind"):
            AffiliationSnapshot(
                memberships=(
                    GroupMembership(
                        "member",
                        GroupKey(GroupKind.PARTY, "party:one"),
                    ),
                    GroupMembership(
                        "member",
                        GroupKey(GroupKind.PARTY, "party:two"),
                    ),
                )
            )

    def test_owned_entity_cannot_have_multiple_direct_owners(self) -> None:
        with self.assertRaisesRegex(AffiliationConfigurationError, "multiple direct owners"):
            AffiliationSnapshot(
                ownership_edges=(
                    OwnershipEdge("one", "pet"),
                    OwnershipEdge("two", "pet"),
                )
            )

    def test_identical_override_endpoints_cannot_disagree(self) -> None:
        left = RelationSubject.for_entity("left")
        right = RelationSubject.for_entity("right")
        with self.assertRaisesRegex(AffiliationConflictError, "identical endpoints"):
            AffiliationSnapshot(
                relation_overrides=(
                    RelationOverride(left, right, Relation.ALLY),
                    RelationOverride(right, left, Relation.ENEMY),
                )
            )


class LegacyTeamCompatibilityTests(unittest.TestCase):
    def test_legacy_team_adapter_reproduces_old_relation_rules(self) -> None:
        snapshot = legacy_team_affiliations(
            {
                "red_one": "red",
                "red_two": "red",
                "blue": "blue",
                "unassigned": None,
            }
        )
        resolver = RelationResolver(snapshot)

        self.assertEqual(Relation.SELF, resolver.coarse_relation("red_one", "red_one"))
        self.assertEqual(Relation.ALLY, resolver.coarse_relation("red_one", "red_two"))
        self.assertEqual(Relation.ENEMY, resolver.coarse_relation("red_one", "blue"))
        self.assertEqual(Relation.NEUTRAL, resolver.coarse_relation("red_one", "unassigned"))
        self.assertTrue(resolver.facts_between("red_one", "blue").opposing_scenario_side)


if __name__ == "__main__":
    unittest.main()
