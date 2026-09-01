"""Offline analysis and before/after comparison of sealed diagnostic captures."""

from __future__ import annotations

import json
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
_ANALYZER_VERSION = "1"


def analyze_diagnostic_capture(
    store: ArtifactStore,
    manifest: EvidenceManifest,
) -> dict[str, object]:
    """Derive a stable report without mutating the source capture or store."""

    records, stream_descriptor = _load_capture_records(store, manifest)
    metrics, times_ns = _metric_samples(records)
    summaries = {
        metric: _summarize_metric(values, times_ns)
        for metric, values in sorted(metrics.items())
    }
    health = tuple(item.as_dict() for item in producer_health(records))
    metric_times = [
        item.monotonic_ns for item in records if item.channel_id == "process-metrics"
    ]
    sample_gaps = tuple(
        (current - previous) / 1_000_000_000
        for previous, current in zip(metric_times, metric_times[1:], strict=False)
    )
    source_summary = _optional_json_channel(store, manifest, "diagnostic-summary")
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
            "mean_ratio": (
                candidate_mean / baseline_mean if baseline_mean != 0 else None
            ),
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
        "same_fingerprint": (
            baseline_manifest.fingerprint_id == candidate_manifest.fingerprint_id
        ),
        "shared_metrics": shared,
        "missing_from_candidate": missing_from_candidate,
        "new_in_candidate": new_in_candidate,
        "metrics": comparisons,
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
    rows = [
        item for item in records if item.channel_id == "process-metrics"
    ]
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
    metrics = {
        name: tuple(float(dict(row.payload)[name]) for row in rows)
        for name in names
    }
    return metrics, tuple(row.monotonic_ns for row in rows)


def _summarize_metric(
    values: tuple[float, ...],
    times_ns: tuple[int, ...],
) -> dict[str, object]:
    elapsed = (
        (times_ns[-1] - times_ns[0]) / 1_000_000_000
        if len(times_ns) > 1
        else 0.0
    )
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
    return sum(
        (time_value - mean_time) * (metric_value - mean_value)
        for time_value, metric_value in zip(times, values, strict=True)
    ) / denominator


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
                    delta >= threshold
                    and slope_value is not None
                    and float(slope_value) > 0
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
            comparison.get("exact_file_match")
            if isinstance(comparison, dict)
            else None
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
        item
        for item in manifest.artifacts
        if dict(item.metadata).get("channel_id") == channel_id
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
            parse_constant=lambda value: (_raise_nonfinite(value)),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DiagnosticError("diagnostic JSON artifact is invalid") from exc


def _raise_nonfinite(value: str) -> None:
    raise DiagnosticError(f"non-finite JSON value: {value}")


__all__ = [
    "analyze_diagnostic_capture",
    "compare_diagnostic_captures",
]
