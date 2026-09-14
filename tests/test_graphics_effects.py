import ctypes
import math
import struct
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

from shadowbane_lab.graphics_lab.effects import (
    CONFIG,
    HEADER,
    PRESETS,
    EffectsClient,
    EffectsConfig,
    presentation_status,
)
from shadowbane_lab.graphics_lab.effects_panel import EffectsPanel


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

    def test_disable_ignores_invalid_unapplied_edits(self):
        client = Mock()
        panel = SimpleNamespace(client=client, flags=[Mock()], status=Mock())
        EffectsPanel.disable(panel)
        sent = client.write.call_args.args[0]
        self.assertEqual(sent.flags, 0)
        sent.validate()

    def test_native_safety_status_layout_and_requested_enabled(self):
        data = bytearray(256)
        HEADER.pack_into(data, 0, 0x46584257, 1, 256, 123, 456, 2, 2, 0, 2)
        data[40:124] = EffectsConfig(flags=7).pack()
        struct.pack_into("<11I", data, 124, *([0] * 8), 1, 3, 42)
        buffer = ctypes.create_string_buffer(bytes(data))
        client = EffectsClient.__new__(EffectsClient)
        client.target = SimpleNamespace(process_id=123, process_creation_filetime_utc=456)
        client._address = ctypes.addressof(buffer)
        config, stats, desired, applied, error = client.read()
        self.assertEqual((config.flags, desired, applied, error), (7, 2, 2, 0))
        self.assertEqual(stats[8:], (1, 3, 42))
        self.assertIn("Enabled but suppressed", presentation_status(stats))
        self.assertIn("bursts are canceled", presentation_status(stats))
        self.assertIn("unavailable", presentation_status(tuple([0] * 8)))
        self.assertIn("unavailable", presentation_status(tuple([0] * 11)))

    def test_poll_discloses_suppression(self):
        stats = tuple([0] * 8 + [1, 3, 10])
        panel = SimpleNamespace(client=Mock(), status=Mock(), tab=Mock(), poll=Mock())
        panel.client.read.return_value = (EffectsConfig(flags=7), stats, 2, 2, 0)
        EffectsPanel.poll(panel)
        self.assertIn("Enabled but suppressed", panel.status.set.call_args.args[0])
        self.assertIn("Particles and trails are hidden", panel.status.set.call_args.args[0])

    def test_default_is_disabled_and_presets_are_explicit(self):
        self.assertEqual(EffectsConfig().flags, 0)
        self.assertTrue(PRESETS["Azure wake"].flags & 4)
        self.assertEqual(PRESETS["Burst only"].flags, 1)


if __name__ == "__main__":
    unittest.main()
