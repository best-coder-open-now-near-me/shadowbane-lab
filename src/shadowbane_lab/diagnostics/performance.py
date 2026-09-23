"""Bounded drainage of exact-process aggregate performance telemetry."""

from __future__ import annotations

from typing import Protocol

from shadowbane_lab.client_extension.performance import (
    PERFORMANCE_AGGREGATE_CAPABILITY,
    PERFORMANCE_TELEMETRY_CAPACITY,
    PERFORMANCE_TELEMETRY_HOOK_COUNT,
    PerformanceRecordKind,
    PerformanceTelemetryHeader,
    PerformanceTelemetrySnapshot,
)
from shadowbane_lab.client_extension.performance_reader import (
    open_windows_performance_telemetry_reader,
)

from .process import ProcessIdentity

PERFORMANCE_EVIDENCE_SCHEMA_VERSION = 1
_MAX_CAPTURED_FRAMES = 1_000_000
_MAX_POLL_FAILURE_DETAILS = 64


class PerformanceSnapshotSource(Protocol):
    def snapshot(self) -> PerformanceTelemetrySnapshot: ...


def open_performance_snapshot_source(
    identity: ProcessIdentity,
) -> PerformanceSnapshotSource:
    return open_windows_performance_telemetry_reader(
        identity.process_id,
        identity.process_creation_filetime_utc,
    )


class PerformanceFrameCollector:
    """Drain one bounded native frame ring without retaining per-operation events."""

    def __init__(
        self,
        identity: ProcessIdentity,
        source: PerformanceSnapshotSource,
    ) -> None:
        self._identity = identity
        self._source = source
        self._frequency_hz: int | None = None
        self._initial_header: PerformanceTelemetryHeader | None = None
        self._latest_header: PerformanceTelemetryHeader | None = None
        self._next_sequence: int | None = None
        self._frames: list[dict[str, object]] = []
        self._gaps: list[dict[str, object]] = []
        self._capture_drop_events: list[tuple[int, int]] = []
        self._poll_failures: list[tuple[int, str]] = []
        self._poll_failure_count = 0
        self._successful_poll_count = 0

    @property
    def initialized(self) -> bool:
        return self._initial_header is not None

    def poll(self, observed_monotonic_ns: int, observed_at_utc: str) -> None:
        snapshot = self._source.snapshot()
        header = snapshot.header
        self._validate_header(header)
        if self._frequency_hz is None:
            self._frequency_hz = header.qpc_frequency
            self._initial_header = header
            self._latest_header = header
            self._next_sequence = header.write_sequence + 1
            self._successful_poll_count += 1
            return

        previous = self._latest_header
        if previous is None or self._next_sequence is None:
            raise ValueError("performance collector was not initialized")
        if header.qpc_frequency != self._frequency_hz:
            raise ValueError("performance counter frequency changed during capture")
        for current, prior, name in (
            (header.write_sequence, previous.write_sequence, "write_sequence"),
            (header.frame_count, previous.frame_count, "frame_count"),
            (header.slow_frame_count, previous.slow_frame_count, "slow_frame_count"),
            (header.cache_read_count, previous.cache_read_count, "cache_read_count"),
            (header.cache_read_bytes, previous.cache_read_bytes, "cache_read_bytes"),
            (
                header.texture_upload_count,
                previous.texture_upload_count,
                "texture_upload_count",
            ),
            (
                header.texture_upload_bytes,
                previous.texture_upload_bytes,
                "texture_upload_bytes",
            ),
        ):
            if current < prior:
                raise ValueError(f"performance {name} regressed during capture")

        next_sequence = self._next_sequence
        retained_floor = max(1, header.write_sequence - PERFORMANCE_TELEMETRY_CAPACITY + 1)
        if next_sequence < retained_floor:
            self._append_gap(
                next_sequence,
                retained_floor - 1,
                "producer-ring-overwrite",
                observed_monotonic_ns,
            )
            next_sequence = retained_floor
        for record in snapshot.records:
            if record.sequence < next_sequence:
                continue
            if record.sequence > next_sequence:
                self._append_gap(
                    next_sequence,
                    record.sequence - 1,
                    "producer-sequence-gap",
                    observed_monotonic_ns,
                )
            if record.kind is not PerformanceRecordKind.FRAME_SUMMARY:
                raise ValueError("aggregate performance snapshot contains a detailed event")
            if len(self._frames) < _MAX_CAPTURED_FRAMES:
                frame = record.as_dict(header)
                frame.update(
                    {
                        "started_qpc": record.started_qpc,
                        "frame_monotonic_ns": (
                            record.started_qpc * 1_000_000_000 // header.qpc_frequency
                        ),
                        "observed_monotonic_ns": observed_monotonic_ns,
                        "observed_at_utc": observed_at_utc,
                    }
                )
                self._frames.append(frame)
            else:
                self._capture_drop_events.append((1, observed_monotonic_ns))
            next_sequence = record.sequence + 1
        if next_sequence <= header.write_sequence:
            self._append_gap(
                next_sequence,
                header.write_sequence,
                "producer-sequence-gap",
                observed_monotonic_ns,
            )
            next_sequence = header.write_sequence + 1
        self._next_sequence = next_sequence
        self._latest_header = header
        self._successful_poll_count += 1

    def record_poll_failure(self, observed_monotonic_ns: int, failure: str) -> None:
        self._poll_failure_count += 1
        if len(self._poll_failures) < _MAX_POLL_FAILURE_DETAILS:
            self._poll_failures.append((observed_monotonic_ns, failure[:2048]))

    def discard_before(self, cutoff_monotonic_ns: int) -> None:
        self._frames = [
            frame
            for frame in self._frames
            if int(frame["observed_monotonic_ns"]) >= cutoff_monotonic_ns
        ]
        self._gaps = [
            gap for gap in self._gaps if int(gap["observed_monotonic_ns"]) >= cutoff_monotonic_ns
        ]
        self._capture_drop_events = [
            event for event in self._capture_drop_events if event[1] >= cutoff_monotonic_ns
        ]

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
            or self._initial_header is None
            or self._latest_header is None
        ):
            raise ValueError("performance collector has no accepted producer snapshot")
        frames = [
            dict(frame)
            for frame in self._frames
            if int(frame["observed_monotonic_ns"]) >= retained_cutoff_monotonic_ns
        ]
        gaps = [
            dict(gap)
            for gap in self._gaps
            if int(gap["observed_monotonic_ns"]) >= retained_cutoff_monotonic_ns
        ]
        capture_drop_count = sum(
            count
            for count, observed_ns in self._capture_drop_events
            if observed_ns >= retained_cutoff_monotonic_ns
        )
        poll_failures = [
            {"observed_monotonic_ns": observed_ns, "failure": failure}
            for observed_ns, failure in self._poll_failures
            if observed_ns >= retained_cutoff_monotonic_ns
        ]
        complete = bool(frames) and not (
            gaps
            or capture_drop_count
            or poll_failures
            or self._poll_failure_count > len(self._poll_failures)
            or self._latest_header.producer_error
        )
        return {
            "schema_version": PERFORMANCE_EVIDENCE_SCHEMA_VERSION,
            "producer_id": "wonderbane-extension.performance",
            "process_identity": self._identity.as_dict(),
            "clock": {
                "domain": "windows-query-performance-counter",
                "counter_frequency_hz": self._frequency_hz,
                "session_monotonic_mapping": "windows-qpc-shared-source",
            },
            "capture_window": {
                "started_monotonic_ns": started_monotonic_ns,
                "started_at_utc": started_at_utc,
                "ended_monotonic_ns": ended_monotonic_ns,
                "ended_at_utc": ended_at_utc,
                "retained_cutoff_monotonic_ns": retained_cutoff_monotonic_ns,
            },
            "initial_header": self._initial_header.as_dict(),
            "latest_header": self._latest_header.as_dict(),
            "frame_count": len(frames),
            "frames": frames,
            "gaps": gaps,
            "capture_frame_limit": _MAX_CAPTURED_FRAMES,
            "capture_frame_drop_count": capture_drop_count,
            "successful_poll_count": self._successful_poll_count,
            "poll_failure_count": self._poll_failure_count,
            "poll_failures": poll_failures,
            "complete": complete,
        }

    def _validate_header(self, header: PerformanceTelemetryHeader) -> None:
        if (
            header.process_id != self._identity.process_id
            or header.process_creation_filetime_utc
            != self._identity.process_creation_filetime_utc
        ):
            raise ValueError("performance telemetry belongs to another process lifetime")
        if header.capability_flags != PERFORMANCE_AGGREGATE_CAPABILITY:
            raise ValueError("performance telemetry is not using the aggregate profile")
        if header.active_hook_count != PERFORMANCE_TELEMETRY_HOOK_COUNT:
            raise ValueError("performance aggregate hook set is incomplete")
        if header.producer_error:
            raise ValueError(f"performance producer error is {header.producer_error}")

    def _append_gap(
        self,
        first_sequence: int,
        last_sequence: int,
        reason: str,
        observed_monotonic_ns: int,
    ) -> None:
        if last_sequence < first_sequence:
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


__all__ = [
    "PERFORMANCE_EVIDENCE_SCHEMA_VERSION",
    "PerformanceFrameCollector",
    "PerformanceSnapshotSource",
    "open_performance_snapshot_source",
]
