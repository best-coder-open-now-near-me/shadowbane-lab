import unittest
from dataclasses import replace

from shadowbane_lab.client_action import (
    ClientActionBoundary,
    ClientActionRunner,
    WorldMapDestinationClickAction,
)
from shadowbane_lab.client_extension import (
    EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
    ExtensionEventChannelHeader,
    ExtensionEventChannelSnapshot,
    ExtensionPointerButton,
    ExtensionWorldMapDestinationEvent,
)
from shadowbane_lab.client_input import (
    ForegroundWindowGuard,
    GuardedInputExecutor,
    RecordingInputBackend,
    StaticWindowInspector,
    WindowBounds,
    WindowSnapshot,
    load_calibration,
)
from shadowbane_lab.client_input.stop import EventEmergencyStop
from shadowbane_lab.client_observation import NativeWorldMapObservation

PROCESS_ID = 42
PROCESS_CREATION = 1_000
WINDOW_HANDLE = 9_001


class FakeWorldMap:
    process_id = PROCESS_ID

    def __init__(self, observation: NativeWorldMapObservation) -> None:
        self.observation = observation

    def observe(self) -> NativeWorldMapObservation:
        return self.observation


class ActionEventSource:
    process_id = PROCESS_ID
    process_creation_filetime_utc = PROCESS_CREATION

    def __init__(
        self,
        backend: RecordingInputBackend,
        observation: NativeWorldMapObservation,
        *,
        mismatch_pixel: bool = False,
        dropped_after_input: bool = False,
    ) -> None:
        self.backend = backend
        self.observation = observation
        self.mismatch_pixel = mismatch_pixel
        self.dropped_after_input = dropped_after_input

    def snapshot(self) -> ExtensionEventChannelSnapshot:
        if not self.backend.invocations:
            return ExtensionEventChannelSnapshot(self._header(), ())
        invocation = self.backend.invocations[-1]
        point = invocation.point  # type: ignore[union-attr]
        destination = self.observation.resolve_screen_point(point.x, point.y)
        event = ExtensionWorldMapDestinationEvent(
            sequence=1,
            process_id=PROCESS_ID,
            process_creation_filetime_utc=PROCESS_CREATION,
            captured_at_filetime_utc=PROCESS_CREATION + 1,
            window_handle=WINDOW_HANDLE,
            button=ExtensionPointerButton.RIGHT,
            lt=destination.lt,
            lg=destination.lg,
            snapshot_token="0123456789abcdef",
            desktop_screen_x=point.x + (1 if self.mismatch_pixel else 0),
            desktop_screen_y=point.y,
            client_x=point.x,
            client_y=point.y,
        )
        return ExtensionEventChannelSnapshot(
            self._header(
                write_sequence=1,
                dropped_event_count=1 if self.dropped_after_input else 0,
            ),
            (event,),
        )

    @staticmethod
    def _header(
        *,
        write_sequence: int = 0,
        dropped_event_count: int = 0,
    ) -> ExtensionEventChannelHeader:
        return ExtensionEventChannelHeader(
            process_id=PROCESS_ID,
            process_creation_filetime_utc=PROCESS_CREATION,
            write_sequence=write_sequence,
            read_sequence=0,
            dropped_event_count=dropped_event_count,
            producer_error=0,
            capability_flags=EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION,
        )


def _map(*, is_open: bool = True) -> NativeWorldMapObservation:
    return NativeWorldMapObservation(
        is_open=is_open,
        left=0,
        top=0,
        right=800,
        bottom=600,
        left_padding=10,
        top_padding=10,
        right_padding=10,
        bottom_padding=10,
        zoom=1.0,
        horizontal_pan=0,
        vertical_pan=0,
        world_length=160_000.0,
        world_width=120_000.0,
        snapshot_token="stable-map-projection",
    )


def _window() -> WindowSnapshot:
    return WindowSnapshot(
        executable_name="sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(0, 0, 1920, 955),
        dpi_scale=1.0,
        is_foreground=True,
        is_visible=True,
        process_id=PROCESS_ID,
        process_started_at_100ns=PROCESS_CREATION,
        window_handle=WINDOW_HANDLE,
    )


def _action(
    *,
    observation: NativeWorldMapObservation | None = None,
    mismatch_pixel: bool = False,
    dropped_after_input: bool = False,
):
    profile = load_calibration("configs/wonderbane-travel.template.json")
    backend = RecordingInputBackend()
    guard = ForegroundWindowGuard(
        profile,
        StaticWindowInspector(_window()),
        expected_process_id=PROCESS_ID,
        expected_process_started_at_100ns=PROCESS_CREATION,
        expected_window_handle=WINDOW_HANDLE,
    )
    active_map = observation or _map()
    events = ActionEventSource(
        backend,
        active_map,
        mismatch_pixel=mismatch_pixel,
        dropped_after_input=dropped_after_input,
    )
    executor = GuardedInputExecutor(
        guard=guard,
        backend=backend,
        stop_signal=EventEmergencyStop(),
        minimum_input_interval_ms=0,
    )
    return (
        WorldMapDestinationClickAction(
            window_guard=guard,
            world_map=FakeWorldMap(active_map),
            events=events,
            executor=executor,
            map_x_fraction=0.5,
            map_y_fraction=0.5,
            action_id="world-map-test-1",
        ),
        backend,
    )


class WorldMapDestinationClickActionTests(unittest.TestCase):
    def test_dispatches_one_right_click_and_verifies_exact_native_event(self) -> None:
        action, backend = _action()

        result = ClientActionRunner().run(action)

        self.assertTrue(result.succeeded)
        self.assertEqual(1, len(backend.invocations))
        self.assertEqual("right", backend.invocations[0].button.value)  # type: ignore[union-attr]
        self.assertEqual(
            ClientActionBoundary.EFFECT_OBSERVED,
            result.boundaries[-3].boundary,
        )
        effect = result.boundaries[-3].evidence
        self.assertEqual(1, effect["event_sequence"])
        self.assertAlmostEqual(80_000.0, effect["lt"], delta=250.0)  # type: ignore[arg-type]

    def test_closed_world_map_fails_before_input(self) -> None:
        action, backend = _action(observation=_map(is_open=False))

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("precondition_failed", result.terminal_reason)
        self.assertEqual((), backend.invocations)
        self.assertIn("world map is not open", result.boundaries[-1].detail)

    def test_mismatched_event_pixel_fails_the_effect_boundary(self) -> None:
        action, _ = _action(mismatch_pixel=True)

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("effect_observation_failed", result.terminal_reason)
        self.assertIn("desktop pixel", result.boundaries[-1].detail)

    def test_channel_loss_fails_instead_of_accepting_the_event(self) -> None:
        action, _ = _action(dropped_after_input=True)

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertIn("event loss", result.boundaries[-1].detail)

    def test_projection_change_between_precondition_and_dispatch_fails_closed(self) -> None:
        action, backend = _action()
        original_prepare = action.prepare

        def prepare_then_change_map():
            checkpoint = original_prepare()
            action._world_map.observation = replace(  # type: ignore[attr-defined]
                action._world_map.observation,  # type: ignore[attr-defined]
                snapshot_token="changed-map-projection",
            )
            return checkpoint

        action.prepare = prepare_then_change_map  # type: ignore[method-assign]

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("dispatch_failed", result.terminal_reason)
        self.assertEqual((), backend.invocations)


if __name__ == "__main__":
    unittest.main()
