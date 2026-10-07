from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.client_guard import NativeClientIdentityGuard
from shadowbane_lab.client_input import (
    StaticWindowInspector,
    WindowBounds,
    WindowGuardError,
    WindowSnapshot,
)


def client():
    return WindowSnapshot(
        executable_name="sb.exe", title="Shadowbane", client_bounds=WindowBounds(0, 0, 1920, 1080),
        dpi_scale=1.0, is_foreground=True, is_visible=True,
        executable_path=r"C:\Games\sb.exe", process_id=123,
        process_started_at_100ns=456, window_handle=789,
    )


def test_native_identity_accepts_resizing_dpi_and_title_changes():
    inspector = StaticWindowInspector(client())
    guard = NativeClientIdentityGuard(inspector)
    guard.require_target()
    inspector.snapshot = replace(client(), client_bounds=WindowBounds(200, 50, 800, 600),
                                 dpi_scale=1.5, title="New client title")
    assert guard.require_target() == inspector.snapshot


@pytest.mark.parametrize("change", [
    {"process_id": 124}, {"process_started_at_100ns": 457}, {"window_handle": 790},
    {"executable_path": r"C:\Other\sb.exe"}, {"is_foreground": False}, {"is_visible": False},
    {"executable_name": "other.exe"}, {"executable_path": None},
    {"process_id": None}, {"process_started_at_100ns": None}, {"window_handle": None},
])
def test_native_identity_rejects_lifetime_replacement_and_missing_identity(change):
    inspector = StaticWindowInspector(client())
    guard = NativeClientIdentityGuard(inspector)
    guard.require_target()
    inspector.snapshot = replace(client(), **change)
    with pytest.raises(WindowGuardError):
        guard.require_target()


@pytest.mark.parametrize("expected", [
    {"expected_process_id": 124}, {"expected_process_started_at_100ns": 457},
    {"expected_window_handle": 790}, {"expected_executable_path": r"C:\Other\sb.exe"},
])
def test_native_identity_rejects_wrong_explicit_binding_before_capture(expected):
    with pytest.raises(WindowGuardError):
        NativeClientIdentityGuard(StaticWindowInspector(client()), **expected).require_target()


def test_capture_requires_complete_identity_and_retains_windows_path_identity():
    inspector = StaticWindowInspector(replace(client(), process_started_at_100ns=None))
    guard = NativeClientIdentityGuard(inspector)
    with pytest.raises(WindowGuardError):
        guard.require_target()
    inspector.snapshot = client()
    guard.require_target()
    inspector.snapshot = replace(client(), executable_path="c:/GAMES/sb.exe")
    guard.require_target()


def test_no_foreground_client_is_not_an_admission():
    with pytest.raises(WindowGuardError):
        NativeClientIdentityGuard(StaticWindowInspector(None)).require_target()


def test_listener_selector_can_select_another_client_without_rebinding_an_operation():
    from shadowbane_lab.client_extension.client_guard import NativeClientWindowSelector

    inspector = StaticWindowInspector(client())
    selector = NativeClientWindowSelector(inspector)
    admitted = selector.require_target()
    owner = NativeClientIdentityGuard(
        inspector, expected_process_id=admitted.process_id,
        expected_process_started_at_100ns=admitted.process_started_at_100ns,
        expected_window_handle=admitted.window_handle,
        expected_executable_path=admitted.executable_path,
    )
    owner.require_target()
    inspector.snapshot = replace(client(), process_id=321, process_started_at_100ns=654,
                                 window_handle=987)
    assert selector.require_target().process_id == 321
    with pytest.raises(WindowGuardError):
        owner.require_target()
