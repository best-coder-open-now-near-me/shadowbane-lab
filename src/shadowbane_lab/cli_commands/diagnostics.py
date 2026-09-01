"""Capture-once diagnostic session, analysis, and comparison commands."""

from __future__ import annotations

import json
from argparse import Namespace
from math import isfinite
from pathlib import Path

from shadowbane_lab.diagnostics import (
    DiagnosticError,
    DiagnosticProfile,
    DiagnosticRequest,
    FileCaptureMode,
    FileChannel,
    TriggerOperator,
    TriggerRule,
    analyze_diagnostic_capture,
    compare_diagnostic_captures,
    run_diagnostic_capture,
)
from shadowbane_lab.evidence import (
    ArtifactKind,
    ArtifactStore,
    EvidenceError,
    ManifestTerminalState,
    load_manifest,
)
from shadowbane_lab.integrity import create_only_json

from .common import _error


def handle(arguments: Namespace) -> int:
    as_json = bool(getattr(arguments, "json", False))
    try:
        if arguments.diagnose_command == "capture":
            return _capture(arguments, as_json=as_json)
        if arguments.diagnose_command == "analyze":
            store = ArtifactStore(arguments.store)
            report = analyze_diagnostic_capture(
                store,
                load_manifest(arguments.manifest),
            )
            _save_optional(arguments.output, report)
            return _report_result(
                report,
                identifier="report_id",
                as_json=as_json,
                output=arguments.output,
            )
        if arguments.diagnose_command == "compare":
            report = compare_diagnostic_captures(
                ArtifactStore(arguments.baseline_store),
                load_manifest(arguments.baseline_manifest),
                ArtifactStore(arguments.candidate_store),
                load_manifest(arguments.candidate_manifest),
            )
            _save_optional(arguments.output, report)
            return _report_result(
                report,
                identifier="comparison_id",
                as_json=as_json,
                output=arguments.output,
            )
    except (DiagnosticError, EvidenceError, OSError, TypeError, ValueError) as exc:
        return _error(str(exc), as_json=as_json)
    return _error("unknown diagnose command", as_json=as_json)


def _capture(arguments: Namespace, *, as_json: bool) -> int:
    profile = DiagnosticProfile(arguments.profile)
    trigger_rules = tuple(_trigger_rule(value) for value in arguments.trigger)
    if (
        profile is DiagnosticProfile.TRIGGERED
        and not trigger_rules
        and arguments.manual_trigger_file is None
    ):
        trigger_rules = (
            TriggerRule(
                "process_handle_count",
                TriggerOperator.GE,
                512.0,
                consecutive_samples=2,
                compare_to_baseline=True,
            ),
            TriggerRule(
                "process_private_bytes",
                TriggerOperator.GE,
                float(256 * 1024 * 1024),
                consecutive_samples=2,
                compare_to_baseline=True,
            ),
        )
    initial_tail_bytes = _mib(arguments.initial_log_mib, "initial-log-mib")
    maximum_bytes = _mib(arguments.max_channel_mib, "max-channel-mib")
    channels = _file_channels(
        arguments,
        initial_tail_bytes=initial_tail_bytes,
        maximum_bytes=maximum_bytes,
    )
    result = run_diagnostic_capture(
        DiagnosticRequest(
            output_directory=arguments.output_directory,
            process_id=arguments.pid,
            profile=profile,
            duration_seconds=arguments.duration,
            sample_interval_seconds=arguments.interval,
            pre_trigger_seconds=arguments.pre_trigger,
            post_trigger_seconds=arguments.post_trigger,
            client_executable=arguments.client_executable,
            client_directory=arguments.client_directory,
            reference_executable=arguments.reference_executable,
            alignment_profile_directory=arguments.alignment_profile_directory,
            repository_directory=arguments.repository,
            capture_graphics_present=(
                arguments.graphics_present
                or arguments.graphics_runtime_status is not None
            ),
            graphics_runtime_status=arguments.graphics_runtime_status,
            capture_native_position=arguments.native_position,
            capture_camera_state=arguments.camera_state,
            file_channels=channels,
            trigger_rules=trigger_rules,
            manual_trigger_file=arguments.manual_trigger_file,
            screenshot_region=_screenshot_region(arguments.screenshot_region),
            screenshot_interval_seconds=arguments.screenshot_interval,
        )
    )
    payload: dict[str, object] = {
        "ok": result.manifest.terminal_state is ManifestTerminalState.COMPLETE,
        "run_id": result.run_id,
        "terminal_state": result.manifest.terminal_state.value,
        "manifest_id": result.manifest.manifest_id,
        "manifest": str(result.manifest_path),
        "store": str(result.store.root),
        "completed_channels": list(result.manifest.completed_channels),
        "omissions": list(result.manifest.omissions),
        "summary": result.summary,
    }
    if as_json:
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
    else:
        for name in (
            "run_id",
            "terminal_state",
            "manifest_id",
            "manifest",
            "store",
        ):
            print(f"{name}: {payload[name]}")
        if result.manifest.omissions:
            print("omissions:")
            for omission in result.manifest.omissions:
                print(f"  - {omission}")
    return 0 if payload["ok"] else 1


def _file_channels(
    arguments: Namespace,
    *,
    initial_tail_bytes: int,
    maximum_bytes: int,
) -> tuple[FileChannel, ...]:
    channels: list[FileChannel] = []
    for index, path in enumerate(arguments.log, start=1):
        channels.append(
            _channel(
                f"client-log-{index:03d}",
                path,
                FileCaptureMode.TAIL,
                ArtifactKind.CLIENT_LOG,
                "text/plain",
                initial_tail_bytes,
                maximum_bytes,
            )
        )
    convenience = (
        (
            "extension-events",
            arguments.extension_events,
            FileCaptureMode.TAIL,
            ArtifactKind.NATIVE_EVENT_STREAM,
            "application/x-ndjson",
        ),
        (
            "network-summary",
            arguments.network_summary,
            FileCaptureMode.SNAPSHOT,
            ArtifactKind.PACKET_SUMMARY,
            "application/json",
        ),
        (
            "packet-capture",
            arguments.packet_capture,
            FileCaptureMode.SNAPSHOT,
            ArtifactKind.PACKET_CAPTURE,
            "application/vnd.tcpdump.pcap",
        ),
        (
            "etw-trace",
            arguments.etw_trace,
            FileCaptureMode.SNAPSHOT,
            ArtifactKind.ETW_TRACE,
            "application/vnd.microsoft.etw",
        ),
        (
            "process-dump",
            arguments.process_dump,
            FileCaptureMode.SNAPSHOT,
            ArtifactKind.PROCESS_DUMP,
            "application/vnd.microsoft.minidump",
        ),
    )
    for channel_id, path, mode, kind, media_type in convenience:
        if path is not None:
            channels.append(
                _channel(
                    channel_id,
                    path,
                    mode,
                    kind,
                    media_type,
                    initial_tail_bytes,
                    maximum_bytes,
                )
            )
    for index, path in enumerate(arguments.snapshot, start=1):
        channels.append(
            _channel(
                f"runtime-snapshot-{index:03d}",
                path,
                FileCaptureMode.SNAPSHOT,
                ArtifactKind.RUNTIME_SNAPSHOT,
                "application/octet-stream",
                initial_tail_bytes,
                maximum_bytes,
            )
        )
    channels.extend(
        _parse_channel_file(
            value,
            initial_tail_bytes=initial_tail_bytes,
            maximum_bytes=maximum_bytes,
        )
        for value in arguments.channel_file
    )
    return tuple(sorted(channels, key=lambda item: item.channel_id))


def _channel(
    channel_id: str,
    path: Path,
    mode: FileCaptureMode,
    kind: ArtifactKind,
    media_type: str,
    initial_tail_bytes: int,
    maximum_bytes: int,
) -> FileChannel:
    return FileChannel(
        channel_id,
        path,
        mode,
        kind,
        media_type,
        initial_tail_bytes=initial_tail_bytes,
        maximum_bytes=maximum_bytes,
    )


def _parse_channel_file(
    value: str,
    *,
    initial_tail_bytes: int,
    maximum_bytes: int,
) -> FileChannel:
    parts = value.split("=", 4)
    if len(parts) != 5:
        raise ValueError(
            "channel-file must use CHANNEL=KIND=MODE=MEDIA=PATH"
        )
    channel_id, kind, mode, media_type, path = parts
    return _channel(
        channel_id,
        Path(path),
        FileCaptureMode(mode),
        ArtifactKind(kind),
        media_type,
        initial_tail_bytes,
        maximum_bytes,
    )


def _trigger_rule(value: str) -> TriggerRule:
    parts = value.split(":")
    if not 3 <= len(parts) <= 5:
        raise ValueError(
            "trigger must use METRIC:OP:THRESHOLD[:COUNT[:delta]]"
        )
    metric, operator, threshold = parts[:3]
    count = 1 if len(parts) < 4 else int(parts[3])
    compare_to_baseline = False
    if len(parts) == 5:
        if parts[4] != "delta":
            raise ValueError("trigger comparison mode must be delta")
        compare_to_baseline = True
    return TriggerRule(
        metric,
        TriggerOperator(operator),
        float(threshold),
        consecutive_samples=count,
        compare_to_baseline=compare_to_baseline,
    )


def _screenshot_region(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError("screenshot-region must use LEFT,TOP,WIDTH,HEIGHT")
    return tuple(int(item) for item in parts)  # type: ignore[return-value]


def _mib(value: float, name: str) -> int:
    if not isfinite(value) or value < 0 or value > 16_384:
        raise ValueError(f"{name} must be finite and in 0-16384")
    return int(value * 1024 * 1024)


def _save_optional(path: Path | None, payload: dict[str, object]) -> None:
    if path is not None:
        create_only_json(path, payload, make_parents=True)


def _report_result(
    report: dict[str, object],
    *,
    identifier: str,
    as_json: bool,
    output: Path | None,
) -> int:
    if as_json:
        print(json.dumps(report, allow_nan=False, sort_keys=True))
    else:
        print(f"{identifier}: {report[identifier]}")
        if output is not None:
            print(f"output: {output}")
        if "sample_count" in report:
            print(f"sample_count: {report['sample_count']}")
        if "review_required" in report:
            print(f"review_required: {report['review_required']}")
    return 0


__all__ = ["handle"]
