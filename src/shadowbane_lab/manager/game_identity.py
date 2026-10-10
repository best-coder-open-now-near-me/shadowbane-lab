"""Bounded checks of an already selected game lifetime; never discover windows."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Protocol


class GameIdentityGuard(Protocol):
    def require_current(self) -> None: ...
    def close(self) -> None: ...


class GameIdentityChanged(RuntimeError):
    """The immutable game process/window is gone, replaced, or unverifiable."""


class _WindowsGameIdentityApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("exact game identity requires Windows")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (
            ctypes.POINTER(wintypes.FILETIME),
        ) * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.user.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD

    def open_process(self, pid: int) -> int:
        handle = self.kernel.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def running(self, handle: int) -> bool:
        result = self.kernel.WaitForSingleObject(handle, 0)
        if result == 0:
            return False
        if result != 258:
            raise ctypes.WinError(ctypes.get_last_error())
        return True

    def creation(self, handle: int) -> int:
        values = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime

    def window_process(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            return 0
        return pid.value

    def close(self, handle: int) -> None:
        if not self.kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


class WindowsGameIdentityGuard:
    """Retain one process handle and check only its exact HWND/lifetime.

    Manifest/path discovery happens before construction. A minimized/background
    window needs no geometry or title query. A lost binding is latched: this guard
    cannot open another handle or adopt a replacement process/window.
    """

    def __init__(self, binding, *, _api=None) -> None:
        self.pid = binding.game_process_id
        self.creation = binding.game_process_started_at_100ns
        self.window = binding.game_window_handle
        if any(
            type(value) is not int or value <= 0 for value in (self.pid, self.creation, self.window)
        ):
            raise ValueError("exact game PID, creation time and HWND must be positive")
        self._api = _WindowsGameIdentityApi() if _api is None else _api
        self._handle = None
        self._failed = False
        try:
            self._handle = self._api.open_process(self.pid)
            self.require_current()
        except BaseException:
            self.close()
            raise

    def require_current(self) -> None:
        if self._handle is None or self._failed:
            raise GameIdentityChanged("exact game identity guard is closed or revoked")
        try:
            if (
                self._api.window_process(self.window) != self.pid
                or not self._api.running(self._handle)
                or self._api.creation(self._handle) != self.creation
                or self._api.window_process(self.window) != self.pid
            ):
                raise GameIdentityChanged("immutable game process/window identity changed")
        except (OSError, RuntimeError):
            self._failed = True
            raise

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            self._api.close(handle)
