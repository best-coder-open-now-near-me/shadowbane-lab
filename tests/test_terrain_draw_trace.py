from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.diagnostics import terrain_trace as trace
from shadowbane_lab.graphics_lab.control import GraphicsControlTarget


@pytest.fixture
def target(tmp_path):
    return GraphicsControlTarget(123, 456, tmp_path / "sb.exe", "a" * 64,
                                 "unused", tmp_path / "graphics-status-123-456.json")


@pytest.fixture
def payload(target):
    return {
        "schema_version": 1, "extension_version": trace.TRACE_VERSION,
        "process_id": target.process_id,
        "process_creation_filetime_utc": target.process_creation_filetime_utc,
        "executable_sha256": target.executable_sha256,
        "sequence": 1, "qpc_frequency": 1000, "requested_qpc": 100,
        "start_qpc": 105, "end_qpc": 150, "query_ticks": 20,
        "unit_count": 1, "omitted_units": 0, "helpers_available": True,
        "retained_submissions": 1, "observed_submissions": 1,
        "capacity_skipped": 0, "unsafe_query_skipped": 0, "query_budget_skipped": 0,
        "reviewed_interval_complete": True, "main_clear_seen": True, "done3d_seen": True,
        "extra_depth_clear": False, "context_or_thread_mismatch": False,
        "scope": {"pixels_read": False, "texture_bytes_read": False},
        "draws": [{"ordinal": 1, "qpc": 110, "active_unit_restored": True,
                   "textures": [{"unit": 0, "binding": 17}], "state": [0] * 11,
                   "model_view": [0] * 16, "projection": [0] * 16,
                   "viewport": [0] * 4, "color": [0] * 4, "alpha_ref": [0.5]}],
    }


def test_complete_trace_is_not_claimed_as_complete_renderer_coverage(payload, target):
    result = trace.assess_trace(payload, target, 100)
    assert result["status"] == "captured"
    assert result["unique_unit_bindings"] == 1
    assert result["observer_query_ms"] == 20
    assert "not cache IDs" in result["scope_note"]


@pytest.mark.parametrize("field,value", [
    ("process_id", 124), ("process_creation_filetime_utc", 457),
    ("executable_sha256", "b" * 64), ("schema_version", True),
    ("extension_version", "1.6.11"), ("requested_qpc", 99),
    ("unit_count", 5), ("retained_submissions", 8193),
    ("observed_submissions", 2), ("qpc_frequency", 0),
    ("scope", None), ("start_qpc", 151), ("end_qpc", 99),
])
def test_wrong_identity_stale_and_malformed_are_rejected(payload, target, field, value):
    payload[field] = value
    with pytest.raises(ValueError):
        trace.assess_trace(payload, target, 100)


def test_incomplete_observation_remains_explicit(payload, target):
    payload["capacity_skipped"] = 4
    payload["observed_submissions"] += 4
    payload["omitted_units"] = 2
    payload["done3d_seen"] = False
    payload["draws"][0]["active_unit_restored"] = False
    payload["draws"][0]["model_view"][0] = None
    result = trace.assess_trace(payload, target, 100)
    assert result["status"] == "captured_with_limits"
    assert not result["reviewed_interval_complete"]
    assert len(result["limitations"]) == 5


def test_nonfinite_json_numbers_are_not_accepted(payload, target):
    payload["draws"][0]["projection"][0] = float("nan")
    with pytest.raises(ValueError, match="number"):
        trace.assess_trace(payload, target, 100)


def test_wait_accepts_only_new_exact_lifetime_file(payload, target):
    stale = target.status_path.parent / "terrain-trace-123-456-1.json"
    stale.write_text(json.dumps(payload), encoding="utf-8")
    fresh = target.status_path.parent / "terrain-trace-123-456-2.json"
    payload["sequence"] = 2
    fresh.write_text(json.dumps(payload), encoding="utf-8")
    path, result = trace.wait_for_trace(target, {stale}, 100, 1, alive=lambda _: True)
    assert path == fresh and result["sequence"] == 2
    assert len(list(target.status_path.parent.iterdir())) == 2  # no copied/exported report


def test_wait_rejects_ambiguity_and_process_exit(payload, target):
    for sequence in (1, 2):
        path = target.status_path.parent / f"terrain-trace-123-456-{sequence}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="multiple"):
        trace.wait_for_trace(target, set(), 100, 1, alive=lambda _: True)
    with pytest.raises(RuntimeError, match="lifetime ended"):
        trace.wait_for_trace(target, set(), 100, 1, alive=lambda _: False)


def test_partial_is_never_success_and_timeout_does_not_retry(target):
    partial = target.status_path.parent / "terrain-trace-123-456-1.json.partial"
    partial.write_text("{", encoding="utf-8")
    with pytest.raises(TimeoutError):
        trace.wait_for_trace(target, set(), 100, 0.01, alive=lambda _: True)


@pytest.mark.skipif(os.name != "nt", reason="Windows request API contract")
@pytest.mark.parametrize("busy", [False, True])
def test_collector_uses_idle_gate_and_releases_handles(monkeypatch, target, busy):
    target.status_path.write_text(json.dumps({
        "extension_version": trace.TRACE_VERSION, "runtime_profile": "full-renderer",
    }), encoding="utf-8")
    kernel = SimpleNamespace(**{name: Mock(return_value=True) for name in (
        "CloseHandle", "SetEvent", "ResetEvent", "ReleaseMutex",
    )})
    kernel.GetDriveTypeW = Mock(return_value=3)
    kernel.CreateMutexW = Mock(return_value=1)
    kernel.OpenEventW = Mock(side_effect=[2, 3])
    kernel.WaitForSingleObject = Mock(side_effect=[0, 258 if busy else 0])

    def counter(pointer):
        pointer._obj.value = 100
        return True

    kernel.QueryPerformanceCounter = Mock(side_effect=counter)
    monkeypatch.setattr(trace.ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    monkeypatch.setattr(trace, "verify_target_identity", lambda _: True)
    wait = Mock(return_value=(Path("local.json"), {"status": "captured"}))
    monkeypatch.setattr(trace, "wait_for_trace", wait)
    if busy:
        with pytest.raises(RuntimeError, match="pending"):
            trace.request_trace(target)
        kernel.SetEvent.assert_not_called()
        wait.assert_not_called()
    else:
        assert trace.request_trace(target)[1]["status"] == "captured"
        kernel.ResetEvent.assert_called_once_with(3)
        kernel.SetEvent.assert_called_once_with(2)
    kernel.ReleaseMutex.assert_called_once_with(1)
    assert {call.args[0] for call in kernel.CloseHandle.call_args_list} == {1, 2, 3}


def test_original_payload_is_not_modified(payload, target):
    original = copy.deepcopy(payload)
    trace.assess_trace(payload, target, 100)
    assert payload == original


@pytest.mark.parametrize("version", trace.TRACE_VERSIONS)
def test_saved_reviewed_versions_remain_readable(payload, target, version):
    payload["extension_version"] = version
    assert trace.assess_trace(payload, target, 100)["status"] == "captured"


def test_live_request_rejects_other_reviewed_version(payload, target):
    payload["extension_version"] = "1.6.12"
    with pytest.raises(ValueError, match="extension_version"):
        trace.assess_trace(payload, target, 100, expected_version="1.6.13")


@pytest.mark.parametrize("version", [None, True, [], "1.6.14"])
def test_unknown_trace_version_remains_closed(payload, target, version):
    payload["extension_version"] = version
    with pytest.raises(ValueError, match="extension_version"):
        trace.assess_trace(payload, target, 100)


def test_material_evidence_does_not_promote_capture_to_replay_approval(payload, target):
    payload["draws"][0]["quad_support"] = {
        "material_gate": "fixed_function_material_candidate",
        "replay_eligible": False,
        "arb_enable_binding": [0, 71, 0, 72],
    }
    payload["draws"][0]["textures"][0]["env_color"] = [None] * 4
    result = trace.assess_trace(payload, target, 100)
    assert result["status"] == "captured"
    assert "replay_eligible" not in result
    assert payload["draws"][0]["quad_support"]["replay_eligible"] is False
