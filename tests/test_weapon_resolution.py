import unittest

from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ActionTriggerSpec,
    ActiveEffectState,
    ApplyEffect,
    AttackModifierSpec,
    DealDamage,
    EntityState,
    ModifyTag,
    PhaseKind,
    ReferenceEnvironment,
    RemoveEffect,
    SubjectRef,
    TagOperation,
    TargetingSpec,
    TriggerConsumption,
    TriggerMoment,
    WeaponAttackSpec,
)


def actor(
    entity_id: str,
    team_id: str,
    action_keys: tuple[str, ...],
    *,
    health: float = 500.0,
    scalars: dict[str, float] | None = None,
    effects: dict[str, ActiveEffectState] | None = None,
    tags: set[str] | None = None,
) -> EntityState:
    values = {"health": health, "mana": 100.0, "stamina": 100.0, "move_speed": 10.0}
    values.update(scalars or {})
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=Vector2(0.0 if team_id == "red" else 1.0, 0.0),
        scalars=values,
        maximums={"health": health, "mana": 100.0, "stamina": 100.0},
        tags=tags or set(),
        action_keys=action_keys,
        effects=effects or {},
    )


def decision(
    environment: ReferenceEnvironment,
    actor_id: str,
    action_key: str,
    *,
    target_id: str | None = None,
    correlation_id: str,
):
    exchange = environment.exchange(actor_id)
    candidates = [
        item
        for item in exchange.affordances.affordances
        if item.action_key == action_key
        and (target_id is None or item.binding.target_entity_id == target_id)
    ]
    if len(candidates) != 1:
        raise AssertionError(f"expected one affordance, found {len(candidates)}")
    return exchange.decision(candidates[0].affordance_id, correlation_id)


def weapon_action(
    action_key: str = "swing",
    *,
    minimum_hit_chance: float = 1.0,
    maximum_hit_chance: float = 1.0,
) -> ActionSpec:
    return ActionSpec(
        action_key=action_key,
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=3.0,
        ),
        phases=(ActionPhase(kind=PhaseKind.ACTIVE, duration_ms=0),),
        weapon_attack=WeaponAttackSpec(
            weapon_slot="main_hand",
            damage_type="physical",
            minimum_damage=10.0,
            maximum_damage=10.0,
            minimum_hit_chance=minimum_hit_chance,
            maximum_hit_chance=maximum_hit_chance,
        ),
        tags=("attack", "weapon", "melee", "physical"),
    )


class WeaponResolutionTests(unittest.TestCase):
    def test_attack_roll_can_miss_without_applying_damage(self) -> None:
        swing = weapon_action(minimum_hit_chance=0.0, maximum_hit_chance=0.0)
        environment = ReferenceEnvironment(
            ActionCatalog((swing,)),
            (
                actor("a", "red", ("swing",)),
                actor("b", "blue", ()),
            ),
            seed=1,
        )

        batch = environment.step(
            (decision(environment, "a", "swing", target_id="b", correlation_id="miss"),)
        )

        self.assertEqual(500.0, environment.entity("b").scalars["health"])
        roll = next(event for event in batch.events if event.kind == EventKind.ATTACK_ROLLED)
        self.assertIn("result.miss", roll.tags)
        self.assertFalse(any(event.kind == EventKind.DAMAGE_APPLIED for event in batch.events))

    def test_passive_defense_blocks_a_normal_hit(self) -> None:
        swing = weapon_action()
        environment = ReferenceEnvironment(
            ActionCatalog((swing,)),
            (
                actor("a", "red", ("swing",)),
                actor("b", "blue", (), scalars={"passive.block.chance": 1.0}),
            ),
            seed=2,
        )

        batch = environment.step(
            (decision(environment, "a", "swing", target_id="b", correlation_id="block"),)
        )

        self.assertEqual(500.0, environment.entity("b").scalars["health"])
        self.assertTrue(
            any(event.kind == EventKind.PASSIVE_DEFENSE_TRIGGERED for event in batch.events)
        )

    def test_armed_modifier_bypasses_passive_defense_and_consumes_on_attempt(self) -> None:
        swing = weapon_action()
        setup = ActionSpec(
            action_key="setup",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(
                        ApplyEffect(
                            SubjectRef.ACTOR,
                            "armed_power",
                            10_000,
                            stacking_key="NextWeaponPower",
                            tags=("trigger.armed",),
                        ),
                    ),
                ),
            ),
            armed_trigger=ActionTriggerSpec(
                trigger_key="armed_power",
                required_action_tags=("attack", "weapon", "melee"),
                fire_on=TriggerMoment.ATTEMPT,
                consume_on=TriggerConsumption.ATTEMPT,
                attack_modifier=AttackModifierSpec(
                    bonus_damage_minimum=20.0,
                    bonus_damage_maximum=20.0,
                    bypass_passive_defense=True,
                ),
                payload=(
                    RemoveEffect(
                        SubjectRef.ACTOR,
                        matching_tag="visibility.invisible",
                    ),
                    ModifyTag(
                        SubjectRef.ACTOR,
                        "visibility.invisible",
                        TagOperation.REMOVE,
                    ),
                ),
            ),
            tags=("setup", "armed_trigger"),
        )
        environment = ReferenceEnvironment(
            ActionCatalog((setup, swing)),
            (
                actor(
                    "a",
                    "red",
                    ("setup", "swing"),
                    tags={"visibility.invisible"},
                ),
                actor("b", "blue", (), scalars={"passive.block.chance": 1.0}),
            ),
            seed=3,
        )
        environment.step((decision(environment, "a", "setup", correlation_id="arm"),))

        batch = environment.step(
            (decision(environment, "a", "swing", target_id="b", correlation_id="swing"),)
        )

        self.assertEqual(470.0, environment.entity("b").scalars["health"])
        self.assertNotIn("NextWeaponPower", environment.entity("a").effects)
        self.assertNotIn("visibility.invisible", environment.entity("a").effective_tags)
        self.assertFalse(
            any(event.kind == EventKind.PASSIVE_DEFENSE_TRIGGERED for event in batch.events)
        )

    def test_resistance_then_absorber_reduce_damage(self) -> None:
        swing = weapon_action()
        shield = ActiveEffectState(
            effect_key="shield",
            source_entity_id="b",
            magnitude=3.0,
            expires_at_ms=10_000,
            stacking_key="Shield",
            tags={"damage.absorb.physical"},
        )
        environment = ReferenceEnvironment(
            ActionCatalog((swing,)),
            (
                actor("a", "red", ("swing",)),
                actor(
                    "b",
                    "blue",
                    (),
                    scalars={"resistance.physical": 0.25},
                    effects={"Shield": shield},
                ),
            ),
            seed=4,
        )

        batch = environment.step(
            (decision(environment, "a", "swing", target_id="b", correlation_id="mitigate"),)
        )

        self.assertEqual(495.5, environment.entity("b").scalars["health"])
        damage = next(event for event in batch.events if event.kind == EventKind.DAMAGE_APPLIED)
        values = {item.name: item.value for item in damage.scalars}
        self.assertEqual(2.5, values["resisted"])
        self.assertEqual(3.0, values["absorbed"])
        self.assertEqual(4.5, values["effective"])
        self.assertTrue(any(event.kind == EventKind.ABSORBER_CONSUMED for event in batch.events))

    def test_consume_on_attempt_can_lose_a_hit_payload_on_miss(self) -> None:
        miss = weapon_action(minimum_hit_chance=0.0, maximum_hit_chance=0.0)
        proc_action = ActionSpec(
            action_key="proc_provider",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(ApplyEffect(SubjectRef.ACTOR, "one_shot", 10_000),),
                ),
            ),
            armed_trigger=ActionTriggerSpec(
                trigger_key="one_shot",
                required_action_tags=("attack", "weapon"),
                fire_on=TriggerMoment.HIT,
                consume_on=TriggerConsumption.ATTEMPT,
                payload=(DealDamage(SubjectRef.TARGET, 25.0, "poison"),),
            ),
        )
        armed = ActiveEffectState(
            effect_key="one_shot",
            source_entity_id="a",
            magnitude=1.0,
            expires_at_ms=10_000,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((proc_action, miss)),
            (
                actor("a", "red", ("swing",), effects={"one_shot": armed}),
                actor("b", "blue", ()),
            ),
            seed=5,
        )

        batch = environment.step(
            (decision(environment, "a", "swing", target_id="b", correlation_id="miss"),)
        )

        self.assertEqual(500.0, environment.entity("b").scalars["health"])
        self.assertNotIn("one_shot", environment.entity("a").effects)
        self.assertFalse(any(event.kind == EventKind.TRIGGER_FIRED for event in batch.events))

    def test_persistent_hit_proc_survives_multiple_attacks(self) -> None:
        swing = weapon_action()
        proc_action = ActionSpec(
            action_key="proc_provider",
            targeting=TargetingSpec(kind=TargetKind.SELF),
            phases=(
                ActionPhase(
                    kind=PhaseKind.ACTIVE,
                    duration_ms=0,
                    effects=(ApplyEffect(SubjectRef.ACTOR, "persistent_proc", 10_000),),
                ),
            ),
            armed_trigger=ActionTriggerSpec(
                trigger_key="persistent_proc",
                required_action_tags=("attack", "weapon"),
                fire_on=TriggerMoment.HIT,
                consume_on=TriggerConsumption.NEVER,
                chance=1.0,
                payload=(DealDamage(SubjectRef.TARGET, 5.0, "poison"),),
            ),
        )
        proc = ActiveEffectState(
            effect_key="persistent_proc",
            source_entity_id="a",
            magnitude=1.0,
            expires_at_ms=10_000,
        )
        environment = ReferenceEnvironment(
            ActionCatalog((proc_action, swing)),
            (
                actor("a", "red", ("swing",), effects={"persistent_proc": proc}),
                actor("b", "blue", ()),
            ),
            seed=6,
        )

        for index in range(2):
            environment.step(
                (
                    decision(
                        environment,
                        "a",
                        "swing",
                        target_id="b",
                        correlation_id=f"swing-{index}",
                    ),
                )
            )

        self.assertEqual(470.0, environment.entity("b").scalars["health"])
        self.assertIn("persistent_proc", environment.entity("a").effects)


if __name__ == "__main__":
    unittest.main()
