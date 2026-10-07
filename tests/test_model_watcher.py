import importlib.util
import json
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shadowbane_lab.client_observation.native_object import NativeObjectKey

SCRIPT = Path(__file__).parents[1] / "scripts" / "watch-wonderbane-models.py"
spec = importlib.util.spec_from_file_location("model_watcher", SCRIPT)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


def test_catalog_keeps_archive_group_and_resource_identity(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    output = tmp_path / "out"
    output.mkdir()
    for name in ("Mesh.cache", "Render.cache"):
        payload = b"12345678"
        entries = struct.pack("<IIIII", 0, 42, 56, 4, 4)
        entries += struct.pack("<IIIII", 1, 42, 60, 4, 4)
        (cache / name).write_bytes(struct.pack("<IIII", 2, 56, 64, 0) + entries + payload)
    watcher.cache_inventory(cache, output)
    rows = [
        json.loads(line) for line in (output / "cache-resources.jsonl").read_text().splitlines()
    ]
    assert {(r["archive"], r["group_id"], r["resource_id"]) for r in rows} == {
        (a, g, 42) for a in ("Mesh.cache", "Render.cache") for g in (0, 1)
    }
    assert all("payload" not in r for r in rows)
    summary = json.loads((output / "cache-summary.json").read_text())
    assert all(a["stable_file"] for a in summary["archives"])


def test_missing_cache_is_not_empty_success(tmp_path):
    with pytest.raises(FileNotFoundError):
        watcher.cache_inventory(tmp_path / "missing", tmp_path)


def test_existing_evidence_is_never_overwritten(tmp_path):
    with pytest.raises(FileExistsError):
        watcher.collect(tmp_path)


def run_fake(
    tmp_path,
    *,
    max_bytes=10000,
    population_error=False,
    sample_count=1,
    expected_character=None,
    change_character=False,
):
    output = tmp_path / "run"
    process = SimpleNamespace(
        pid=7,
        process_creation_filetime_utc=123,
        executable_sha256="a" * 64,
        executable_path=tmp_path / "sb.exe",
    )
    closed = []
    process.close = lambda: closed.append(True)
    key = NativeObjectKey(123, 53)
    identity = SimpleNamespace(character_name="umbra", server_name="Wonderbane")
    observation = SimpleNamespace(local_player_object_key=key, rejected_candidates=0, characters=[])
    sleeps = []

    def sleep(_):
        sleeps.append(True)
        if len(sleeps) >= sample_count:
            (output / "STOP").touch()

    with (
        patch.object(watcher.WindowsReadOnlyProcessMemory, "open_unique", return_value=process),
        patch.object(watcher, "NativeCharacterConfigReader") as identity_reader,
        patch.object(watcher, "NativeCharacterPopulationReader") as population,
        patch.object(watcher, "NativeCurrentZoneReader") as zone,
        patch.object(watcher, "cache_inventory"),
        patch.object(watcher.time, "sleep", side_effect=sleep),
    ):
        identity_reader.return_value.observe.return_value = identity
        identity_reader.return_value.observe_local_key.return_value = key
        if change_character:
            identity_reader.return_value.observe.side_effect = [
                identity,
                identity,
                SimpleNamespace(character_name="other", server_name="Wonderbane"),
            ]
        if population_error:
            population.return_value.observe.side_effect = RuntimeError("unavailable")
        else:
            population.return_value.observe.return_value = observation
        zone.return_value.observe.side_effect = RuntimeError("loading")
        result = watcher.collect(
            output, seconds=100, max_bytes=max_bytes, expected_character=expected_character
        )
    assert closed == [True]
    return result, json.loads((output / "status.json").read_text()), output


def test_stop_file_and_independent_zone_failure(tmp_path):
    result, status, output = run_fake(tmp_path)
    assert result == 0 and status["stop_reason"] == "requested"
    assert status["samples"] == 1 and status["last_population_ok"]
    row = json.loads((output / "observations.jsonl").read_text())
    assert row["zone_error"] == "loading" and "population" in row


def test_byte_limit_stops_before_writing_oversize_row(tmp_path):
    _, status, output = run_fake(tmp_path, max_bytes=1)
    assert status["stop_reason"] == "size_limit" and status["bytes"] == 0
    assert (output / "observations.jsonl").stat().st_size == 0


def test_population_failure_is_not_reported_as_observed_empty_world(tmp_path):
    _, status, output = run_fake(tmp_path, population_error=True)
    assert not status["last_population_ok"] and status["errors"] == 1
    row = json.loads((output / "observations.jsonl").read_text())
    assert "population" not in row and row["population_error"] == "unavailable"


def test_unknown_client_startup_failure_is_visible(tmp_path):
    output = tmp_path / "run"
    with patch.object(
        watcher.WindowsReadOnlyProcessMemory,
        "open_unique",
        side_effect=RuntimeError("unknown build"),
    ):
        assert watcher.collect(output) == 1
    status = json.loads((output / "status.json").read_text())
    assert status["status"] == "failed" and status["error"] == "unknown build"


def character(key=1, *, current=90, maximum=100, x=1, roles=None):
    return {
        "object_key": {"object_type": key, "object_uuid": 37},
        "kind": "npc",
        "roles": roles or [],
        "owner_object_key": None,
        "health": [current, maximum],
        "position": [x, 2, 3],
    }


def frame(at, characters):
    return {
        "at": at,
        "population": {
            "local_player_object_key": {"id": 123},
            "characters": characters,
            "rejected_candidates": 0,
        },
    }


def test_repeated_motion_and_health_fluctuation_only_updates_summary():
    f = watcher.ObservationFilter()
    assert f.filter(frame("first", [character()])) is not None
    assert f.filter(frame("last", [character(current=70, x=99)])) is None
    record = f.summary()["entities"][0]
    assert record["first_seen"] == "first" and record["last_seen"] == "last"
    assert record["sightings"] == 2 and f.suppressed == 1
    assert record["last_observation"]["position"][0] == 99


def test_death_and_role_changes_are_kept():
    f = watcher.ObservationFilter()
    f.filter(frame("a", [character()]))
    assert (
        f.filter(frame("b", [character(current=0)]))["population"]["events"][0]["event"]
        == "changed"
    )
    assert f.filter(frame("c", [character(current=0, roles=["merchant"])])) is not None


def test_population_reordering_does_not_create_duplicates():
    f = watcher.ObservationFilter()
    f.filter(frame("a", [character(1), character(2)]))
    assert f.filter(frame("b", [character(2), character(1)])) is None


def test_read_failure_does_not_mean_departure_and_recovery_is_retained():
    f = watcher.ObservationFilter()
    f.filter(frame("a", [character()]))
    assert f.filter({"at": "b", "population_error": "loading"}) is not None
    assert f.filter({"at": "c", "population_error": "loading"}) is None
    assert f.summary()["entities"][0]["present"]
    assert f.filter(frame("d", [character()])) is not None
    assert f.filter(frame("e", []))["population"]["events"][0]["event"] == "left"
    assert f.filter(frame("f", [character()]))["population"]["events"][0]["event"] == "returned"
    assert f.summary()["entities"][0]["appearances"] == 2


def test_unchanged_sample_not_written(tmp_path):
    _, status, output = run_fake(tmp_path, sample_count=2)
    assert status["samples"] == 2 and status["written_records"] == 1
    assert status["suppressed_samples"] == 1
    assert len((output / "observations.jsonl").read_text().splitlines()) == 1


def test_wrong_character_is_rejected_before_observation(tmp_path):
    result, status, output = run_fake(tmp_path, expected_character="other")
    assert result == 1 and status["status"] == "failed"
    assert not (output / "observations.jsonl").exists()


def test_character_switch_stops_without_collecting_other_character(tmp_path):
    _, status, output = run_fake(tmp_path, change_character=True)
    assert status["stop_reason"] == "character_changed"
    assert status["samples"] == 0
    assert (output / "observations.jsonl").stat().st_size == 0
