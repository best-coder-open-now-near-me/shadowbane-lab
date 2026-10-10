# ruff: noqa: F811
import json
from dataclasses import replace

import pytest
from test_pve_settings import cli, owner  # noqa: F401

from shadowbane_lab.cli_commands import client_pve_settings as command
from shadowbane_lab.pve import settings


@pytest.mark.parametrize("schema", [1, 2, 3, 4])
def test_migration_never_enables_commands_or_rewrites_settings(tmp_path, owner, schema):
    raw = {"schema_version": schema, "server": owner.server_name,
           "character": owner.character_name, "policy": "basic",
           "opening_skill": None, "revision": 7}
    if schema >= 2:
        raw["buffs"] = settings.PvESettings().buffs.as_dict()
    if schema >= 3:
        raw["tracking"] = settings.PvESettings().tracking.as_dict()
        if schema == 3:
            raw["tracking"].pop("group_callouts_enabled")
    path = settings._path(owner, tmp_path)
    data = json.dumps(raw).encode()
    path.write_bytes(data)
    loaded = settings.load_pve_settings(owner, root=tmp_path)
    assert not loaded.group_commands.enabled
    assert path.read_bytes() == data
    updated = settings.save_pve_settings(owner, replace(loaded,
        group_commands=settings.GroupCommandSettings(True)), expected=loaded,
        require_current=lambda: None, root=tmp_path)
    assert settings.load_pve_settings(owner, root=tmp_path) == updated
    assert updated.tracking == loaded.tracking and updated.buffs == loaded.buffs


def test_supported_command_setting_independent_of_tracking(cli, owner):
    assert not settings.load_pve_settings(owner).tracking.enabled
    assert command._configure_pve_settings(process_id=123, group_commands="enabled") == 0
    saved = settings.load_pve_settings(owner)
    assert saved.group_commands.enabled and not saved.tracking.enabled
    assert command._configure_pve_settings(process_id=123, group_commands="disabled") == 0
    assert not settings.load_pve_settings(owner).group_commands.enabled


@pytest.mark.parametrize("value", [{"enabled": 1}, {"enabled": True, "attack_all": True}, {}])
def test_only_typed_explicit_group_enable(value):
    with pytest.raises(ValueError):
        settings.GroupCommandSettings.from_dict(value)
