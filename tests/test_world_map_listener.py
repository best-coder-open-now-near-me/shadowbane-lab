from __future__ import annotations

import unittest
from dataclasses import replace

from shadowbane_lab.client_input import (
    ForegroundWindowGuard,
    StaticWindowInspector,
    WindowBounds,
)
from shadowbane_lab.client_observation import NativeWorldMapObservation
from shadowbane_lab.travel import PhysicalPointerInteraction, WindowsGoChatCommandListener
from shadowbane_lab.travel.world_map_listener import (
    WorldMapPointerInteraction,
    _WorldMapCaptureSnapshot,
)
from tests.test_client_input_compiler import _load_profile
from tests.test_client_input_executor import _valid_snapshot


class WorldMapPointerCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        profile = _load_profile()
        self.window_handle = 0x1234
        self.process_id = 4320
        self.client_left = 140
        self.client_top = 90
        self.snapshot = replace(
            _valid_snapshot(),
            client_bounds=WindowBounds(
                left=self.client_left,
                top=self.client_top,
                width=profile.target.reference_width,
                height=profile.target.reference_height,
            ),
            process_id=self.process_id,
            window_handle=self.window_handle,
        )
        self.listener = WindowsGoChatCommandListener(
            ForegroundWindowGuard(profile, StaticWindowInspector(self.snapshot)),
            on_command=lambda _: None,
        )
        self.observation = NativeWorldMapObservation(
            is_open=True,
            left=324,
            top=0,
            right=1597,
            bottom=955,
            left_padding=3,
            top_padding=16,
            right_padding=3,
            bottom_padding=3,
            zoom=1.0,
            horizontal_pan=0,
            vertical_pan=0,
            world_length=131_072.0,
            world_width=98_304.0,
            snapshot_token="ab" * 12,
        )
        self.observed_at = 100.0
        self.listener._world_map_capture = _WorldMapCaptureSnapshot(
            observation=self.observation,
            observed_at=self.observed_at,
            client_left=self.client_left,
            client_top=self.client_top,
            process_id=self.process_id,
            window_handle=self.window_handle,
        )

    def test_fresh_projected_right_click_is_normalized_and_claimed(self) -> None:
        client_x = 900
        client_y = 420
        expected = self.observation.resolve_screen_point(client_x, client_y)
        physical = PhysicalPointerInteraction(
            self.client_left + client_x,
            self.client_top + client_y,
            "right",
        )

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertTrue(suppress)
        self.assertIsInstance(prepared, WorldMapPointerInteraction)
        assert isinstance(prepared, WorldMapPointerInteraction)
        self.assertEqual((client_x, client_y), (prepared.screen_x, prepared.screen_y))
        self.assertEqual(
            (physical.screen_x, physical.screen_y),
            (prepared.desktop_screen_x, prepared.desktop_screen_y),
        )
        self.assertAlmostEqual(expected.lt, prepared.lt)
        self.assertAlmostEqual(expected.lg, prepared.lg)
        self.assertEqual(self.window_handle, prepared.window_handle)
        self.assertEqual(self.process_id, prepared.process_id)

    def test_click_outside_projected_map_passes_through(self) -> None:
        physical = PhysicalPointerInteraction(
            self.client_left + 100,
            self.client_top + 100,
            "right",
        )

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_stale_map_sample_passes_through(self) -> None:
        physical = PhysicalPointerInteraction(
            self.client_left + 900,
            self.client_top + 420,
            "right",
        )

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + self.listener._WORLD_MAP_MAX_AGE_SECONDS + 0.01,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_different_foreground_window_passes_through(self) -> None:
        physical = PhysicalPointerInteraction(
            self.client_left + 900,
            self.client_top + 420,
            "right",
        )

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle + 1,
            now=self.observed_at + 0.05,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_left_click_on_map_passes_through_for_native_emblem_behavior(self) -> None:
        physical = PhysicalPointerInteraction(
            self.client_left + 900,
            self.client_top + 420,
            "left",
        )

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_captured_click_preserves_existing_pointer_callback_contract(self) -> None:
        delivered: list[PhysicalPointerInteraction] = []
        cancelled: list[str] = []
        listener = WindowsGoChatCommandListener(
            ForegroundWindowGuard(
                _load_profile(),
                StaticWindowInspector(self.snapshot),
            ),
            on_command=lambda _: None,
            on_interaction=lambda: cancelled.append("cancelled"),
            on_pointer=delivered.append,
        )
        listener._world_map_capture = self.listener._world_map_capture
        physical = PhysicalPointerInteraction(
            self.client_left + 900,
            self.client_top + 420,
            "right",
        )
        prepared, suppress = listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        listener._handle_pointer_interaction(prepared)

        self.assertTrue(suppress)
        self.assertEqual(["cancelled"], cancelled)
        self.assertEqual([prepared], delivered)


if __name__ == "__main__":
    unittest.main()
