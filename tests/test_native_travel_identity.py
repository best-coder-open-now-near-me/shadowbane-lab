"""Native travel admits exact clients without screen calibration authority."""
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.cli_commands import client_travel as travel
from shadowbane_lab.client_input import (
    EventEmergencyStop,
    StaticWindowInspector,
    WindowBounds,
    WindowSnapshot,
)
from shadowbane_lab.travel import TravelPhase


@pytest.fixture
def setup_travel(monkeypatch, tmp_path):
    snapshot = WindowSnapshot(
        executable_name="sb.exe", title="Any native client title",
        client_bounds=WindowBounds(200, 70, 2560, 1440), dpi_scale=1.5,
        is_foreground=True, is_visible=True, executable_path=r"C:\Games\sb.exe",
        process_id=123, process_started_at_100ns=456, window_handle=789,
    )
    inspector = StaticWindowInspector(snapshot)
    position = SimpleNamespace(process_id=123, process_creation_filetime_utc=456,
                               executable_path=Path(r"C:\Games\sb.exe"))
    vitals = SimpleNamespace(process_id=123)
    profile = SimpleNamespace(executable_sha256="ab" * 32)
    for name in ("load_bundled_native_position_profile", "load_bundled_native_vitals_profile"):
        monkeypatch.setattr(travel, name, lambda: profile)
    monkeypatch.setattr(travel, "WindowsForegroundWindowInspector", lambda: inspector)
    open_position = Mock(side_effect=lambda *a, **k: nullcontext(position))
    open_vitals = Mock(side_effect=lambda *a, **k: nullcontext(vitals))
    monkeypatch.setattr(travel, "open_windows_native_player_position_reader", open_position)
    monkeypatch.setattr(travel, "open_windows_native_player_vitals_reader", open_vitals)
    monkeypatch.setattr(travel, "optional_session", lambda *_: nullcontext(None))
    dispatcher = SimpleNamespace(dispatch=Mock(), stop_movement=Mock())
    owner = SimpleNamespace(dispatcher=dispatcher)
    operation = Mock(return_value=nullcontext(owner))
    monkeypatch.setattr(travel, "NativeMovementOperation", operation)
    completed = SimpleNamespace(final_phase=TravelPhase.COMPLETE, terminal_reason="arrived",
        final_position=None, trace=(), clicks=1, arrival_confirmed=True,
        stop_input_accepted=True, stop_input_reason="native_stopped")
    runner = Mock()
    runner.return_value.run.return_value = completed
    monkeypatch.setattr(travel, "TravelRunner", runner)
    args = dict(lt=1000, lg=2000, radius=75, destination_state_path=tmp_path / "go.json",
        native_position_profile_path=None, native_vitals_profile_path=None,
        max_seconds=30, wait_for_client_seconds=0, poll_ms=200, click_interval_ms=4000,
        live=True, as_json=True, stop_signal=EventEmergencyStop())
    return SimpleNamespace(inspector=inspector, position=position, vitals=vitals,
        open_position=open_position, open_vitals=open_vitals, operation=operation,
        runner=runner, dispatcher=dispatcher, args=args)


@pytest.mark.parametrize("legacy_profile", [None, Path("missing-disabled-calibration.json")])
@pytest.mark.parametrize("injected", [False, True])
def test_native_travel_accepts_uncalibrated_client_without_pixel_dispatch(
    setup_travel, legacy_profile, injected, monkeypatch,
):
    f = setup_travel
    # Neither the legacy profile nor a mouse backend may be consulted.
    import shadowbane_lab.client_input as inputs
    forbidden = Mock(side_effect=AssertionError("pixel/calibration path consulted"))
    monkeypatch.setattr(inputs, "load_calibration", forbidden)
    monkeypatch.setattr(inputs, "PyAutoGuiBackend", forbidden)
    kwargs = dict(f.args, client_profile_path=legacy_profile)
    if injected:
        kwargs["movement_dispatcher"] = f.dispatcher
    assert travel._run_travel(**kwargs) == 0
    forbidden.assert_not_called()
    assert f.runner.call_args.kwargs["dispatcher"] is f.dispatcher
    if injected:
        f.operation.assert_not_called()
    else:
        guard = f.operation.call_args.args[0]
        assert guard.require_target().process_started_at_100ns == 456


@pytest.mark.parametrize("field,value", [
    ("process_started_at_100ns", None), ("window_handle", None),
    ("executable_path", None), ("is_foreground", False), ("is_visible", False),
])
def test_incomplete_or_inactive_identity_never_opens_readers(setup_travel, field, value):
    f = setup_travel
    f.inspector.snapshot = replace(f.inspector.snapshot, **{field: value})
    assert travel._run_travel(**f.args) == 2
    f.open_position.assert_not_called()
    f.operation.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("process_id", 124), ("process_creation_filetime_utc", 457),
    ("executable_path", Path(r"C:\Other\sb.exe")),
])
def test_native_reader_replacement_fails_before_other_readers_or_grant(setup_travel, field, value):
    f = setup_travel
    setattr(f.position, field, value)
    assert travel._run_travel(**f.args) == 2
    f.open_vitals.assert_not_called()
    f.operation.assert_not_called()
    f.runner.assert_not_called()


@pytest.mark.parametrize("change", [
    {"process_id": 124}, {"process_started_at_100ns": 457}, {"window_handle": 790},
    {"executable_path": r"C:\Other\sb.exe"},
])
def test_identity_change_during_reader_initialization_prevents_dispatch(setup_travel, change):
    f = setup_travel
    def open_vitals(*args, **kwargs):
        f.inspector.snapshot = replace(f.inspector.snapshot, **change)
        return nullcontext(f.vitals)
    f.open_vitals.side_effect = open_vitals
    assert travel._run_travel(**f.args, movement_dispatcher=f.dispatcher) == 2
    f.operation.assert_not_called()
    f.runner.assert_not_called()


def test_requested_process_must_be_current_foreground_client(setup_travel):
    f = setup_travel
    assert travel._run_travel(**f.args, client_process_id=999) == 2
    f.open_position.assert_not_called()
    f.runner.assert_not_called()
