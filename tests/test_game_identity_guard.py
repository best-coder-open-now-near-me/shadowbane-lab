"""Exact lifetime guard tests; synthetic Windows APIs never send game input."""

import ctypes
import os
from ctypes import wintypes
from types import SimpleNamespace

import pytest

from shadowbane_lab.manager.game_identity import (
    GameIdentityChanged,
    WindowsGameIdentityGuard,
    _WindowsGameIdentityApi,
)


def binding(pid=17, creation=100, hwnd=99):
    return SimpleNamespace(
        game_process_id=pid, game_process_started_at_100ns=creation, game_window_handle=hwnd
    )


class Api:
    def __init__(self):
        self.pid = 17
        self.birth = 100
        self.alive = True
        self.closed = []
        self.opens = []
        self.error = None
        self.rebound = False

    def open_process(self, pid):
        self.opens.append(pid)
        return 123

    def window_process(self, hwnd):
        assert hwnd == 99
        return self.pid

    def running(self, handle):
        assert handle == 123
        if self.error:
            raise self.error
        return self.alive

    def creation(self, handle):
        if self.rebound:
            self.pid = 18
        return self.birth

    def close(self, handle):
        self.closed.append(handle)


@pytest.mark.parametrize("fault", ["exit", "creation", "window", "rebound", "unknown"])
def test_identity_loss_latches_without_reopening(fault):
    api = Api()
    guard = WindowsGameIdentityGuard(binding(), _api=api)
    if fault == "exit":
        api.alive = False
    if fault == "creation":
        api.birth += 1
    if fault == "window":
        api.pid = 0
    if fault == "rebound":
        api.rebound = True
    if fault == "unknown":
        api.error = OSError("inspection unavailable")
    with pytest.raises((GameIdentityChanged, OSError)):
        guard.require_current()
    api.alive, api.birth, api.pid, api.rebound, api.error = True, 100, 17, False, None
    with pytest.raises(GameIdentityChanged, match="revoked"):
        guard.require_current()
    guard.close()
    guard.close()
    assert api.opens == [17] and api.closed == [123]


def test_partial_construction_closes_original_handle():
    api = Api()
    api.birth = 101
    with pytest.raises(GameIdentityChanged):
        WindowsGameIdentityGuard(binding(), _api=api)
    assert api.closed == [123]


def test_live_binding_needs_no_geometry_discovery_or_parent_process():
    api = Api()
    guard = WindowsGameIdentityGuard(binding(), _api=api)
    for _ in range(5):
        guard.require_current()
    assert api.opens == [17]
    guard.close()
    with pytest.raises(GameIdentityChanged):
        guard.require_current()


@pytest.mark.skipif(os.name != "nt", reason="actual Windows process/window identity")
def test_real_hidden_window_identity_and_destroyed_window():
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.CreateWindowExW.argtypes = (
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    )
    user.CreateWindowExW.restype = wintypes.HWND
    user.DestroyWindow.argtypes = (wintypes.HWND,)
    user.DestroyWindow.restype = wintypes.BOOL
    # A message-only, hidden standard-class window requires no visible desktop UI.
    hwnd = user.CreateWindowExW(
        0, "STATIC", "identity-test", 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None
    )
    assert hwnd, ctypes.WinError(ctypes.get_last_error())
    api = _WindowsGameIdentityApi()
    handle = api.open_process(os.getpid())
    try:
        creation = api.creation(handle)
    finally:
        api.close(handle)
    guard = None
    try:
        guard = WindowsGameIdentityGuard(binding(os.getpid(), creation, int(hwnd)))
        guard.require_current()
        assert user.DestroyWindow(hwnd)
        hwnd = None
        with pytest.raises(GameIdentityChanged):
            guard.require_current()
    finally:
        if guard is not None:
            guard.close()
        if hwnd:
            user.DestroyWindow(hwnd)
