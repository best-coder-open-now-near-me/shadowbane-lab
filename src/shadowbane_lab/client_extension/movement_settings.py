"""Open the selected client's native settings UI without an automation lease.

The registered window message carries no movement, camera or settings payload.
Native focus safety remains in the owning client.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from shadowbane_lab.graphics_lab.control import (
    GraphicsControlTarget,
    target_process_is_alive,
    verify_target_identity,
)

SETTINGS_MESSAGE = "ShadowbaneLab.NativeMovement.OpenSettings.v1"


class _WindowsSettings:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Native movement settings require Windows")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = (self.callback_type, wintypes.LPARAM)
        self.user.EnumWindows.restype = wintypes.BOOL
        self.user.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user.RegisterWindowMessageW.argtypes = (wintypes.LPCWSTR,)
        self.user.RegisterWindowMessageW.restype = wintypes.UINT
        self.user.AllowSetForegroundWindow.argtypes = (wintypes.DWORD,)
        self.user.AllowSetForegroundWindow.restype = wintypes.BOOL
        self.user.SendMessageTimeoutW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        )
        self.user.SendMessageTimeoutW.restype = wintypes.LPARAM
        self.message = self.user.RegisterWindowMessageW(SETTINGS_MESSAGE)
        if not self.message:
            raise ctypes.WinError(ctypes.get_last_error())

    def windows(self, process_id: int) -> tuple[int, ...]:
        found: list[int] = []

        @self.callback_type
        def collect(window: int, _data: int) -> bool:
            pid = wintypes.DWORD()
            if self.user.GetWindowThreadProcessId(window, ctypes.byref(pid)):
                if pid.value == process_id:
                    found.append(int(window))
            return True

        if not self.user.EnumWindows(collect, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return tuple(found)

    def open(self, window: int, process_id: int, creation: int) -> bool:
        # This call follows an explicit Graphics Lab button click. It lets the
        # selected client show its owned panel; it grants no movement authority.
        self.user.AllowSetForegroundWindow(process_id)
        result = ctypes.c_size_t()
        sent = self.user.SendMessageTimeoutW(
            window,
            self.message,
            creation & 0xFFFFFFFF,
            creation >> 32,
            0x0001 | 0x0002,
            750,
            ctypes.byref(result),
        )
        return bool(sent and result.value == 1)


def open_native_movement_settings(target: GraphicsControlTarget) -> None:
    if not verify_target_identity(target):
        raise RuntimeError("Selected client identity changed; refresh the client list")
    windows = _WindowsSettings()
    # The native receiver validates its own HWND chain and full creation time.
    # Other windows of the same process do not handle this message. No gameplay
    # command, settings payload or host lease is sent through this UI request.
    for window in windows.windows(target.process_id):
        if not target_process_is_alive(target):
            raise RuntimeError("Selected client exited before opening settings")
        if windows.open(window, target.process_id, target.process_creation_filetime_utc):
            if not target_process_is_alive(target):
                raise RuntimeError("Selected client exited while opening settings")
            return
    raise RuntimeError(
        "Native movement settings are unavailable in this client's installed package, "
        "or the client is in a text/modal screen. Return to gameplay and try again."
    )
