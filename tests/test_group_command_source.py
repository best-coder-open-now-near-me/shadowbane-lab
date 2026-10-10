from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from shadowbane_lab.manager import group_command_source as m


@pytest.mark.parametrize("enabled,grouped", [(False, True), (True, False), (True, True)])
def test_population_is_lazy_but_receive_and_scene_checks_remain(monkeypatch, enabled, grouped):
    local = S(object_type=42, object_uuid=53)
    character = Mock()
    character.binding = S(process_creation_filetime_utc=456, object_key=local, identity=object())
    character.__enter__ = Mock(return_value=character)
    character.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(m, "open_native_character_session", Mock(return_value=character))
    monkeypatch.setattr(m, "WindowsSharedMemorySnapshotReader", Mock())
    messages, updates = Mock(), Mock()
    messages.drain.return_value = {"sequence": 3}
    updates.drain.return_value = {"sequence": 6}
    readers = Mock(side_effect=[messages, updates])
    monkeypatch.setattr(m, "GroupPublicationReader", readers)
    context = S(members=((100, 200, 123, 53, 0),) if grouped else (), digest=b"g" * 32)
    group = Mock()
    group.observe_context.return_value = context
    group.observe.return_value = S(members=(
        [S(object_type=123, object_uuid=53, first_name="Alice")] if grouped else []))
    monkeypatch.setattr(m, "load_bundled_native_group_profile", Mock())
    monkeypatch.setattr(m, "NativeGroupReader", Mock(return_value=group))
    profile = Mock()
    population = Mock()
    population.observe.return_value = S(local_player_object_key=local, characters=[])
    factory = Mock(return_value=population)
    monkeypatch.setattr(m, "load_bundled_native_character_population_profile", profile)
    monkeypatch.setattr(m, "NativeCharacterPopulationReader", factory)
    settings = S(group_commands=S(enabled=enabled))
    monkeypatch.setattr(m, "load_pve_settings", Mock(return_value=settings))
    scene_reader = Mock(return_value=S(flags=m.BINDINGS, grant=S(scene=7), tick=1000))
    monkeypatch.setattr(m, "read_snapshot", scene_reader)
    monkeypatch.setattr(m, "tick_ms", lambda: 1001)
    source = m.NativeGroupCommandSource(S(game_process_id=123,
        game_process_started_at_100ns=456, game_window_handle=789))
    try:
        message_batch, update_batch, current, _ = source.read()
        assert message_batch == {"sequence": 3} and update_batch == {"sequence": 6}
        assert current["enabled"] is enabled
        assert current["positions"] == {}
        assert current["scene"] == 7 and current["local"] == (42, 53)
        assert group.observe_context.call_count == 2
        assert scene_reader.call_count == 2
        if enabled and grouped:
            factory.assert_called_once()
            population.observe.assert_called_once()
        else:
            factory.assert_not_called()
            profile.assert_not_called()
            population.observe.assert_not_called()
        # Enabling/joining begins ordinary exact population observation; no reader
        # or history reset is required and the borrowed reader is reused thereafter.
        settings.group_commands.enabled = True
        context.members = ((100, 200, 123, 53, 0),)
        group.observe.return_value = S(members=[
            S(object_type=123, object_uuid=53, first_name="Alice")])
        source.read()
        source.read()
        assert factory.call_count == 1
        assert population.observe.call_count == (3 if enabled and grouped else 2)
        assert messages.drain.call_count == updates.drain.call_count == 3
        assert readers.call_count == 2
    finally:
        source.close()
    character.__exit__.assert_called_once()


@pytest.mark.parametrize("flags,tick,scene", [
    (0, 1000, 7), (m.BINDINGS | m.TERMINAL, 1000, 7),
    (m.BINDINGS, 400, 7), (m.BINDINGS, 1002, 7), (m.BINDINGS, 1000, 8)])
def test_final_scene_must_still_be_live_and_fresh(monkeypatch, flags, tick, scene):
    monkeypatch.setattr(m, "WindowsSharedMemorySnapshotReader", Mock())
    monkeypatch.setattr(m, "GroupPublicationReader", Mock())
    source = m.NativeGroupCommandSource(S(game_process_id=123,
        game_process_started_at_100ns=456, game_window_handle=789))
    source.character = Mock()
    source.character.binding = S(object_key=S(object_type=42, object_uuid=53), identity=object())
    source.group = Mock()
    source.group.observe_context.return_value = S(members=(), digest=b"g" * 32)
    source.group.observe.return_value = S(members=[])
    monkeypatch.setattr(m, "load_pve_settings", Mock(return_value=S(
        group_commands=S(enabled=True))))
    monkeypatch.setattr(m, "tick_ms", lambda: 1001)
    monkeypatch.setattr(m, "read_snapshot", Mock(side_effect=[
        S(flags=m.BINDINGS, tick=1000, grant=S(scene=7)),
        S(flags=flags, tick=tick, grant=S(scene=scene))]))
    with pytest.raises(ValueError, match="scene changed or expired"):
        source.read()
    assert source.character is None
