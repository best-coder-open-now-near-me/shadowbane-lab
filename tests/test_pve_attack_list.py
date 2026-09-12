import multiprocessing
from pathlib import Path
from unittest.mock import patch

import pytest

from shadowbane_lab.pve.attack_list import AttackListEntry, AttackListOwner, AttackListStore


def _add_in_process(root, number, ready, release):
    store = AttackListStore(Path(root), AttackListOwner("server", "player"))
    ready.put(number)
    if not release.wait(10):
        raise RuntimeError("parent did not release writers")
    store.add(AttackListEntry(str(number), f"Enemy {number}", "response", str(number)))


def test_independent_process_updates_survive_reload(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, release = context.Queue(), context.Event()
    children = [context.Process(target=_add_in_process, args=(tmp_path, n, ready, release))
                for n in range(3)]
    try:
        for child in children:
            child.start()
        assert {ready.get(timeout=15) for _ in children} == {0, 1, 2}
        release.set()
        for child in children:
            child.join(15)
            assert child.exitcode == 0
    finally:
        release.set()
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(5)
        ready.close()
    snapshot = AttackListStore(tmp_path, AttackListOwner("server", "player")).snapshot()
    assert snapshot.revision == 3
    assert {e.entry_id for e in snapshot.entries} == {"0", "1", "2"}


def test_persistent_sources_deduplicate_and_require_explicit_removal(tmp_path):
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    manual = AttackListEntry("enemy", "Enemy", "manual", "command-1")
    saved = store.add(manual)
    assert store.add(AttackListEntry("enemy", "Enemy", "response", "hit-1")) == saved
    assert AttackListStore(tmp_path, store.owner).snapshot() == saved
    assert store.remove("enemy").entries == ()
    assert store.remove("enemy").revision == 2


def test_owner_isolation_and_clear(tmp_path):
    stores = [AttackListStore(tmp_path, AttackListOwner(server, player))
              for server, player in [("one", "player"), ("two", "player"), ("one", "other")]]
    for store in stores:
        store.add(AttackListEntry("enemy", "Enemy", "response", "hit"))
    stores[0].clear()
    assert not stores[0].snapshot().entries
    assert all(store.snapshot().entries for store in stores[1:])


def test_failed_publish_keeps_prior_intent(tmp_path):
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    original = store.add(AttackListEntry("enemy", "Enemy", "manual", "command"))
    with patch("shadowbane_lab.pve.attack_list.publish_atomic_record", side_effect=OSError):
        with pytest.raises(OSError):
            store.clear()
    assert store.snapshot() == original


def test_corrupt_record_is_not_silently_replaced(tmp_path):
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        store.add(AttackListEntry("enemy", "Enemy", "manual", "command"))
    assert store.path.read_text() == "broken"

@pytest.mark.parametrize("source", ["manual", "response"])
def test_command_removal_is_explicit_for_both_sources(tmp_path, source):
    from shadowbane_lab.pve.attack_list_commands import apply_attack_list_command

    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    entry = AttackListEntry("enemy", "Enemy", source, "evidence")
    assert apply_attack_list_command("/blacklist add", store, entry)["entries"]
    assert apply_attack_list_command("/blacklist", store)["entries"]
    assert not apply_attack_list_command("/blacklist remove enemy", store)["entries"]


@pytest.mark.parametrize("command", ["/blacklisted add", "/blacklist add stranger",
                                     "/blacklist clear extra", "/blacklist forget"])
def test_invalid_command_never_changes_list(tmp_path, command):
    from shadowbane_lab.pve.attack_list_commands import apply_attack_list_command

    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    with pytest.raises(ValueError):
        apply_attack_list_command(command, store)
    assert store.snapshot().revision == 0


def test_chat_assembler_captures_attack_list_only():
    from shadowbane_lab.travel.chat import GoChatCommandAssembler

    for text, expected in [("/blacklist add", "/blacklist add"),
                           ("/blacklist list", "/blacklist list"),
                           ("/blacklisted hello", None), ("ordinary private chat", None)]:
        assembler = GoChatCommandAssembler()
        assembler.handle_enter()
        for character in text:
            assembler.handle_character(character)
        assert assembler.handle_enter().submitted_command == expected


@pytest.mark.parametrize("change", ["process", "foreground"])
def test_command_rejects_lifetime_change_before_storage(tmp_path, change):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from shadowbane_lab.pve.attack_list_commands import run_attack_list_command

    window = SimpleNamespace(process_id=10, process_started_at_100ns=100, window_handle=20)
    other = SimpleNamespace(process_id=11, process_started_at_100ns=200, window_handle=21)
    guard = MagicMock()
    guard.require_target.side_effect = [window, other if change == "foreground" else window]
    session = MagicMock()
    session.__enter__.return_value = session
    session.binding = SimpleNamespace(
        process_creation_filetime_utc=200 if change == "process" else 100,
        identity=SimpleNamespace(server_name="server", character_name="player"),
    )
    with patch("shadowbane_lab.pve.attack_list_commands.open_active_character_config",
               return_value=session):
        with pytest.raises(ValueError):
            run_attack_list_command("/blacklist clear", guard, root=tmp_path)
    assert not list(tmp_path.glob("*.json"))
    session.__exit__.assert_called_once()


def test_listener_presents_success_instead_of_rejection(capsys):
    from shadowbane_lab.cli_commands.client_listener import _print_go_listener_event

    result = {"action": "list", "revision": 0, "entries": []}
    _print_go_listener_event("attack-list", as_json=False, result=result)
    assert "Empty" in capsys.readouterr().out
    _print_go_listener_event("attack-list", as_json=True, result=result)
    assert '"ok": true' in capsys.readouterr().out


def _observed_target():
    from shadowbane_lab.client_observation.native_object import NativeObjectKey
    from shadowbane_lab.pve.attack_list import AttackTargetObservation

    return AttackTargetObservation("ab" * 32, 42, 1000,
                                   NativeObjectKey(1, 53), NativeObjectKey(2, 53), "player")


def test_target_evidence_survives_restart_without_claiming_durable_identity(tmp_path):
    observation = _observed_target()
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    entry = AttackListEntry(observation.entry_id, "Observed player", "manual", "selection",
                           observation)
    store.add(entry)
    loaded = AttackListStore(tmp_path, store.owner).snapshot().entries[0]
    assert loaded == entry
    assert loaded.observation.process_started_at_100ns == 1000
    assert loaded.observation.target_key.object_type == 2


def test_legacy_intent_migrates_unresolved_without_losing_entries(tmp_path):
    import json

    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    legacy = {"entry_id": "old", "label": "Old enemy", "source": "manual",
              "evidence_id": "old-selection"}
    store.path.write_text(json.dumps({"schema": 1, "owner": ["server", "player"],
                                     "revision": 4, "entries": [legacy]}))
    snapshot = store.snapshot()
    assert snapshot.entries[0].observation is None
    assert snapshot.revision == 4
    observation = _observed_target()
    store.add(AttackListEntry(observation.entry_id, "New enemy", "manual", "new-selection",
                             observation))
    raw = json.loads(store.path.read_text())
    assert raw["schema"] == 3
    assert raw["revision"] == 5
    assert next(e for e in raw["entries"] if e["entry_id"] == "old")["observation"] is None
    assert len(AttackListStore(tmp_path, store.owner).snapshot().entries) == 2


def test_forged_identity_evidence_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not match"):
        AttackListEntry("different", "Enemy", "manual", "selection", _observed_target())


@pytest.mark.parametrize("field,value", [("process_id", True), ("process_started_at_100ns", 0),
                                         ("executable_sha256", "unknown")])
def test_invalid_evidence_never_forms_a_binding(field, value):
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(_observed_target(), **{field: value})


def test_changed_process_or_object_has_a_different_observation_identity():
    from dataclasses import replace

    from shadowbane_lab.client_observation.native_object import NativeObjectKey

    observation = _observed_target()
    assert replace(observation, process_started_at_100ns=2000).entry_id != observation.entry_id
    assert replace(observation, target_key=NativeObjectKey(3, 53)).entry_id != observation.entry_id


def test_fresh_matching_observation_enriches_legacy_without_rewriting_provenance(tmp_path):
    observation = _observed_target()
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    store.add(AttackListEntry(observation.entry_id, "Saved enemy", "manual", "original-command"))
    result = store.add(AttackListEntry(observation.entry_id, "Observed enemy", "response", "hit",
                                      observation))
    assert len(result.entries) == 1
    assert result.entries[0].observation == observation
    assert result.entries[0].source == "manual"
    assert result.entries[0].evidence_id == "original-command"


def test_persistent_player_entry_survives_observer_restart(tmp_path):
    from dataclasses import replace

    from shadowbane_lab.pve.attack_list import AttackPlayerIdentity

    observation = _observed_target()
    player = AttackPlayerIdentity("server", observation.target_key, "lowercase")
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    first = AttackListEntry(
        player.entry_id, player.name, "manual", "selection", observation, player
    )
    saved = store.add(first)
    new_observation = replace(observation, process_id=99, process_started_at_100ns=2000)
    repeated = AttackListEntry(player.entry_id, player.name, "response", "new-hit",
                               new_observation, player)
    assert store.add(repeated) == saved
    assert AttackListStore(tmp_path, store.owner).snapshot().entries[0].player_identity == player
    assert replace(player, server="another").entry_id != player.entry_id


def test_same_key_changed_name_requires_explicit_resolution(tmp_path):
    from dataclasses import replace

    from shadowbane_lab.pve.attack_list import AttackPlayerIdentity

    observation = _observed_target()
    player = AttackPlayerIdentity("server", observation.target_key, "enemy")
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    original = store.add(AttackListEntry(player.entry_id, player.name, "manual", "selection",
                                        observation, player))
    changed = replace(player, name="different")
    with pytest.raises(ValueError, match="differs"):
        store.add(AttackListEntry(changed.entry_id, changed.name, "response", "hit",
                                  observation, changed))
    assert store.snapshot() == original


def test_invalid_player_identity_reports_validation_error():
    observation = _observed_target()
    with pytest.raises(ValueError, match="invalid player identity"):
        AttackListEntry(observation.entry_id, "Enemy", "manual", "selection", observation, "bad")


def test_invalid_command_never_opens_or_scans_client():
    from shadowbane_lab.pve.attack_list_commands import run_attack_list_command

    class Guard:
        def require_target(self):
            pytest.fail("invalid syntax reached the client")

    with pytest.raises(ValueError, match="only remove"):
        run_attack_list_command("/blacklist add someone", Guard())


def test_schema_two_observation_stays_unresolved_on_upgrade(tmp_path):
    import json

    observation = _observed_target()
    old = AttackListEntry(observation.entry_id, "Enemy", "manual", "selection", observation)
    legacy = old.as_dict()
    legacy.pop("player_identity")
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    store.path.write_text(json.dumps({"schema": 2, "owner": ["server", "player"],
                                     "revision": 7, "entries": [legacy]}))
    assert store.snapshot().entries == (old,)
    store.add(AttackListEntry("another", "Other", "manual", "legacy"))
    reread = AttackListStore(tmp_path, store.owner).snapshot()
    retained = next(e for e in reread.entries if e.entry_id == old.entry_id)
    assert retained.observation == observation
    assert retained.player_identity is None
    assert reread.revision == 8


@pytest.mark.parametrize("changed,party_failure", [(False, False), (True, False), (False, True)])
def test_command_revalidates_selected_player_and_reports_party(tmp_path, changed, party_failure):
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    from shadowbane_lab.pve.attack_list_commands import run_attack_list_command

    observation = _observed_target()
    key = observation.target_key
    window = NS(process_id=42, process_started_at_100ns=1000, window_handle=20)
    guard = MagicMock()
    guard.require_target.return_value = window
    session = MagicMock()
    session.__enter__.return_value = session
    session.binding = NS(process_creation_filetime_utc=1000, executable_sha256="ab" * 32,
                         identity=NS(server_name="server", character_name="player"))
    session.reader.observe_selected_player.return_value = NS(
        object_key=key, character_name="enemy", server_name="server")
    target = NS(token="selected", object_key=key, character_kind=NS(value="player"))
    population = NS(characters=(target,), selected_target_token="selected",
                    local_player_object_key=observation.local_player_key)
    latest = NS(characters=(), selected_target_token=None,
                local_player_object_key=observation.local_player_key) if changed else population
    reader = MagicMock()
    reader.observe.side_effect = [population, latest]
    group = MagicMock()
    group.observe.return_value = NS(members=(NS(object_type=key.object_type,
                                               object_uuid=key.object_uuid),))
    if party_failure:
        group.observe.side_effect = OSError("party unavailable")
    module = "shadowbane_lab.pve.attack_list_commands."
    with patch(module + "open_active_character_config", return_value=session), \
         patch(module + "NativeCharacterPopulationReader", return_value=reader), \
         patch(module + "NativeGroupReader", return_value=group):
        if changed:
            with pytest.raises(ValueError, match="selection changed"):
                run_attack_list_command("/blacklist add", guard, root=tmp_path)
            assert not list(tmp_path.glob("*.json"))
        else:
            result = run_attack_list_command("/blacklist add", guard, root=tmp_path)
            expected_party = "unknown" if party_failure else "protected"
            assert result["entries"][0]["party_status"] == expected_party
            assert result["entries"][0]["label"] == "enemy"
            assert len(AttackListStore(tmp_path, AttackListOwner("server", "player"))
                       .snapshot().entries) == 1


def test_unresolved_and_unavailable_party_status_remain_explicit(capsys):
    from shadowbane_lab.cli_commands.client_listener import _print_go_listener_event
    from shadowbane_lab.pve.attack_list_commands import describe_attack_list_result

    entry = AttackListEntry("legacy", "Old enemy", "manual", "old")
    result = describe_attack_list_result({"action": "list", "revision": 1,
                                         "entries": [entry.as_dict()]}, set())
    assert result["entries"][0]["identity_status"] == "unresolved"
    assert result["entries"][0]["party_status"] == "unknown"
    _print_go_listener_event("attack-list", as_json=False, result=result)
    output = capsys.readouterr().out
    assert "identity unresolved" in output
    assert "party status unknown" in output
    assert "legacy" in output


def test_listener_edits_list_and_cancels_while_pve_is_blocked(tmp_path, monkeypatch):
    from contextlib import ExitStack, nullcontext
    from dataclasses import replace
    from threading import Event, Thread
    from types import SimpleNamespace as NS
    from unittest.mock import MagicMock

    from shadowbane_lab.cli_commands import client_listener as listener
    from shadowbane_lab.client_input import (
        EventEmergencyStop,
        RecordingInputBackend,
        StaticWindowInspector,
        WindowBounds,
        WindowSnapshot,
        load_calibration,
    )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    store = AttackListStore(tmp_path / "ShadowbaneLab" / "attack-lists",
                            AttackListOwner("server", "player"))
    store.add(AttackListEntry("enemy", "Enemy", "manual", "command"))
    template = Path(__file__).parents[1] / "configs" / "wonderbane-travel.template.json"
    profile = replace(load_calibration(template), live_input_enabled=True)
    stop = EventEmergencyStop()
    entered, edited, release = Event(), Event(), Event()
    errors = []
    window = WindowSnapshot("sb.exe", "Shadowbane", WindowBounds(0, 0, 1920, 955),
                            1.0, True, True, process_id=42,
                            process_started_at_100ns=1000, window_handle=20)
    session = MagicMock()
    session.__enter__.return_value = session
    session.binding = NS(process_creation_filetime_utc=1000,
                         identity=NS(server_name="server", character_name="player"))

    def blocked_pve(**kwargs):
        entered.set()
        assert release.wait(5), "callback did not release the held PvE operation"
        assert edited.is_set(), "list edit waited behind PvE"
        assert kwargs["stop_signal"].is_set(), "interaction did not cancel held PvE"

    class CallbackListener:
        is_alive = True

        def __init__(self, _guard, *, on_command, on_interaction, on_pointer):
            self.submit, self.cancel = on_command, on_interaction

        def __enter__(self):
            def drive():
                try:
                    self.submit("/pve")
                    assert entered.wait(5), "PvE never entered its operation boundary"
                    self.submit("/blacklist clear")
                    assert store.snapshot().entries == ()
                    edited.set()
                    self.cancel()
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    stop.trip()
                    release.set()
            self.thread = Thread(target=drive)
            self.thread.start()
            return self

        def __exit__(self, *_args):
            release.set()
            self.thread.join(5)
            assert not self.thread.is_alive()

    with ExitStack() as stack:
        for name, value in {
            "load_calibration": MagicMock(return_value=profile),
            "WindowsForegroundWindowInspector": lambda: StaticWindowInspector(window),
            "WindowsHotkeyEmergencyStop": lambda: nullcontext(stop),
            "WindowsGoChatCommandListener": CallbackListener,
            "WindowsZoneSearchOverlay": lambda: nullcontext(MagicMock()),
            "PyAutoGuiBackend": RecordingInputBackend,
            "_run_pve": blocked_pve,
        }.items():
            stack.enter_context(patch.object(listener, name, value))
        stack.enter_context(patch.object(listener.attack_list_commands,
                                         "open_active_character_config", return_value=session))
        stack.enter_context(patch.object(listener.attack_list_commands,
                                         "NativeGroupReader", side_effect=OSError("unavailable")))
        result = listener._listen_for_go_commands(
            destination_state_path=tmp_path / "travel.json", client_profile_path=template,
            native_position_profile_path=None, native_vitals_profile_path=None,
            native_runegate_profile_path=None, world_def_path=None,
            named_destination_overrides_path=None, pve_client_profile_path=template,
            pve_hotbar_config_path=None, pve_evidence_directory=None,
            navigation_cache_directory=None, pve_max_kills=3, pve_max_seconds=300,
            pve_max_encounter_seconds=120, pve_recovery_timeout_seconds=30, pve_poll_ms=100,
            max_seconds=300, wait_for_client_seconds=0, poll_ms=100, click_interval_ms=4000,
            live=True, as_json=True,
        )
    assert not errors
    assert result == 0
    assert edited.is_set()


def _conditional_add_in_process(root, number, ready, release, results):
    store = AttackListStore(Path(root), AttackListOwner("server", "player"))
    revision = store.snapshot().revision
    ready.put(number)
    if not release.wait(10):
        raise RuntimeError("parent did not release writers")
    try:
        store.add(AttackListEntry(str(number), "Enemy", "manual", "command"),
                  expected_revision=revision)
        results.put("saved")
    except ValueError as exc:
        results.put(str(exc))


def test_two_process_commands_cannot_both_commit_the_same_revision(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, results, release = context.Queue(), context.Queue(), context.Event()
    children = [context.Process(target=_conditional_add_in_process,
                                args=(tmp_path, n, ready, release, results)) for n in range(2)]
    try:
        for child in children:
            child.start()
        assert {ready.get(timeout=15) for _ in children} == {0, 1}
        release.set()
        outcomes = [results.get(timeout=15) for _ in children]
        assert outcomes.count("saved") == 1
        assert sum("changed during command" in outcome for outcome in outcomes) == 1
        for child in children:
            child.join(15)
            assert child.exitcode == 0
    finally:
        release.set()
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(5)
        ready.close()
        results.close()
    snapshot = AttackListStore(tmp_path, AttackListOwner("server", "player")).snapshot()
    assert snapshot.revision == 1
    assert len(snapshot.entries) == 1


@pytest.mark.parametrize(
    "command", ["/blacklist add", "/blacklist remove enemy", "/blacklist clear"]
)
def test_command_rejects_stale_revision_without_losing_concurrent_work(tmp_path, command):
    from shadowbane_lab.pve.attack_list_commands import apply_attack_list_command

    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    entry = AttackListEntry("enemy", "Enemy", "manual", "command")
    first = store.add(entry)
    current = store.add(AttackListEntry("new", "New enemy", "response", "hit"))
    with pytest.raises(ValueError, match="changed during command"):
        apply_attack_list_command(command, store, entry, expected_revision=first.revision)
    assert store.snapshot() == current


def test_cross_server_player_identity_cannot_enter_another_owner_list(tmp_path):
    from shadowbane_lab.pve.attack_list import AttackPlayerIdentity

    observation = _observed_target()
    player = AttackPlayerIdentity("other-server", observation.target_key, "enemy")
    store = AttackListStore(tmp_path, AttackListOwner("server", "player"))
    with pytest.raises(ValueError, match="target server"):
        store.add(AttackListEntry(player.entry_id, "Enemy", "manual", "command",
                                  observation, player))
    assert store.snapshot().entries == ()
