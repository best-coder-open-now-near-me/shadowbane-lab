from pathlib import Path

import pytest

from shadowbane_lab.client_extension import movement_settings as settings
from shadowbane_lab.graphics_lab.control import GraphicsControlTarget


def target():
    return GraphicsControlTarget(
        42, 134330704095521110, Path("sb.exe"), "a" * 64, "mapping", Path("status")
    )


class Windows:
    def __init__(self, accepted=200):
        self.accepted = accepted
        self.requests = []

    def windows(self, pid):
        assert pid == 42
        return (100, 200)

    def open(self, window, pid, creation):
        self.requests.append((window, pid, creation))
        return window == self.accepted


def test_selected_client_request_preserves_full_identity(monkeypatch):
    windows = Windows()
    monkeypatch.setattr(settings, "_WindowsSettings", lambda: windows)
    monkeypatch.setattr(settings, "verify_target_identity", lambda value: value == target())
    monkeypatch.setattr(settings, "target_process_is_alive", lambda value: value == target())
    settings.open_native_movement_settings(target())
    assert windows.requests == [
        (100, 42, target().process_creation_filetime_utc),
        (200, 42, target().process_creation_filetime_utc),
    ]


def test_identity_mismatch_never_touches_window_api(monkeypatch):
    monkeypatch.setattr(settings, "verify_target_identity", lambda _: False)
    monkeypatch.setattr(
        settings, "_WindowsSettings", lambda: pytest.fail("identity mismatch must not dispatch")
    )
    with pytest.raises(RuntimeError, match="identity changed"):
        settings.open_native_movement_settings(target())


def test_process_loss_stops_before_dispatch(monkeypatch):
    windows = Windows()
    monkeypatch.setattr(settings, "_WindowsSettings", lambda: windows)
    monkeypatch.setattr(settings, "verify_target_identity", lambda _: True)
    monkeypatch.setattr(settings, "target_process_is_alive", lambda _: False)
    with pytest.raises(RuntimeError, match="exited"):
        settings.open_native_movement_settings(target())
    assert windows.requests == []


def test_unavailable_package_is_explicit(monkeypatch):
    windows = Windows(accepted=None)
    monkeypatch.setattr(settings, "_WindowsSettings", lambda: windows)
    monkeypatch.setattr(settings, "verify_target_identity", lambda _: True)
    monkeypatch.setattr(settings, "target_process_is_alive", lambda _: True)
    with pytest.raises(RuntimeError, match="unavailable"):
        settings.open_native_movement_settings(target())


def test_graphics_lab_button_uses_connected_target(monkeypatch):
    from shadowbane_lab.graphics_lab.app import GraphicsLabApp

    requested = []
    monkeypatch.setattr(settings, "open_native_movement_settings", requested.append)

    class Client:
        target = target()

    class App:
        client = Client()

        def _show_status(self, *_args, **_kwargs):
            pass

    GraphicsLabApp._open_movement_controls(App())
    assert requested == [target()]
