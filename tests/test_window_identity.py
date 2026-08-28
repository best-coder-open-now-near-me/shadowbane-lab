import ctypes
import unittest
from ctypes import wintypes
from dataclasses import replace

from shadowbane_lab.client_input import WindowBounds, WindowSnapshot
from shadowbane_lab.client_input.window import _WindowsWindowApi


def _snapshot(**changes: object) -> WindowSnapshot:
    snapshot = WindowSnapshot(
        executable_name="Shadowbane.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(left=10, top=20, width=1280, height=720),
        dpi_scale=1.0,
        is_foreground=True,
        is_visible=True,
    )
    return replace(snapshot, **changes)


class FakeUser32:
    def GetWindowTextLengthW(self, _window: int) -> int:
        return len("Shadowbane")

    def GetWindowTextW(self, _window: int, buffer: object, _length: int) -> int:
        buffer.value = "Shadowbane"
        return len(buffer.value)

    def GetClientRect(self, _window: int, rect: object) -> bool:
        rect._obj.left = 0
        rect._obj.top = 0
        rect._obj.right = 1280
        rect._obj.bottom = 720
        return True

    def ClientToScreen(self, _window: int, _point: object) -> bool:
        return True

    def GetWindowThreadProcessId(self, _window: int, process_id: object) -> int:
        process_id._obj.value = 2468
        return 1

    def IsWindowVisible(self, _window: int) -> bool:
        return True


class FakeKernel32:
    def __init__(self, *, process_times_available: bool = True) -> None:
        self.process_times_available = process_times_available
        self.opened_handle = 9001
        self.process_times_handles: list[int] = []
        self.closed_handles: list[int] = []

    def OpenProcess(self, _access: int, _inherit: bool, _process_id: int) -> int:
        return self.opened_handle

    def QueryFullProcessImageNameW(
        self,
        _process: int,
        _flags: int,
        buffer: object,
        path_length: object,
    ) -> bool:
        buffer.value = r"C:\Games\Shadowbane.exe"
        path_length._obj.value = len(buffer.value)
        return True

    def GetProcessTimes(
        self,
        process: int,
        creation_time: object,
        _exit_time: object,
        _kernel_time: object,
        _user_time: object,
    ) -> bool:
        self.process_times_handles.append(process)
        if not self.process_times_available:
            return False
        creation_time._obj.dwHighDateTime = 0x01234567
        creation_time._obj.dwLowDateTime = 0x89ABCDEF
        return True

    def CloseHandle(self, process: int) -> bool:
        self.closed_handles.append(process)
        return True


def _window_api(kernel32: FakeKernel32) -> _WindowsWindowApi:
    api = object.__new__(_WindowsWindowApi)
    api._ctypes = ctypes
    api._wintypes = wintypes
    api._user32 = FakeUser32()
    api._kernel32 = kernel32
    return api


class WindowSnapshotIdentityTests(unittest.TestCase):
    def test_identity_fields_default_to_none_for_existing_constructors(self) -> None:
        snapshot = _snapshot()

        self.assertIsNone(snapshot.window_handle)
        self.assertIsNone(snapshot.process_started_at_100ns)

    def test_identity_fields_require_positive_non_boolean_integers(self) -> None:
        invalid_values = (True, False, 0, -1, 1.5, "1")
        for field in ("window_handle", "process_started_at_100ns"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        _snapshot(**{field: value})

    def test_identity_fields_accept_positive_integers(self) -> None:
        snapshot = _snapshot(window_handle=12345, process_started_at_100ns=67890)

        self.assertEqual(12345, snapshot.window_handle)
        self.assertEqual(67890, snapshot.process_started_at_100ns)


class WindowsWindowApiIdentityTests(unittest.TestCase):
    def test_live_snapshot_uses_same_process_handle_for_creation_time(self) -> None:
        kernel32 = FakeKernel32()
        api = _window_api(kernel32)

        snapshot = api.snapshot(12345, foreground_window=12345)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(12345, snapshot.window_handle)
        self.assertEqual(2468, snapshot.process_id)
        self.assertEqual(0x0123456789ABCDEF, snapshot.process_started_at_100ns)
        self.assertEqual([kernel32.opened_handle], kernel32.process_times_handles)
        self.assertEqual([kernel32.opened_handle], kernel32.closed_handles)

    def test_live_snapshot_fails_closed_when_creation_time_is_unavailable(self) -> None:
        kernel32 = FakeKernel32(process_times_available=False)
        api = _window_api(kernel32)

        snapshot = api.snapshot(12345, foreground_window=12345)

        self.assertIsNone(snapshot)
        self.assertEqual([kernel32.opened_handle], kernel32.process_times_handles)
        self.assertEqual([kernel32.opened_handle], kernel32.closed_handles)


if __name__ == "__main__":
    unittest.main()
