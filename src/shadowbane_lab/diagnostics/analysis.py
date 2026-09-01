"""Offline analysis and before/after comparison of sealed diagnostic captures."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from statistics import fmean, median
from typing import Any

from shadowbane_lab.cases import CaptureRecord, parse_capture_record, producer_health
from shadowbane_lab.differential.statistics import summarize_samples
from shadowbane_lab.evidence import (
    ArtifactDescriptor,
    ArtifactStore,
    EvidenceManifest,
    VerificationStatus,
    verify_manifest,
)
from shadowbane_lab.integrity import canonical_json_sha256

from .model import DiagnosticError

_ANALYSIS_SCHEMA_VERSION = 1
_ANALYZER_ID = "shadowbane-lab.diagnostic-analysis"
_ANALYZER_VERSION = "2"
_MAX_HITCH_RECORDS_PER_THRESHOLD = 10_000
_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)


def analyze_diagnostic_capture(
    store: ArtifactStore,
    manifest: EvidenceManifest,
) -> dict[str, object]:
    """Derive a stable report without mutating the source capture or store."""

    records, stream_descriptor = _load_capture_records(store, manifest)
    metrics, times_ns = _metric_samples(records)
    summaries = {
        metric: _summarize_metric(values, times_ns) for metric, values in sorted(metrics.items())
    }
    health = tuple(item.as_dict() for item in producer_health(records))
    metric_times = [item.monotonic_ns for item in records if item.channel_id == "process-metrics"]
    sample_gaps = tuple(
        (current - previous) / 1_000_000_000
        for previous, current in zip(metric_times, metric_times[1:], strict=False)
    )
    source_summary = _optional_json_channel(store, manifest, "diagnostic-summary")
    frame_timing_payload = _optional_json_channel(store, manifest, "frame-timing")
    frame_timing = _summarize_frame_timing(frame_timing_payload)
    if frame_timing is not None:
        frame_timing = {
            "source_artifact_id": _single_channel(manifest, "frame-timing").artifact_id,
            **frame_timing,
        }
    alignment = _optional_json_channel(store, manifest, "client-alignment")
    content: dict[str, object] = {
        "schema_version": _ANALYSIS_SCHEMA_VERSION,
        "analyzer_id": _ANALYZER_ID,
        "analyzer_version": _ANALYZER_VERSION,
        "source_manifest_id": manifest.manifest_id,
        "source_fingerprint_id": manifest.fingerprint_id,
        "source_run_id": manifest.run_id,
        "source_capture_stream_artifact_id": stream_descriptor.artifact_id,
        "source_terminal_state": manifest.terminal_state.value,
        "source_omissions": list(manifest.omissions),
        "sample_count": len(metric_times),
        "sample_timing": {
            "elapsed_seconds": (
                (metric_times[-1] - metric_times[0]) / 1_000_000_000
                if len(metric_times) > 1
                else 0.0
            ),
            "gap_count": len(sample_gaps),
            "minimum_gap_seconds": min(sample_gaps) if sample_gaps else None,
            "median_gap_seconds": median(sample_gaps) if sample_gaps else None,
            "maximum_gap_seconds": max(sample_gaps) if sample_gaps else None,
        },
        "metrics": summaries,
        "growth_signals": _growth_signals(summaries),
        "producer_health": list(health),
        "capture_summary": source_summary,
        "frame_timing": frame_timing,
        "client_alignment": _alignment_summary(alignment),
        "limitations": [
            "sampled counters establish timing and correlation, not root-cause causation",
            (
                "thread stalls, GPU queues, kernel scheduling, and packet payloads "
                "require their own requested channels"
            ),
            "heuristic client alignment never authorizes an address mapping without review",
        ],
    }
    return {
        "report_id": f"sha256:{canonical_json_sha256(content)}",
        **content,
    }


def compare_diagnostic_captures(
    baseline_store: ArtifactStore,
    baseline_manifest: EvidenceManifest,
    candidate_store: ArtifactStore,
    candidate_manifest: EvidenceManifest,
) -> dict[str, object]:
    """Compare raw metric samples from two independently sealed captures."""

    baseline_records, baseline_stream = _load_capture_records(
        baseline_store,
        baseline_manifest,
    )
    candidate_records, candidate_stream = _load_capture_records(
        candidate_store,
        candidate_manifest,
    )
    baseline_metrics, baseline_times = _metric_samples(baseline_records)
    candidate_metrics, candidate_times = _metric_samples(candidate_records)
    baseline_frame_timing = _summarize_frame_timing(
        _optional_json_channel(baseline_store, baseline_manifest, "frame-timing")
    )
    candidate_frame_timing = _summarize_frame_timing(
        _optional_json_channel(candidate_store, candidate_manifest, "frame-timing")
    )
    frame_timing_comparison = _compare_frame_timing(baseline_frame_timing, candidate_frame_timing)
    shared = sorted(set(baseline_metrics) & set(candidate_metrics))
    comparisons: dict[str, object] = {}
    for metric in shared:
        baseline_values = baseline_metrics[metric]
        candidate_values = candidate_metrics[metric]
        baseline_summary = _summarize_metric(baseline_values, baseline_times)
        candidate_summary = _summarize_metric(candidate_values, candidate_times)
        statistical = summarize_samples(
            metric,
            candidate_values,
            baseline_samples=baseline_values,
            minimum_samples=30,
        )
        baseline_mean = float(baseline_summary["mean"])
        candidate_mean = float(candidate_summary["mean"])
        comparisons[metric] = {
            "baseline": baseline_summary,
            "candidate": candidate_summary,
            "mean_delta": candidate_mean - baseline_mean,
            "mean_ratio": (candidate_mean / baseline_mean if baseline_mean != 0 else None),
            "net_change_delta": (
                float(candidate_summary["delta"]) - float(baseline_summary["delta"])
            ),
            "statistical_result": statistical.as_dict(),
        }
    missing_from_candidate = sorted(set(baseline_metrics) - set(candidate_metrics))
    new_in_candidate = sorted(set(candidate_metrics) - set(baseline_metrics))
    content: dict[str, object] = {
        "schema_version": _ANALYSIS_SCHEMA_VERSION,
        "analyzer_id": _ANALYZER_ID,
        "analyzer_version": _ANALYZER_VERSION,
        "baseline": {
            "manifest_id": baseline_manifest.manifest_id,
            "fingerprint_id": baseline_manifest.fingerprint_id,
            "run_id": baseline_manifest.run_id,
            "capture_stream_artifact_id": baseline_stream.artifact_id,
            "sample_count": len(baseline_times),
        },
        "candidate": {
            "manifest_id": candidate_manifest.manifest_id,
            "fingerprint_id": candidate_manifest.fingerprint_id,
            "run_id": candidate_manifest.run_id,
            "capture_stream_artifact_id": candidate_stream.artifact_id,
            "sample_count": len(candidate_times),
        },
        "same_fingerprint": (baseline_manifest.fingerprint_id == candidate_manifest.fingerprint_id),
        "shared_metrics": shared,
        "missing_from_candidate": missing_from_candidate,
        "new_in_candidate": new_in_candidate,
        "metrics": comparisons,
        "frame_timing": frame_timing_comparison,
        "review_required": (
            baseline_manifest.fingerprint_id != candidate_manifest.fingerprint_id
            or bool(missing_from_candidate)
        ),
        "limitations": [
            "different fingerprints can confound before/after attribution",
            (
                "effect sizes are descriptive unless the stopping rule and sampling "
                "design were fixed in advance"
            ),
        ],
    }
    return {
        "comparison_id": f"sha256:{canonical_json_sha256(content)}",
        **content,
    }


def _summarize_frame_timing(payload: object | None) -> dict[str, object] | None:
    if payload is None:
        return None
    value = _mapping(payload, "frame timing artifact")
    if value.get("schema_version") != 1:
        raise DiagnosticError("frame timing artifact schema is unsupported")
    if value.get("producer_id") != "wonderbane-extension.graphics":
        raise DiagnosticError("frame timing artifact producer is unsupported")
    clock = _mapping(value.get("clock"), "frame timing clock")
    if clock.get("domain") != "windows-query-performance-counter":
        raise DiagnosticError("frame timing clock domain is unsupported")
    frequency = _positive_integer(
        clock.get("counter_frequency_hz"),
        "frame timing counter frequency",
    )
    anchors_value = clock.get("anchors")
    if not isinstance(anchors_value, list) or len(anchors_value) > 100_001:
        raise DiagnosticError("frame timing anchors must be a bounded list")
    anchors = tuple(_frame_anchor(item) for item in anchors_value)
    samples_value = value.get("samples")
    if not isinstance(samples_value, list) or len(samples_value) > 2_000_000:
        raise DiagnosticError("frame timing samples must be a bounded list")
    if value.get("sample_count") != len(samples_value):
        raise DiagnosticError("frame timing sample_count does not match samples")
    samples: list[tuple[int, int, int]] = []
    previous_sequence = 0
    for item in samples_value:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or any(isinstance(part, bool) or not isinstance(part, int) for part in item)
        ):
            raise DiagnosticError(
                "frame timing samples must be sequence,counter,observation triples"
            )
        sequence, counter, observed_ns = item
        if sequence <= previous_sequence or counter <= 0 or observed_ns < 0:
            raise DiagnosticError("frame timing samples are not strictly ordered")
        samples.append((sequence, counter, observed_ns))
        previous_sequence = sequence
    gaps_value = value.get("gaps")
    if not isinstance(gaps_value, list) or len(gaps_value) > 2_000_000:
        raise DiagnosticError("frame timing gaps must be a bounded list")
    gaps = tuple(_mapping(item, "frame timing gap") for item in gaps_value)
    missing_present_count = 0
    for gap in gaps:
        missing = _nonnegative_integer(gap.get("missing_count"), "frame timing gap count")
        first = _positive_integer(gap.get("first_sequence"), "frame timing gap start")
        last = _positive_integer(gap.get("last_sequence"), "frame timing gap end")
        if last < first or missing != last - first + 1:
            raise DiagnosticError("frame timing gap range is inconsistent")
        missing_present_count += missing

    intervals: list[tuple[int, int, float]] = []
    for previous, current in zip(samples, samples[1:], strict=False):
        if current[0] != previous[0] + 1:
            continue
        delta = current[1] - previous[1]
        if delta <= 0:
            raise DiagnosticError("frame timing counters do not increase")
        intervals.append((current[0], current[1], delta * 1000.0 / frequency))
    durations = tuple(item[2] for item in intervals)
    mean_duration = fmean(durations) if durations else None
    frame_time = (
        {
            "minimum": min(durations),
            "median": median(durations),
            "p95": _nearest_rank(durations, 0.95),
            "p99": _nearest_rank(durations, 0.99),
            "maximum": max(durations),
            "mean": mean_duration,
        }
        if durations
        else None
    )
    average_fps = (
        1000.0 / mean_duration if mean_duration is not None and mean_duration > 0 else None
    )
    hitches = {
        label: _hitch_summary(intervals, threshold, frequency, anchors)
        for label, threshold in (
            ("at_least_33_3_ms", 33.3),
            ("at_least_50_ms", 50.0),
            ("at_least_100_ms", 100.0),
            ("at_least_250_ms", 250.0),
        )
    }
    query_failures = _nonnegative_integer(
        value.get("retained_timing_query_failure_delta"),
        "retained timing query failure delta",
    )
    sample_drops = _nonnegative_integer(
        value.get("capture_sample_drop_count"),
        "frame timing capture sample drop count",
    )
    poll_failures = _nonnegative_integer(
        value.get("poll_failure_count"),
        "frame timing poll failure count",
    )
    if not isinstance(value.get("complete"), bool):
        raise DiagnosticError("frame timing complete flag must be boolean")
    return {
        "complete": value["complete"],
        "sample_count": len(samples),
        "interval_count": len(intervals),
        "average_fps": average_fps,
        "frame_time_ms": frame_time,
        "hitches": hitches,
        "gap_count": len(gaps),
        "missing_present_count": missing_present_count,
        "timing_query_failure_count": query_failures,
        "capture_sample_drop_count": sample_drops,
        "poll_failure_count": poll_failures,
        "limitations": [
            "present intervals measure completed buffer swaps, not isolated GPU execution time",
            "UTC present timestamps are QPC-to-FILETIME estimates from the nearest producer anchor",
        ],
    }


def _hitch_summary(
    intervals: list[tuple[int, int, float]],
    threshold_ms: float,
    frequency_hz: int,
    anchors: tuple[dict[str, int], ...],
) -> dict[str, object]:
    matching = [item for item in intervals if item[2] >= threshold_ms]
    records = [
        {
            "present_sequence": sequence,
            "frame_time_ms": duration_ms,
            "estimated_presented_at_utc": _estimated_present_utc(counter, frequency_hz, anchors),
        }
        for sequence, counter, duration_ms in matching[:_MAX_HITCH_RECORDS_PER_THRESHOLD]
    ]
    return {
        "threshold_ms": threshold_ms,
        "count": len(matching),
        "records": records,
        "record_drop_count": len(matching) - len(records),
    }


def _estimated_present_utc(
    counter: int,
    frequency_hz: int,
    anchors: tuple[dict[str, int], ...],
) -> str | None:
    if not anchors:
        return None
    anchor = min(anchors, key=lambda item: abs(counter - item["snapshot_counter"]))
    filetime = anchor["snapshot_filetime_utc"] + round(
        (counter - anchor["snapshot_counter"]) * 10_000_000 / frequency_hz
    )
    if filetime < 0:
        return None
    timestamp = _FILETIME_EPOCH + timedelta(microseconds=filetime // 10)
    return timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _frame_anchor(value: object) -> dict[str, int]:
    anchor = _mapping(value, "frame timing anchor")
    return {
        "snapshot_counter": _positive_integer(
            anchor.get("snapshot_counter"), "frame timing snapshot counter"
        ),
        "snapshot_filetime_utc": _positive_integer(
            anchor.get("snapshot_filetime_utc"), "frame timing snapshot FILETIME"
        ),
    }


def _compare_frame_timing(
    baseline: dict[str, object] | None,
    candidate: dict[str, object] | None,
) -> dict[str, object] | None:
    if baseline is None and candidate is None:
        return None
    if baseline is None or candidate is None:
        return {
            "state": "not-comparable",
            "baseline": baseline,
            "candidate": candidate,
            "reason": "frame timing channel is absent from one capture",
        }
    comparisons: dict[str, object] = {
        "average_fps": _numeric_comparison(
            baseline.get("average_fps"), candidate.get("average_fps")
        )
    }
    for name in ("median", "p95", "p99", "maximum"):
        baseline_frame = baseline.get("frame_time_ms")
        candidate_frame = candidate.get("frame_time_ms")
        comparisons[f"frame_time_ms_{name}"] = _numeric_comparison(
            baseline_frame.get(name) if isinstance(baseline_frame, dict) else None,
            candidate_frame.get(name) if isinstance(candidate_frame, dict) else None,
        )
    return {
        "state": "comparable",
        "baseline": baseline,
        "candidate": candidate,
        "metrics": comparisons,
    }


def _numeric_comparison(baseline: object, candidate: object) -> dict[str, object]:
    if not isinstance(baseline, int | float) or not isinstance(candidate, int | float):
        return {"baseline": baseline, "candidate": candidate, "delta": None, "ratio": None}
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": candidate - baseline,
        "ratio": candidate / baseline if baseline != 0 else None,
    }


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DiagnosticError(f"{name} must be an object")
    return value


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DiagnosticError(f"{name} must be a positive integer")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DiagnosticError(f"{name} must be a non-negative integer")
    return value


def _load_capture_records(
    store: ArtifactStore,
    manifest: EvidenceManifest,
) -> tuple[tuple[CaptureRecord, ...], ArtifactDescriptor]:
    receipt = verify_manifest(store, manifest)
    if receipt.status is not VerificationStatus.PASS:
        raise DiagnosticError("source diagnostic manifest failed artifact verification")
    descriptor = _single_channel(manifest, "capture-stream")
    payload = _load_json_artifact(store, descriptor)
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "records",
        "producer_health",
    }:
        raise DiagnosticError("capture stream fields are not exact")
    if payload["schema_version"] != 1 or not isinstance(payload["records"], list):
        raise DiagnosticError("capture stream schema is unsupported")
    try:
        records = tuple(parse_capture_record(item) for item in payload["records"])
    except (TypeError, ValueError) as exc:
        raise DiagnosticError(f"capture stream contains an invalid record: {exc}") from exc
    expected_health = [item.as_dict() for item in producer_health(records)]
    if payload["producer_health"] != expected_health:
        raise DiagnosticError("capture stream producer health does not match its records")
    return records, descriptor


def _metric_samples(
    records: tuple[CaptureRecord, ...],
) -> tuple[dict[str, tuple[float, ...]], tuple[int, ...]]:
    rows = [item for item in records if item.channel_id == "process-metrics"]
    if not rows:
        raise DiagnosticError("capture contains no process metric samples")
    names = sorted(
        set.intersection(
            *(
                {
                    name
                    for name, value in row.payload
                    if name != "sample_index"
                    and isinstance(value, int | float)
                    and not isinstance(value, bool)
                }
                for row in rows
            )
        )
    )
    metrics = {name: tuple(float(dict(row.payload)[name]) for row in rows) for name in names}
    return metrics, tuple(row.monotonic_ns for row in rows)


def _summarize_metric(
    values: tuple[float, ...],
    times_ns: tuple[int, ...],
) -> dict[str, object]:
    elapsed = (times_ns[-1] - times_ns[0]) / 1_000_000_000 if len(times_ns) > 1 else 0.0
    delta = values[-1] - values[0]
    return {
        "sample_count": len(values),
        "first": values[0],
        "last": values[-1],
        "minimum": min(values),
        "maximum": max(values),
        "mean": fmean(values),
        "median": median(values),
        "p95": _nearest_rank(values, 0.95),
        "p99": _nearest_rank(values, 0.99),
        "delta": delta,
        "delta_per_second": delta / elapsed if elapsed > 0 else None,
        "least_squares_slope_per_second": _least_squares_slope(values, times_ns),
    }


def _nearest_rank(values: tuple[float, ...], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * quantile + 0.999999) - 1))
    return ordered[index]


def _least_squares_slope(
    values: tuple[float, ...],
    times_ns: tuple[int, ...],
) -> float | None:
    if len(values) < 2 or times_ns[-1] == times_ns[0]:
        return None
    times = tuple((value - times_ns[0]) / 1_000_000_000 for value in times_ns)
    mean_time = fmean(times)
    mean_value = fmean(values)
    denominator = sum((value - mean_time) ** 2 for value in times)
    if denominator == 0:
        return None
    return (
        sum(
            (time_value - mean_time) * (metric_value - mean_value)
            for time_value, metric_value in zip(times, values, strict=True)
        )
        / denominator
    )


def _growth_signals(
    summaries: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []
    thresholds = {
        "process_private_bytes": (16 * 1024 * 1024, 0.05),
        "process_working_set_bytes": (16 * 1024 * 1024, 0.05),
        "process_handle_count": (100.0, 0.10),
        "gdi_object_count": (100.0, 0.10),
        "user_object_count": (100.0, 0.10),
    }
    for metric, (absolute_threshold, relative_threshold) in thresholds.items():
        if metric not in summaries:
            continue
        summary = summaries[metric]
        first = abs(float(summary["first"]))
        delta = float(summary["delta"])
        slope_value = summary["least_squares_slope_per_second"]
        threshold = max(absolute_threshold, first * relative_threshold)
        signals.append(
            {
                "metric": metric,
                "candidate": (
                    delta >= threshold and slope_value is not None and float(slope_value) > 0
                ),
                "observed_delta": delta,
                "positive_growth_threshold": threshold,
                "least_squares_slope_per_second": slope_value,
            }
        )
    return signals


def _alignment_summary(value: object | None) -> object | None:
    if not isinstance(value, dict):
        return None
    comparison = value.get("comparison")
    interpretation = value.get("diagnostic_interpretation")
    return {
        "reference_sha256": (
            value.get("reference", {}).get("sha256")
            if isinstance(value.get("reference"), dict)
            else None
        ),
        "candidate_sha256": (
            value.get("candidate", {}).get("sha256")
            if isinstance(value.get("candidate"), dict)
            else None
        ),
        "exact_file_match": (
            comparison.get("exact_file_match") if isinstance(comparison, dict) else None
        ),
        "recommendation": value.get("recommendation"),
        "diagnostic_interpretation": interpretation,
    }


def _optional_json_channel(
    store: ArtifactStore,
    manifest: EvidenceManifest,
    channel_id: str,
) -> object | None:
    descriptors = _channel_descriptors(manifest, channel_id)
    if not descriptors:
        return None
    if len(descriptors) != 1:
        raise DiagnosticError(f"expected exactly one {channel_id} artifact")
    return _load_json_artifact(store, descriptors[0])


def _single_channel(
    manifest: EvidenceManifest,
    channel_id: str,
) -> ArtifactDescriptor:
    descriptors = _channel_descriptors(manifest, channel_id)
    if len(descriptors) != 1:
        raise DiagnosticError(f"expected exactly one {channel_id} artifact")
    return descriptors[0]


def _channel_descriptors(
    manifest: EvidenceManifest,
    channel_id: str,
) -> tuple[ArtifactDescriptor, ...]:
    return tuple(
        item for item in manifest.artifacts if dict(item.metadata).get("channel_id") == channel_id
    )


def _load_json_artifact(
    store: ArtifactStore,
    descriptor: ArtifactDescriptor,
) -> object:
    with store.open_artifact(descriptor.artifact_id or "") as stream:
        payload = stream.read()

    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DiagnosticError(f"duplicate JSON field in artifact: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=lambda value: _raise_nonfinite(value),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DiagnosticError("diagnostic JSON artifact is invalid") from exc


def _raise_nonfinite(value: str) -> None:
    raise DiagnosticError(f"non-finite JSON value: {value}")


__all__ = [
    "analyze_diagnostic_capture",
    "compare_diagnostic_captures",
]
