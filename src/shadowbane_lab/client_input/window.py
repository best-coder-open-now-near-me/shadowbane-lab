"""Foreground-window discovery and fail-closed target validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input.model import CalibrationProfile, WindowBounds


@dataclass(frozen=True, slots=True)
class WindowSnapshot:
    executable_name: str
    title: str
    client_bounds: WindowBounds
    dpi_scale: float
    is_foreground: bool
    is_visible: bool

    def __post_init__(self) -> None:
        if not self.executable_name.strip():
            raise ValueError("executable_name must be a non-empty string")
        if not isinstance(self.title, str):
            raise ValueError("title must be a string")
        if not isinstance(self.client_bounds, WindowBounds):
            raise ValueError("client_bounds must be WindowBounds")
        if isinstance(self.dpi_scale, bool) or not isinstance(self.dpi_scale, (int, float)):
            raise ValueError("dpi_scale must be numeric")
        if not isfinite(self.dpi_scale) or self.dpi_scale <= 0:
            raise ValueError("dpi_scale must be positive")
        if not isinstance(self.is_foreground, bool) or not isinstance(self.is_visible, bool):
            raise ValueError("window state flags must be booleans")


@runtime_checkable
class WindowInspector(Protocol):
    def inspect(self) -> WindowSnapshot | None: ...


class StaticWindowInspector:
    """Deterministic inspector for recording runs and tests."""

    def __init__(self, snapshot: WindowSnapshot | None) -> None:
        if snapshot is not None and not isinstance(snapshot, WindowSnapshot):
            raise ValueError("snapshot must be WindowSnapshot or None")
        self.snapshot = snapshot
        self.inspection_count = 0

    def inspect(self) -> WindowSnapshot | None:
        self.inspection_count += 1
        return self.snapshot


class WindowGuardError(RuntimeError):
    """Raised before input when the active window does not match calibration."""


class ForegroundWindowGuard:
    def __init__(self, profile: CalibrationProfile, inspector: WindowInspector) -> None:
        if not isinstance(profile, CalibrationProfile):
            raise ValueError("profile must be a CalibrationProfile")
        if not isinstance(inspector, WindowInspector):
            raise ValueError("inspector must implement WindowInspector")
        target = profile.target
        try:
            self._title_pattern = re.compile(target.title_pattern)
        except re.error as exc:
            raise ValueError("target title_pattern is not a valid regular expression") from exc
        self._profile = profile
        self._inspector = inspector
        self._allowed_executables = frozenset(name.casefold() for name in target.executable_names)

    @property
    def profile(self) -> CalibrationProfile:
        return self._profile

    def require_target(self) -> WindowSnapshot:
        snapshot = self._inspector.inspect()
        if snapshot is None:
            raise WindowGuardError("no foreground window could be inspected")
        if not snapshot.is_foreground:
            raise WindowGuardError("calibrated client is not the foreground window")
        if not snapshot.is_visible:
            raise WindowGuardError("calibrated client is not visible")
        if snapshot.executable_name.casefold() not in self._allowed_executables:
            raise WindowGuardError("foreground executable is not in the calibration allowlist")
        if self._title_pattern.search(snapshot.title) is None:
            raise WindowGuardError("foreground title does not match the calibration profile")
        bounds = snapshot.client_bounds
        target = self._profile.target
        if abs(bounds.width - target.reference_width) > target.size_tolerance_px:
            raise WindowGuardError("client width is outside the calibration tolerance")
        if abs(bounds.height - target.reference_height) > target.size_tolerance_px:
            raise WindowGuardError("client height is outside the calibration tolerance")
        if abs(snapshot.dpi_scale - target.dpi_scale) > target.dpi_tolerance:
            raise WindowGuardError("client DPI scale is outside the calibration tolerance")
        return snapshot


class WindowsForegroundWindowInspector:
    """Inspects the current Win32 foreground window without sending input."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsForegroundWindowInspector requires Windows")

    def inspect(self) -> WindowSnapshot | None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        user32.GetClientRect.restype = wintypes.BOOL
        user32.ClientToScreen.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.POINT),
        )
        user32.ClientToScreen.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsWindowVisible.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        window = user32.GetForegroundWindow()
        if not window:
            return None

        title_length = user32.GetWindowTextLengthW(window)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(window, title_buffer, len(title_buffer))

        rect = wintypes.RECT()
        if not user32.GetClientRect(window, ctypes.byref(rect)):
            return None
        top_left = wintypes.POINT(rect.left, rect.top)
        bottom_right = wintypes.POINT(rect.right, rect.bottom)
        if not user32.ClientToScreen(window, ctypes.byref(top_left)):
            return None
        if not user32.ClientToScreen(window, ctypes.byref(bottom_right)):
            return None

        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not process:
            return None
        try:
            path_buffer = ctypes.create_unicode_buffer(32_768)
            path_length = wintypes.DWORD(len(path_buffer))
            if not kernel32.QueryFullProcessImageNameW(
                process, 0, path_buffer, ctypes.byref(path_length)
            ):
                return None
            executable_name = Path(path_buffer.value).name
        finally:
            kernel32.CloseHandle(process)

        if hasattr(user32, "GetDpiForWindow"):
            user32.GetDpiForWindow.argtypes = (wintypes.HWND,)
            user32.GetDpiForWindow.restype = wintypes.UINT
            dpi = user32.GetDpiForWindow(window)
        else:
            dpi = 96
        return WindowSnapshot(
            executable_name=executable_name,
            title=title_buffer.value,
            client_bounds=WindowBounds(
                left=top_left.x,
                top=top_left.y,
                width=bottom_right.x - top_left.x,
                height=bottom_right.y - top_left.y,
            ),
            dpi_scale=dpi / 96.0,
            is_foreground=True,
            is_visible=bool(user32.IsWindowVisible(window)),
        )
