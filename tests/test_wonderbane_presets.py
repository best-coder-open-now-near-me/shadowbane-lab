import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from shadowbane_lab.rollouts import (
    run_verified_duel,
    wonderbane_deflock,
    wonderbane_sundancer_deflock_matrix,
    wonderbane_sundancer_proc_assassin,
    wonderbane_sundancer_vs_deflock,
)
from shadowbane_lab.rollouts.__main__ import main
from shadowbane_lab.rollouts.duel import (
    BACKSTAB,
    MIND_SNARE,
    MIND_STRIKE,
    PSYCHIC_HEALING,
    SHADOW_BOLT,
    SHADOW_MANTLE,
    SHADOW_TOUCH,
)
from shadowbane_lab.rollouts.presets import (
    BLIND,
    BREAK_ENCHANTMENT,
    CONSECRATE_WEAPON,
    DULL_THE_BODY,
    DULL_THE_MIND,
    NEEDS_OF_THE_ONE,
    POISON_BLADE,
    PSYCHIC_SHIELD,
    PSYCHIC_SHOUT,
    SHADOW_OF_BLINDNESS,
    SHATTER_WILL,
    SILENCE,
    STEAL_BREATH,
    SURPASS_LIMITS,
)


class WonderBanePresetTests(unittest.TestCase):
    def test_sundancer_preset_compiles_the_full_archived_combat_loadout(self) -> None:
        preset = wonderbane_sundancer_proc_assassin()
        attributes = dict(preset.attribute_targets)
        intended = dict(preset.intended_power_ranks)
        enabled = set(preset.build.enabled_power_keys or ())

        self.assertEqual(165, attributes["intelligence"])
        self.assertEqual(102, attributes["dexterity"])
        self.assertEqual(85, attributes["constitution"])
        self.assertEqual(
            {"sun_dancer", "bounty_hunter", "saboteur", "undead_hunter"},
            set(preset.disciplines),
        )
        self.assertEqual(1, intended[BACKSTAB])
        self.assertEqual(40, intended[SHADOW_MANTLE])
        self.assertEqual(
            {
                SHADOW_BOLT,
                SHADOW_TOUCH,
                BACKSTAB,
                SHADOW_MANTLE,
                BLIND,
                SHADOW_OF_BLINDNESS,
                SILENCE,
                STEAL_BREATH,
                POISON_BLADE,
                CONSECRATE_WEAPON,
            },
            enabled,
        )
        self.assertIsNotNone(preset.combat_sheet.off_hand_weapon)
        self.assertIn("equipment.melee_weapon", preset.combat_sheet.tags)
        self.assertIn("power.stalk", preset.combat_sheet.tags)
        self.assertIn("poison_blade_proc", {item.effect_key for item in preset.initial_effects})
        self.assertTrue(preset.unresolved)

    def test_deflock_preset_compiles_the_full_archived_combat_loadout(self) -> None:
        preset = wonderbane_deflock()
        attributes = dict(preset.attribute_targets)
        skills = dict(preset.skill_ranks)
        enabled = set(preset.build.enabled_power_keys or ())

        self.assertEqual(150, attributes["intelligence"])
        self.assertEqual(110, attributes["constitution"])
        self.assertEqual(120, skills["warlockry"])
        self.assertEqual(140, skills["medium_armor"])
        self.assertEqual(95, skills["block"])
        self.assertEqual(
            {
                MIND_STRIKE,
                MIND_SNARE,
                PSYCHIC_HEALING,
                PSYCHIC_SHIELD,
                PSYCHIC_SHOUT,
                SHATTER_WILL,
                BREAK_ENCHANTMENT,
                DULL_THE_MIND,
                DULL_THE_BODY,
                SURPASS_LIMITS,
                NEEDS_OF_THE_ONE,
            },
            enabled,
        )
        self.assertEqual(
            {"blade_master", "traveler", "bounty_hunter"},
            set(preset.disciplines),
        )
        self.assertNotIn("discipline.commander", preset.tags)
        self.assertIn("psychic_shield", {item.effect_key for item in preset.initial_effects})
        self.assertTrue(preset.unresolved)

    def test_complete_matchup_uses_triggers_and_complete_sheet_attack_metrics(self) -> None:
        config = wonderbane_sundancer_vs_deflock(
            starting_distance=15.0,
            max_ticks=500,
            seed=14,
            assassin_starts_stealthed=True,
        )

        result = run_verified_duel(config).duel

        assassin, warlock = result.combatants
        actions = {item.action_key.split("@")[0] for item in assassin.actions}
        triggers = {item.trigger_key for item in assassin.triggers}
        self.assertIn(BACKSTAB, actions)
        self.assertIn("backstab_armed", triggers)
        self.assertGreater(assassin.attacks_attempted, 0)
        self.assertGreater(warlock.attacks_attempted, 0)
        self.assertEqual(
            assassin.attacks_attempted,
            assassin.weapon_hits + assassin.weapon_misses,
        )
        self.assertEqual(0, assassin.rejected_actions)
        self.assertEqual(0, warlock.rejected_actions)

    def test_matrix_crosses_distance_and_opener_with_reproducible_batches(self) -> None:
        first = wonderbane_sundancer_deflock_matrix(
            starting_distances=(6.0, 40.0),
            assassin_stealth_openers=(False, True),
            episodes=2,
            max_ticks=30,
            seed_start=9,
        )
        second = wonderbane_sundancer_deflock_matrix(
            starting_distances=(6.0, 40.0),
            assassin_stealth_openers=(False, True),
            episodes=2,
            max_ticks=30,
            seed_start=9,
        )

        self.assertEqual(first, second)
        self.assertEqual(4, len(first))
        self.assertEqual({False, True}, {cell.assassin_starts_stealthed for cell in first})
        self.assertTrue(all(cell.batch.episodes == 2 for cell in first))

    def test_guide_duel_cli_emits_bundled_matrix_without_profile_files(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                (
                    "--scenario",
                    "wonderbane-guide-duel",
                    "--matrix",
                    "--distances",
                    "6,15",
                    "--episodes",
                    "2",
                    "--max-ticks",
                    "20",
                    "--assassin-stealthed",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(2, len(payload))
        self.assertTrue(all(cell["assassin_starts_stealthed"] for cell in payload))
        self.assertTrue(all(cell["batch"]["episodes"] == 2 for cell in payload))


if __name__ == "__main__":
    unittest.main()
