# ruff: noqa: F811
"""Tracking shares production service ownership and runs independently of buff coverage."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_native_preparation_service import resources  # noqa: F401
from test_preparation_service import Owner, service
from test_pve_controller import (
    AdvancingClock,
    ConstantHealthSource,
    RecordingPvEDispatcher,
    SequencePlayerActionSource,
    SequencePlayerVitalsSource,
    _player,
    _player_action,
    _runner,
    _target,
)

from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.manager import native_preparation as module
from shadowbane_lab.pve import PvEController, PvEControllerConfig
from shadowbane_lab.pve.preparation_status import PreparationStatus
from shadowbane_lab.pve.settings import PvESettings
from shadowbane_lab.pve.tracking import TrackingActor, TrackingSettings, TrackingStatus


def current_status():
    return TrackingStatus(enabled=True, state="current", current=True, generation=3,
        observed_at=100, response_age_seconds=0, actor=TrackingActor(1, 2, 3, (4, 5)))


def test_tracking_only_factory_reuses_preparation_lease_without_buff_manifest(
        resources, monkeypatch):
    binding, _, _, coordinator, events = resources
    settings = PvESettings(tracking=TrackingSettings(True))
    monkeypatch.setattr(module, "load_pve_settings", lambda _: settings)
    monkeypatch.setattr(coordinator, "configure_tracking",
                        lambda self, value: events.append(("tracking", value)), raising=False)
    value = module.NativePreparationFactory(binding)()
    assert value.settings == settings and not settings.buffs.enabled
    assert events.count(("lease", 7)) == 1 and events.count("ticket-open") == 1
    assert "manifest-open" not in events and ("tracking", settings.tracking) in events
    value.close()


def test_idle_owner_polls_tracking_without_changing_buff_lane():
    coordinator = Mock()
    owner = module.NativePreparationOwner(None, None, None, coordinator, None,
                                          PvESettings(tracking=TrackingSettings(True)))
    owner.step(allow_new=True)
    coordinator.tracking_step.assert_called_once_with(allow_new=True)
    coordinator.preparation_step.assert_not_called()
    owner.step(allow_new=False)
    assert coordinator.tracking_step.call_args.kwargs == {"allow_new": False}


def test_tracking_intent_change_requests_existing_owner_handoff(monkeypatch):
    original = PvESettings(tracking=TrackingSettings(True))
    owner = module.NativePreparationOwner(None, None, None, None,
        SimpleNamespace(binding=SimpleNamespace(identity=object())), original)
    monkeypatch.setattr(module, "load_pve_settings", lambda _: PvESettings())
    assert owner.settings_changed()


def test_service_publishes_tracking_with_disabled_buffs_and_revokes_on_pause():
    owner = Owner()
    owner.tracking_status = current_status()
    owner.finish_result = True
    enabled = [True]
    value = service(owner, intent=lambda: (enabled[0], 1))
    value._cycle()
    assert value.snapshot.tracking.current
    assert value.snapshot.preparation == PreparationStatus.disabled()
    enabled[0] = False
    value._cycle()
    assert value.snapshot.state == "paused" and not value.snapshot.tracking.current
    assert ("step", False) in [v[:2] for v in owner.calls]
    assert [v[0] for v in owner.calls].count("finish") == 1


@pytest.mark.parametrize("listed", [False, True])
def test_runner_tracks_with_existing_cast_and_in_listed_path_without_buff_lane(listed):
    clock, dispatcher, stop = AdvancingClock(), RecordingPvEDispatcher(), EventEmergencyStop()
    tracker = Mock(tracking_status=current_status())
    class Listed:
        active = True
        preparation_allowed = False
        def prepare(self, observation, camp):
            return True
        def advance(self, observation):
            return SimpleNamespace(terminal_reason=None, recovered=False)
        def finish(self, reason):
            self.active = False
            return SimpleNamespace(terminal_reason=None, recovered=False)
    busy = _player_action(token="mob", mode=1, action_state=4, initiation_state=6)
    progress = []
    def sleep(seconds):
        clock.sleep(seconds)
        stop.trip()
    result = _runner(controller=PvEController(PvEControllerConfig()),
        health_reader=ConstantHealthSource(_target("mob")),
        player_vitals_reader=SequencePlayerVitalsSource((_player(),)),
        player_action_reader=SequencePlayerActionSource((busy,)),
        dispatcher=dispatcher, stop_signal=stop, clock=clock, sleeper=sleep,
        listed_combat=Listed() if listed else None, actor_tracking=tracker,
        progress_sink=progress.append).run()
    assert result.terminal_reason == "emergency_stop"
    tracker.tracking_step.assert_called_once_with()
    assert any(p.tracking.current for p in progress)
    assert all(p.preparation == PreparationStatus.disabled() for p in progress)
    assert dispatcher.intents == []  # Existing cast was not forced to settle for a query.
