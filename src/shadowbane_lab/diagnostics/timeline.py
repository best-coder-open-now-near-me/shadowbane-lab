"""One-file correlation of frame, streaming, position, camera, and operator phases."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from .markers import ObservationMarker, ObservationPhase
from .process import ProcessIdentity

DIAGNOSTIC_TIMELINE_SCHEMA_VERSION = 1
SLOW_FRAME_THRESHOLD_MS = 40.0
_CLASSIFICATIONS = (
    "unmeasured",
    "normal",
    "cache-read",
    "texture-upload",
    "arrival-streaming-and-upload",
    "resident-unexplained",
)
_EXPECTED_PHASES = (
    ObservationPhase.COLD_APPROACH.value,
    ObservationPhase.STATIONARY.value,
    ObservationPhase.WARM_RETURN.value,
)


def build_diagnostic_timeline(
    *,
    run_id: str,
    identity: ProcessIdentity,
    started_monotonic_ns: int,
    started_at_utc: str,
    ended_monotonic_ns: int,
    ended_at_utc: str,
    performance_report: dict[str, object],
    player_samples: Sequence[dict[str, object]],
    camera_report: dict[str, object] | None,
    observation_markers: Sequence[ObservationMarker],
) -> dict[str, object]:
    """Build a deterministic, self-contained timeline without inventing missing data."""

    frames = _mapping_list(performance_report.get("frames"), "performance frames")
    players = sorted(
        (dict(item) for item in player_samples),
        key=lambda item: _integer(item.get("monotonic_ns"), "player monotonic_ns"),
    )
    cameras = _camera_samples(camera_report)
    markers = sorted(
        observation_markers,
        key=lambda item: (item.monotonic_ns, item.marker_id),
    )
    player_times = [
        _integer(item.get("monotonic_ns"), "player monotonic_ns") for item in players
    ]
    camera_times = [
        _integer(item.get("camera_monotonic_ns"), "camera monotonic_ns")
        for item in cameras
    ]
    phase: str | None = None
    phase_cursor = 0
    marker_cursor = 0
    previous_frame_ns: int | None = None
    correlated_frames: list[dict[str, object]] = []
    classification_counts = {name: 0 for name in _CLASSIFICATIONS}
    phase_statistics: dict[str, dict[str, int]] = {}

    ordered_frames = sorted(
        (dict(item) for item in frames),
        key=lambda item: _integer(item.get("sequence"), "frame sequence"),
    )
    for frame in ordered_frames:
        frame_ns = _integer(frame.get("frame_monotonic_ns"), "frame monotonic_ns")
        while phase_cursor < len(markers) and markers[phase_cursor].monotonic_ns <= frame_ns:
            marker_phase = markers[phase_cursor].phase
            if marker_phase is not None:
                phase = marker_phase.value
            phase_cursor += 1
        frame_marker_ids: list[str] = []
        while marker_cursor < len(markers) and markers[marker_cursor].monotonic_ns <= frame_ns:
            marker = markers[marker_cursor]
            if previous_frame_ns is None or marker.monotonic_ns > previous_frame_ns:
                frame_marker_ids.append(marker.marker_id)
            marker_cursor += 1
        classification = _classify_frame(frame)
        classification_counts[classification] += 1
        active_phase = phase or "unmarked"
        statistics = phase_statistics.setdefault(
            active_phase,
            {
                "frame_count": 0,
                "measured_frame_count": 0,
                "slow_frame_count": 0,
                "resident_unexplained_slow_frame_count": 0,
                "cache_read_count": 0,
                "cache_read_bytes": 0,
                "texture_upload_count": 0,
                "texture_upload_bytes": 0,
            },
        )
        statistics["frame_count"] += 1
        frame_time = _optional_number(frame.get("frame_time_ms"), "frame_time_ms")
        if frame_time is not None:
            statistics["measured_frame_count"] += 1
            if frame_time >= SLOW_FRAME_THRESHOLD_MS:
                statistics["slow_frame_count"] += 1
                if classification == "resident-unexplained":
                    statistics["resident_unexplained_slow_frame_count"] += 1
        cache = _mapping(frame.get("cache_reads"), "frame cache_reads")
        texture = _mapping(frame.get("texture_uploads"), "frame texture_uploads")
        statistics["cache_read_count"] += _integer(cache.get("count"), "cache count")
        statistics["cache_read_bytes"] += _integer(cache.get("bytes"), "cache bytes")
        statistics["texture_upload_count"] += _integer(
            texture.get("count"), "texture count"
        )
        statistics["texture_upload_bytes"] += _integer(
            texture.get("bytes"), "texture bytes"
        )
        player_index = _nearest_index(player_times, frame_ns)
        camera_index = _nearest_index(camera_times, frame_ns)
        correlated_frames.append(
            {
                **frame,
                "frame_at_utc": _utc_at(
                    started_at_utc,
                    frame_ns - started_monotonic_ns,
                ),
                "classification": classification,
                "phase": active_phase,
                "correlation": {
                    "marker_ids_since_previous_frame": frame_marker_ids,
                    "player": _sample_reference(
                        players,
                        player_times,
                        player_index,
                        frame_ns,
                        "sample_index",
                    ),
                    "camera": _sample_reference(
                        cameras,
                        camera_times,
                        camera_index,
                        frame_ns,
                        "sequence",
                    ),
                },
            }
        )
        previous_frame_ns = frame_ns

    present_phases = sorted(
        {marker.phase.value for marker in markers if marker.phase is not None}
    )
    missing_phases = [
        phase_name for phase_name in _EXPECTED_PHASES if phase_name not in present_phases
    ]
    stationary = phase_statistics.get(ObservationPhase.STATIONARY.value, {})
    stationary_unexplained = int(
        stationary.get("resident_unexplained_slow_frame_count", 0)
    )
    warm_upload_frames = sum(
        1
        for frame in correlated_frames
        if frame["phase"] == ObservationPhase.WARM_RETURN.value
        and _integer(
            _mapping(frame["texture_uploads"], "frame texture_uploads").get("count"),
            "texture count",
        )
        > 0
    )
    measured_frame_count = sum(
        count
        for name, count in classification_counts.items()
        if name != "unmeasured"
    )
    slow_frame_count = sum(
        int(stats["slow_frame_count"]) for stats in phase_statistics.values()
    )
    timeline_complete = bool(correlated_frames) and bool(
        performance_report.get("complete")
    )
    return {
        "schema_version": DIAGNOSTIC_TIMELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "process_identity": identity.as_dict(),
        "capture_window": {
            "started_monotonic_ns": started_monotonic_ns,
            "started_at_utc": started_at_utc,
            "ended_monotonic_ns": ended_monotonic_ns,
            "ended_at_utc": ended_at_utc,
        },
        "policy": {
            "slow_frame_threshold_ms": SLOW_FRAME_THRESHOLD_MS,
            "frame_clock": "windows-query-performance-counter",
            "correlation_clock": "windows-qpc-shared-source",
            "player_sampling_target_hz": "5-10",
        },
        "markers": [item.as_dict() for item in markers],
        "player_samples": players,
        "camera_samples": cameras,
        "frames": correlated_frames,
        "summary": {
            "frame_count": len(correlated_frames),
            "measured_frame_count": measured_frame_count,
            "slow_frame_count": slow_frame_count,
            "classification_counts": classification_counts,
            "phase_statistics": dict(sorted(phase_statistics.items())),
            "present_phases": present_phases,
            "missing_protocol_phases": missing_phases,
            "phase_protocol_complete": not missing_phases,
            "stationary_resident_unexplained_slow_frame_count": stationary_unexplained,
            "warm_return_texture_upload_frame_count": warm_upload_frames,
            "cpu_stack_capture_recommended": stationary_unexplained >= 3,
            "texture_identity_followup_recommended": warm_upload_frames > 0,
            "texture_identity_followup_reason": (
                "warm return still uploads textures; collect IDs and lifetimes to test repetition"
                if warm_upload_frames
                else "no warm-return texture uploads observed"
            ),
        },
        "health": {
            "performance_complete": bool(performance_report.get("complete")),
            "phase_protocol_complete": not missing_phases,
            "player_sample_count": len(players),
            "camera_sample_count": len(cameras),
        },
        "complete": timeline_complete,
    }


def _camera_samples(report: dict[str, object] | None) -> list[dict[str, object]]:
    if report is None:
        return []
    clock = _mapping(report.get("clock"), "camera clock")
    frequency = _integer(clock.get("counter_frequency_hz"), "camera frequency")
    if frequency <= 0:
        raise ValueError("camera frequency must be positive")
    samples = _mapping_list(report.get("samples"), "camera samples")
    result = []
    for item in samples:
        counter = _integer(item.get("counter"), "camera counter")
        result.append(
            {
                **item,
                "camera_monotonic_ns": counter * 1_000_000_000 // frequency,
            }
        )
    return sorted(result, key=lambda item: int(item["camera_monotonic_ns"]))


def _classify_frame(frame: dict[str, object]) -> str:
    frame_time = _optional_number(frame.get("frame_time_ms"), "frame_time_ms")
    if frame_time is None:
        return "unmeasured"
    if frame_time < SLOW_FRAME_THRESHOLD_MS:
        return "normal"
    cache_count = _integer(
        _mapping(frame.get("cache_reads"), "frame cache_reads").get("count"),
        "cache count",
    )
    texture_count = _integer(
        _mapping(frame.get("texture_uploads"), "frame texture_uploads").get("count"),
        "texture count",
    )
    if cache_count and texture_count:
        return "arrival-streaming-and-upload"
    if cache_count:
        return "cache-read"
    if texture_count:
        return "texture-upload"
    return "resident-unexplained"


def _sample_reference(
    samples: Sequence[dict[str, object]],
    times: Sequence[int],
    index: int | None,
    frame_ns: int,
    identifier_name: str,
) -> dict[str, object] | None:
    if index is None:
        return None
    sample = samples[index]
    return {
        "index": index,
        identifier_name: sample.get(identifier_name),
        "signed_delta_ms": (times[index] - frame_ns) / 1_000_000,
    }


def _nearest_index(values: Sequence[int], target: int) -> int | None:
    if not values:
        return None
    right = bisect_left(values, target)
    if right == 0:
        return 0
    if right == len(values):
        return len(values) - 1
    left = right - 1
    if target - values[left] <= values[right] - target:
        return left
    return right


def _utc_at(started_at_utc: str, delta_ns: int) -> str:
    anchor = datetime.fromisoformat(started_at_utc.replace("Z", "+00:00"))
    result = anchor + timedelta(microseconds=delta_ns / 1_000)
    return result.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _mapping_list(value: object, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{name} must be a list of objects")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _optional_number(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ValueError(f"{name} must be a non-negative number or null")
    return float(value)


__all__ = [
    "DIAGNOSTIC_TIMELINE_SCHEMA_VERSION",
    "SLOW_FRAME_THRESHOLD_MS",
    "build_diagnostic_timeline",
]
