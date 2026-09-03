"""Bounded, OS-only vanilla Shadowbane diagnostic capture."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .frame_surface import WindowsSurfaceFrameProbe
from .model import CAPTURE_SCHEMA_VERSION, ProcessIdentity, ProcessSample
from .package import verify_package
from .residue import build_vanilla_preflight
from .windows import (
    WindowsDwmFrameProbe,
    WindowsModuleProbe,
    WindowsNetworkProbe,
    WindowsProcessProbe,
    WindowsWindowInputProbe,
    select_primary_window,
)

_MARKER_LABEL = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_MAX_CAPTURE_SECONDS = 3600.0
_MAX_MARKER_NOTE_CHARACTERS = 256


class CaptureError(RuntimeError):
    """Raised when a capture cannot preserve the vanilla evidence contract."""


@dataclass(frozen=True, slots=True)
class CaptureConfig:
    package_root: Path
    output_root: Path
    process_id: int
    client_executable: Path
    duration_seconds: float = 600.0
    interval_seconds: float = 0.125
    network_interval_seconds: float = 1.0
    runtime_status_directory: Path | None = None

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or self.process_id <= 0:
            raise ValueError("process_id must be positive")
        if not (1.0 <= self.duration_seconds <= _MAX_CAPTURE_SECONDS):
            raise ValueError("duration_seconds must be from 1 through 3600")
        if not (0.1 <= self.interval_seconds <= 0.2):
            raise ValueError("interval_seconds must be from 0.1 through 0.2 (5-10 Hz)")
        if self.network_interval_seconds < self.interval_seconds:
            raise ValueError("network_interval_seconds must not be below the sample interval")


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_json_create_new(path: Path, value: object) -> None:
    source = (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        offset = 0
        while offset < len(source):
            offset += os.write(descriptor, source[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _same_windows_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def assert_required_output_root(
    actual: Path,
    required: str,
    *,
    package_root: Path | None = None,
) -> None:
    package_prefix = "{PACKAGE_ROOT}\\"
    if required.startswith(package_prefix):
        if package_root is None:
            raise CaptureError("portable output policy requires the verified package root")
        relative = Path(required[len(package_prefix) :])
        if relative.is_absolute() or ".." in relative.parts:
            raise CaptureError("portable output policy contains an unsafe relative path")
        expected = package_root.resolve(strict=True) / relative
        if not _same_windows_path(actual, expected):
            raise CaptureError(
                f"output root must be exactly the portable evidence path: {expected}"
            )
        return
    if not required.startswith("\\\\VBOXSVR\\codexdiag\\"):
        raise CaptureError("package required_output_root has an unsupported boundary")
    if not _same_windows_path(actual, required):
        raise CaptureError(f"output root must be exactly the packaged codexdiag path: {required}")


def calculate_cpu_rates(
    previous: ProcessSample | None,
    current: ProcessSample,
    elapsed_seconds: float,
    logical_processor_count: int,
) -> dict[str, float | None]:
    if previous is None or elapsed_seconds <= 0:
        return {
            "cpu_percent_one_core": None,
            "cpu_percent_system_capacity": None,
        }
    previous_seconds = float(previous.metrics["cpu_kernel_seconds"]) + float(
        previous.metrics["cpu_user_seconds"]
    )
    current_seconds = float(current.metrics["cpu_kernel_seconds"]) + float(
        current.metrics["cpu_user_seconds"]
    )
    cpu_delta = max(0.0, current_seconds - previous_seconds)
    one_core = 100.0 * cpu_delta / elapsed_seconds
    return {
        "cpu_percent_one_core": one_core,
        "cpu_percent_system_capacity": one_core / max(1, logical_processor_count),
    }


def _assert_exact_identity(expected: ProcessIdentity, actual: ProcessIdentity) -> None:
    if expected.exact_key != actual.exact_key:
        raise CaptureError("target process lifetime changed during capture")
    if not _same_windows_path(expected.executable_path, actual.executable_path):
        raise CaptureError("target process executable path changed during capture")


def _channel_sample(
    channel: str,
    failures: dict[str, list[str]],
    function: Any,
    *arguments: object,
) -> object | None:
    try:
        return function(*arguments)
    except Exception as exc:
        messages = failures.setdefault(channel, [])
        message = f"{type(exc).__name__}: {exc}"
        if not messages or messages[-1] != message:
            messages.append(message)
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_inventory(run_directory: Path) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    for candidate in sorted(run_directory.rglob("*"), key=lambda value: value.as_posix()):
        if not candidate.is_file() or candidate.name == "capture-complete.json":
            continue
        inventory.append(
            {
                "path": candidate.relative_to(run_directory).as_posix(),
                "length": candidate.stat().st_size,
                "sha256": _sha256(candidate),
            }
        )
    return inventory


def _close_and_read_markers(run_directory: Path) -> list[dict[str, object]]:
    marker_directory = run_directory / "markers"
    _write_json_create_new(
        run_directory / "markers-closed.json",
        {"schema_version": 1, "closed_at_utc": utc_timestamp()},
    )
    deadline = time.monotonic() + 2.0
    while any(marker_directory.glob("*.writing")):
        if time.monotonic() >= deadline:
            raise CaptureError("marker writer did not finish before evidence sealing")
        time.sleep(0.01)
    markers: list[dict[str, object]] = []
    for path in sorted(marker_directory.glob("*.json"), key=lambda item: item.name):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CaptureError(f"marker is not valid UTF-8 JSON: {path.name}") from exc
        if not isinstance(value, dict):
            raise CaptureError(f"marker must be a JSON object: {path.name}")
        markers.append(value)
    return markers


def _notify_progress(
    callback: Callable[[dict[str, object]], None] | None,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        return


def run_capture(
    config: CaptureConfig,
    *,
    stop_requested: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> Path:
    """Capture one exact process without importing or reading extension telemetry."""

    package = verify_package(config.package_root)
    assert_required_output_root(
        config.output_root,
        str(package["required_output_root"]),
        package_root=config.package_root,
    )
    config.output_root.mkdir(parents=True, exist_ok=True)

    process_probe = WindowsProcessProbe()
    collector_identity = process_probe.sample(os.getpid()).identity
    module_probe = WindowsModuleProbe()
    window_probe = WindowsWindowInputProbe()
    frame_probe = WindowsDwmFrameProbe()
    surface_probe = WindowsSurfaceFrameProbe()
    network_probe = WindowsNetworkProbe()
    discovery = process_probe.sample(config.process_id)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"shadowbane-vanilla-{timestamp}-{config.process_id}-{uuid.uuid4().hex[:8]}"
    run_directory = config.output_root / run_id
    run_directory.mkdir()
    marker_directory = run_directory / "markers"
    marker_directory.mkdir()

    modules = module_probe.list_modules(config.process_id)
    runtime_status_directory = config.runtime_status_directory
    if runtime_status_directory is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        runtime_status_directory = (
            Path(local_app_data) / "ShadowbaneLab" / "client-extension"
            if local_app_data
            else None
        )
    preflight = build_vanilla_preflight(
        requested_executable=config.client_executable,
        identity=discovery.identity,
        allowed_executable_sha256=package["allowed_executable_sha256"],
        modules=modules,
        runtime_status_directory=runtime_status_directory,
    )
    preflight.update(
        {
            "captured_at_utc": utc_timestamp(),
            "package_id": package["package_id"],
            "package_version": package["package_version"],
            "package_source_revision": package["source_revision"],
        }
    )
    _write_json_create_new(run_directory / "preflight.json", preflight)
    if not preflight["accepted"]:
        completion = {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "run_id": run_id,
            "terminal_state": "preflight_rejected",
            "completed_at_utc": utc_timestamp(),
            "failures": preflight["failures"],
            "artifacts": _artifact_inventory(run_directory),
        }
        _write_json_create_new(run_directory / "capture-complete.json", completion)
        raise CaptureError(
            "vanilla preflight rejected the target: " + "; ".join(preflight["failures"])
        )

    initial = process_probe.sample(config.process_id)
    _assert_exact_identity(discovery.identity, initial.identity)
    started_at_utc = utc_timestamp()
    started_ns = time.perf_counter_ns()
    deadline_ns = started_ns + int(config.duration_seconds * 1_000_000_000)
    _write_json_create_new(
        run_directory / "capture-active.json",
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "active",
            "started_at_utc": started_at_utc,
            "collector_process_id": os.getpid(),
            "collector_process_creation_filetime_utc": (
                collector_identity.process_creation_filetime_utc
            ),
            "target": initial.identity.as_dict(),
            "duration_seconds": config.duration_seconds,
            "interval_seconds": config.interval_seconds,
            "marker_directory": str(marker_directory),
        },
    )
    _notify_progress(
        progress_callback,
        {
            "event": "started",
            "run_id": run_id,
            "duration_seconds": config.duration_seconds,
        },
    )

    samples: list[dict[str, object]] = []
    network_samples: list[dict[str, object]] = []
    channel_failures: dict[str, list[str]] = {}
    terminal_state = "completed"
    terminal_failure: str | None = None
    previous_process: ProcessSample | None = None
    previous_sample_ns: int | None = None
    previous_surface_hash: str | None = None
    dwm_probe_enabled = True
    next_network_ns = started_ns
    logical_processors = os.cpu_count() or 1
    sample_index = 0
    progress_stride = max(1, round(1.0 / config.interval_seconds))
    try:
        while True:
            captured_ns = time.perf_counter_ns()
            if sample_index > 0 and stop_requested is not None and stop_requested():
                terminal_state = "operator_stopped"
                break

            if captured_ns > deadline_ns and sample_index > 0:
                break
            captured_at_utc = utc_timestamp()
            process_sample = process_probe.sample(config.process_id)
            _assert_exact_identity(initial.identity, process_sample.identity)
            elapsed_seconds = (
                (captured_ns - previous_sample_ns) / 1_000_000_000
                if previous_sample_ns is not None
                else 0.0
            )
            process_metrics = dict(process_sample.metrics)
            process_metrics.update(
                calculate_cpu_rates(
                    previous_process,
                    process_sample,
                    elapsed_seconds,
                    logical_processors,
                )
            )
            window_input = _channel_sample(
                "window-input",
                channel_failures,
                window_probe.sample,
                config.process_id,
            )
            primary_window = (
                select_primary_window(window_input)
                if isinstance(window_input, dict)
                else 0
            )
            dwm_frame = (
                _channel_sample(
                    "dwm-frame-proxy",
                    channel_failures,
                    frame_probe.sample,
                    primary_window,
                )
                if primary_window and dwm_probe_enabled
                else None
            )
            if primary_window and dwm_probe_enabled and dwm_frame is None:
                dwm_probe_enabled = False
            surface_frame = (
                _channel_sample(
                    "window-surface-frame-proxy",
                    channel_failures,
                    surface_probe.sample,
                    primary_window,
                )
                if primary_window
                else None
            )
            if isinstance(surface_frame, dict):
                surface_hash = str(surface_frame["surface_sha256"])
                surface_frame["changed_since_previous_sample"] = (
                    None
                    if previous_surface_hash is None
                    else surface_hash != previous_surface_hash
                )
                previous_surface_hash = surface_hash
            samples.append(
                {
                    "sample_index": sample_index,
                    "captured_at_utc": captured_at_utc,
                    "elapsed_ns": captured_ns - started_ns,
                    "process": process_metrics,
                    "window_input": window_input,
                    "dwm_frame_proxy": dwm_frame,
                    "window_surface_frame_proxy": surface_frame,
                }
            )
            if captured_ns >= next_network_ns:
                network = _channel_sample(
                    "network",
                    channel_failures,
                    network_probe.sample,
                    config.process_id,
                )
                network_samples.append(
                    {
                        "captured_at_utc": captured_at_utc,
                        "elapsed_ns": captured_ns - started_ns,
                        "network": network,
                    }
                )
                next_network_ns = captured_ns + int(
                    config.network_interval_seconds * 1_000_000_000
                )
            previous_process = process_sample
            previous_sample_ns = captured_ns
            sample_index += 1
            next_sample_ns = started_ns + int(
                sample_index * config.interval_seconds * 1_000_000_000
            )
            if sample_index % progress_stride == 0:
                _notify_progress(
                    progress_callback,
                    {
                        "event": "progress",
                        "elapsed_seconds": (captured_ns - started_ns) / 1_000_000_000,
                        "sample_count": sample_index,
                    },
                )
            remaining = next_sample_ns - time.perf_counter_ns()
            if remaining > 0:
                time.sleep(remaining / 1_000_000_000)
    except KeyboardInterrupt:
        terminal_state = "operator_interrupted"
    except ProcessLookupError as exc:
        terminal_state = "target_exited"
        terminal_failure = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        terminal_state = "collector_failed"
        terminal_failure = f"{type(exc).__name__}: {exc}"

    markers = _close_and_read_markers(run_directory)
    completed_at_utc = utc_timestamp()
    evidence_path = run_directory / "capture-evidence.json"
    _write_json_create_new(
        evidence_path,
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "run_id": run_id,
            "capture_contract": {
                "target": initial.identity.as_dict(),
                "executable_sha256": preflight["executable_sha256"],
                "extension_telemetry_loaded": False,
                "process_sample_hz": 1.0 / config.interval_seconds,
                "network_sample_hz": 1.0 / config.network_interval_seconds,
                "frame_evidence_scope": (
                    "16x9 visible-client surface hashes plus optional DWM compositor "
                    "counters; no pixels retained and not exact application presents"
                ),
                "input_evidence_scope": (
                    "last-input age, cursor position, and foreground ownership; no key or "
                    "message content"
                ),
                "network_evidence_scope": "exact-process endpoints only; no packet payloads",
            },
            "started_at_utc": started_at_utc,
            "completed_at_utc": completed_at_utc,
            "terminal_state": terminal_state,
            "terminal_failure": terminal_failure,
            "sample_count": len(samples),
            "samples": samples,
            "network_sample_count": len(network_samples),
            "network_samples": network_samples,
            "markers": markers,
            "channel_failures": channel_failures,
        },
    )
    manifest_path = run_directory / "evidence-manifest.json"
    _write_json_create_new(
        manifest_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "sealed_at_utc": utc_timestamp(),
            "artifacts": _artifact_inventory(run_directory),
        },
    )
    _write_json_create_new(
        run_directory / "capture-complete.json",
        {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "run_id": run_id,
            "terminal_state": terminal_state,
            "completed_at_utc": completed_at_utc,
            "sample_count": len(samples),
            "marker_count": len(markers),
            "channel_failures": channel_failures,
            "evidence_manifest_sha256": _sha256(manifest_path),
        },
    )
    _notify_progress(
        progress_callback,
        {
            "event": "completed",
            "terminal_state": terminal_state,
            "sample_count": len(samples),
            "marker_count": len(markers),
            "run_directory": str(run_directory),
        },
    )
    if terminal_state == "collector_failed":
        raise CaptureError(terminal_failure or "collector failed")
    return run_directory


def mark_active_capture(
    output_root: Path,
    label: str,
    note: str = "",
    *,
    process_probe: Any | None = None,
) -> Path:
    """Append one create-only observation marker to the sole active vanilla capture."""

    canonical_label = label.strip().casefold().replace(" ", "_")
    if not _MARKER_LABEL.fullmatch(canonical_label):
        raise CaptureError("marker label must use 1-64 lowercase letters, numbers, '_' or '-'")
    if "\0" in note or len(note) > _MAX_MARKER_NOTE_CHARACTERS:
        raise CaptureError("marker note is invalid or exceeds 256 characters")
    active: list[tuple[Path, dict[str, object]]] = []
    marker_process_probe = process_probe or WindowsProcessProbe()
    if output_root.is_dir():
        for path in output_root.glob("shadowbane-vanilla-*/capture-active.json"):
            run_directory = path.parent
            if (run_directory / "markers-closed.json").exists():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or value.get("status") != "active":
                continue
            try:
                collector_process_id = int(value["collector_process_id"])
                collector_creation = int(
                    value["collector_process_creation_filetime_utc"]
                )
                live_collector = marker_process_probe.sample(collector_process_id).identity
            except (KeyError, TypeError, ValueError, OSError, ProcessLookupError):
                continue
            if live_collector.exact_key != (
                collector_process_id,
                collector_creation,
            ):
                continue
            active.append((run_directory, value))
    if len(active) != 1:
        raise CaptureError(f"expected exactly one active vanilla capture, found {len(active)}")
    run_directory, state = active[0]
    marker_directory = run_directory / "markers"
    marker_id = f"{time.time_ns()}-{uuid.uuid4().hex}"
    staging = marker_directory / f"{marker_id}.writing"
    final = marker_directory / f"{marker_id}.json"
    if (run_directory / "markers-closed.json").exists():
        raise CaptureError("the capture stopped accepting markers")
    marker = {
        "schema_version": 1,
        "run_id": state["run_id"],
        "marker_id": marker_id,
        "label": canonical_label,
        "note": note,
        "captured_at_utc": utc_timestamp(),
        "monotonic_ns": time.perf_counter_ns(),
    }
    _write_json_create_new(staging, marker)
    os.replace(staging, final)
    return final


__all__ = [
    "CaptureConfig",
    "CaptureError",
    "assert_required_output_root",
    "calculate_cpu_rates",
    "mark_active_capture",
    "run_capture",
]
