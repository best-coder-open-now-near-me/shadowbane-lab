import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.character_capture import watcher as w


def setup(monkeypatch, tmp_path):
    process = Mock(pid=4, process_creation_filetime_utc=5)
    session = Mock()
    session.binding.identity.character_name = "Fixture"
    session.binding.identity.server_name = "Local"
    session.binding.as_dict.return_value = {"character_name": "Fixture", "server_name": "Local"}
    monkeypatch.setattr(w.WindowsReadOnlyProcessMemory, "open_unique", lambda _: process)
    monkeypatch.setattr(w, "NativeCharacterConfigReader", lambda _: None)
    monkeypatch.setattr(w, "NativeCharacterSession", lambda _: session)
    monkeypatch.setattr(w, "NativeCharacterBuildReader", lambda _: Mock())
    monkeypatch.setattr(w, "NativePlayerSnapshotReader", lambda *_: Mock())
    monkeypatch.setattr(w, "load_bundled_native_player_snapshot_profiles", lambda: ())
    snapshot = {"current_build": {"equipment": [], "applied_runes": []}}
    monkeypatch.setattr(w, "observe_character", Mock(return_value=snapshot))
    monkeypatch.setattr(w, "WindowsForegroundWindowInspector", lambda: Mock(inspect=lambda: None))
    metrics = Mock()
    metrics.sample.return_value = SimpleNamespace(
        identity=SimpleNamespace(exact_key=(4, 5)), metrics={"memory": 1}
    )
    monkeypatch.setattr(w, "WindowsProcessProbe", lambda: metrics)
    monkeypatch.setattr(w, "WindowsNetworkProbe", lambda: Mock(sample=lambda _: {}))
    return w.Watcher(tmp_path, "Fixture", "Local"), process, session, metrics


def drain(watcher):
    items = []
    while not watcher.updates.empty():
        items.append(watcher.updates.get_nowait())
    return items


def test_stop_drains_accepted_mark_and_annotation_commands(monkeypatch, tmp_path):
    watcher, process, *_ = setup(monkeypatch, tmp_path)
    original = watcher.notify

    def notify(kind, **payload):
        original(kind, **payload)
        if kind == "started":
            watcher.command("mark", label="noticed it")
        elif kind == "marked":
            watcher.command(
                "annotate",
                incident_id=payload["incident_id"],
                intent="cast",
                expected="damage",
                actual="nothing",
            )
            watcher.stop()

    watcher.notify = notify
    watcher._run()
    events = drain(watcher)
    assert {"marked", "annotated", "finished", "stopped"} <= {x["kind"] for x in events}
    assert not next(x for x in events if x["kind"] == "finished")["failed"]
    process.close.assert_called_once()


@pytest.mark.parametrize("fault", ["identity", "metrics", "input"])
def test_binding_and_producer_failures_seal_failed_session(monkeypatch, tmp_path, fault):
    watcher, process, session, metrics = setup(monkeypatch, tmp_path)
    if fault == "identity":
        session.require_current.side_effect = RuntimeError("character changed")
    elif fault == "metrics":
        metrics.sample.return_value.identity.exact_key = (4, 6)
    else:
        fake = Mock()
        fake.events = queue.Queue()
        fake.dropped = 0
        fake.error = "hook failed"
        monkeypatch.setattr(w, "WindowsGameInput", lambda *_: fake)
        watcher.inputs = True
    watcher._run()
    events = drain(watcher)
    finished = next(x for x in events if x["kind"] == "finished")
    assert finished["failed"]
    assert events[-1]["kind"] == "stopped"
    process.close.assert_called_once()


def test_wrong_character_stops_before_recording_or_input(monkeypatch, tmp_path):
    watcher, process, session, _ = setup(monkeypatch, tmp_path)
    session.binding.identity.character_name = "Other"
    watcher._run()
    assert not list(tmp_path.iterdir())
    assert "error" in {x["kind"] for x in drain(watcher)}
    process.close.assert_called_once()
