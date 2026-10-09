# ruff: noqa: F811
import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_pve_settings import cli, owner, save  # noqa: F401

from shadowbane_lab.cli_commands import client_pve_settings as command
from shadowbane_lab.client_observation.native_tracking_ability import NativeTrackingAbility
from shadowbane_lab.pve import settings
from shadowbane_lab.pve.tracking import TrackingSettings


@pytest.mark.parametrize("schema", [1, 2])
def test_old_settings_load_without_write_or_automatic_tracking_enable(tmp_path, owner, schema):
    value = dict(schema_version=schema, server=owner.server_name, character=owner.character_name,
                 policy="basic", opening_skill=None, revision=4)
    if schema == 2:
        value["buffs"] = settings.PvESettings().buffs.as_dict()
    path = settings._path(owner, tmp_path)
    original = json.dumps(value).encode()
    path.write_bytes(original)
    loaded = settings.load_pve_settings(owner, root=tmp_path)
    assert loaded.tracking == TrackingSettings() and path.read_bytes() == original
    enabled = save(owner, tmp_path, replace(loaded, tracking=TrackingSettings(True)),
                   expected=loaded)
    assert json.loads(path.read_text())["schema_version"] == 3
    assert settings.load_pve_settings(owner, root=tmp_path) == enabled
    assert not settings.load_pve_settings(replace(owner, character_name="Other"),
                                          root=tmp_path).tracking.enabled


def test_normal_tracking_enable_resolves_hunt_foe_and_disable_does_not(cli, owner, monkeypatch):
    session, _, _ = cli
    resolver = Mock(return_value=NativeTrackingAbility(123, "Hunt Foe", "native", 4, 4, 0, 1))
    monkeypatch.setattr(command, "resolve_learned_tracking_ability", resolver)
    assert command._configure_pve_settings(process_id=123, tracking="enabled") == 0
    resolver.assert_called_once_with(session)
    assert settings.load_pve_settings(owner).tracking.enabled
    resolver.reset_mock()
    assert command._configure_pve_settings(process_id=123, tracking="disabled") == 0
    resolver.assert_not_called()
    assert not settings.load_pve_settings(owner).tracking.enabled


def test_unlearned_hunt_foe_cannot_be_enabled(cli, owner, monkeypatch):
    monkeypatch.setattr(command, "resolve_learned_tracking_ability",
                        Mock(side_effect=RuntimeError("unlearned")))
    assert command._configure_pve_settings(process_id=123, tracking="enabled") == 2
    assert settings.load_pve_settings(owner) == settings.PvESettings()


@pytest.mark.parametrize("value", [
    {"enabled": 1, "refresh_interval_seconds": 10},
    {"enabled": True, "refresh_interval_seconds": 0},
    {"enabled": True, "refresh_interval_seconds": 3601},
    {"enabled": True, "refresh_interval_seconds": 10, "auto_attack": True},
])
def test_tracking_intent_rejects_invalid_or_attack_fields(value):
    with pytest.raises(ValueError):
        TrackingSettings.from_dict(value)
