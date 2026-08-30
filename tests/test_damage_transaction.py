import unittest

from shadowbane_lab.combat import DamageType
from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    ActiveEffectState,
    DamageBreakpoint,
    DamageResolution,
    DamageTransaction,
    DealDamage,
    EntityState,
    PhaseKind,
    ReferenceEnvironment,
    SubjectRef,
    TargetingSpec,
    WeaponAttackSpec,
)


def entity(
    entity_id: str,
    team_id: str,
    action_keys: tuple[str, ...],
    scalars: dict[str, float],
    *,
    effects: dict[str, ActiveEffectState] | None = None,
) -> EntityState:
    health = scalars["health"]
    return EntityState(
        entity_id=entity_id,
        life_id=f"{entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=team_id,
        position=Vector2(0.0 if team_id == "red" else 1.0, 0.0),
        scalars=scalars,
        maximums={"health": health},
        action_keys=action_keys,
        effects=effects or {},
    )


def choose(environment: ReferenceEnvironment, actor_id: str, action_key: str, target_id: str):
    exchange = environment.exchange(actor_id)
    affordance = next(
        item
        for item in exchange.affordances.affordances
        if item.action_key == action_key and item.binding.target_entity_id == target_id
    )
    return exchange.decision(affordance.affordance_id, f"{action_key}:1")


def generic_weapon_action() -> ActionSpec:
    return ActionSpec(
        action_key="generic",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=3.0,
        ),
        phases=(ActionPhase(PhaseKind.ACTIVE, 0),),
        weapon_attack=WeaponAttackSpec(
            weapon_slot="main_hand",
            damage_type="crush",
            minimum_damage=10.0,
            maximum_damage=10.0,
            minimum_hit_chance=1.0,
            maximum_hit_chance=1.0,
        ),
        tags=("attack", "weapon", "melee"),
    )


def compiled_damage_action() -> ActionSpec:
    return ActionSpec(
        action_key="compiled",
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=3.0,
        ),
        phases=(
            ActionPhase(
                PhaseKind.ACTIVE,
                0,
                (
                    DealDamage(
                        SubjectRef.TARGET,
                        10.0,
                        DamageType.CRUSH,
                        uses_resistance=True,
                    ),
                ),
            ),
        ),
    )


class DamageValueTests(unittest.TestCase):
    def test_transaction_normalizes_tags_and_exposes_resistance_views(self) -> None:
        transaction = DamageTransaction(
            damage_type="crush",
            requested=10.0,
            post_resistance=7.5,
            resistance_percent=25.0,
            breakpoint_damage_type=DamageType.CRUSH,
            breakpoint_amount=7.5,
            tags=("attack.weapon", "attack.weapon"),
        )
        resolution = DamageResolution(
            transaction=transaction,
            absorbed=2.5,
            health_before=100.0,
            health_after=95.0,
        )

        self.assertEqual(("attack.weapon",), transaction.tags)
        self.assertEqual(0.25, transaction.resistance_fraction)
        self.assertEqual(2.5, transaction.resisted)
        self.assertEqual(5.0, resolution.post_absorption)
        self.assertEqual(5.0, resolution.effective)

    def test_breakpoint_amount_requires_a_typed_channel(self) -> None:
        with self.assertRaisesRegex(ValueError, "typed breakpoint damage channel"):
            DamageTransaction(
                damage_type="physical",
                requested=10.0,
                post_resistance=10.0,
                breakpoint_amount=10.0,
            )


class CanonicalDamageRuntimeTests(unittest.TestCase):
    def test_generic_and_compiled_damage_share_commit_scalars_and_state(self) -> None:
        generic = ReferenceEnvironment(
            ActionCatalog((generic_weapon_action(),)),
            (
                entity("source", "red", ("generic",), {"health": 100.0}),
                entity(
                    "target",
                    "blue",
                    (),
                    {"health": 100.0, "resistance.crush": 0.25},
                ),
            ),
            seed=7,
        )
        compiled = ReferenceEnvironment(
            ActionCatalog((compiled_damage_action(),)),
            (
                entity(
                    "source",
                    "red",
                    ("compiled",),
                    {"health": 100.0, "armor_piercing": 0.0},
                ),
                entity(
                    "target",
                    "blue",
                    (),
                    {"health": 100.0, "resist.crush": 25.0},
                ),
            ),
            seed=7,
        )

        generic_batch = generic.step((choose(generic, "source", "generic", "target"),))
        compiled_batch = compiled.step((choose(compiled, "source", "compiled", "target"),))

        generic_event = next(
            event for event in generic_batch.events if event.kind == EventKind.DAMAGE_APPLIED
        )
        compiled_event = next(
            event for event in compiled_batch.events if event.kind == EventKind.DAMAGE_APPLIED
        )
        names = (
            "requested",
            "post_resistance",
            "resistance_percent",
            "resisted",
            "absorbed",
            "effective",
        )
        generic_values = {item.name: item.value for item in generic_event.scalars}
        compiled_values = {item.name: item.value for item in compiled_event.scalars}

        self.assertEqual(
            tuple(generic_values[name] for name in names),
            tuple(compiled_values[name] for name in names),
        )
        self.assertEqual(92.5, generic.entity("target").scalars["health"])
        self.assertEqual(92.5, compiled.entity("target").scalars["health"])

    def test_compiled_damage_uses_the_shared_absorber_stage(self) -> None:
        shield = ActiveEffectState(
            effect_key="shield",
            source_entity_id="target",
            magnitude=3.0,
            expires_at_ms=10_000,
            stacking_key="Shield",
            tags={"damage.absorb.crush"},
        )
        environment = ReferenceEnvironment(
            ActionCatalog((compiled_damage_action(),)),
            (
                entity(
                    "source",
                    "red",
                    ("compiled",),
                    {"health": 100.0, "armor_piercing": 0.0},
                ),
                entity(
                    "target",
                    "blue",
                    (),
                    {"health": 100.0, "resist.crush": 0.0},
                    effects={"Shield": shield},
                ),
            ),
            seed=8,
        )

        batch = environment.step((choose(environment, "source", "compiled", "target"),))

        damage = next(event for event in batch.events if event.kind == EventKind.DAMAGE_APPLIED)
        values = {item.name: item.value for item in damage.scalars}
        self.assertEqual(93.0, environment.entity("target").scalars["health"])
        self.assertEqual(3.0, values["absorbed"])
        self.assertEqual(7.0, values["effective"])
        self.assertNotIn("Shield", environment.entity("target").effects)
        self.assertTrue(any(event.kind == EventKind.ABSORBER_CONSUMED for event in batch.events))

    def test_typed_generic_weapon_damage_reaches_the_breakpoint_stage(self) -> None:
        breakpoint = DamageBreakpoint("generic", 5.0, (DamageType.CRUSH,))
        breakable = ActiveEffectState(
            effect_key="breakable",
            source_entity_id="target",
            magnitude=1.0,
            expires_at_ms=10_000,
            modifiers=(breakpoint,),
            modifier_values={breakpoint.state_key: 0.0},
        )
        environment = ReferenceEnvironment(
            ActionCatalog((generic_weapon_action(),)),
            (
                entity("source", "red", ("generic",), {"health": 100.0}),
                entity(
                    "target",
                    "blue",
                    (),
                    {"health": 100.0, "resistance.crush": 0.0},
                    effects={"breakable": breakable},
                ),
            ),
            seed=9,
        )

        batch = environment.step((choose(environment, "source", "generic", "target"),))

        self.assertNotIn("breakable", environment.entity("target").effects)
        removed = next(event for event in batch.events if event.kind == EventKind.EFFECT_REMOVED)
        self.assertIn("reason.damage_breakpoint", removed.tags)


if __name__ == "__main__":
    unittest.main()
