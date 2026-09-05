import math
import unittest
from dataclasses import replace

from shadowbane_lab.graphics_lab.effects import CONFIG, PRESETS, EffectsConfig


class EffectsConfigurationTests(unittest.TestCase):
    def test_native_layout_roundtrip(self):
        self.assertEqual(CONFIG.size, 84)
        for preset in PRESETS.values():
            decoded = EffectsConfig(*CONFIG.unpack(preset.pack()))
            for field in ("flags", "attachment", "burst_count", "particle_budget", "sample_budget"):
                self.assertEqual(getattr(decoded, field), getattr(preset, field))
            self.assertAlmostEqual(decoded.opacity, preset.opacity)

    def test_reject_invalid_settings(self):
        for change in (
            {"flags": 16},
            {"attachment": 2},
            {"burst_count": 257},
            {"particle_budget": 1025},
            {"sample_budget": 1},
            {"rate": math.nan},
            {"lifetime": 0},
            {"sample_distance": 0},
            {"width": math.inf},
            {"opacity": -1},
            {"height": 11},
            {"burst": True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(EffectsConfig(), **change).pack()

    def test_default_is_disabled_and_presets_are_explicit(self):
        self.assertEqual(EffectsConfig().flags, 0)
        self.assertTrue(PRESETS["Azure wake"].flags & 4)
        self.assertEqual(PRESETS["Burst only"].flags, 1)


if __name__ == "__main__":
    unittest.main()
