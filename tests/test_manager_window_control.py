import unittest
from dataclasses import FrozenInstanceError, replace

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager.model import ClientInstanceSnapshot, ClientRegistrySnapshot
from shadowbane_lab.manager.window_control import (
    SWP_NOACTIVATE,
    SWP_NOOWNERZORDER,
    SWP_NOZORDER,
    WINDOW_TILE_FLAGS,
    WM_CLOSE,
    AmbiguousClientIdentityError,
    GuardedWindowControl,
    StaleClientIdentityError,
    WindowActionError,
    WindowControlError,
    WindowRectangle,
)


def _client(
    *,
    instance_id: str = "client-primary",
    node_id: str = "gaming-pc-east",
    process_id: int = 101,
    process_started_at_100ns: int = 133_700_000_000_000_000,
    window_handle: int = 1001,
) -> ClientInstanceSnapshot:
    return ClientInstanceSnapshot(
        node_id=node_id,
        instance_id=instance_id,
        process_id=process_id,
        process_started_at_100ns=process_started_at_100ns,
        window_handle=window_handle,
        executable_name="sb.exe",
        executable_path=r"C:\Games\Shadowbane\sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(left=10, top=20, width=1280, height=720),
        dpi_scale=1.25,
        is_foreground=False,
        is_visible=True,
    )


def _registry(
    *clients: ClientInstanceSnapshot,
    node_id: str = "gaming-pc-east",
) -> ClientRegistrySnapshot:
    ordered = tuple(
        sorted(
            clients,
            key=lambda client: (
                client.node_id,
                client.executable_name.casefold(),
                client.process_id,
                client.process_started_at_100ns,
                client.window_handle,
                client.instance_id,
            ),
        )
    )
    return ClientRegistrySnapshot(node_id=node_id, clients=ordered)


class _SnapshotProvider:
    def __init__(self, *snapshots: object) -> None:
        self._snapshots = snapshots
        self.inspection_count = 0

    def inspect(self) -> object:
        index = min(self.inspection_count, len(self._snapshots) - 1)
        self.inspection_count += 1
        return self._snapshots[index]


class _RecordingWindowApi:
    def __init__(self, *, error: OSError | None = None) -> None:
        self.error = error
        self.position_calls: list[tuple[object, ...]] = []
        self.message_calls: list[tuple[int, int, int, int]] = []

    def set_window_pos(
        self,
        window_handle: int,
        insert_after: int,
        rectangle: WindowRectangle,
        flags: int,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.position_calls.append((window_handle, insert_after, rectangle, flags))

    def post_message(
        self,
        window_handle: int,
        message: int,
        wparam: int,
        lparam: int,
    ) -> None:
        if self.error is not None:
            raise self.error
        self.message_calls.append((window_handle, message, wparam, lparam))


class WindowRectangleTests(unittest.TestCase):
    def test_is_immutable_and_accepts_negative_multi_monitor_coordinates(self) -> None:
        rectangle = WindowRectangle(left=-1920, top=-20, width=960, height=540)

        self.assertEqual(
            (-1920, -20, 960, 540),
            (
                rectangle.left,
                rectangle.top,
                rectangle.width,
                rectangle.height,
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            rectangle.left = 0  # type: ignore[misc]

    def test_rejects_invalid_or_out_of_range_win32_values(self) -> None:
        cases = (
            {"left": True, "top": 0, "width": 10, "height": 10},
            {"left": -(2**31) - 1, "top": 0, "width": 10, "height": 10},
            {"left": 0, "top": 2**31, "width": 10, "height": 10},
            {"left": 0, "top": 0, "width": 0, "height": 10},
            {"left": 0, "top": 0, "width": 10, "height": -1},
            {"left": 0, "top": 0, "width": 2**31, "height": 10},
        )

        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    WindowRectangle(**values)


class GuardedWindowControlTests(unittest.TestCase):
    def test_tiles_current_identity_without_activation_or_z_order_changes(self) -> None:
        expected = _client()
        current = replace(
            expected,
            title="Shadowbane - Live",
            client_bounds=WindowBounds(left=50, top=60, width=800, height=600),
        )
        provider = _SnapshotProvider(_registry(current))
        native_api = _RecordingWindowApi()
        controller = GuardedWindowControl(provider, native_api)
        rectangle = WindowRectangle(left=-960, top=0, width=960, height=540)

        result = controller.tile(expected, rectangle)

        self.assertEqual(current, result)
        self.assertEqual(1, provider.inspection_count)
        self.assertEqual(
            [(1001, 0, rectangle, WINDOW_TILE_FLAGS)],
            native_api.position_calls,
        )
        self.assertEqual(
            0, WINDOW_TILE_FLAGS & ~(SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_NOZORDER)
        )
        self.assertTrue(WINDOW_TILE_FLAGS & SWP_NOACTIVATE)
        self.assertEqual([], native_api.message_calls)

    def test_revalidates_again_before_requesting_graceful_close(self) -> None:
        expected = _client()
        first = replace(expected, title="Before tile")
        second = replace(expected, title="Before close")
        provider = _SnapshotProvider(_registry(first), _registry(second))
        native_api = _RecordingWindowApi()
        controller = GuardedWindowControl(provider, native_api)

        controller.tile(expected, WindowRectangle(left=0, top=0, width=800, height=600))
        result = controller.request_graceful_close(expected)

        self.assertEqual(second, result)
        self.assertEqual(2, provider.inspection_count)
        self.assertEqual([(1001, WM_CLOSE, 0, 0)], native_api.message_calls)

    def test_missing_client_fails_closed_without_a_native_call(self) -> None:
        expected = _client()
        provider = _SnapshotProvider(_registry())
        native_api = _RecordingWindowApi()
        controller = GuardedWindowControl(provider, native_api)

        with self.assertRaisesRegex(StaleClientIdentityError, "no longer registered"):
            controller.tile(
                expected,
                WindowRectangle(left=0, top=0, width=800, height=600),
            )

        self.assertEqual([], native_api.position_calls)
        self.assertEqual([], native_api.message_calls)

    def test_reused_process_or_window_identity_fails_closed(self) -> None:
        expected = _client()
        replacements = (
            _client(
                instance_id="client-restarted",
                process_started_at_100ns=expected.process_started_at_100ns + 1,
            ),
            _client(instance_id="client-new-window", window_handle=2002),
        )

        for current in replacements:
            with self.subTest(current=current.instance_id):
                native_api = _RecordingWindowApi()
                controller = GuardedWindowControl(
                    _SnapshotProvider(_registry(current)),
                    native_api,
                )
                with self.assertRaises(StaleClientIdentityError):
                    controller.request_graceful_close(expected)
                self.assertEqual([], native_api.message_calls)

    def test_duplicate_process_or_window_mapping_is_ambiguous(self) -> None:
        expected = _client()
        duplicate_pid = _client(
            instance_id="client-other",
            window_handle=2002,
            process_started_at_100ns=expected.process_started_at_100ns + 1,
        )
        duplicate_window = _client(
            instance_id="client-other-window",
            process_id=202,
            process_started_at_100ns=expected.process_started_at_100ns + 2,
        )

        for other in (duplicate_pid, duplicate_window):
            with self.subTest(other=other.instance_id):
                native_api = _RecordingWindowApi()
                controller = GuardedWindowControl(
                    _SnapshotProvider(_registry(expected, other)),
                    native_api,
                )
                with self.assertRaises(AmbiguousClientIdentityError):
                    controller.request_graceful_close(expected)
                self.assertEqual([], native_api.message_calls)

    def test_wrong_node_and_malformed_provider_result_fail_closed(self) -> None:
        expected = _client()
        values = (
            _registry(node_id="gaming-pc-west"),
            object(),
        )

        for snapshot in values:
            with self.subTest(snapshot=snapshot):
                native_api = _RecordingWindowApi()
                controller = GuardedWindowControl(_SnapshotProvider(snapshot), native_api)
                with self.assertRaises((StaleClientIdentityError, WindowControlError)):
                    controller.request_graceful_close(expected)
                self.assertEqual([], native_api.message_calls)

    def test_native_errors_are_wrapped_after_identity_authorization(self) -> None:
        expected = _client()
        provider = _SnapshotProvider(_registry(expected))
        native_api = _RecordingWindowApi(error=OSError(5, "access denied"))
        controller = GuardedWindowControl(provider, native_api)

        with self.assertRaisesRegex(WindowActionError, "graceful close") as context:
            controller.request_graceful_close(expected)

        self.assertIsInstance(context.exception.__cause__, OSError)
        self.assertEqual(1, provider.inspection_count)


if __name__ == "__main__":
    unittest.main()
