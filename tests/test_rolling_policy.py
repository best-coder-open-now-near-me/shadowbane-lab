import unittest

from shadowbane_lab.equipment.rolling_policy import RollDisposition, evaluate_roll_tiers


class RollingPolicyTests(unittest.TestCase):
    def test_unknown_overrides_known_low_tier(self):
        for prefix, suffix in ((None, None), (None, 1), (2, None), (None, 4)):
            with self.subTest(prefix=prefix, suffix=suffix):
                self.assertEqual(
                    RollDisposition.KEEP,
                    evaluate_roll_tiers(prefix, suffix, completed=True),
                )

    def test_only_confirmed_low_tiers_are_excluded(self):
        for prefix, suffix in ((1, 2), (3, 1), (2, 4), (0, 1), (2, 0)):
            self.assertEqual(
                RollDisposition.EXCLUDE,
                evaluate_roll_tiers(prefix, suffix, completed=True),
            )
        for prefix, suffix in ((3, 3), (3, 4), (4, 4), (5, 3), (0, 0), (0, 4)):
            self.assertEqual(
                RollDisposition.KEEP,
                evaluate_roll_tiers(prefix, suffix, completed=True),
            )

    def test_hidden_cooking_modifiers_never_authorize_disposal(self):
        for prefix, suffix in ((1, 2), (None, None), (0, 0)):
            self.assertEqual(
                RollDisposition.WAIT,
                evaluate_roll_tiers(prefix, suffix, completed=False),
            )

    def test_invalid_tiers_fail_without_a_disposition(self):
        for invalid in (True, False, -1, 1.0, "1"):
            with self.assertRaises(ValueError):
                evaluate_roll_tiers(invalid, 3, completed=True)
        with self.assertRaises(ValueError):
            evaluate_roll_tiers(1, 2, completed=1)
