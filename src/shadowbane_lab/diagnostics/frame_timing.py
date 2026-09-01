"""Continuous, identity-bound drainage of the renderer present-timing ring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .graphics import load_graphics_runtime_status
from .process import ProcessIdentity

FRAME_TIMING_EVIDENCE_SCHEMA_VERSION = 1
_MAX_CAPTURED_SAMPLES = 2_000_000
_MAX_ANCHORS = 100_000
_MAX_POLL_FAILURE_DETAILS = 64


class FrameTimingCollector:
    """Drain exact QPC present records without allowing an unbounded producer."""

    def __init__(
        self,
        path: Path,
        identity: ProcessIdentity,
        executable_sha256: str,
        candidates: tuple[dict[str, object], ...],
    ) -> None:
        self._path = path
        self._identity = identity
        self._executable_sha256 = executable_sha256
        self._candidates = candidates
        self._frequency_hz: int | None = None
        self._initial_latest_sequence: int | None = None
        self._latest_sequence: int | None = None
        self._next_sequence: int | None = None
        self._initial_query_failures: int | None = None
        self._latest_query_failures: int | None = None
        self._samples: list[tuple[int, int, int]] = []
        self._gaps: list[dict[str, object]] = []
        self._anchors: list[dict[str, object]] = []
        self._query_failure_events: list[tuple[int, int]] = []
        self._sample_drop_events: list[tuple[int, int]] = []
        self._poll_failures: list[tuple[int, str]] = []
        self._poll_failure_count = 0
        self._successful_poll_count = 0

    def poll(self, observed_monotonic_ns: int, observed_at_utc: str) -> None:
        payload = load_graphics_runtime_status(
            self._path,
            self._identity,
            self._executable_sha256,
            self._candidates,
        )
        timing = _mapping(payload.get("frame_timing"), "frame_timing")
        frequency = _positive_integer(timing.get("counter_frequency_hz"), "counter frequency")
        latest = _nonnegative_integer(
            timing.get("latest_present_sequence"),
            "latest present sequence",
        )
        capacity = _positive_integer(timing.get("sample_capacity"), "sample capacity")
        query_failures = _nonnegative_integer(
            timing.get("timing_query_failure_count"),
            "timing query failure count",
        )
        samples = timing.get("samples")
        if not isinstance(samples, list):
            raise ValueError("frame timing samples must be a list")

        if self._frequency_hz is None:
            self._frequency_hz = frequency
            self._initial_latest_sequence = latest
            self._latest_sequence = latest
            self._next_sequence = latest + 1
            self._initial_query_failures = query_failures
            self._latest_query_failures = query_failures
            self._successful_poll_count += 1
            self._append_anchor(timing, observed_monotonic_ns, observed_at_utc)
            return
        if frequency != self._frequency_hz:
            raise ValueError("frame timing counter frequency changed during capture")
        if self._latest_sequence is None or latest < self._latest_sequence:
            raise ValueError("frame timing present sequence regressed during capture")
        if self._latest_query_failures is None or query_failures < self._latest_query_failures:
            raise ValueError("frame timing query failure count regressed during capture")
        if query_failures > self._latest_query_failures:
            self._query_failure_events.append(
                (query_failures - self._latest_query_failures, observed_monotonic_ns)
            )

        next_sequence = self._next_sequence
        if next_sequence is None:
            raise ValueError("frame timing collector was not initialized")
        retained_floor = max(1, latest - capacity + 1)
        if next_sequence < retained_floor:
            self._append_gap(
                next_sequence,
                retained_floor - 1,
                "producer-ring-overwrite",
                observed_monotonic_ns,
            )
            next_sequence = retained_floor

        for item in samples:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or any(isinstance(part, bool) or not isinstance(part, int) for part in item)
            ):
                raise ValueError("frame timing sample must be an integer pair")
            sequence, counter = item
            if sequence < next_sequence:
                continue
            if sequence > next_sequence:
                self._append_gap(
                    next_sequence,
                    sequence - 1,
                    "producer-timing-query-failure",
                    observed_monotonic_ns,
                )
            if len(self._samples) < _MAX_CAPTURED_SAMPLES:
                self._samples.append((sequence, counter, observed_monotonic_ns))
            else:
                self._sample_drop_events.append((1, observed_monotonic_ns))
            next_sequence = sequence + 1
        if next_sequence <= latest:
            self._append_gap(
                next_sequence,
                latest,
                "producer-timing-query-failure",
                observed_monotonic_ns,
            )
            next_sequence = latest + 1

        self._next_sequence = next_sequence
        self._latest_sequence = latest
        self._latest_query_failures = query_failures
        self._successful_poll_count += 1
        self._append_anchor(timing, observed_monotonic_ns, observed_at_utc)

    def record_poll_failure(self, observed_monotonic_ns: int, failure: str) -> None:
        self._poll_failure_count += 1
        if len(self._poll_failures) < _MAX_POLL_FAILURE_DETAILS:
            self._poll_failures.append((observed_monotonic_ns, failure[:2048]))

    def discard_before(self, cutoff_monotonic_ns: int) -> None:
        self._samples = [item for item in self._samples if item[2] >= cutoff_monotonic_ns]
        self._gaps = [
            item for item in self._gaps if int(item["observed_monotonic_ns"]) >= cutoff_monotonic_ns
        ]
        self._query_failure_events = [
            event for event in self._query_failure_events if event[1] >= cutoff_monotonic_ns
        ]
        self._sample_drop_events = [
            event for event in self._sample_drop_events if event[1] >= cutoff_monotonic_ns
        ]
        self._anchors = self._retained_anchors(cutoff_monotonic_ns)

    def as_report(
        self,
        *,
        started_monotonic_ns: int,
        started_at_utc: str,
        ended_monotonic_ns: int,
        ended_at_utc: str,
        retained_cutoff_monotonic_ns: int,
    ) -> dict[str, object]:
        if (
            self._frequency_hz is None
            or self._initial_latest_sequence is None
            or self._latest_sequence is None
            or self._initial_query_failures is None
            or self._latest_query_failures is None
        ):
            raise ValueError("frame timing collector has no accepted producer snapshot")
        samples = [
            [sequence, counter, observed_ns]
            for sequence, counter, observed_ns in self._samples
            if observed_ns >= retained_cutoff_monotonic_ns
        ]
        gaps = [
            dict(item)
            for item in self._gaps
            if int(item["observed_monotonic_ns"]) >= retained_cutoff_monotonic_ns
        ]
        query_failure_delta = sum(
            count
            for count, observed_ns in self._query_failure_events
            if observed_ns >= retained_cutoff_monotonic_ns
        )
        sample_drop_count = sum(
            count
            for count, observed_ns in self._sample_drop_events
            if observed_ns >= retained_cutoff_monotonic_ns
        )
        poll_failures = [
            {
                "observed_monotonic_ns": observed_ns,
                "failure": failure,
            }
            for observed_ns, failure in self._poll_failures
            if observed_ns >= retained_cutoff_monotonic_ns
        ]
        retained_anchors = self._retained_anchors(retained_cutoff_monotonic_ns)
        complete = not (
            gaps
            or query_failure_delta
            or sample_drop_count
            or poll_failures
            or self._poll_failure_count > len(self._poll_failures)
        )
        return {
            "schema_version": FRAME_TIMING_EVIDENCE_SCHEMA_VERSION,
            "producer_id": "wonderbane-extension.graphics",
            "source_path": str(self._path),
            "process_identity": self._identity.as_dict(),
            "executable_sha256": self._executable_sha256,
            "clock": {
                "domain": "windows-query-performance-counter",
                "counter_frequency_hz": self._frequency_hz,
                "anchors": retained_anchors,
            },
            "capture_window": {
                "started_monotonic_ns": started_monotonic_ns,
                "started_at_utc": started_at_utc,
                "ended_monotonic_ns": ended_monotonic_ns,
                "ended_at_utc": ended_at_utc,
                "retained_cutoff_monotonic_ns": retained_cutoff_monotonic_ns,
            },
            "initial_present_sequence": self._initial_latest_sequence,
            "latest_present_sequence": self._latest_sequence,
            "sample_count": len(samples),
            "samples": samples,
            "gaps": gaps,
            "timing_query_failure_count_at_start": self._initial_query_failures,
            "timing_query_failure_count_at_end": self._latest_query_failures,
            "retained_timing_query_failure_delta": query_failure_delta,
            "capture_sample_limit": _MAX_CAPTURED_SAMPLES,
            "capture_sample_drop_count": sample_drop_count,
            "successful_poll_count": self._successful_poll_count,
            "poll_failure_count": self._poll_failure_count,
            "poll_failures": poll_failures,
            "complete": complete,
        }

    def _append_gap(
        self,
        first_sequence: int,
        last_sequence: int,
        reason: str,
        observed_monotonic_ns: int,
    ) -> None:
        if last_sequence < first_sequence:
            return
        if (
            self._gaps
            and self._gaps[-1]["reason"] == reason
            and int(self._gaps[-1]["last_sequence"]) + 1 == first_sequence
        ):
            self._gaps[-1]["last_sequence"] = last_sequence
            self._gaps[-1]["missing_count"] = (
                last_sequence - int(self._gaps[-1]["first_sequence"]) + 1
            )
            self._gaps[-1]["observed_monotonic_ns"] = observed_monotonic_ns
            return
        self._gaps.append(
            {
                "first_sequence": first_sequence,
                "last_sequence": last_sequence,
                "missing_count": last_sequence - first_sequence + 1,
                "reason": reason,
                "observed_monotonic_ns": observed_monotonic_ns,
            }
        )

    def _append_anchor(
        self,
        timing: dict[str, Any],
        observed_monotonic_ns: int,
        observed_at_utc: str,
    ) -> None:
        anchor = {
            "snapshot_counter": timing["snapshot_counter"],
            "snapshot_filetime_utc": timing["snapshot_filetime_utc"],
            "latest_present_sequence": timing["latest_present_sequence"],
            "oldest_available_sequence": timing["oldest_available_sequence"],
            "observed_monotonic_ns": observed_monotonic_ns,
            "observed_at_utc": observed_at_utc,
        }
        identity = tuple(anchor.items())[:4]
        if self._anchors and tuple(self._anchors[-1].items())[:4] == identity:
            return
        if len(self._anchors) >= _MAX_ANCHORS:
            raise ValueError("frame timing clock anchor limit exceeded")
        self._anchors.append(anchor)

    def _retained_anchors(self, cutoff_ns: int) -> list[dict[str, object]]:
        before = [item for item in self._anchors if int(item["observed_monotonic_ns"]) < cutoff_ns]
        retained = [
            dict(item) for item in self._anchors if int(item["observed_monotonic_ns"]) >= cutoff_ns
        ]
        if before:
            retained.insert(0, dict(before[-1]))
        return retained


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


__all__ = [
    "FRAME_TIMING_EVIDENCE_SCHEMA_VERSION",
    "FrameTimingCollector",
]
