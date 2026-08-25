import json
import unittest
from importlib.resources import files

from shadowbane_lab.protocol import EntityKind, Vector2
from shadowbane_lab.rulesets import (
    CompilationStatus,
    RulesetLoadError,
    load_ruleset_text,
    load_shadowbane_vertical_slice,
)
from shadowbane_lab.sim import ActiveEffectState, EntityState, ReferenceEnvironment
from shadowbane_lab.sim.actions import ApplyEffect, DealDamage, RestoreResource

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
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
    def test_bundled_slice_loads_with_explicit_quality_states(self) -> None:
        ruleset = load_shadowbane_vertical_slice()

        self.assertEqual("shadowbane.vertical-slice.v1", ruleset.ruleset_id)
        self.assertEqual(6, len(ruleset.records))
        self.assertEqual(5, len(ruleset.catalog))
        self.assertEqual(
            {
                CompilationStatus.COMPILED: 0,
                CompilationStatus.COMPILED_WITH_OVERRIDE: 5,
                CompilationStatus.UNRESOLVED: 1,
            },
            ruleset.status_counts(),
        )
        source = next(item for item in ruleset.sources if item.source_id == "magicbane-subdate2")
        self.assertEqual("ab96cfcda4e983dd7fc1fc205205810f11ddd3de", source.revision)

    def test_shadow_bolt_rank_40_values_and_effects_are_compiled(self) -> None:
        record = load_shadowbane_vertical_slice().record(SHADOW_BOLT)
        action = record.action

        self.assertIsNotNone(action)
        assert action is not None
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
        self.assertEqual(28.5, damage.amount)
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
        self.assertEqual(64.5, heal.amount)

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
        self.assertAlmostEqual(20.25, damage.amount)

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

        environment.step((decision,))
        for _ in range(9):
            environment.step()

        caster_after = environment.entity("assassin")
        target_after = environment.entity("target")
        self.assertAlmostEqual(60.2, caster_after.scalars["mana"])
        self.assertEqual(71.5, target_after.scalars["health"])
        self.assertNotIn("Flight", target_after.effects)
        self.assertEqual({"Stun", "NoStun"}, set(target_after.effects))


if __name__ == "__main__":
    unittest.main()
