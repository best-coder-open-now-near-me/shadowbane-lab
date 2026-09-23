import unittest

from shadowbane_lab.rollouts import progression_build as public_progression_build
from shadowbane_lab.rollouts.builds import progression_build
from shadowbane_lab.rollouts.duel import progression_build as duel_progression_build


class RolloutBuildOwnershipTests(unittest.TestCase):
    def test_existing_public_and_duel_imports_resolve_to_build_owner(self) -> None:
        self.assertIs(progression_build, public_progression_build)
        self.assertIs(progression_build, duel_progression_build)

    def test_progression_build_preserves_rank_caps_and_skills(self) -> None:
        assassin = progression_build("assassin", 75, 40)
        warlock = progression_build("warlock", 42, 20)

        assassin_ranks = dict(assassin.power_ranks)
        self.assertEqual(20, assassin_ranks["shadowbane.assassin.fade"])
        self.assertEqual(20, assassin_ranks["shadowbane.assassin.invisibility"])
        self.assertEqual(40, assassin_ranks["shadowbane.assassin.shadow_bolt"])
        self.assertEqual(
            (("shadowmastery", 200), ("sorcery", 1), ("stalk", 1)),
            assassin.skill_ranks,
        )
        self.assertEqual({20}, set(dict(warlock.power_ranks).values()))
        self.assertEqual((("warlockry", 200),), warlock.skill_ranks)

    def test_invalid_brackets_retain_fail_closed_errors(self) -> None:
        cases = (
            (("druid", 75, 40), "unsupported duel profession"),
            (("assassin", 0, 40), "level must be a positive integer"),
            (("warlock", 75, 41), "rank must be an integer between zero and 40"),
        )
        for arguments, message in cases:
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, message):
                progression_build(*arguments)


if __name__ == "__main__":
    unittest.main()
