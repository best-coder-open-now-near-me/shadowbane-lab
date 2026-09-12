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
