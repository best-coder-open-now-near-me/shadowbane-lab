import unittest

from shadowbane_lab.rollouts import (
    run_duel,
    wonderbane_deflock,
    wonderbane_sundancer_proc_assassin,
    wonderbane_sundancer_vs_deflock,
)
from shadowbane_lab.rollouts.duel import (
    BACKSTAB,
    FADE,
    INVISIBILITY,
    MIND_SNARE,
    MIND_STRIKE,
    PSYCHIC_HEALING,
    SHADOW_BOLT,
    SHADOW_MANTLE,
    SHADOW_TOUCH,
)


class WonderBanePresetTests(unittest.TestCase):
    def test_sundancer_preset_keeps_full_build_description_and_safe_subset(self) -> None:
        preset = wonderbane_sundancer_proc_assassin()
        attributes = dict(preset.attribute_targets)
        intended = dict(preset.intended_power_ranks)
        build = preset.build
        enabled = set(build.enabled_power_keys or ())

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
            {SHADOW_BOLT, SHADOW_TOUCH, BACKSTAB, SHADOW_MANTLE},
            enabled,
        )
        self.assertNotIn(FADE, enabled)
        self.assertNotIn(INVISIBILITY, enabled)
        self.assertTrue(preset.unresolved)

    def test_deflock_preset_records_sdr_shell_without_inventing_defense(self) -> None:
        preset = wonderbane_deflock()
        attributes = dict(preset.attribute_targets)
        skills = dict(preset.skill_ranks)
        build = preset.build
        enabled = set(build.enabled_power_keys or ())

        self.assertEqual(150, attributes["intelligence"])
        self.assertEqual(110, attributes["constitution"])
        self.assertEqual(120, skills["warlockry"])
        self.assertEqual(140, skills["medium_armor"])
        self.assertEqual(95, skills["block"])
        self.assertEqual(
            {MIND_STRIKE, MIND_SNARE, PSYCHIC_HEALING},
            enabled,
        )
        self.assertIn("discipline.commander", preset.tags)
        self.assertTrue(any("no chant bonus is assumed" in issue for issue in preset.unresolved))

    def test_concrete_matchup_smoke_runs_only_currently_executable_subset(self) -> None:
        config = wonderbane_sundancer_vs_deflock(
            starting_distance=15.0,
            max_ticks=10,
            seed=14,
            assassin_starts_stealthed=True,
        )

        result = run_duel(config)

        assassin, warlock = result.combatants
        self.assertIn(BACKSTAB, assassin.available_actions)
        self.assertNotIn(FADE, assassin.available_actions)
        self.assertIn(PSYCHIC_HEALING, warlock.available_actions)
        self.assertEqual(0, assassin.rejected_actions)
        self.assertEqual(0, warlock.rejected_actions)


if __name__ == "__main__":
    unittest.main()
