from __future__ import annotations

import unittest

from shadowbane_lab.progression import (
    CharacterProgression,
    IllegalProgressionError,
    ProcLoadout,
    StatLine,
    TrainingInvestment,
    ability_points_for_level,
    audit_proc_assassin_training,
    estimate_procs,
    evaluate_progression,
    irekei_proc_assassin_roadmap,
    load_wonderbane_irekei_proc_profile,
    rogue_training_points_for_level,
)


class ProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_wonderbane_irekei_proc_profile()

    def test_current_level_budgets_match_server_tables(self) -> None:
        self.assertEqual(0, ability_points_for_level(1))
        self.assertEqual(90, ability_points_for_level(19))
        self.assertEqual(190, ability_points_for_level(59))
        self.assertEqual(206, ability_points_for_level(75))
        self.assertEqual(36, rogue_training_points_for_level(10))
        self.assertEqual(526, rogue_training_points_for_level(59))
        self.assertEqual(588, rogue_training_points_for_level(75))

    def test_level_59_current_cap_plan_is_legal_and_complete(self) -> None:
        result = evaluate_progression(
            self.profile,
            CharacterProgression(
                level=59,
                attribute_adjustments=StatLine(0, 65, 45, 55, 25),
                rune_keys=("sun_dancer", "saboteur"),
                other_ability_points_spent=15,
                training=(TrainingInvestment("reserved", 526),),
            ),
        )
        self.assertEqual(StatLine(45, 150, 95, 110, 50), result.stats)
        self.assertEqual(StatLine(85, 150, 95, 110, 85), result.caps)
        self.assertEqual(0, result.ability_points_remaining)
        self.assertEqual(0, result.training_points_remaining)
        self.assertEqual(1771, result.health)
        self.assertEqual(549, result.mana)
        self.assertEqual(407, result.stamina)
        self.assertEqual(300, result.baseline_defense)

    def test_level_59_rejects_third_discipline(self) -> None:
        with self.assertRaisesRegex(IllegalProgressionError, "only 2 disciplines"):
            evaluate_progression(
                self.profile,
                CharacterProgression(
                    level=59,
                    rune_keys=("sun_dancer", "saboteur", "bounty_hunter"),
                ),
            )

    def test_stat_rune_requires_pre_rune_stat(self) -> None:
        with self.assertRaisesRegex(IllegalProgressionError, "requires intelligence 120"):
            evaluate_progression(
                self.profile,
                CharacterProgression(level=59, rune_keys=("intelligence_of_the_gods",)),
            )

    def test_proc_estimate_rewards_intelligence(self) -> None:
        loadout = ProcLoadout(
            weapon_key="generic_fast_fist",
            proc_effect_keys=("tier_three_mental", "poison_blade_rank_40"),
        )
        balanced = estimate_procs(self.profile, StatLine(45, 150, 95, 110, 50), loadout)
        high_int = estimate_procs(self.profile, StatLine(35, 102, 85, 165, 10), loadout)
        self.assertEqual(2.0, balanced.delay_seconds_per_hand)
        self.assertEqual(1.0, balanced.successful_hits_per_second)
        self.assertAlmostEqual(0.1, balanced.expected_triggers_per_second)
        self.assertGreater(
            high_int.expected_proc_damage_per_second,
            balanced.expected_proc_damage_per_second,
        )

    def test_level_59_roadmap_preserves_remaining_level_75_trains(self) -> None:
        roadmap = irekei_proc_assassin_roadmap(self.profile, level=59)
        self.assertEqual(526, roadmap.training_points_now)
        self.assertEqual(588, roadmap.training_points_at_75)
        self.assertEqual(("sun_dancer", "saboteur"), roadmap.disciplines_now)
        self.assertEqual("bounty_hunter", roadmap.third_discipline_at_70)
        self.assertEqual("poison_blade", roadmap.power_targets[0].key)
        self.assertEqual(
            StatLine(35, 105, 85, 165, 15),
            roadmap.candidates[0].stats,
        )

    def test_observed_creation_traits_establish_godly_intelligence_legality(self) -> None:
        brilliant = self.profile.rune("brilliant_mind")
        apprentice = self.profile.rune("wizards_apprentice")
        godly = self.profile.rune("intelligence_of_the_gods")

        observed_caps = self.profile.identity.race_caps.plus(
            brilliant.cap_grants,
            apprentice.cap_grants,
        )
        final_caps = observed_caps.plus(godly.cap_grants)
        self.assertEqual(StatLine(85, 130, 85, 130, 80), observed_caps)
        self.assertEqual(StatLine(85, 130, 85, 170, 80), final_caps)
        self.assertEqual(120, godly.minimum_stats.intelligence)
        self.assertEqual(15, godly.cost)

    def test_live_training_audit_finds_only_four_power_gaps(self) -> None:
        roadmap = irekei_proc_assassin_roadmap(self.profile, level=59)
        audit = audit_proc_assassin_training(
            roadmap,
            skill_ranks={
                "light_armor": 110,
                "dodge": 46,
                "shadowmastery": 100,
                "unarmed_mastery": 110,
                "unarmed": 110,
            },
            power_ranks={
                "poison_blade": 40,
                "cloak_of_shadows": 40,
                "shadow_touch": 40,
                "shadow_mantle": 24,
                "sneak": 20,
                "blindness": 12,
                "plague_of_blindness": 1,
                "steal_breath": 1,
                "silence": 1,
                "backstab": 1,
                "shadow_bolt": 2,
                "slayers_focus": 1,
            },
            unspent_training_points=113,
        )

        power_gaps = {item.key: item.rank_gap for item in audit.power_targets if item.rank_gap}
        skill_gaps = {item.key: item.rank_gap for item in audit.skill_targets if item.rank_gap}
        self.assertEqual(
            {
                "shadow_mantle": 16,
                "sneak": 1,
                "plague_of_blindness": 29,
                "shadow_bolt": 3,
            },
            power_gaps,
        )
        self.assertEqual(49, audit.power_rank_increments_needed)
        self.assertEqual(64, audit.power_training_reserve_after_targets)
        self.assertEqual(
            {"unarmed": 51, "light_armor": 51, "dodge": 54},
            skill_gaps,
        )


if __name__ == "__main__":
    unittest.main()
