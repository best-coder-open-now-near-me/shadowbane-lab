import unittest

from shadowbane_lab.combat import (
    StackPriority,
    WeaponDamageInputs,
    defense_rating,
    effective_resistance,
    melee_hit_chance_percent,
    power_attack_rating,
    power_hit_chance_percent,
    resisted_amount,
    should_overwrite_effect,
    spell_amount_bounds,
    triangular_roll,
    weapon_attack_rating,
    weapon_damage_bounds,
)


class CombatFormulaTests(unittest.TestCase):
    def test_melee_hit_curve_has_source_caps_and_center(self) -> None:
        self.assertEqual(4, melee_hit_chance_percent(899, 1_000))
        self.assertEqual(4, melee_hit_chance_percent(900, 1_000))
        self.assertEqual(49, melee_hit_chance_percent(1_000, 1_000))
        self.assertEqual(94, melee_hit_chance_percent(1_101, 1_000))

    def test_power_hit_curve_uses_ratio_and_strict_attack_advantage(self) -> None:
        self.assertEqual(4, power_hit_chance_percent(800, 1_000))
        self.assertEqual(48, power_hit_chance_percent(900, 1_000))
        self.assertEqual(93, power_hit_chance_percent(1_000, 1_000))
        self.assertEqual(94, power_hit_chance_percent(1_001, 1_000))
        self.assertEqual(94, power_hit_chance_percent(0, 0))

    def test_attack_and_defense_sheets_preserve_ordered_modifiers(self) -> None:
        self.assertEqual(
            1_002,
            weapon_attack_rating(
                161.9,
                70.8,
                90,
                170,
                flat_ocv=20,
                positive_ocv_percent=0.10,
                negative_ocv_percent=-0.05,
            ),
        )
        self.assertAlmostEqual(
            1_234.8,
            power_attack_rating(
                160.9,
                140,
                flat_ocv=10,
                positive_ocv_percent=0.05,
                negative_ocv_percent=-0.02,
            ),
            places=3,
        )
        self.assertEqual(
            488,
            defense_rating(
                150,
                140.6,
                flat_dcv=12.9,
                positive_dcv_percent=0.15,
                negative_dcv_percent=-0.06,
            ),
        )

    def test_weapon_bounds_apply_item_scaling_dual_wield_and_character_bonuses(self) -> None:
        bounds = weapon_damage_bounds(
            WeaponDamageInputs(
                base_minimum=8,
                base_maximum=16,
                primary_attribute=170,
                secondary_attribute=90,
                weapon_skill=161.9,
                weapon_mastery=70.8,
                item_minimum_flat=1,
                item_maximum_flat=2,
                item_damage_percent=0.10,
                character_damage_flat=3,
                character_damage_percent=0.15,
                dual_wielding=True,
            )
        )

        self.assertEqual((43, 97), bounds)

    def test_spell_bounds_and_centered_roll_are_deterministic(self) -> None:
        self.assertEqual((59, 131), spell_amount_bounds(10, 20, 170, 90, 161.9))
        self.assertAlmostEqual(28.5, triangular_roll(24, 33, 0.25, 0.75))
        self.assertAlmostEqual(24.0, triangular_roll(24, 33, 0.0, 0.0))

    def test_resistance_cap_protection_and_armor_piercing_match_source_order(self) -> None:
        self.assertEqual(
            75.0,
            effective_resistance(
                60,
                protection_trains=30,
                incoming_trains=20,
                protection_applies=True,
            ),
        )
        self.assertEqual(-10.0, effective_resistance(-10))
        self.assertAlmostEqual(35.0, resisted_amount(100, 75, 0.10), places=4)
        self.assertAlmostEqual(110.0, resisted_amount(100, -10))

    def test_odd_attributes_use_java_integer_division_in_attack_rating(self) -> None:
        self.assertEqual(85, weapon_attack_rating(0, 0, 1, 171))
        self.assertEqual(70.0, power_attack_rating(0, 141))

    def test_stack_order_precedes_rank_priority(self) -> None:
        self.assertFalse(
            should_overwrite_effect(
                incoming_order=1,
                existing_order=2,
                incoming_trains=100,
                existing_trains=1,
                priority=StackPriority.ALWAYS,
            )
        )
        self.assertTrue(
            should_overwrite_effect(
                incoming_order=2,
                existing_order=2,
                incoming_trains=20,
                existing_trains=20,
                priority=StackPriority.GREATER_THAN_OR_EQUAL,
            )
        )
        self.assertTrue(
            should_overwrite_effect(
                incoming_order=2,
                existing_order=2,
                incoming_trains=1,
                existing_trains=40,
                priority=StackPriority.GREATER_THAN,
                same_power=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
