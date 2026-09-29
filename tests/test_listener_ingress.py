from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shadowbane_lab.cli_commands import client_listener as listener
from shadowbane_lab.client_input import (
    EventEmergencyStop,
    ForegroundWindowGuard,
    RecordingInputBackend,
    StaticWindowInspector,
    WindowBounds,
    WindowGuardError,
    WindowSnapshot,
    load_calibration,
)
from shadowbane_lab.travel import PhysicalPointerInteraction
from shadowbane_lab.travel.listener_ingress import (
    ListenerClientIdentity,
    ListenerCommandIngress,
    ListenerOwnershipStop,
)


@pytest.fixture
def client():
    template = Path(__file__).parents[1] / "configs" / "wonderbane-travel.template.json"
    profile = replace(load_calibration(template), live_input_enabled=True)
    snapshot = WindowSnapshot(
        "sb.exe", "Shadowbane", WindowBounds(0, 0, 1920, 955), 1.0, True, True,
        process_id=42, process_started_at_100ns=1000, window_handle=20,
    )
    inspector = StaticWindowInspector(snapshot)
    return template, profile, inspector, ForegroundWindowGuard(profile, inspector)


@pytest.mark.parametrize("field", ["process_id", "process_started_at_100ns", "window_handle"])
def test_admission_requires_full_client_identity(client, field):
    _, _, inspector, guard = client
    inspector.snapshot = replace(inspector.snapshot, **{field: None})
    with pytest.raises(WindowGuardError, match="exact process"):
        ListenerCommandIngress(guard).submit("/pve")


@pytest.mark.parametrize("field", ["process_id", "process_started_at_100ns", "window_handle"])
def test_captured_lifetime_cannot_rebind_and_local_revocation_is_permanent(client, field):
    _, _, inspector, guard = client
    original = inspector.snapshot
    ingress = ListenerCommandIngress(guard)
    ingress.submit("/pve")
    admitted = ingress.get(timeout=0.1)
    stop = ListenerOwnershipStop(admitted.client, guard)
    assert not stop.is_set()
    inspector.snapshot = replace(original, **{field: getattr(original, field) + 1})
    with pytest.raises(WindowGuardError, match="different client"):
        admitted.client.require_current(guard)
    assert stop.is_set()
    inspector.snapshot = original
    assert stop.is_set()


def test_pending_cancellation_is_coalesced_per_captured_client(client):
    _, _, inspector, guard = client
    first = inspector.snapshot
    ingress = ListenerCommandIngress(guard)
    ingress.submit(None)
    ingress.submit(None)
    inspector.snapshot = replace(first, process_id=43, window_handle=21)
    ingress.submit(None)
    assert ingress.get(timeout=0.1).client == ListenerClientIdentity.capture(first)
    assert ingress.get(timeout=0.1).client == ListenerClientIdentity.capture(inspector.snapshot)
    # Draining one owner permits a fresh cancellation for that owner.
    ingress.submit(None)
    assert ingress.get(timeout=0.1).command is None


def _run_listener(tmp_path, template, *, managed=False):
    return listener._listen_for_go_commands(
        destination_state_path=tmp_path / "travel.json", client_profile_path=template,
        native_position_profile_path=None, native_vitals_profile_path=None,
        native_runegate_profile_path=None, world_def_path=None,
        named_destination_overrides_path=None, pve_client_profile_path=template,
        pve_hotbar_config_path=None, pve_evidence_directory=None,
        navigation_cache_directory=None, pve_max_kills=3, pve_max_seconds=300,
        pve_max_encounter_seconds=120, pve_recovery_timeout_seconds=30, pve_poll_ms=100,
        max_seconds=300, wait_for_client_seconds=0, poll_ms=100, click_interval_ms=4000,
        manager_manifest_path=tmp_path / "manager.json" if managed else None,
        worker_state_directory=tmp_path / "workers" if managed else None,
        live=True, as_json=True,
    )


def _patch_listener(monkeypatch, profile, inspector, stop, callback_type):
    for name, value in {
        "load_calibration": lambda _: profile,
        "WindowsForegroundWindowInspector": lambda: inspector,
        "WindowsHotkeyEmergencyStop": lambda: nullcontext(stop),
        "WindowsGoChatCommandListener": callback_type,
        "WindowsZoneSearchOverlay": lambda: nullcontext(MagicMock()),
        "PyAutoGuiBackend": RecordingInputBackend,
    }.items():
        monkeypatch.setattr(listener, name, value)


@pytest.mark.parametrize("command", [
    "/pve", "/go 12 34", "/stop", PhysicalPointerInteraction(100, 200, "right"),
])
@pytest.mark.parametrize("field", ["process_id", "process_started_at_100ns", "window_handle"])
def test_real_listener_rejects_queued_command_after_client_change(
    tmp_path, monkeypatch, client, command, field,
):
    template, profile, inspector, _ = client
    entered, release = Event(), Event()
    stop = EventEmergencyStop()
    errors, events, runs = [], [], []
    finished = Event()
    backend = RecordingInputBackend()

    class CallbackListener:
        is_alive = True

        def __init__(self, _guard, *, on_command, on_interaction, on_pointer):
            self.submit, self.pointer = on_command, on_pointer

        def __enter__(self):
            def drive():
                try:
                    self.submit("/pve")
                    assert entered.wait(5), "initial PvE did not enter"
                    if isinstance(command, str):
                        self.submit(command)
                    else:
                        self.pointer(command)
                    old = inspector.snapshot
                    inspector.snapshot = replace(old, **{field: getattr(old, field) + 1})
                except BaseException as exc:
                    errors.append(exc)
                    stop.trip()
                finally:
                    release.set()
                finished.wait(5)
                stop.trip()
            self.thread = Thread(target=drive)
            self.thread.start()
            return self

        def __exit__(self, *_args):
            release.set()
            self.thread.join(5)
            assert not self.thread.is_alive()

    def blocked_pve(**kwargs):
        runs.append(kwargs)
        entered.set()
        assert release.wait(5)
        assert kwargs["stop_signal"].is_set(), "local operation kept a changed client"

    def report(event, **kwargs):
        events.append((event, kwargs))
        if event == "rejected":
            finished.set()
            stop.trip()

    _patch_listener(monkeypatch, profile, inspector, stop, CallbackListener)
    monkeypatch.setattr(listener, "PyAutoGuiBackend", lambda: backend)
    monkeypatch.setattr(listener, "_run_pve", blocked_pve)
    monkeypatch.setattr(listener, "_run_travel", MagicMock())
    monkeypatch.setattr(listener, "open_windows_native_world_map_reader", MagicMock())
    monkeypatch.setattr(listener, "_print_go_listener_event", report)
    assert _run_listener(tmp_path, template) == 0
    assert not errors
    assert len(runs) == 1
    assert any(event == "rejected" and "different client" in data["reason"]
               for event, data in events)
    listener._run_travel.assert_not_called()
    listener.open_windows_native_world_map_reader.assert_not_called()
    assert backend.invocations == ()


@pytest.mark.parametrize("changed", [False, True])
def test_real_listener_cancellation_keeps_captured_worker_lifetime(
    tmp_path, monkeypatch, client, changed,
):
    template, profile, inspector, _ = client
    entered, release = Event(), Event()
    stop = EventEmergencyStop()
    errors, submitted = [], []
    ingress = MagicMock()

    class CallbackListener:
        is_alive = True

        def __init__(self, _guard, *, on_command, on_interaction, **_kwargs):
            self.submit, self.cancel = on_command, on_interaction

        def __enter__(self):
            def drive():
                try:
                    self.submit("/pve")
                    assert entered.wait(5)
                    self.cancel()
                    self.cancel()
                    if changed:
                        inspector.snapshot = replace(
                            inspector.snapshot, process_id=43, window_handle=21,
                        )
                except BaseException as exc:
                    errors.append(exc)
                    stop.trip()
                finally:
                    release.set()
            self.thread = Thread(target=drive)
            self.thread.start()
            return self

        def __exit__(self, *_args):
            release.set()
            self.thread.join(5)
            assert not self.thread.is_alive()

    def dispatch(*args, **kwargs):
        submitted.append(kwargs)
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(
            operation=SimpleNamespace(operation_id="op", client_id="client"),
            acknowledgement=None,
        )

    polls = 0

    def poll():
        nonlocal polls
        polls += 1
        if polls >= 3:
            stop.trip()
        return SimpleNamespace(
            connected_clients=0, dispatched_events=0, rejected_events=0,
            pending_events=0, dispatched_process_ids=(), issues=(),
        )

    ingress.dispatch.side_effect = dispatch
    router = MagicMock()
    router.poll_once.side_effect = poll
    _patch_listener(monkeypatch, profile, inspector, stop, CallbackListener)
    for name in (
        "load_manager_manifest", "WindowsVisibleWindowInspector",
        "ManifestClientRegistryProvider", "WorkerHeartbeatLedger", "WorkerOperationLedger",
    ):
        monkeypatch.setattr(listener, name, MagicMock())
    monkeypatch.setattr(listener, "ForegroundWorkerOperationIngress", lambda *_: ingress)
    monkeypatch.setattr(listener, "ExactExtensionEventRouter", lambda *_, **__: router)
    assert _run_listener(tmp_path, template, managed=True) == 0
    assert not errors
    assert len(submitted) == 1
    assert submitted[0]["expected_process_id"] == 42
    assert submitted[0]["expected_process_started_at_100ns"] == 1000
    assert submitted[0]["expected_window_handle"] == 20
    ingress.cancel_if_inflight.assert_called_once_with(
        "physical-client-interaction", expected_process_id=42,
        expected_window_handle=20, expected_process_started_at_100ns=1000,
        require_foreground=False,
    )


@pytest.mark.parametrize("field", ["process_id", "process_started_at_100ns", "window_handle"])
def test_map_resolution_client_change_cannot_close_map_or_start_travel(
    tmp_path, monkeypatch, client, field,
):
    from shadowbane_lab.client_input import InputPlan, KeyPressCommand

    template, profile, inspector, _ = client
    stop = EventEmergencyStop()
    backend = RecordingInputBackend()
    rejections = []

    class PointerListener:
        is_alive = True

        def __init__(self, _guard, *, on_pointer, **_kwargs):
            self.pointer = on_pointer

        def __enter__(self):
            self.pointer(PhysicalPointerInteraction(100, 200, "right"))
            return self

        def __exit__(self, *_args):
            pass

    def resolve(*_):
        old = inspector.snapshot
        inspector.snapshot = replace(old, **{field: getattr(old, field) + 1})
        return SimpleNamespace(lt=12, lg=34)

    def report(event, **kwargs):
        if event == "rejected":
            rejections.append(kwargs)
            stop.trip()

    reader = MagicMock(process_id=42)
    reader.resolve_screen_point.side_effect = resolve
    _patch_listener(monkeypatch, profile, inspector, stop, PointerListener)
    monkeypatch.setattr(listener, "PyAutoGuiBackend", lambda: backend)
    monkeypatch.setattr(listener, "open_windows_native_world_map_reader", lambda *_, **__: reader)
    monkeypatch.setattr(listener, "_load_world_map_close_plan", lambda *_, **__: InputPlan(
        "test", "client.world-map.close", (KeyPressCommand("m"),),
    ))
    monkeypatch.setattr(listener, "_print_go_listener_event", report)
    monkeypatch.setattr(listener, "_run_travel", MagicMock(side_effect=lambda **_: stop.trip()))
    assert _run_listener(tmp_path, template) == 0
    assert len(rejections) == 1
    assert "could not close world map" in rejections[0]["reason"]
    assert backend.invocations == ()
    listener._run_travel.assert_not_called()
