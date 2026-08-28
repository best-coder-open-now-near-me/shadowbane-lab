import json
import unittest
from importlib.resources import files

from shadowbane_lab.combat import StackPriority
from shadowbane_lab.protocol import EntityKind, Vector2
from shadowbane_lab.rulesets import (
    CharacterBuild,
    CompilationStatus,
    RulesetLoadError,
    load_ruleset_text,
    load_shadowbane_vertical_slice,
)
from shadowbane_lab.sim import ActiveEffectState, EntityState, ReferenceEnvironment
from shadowbane_lab.sim.actions import (
    ApplyEffect,
    AttackGate,
    AttackKind,
    ChanceGate,
    DamageBreakpoint,
    DealDamage,
    PeriodicPulse,
    ResistanceAdjustment,
    RestoreResource,
    TriangularAmount,
    UniformAmount,
    UniformIntegerAmount,
)

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
LEVITATION = "shadowbane.warlock.levitation"
PASSWALL = "shadowbane.assassin.passwall"


def bundled_source() -> dict:
    resource = files("shadowbane_lab.rulesets").joinpath("data/shadowbane_vertical_slice_v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def matching_decision(
    environment: ReferenceEnvironment,
    agent_id: str,
    action_key: str,
    *,
    target_id: str | None = None,
):
    exchange = environment.exchange(agent_id)
    matches = tuple(
        affordance
        for affordance in exchange.affordances.affordances
        if affordance.action_key == action_key and affordance.binding.target_entity_id == target_id
    )
    if len(matches) != 1:
        raise AssertionError(f"expected one matching affordance, found {len(matches)}")
    return exchange.decision(matches[0].affordance_id, "ruleset-integration")


class RulesetCompilerTests(unittest.TestCase):
    def test_periodic_modifier_compiles_from_bounded_ruleset_data(self) -> None:
        source = bundled_source()
        shadow_touch = next(
            action
            for action in source["actions"]
            if action["action_key"] == SHADOW_TOUCH
        )
        applied = next(
            effect
            for effect in shadow_touch["spec"]["phases"][0]["effects"]
            if effect["op"] == "apply_effect"
        )
        applied["modifiers"] = [
            {
                "op": "periodic_pulse",
                "periodic_key": "test-dot",
                "interval_ms": 1_000,
                "tick_count": 2,
                "effects": [
                    {
                        "op": "deal_damage",
                        "subject": "target",
                        "amount": 5,
                        "damage_type": "poison",
                    }
                ],
            }
        ]

        action = load_ruleset_text(json.dumps(source)).record(SHADOW_TOUCH).action

        assert action is not None
        effect = next(
            item for item in action.phases[0].effects if isinstance(item, ApplyEffect)
        )
        self.assertIsInstance(effect.modifiers[0], PeriodicPulse)
        pulse = effect.modifiers[0]
        assert isinstance(pulse, PeriodicPulse)
        self.assertEqual(2, pulse.tick_count)
        self.assertEqual("poison", pulse.effects[0].damage_type)

    def test_damage_breakpoint_and_resistance_compile_from_ruleset_data(self) -> None:
        source = bundled_source()
        shadow_touch = next(
            action
            for action in source["actions"]
            if action["action_key"] == SHADOW_TOUCH
        )
        applied = next(
            effect
            for effect in shadow_touch["spec"]["phases"][0]["effects"]
            if effect["op"] == "apply_effect"
        )
        applied["modifiers"] = [
            {
                "op": "resistance_adjustment",
                "damage_type": "crush",
                "amount": 75,
            },
            {
                "op": "damage_breakpoint",
                "breakpoint_key": "physical",
                "threshold": 1_000,
                "damage_types": ["crush", "pierce", "slash"],
            },
        ]

        action = load_ruleset_text(json.dumps(source)).record(SHADOW_TOUCH).action

        assert action is not None
        effect = next(
            item for item in action.phases[0].effects if isinstance(item, ApplyEffect)
        )
        self.assertEqual(
            ResistanceAdjustment("crush", 75.0),
            effect.modifiers[0],
        )
        self.assertEqual(
            DamageBreakpoint(
                "physical",
                1_000.0,
                ("crush", "pierce", "slash"),
            ),
            effect.modifiers[1],
        )

    def test_bundled_slice_loads_with_explicit_quality_states(self) -> None:
        ruleset = load_shadowbane_vertical_slice()

        self.assertEqual("shadowbane.vertical-slice.v1", ruleset.ruleset_id)
        self.assertEqual(9, len(ruleset.records))
        self.assertEqual(8, len(ruleset.catalog))
        self.assertEqual(
            {
                CompilationStatus.COMPILED: 0,
                CompilationStatus.COMPILED_WITH_OVERRIDE: 8,
                CompilationStatus.UNRESOLVED: 1,
            },
            ruleset.status_counts(),
        )
        source = next(item for item in ruleset.sources if item.source_id == "magicbane-subdate2")
        self.assertEqual("ab96cfcda4e983dd7fc1fc205205810f11ddd3de", source.revision)

    def test_level_and_training_requirements_select_progression_subset(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        level_14 = CharacterBuild(
            profession="assassin",
            level=14,
            skill_ranks=(("shadowmastery", 35),),
        )
        level_15 = CharacterBuild(
            profession="assassin",
            level=15,
            skill_ranks=(("shadowmastery", 36),),
        )

        self.assertIn(SHADOW_BOLT, ruleset.action_keys_for(level_14))
        self.assertNotIn(SHADOW_TOUCH, ruleset.action_keys_for(level_14))
        self.assertIn(SHADOW_TOUCH, ruleset.action_keys_for(level_15))
        self.assertNotIn(MIND_STRIKE, ruleset.action_keys_for(level_15))

    def test_warlock_unlocks_are_independent_of_power_rank(self) -> None:
        ruleset = load_shadowbane_vertical_slice(rank_overrides={MIND_STRIKE: 0})
        build = CharacterBuild(
            profession="warlock",
            level=22,
            skill_ranks=(("warlockry", 52),),
            power_ranks=((MIND_STRIKE, 0),),
        )

        action_keys = ruleset.action_keys_for(build)

        self.assertIn(MIND_STRIKE, action_keys)
        self.assertIn(LEVITATION, action_keys)
        self.assertNotIn(PSYCHIC_HEALING, action_keys)
        self.assertEqual(0, ruleset.record(MIND_STRIKE).rank)

    def test_build_fails_if_ruleset_was_compiled_at_a_different_rank(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        build = CharacterBuild(
            profession="warlock",
            level=10,
            power_ranks=((MIND_STRIKE, 20),),
        )

        with self.assertRaisesRegex(ValueError, "compiled at rank 40"):
            ruleset.action_keys_for(build)

    def test_fixed_power_rank_cannot_be_overridden(self) -> None:
        with self.assertRaisesRegex(RulesetLoadError, "fixed power"):
            load_shadowbane_vertical_slice(rank_overrides={LEVITATION: 4})

    def test_unknown_rank_override_fails_closed(self) -> None:
        with self.assertRaisesRegex(RulesetLoadError, "unknown actions"):
            load_shadowbane_vertical_slice(rank_overrides={"missing.power": 20})

    def test_build_cannot_select_another_professions_power(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        build = CharacterBuild(
            profession="assassin",
            level=40,
            power_ranks=((MIND_STRIKE, 40),),
        )

        with self.assertRaisesRegex(ValueError, "another profession"):
            ruleset.action_keys_for(build)

    def test_shadow_bolt_rank_40_values_and_effects_are_compiled(self) -> None:
        record = load_shadowbane_vertical_slice().record(SHADOW_BOLT)
        action = record.action

        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(429213513, record.mapping.server_power_token)
        self.assertEqual("ASS-018", record.mapping.server_id_string)
        self.assertEqual(39.8, action.costs[0].amount)
        self.assertEqual(2_000, action.phases[0].duration_ms)
        self.assertEqual(2_000, action.cooldown_ms)
        self.assertEqual(120.0, action.targeting.maximum_range)
        damage = next(
            effect for effect in action.phases[0].effects if isinstance(effect, DealDamage)
        )
        effects = tuple(
            effect for effect in action.phases[0].effects if isinstance(effect, ApplyEffect)
        )
        self.assertEqual(UniformAmount(24.0, 33.0), damage.amount)
        self.assertEqual(28.5, damage.amount.expected)
        self.assertEqual((3_000, 9_000), tuple(effect.duration_ms for effect in effects))

    def test_psychic_healing_uses_cast_plus_recycle_readiness(self) -> None:
        record = load_shadowbane_vertical_slice().record(PSYCHIC_HEALING)
        action = record.action

        self.assertIsNotNone(action)
        assert action is not None
        heal = next(
            effect for effect in action.phases[0].effects if isinstance(effect, RestoreResource)
        )
        self.assertEqual(38.8, action.costs[0].amount)
        self.assertEqual(2_500, action.phases[0].duration_ms)
        self.assertEqual(8_500, action.cooldown_ms)
        self.assertEqual(UniformAmount(37.0, 92.0), heal.amount)
        self.assertEqual(64.5, heal.amount.expected)

    def test_mind_strike_and_shadow_touch_are_compiled(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        mind_strike = ruleset.record(MIND_STRIKE).action
        shadow_touch_record = ruleset.record(SHADOW_TOUCH)
        shadow_touch = shadow_touch_record.action

        self.assertIsNotNone(mind_strike)
        self.assertIsNotNone(shadow_touch)
        assert mind_strike is not None and shadow_touch is not None
        self.assertEqual(428918601, shadow_touch_record.mapping.server_power_token)
        self.assertEqual("ASS-013", shadow_touch_record.mapping.server_id_string)
        damage = next(
            effect for effect in mind_strike.phases[0].effects if isinstance(effect, DealDamage)
        )
        self.assertEqual(UniformAmount(33.0, 52.0), damage.amount)
        self.assertEqual(3_600, mind_strike.cooldown_ms)
        self.assertEqual(9_000, shadow_touch.features[0].value)

    def test_unresolved_action_is_excluded_from_executable_catalog(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        record = ruleset.record(PASSWALL)

        self.assertEqual(CompilationStatus.UNRESOLVED, record.status)
        self.assertIsNone(record.action)
        with self.assertRaises(KeyError):
            ruleset.catalog.get(PASSWALL)

    def test_linear_rank_curves_are_resolved_at_compile_time(self) -> None:
        source = bundled_source()
        shadow_bolt = next(
            action for action in source["actions"] if action["action_key"] == SHADOW_BOLT
        )
        shadow_bolt["rank"] = 20

        action = load_ruleset_text(json.dumps(source)).record(SHADOW_BOLT).action

        self.assertIsNotNone(action)
        assert action is not None
        self.assertAlmostEqual(28.4, action.costs[0].amount)
        damage = next(
            effect for effect in action.phases[0].effects if isinstance(effect, DealDamage)
        )
        self.assertEqual(UniformAmount(17.0, 23.5), damage.amount)
        self.assertAlmostEqual(20.25, damage.amount.expected)

    def test_uniform_integer_amounts_compile_for_observed_discrete_rolls(self) -> None:
        source = bundled_source()
        basic_attack = next(
            action
            for action in source["actions"]
            if action["action_key"] == "shadowbane.basic_attack"
        )
        basic_attack["spec"]["phases"][0]["effects"][0]["amount"] = {
            "distribution": "uniform_integer",
            "minimum": 4,
            "maximum": 5,
        }

        action = load_ruleset_text(json.dumps(source)).record("shadowbane.basic_attack").action

        self.assertIsNotNone(action)
        assert action is not None
        damage = next(
            effect for effect in action.phases[0].effects if isinstance(effect, DealDamage)
        )
        self.assertEqual(UniformIntegerAmount(4, 5), damage.amount)

    def test_chance_gates_compile_as_bounded_non_recursive_effects(self) -> None:
        source = bundled_source()
        basic_attack = next(
            action
            for action in source["actions"]
            if action["action_key"] == "shadowbane.basic_attack"
        )
        basic_attack["spec"]["phases"][0]["effects"] = [
            {
                "op": "chance_gate",
                "chance_key": "weapon_proc",
                "probability": 0.05,
                "effects": [
                    {
                        "op": "deal_damage",
                        "subject": "target",
                        "amount": 12,
                        "damage_type": "mental",
                    }
                ],
            }
        ]

        action = load_ruleset_text(json.dumps(source)).record("shadowbane.basic_attack").action

        self.assertIsNotNone(action)
        assert action is not None
        gate = action.phases[0].effects[0]
        self.assertIsInstance(gate, ChanceGate)
        assert isinstance(gate, ChanceGate)
        self.assertEqual("weapon_proc", gate.chance_key)
        self.assertEqual(0.05, gate.probability)

    def test_source_combat_primitives_compile_without_runtime_guessing(self) -> None:
        source = bundled_source()
        basic_attack = next(
            action
            for action in source["actions"]
            if action["action_key"] == "shadowbane.basic_attack"
        )
        basic_attack["spec"]["cancel_on_damage"] = True
        basic_attack["spec"]["phases"][0]["effects"] = [
            {
                "op": "attack_gate",
                "attack_key": "main_hand",
                "kind": "basic",
                "attack_rating_key": "attack.main_hand",
                "defense_rating_key": "defense",
                "passive_defense_keys": ["passive.block", "passive.dodge"],
                "effects": [
                    {
                        "op": "deal_damage",
                        "subject": "target",
                        "amount": {
                            "distribution": "triangular",
                            "minimum": 40,
                            "maximum": 80,
                        },
                        "damage_type": "crush",
                        "uses_resistance": True,
                        "power_trains": 20,
                    },
                    {
                        "op": "apply_effect",
                        "subject": "target",
                        "effect_key": "debuff",
                        "duration_ms": 1_000,
                        "stacking_key": "Debuff",
                        "tags": [],
                        "stack_order": 2,
                        "trains": 20,
                        "stack_priority": "greater_than_or_equal",
                    },
                ],
            }
        ]

        action = load_ruleset_text(json.dumps(source)).record(
            "shadowbane.basic_attack"
        ).action

        self.assertIsNotNone(action)
        assert action is not None
        self.assertTrue(action.cancel_on_damage)
        gate = action.phases[0].effects[0]
        self.assertIsInstance(gate, AttackGate)
        assert isinstance(gate, AttackGate)
        self.assertIs(gate.kind, AttackKind.BASIC)
        damage = gate.effects[0]
        self.assertIsInstance(damage, DealDamage)
        assert isinstance(damage, DealDamage)
        self.assertEqual(TriangularAmount(40.0, 80.0), damage.amount)
        self.assertTrue(damage.uses_resistance)
        applied = gate.effects[1]
        self.assertIsInstance(applied, ApplyEffect)
        assert isinstance(applied, ApplyEffect)
        self.assertIs(StackPriority.GREATER_THAN_OR_EQUAL, applied.stack_priority)

    def test_unknown_provenance_source_fails_closed(self) -> None:
        source = bundled_source()
        source["actions"][0]["provenance"][0]["source_id"] = "missing-source"

        with self.assertRaisesRegex(RulesetLoadError, "unknown source"):
            load_ruleset_text(json.dumps(source))

    def test_invalid_source_enum_is_reported_as_a_load_error(self) -> None:
        source = bundled_source()
        source["sources"][0]["kind"] = "forum-memory"

        with self.assertRaises(RulesetLoadError):
            load_ruleset_text(json.dumps(source))

    def test_missing_nested_field_is_reported_as_a_load_error(self) -> None:
        source = bundled_source()
        del source["actions"][0]["spec"]["features"][0]["value"]

        with self.assertRaisesRegex(RulesetLoadError, "missing required field: value"):
            load_ruleset_text(json.dumps(source))

    def test_compiled_shadow_bolt_runs_through_reference_environment(self) -> None:
        ruleset = load_shadowbane_vertical_slice()
        caster = EntityState(
            entity_id="assassin",
            life_id="assassin:1",
            kind=EntityKind.ACTOR,
            team_id="red",
            position=Vector2(0.0, 0.0),
            scalars={"health": 100.0, "mana": 100.0},
            maximums={"health": 100.0, "mana": 100.0},
            action_keys=(SHADOW_BOLT,),
        )
        target = EntityState(
            entity_id="target",
            life_id="target:1",
            kind=EntityKind.ACTOR,
            team_id="blue",
            position=Vector2(10.0, 0.0),
            scalars={"health": 100.0, "mana": 100.0},
            maximums={"health": 100.0, "mana": 100.0},
            effects={
                "Flight": ActiveEffectState(
                    effect_key="levitation",
                    source_entity_id="target",
                    magnitude=1.0,
                    expires_at_ms=300_000,
                    stacking_key="Flight",
                    tags={"movement.flight"},
                )
            },
        )
        environment = ReferenceEnvironment(ruleset.catalog, (caster, target), seed=11)
        decision = matching_decision(environment, "assassin", SHADOW_BOLT, target_id="target")

        result = environment.step((decision,))
        for _ in range(9):
            result = environment.step()

        caster_after = environment.entity("assassin")
        target_after = environment.entity("target")
        damage_event = next(event for event in result.events if event.kind == "damage_applied")
        rolled_damage = next(
            item.value for item in damage_event.scalars if item.name == "requested"
        )
        self.assertAlmostEqual(60.2, caster_after.scalars["mana"])
        self.assertGreaterEqual(rolled_damage, 24.0)
        self.assertLess(rolled_damage, 33.0)
        self.assertAlmostEqual(100.0 - rolled_damage, target_after.scalars["health"])
        self.assertNotIn("Flight", target_after.effects)
        self.assertEqual({"Stun", "NoStun"}, set(target_after.effects))


if __name__ == "__main__":
    unittest.main()
