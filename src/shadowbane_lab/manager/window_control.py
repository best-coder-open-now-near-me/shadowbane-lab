"""Guarded, non-activating window management for registered client instances."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .model import ClientInstanceSnapshot, ClientRegistrySnapshot

WM_CLOSE = 0x0010

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
WINDOW_TILE_FLAGS = SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER

_SIGNED_WIN32_MIN = -(2**31)
_SIGNED_WIN32_MAX = (2**31) - 1


class WindowControlError(RuntimeError):
    """Base class for guarded window-control failures."""


class StaleClientIdentityError(WindowControlError):
    """Raised when an instance is no longer present with its original identity."""


class AmbiguousClientIdentityError(WindowControlError):
    """Raised when a registry snapshot cannot identify one safe action target."""


class WindowActionError(WindowControlError):
    """Raised when Windows rejects an otherwise authorized window action."""


def _require_win32_integer(value: int, field_name: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    lower_bound = 1 if positive else _SIGNED_WIN32_MIN
    if value < lower_bound or value > _SIGNED_WIN32_MAX:
        constraint = "positive" if positive else "a signed 32-bit integer"
        raise ValueError(f"{field_name} must be {constraint} within the Win32 range")


@dataclass(frozen=True, slots=True)
class WindowRectangle:
    """An outer-window placement accepted by Win32 ``SetWindowPos``."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        _require_win32_integer(self.left, "left")
        _require_win32_integer(self.top, "top")
        _require_win32_integer(self.width, "width", positive=True)
        _require_win32_integer(self.height, "height", positive=True)


@runtime_checkable
class ClientRegistrySnapshotProvider(Protocol):
    """Provide a fresh local registry snapshot immediately before an action."""

    def inspect(self) -> ClientRegistrySnapshot: ...


@runtime_checkable
class NativeWindowApi(Protocol):
    """The restricted native calls used by the manager window controller."""

    def set_window_pos(
        self,
        window_handle: int,
        insert_after: int,
        rectangle: WindowRectangle,
        flags: int,
    ) -> None: ...

    def post_message(
        self,
        window_handle: int,
        message: int,
        wparam: int,
        lparam: int,
    ) -> None: ...


@runtime_checkable
class WindowControl(Protocol):
    """A manager-facing window lifecycle boundary with no game-input methods."""

    def tile(
        self,
        expected: ClientInstanceSnapshot,
        rectangle: WindowRectangle,
    ) -> ClientInstanceSnapshot: ...

    def request_graceful_close(
        self,
        expected: ClientInstanceSnapshot,
    ) -> ClientInstanceSnapshot: ...


class GuardedWindowControl:
    """Revalidate process lifetime and window identity before every native call."""

    def __init__(
        self,
        registry: ClientRegistrySnapshotProvider,
        native_api: NativeWindowApi,
    ) -> None:
        if not isinstance(registry, ClientRegistrySnapshotProvider):
            raise ValueError("registry must implement ClientRegistrySnapshotProvider")
        if not isinstance(native_api, NativeWindowApi):
            raise ValueError("native_api must implement NativeWindowApi")
        self._registry = registry
        self._native_api = native_api

    def tile(
        self,
        expected: ClientInstanceSnapshot,
        rectangle: WindowRectangle,
    ) -> ClientInstanceSnapshot:
        if not isinstance(rectangle, WindowRectangle):
            raise ValueError("rectangle must be WindowRectangle")
        current = self._require_current_identity(expected)
        try:
            self._native_api.set_window_pos(
                current.window_handle,
                0,
                rectangle,
                WINDOW_TILE_FLAGS,
            )
        except OSError as exc:
            raise WindowActionError(
                f"could not tile registered client {current.instance_id}"
            ) from exc
        return current

    def request_graceful_close(
        self,
        expected: ClientInstanceSnapshot,
    ) -> ClientInstanceSnapshot:
        current = self._require_current_identity(expected)
        try:
            self._native_api.post_message(current.window_handle, WM_CLOSE, 0, 0)
        except OSError as exc:
            raise WindowActionError(
                f"could not request graceful close for registered client {current.instance_id}"
            ) from exc
        return current

    def _require_current_identity(
        self,
        expected: ClientInstanceSnapshot,
    ) -> ClientInstanceSnapshot:
        if not isinstance(expected, ClientInstanceSnapshot):
            raise ValueError("expected must be ClientInstanceSnapshot")

        snapshot = self._registry.inspect()
        if not isinstance(snapshot, ClientRegistrySnapshot):
            raise WindowControlError(
                "registry must return a ClientRegistrySnapshot before a window action"
            )
        if snapshot.node_id != expected.node_id:
            raise StaleClientIdentityError(
                f"client {expected.instance_id} belongs to node {expected.node_id}, "
                f"not current node {snapshot.node_id}"
            )

        process_matches = tuple(
            client for client in snapshot.clients if client.process_id == expected.process_id
        )
        window_matches = tuple(
            client for client in snapshot.clients if client.window_handle == expected.window_handle
        )
        if len(process_matches) > 1 or len(window_matches) > 1:
            raise AmbiguousClientIdentityError(
                f"client {expected.instance_id} does not map one-to-one to a process and window"
            )

        instance_matches = tuple(
            client for client in snapshot.clients if client.instance_id == expected.instance_id
        )
        if len(instance_matches) > 1:
            raise AmbiguousClientIdentityError(
                f"registry returned multiple clients for {expected.instance_id}"
            )
        if not instance_matches:
            raise StaleClientIdentityError(f"client {expected.instance_id} is no longer registered")

        current = instance_matches[0]
        expected_identity = (
            expected.node_id,
            expected.process_id,
            expected.process_started_at_100ns,
            expected.window_handle,
        )
        current_identity = (
            current.node_id,
            current.process_id,
            current.process_started_at_100ns,
            current.window_handle,
        )
        if current_identity != expected_identity:
            raise StaleClientIdentityError(
                f"client {expected.instance_id} process/window lifetime has changed"
            )
        if process_matches != (current,) or window_matches != (current,):
            raise StaleClientIdentityError(
                f"client {expected.instance_id} process or window handle has been reused"
            )
        return current


class Win32WindowApi:
    """Restricted ``user32`` adapter for placement and graceful close requests."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Win32 window control requires Windows")

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.argtypes = (
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        )
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.PostMessageW.restype = wintypes.BOOL
        self._ctypes = ctypes
        self._user32 = user32

    def set_window_pos(
        self,
        window_handle: int,
        insert_after: int,
        rectangle: WindowRectangle,
        flags: int,
    ) -> None:
        self._ctypes.set_last_error(0)
        if not self._user32.SetWindowPos(
            window_handle,
            insert_after,
            rectangle.left,
            rectangle.top,
            rectangle.width,
            rectangle.height,
            flags,
        ):
            raise OSError(self._ctypes.get_last_error(), "SetWindowPos failed")

    def post_message(
        self,
        window_handle: int,
        message: int,
        wparam: int,
        lparam: int,
    ) -> None:
        self._ctypes.set_last_error(0)
        if not self._user32.PostMessageW(window_handle, message, wparam, lparam):
            raise OSError(self._ctypes.get_last_error(), "PostMessageW failed")


__all__ = [
    "SWP_NOACTIVATE",
    "SWP_NOOWNERZORDER",
    "SWP_NOZORDER",
    "WINDOW_TILE_FLAGS",
    "WM_CLOSE",
    "AmbiguousClientIdentityError",
    "ClientRegistrySnapshotProvider",
    "GuardedWindowControl",
    "NativeWindowApi",
    "StaleClientIdentityError",
    "Win32WindowApi",
    "WindowActionError",
    "WindowControl",
    "WindowControlError",
    "WindowRectangle",
]
