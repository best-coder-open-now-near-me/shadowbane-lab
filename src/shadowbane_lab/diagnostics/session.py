"""Capture-once diagnostic sessions with immutable evidence sealing."""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from shadowbane_lab.cases import (
    CaptureQuality,
    CaptureRecord,
    CaptureRecordKind,
    align_capture_records,
    producer_health,
)
from shadowbane_lab.client_alignment import compare_client_builds
from shadowbane_lab.evidence import (
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactStore,
    EvidenceManifest,
    ManifestTerminalState,
    save_contract,
)
from shadowbane_lab.fingerprints import FingerprintCaptureInputs, capture_fingerprint
from shadowbane_lab.integrity import canonical_json_bytes, canonical_timestamp

from .collectors import FileChunk, ScreenshotCapture, ScreenshotCollector, TailFileCollector
from .model import DiagnosticError, DiagnosticProfile, DiagnosticRequest, FileCaptureMode
from .process import ProcessIdentity, ProcessProbe, ProcessSample, WindowsProcessProbe

_PRODUCER_ID = "shadowbane-lab.diagnostics"
_PRODUCER_VERSION = "1"
_MAX_SCREENSHOT_BUFFER_BYTES = 256 * 1024 * 1024


class SessionClock(Protocol):
    def monotonic_ns(self) -> int: ...

    def utc_timestamp(self) -> str: ...

    def sleep(self, seconds: float) -> None: ...


class SystemSessionClock:
    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def utc_timestamp(self) -> str:
        return canonical_timestamp()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True, slots=True)
class DiagnosticCaptureResult:
    run_id: str
    output_directory: Path
    store: ArtifactStore
    manifest_path: Path
    manifest: EvidenceManifest
    summary: dict[str, object]


@dataclass(frozen=True, slots=True)
class _PendingRecord:
    channel_id: str
    monotonic_ns: int
    captured_at_utc: str
    kind: CaptureRecordKind
    payload: tuple[tuple[str, Any], ...] = ()
    correlation_id: str | None = None
    artifact_id: str | None = None
    quality: tuple[CaptureQuality, ...] = ()
    binary_key: tuple[object, ...] | None = None


def run_diagnostic_capture(
    request: DiagnosticRequest,
    *,
    process_probe: ProcessProbe | None = None,
    clock: SessionClock | None = None,
    screenshot_factory: Callable[
        [tuple[int, int, int, int], float], ScreenshotCollector
    ]
    | None = None,
) -> DiagnosticCaptureResult:
    """Capture one bounded session and seal every retained artifact in one manifest."""

    probe = process_probe or WindowsProcessProbe()
    session_clock = clock or SystemSessionClock()
    initial_sample = probe.sample(request.process_id)
    _validate_requested_executable(request.client_executable, initial_sample.identity)
    live_executable = Path(initial_sample.identity.executable_path)
    fingerprint = capture_fingerprint(
        FingerprintCaptureInputs(
            client_directory=request.client_directory,
            client_executable=live_executable,
            runtime_executable=live_executable,
            process_id=request.process_id,
            environment_id="local-diagnostic",
            scenario_id=f"diagnostic-{request.profile.value}",
            repository_directory=request.repository_directory,
        )
    )
    output = request.output_directory.resolve(strict=False)
    if output.exists() and any(output.iterdir()):
        raise DiagnosticError(f"diagnostic output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore.initialize(
        output / "store",
        store_id=f"diagnostics-{uuid.uuid4().hex}",
    )
    manifests = output / "manifests"
    manifests.mkdir()
    run_id = f"diag-{uuid.uuid4().hex}"
    manifest_path = manifests / f"{run_id}.manifest.json"
    clock_domain_id = f"session-{run_id}"
    descriptors: list[ArtifactDescriptor] = []
    pending: list[_PendingRecord] = []
    completed: set[str] = set()
    channel_failures: dict[str, str] = {}
    warnings: set[str] = set()
    fatal = False
    started_ns = session_clock.monotonic_ns()
    started_utc = session_clock.utc_timestamp()
    deadline_ns = started_ns + int(request.effective_duration_seconds * 1_000_000_000)

    identity_descriptor = _ingest_json(
        store,
        initial_sample.identity.as_dict(),
        kind=ArtifactKind.RUNTIME_SNAPSHOT,
        logical_name=f"{run_id}.process-identity.json",
        captured_at_utc=started_utc,
        metadata=(("channel_id", "process-identity"),),
    )
    descriptors.append(identity_descriptor)
    completed.add("process-identity")
    pending.append(
        _PendingRecord(
            channel_id="process-identity",
            monotonic_ns=started_ns,
            captured_at_utc=started_utc,
            kind=CaptureRecordKind.ARTIFACT_REFERENCE,
            artifact_id=identity_descriptor.artifact_id,
        )
    )
    fingerprint_descriptor = _ingest_json(
        store,
        fingerprint.as_dict(),
        kind=ArtifactKind.ENVIRONMENT_SNAPSHOT,
        logical_name=f"{run_id}.fingerprint.json",
        captured_at_utc=fingerprint.captured_at_utc,
        metadata=(("channel_id", "execution-fingerprint"),),
    )
    descriptors.append(fingerprint_descriptor)
    completed.add("execution-fingerprint")
    pending.append(
        _PendingRecord(
            channel_id="execution-fingerprint",
            monotonic_ns=started_ns,
            captured_at_utc=started_utc,
            kind=CaptureRecordKind.ARTIFACT_REFERENCE,
            artifact_id=fingerprint_descriptor.artifact_id,
        )
    )

    if request.reference_executable is not None:
        try:
            alignment = compare_client_builds(
                request.reference_executable,
                live_executable,
                profile_directory=request.alignment_profile_directory,
            )
            alignment_payload = alignment.as_dict()
            alignment_payload["diagnostic_interpretation"] = {
                "address_mapping_authority": (
                    "exact-build"
                    if alignment.exact_file_match
                    else "candidate-evidence-only"
                ),
                "automatic_compatibility_promotion": False,
                "unresolved_mapping_blocks_dependent_decoders": not alignment.exact_file_match,
            }
            descriptor = _ingest_json(
                store,
                alignment_payload,
                kind=ArtifactKind.BUILD_DIFF,
                logical_name=f"{run_id}.client-alignment.json",
                captured_at_utc=started_utc,
                metadata=(
                    ("channel_id", "client-alignment"),
                    ("recommendation", alignment.recommendation),
                ),
            )
            descriptors.append(descriptor)
            completed.add("client-alignment")
            pending.append(
                _PendingRecord(
                    channel_id="client-alignment",
                    monotonic_ns=started_ns,
                    captured_at_utc=started_utc,
                    kind=CaptureRecordKind.ARTIFACT_REFERENCE,
                    artifact_id=descriptor.artifact_id,
                )
            )
            if not alignment.exact_file_match:
                warnings.add(
                    "client alignment is heuristic candidate evidence and requires review"
                )
        except Exception as exc:
            channel_failures["client-alignment"] = f"{type(exc).__name__}: {exc}"

    tail_collectors = {
        channel.channel_id: TailFileCollector(channel)
        for channel in request.file_channels
        if channel.mode is FileCaptureMode.TAIL
    }
    tail_chunks: dict[str, list[FileChunk]] = {
        channel_id: [] for channel_id in tail_collectors
    }
    screenshot_collector: ScreenshotCollector | None = None
    screenshots: list[ScreenshotCapture] = []
    screenshot_bytes = 0
    if request.screenshot_region is not None:
        factory = screenshot_factory or (
            lambda region, interval: ScreenshotCollector(region, interval)
        )
        try:
            screenshot_collector = factory(
                request.screenshot_region,
                request.screenshot_interval_seconds,
            )
        except Exception as exc:
            channel_failures["screenshots"] = f"{type(exc).__name__}: {exc}"

    _capture_snapshot_channels(
        request,
        phase="start",
        store=store,
        descriptors=descriptors,
        completed=completed,
        failures=channel_failures,
        pending=pending,
        monotonic_ns=started_ns,
        captured_at_utc=started_utc,
    )
    pending.append(
        _PendingRecord(
            channel_id="capture-markers",
            monotonic_ns=started_ns,
            captured_at_utc=started_utc,
            kind=CaptureRecordKind.MARKER,
            payload=(("marker", "session-start"),),
            correlation_id="session-lifecycle",
        )
    )

    baseline = dict(initial_sample.metrics)
    trigger_counts = {index: 0 for index, _ in enumerate(request.trigger_rules)}
    trigger_ns: int | None = None
    trigger_reason: str | None = None
    sample_count = 0
    current_sample: ProcessSample | None = initial_sample
    stop_reason = "duration-complete"
    while True:
        now_ns = session_clock.monotonic_ns()
        now_utc = session_clock.utc_timestamp()
        if current_sample is None:
            try:
                current_sample = probe.sample(request.process_id)
            except Exception as exc:
                stop_reason = "process-sample-failed"
                warnings.add(f"process sampling stopped: {type(exc).__name__}: {exc}")
                break
        if current_sample.identity.exact_key != initial_sample.identity.exact_key:
            fatal = True
            stop_reason = "process-identity-changed"
            warnings.add("PID was reused or process creation identity changed during capture")
            break
        if _normalized_path(current_sample.identity.executable_path) != _normalized_path(
            initial_sample.identity.executable_path
        ):
            fatal = True
            stop_reason = "process-image-changed"
            warnings.add("process executable path changed during capture")
            break
        metrics = dict(current_sample.metrics)
        sample_count += 1
        pending.append(
            _PendingRecord(
                channel_id="process-metrics",
                monotonic_ns=now_ns,
                captured_at_utc=now_utc,
                kind=CaptureRecordKind.OBSERVATION,
                payload=tuple(
                    sorted(
                        {
                            **metrics,
                            "sample_index": sample_count,
                        }.items()
                    )
                ),
            )
        )
        completed.add("process-metrics")
        for channel_id, collector in tuple(tail_collectors.items()):
            try:
                for chunk in collector.poll(now_ns):
                    tail_chunks[channel_id].append(chunk)
                    key = _file_chunk_key(chunk)
                    quality = (
                        (CaptureQuality.DROPPED,)
                        if chunk.dropped_bytes
                        else (CaptureQuality.RECONSTRUCTED,)
                        if chunk.rotated_or_truncated
                        else ()
                    )
                    pending.append(
                        _PendingRecord(
                            channel_id=channel_id,
                            monotonic_ns=now_ns,
                            captured_at_utc=now_utc,
                            kind=CaptureRecordKind.EVENT,
                            payload=tuple(
                                sorted(
                                    {
                                        "captured_length": len(chunk.payload),
                                        "dropped_bytes": chunk.dropped_bytes,
                                        "initial_context": chunk.initial_context,
                                        "payload_sha256": hashlib.sha256(
                                            chunk.payload
                                        ).hexdigest(),
                                        "source_generation": chunk.source_generation,
                                        "source_offset": chunk.source_offset,
                                    }.items()
                                )
                            ),
                            quality=quality,
                            binary_key=key,
                        )
                    )
                    if chunk.dropped_bytes:
                        channel_failures[channel_id] = (
                            f"maximum capture size exceeded; dropped {chunk.dropped_bytes} bytes"
                        )
            except Exception as exc:
                channel_failures[channel_id] = f"{type(exc).__name__}: {exc}"
                del tail_collectors[channel_id]
        if screenshot_collector is not None:
            try:
                for capture in screenshot_collector.poll(now_ns):
                    screenshots.append(capture)
                    screenshot_bytes += len(capture.png_bytes)
                    pending.append(
                        _PendingRecord(
                            channel_id="screenshots",
                            monotonic_ns=capture.captured_monotonic_ns,
                            captured_at_utc=now_utc,
                            kind=CaptureRecordKind.EVENT,
                            payload=(
                                ("height", capture.height),
                                ("png_sha256", hashlib.sha256(capture.png_bytes).hexdigest()),
                                ("width", capture.width),
                            ),
                            binary_key=_screenshot_key(capture),
                        )
                    )
                    if screenshot_bytes > _MAX_SCREENSHOT_BUFFER_BYTES:
                        channel_failures["screenshots"] = (
                            "screenshot buffer exceeded 256 MiB"
                        )
                        screenshot_collector = None
                        break
            except Exception as exc:
                channel_failures["screenshots"] = f"{type(exc).__name__}: {exc}"
                screenshot_collector = None
        if trigger_ns is None:
            trigger_reason = _trigger_reason(
                request,
                metrics,
                baseline,
                trigger_counts,
            )
            if trigger_reason is not None:
                trigger_ns = now_ns
                completed.add("trigger")
                pending.append(
                    _PendingRecord(
                        channel_id="trigger",
                        monotonic_ns=now_ns,
                        captured_at_utc=now_utc,
                        kind=CaptureRecordKind.MARKER,
                        payload=(("reason", trigger_reason),),
                        correlation_id="diagnostic-trigger",
                    )
                )
        if trigger_ns is not None and request.profile is DiagnosticProfile.TRIGGERED:
            post_ns = int(request.effective_post_trigger_seconds * 1_000_000_000)
            if now_ns - trigger_ns >= post_ns:
                stop_reason = "post-trigger-complete"
                break
        if now_ns >= deadline_ns:
            break
        sleep_seconds = min(
            request.effective_sample_interval_seconds,
            max(0.0, (deadline_ns - now_ns) / 1_000_000_000),
        )
        if sleep_seconds <= 0:
            break
        session_clock.sleep(sleep_seconds)
        current_sample = None

    ended_ns = session_clock.monotonic_ns()
    ended_utc = session_clock.utc_timestamp()
    _capture_snapshot_channels(
        request,
        phase="end",
        store=store,
        descriptors=descriptors,
        completed=completed,
        failures=channel_failures,
        pending=pending,
        monotonic_ns=ended_ns,
        captured_at_utc=ended_utc,
    )
    retained_cutoff_ns = started_ns
    if request.profile is DiagnosticProfile.TRIGGERED:
        anchor_ns = trigger_ns if trigger_ns is not None else ended_ns
        retained_cutoff_ns = max(
            started_ns,
            anchor_ns - int(request.effective_pre_trigger_seconds * 1_000_000_000),
        )
    retained_binary_keys: set[tuple[object, ...]] = set()
    for channel in request.file_channels:
        if channel.mode is not FileCaptureMode.TAIL:
            continue
        collector = tail_collectors.get(channel.channel_id)
        chunks = [
            item
            for item in tail_chunks.get(channel.channel_id, [])
            if item.captured_monotonic_ns >= retained_cutoff_ns
        ]
        source_seen = bool(chunks) or channel.path.exists() or (
            collector is not None and collector.source_seen
        )
        if not source_seen:
            channel_failures.setdefault(channel.channel_id, f"source not found: {channel.path}")
            continue
        payload = b"".join(item.payload for item in chunks)
        descriptor = store.ingest_bytes(
            payload,
            artifact_kind=channel.artifact_kind,
            media_type=channel.media_type,
            logical_name=f"{channel.channel_id}-{channel.path.name}.tail",
            producer_id=_PRODUCER_ID,
            producer_version=_PRODUCER_VERSION,
            captured_at_utc=ended_utc,
            metadata=(
                ("channel_id", channel.channel_id),
                ("chunk_count", len(chunks)),
                ("retained_cutoff_monotonic_ns", retained_cutoff_ns),
            ),
        )
        descriptors.append(descriptor)
        retained_binary_keys.update(_file_chunk_key(item) for item in chunks)
        pending.append(
            _PendingRecord(
                channel_id=channel.channel_id,
                monotonic_ns=ended_ns,
                captured_at_utc=ended_utc,
                kind=CaptureRecordKind.ARTIFACT_REFERENCE,
                artifact_id=descriptor.artifact_id,
            )
        )
        if channel.channel_id not in channel_failures:
            completed.add(channel.channel_id)

    retained_screenshots = [
        item for item in screenshots if item.captured_monotonic_ns >= retained_cutoff_ns
    ]
    for index, capture in enumerate(retained_screenshots, start=1):
        descriptor = store.ingest_bytes(
            capture.png_bytes,
            artifact_kind=ArtifactKind.SCREENSHOT,
            media_type="image/png",
            logical_name=f"{run_id}.screenshot-{index:04d}.png",
            producer_id=_PRODUCER_ID,
            producer_version=_PRODUCER_VERSION,
            captured_at_utc=ended_utc,
            metadata=(
                ("channel_id", "screenshots"),
                ("height", capture.height),
                ("monotonic_ns", capture.captured_monotonic_ns),
                ("width", capture.width),
            ),
        )
        descriptors.append(descriptor)
        retained_binary_keys.add(_screenshot_key(capture))
        pending.append(
            _PendingRecord(
                channel_id="screenshots",
                monotonic_ns=ended_ns,
                captured_at_utc=ended_utc,
                kind=CaptureRecordKind.ARTIFACT_REFERENCE,
                payload=(("source_monotonic_ns", capture.captured_monotonic_ns),),
                artifact_id=descriptor.artifact_id,
            )
        )
    if request.screenshot_region is not None and retained_screenshots:
        if "screenshots" not in channel_failures:
            completed.add("screenshots")
    elif request.screenshot_region is not None:
        channel_failures.setdefault("screenshots", "no screenshots were retained")

    pending.append(
        _PendingRecord(
            channel_id="capture-markers",
            monotonic_ns=ended_ns,
            captured_at_utc=ended_utc,
            kind=CaptureRecordKind.MARKER,
            payload=(("marker", "session-end"), ("stop_reason", stop_reason)),
            correlation_id="session-lifecycle",
        )
    )
    filtered_pending = [
        item
        for item in pending
        if item.binary_key is None or item.binary_key in retained_binary_keys
    ]
    records = _finalize_records(
        run_id,
        clock_domain_id,
        filtered_pending,
    )
    stream_payload = {
        "schema_version": 1,
        "records": [item.as_dict() for item in records],
        "producer_health": [item.as_dict() for item in producer_health(records)],
    }
    stream_descriptor = _ingest_json(
        store,
        stream_payload,
        kind=ArtifactKind.PROCESS_METRICS,
        logical_name=f"{run_id}.capture-stream.json",
        captured_at_utc=ended_utc,
        metadata=(("channel_id", "capture-stream"),),
    )
    descriptors.append(stream_descriptor)
    completed.add("capture-stream")
    trace = align_capture_records(records)
    trace_descriptor = _ingest_json(
        store,
        trace.as_dict(),
        kind=ArtifactKind.SEMANTIC_TRACE,
        logical_name=f"{run_id}.semantic-trace.json",
        captured_at_utc=ended_utc,
        metadata=(("channel_id", "semantic-trace"), ("trace_id", trace.trace_id or "")),
    )
    descriptors.append(trace_descriptor)
    completed.add("semantic-trace")

    required = {
        "capture-window",
        "capture-stream",
        "execution-fingerprint",
        "process-identity",
        "process-metrics",
        "semantic-trace",
    }
    if request.reference_executable is not None:
        required.add("client-alignment")
    required.update(item.channel_id for item in request.file_channels)
    if request.screenshot_region is not None:
        required.add("screenshots")
    if request.profile is DiagnosticProfile.TRIGGERED:
        required.add("trigger")
        if trigger_ns is None:
            channel_failures["trigger"] = "no trigger was observed before the duration limit"
    if stop_reason in {"duration-complete", "post-trigger-complete"}:
        completed.add("capture-window")
    else:
        channel_failures["capture-window"] = (
            f"requested capture window ended early: {stop_reason}"
        )
    completed.intersection_update(required)
    missing = sorted(required - completed)
    omissions = tuple(
        sorted(
            f"{channel_id}: {channel_failures.get(channel_id, 'not captured')}"
            for channel_id in missing
        )
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "profile": request.profile.value,
        "started_at_utc": started_utc,
        "ended_at_utc": ended_utc,
        "elapsed_seconds": max(0.0, (ended_ns - started_ns) / 1_000_000_000),
        "stop_reason": stop_reason,
        "process_identity": initial_sample.identity.as_dict(),
        "fingerprint_id": fingerprint.fingerprint_id,
        "sample_count": sample_count,
        "triggered": trigger_ns is not None,
        "trigger_reason": trigger_reason,
        "retained_pre_trigger_cutoff_monotonic_ns": retained_cutoff_ns,
        "required_channels": sorted(required),
        "completed_channels": sorted(completed),
        "channel_failures": dict(sorted(channel_failures.items())),
        "warnings": sorted(warnings),
    }
    summary_descriptor = _ingest_json(
        store,
        summary,
        kind=ArtifactKind.RUNTIME_SNAPSHOT,
        logical_name=f"{run_id}.summary.json",
        captured_at_utc=ended_utc,
        metadata=(("channel_id", "diagnostic-summary"),),
    )
    descriptors.append(summary_descriptor)
    terminal = (
        ManifestTerminalState.FAILED
        if fatal or sample_count == 0
        else ManifestTerminalState.INCOMPLETE
        if missing
        else ManifestTerminalState.COMPLETE
    )
    artifacts = tuple(
        sorted(
            {item.artifact_id: item for item in descriptors}.values(),
            key=lambda item: item.artifact_id or "",
        )
    )
    manifest = EvidenceManifest(
        created_at_utc=ended_utc,
        fingerprint_id=fingerprint.fingerprint_id,
        run_id=run_id,
        artifacts=artifacts,
        terminal_state=terminal,
        required_channels=tuple(sorted(required)),
        completed_channels=tuple(sorted(completed)),
        omissions=omissions,
        warnings=tuple(sorted(warnings)),
    )
    save_contract(manifest_path, manifest)
    return DiagnosticCaptureResult(
        run_id=run_id,
        output_directory=output,
        store=store,
        manifest_path=manifest_path,
        manifest=manifest,
        summary=summary,
    )


def _capture_snapshot_channels(
    request: DiagnosticRequest,
    *,
    phase: str,
    store: ArtifactStore,
    descriptors: list[ArtifactDescriptor],
    completed: set[str],
    failures: dict[str, str],
    pending: list[_PendingRecord],
    monotonic_ns: int,
    captured_at_utc: str,
) -> None:
    for channel in request.file_channels:
        if channel.mode is not FileCaptureMode.SNAPSHOT:
            continue
        if not channel.path.is_file():
            failures[channel.channel_id] = f"source not found: {channel.path}"
            continue
        try:
            descriptor = store.ingest_file(
                channel.path,
                artifact_kind=channel.artifact_kind,
                media_type=channel.media_type,
                logical_name=f"{channel.channel_id}-{phase}-{channel.path.name}",
                producer_id=_PRODUCER_ID,
                producer_version=_PRODUCER_VERSION,
                captured_at_utc=captured_at_utc,
                metadata=(("channel_id", channel.channel_id), ("phase", phase)),
            )
            descriptors.append(descriptor)
            completed.add(channel.channel_id)
            failures.pop(channel.channel_id, None)
            pending.append(
                _PendingRecord(
                    channel_id=channel.channel_id,
                    monotonic_ns=monotonic_ns,
                    captured_at_utc=captured_at_utc,
                    kind=CaptureRecordKind.ARTIFACT_REFERENCE,
                    payload=(("phase", phase),),
                    artifact_id=descriptor.artifact_id,
                )
            )
        except Exception as exc:
            failures[channel.channel_id] = f"{type(exc).__name__}: {exc}"


def _trigger_reason(
    request: DiagnosticRequest,
    metrics: dict[str, float],
    baseline: dict[str, float],
    counts: dict[int, int],
) -> str | None:
    if request.manual_trigger_file is not None and request.manual_trigger_file.exists():
        return f"manual-trigger-file:{request.manual_trigger_file}"
    for index, rule in enumerate(request.trigger_rules):
        counts[index] = counts[index] + 1 if rule.matches(metrics, baseline) else 0
        if counts[index] >= rule.consecutive_samples:
            mode = "delta" if rule.compare_to_baseline else "absolute"
            return (
                f"metric:{rule.metric}:{mode}:{rule.operator.value}:"
                f"{float(rule.threshold)}:{rule.consecutive_samples}"
            )
    return None


def _finalize_records(
    run_id: str,
    clock_domain_id: str,
    pending: list[_PendingRecord],
) -> tuple[CaptureRecord, ...]:
    ordered = tuple(
        item
        for _, item in sorted(
            enumerate(pending),
            key=lambda indexed: (indexed[1].monotonic_ns, indexed[0]),
        )
    )
    return tuple(
        CaptureRecord(
            run_id=run_id,
            channel_id=item.channel_id,
            producer_id=_PRODUCER_ID,
            producer_version=_PRODUCER_VERSION,
            clock_domain_id=clock_domain_id,
            monotonic_ns=item.monotonic_ns,
            utc_uncertainty_ns=1_000_000,
            captured_at_utc=item.captured_at_utc,
            producer_sequence=sequence,
            kind=item.kind,
            payload=item.payload,
            correlation_id=item.correlation_id,
            artifact_id=item.artifact_id,
            quality=tuple(sorted(item.quality, key=lambda value: value.value)),
        )
        for sequence, item in enumerate(ordered, start=1)
    )


def _ingest_json(
    store: ArtifactStore,
    payload: dict[str, object],
    *,
    kind: ArtifactKind,
    logical_name: str,
    captured_at_utc: str,
    metadata: tuple[tuple[str, object], ...],
) -> ArtifactDescriptor:
    return store.ingest_bytes(
        canonical_json_bytes(payload),
        artifact_kind=kind,
        media_type="application/json",
        logical_name=logical_name,
        producer_id=_PRODUCER_ID,
        producer_version=_PRODUCER_VERSION,
        captured_at_utc=captured_at_utc,
        metadata=metadata,
    )


def _validate_requested_executable(
    requested: Path | None,
    identity: ProcessIdentity,
) -> None:
    if requested is None:
        return
    if _normalized_path(requested) != _normalized_path(identity.executable_path):
        raise DiagnosticError(
            "requested client executable does not match the exact live process image"
        )


def _normalized_path(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve(strict=False)))


def _file_chunk_key(chunk: FileChunk) -> tuple[object, ...]:
    return (
        "file",
        chunk.channel_id,
        chunk.captured_monotonic_ns,
        chunk.source_generation,
        chunk.source_offset,
        hashlib.sha256(chunk.payload).hexdigest(),
    )


def _screenshot_key(capture: ScreenshotCapture) -> tuple[object, ...]:
    return (
        "screenshot",
        capture.captured_monotonic_ns,
        hashlib.sha256(capture.png_bytes).hexdigest(),
    )


__all__ = [
    "DiagnosticCaptureResult",
    "SessionClock",
    "SystemSessionClock",
    "run_diagnostic_capture",
]
