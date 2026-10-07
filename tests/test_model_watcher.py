import importlib.util
import json
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


def run_fake(tmp_path, *, max_bytes=10000, population_error=False):
    output = tmp_path / "run"
    process = SimpleNamespace(
        pid=7,
        process_creation_filetime_utc=123,
        executable_sha256="a" * 64,
        executable_path=tmp_path / "sb.exe",
    )
    closed = []
    process.close = lambda: closed.append(True)
    observation = SimpleNamespace(
        local_player_object_key=None, rejected_candidates=0, characters=[]
    )
    with (
        patch.object(watcher.WindowsReadOnlyProcessMemory, "open_unique", return_value=process),
        patch.object(watcher, "NativeCharacterPopulationReader") as population,
        patch.object(watcher, "NativeCurrentZoneReader") as zone,
        patch.object(watcher, "cache_inventory"),
        patch.object(watcher.time, "sleep", side_effect=lambda _: (output / "STOP").touch()),
    ):
        if population_error:
            population.return_value.observe.side_effect = RuntimeError("unavailable")
        else:
            population.return_value.observe.return_value = observation
        zone.return_value.observe.side_effect = RuntimeError("loading")
        result = watcher.collect(output, seconds=100, max_bytes=max_bytes)
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
