import json

import pytest

from shadowbane_lab.cases.capture import parse_capture_record
from shadowbane_lab.character_capture.recording import Recording, RecordingLimit
from shadowbane_lab.evidence import verify_bundle


def test_incident_annotations_and_portable_contracts(tmp_path):
    now = [100_000_000_000]
    r = Recording(tmp_path, {"character_name": "Fixture"}, clock=lambda: now[0])
    r.emit("character", {"equipment": []})
    now[0] += 10_000_000_000
    incident = r.mark("gear changed")
    now[0] += 2_000_000_000
    r.annotate(incident, intent="equip ring", expected="more mana", actual="no change")
    now[0] += 40_000_000_000
    path = r.finish("test")
    records = [
        parse_capture_record(json.loads(s))
        for s in (path / "timeline.jsonl").read_text().splitlines()
    ]
    assert [x.correlation_id for x in records[1:]] == [incident, incident]
    summary = json.loads((path / "summary.json").read_text())
    assert not summary["incidents"][0]["pre_window_complete"]
    assert summary["incidents"][0]["post_window_complete"]
    manifest = verify_bundle(path / "evidence.zip")
    assert manifest.run_id == r.run_id
    assert len(manifest.artifacts) == 3


def test_early_stop_preserves_partial_post_window(tmp_path):
    now = [100_000_000_000]
    r = Recording(tmp_path, {}, clock=lambda: now[0])
    incident = r.mark("failure")
    r.finish("game exited", failed=True)
    summary = json.loads((r.path / "summary.json").read_text())
    assert summary["incidents"][0]["incident_id"] == incident
    assert not summary["incidents"][0]["post_window_complete"]
    assert verify_bundle(r.path / "evidence.zip").terminal_state.value == "failed"


@pytest.mark.parametrize("fault", ["size", "time", "clock", "unknown_incident", "note_length"])
def test_rejects_unbounded_or_uncorrelated_records(tmp_path, fault):
    now = [10_000_000_000]
    r = Recording(tmp_path, {}, maximum_bytes=2048, maximum_seconds=2, clock=lambda: now[0])
    if fault == "size":
        with pytest.raises(RecordingLimit):
            r.emit("test", {"huge": "x" * 4000})
    elif fault == "time":
        now[0] += 3_000_000_000
        with pytest.raises(RecordingLimit):
            r.emit("test", {})
    elif fault == "clock":
        with pytest.raises(ValueError):
            r.emit("test", {}, at=now[0] - 1)
    elif fault == "unknown_incident":
        with pytest.raises(ValueError):
            r.annotate("wrong", intent="a", expected="", actual="")
    else:
        identifier = r.mark("test")
        with pytest.raises(ValueError):
            r.annotate(identifier, intent="x" * 4001, expected="", actual="")
    r.finish("test ended")


def test_records_cannot_be_replaced_after_seal(tmp_path):
    r = Recording(tmp_path, {})
    r.emit("test", {"value": 1})
    r.finish("done")
    with pytest.raises(RuntimeError):
        r.emit("test", {})
    with pytest.raises(RuntimeError):
        r.finish("again")
