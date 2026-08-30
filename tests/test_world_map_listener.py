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

    def _physical(self, button: str, *, client_x: int = 900, client_y: int = 420):
        return PhysicalPointerInteraction(
            self.client_left + client_x,
            self.client_top + client_y,
            button,
        )

    def test_fresh_projected_right_click_is_normalized_and_claimed(self) -> None:
        client_x = 900
        client_y = 420
        expected = self.observation.resolve_screen_point(client_x, client_y)
        physical = self._physical("right", client_x=client_x, client_y=client_y)

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertTrue(suppress)
        self.assertIsInstance(prepared, WorldMapPointerInteraction)
        assert isinstance(prepared, WorldMapPointerInteraction)
        self.assertEqual("right", prepared.button)
        self.assertEqual("right", prepared.physical_button)
        self.assertEqual((client_x, client_y), (prepared.screen_x, prepared.screen_y))
        self.assertEqual(
            (physical.screen_x, physical.screen_y),
            (prepared.desktop_screen_x, prepared.desktop_screen_y),
        )
        self.assertAlmostEqual(expected.lt, prepared.lt)
        self.assertAlmostEqual(expected.lg, prepared.lg)
        self.assertEqual(self.window_handle, prepared.window_handle)
        self.assertEqual(self.process_id, prepared.process_id)

    def test_left_click_on_projected_world_is_claimed_for_emblem_selection(self) -> None:
        physical = self._physical("left")

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertTrue(suppress)
        self.assertIsInstance(prepared, WorldMapPointerInteraction)
        assert isinstance(prepared, WorldMapPointerInteraction)
        self.assertEqual("left", prepared.physical_button)
        self.assertEqual(
            "right",
            prepared.button,
            "the existing command queue routes map destinations through right-click",
        )
        self.assertEqual(1, self.listener.diagnostics["world_map_captured_left_clicks"])

    def test_left_click_outside_projected_map_passes_through(self) -> None:
        physical = self._physical("left", client_x=100, client_y=100)

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_stale_map_sample_passes_through(self) -> None:
        physical = self._physical("left")

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + self.listener._WORLD_MAP_MAX_AGE_SECONDS + 0.01,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_different_foreground_window_passes_through(self) -> None:
        physical = self._physical("left")

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle + 1,
            now=self.observed_at + 0.05,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_middle_click_on_map_passes_through(self) -> None:
        physical = self._physical("middle")

        prepared, suppress = self.listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        self.assertFalse(suppress)
        self.assertIs(physical, prepared)

    def test_matching_left_button_up_is_consumed_once(self) -> None:
        self.listener._arm_button_up_suppression("left")

        self.assertTrue(self.listener._consume_button_up_suppression("left"))
        self.assertFalse(self.listener._consume_button_up_suppression("left"))
        self.assertEqual(1, self.listener.diagnostics["suppressed_left_button_ups"])

    def test_captured_left_click_preserves_pointer_callback_contract(self) -> None:
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
        physical = self._physical("left")
        prepared, suppress = listener._prepare_pointer_interaction(
            physical,
            foreground_window_handle=self.window_handle,
            now=self.observed_at + 0.05,
        )

        listener._handle_pointer_interaction(prepared)

        self.assertTrue(suppress)
        self.assertEqual([prepared], delivered)
        self.assertEqual("right", delivered[0].button)
        self.assertEqual(["cancelled"], cancelled)


if __name__ == "__main__":
    unittest.main()
