from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / "src/shadowbane_lab/rulesets/loader.py"
VERTICAL_SLICE = ROOT / "src/shadowbane_lab/rulesets/data/shadowbane_vertical_slice_v1.json"
WONDERBANE_EXTENSION = (
    ROOT / "src/shadowbane_lab/rulesets/data/wonderbane_sundancer_deflock_v1.json"
)
RULESET_TESTS = ROOT / "tests/test_ruleset_compiler.py"
PRESET_TESTS = ROOT / "tests/test_wonderbane_presets.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement target, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def matching_array_end(text: str, start: int) -> int:
    if text[start] != "[":
        raise RuntimeError("array scan must start on an opening bracket")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
    raise RuntimeError("unterminated JSON array")


def action_collection(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("actions", data.get("additional_actions"))
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise RuntimeError("ruleset does not contain an action-object array")
    return raw


def replace_first_phase_effects(
    path: Path,
    action_key: str,
    transform: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    actions = action_collection(data)
    matches = [item for item in actions if item.get("action_key") == action_key]
    if len(matches) != 1:
        raise RuntimeError(f"{path}: expected one {action_key} declaration")
    phases = matches[0]["spec"]["phases"]
    if not isinstance(phases, list) or not phases:
        raise RuntimeError(f"{action_key}: missing first phase")
    effects = phases[0]["effects"]
    if not isinstance(effects, list) or any(not isinstance(item, dict) for item in effects):
        raise RuntimeError(f"{action_key}: first-phase effects must be objects")
    transformed = transform(copy.deepcopy(effects))

    marker = f'"action_key": "{action_key}"'
    action_start = text.index(marker)
    phases_key = text.index('"phases":', action_start)
    effects_key = text.index('"effects":', phases_key)
    array_start = text.index("[", effects_key)
    array_end = matching_array_end(text, array_start)
    line_start = text.rfind("\n", 0, effects_key) + 1
    indentation = text[line_start:effects_key]
    serialized = json.dumps(transformed, indent=2, ensure_ascii=False).splitlines()
    aligned = serialized[0] + "".join(f"\n{indentation}{line}" for line in serialized[1:])
    path.write_text(text[:array_start] + aligned + text[array_end + 1 :], encoding="utf-8")


def conditionalize_control_bundle(
    effects: list[dict[str, Any]],
    *,
    conditional_key: str,
) -> list[dict[str, Any]]:
    ground_indexes = [
        index
        for index, effect in enumerate(effects)
        if effect.get("op") == "remove_effect"
        and effect.get("matching_tag") == "movement.flight"
    ]
    stun_indexes = [
        index
        for index, effect in enumerate(effects)
        if effect.get("op") == "apply_effect"
        and "control.stun" in effect.get("tags", [])
    ]
    immunity_indexes = [
        index
        for index, effect in enumerate(effects)
        if effect.get("op") == "apply_effect"
        and "immunity.stun" in effect.get("tags", [])
    ]
    if not (
        len(ground_indexes) == len(stun_indexes) == len(immunity_indexes) == 1
    ):
        raise RuntimeError(f"{conditional_key}: expected one grounding, stun, and immunity effect")
    selected = {ground_indexes[0], stun_indexes[0], immunity_indexes[0]}
    first = min(selected)
    last = max(selected)
    if selected != set(range(first, last + 1)):
        raise RuntimeError(f"{conditional_key}: dependent effects must form one contiguous bundle")

    ground = effects[ground_indexes[0]]
    stun = effects[stun_indexes[0]]
    immunity = effects[immunity_indexes[0]]
    stun["immunity_tags"] = ["immunity.stun"]
    conditional = {
        "op": "outcome_conditional",
        "conditional_key": conditional_key,
        "condition": stun,
        "outcomes": ["applied"],
        "effects": [ground, immunity],
        "else_effects": [],
    }
    return [*effects[:first], conditional, *effects[last + 1 :]]


def conditionalize_psychic_shout(
    effects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    areas = [effect for effect in effects if effect.get("op") == "area_effect"]
    if len(areas) != 1:
        raise RuntimeError("psychic_shout: expected one area effect")
    nested = areas[0].get("effects")
    if not isinstance(nested, list) or any(not isinstance(item, dict) for item in nested):
        raise RuntimeError("psychic_shout: area effects must be objects")
    areas[0]["effects"] = conditionalize_control_bundle(
        nested,
        conditional_key="psychic_shout_stun_followups",
    )
    return effects


def replace_test_method(path: Path, method_name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    marker = f"    def {method_name}("
    start = text.index(marker)
    next_method = text.find("\n    def ", start + len(marker))
    main_guard = text.find("\n\nif __name__", start + len(marker))
    candidates = [value for value in (next_method, main_guard) if value >= 0]
    if not candidates:
        raise RuntimeError(f"{path}: cannot find end of {method_name}")
    end = min(candidates)
    path.write_text(text[:start] + replacement.rstrip() + "\n" + text[end:], encoding="utf-8")


def patch_loader() -> None:
    replace_once(
        LOADER,
        "    DeliverySpec,\n    ModifyObjective,",
        "    DeliverySpec,\n    EffectOutcomeKind,\n    ModifyObjective,",
    )
    replace_once(
        LOADER,
        "    MovementMode,\n    PeriodicPulse,",
        "    MovementMode,\n    OutcomeConditional,\n    PeriodicPulse,",
    )
    operation_header = (
        "def _parse_effect(data: Mapping[str, Any], rank: int) -> EffectPrimitive:\n"
        "    operation = _string(data, \"op\")\n"
    )
    conditional_parser = operation_header + '''    if operation == "outcome_conditional":
        condition = _parse_effect(_object(data, "condition"), rank)
        effects = tuple(_parse_effect(item, rank) for item in _objects(data, "effects"))
        else_effects = tuple(
            _parse_effect(item, rank) for item in _optional_objects(data, "else_effects")
        )
        try:
            return OutcomeConditional(
                conditional_key=_string(data, "conditional_key"),
                condition=condition,
                outcomes=tuple(
                    EffectOutcomeKind(value) for value in _strings(data, "outcomes")
                ),
                effects=effects,
                else_effects=else_effects,
            )
        except ValueError as exc:
            raise RulesetLoadError(str(exc)) from exc
'''
    replace_once(LOADER, operation_header, conditional_parser)
    replace_once(
        LOADER,
        '            tags=tuple(_strings(data, "tags")),\n            modifiers=tuple(',
        '''            tags=tuple(_strings(data, "tags")),
            immunity_tags=(
                tuple(_strings(data, "immunity_tags"))
                if "immunity_tags" in data
                else ()
            ),
            modifiers=tuple(''',
    )


def patch_ruleset_data() -> None:
    for action_key, conditional_key in (
        ("shadowbane.assassin.shadow_bolt", "shadow_bolt_stun_followups"),
        ("shadowbane.assassin.shadow_touch", "shadow_touch_stun_followups"),
        ("shadowbane.warlock.mind_strike", "mind_strike_stun_followups"),
    ):
        replace_first_phase_effects(
            VERTICAL_SLICE,
            action_key,
            lambda effects, key=conditional_key: conditionalize_control_bundle(
                effects,
                conditional_key=key,
            ),
        )
    replace_first_phase_effects(
        WONDERBANE_EXTENSION,
        "shadowbane.warlock.psychic_shout",
        conditionalize_psychic_shout,
    )


def patch_ruleset_tests() -> None:
    replace_once(
        RULESET_TESTS,
        "    DealDamage,\n    PeriodicPulse,",
        "    DealDamage,\n    EffectOutcomeKind,\n    OutcomeConditional,\n    PeriodicPulse,",
    )
    replace_once(
        RULESET_TESTS,
        "    ResistanceAdjustment,\n    RestoreResource,",
        "    ResistanceAdjustment,\n    RestoreResource,\n    RemoveEffect,",
    )
    replace_test_method(
        RULESET_TESTS,
        "test_shadow_bolt_rank_40_values_and_effects_are_compiled",
        '''    def test_shadow_bolt_rank_40_values_and_effects_are_compiled(self) -> None:
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
        conditional = next(
            effect
            for effect in action.phases[0].effects
            if isinstance(effect, OutcomeConditional)
        )
        self.assertEqual(UniformAmount(24.0, 33.0), damage.amount)
        self.assertEqual(28.5, damage.amount.expected)
        self.assertEqual((EffectOutcomeKind.APPLIED,), conditional.outcomes)
        self.assertIsInstance(conditional.condition, ApplyEffect)
        stun = conditional.condition
        assert isinstance(stun, ApplyEffect)
        grounding = next(
            effect for effect in conditional.effects if isinstance(effect, RemoveEffect)
        )
        immunity = next(
            effect for effect in conditional.effects if isinstance(effect, ApplyEffect)
        )
        self.assertEqual(("stunned", 3_000), (stun.effect_key, stun.duration_ms))
        self.assertEqual(("immunity.stun",), stun.immunity_tags)
        self.assertEqual("movement.flight", grounding.matching_tag)
        self.assertEqual(("stun_immunity", 9_000), (immunity.effect_key, immunity.duration_ms))
        self.assertEqual((), conditional.else_effects)
''',
    )
    replace_test_method(
        RULESET_TESTS,
        "test_mind_strike_and_shadow_touch_are_compiled",
        '''    def test_mind_strike_and_shadow_touch_are_compiled(self) -> None:
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
        for action, expected in (
            (mind_strike, (3_000, 9_000)),
            (shadow_touch, (9_000, 27_000)),
        ):
            conditional = next(
                effect
                for effect in action.phases[0].effects
                if isinstance(effect, OutcomeConditional)
            )
            self.assertEqual((EffectOutcomeKind.APPLIED,), conditional.outcomes)
            self.assertIsInstance(conditional.condition, ApplyEffect)
            stun = conditional.condition
            assert isinstance(stun, ApplyEffect)
            immunity = next(
                effect for effect in conditional.effects if isinstance(effect, ApplyEffect)
            )
            self.assertEqual(expected, (stun.duration_ms, immunity.duration_ms))
            self.assertEqual(("immunity.stun",), stun.immunity_tags)
            self.assertTrue(
                any(isinstance(effect, RemoveEffect) for effect in conditional.effects)
            )
''',
    )
    success_method = '''    def test_compiled_shadow_bolt_runs_through_reference_environment(self) -> None:
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

        batches = [environment.step((decision,))]
        for _ in range(9):
            batches.append(environment.step())
        events = tuple(event for batch in batches for event in batch.events)

        caster_after = environment.entity("assassin")
        target_after = environment.entity("target")
        damage_event = next(event for event in events if event.kind == "damage_applied")
        rolled_damage = next(
            item.value for item in damage_event.scalars if item.name == "requested"
        )
        conditional = next(
            event for event in events if event.kind == "effect_outcome_resolved"
        )
        self.assertAlmostEqual(60.2, caster_after.scalars["mana"])
        self.assertGreaterEqual(rolled_damage, 24.0)
        self.assertLess(rolled_damage, 33.0)
        self.assertAlmostEqual(100.0 - rolled_damage, target_after.scalars["health"])
        self.assertNotIn("Flight", target_after.effects)
        self.assertEqual({"Stun", "NoStun"}, set(target_after.effects))
        self.assertIn("outcome.applied", conditional.tags)
        self.assertIn("branch.effects", conditional.tags)

    def test_compiled_shadow_bolt_blocked_stun_preserves_existing_state(self) -> None:
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
                ),
                "NoStun": ActiveEffectState(
                    effect_key="existing_stun_immunity",
                    source_entity_id="target",
                    magnitude=1.0,
                    expires_at_ms=300_000,
                    stacking_key="NoStun",
                    tags={"immunity.stun"},
                ),
            },
        )
        environment = ReferenceEnvironment(ruleset.catalog, (caster, target), seed=11)
        decision = matching_decision(environment, "assassin", SHADOW_BOLT, target_id="target")

        batches = [environment.step((decision,))]
        for _ in range(9):
            batches.append(environment.step())
        events = tuple(event for batch in batches for event in batch.events)

        target_after = environment.entity("target")
        conditional = next(
            event for event in events if event.kind == "effect_outcome_resolved"
        )
        self.assertEqual({"Flight", "NoStun"}, set(target_after.effects))
        self.assertNotIn("Stun", target_after.effects)
        self.assertIn("outcome.blocked_immunity", conditional.tags)
        self.assertIn("branch.else_effects", conditional.tags)
        self.assertTrue(
            any(
                event.kind == "effect_blocked" and "reason.immune" in event.tags
                for event in events
            )
        )
'''
    replace_test_method(
        RULESET_TESTS,
        "test_compiled_shadow_bolt_runs_through_reference_environment",
        success_method,
    )


def patch_preset_tests() -> None:
    replace_once(
        PRESET_TESTS,
        "    CombatStance,\n    RemoveEffect,",
        "    CombatStance,\n    EffectOutcomeKind,\n    OutcomeConditional,\n    RemoveEffect,",
    )
    old = '''        silence = ruleset.record(SILENCE).action
        needs = ruleset.record(NEEDS_OF_THE_ONE).action
        snare = ruleset.record(MIND_SNARE).action
        dispel = ruleset.record(BREAK_ENCHANTMENT).action

        assert silence is not None and needs is not None and snare is not None
        assert dispel is not None
'''
    new = '''        silence = ruleset.record(SILENCE).action
        needs = ruleset.record(NEEDS_OF_THE_ONE).action
        snare = ruleset.record(MIND_SNARE).action
        dispel = ruleset.record(BREAK_ENCHANTMENT).action
        psychic_shout = ruleset.record(PSYCHIC_SHOUT).action

        assert silence is not None and needs is not None and snare is not None
        assert dispel is not None and psychic_shout is not None
'''
    replace_once(PRESET_TESTS, old, new)
    insertion = '''        removal = next(
            effect for effect in dispel.phases[0].effects if isinstance(effect, RemoveEffect)
        )
        self.assertEqual(1, removal.maximum_count)
'''
    expanded = insertion + '''
        shout_area = next(
            effect for effect in psychic_shout.phases[0].effects if isinstance(effect, AreaEffect)
        )
        conditional = next(
            effect for effect in shout_area.effects if isinstance(effect, OutcomeConditional)
        )
        self.assertEqual((EffectOutcomeKind.APPLIED,), conditional.outcomes)
        self.assertIsInstance(conditional.condition, ApplyEffect)
        stun = conditional.condition
        assert isinstance(stun, ApplyEffect)
        self.assertEqual("psychic_shout_stun", stun.effect_key)
        self.assertEqual(("immunity.stun",), stun.immunity_tags)
        self.assertTrue(any(isinstance(effect, RemoveEffect) for effect in conditional.effects))
'''
    replace_once(PRESET_TESTS, insertion, expanded)


def main() -> None:
    patch_loader()
    patch_ruleset_data()
    patch_ruleset_tests()
    patch_preset_tests()


if __name__ == "__main__":
    main()
