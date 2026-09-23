"""Concrete runtime scenario for exact manager, worker, and extension health."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from shadowbane_lab.client_extension import open_windows_extension_event_channel_reader

from .model import ScenarioResult
from .process_metrics import inspect_windows_process_metrics

_MAX_STATUS_BYTES = 4 * 1024 * 1024


def main() -> int:
    result_path_text = os.environ.get("SHADOWBANE_RUNTIME_RESULT_PATH")
    client_id = os.environ.get("SHADOWBANE_RUNTIME_CLIENT_ID")
    manager_url = os.environ.get("SHADOWBANE_MANAGER_URL")
    manager_token = os.environ.get("SHADOWBANE_MANAGER_TOKEN")
    if not result_path_text:
        print("SHADOWBANE_RUNTIME_RESULT_PATH is required", file=sys.stderr)
        return 2
    result_path = Path(result_path_text).resolve(strict=False)
    started = time.perf_counter_ns()
    try:
        if not client_id:
            raise ValueError("SHADOWBANE_RUNTIME_CLIENT_ID is required")
        if not manager_url or not manager_token:
            raise ValueError("SHADOWBANE_MANAGER_URL and SHADOWBANE_MANAGER_TOKEN are required")
        status = _read_manager_status(manager_url, manager_token)
        latency_ms = max(0.0, (time.perf_counter_ns() - started) / 1_000_000.0)
        process_id, process_creation = _target_process_identity(status, client_id)
        process_metrics = inspect_windows_process_metrics(process_id)
        event_channel = open_windows_extension_event_channel_reader(
            process_id,
            process_creation,
        ).snapshot()
        result = build_manager_health_result(
            status,
            client_id,
            latency_ms=latency_ms,
            process_metrics=process_metrics,
            event_channel=event_channel,
        )
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        latency_ms = max(0.0, (time.perf_counter_ns() - started) / 1_000_000.0)
        result = ScenarioResult(
            scenario_id=os.environ.get("SHADOWBANE_RUNTIME_SCENARIO_ID", "manager-health"),
            passed=False,
            terminal_reason=f"probe_error_{type(exc).__name__}",
            semantic={"probe": "failed", "error_type": type(exc).__name__},
            metrics=(
                ("manager_status_latency_ms", latency_ms),
                ("process_handle_count", 0.0),
                ("process_private_bytes", 0.0),
                ("process_working_set_bytes", 0.0),
                ("worker_heartbeat_age_seconds", 0.0),
            ),
            counters=(
                ("active_operation_count", 0),
                ("candidate_count", 0),
                ("event_dropped_count", 0),
                ("event_pending_count", 0),
                ("event_producer_error_count", 0),
                ("queued_operation_count", 0),
                ("rejected_window_count", 0),
                ("worker_issue_count", 0),
            ),
        )
    _write_result(result_path, result)
    return 0 if result.passed else 1


def build_manager_health_result(
    status: object,
    client_id: str,
    *,
    latency_ms: float,
    process_metrics: Mapping[str, float] | None = None,
    event_channel: object | None = None,
) -> ScenarioResult:
    root = _object(status, "manager status")
    if root.get("ok") is not True:
        raise ValueError("manager status is not successful")
    slots = root.get("slots")
    if not isinstance(slots, list):
        raise ValueError("manager status slots must be an array")
    matches = [
        _object(slot, "manager slot")
        for slot in slots
        if isinstance(slot, dict) and slot.get("client_id") == client_id
    ]
    if len(matches) != 1:
        raise ValueError("manager status must contain the exact target client once")
    slot = matches[0]
    worker = _object(slot.get("worker"), "worker status")
    extension = _object(slot.get("extension"), "extension status")
    operation = _object(slot.get("operation"), "operation status")
    binding = slot.get("binding")
    issues = worker.get("issues")
    candidates = slot.get("candidates")
    rejected = slot.get("rejected_windows")
    if not isinstance(issues, list):
        raise ValueError("worker issues must be an array")
    if not isinstance(candidates, list) or not isinstance(rejected, list):
        raise ValueError("manager candidates and rejected windows must be arrays")
    queued_count = _non_negative_integer(operation.get("queued_count"), "queued_count")
    heartbeat_age = worker.get("heartbeat_age_seconds")
    if (
        isinstance(heartbeat_age, bool)
        or not isinstance(heartbeat_age, (int, float))
        or heartbeat_age < 0
    ):
        heartbeat_age = 0.0
    active_operation_count = 0 if operation.get("active") is None else 1
    resource_metrics = {} if process_metrics is None else dict(process_metrics)
    expected_resource_metrics = {
        "process_handle_count",
        "process_private_bytes",
        "process_working_set_bytes",
    }
    if process_metrics is not None and set(resource_metrics) != expected_resource_metrics:
        raise ValueError("process metrics do not use the exact runtime contract")
    event_dropped_count = 0
    event_pending_count = 0
    event_producer_error_count = 0
    event_capability_flags = None
    if event_channel is not None:
        header = getattr(event_channel, "header", None)
        if header is None:
            raise ValueError("event channel snapshot is missing its header")
        event_dropped_count = _non_negative_integer(
            getattr(header, "dropped_event_count", None),
            "dropped_event_count",
        )
        event_pending_count = _non_negative_integer(
            getattr(header, "pending_count", None),
            "pending_count",
        )
        event_producer_error_count = _non_negative_integer(
            getattr(header, "producer_error", None),
            "producer_error",
        )
        event_capability_flags = _non_negative_integer(
            getattr(header, "capability_flags", None),
            "capability_flags",
        )
    passed = all(
        (
            slot.get("state") == "attached",
            slot.get("dispatch_enabled") is True,
            binding is not None,
            slot.get("failure_detail") is None,
            worker.get("state") == "healthy",
            worker.get("dispatch_allowed") is True,
            worker.get("active_worker_count") == 1,
            not issues,
            extension.get("state") == "initialized",
            extension.get("ready") is True,
            not candidates,
            not rejected,
            queued_count == 0,
            active_operation_count == 0,
            event_dropped_count == 0,
            event_pending_count == 0,
            event_producer_error_count == 0,
        )
    )
    scenario_id = os.environ.get("SHADOWBANE_RUNTIME_SCENARIO_ID", "manager-health")
    return ScenarioResult(
        scenario_id=scenario_id,
        passed=passed,
        terminal_reason="healthy" if passed else "manager_health_invariant_failed",
        semantic={
            "manager": {
                "binding_present": binding is not None,
                "dispatch_enabled": slot.get("dispatch_enabled"),
                "slot_state": slot.get("state"),
            },
            "worker": {
                "active_worker_count": worker.get("active_worker_count"),
                "dispatch_allowed": worker.get("dispatch_allowed"),
                "state": worker.get("state"),
            },
            "extension": {
                "abi_version": extension.get("abi_version"),
                "ready": extension.get("ready"),
                "state": extension.get("state"),
            },
            "event_channel": {
                "capability_flags": event_capability_flags,
                "readable": event_channel is not None,
            },
        },
        metrics=(
            ("manager_status_latency_ms", float(latency_ms)),
            *tuple(sorted(resource_metrics.items())),
            ("worker_heartbeat_age_seconds", float(heartbeat_age)),
        ),
        counters=(
            ("active_operation_count", active_operation_count),
            ("candidate_count", len(candidates)),
            ("event_dropped_count", event_dropped_count),
            ("event_pending_count", event_pending_count),
            ("event_producer_error_count", event_producer_error_count),
            ("queued_operation_count", queued_count),
            ("rejected_window_count", len(rejected)),
            ("worker_issue_count", len(issues)),
        ),
    )


def _target_process_identity(status: object, client_id: str) -> tuple[int, int]:
    root = _object(status, "manager status")
    slots = root.get("slots")
    if not isinstance(slots, list):
        raise ValueError("manager status slots must be an array")
    matches = [
        _object(slot, "manager slot")
        for slot in slots
        if isinstance(slot, dict) and slot.get("client_id") == client_id
    ]
    if len(matches) != 1:
        raise ValueError("manager status must contain the exact target client once")
    binding = _object(matches[0].get("binding"), "manager binding")
    process_id = binding.get("process_id")
    process_creation = binding.get("process_started_at_100ns")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0:
        raise ValueError("manager binding process_id must be positive")
    if (
        isinstance(process_creation, bool)
        or not isinstance(process_creation, int)
        or process_creation <= 0
    ):
        raise ValueError("manager binding process creation time must be positive")
    return process_id, process_creation


def _read_manager_status(manager_url: str, token: str) -> object:
    parsed = urlsplit(manager_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("manager URL must be a plain loopback HTTP URL")
    base = manager_url.rstrip("/")
    request = urllib.request.Request(
        f"{base}/api/v1/status",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=5.0) as response:
        content_length = response.headers.get("Content-Length")
        if content_length is not None and int(content_length) > _MAX_STATUS_BYTES:
            raise ValueError("manager status response is too large")
        source = response.read(_MAX_STATUS_BYTES + 1)
    if len(source) > _MAX_STATUS_BYTES:
        raise ValueError("manager status response is too large")
    try:
        return json.loads(source, object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manager status is not valid UTF-8 JSON") from exc


def _write_result(path: Path, result: ScenarioResult) -> None:
    if path.exists():
        raise RuntimeError(f"runtime result already exists: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    encoded = (
        json.dumps(result.as_dict(), allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True)
        + "\n"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _object(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be an object")
    return value


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manager status field {key!r}")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
