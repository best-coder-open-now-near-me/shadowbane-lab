import json
import unittest
from importlib.resources import files

from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.rulesets import load_ruleset_text
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    AreaEffect,
    AreaOrigin,
    AttackGate,
    AttackKind,
    ChangeStance,
    CombatStance,
    DealDamage,
    EntityState,
    ModifyTag,
    PhaseKind,
    ReferenceEnvironment,
    SubjectRef,
    TagOperation,
    TargetingSpec,
)


def _actor(
    entity_id: str,
    team_id: str,
    position: Vector2,
    action_keys: tuple[str, ...] = (),
) -> EntityState:
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=position,
        scalars={"health": 100.0},
        maximums={"health": 100.0},
        action_keys=action_keys,
    )


def _decision(
    environment: ReferenceEnvironment,
    actor_id: str,
    action_key: str,
    *,
    correlation_id: str,
):
    exchange = environment.exchange(actor_id)
    matches = tuple(
        item
        for item in exchange.affordances.affordances
        if item.action_key == action_key
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one {action_key} affordance, found {len(matches)}")
    return exchange.decision(matches[0].affordance_id, correlation_id)


class StanceRuntimeTests(unittest.TestCase):
    def test_stances_are_mutually_exclusive_snapshot_state_and_travel_drops_on_damage(
        self,
    ) -> None:
        travel = ActionSpec(
            action_key="stance.travel",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(ChangeStance(SubjectRef.ACTOR, CombatStance.TRAVEL),),
                ),
            ),
        )
        strike = ActionSpec(
            action_key="strike",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(DealDamage(SubjectRef.TARGET, 5.0, "crush"),),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((travel, strike)),
            (
                _actor("traveler", "red", Vector2(0.0, 0.0), ("stance.travel",)),
                _actor("attacker", "blue", Vector2(1.0, 0.0), ("strike",)),
            ),
            seed=3,
        )

        entered = environment.step(
            (_decision(environment, "traveler", "stance.travel", correlation_id="travel"),)
        )
        snapshot = environment.snapshot()

        self.assertIs(CombatStance.TRAVEL, environment.entity("traveler").stance)
        self.assertIn("stance.travel", environment.entity("traveler").effective_tags)
        self.assertNotIn("stance.normal", environment.entity("traveler").effective_tags)
        self.assertTrue(
            any(event.kind == EventKind.STANCE_CHANGED for event in entered.events)
        )

        damaged = environment.step(
            (_decision(environment, "attacker", "strike", correlation_id="damage"),)
        )

        traveler = environment.entity("traveler")
        self.assertIs(CombatStance.NORMAL, traveler.stance)
        self.assertIn("stance.normal", traveler.effective_tags)
        self.assertNotIn("stance.travel", traveler.effective_tags)
        dropped = next(
            event for event in damaged.events if event.kind == EventKind.STANCE_CHANGED
        )
        self.assertIn("reason.damage", dropped.tags)

        environment.restore(snapshot)
        self.assertIs(CombatStance.TRAVEL, environment.entity("traveler").stance)

    def test_change_stance_rejects_non_actor_subjects(self) -> None:
        with self.assertRaisesRegex(ValueError, "actor subject"):
            ChangeStance(SubjectRef.TARGET, CombatStance.DEFENSIVE)

    def test_unavoided_power_hit_drops_travel_before_a_non_damage_effect(self) -> None:
        mark = ActionSpec(
            action_key="mark",
            targeting=TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=3.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        AttackGate(
                            attack_key="mark",
                            kind=AttackKind.POWER,
                            attack_rating_key="attack.mark",
                            defense_rating_key="defense",
                            effects=(
                                ModifyTag(
                                    SubjectRef.TARGET,
                                    "marked",
                                    TagOperation.ADD,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        attacker = _actor("attacker", "blue", Vector2(0.0, 0.0), ("mark",))
        attacker.scalars["attack.mark"] = 1_000.0
        traveler = _actor("traveler", "red", Vector2(1.0, 0.0))
        traveler.scalars["defense"] = 0.0
        traveler.stance = CombatStance.TRAVEL
        environment = ReferenceEnvironment(
            ActionCatalog((mark,)),
            (attacker, traveler),
            seed=3,
        )

        result = environment.step(
            (_decision(environment, "attacker", "mark", correlation_id="mark"),)
        )

        self.assertIs(CombatStance.NORMAL, environment.entity("traveler").stance)
        self.assertIn("marked", environment.entity("traveler").effective_tags)
        dropped = next(
            event for event in result.events if event.kind == EventKind.STANCE_CHANGED
        )
        self.assertIn("reason.hit", dropped.tags)


class AreaRuntimeTests(unittest.TestCase):
    def test_actor_centered_area_hits_only_matching_relations_inside_radius(self) -> None:
        pulse = ActionSpec(
            action_key="self-pulse",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        AreaEffect(
                            origin=AreaOrigin.ACTOR,
                            radius=3.0,
                            allowed_relations=(Relation.ENEMY,),
                            effects=(
                                DealDamage(SubjectRef.TARGET, 10.0, "mental"),
                            ),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((pulse,)),
            (
                _actor("caster", "red", Vector2(0.0, 0.0), ("self-pulse",)),
                _actor("ally", "red", Vector2(1.0, 0.0)),
                _actor("near-a", "blue", Vector2(1.0, 0.0)),
                _actor("near-b", "blue", Vector2(3.0, 0.0)),
                _actor("far", "blue", Vector2(3.1, 0.0)),
            ),
            seed=5,
        )

        result = environment.step(
            (_decision(environment, "caster", "self-pulse", correlation_id="pulse"),)
        )

        self.assertEqual(90.0, environment.entity("near-a").scalars["health"])
        self.assertEqual(90.0, environment.entity("near-b").scalars["health"])
        self.assertEqual(100.0, environment.entity("ally").scalars["health"])
        self.assertEqual(100.0, environment.entity("far").scalars["health"])
        self.assertEqual(
            ("near-a", "near-b"),
            tuple(
                event.target_entity_id
                for event in result.events
                if event.kind == EventKind.DAMAGE_APPLIED
            ),
        )

    def test_area_attack_gate_resolves_separately_for_each_victim(self) -> None:
        pulse = ActionSpec(
            action_key="checked-pulse",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        AreaEffect(
                            origin=AreaOrigin.ACTOR,
                            radius=3.0,
                            allowed_relations=(Relation.ENEMY,),
                            effects=(
                                AttackGate(
                                    attack_key="checked-pulse",
                                    kind=AttackKind.POWER,
                                    attack_rating_key="attack.checked-pulse",
                                    defense_rating_key="defense",
                                    effects=(
                                        DealDamage(
                                            SubjectRef.TARGET,
                                            10.0,
                                            "mental",
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        caster = _actor("caster", "red", Vector2(0.0, 0.0), ("checked-pulse",))
        caster.scalars["attack.checked-pulse"] = 1_000.0
        first = _actor("first", "blue", Vector2(1.0, 0.0))
        second = _actor("second", "blue", Vector2(2.0, 0.0))
        first.scalars["defense"] = 0.0
        second.scalars["defense"] = 0.0
        environment = ReferenceEnvironment(
            ActionCatalog((pulse,)),
            (caster, first, second),
            seed=3,
        )

        result = environment.step(
            (_decision(environment, "caster", "checked-pulse", correlation_id="pulse"),)
        )

        resolved = tuple(
            event for event in result.events if event.kind == EventKind.ATTACK_RESOLVED
        )
        self.assertEqual(("first", "second"), tuple(event.target_entity_id for event in resolved))
        self.assertEqual(90.0, environment.entity("first").scalars["health"])
        self.assertEqual(90.0, environment.entity("second").scalars["health"])

    def test_target_area_uses_bound_position_and_deterministic_target_cap(self) -> None:
        blast = ActionSpec(
            action_key="ground-blast",
            targeting=TargetingSpec(
                kind=TargetKind.POSITION,
                maximum_range=50.0,
            ),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        AreaEffect(
                            origin=AreaOrigin.TARGET,
                            radius=2.0,
                            allowed_relations=(Relation.ENEMY,),
                            maximum_targets=2,
                            effects=(DealDamage(SubjectRef.TARGET, 7.0, "fire"),),
                        ),
                    ),
                ),
            ),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((blast,)),
            (
                _actor("caster", "red", Vector2(0.0, 0.0), ("ground-blast",)),
                _actor("center", "blue", Vector2(10.0, 0.0)),
                _actor("near", "blue", Vector2(11.0, 0.0)),
                _actor("third", "blue", Vector2(8.5, 0.0)),
                _actor("outside", "blue", Vector2(12.1, 0.0)),
            ),
            seed=7,
            position_candidates=(Vector2(10.0, 0.0),),
        )

        result = environment.step(
            (_decision(environment, "caster", "ground-blast", correlation_id="blast"),)
        )

        self.assertEqual(93.0, environment.entity("center").scalars["health"])
        self.assertEqual(93.0, environment.entity("near").scalars["health"])
        self.assertEqual(100.0, environment.entity("third").scalars["health"])
        self.assertEqual(100.0, environment.entity("outside").scalars["health"])
        self.assertEqual(
            ("center", "near"),
            tuple(
                event.target_entity_id
                for event in result.events
                if event.kind == EventKind.DAMAGE_APPLIED
            ),
        )

    def test_area_origin_and_action_targeting_must_agree(self) -> None:
        area = AreaEffect(
            origin=AreaOrigin.ACTOR,
            radius=3.0,
            allowed_relations=(Relation.ENEMY,),
            effects=(DealDamage(SubjectRef.TARGET, 1.0, "magic"),),
        )
        with self.assertRaisesRegex(ValueError, "self targeting"):
            ActionSpec(
                action_key="invalid-self-area",
                targeting=TargetingSpec(
                    kind=TargetKind.POSITION,
                    maximum_range=10.0,
                ),
                phases=(ActionPhase(PhaseKind.ACTIVE, 0, effects=(area,)),),
            )


class StanceAndAreaLoaderTests(unittest.TestCase):
    def test_ruleset_loader_preserves_explicit_stance_and_area_semantics(self) -> None:
        resource = files("shadowbane_lab.rulesets").joinpath(
            "data/shadowbane_vertical_slice_v1.json"
        )
        source = json.loads(resource.read_text(encoding="utf-8"))
        movement = source["actions"][0]
        movement["spec"]["targeting"] = {
            "kind": "self",
            "allowed_relations": [],
            "minimum_range": 0,
            "maximum_range": None,
            "requires_line_of_sight": False,
        }
        movement["spec"]["phases"][0]["effects"] = [
            {
                "op": "change_stance",
                "subject": "actor",
                "stance": "precise",
            },
            {
                "op": "area_effect",
                "origin": "actor",
                "radius": 12,
                "allowed_relations": ["enemy"],
                "maximum_targets": None,
                "effects": [
                    {
                        "op": "deal_damage",
                        "subject": "target",
                        "amount": 4,
                        "damage_type": "magic",
                    }
                ],
            },
        ]

        action = load_ruleset_text(json.dumps(source)).record("shadowbane.move").action

        self.assertIsNotNone(action)
        assert action is not None
        stance, area = action.phases[0].effects
        self.assertEqual(
            ChangeStance(SubjectRef.ACTOR, CombatStance.PRECISE),
            stance,
        )
        self.assertIsInstance(area, AreaEffect)
        assert isinstance(area, AreaEffect)
        self.assertIs(AreaOrigin.ACTOR, area.origin)
        self.assertEqual(12.0, area.radius)
        self.assertEqual((Relation.ENEMY,), area.allowed_relations)


if __name__ == "__main__":
    unittest.main()
