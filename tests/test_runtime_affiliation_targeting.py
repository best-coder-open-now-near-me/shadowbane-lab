from __future__ import annotations

import unittest

from shadowbane_lab.protocol import EntityKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim.actions import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    AreaEffect,
    AreaOrigin,
    PhaseKind,
    RestoreResource,
    SubjectRef,
    TargetingSpec,
)
from shadowbane_lab.sim.affiliated_environment import AffiliatedReferenceEnvironment
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    RelationOverride,
    RelationSubject,
)
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.runtime_targeting import (
    AffiliationTargetConstraints,
    RuntimeTargetingProfile,
)
from shadowbane_lab.sim.state import EntityState


def _actor(
    entity_id: str,
    x: float,
    action_keys: tuple[str, ...] = (),
    *,
    team_id: str | None = "legacy-red",
    health: float = 5.0,
) -> EntityState:
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=Vector2(x, 0.0),
        scalars={"health": health, "mana": 10.0, "move_speed": 10.0},
        maximums={"health": 10.0, "mana": 10.0},
        action_keys=action_keys,
    )


def _party_snapshot(*, outsider_in_party: bool = False) -> AffiliationSnapshot:
    red = GroupKey(GroupKind.SCENARIO_SIDE, "red")
    blue = GroupKey(GroupKind.SCENARIO_SIDE, "blue")
    party = GroupKey(GroupKind.PARTY, "red-one")
    other_party = party if outsider_in_party else GroupKey(GroupKind.PARTY, "red-two")
    return AffiliationSnapshot(
        revision=7,
        memberships=(
            GroupMembership("healer", red),
            GroupMembership("healer", party, "leader"),
            GroupMembership("tank", red),
            GroupMembership("tank", party, "member"),
            GroupMembership("scout", red),
            GroupMembership("scout", other_party, "member"),
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


def _party_profile() -> RuntimeTargetingProfile:
    exact_party = AffiliationTargetConstraints(require_same_party=True)
    return RuntimeTargetingProfile(
        action_constraints=(("party-heal", exact_party),),
        area_constraints=(("party-wave", exact_party),),
    )


def _party_heal() -> ActionSpec:
    return ActionSpec(
        action_key="party-heal",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ALLY,),
            maximum_range=20.0,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(RestoreResource(SubjectRef.TARGET, "health", 2.0),),
            ),
        ),
    )


def _party_wave() -> ActionSpec:
    return ActionSpec(
        action_key="party-wave",
        targeting=TargetingSpec(kind=TargetKind.SELF),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(
                    AreaEffect(
                        origin=AreaOrigin.ACTOR,
                        radius=20.0,
                        allowed_relations=(Relation.SELF, Relation.ALLY),
                        effects=(RestoreResource(SubjectRef.TARGET, "health", 2.0),),
                    ),
                ),
            ),
        ),
    )


def _decision(
    environment: AffiliatedReferenceEnvironment,
    actor_id: str,
    action_key: str,
    *,
    target_id: str | None = None,
    correlation_id: str,
):
    exchange = environment.exchange(actor_id)
    matches = tuple(
        affordance
        for affordance in exchange.affordances.affordances
        if affordance.action_key == action_key
        and (target_id is None or affordance.binding.target_entity_id == target_id)
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one affordance, found {len(matches)}")
    return exchange.decision(matches[0].affordance_id, correlation_id)


class RuntimeAffiliationTargetingTests(unittest.TestCase):
    def test_party_only_direct_heal_excludes_friendly_outsider(self) -> None:
        environment = AffiliatedReferenceEnvironment(
            ActionCatalog((_party_heal(),)),
            (
                _actor("healer", 0.0, ("party-heal",)),
                _actor("tank", 3.0),
                _actor("scout", 2.0),
                _actor("enemy", 1.0),
            ),
            seed=1,
            affiliation_snapshot=_party_snapshot(),
            targeting_profile=_party_profile(),
        )

        exchange = environment.exchange("healer")
        targets = tuple(
            affordance.binding.target_entity_id
            for affordance in exchange.affordances.affordances
            if affordance.action_key == "party-heal"
        )
        resolution = environment.resolve_targets("healer", "party-heal")
        decisions = {decision.entity_id: decision for decision in resolution.decisions}

        self.assertEqual(("tank",), targets)
        self.assertEqual(("not_same_party",), decisions["scout"].exclusion_reasons)
        self.assertEqual(Relation.ENEMY, decisions["enemy"].coarse_relation)
        self.assertEqual(7, resolution.affiliation_revision)

    def test_direct_and_area_paths_use_the_same_exact_party_constraint(self) -> None:
        environment = AffiliatedReferenceEnvironment(
            ActionCatalog((_party_heal(), _party_wave())),
            (
                _actor("healer", 0.0, ("party-heal", "party-wave")),
                _actor("tank", 3.0),
                _actor("scout", 2.0),
                _actor("enemy", 1.0),
            ),
            seed=2,
            affiliation_snapshot=_party_snapshot(),
            targeting_profile=_party_profile(),
        )

        environment.step(
            (
                _decision(
                    environment,
                    "healer",
                    "party-wave",
                    correlation_id="wave",
                ),
            )
        )

        self.assertEqual(7.0, environment.entity("healer").scalars["health"])
        self.assertEqual(7.0, environment.entity("tank").scalars["health"])
        self.assertEqual(5.0, environment.entity("scout").scalars["health"])
        self.assertEqual(5.0, environment.entity("enemy").scalars["health"])
        self.assertEqual(
            ("tank",),
            tuple(
                affordance.binding.target_entity_id
                for affordance in environment.exchange("healer").affordances.affordances
                if affordance.action_key == "party-heal"
            ),
        )

    def test_required_line_of_sight_fails_closed_without_provider(self) -> None:
        attack = ActionSpec(
            action_key="los-attack",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
                requires_line_of_sight=True,
            ),
            phases=(ActionPhase(kind=PhaseKind.ACTIVE, duration_ms=0),),
        )
        entities = (
            _actor("attacker", 0.0, ("los-attack",), team_id="red"),
            _actor("target", 1.0, team_id="blue"),
        )
        unavailable = AffiliatedReferenceEnvironment(
            ActionCatalog((attack,)),
            entities,
            seed=3,
        )
        available = AffiliatedReferenceEnvironment(
            ActionCatalog((attack,)),
            entities,
            seed=3,
            line_of_sight_provider=lambda _actor, _target: True,
        )

        self.assertEqual((), unavailable.exchange("attacker").affordances.affordances)
        resolution = unavailable.resolve_targets("attacker", "los-attack")
        decisions = {decision.entity_id: decision for decision in resolution.decisions}
        self.assertEqual(
            ("line_of_sight_blocked",),
            decisions["target"].exclusion_reasons,
        )
        self.assertEqual(1, len(available.exchange("attacker").affordances.affordances))

    def test_snapshot_restore_is_bound_to_affiliation_digest_and_revision(self) -> None:
        catalog = ActionCatalog((_party_heal(),))
        entities = (
            _actor("healer", 0.0, ("party-heal",)),
            _actor("tank", 3.0),
            _actor("scout", 2.0),
            _actor("enemy", 1.0),
        )
        original = AffiliatedReferenceEnvironment(
            catalog,
            entities,
            seed=4,
            affiliation_snapshot=_party_snapshot(),
            targeting_profile=_party_profile(),
        )
        changed = AffiliatedReferenceEnvironment(
            catalog,
            entities,
            seed=4,
            affiliation_snapshot=_party_snapshot(outsider_in_party=True),
            targeting_profile=_party_profile(),
        )
        snapshot = original.snapshot()

        original.restore(snapshot)
        with self.assertRaisesRegex(SimulationConfigurationError, "digest"):
            changed.restore(snapshot)

    def test_affiliation_snapshot_cannot_reference_an_absent_entity(self) -> None:
        snapshot = AffiliationSnapshot(
            memberships=(
                GroupMembership(
                    "missing",
                    GroupKey(GroupKind.PARTY, "party"),
                ),
            )
        )
        with self.assertRaisesRegex(SimulationConfigurationError, "unknown entities"):
            AffiliatedReferenceEnvironment(
                ActionCatalog((_party_heal(),)),
                (_actor("healer", 0.0, ("party-heal",)),),
                seed=5,
                affiliation_snapshot=snapshot,
            )


if __name__ == "__main__":
    unittest.main()
