import unittest

from shadowbane_lab.client_extension.runtime_drift import (
    assess_runtime_drift_paths,
    is_reviewed_runtime_mutable_path,
)


class RuntimeDriftPolicyTests(unittest.TestCase):
    def test_reviewed_exact_and_per_instance_paths_are_allowed_case_insensitively(self) -> None:
        self.assertTrue(is_reviewed_runtime_mutable_path("Config/ArcanePref.cfg"))
        self.assertTrue(
            is_reviewed_runtime_mutable_path(
                "config/screen_game_1024x768_primary_WonderBane.cfg"
            )
        )

    def test_similar_but_broader_paths_are_not_allowed(self) -> None:
        for path in (
            "config/arcanepref.cfg.bak",
            "config/nested/screen_game_1024x768_wonderbane.cfg",
            "config/screen_game_wonderbane.cfg/extra",
            "logs/other.txt",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_reviewed_runtime_mutable_path(path))

    def test_assessment_retains_drift_kind_and_canonical_order(self) -> None:
        assessment = assess_runtime_drift_paths(
            added=("logs/debug.txt", "mods/unreviewed.dll"),
            missing=("sb.exe", "doublefusion/dftm.dat"),
            changed=("z-last.dat", "config/arcanepref.cfg", "a-first.dat"),
        )

        self.assertFalse(assessment.allowed)
        self.assertEqual(("mods/unreviewed.dll",), assessment.unexpected_added)
        self.assertEqual(("sb.exe",), assessment.unexpected_missing)
        self.assertEqual(
            ("a-first.dat", "z-last.dat"),
            assessment.unexpected_changed,
        )
        self.assertEqual(
            (
                "added:mods/unreviewed.dll",
                "missing:sb.exe",
                "changed:a-first.dat",
                "changed:z-last.dat",
            ),
            assessment.labeled_paths(),
        )

    def test_invalid_or_case_colliding_paths_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "relative_path"):
            assess_runtime_drift_paths(added=("../escape",))
        with self.assertRaisesRegex(ValueError, "case-insensitively unique"):
            assess_runtime_drift_paths(
                changed=("Config/ArcanePref.cfg", "config/arcanepref.cfg")
            )


if __name__ == "__main__":
    unittest.main()
