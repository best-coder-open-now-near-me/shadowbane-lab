from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests/test_ruleset_compiler.py"


def replace_method(method_name: str, replacement: str) -> None:
    text = TESTS.read_text(encoding="utf-8")
    marker = f"    def {method_name}("
    start = text.index(marker)
    next_method = text.find("\n    def ", start + len(marker))
    if next_method < 0:
        raise RuntimeError(f"cannot find end of {method_name}")
    TESTS.write_text(
        text[:start] + replacement.rstrip() + "\n" + text[next_method:],
        encoding="utf-8",
    )


def main() -> None:
    replace_method(
        "test_periodic_modifier_compiles_from_bounded_ruleset_data",
        '''    def test_periodic_modifier_compiles_from_bounded_ruleset_data(self) -> None:
        source = bundled_source()
        shadow_touch = next(
            action for action in source["actions"] if action["action_key"] == SHADOW_TOUCH
        )
        conditional_data = next(
            effect
            for effect in shadow_touch["spec"]["phases"][0]["effects"]
            if effect["op"] == "outcome_conditional"
        )
        applied = conditional_data["condition"]
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
        conditional = next(
            item for item in action.phases[0].effects if isinstance(item, OutcomeConditional)
        )
        effect = conditional.condition
        self.assertIsInstance(effect, ApplyEffect)
        assert isinstance(effect, ApplyEffect)
        self.assertIsInstance(effect.modifiers[0], PeriodicPulse)
        pulse = effect.modifiers[0]
        assert isinstance(pulse, PeriodicPulse)
        self.assertEqual(2, pulse.tick_count)
        self.assertEqual("poison", pulse.effects[0].damage_type)
''',
    )
    replace_method(
        "test_damage_breakpoint_and_resistance_compile_from_ruleset_data",
        '''    def test_damage_breakpoint_and_resistance_compile_from_ruleset_data(self) -> None:
        source = bundled_source()
        shadow_touch = next(
            action for action in source["actions"] if action["action_key"] == SHADOW_TOUCH
        )
        conditional_data = next(
            effect
            for effect in shadow_touch["spec"]["phases"][0]["effects"]
            if effect["op"] == "outcome_conditional"
        )
        applied = conditional_data["condition"]
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
            {
                "op": "scalar_multiplier",
                "scalar_key": "move_speed",
                "factor": 0.4,
            },
        ]

        action = load_ruleset_text(json.dumps(source)).record(SHADOW_TOUCH).action

        assert action is not None
        conditional = next(
            item for item in action.phases[0].effects if isinstance(item, OutcomeConditional)
        )
        effect = conditional.condition
        self.assertIsInstance(effect, ApplyEffect)
        assert isinstance(effect, ApplyEffect)
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
        self.assertEqual(
            ScalarMultiplier("move_speed", 0.4),
            effect.modifiers[2],
        )
''',
    )


if __name__ == "__main__":
    main()
