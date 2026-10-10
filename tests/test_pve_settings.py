"""Character preferences are durable intent, resolved separately from current authority."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.cli_commands import client_pve_settings as command
from shadowbane_lab.client_observation.native_character_config import ActiveCharacterIdentity
from shadowbane_lab.pve import settings


@pytest.fixture
def owner():
    return ActiveCharacterIdentity(0x123000, "Umbra", "Wonderbane")


def save(owner, root, value, expected=None, current=lambda: None):
    return settings.save_pve_settings(
        owner,
        value,
        expected=settings.PvESettings() if expected is None else expected,
        require_current=current,
        root=root,
    )


def test_missing_defaults_basic_without_creating_storage(tmp_path, owner):
    root = tmp_path / "absent"
    assert settings.load_pve_settings(owner, root=root) == settings.PvESettings()
    assert not root.exists()


def test_preferences_follow_character_across_processes_not_slots(tmp_path, owner):
    desired = settings.PvESettings(opening_skill="12345")
    first = save(owner, tmp_path, desired)
    assert first.revision == 1
    relogged = replace(owner, player_pointer=0x456000)
    assert settings.load_pve_settings(relogged, root=tmp_path) == first
    for other in (replace(owner, character_name="Other"), replace(owner, server_name="Other")):
        assert settings.load_pve_settings(other, root=tmp_path) == settings.PvESettings()
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_revision_prevents_silent_overwrite(tmp_path, owner):
    first = save(owner, tmp_path, settings.PvESettings(policy="proc-assassin"))
    with pytest.raises(ValueError, match="changed"):
        save(owner, tmp_path, settings.PvESettings(opening_skill="123"))
    assert settings.load_pve_settings(owner, root=tmp_path) == first
    cleared = save(owner, tmp_path, settings.PvESettings(), expected=first)
    assert cleared.policy == "basic" and cleared.revision == 2


def test_revocation_before_atomic_save_preserves_existing_settings(tmp_path, owner):
    first = save(owner, tmp_path, settings.PvESettings(opening_skill="123"))

    def revoked():
        raise RuntimeError("character replaced")

    with pytest.raises(RuntimeError, match="replaced"):
        save(owner, tmp_path, settings.PvESettings(), expected=first, current=revoked)
    assert settings.load_pve_settings(owner, root=tmp_path) == first


@pytest.mark.parametrize("fault", ["identity", "schema", "extra", "duplicate", "oversize", "json"])
def test_corrupt_saved_preferences_never_fall_back_to_basic(tmp_path, owner, fault):
    save(owner, tmp_path, settings.PvESettings())
    path = next(tmp_path.glob("*.json"))
    value = json.loads(path.read_text())
    if fault == "identity":
        value["character"] = "Other"
    elif fault == "schema":
        value["schema_version"] = True
    elif fault == "extra":
        value["hotbar"] = "unused"
    if fault == "duplicate":
        path.write_text('{"policy":"basic","policy":"proc-assassin"}')
    elif fault == "oversize":
        path.write_bytes(b"x" * 16385)
    elif fault == "json":
        path.write_text("{")
    else:
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        settings.load_pve_settings(owner, root=tmp_path)


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(policy="assassin"),
        dict(opening_skill=""),
        dict(opening_skill=" x "),
        dict(opening_skill="x\n"),
        dict(opening_skill="x" * 257),
        dict(revision=True),
        dict(revision=-1),
    ],
)
def test_invalid_preferences_rejected(kwargs):
    with pytest.raises(ValueError):
        settings.PvESettings(**kwargs)


@pytest.fixture
def cli(tmp_path, owner, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    session = Mock(binding=SimpleNamespace(identity=owner))
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    opener = Mock(return_value=session)
    monkeypatch.setattr(command, "open_native_character_session", opener)
    resolved = SimpleNamespace(power_id=12345, as_dict=lambda: {"power_id": 12345})
    resolver = Mock(return_value=resolved)
    monkeypatch.setattr(command, "resolve_learned_ability", resolver)
    return session, opener, resolver


def test_show_has_no_write_or_skill_resolution(cli, owner, capsys, tmp_path):
    session, opener, resolver = cli
    assert command._configure_pve_settings(process_id=123, as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["settings"] == settings.PvESettings().as_dict()
    resolver.assert_not_called()
    session.require_current.assert_called_once()
    opener.assert_called_once_with(process_id=123)
    assert not list(tmp_path.rglob("*.json"))


def test_save_resolves_current_native_ability_and_persists_numeric_choice(cli, owner, capsys):
    session, _, resolver = cli
    assert (
        command._configure_pve_settings(process_id=123, opening_skill="My Skill", as_json=True) == 0
    )
    resolver.assert_called_once_with(session, "My Skill")
    saved = settings.load_pve_settings(owner)
    assert saved == settings.PvESettings(opening_skill="12345", revision=1)
    assert json.loads(capsys.readouterr().out)["state"] == "saved"
    session.require_current.assert_called_once()


def test_clear_opener_preserves_explicit_policy(cli, owner):
    assert (
        command._configure_pve_settings(
            process_id=123, policy="proc-assassin", opening_skill="My Skill"
        )
        == 0
    )
    assert command._configure_pve_settings(process_id=123, clear_opening_skill=True) == 0
    assert settings.load_pve_settings(owner) == settings.PvESettings("proc-assassin", None, 2)


def test_unlearned_skill_or_relogged_character_cannot_publish(cli, owner):
    session, _, resolver = cli
    resolver.side_effect = ValueError("unlearned")
    assert command._configure_pve_settings(process_id=123, opening_skill="Skill") == 2
    assert settings.load_pve_settings(owner) == settings.PvESettings()
    resolver.side_effect = None
    session.require_current.side_effect = RuntimeError("relogged")
    assert command._configure_pve_settings(process_id=123, opening_skill="Skill") == 2
    assert settings.load_pve_settings(owner) == settings.PvESettings()


def test_contradictory_edit_rejected_before_open(cli):
    _, opener, _ = cli
    assert (
        command._configure_pve_settings(
            process_id=123, opening_skill="Skill", clear_opening_skill=True
        )
        == 2
    )
    opener.assert_not_called()


def test_worker_uses_current_character_settings_instead_of_assassin_default(tmp_path, monkeypatch):
    from threading import Event

    from test_manager_movement import context, make_executor
    from test_manager_operation import _permit

    from shadowbane_lab.cli_commands import manager
    from shadowbane_lab.manager.operation import WorkerOperationKind, new_worker_operation

    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    def prepared_run(**kwargs):
        assert not session.acquire_calls
        dispatcher = kwargs["movement_acquirer"]()
        assert dispatcher is executor._movement.dispatcher
        return 0

    run = Mock(side_effect=prepared_run)
    monkeypatch.setattr(manager, "_run_pve", run)
    operation = new_worker_operation(_permit(), WorkerOperationKind.PVE, "/pve", now=100.0)
    executor._binding = replace(executor._binding, client_id=operation.client_id,
                                instance_id=operation.instance_id, worker_id=operation.worker_id)
    result = executor.execute(operation, stop_signal=Event())
    assert result.state.value == "succeeded"
    assert run.call_args.kwargs["policy"] is None
    assert run.call_args.kwargs["client_process_id"] == 123
    assert "movement_dispatcher" not in run.call_args.kwargs
    assert len(session.acquire_calls) == len(session.stop_calls) == session.closed == 1


def buff_intent():
    from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
    from shadowbane_lab.pve.preparation import PreparationAction
    return BuffSettings(True, (BuffGroup("concoction", (BuffAction(
        PreparationAction("concoction", item_template=(980066, 0)), 429021400),)),))


def test_schema1_migration_preserves_intent_and_revision_without_write(tmp_path, owner):
    path = settings._path(owner, tmp_path)
    original = json.dumps({"schema_version": 1, "server": "Wonderbane", "character": "Umbra",
                           "policy": "basic", "opening_skill": "563795161", "revision": 9})
    path.write_text(original)
    loaded = settings.load_pve_settings(owner, root=tmp_path)
    assert loaded.opening_skill == "563795161" and loaded.revision == 9
    assert not loaded.buffs.enabled and loaded.buffs.groups == ()
    assert path.read_text() == original
    updated = save(owner, tmp_path, replace(loaded, buffs=buff_intent()), expected=loaded)
    stored = json.loads(path.read_text())
    assert stored["schema_version"] == 4 and stored["revision"] == 10
    assert stored["opening_skill"] == "563795161"
    assert settings.load_pve_settings(owner, root=tmp_path) == updated
    with pytest.raises(ValueError, match="changed"):
        save(owner, tmp_path, loaded, expected=loaded)


def test_buff_config_edit_preserves_opener_and_disable_preserves_groups(cli, owner, tmp_path):
    assert command._configure_pve_settings(process_id=123, opening_skill="My Skill") == 0
    path = tmp_path / "buffs.json"
    path.write_text(json.dumps(buff_intent().as_dict()))
    assert command._configure_pve_settings(process_id=123, buff_config=path) == 0
    configured = settings.load_pve_settings(owner)
    assert configured.opening_skill == "12345" and configured.buffs == buff_intent()
    assert command._configure_pve_settings(process_id=123, buffs_enabled=False) == 0
    disabled = settings.load_pve_settings(owner)
    assert not disabled.buffs.enabled and disabled.buffs.groups == configured.buffs.groups
    assert disabled.opening_skill == configured.opening_skill


@pytest.mark.parametrize("field,value", [("enabled", 1), ("groups", {}), ("observed", True)])
def test_invalid_buff_configuration_never_changes_saved_intent(cli, owner, tmp_path, field, value):
    original = settings.load_pve_settings(owner)
    document = buff_intent().as_dict()
    document[field] = value
    path = tmp_path / "invalid-buffs.json"
    path.write_text(json.dumps(document))
    assert command._configure_pve_settings(process_id=123, buff_config=path) == 2
    assert settings.load_pve_settings(owner) == original


def test_buff_config_rejects_foreign_power_coverage_and_duplicate_actions():
    from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
    from shadowbane_lab.pve.preparation import PreparationAction
    action = BuffAction(PreparationAction("precision", power_id=429545819), 429545819)
    with pytest.raises(ValueError, match="own native definition"):
        replace(action, coverage_power_id=429021400)
    with pytest.raises(ValueError, match="unique"):
        BuffSettings(True, (BuffGroup("one", (action,)), BuffGroup("two", (action,))))
