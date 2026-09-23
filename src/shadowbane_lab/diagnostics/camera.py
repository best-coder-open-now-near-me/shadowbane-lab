"""Bounded drainage of exact-process renderer camera-state telemetry."""

from __future__ import annotations

from math import isfinite, sqrt
from pathlib import Path
from typing import Any, cast

from .graphics import load_graphics_runtime_status
from .process import ProcessIdentity

CAMERA_STATE_EVIDENCE_SCHEMA_VERSION = 1
CAMERA_STATE_PRODUCER_SCHEMA_VERSION = 1
_MAX_CAPTURED_SAMPLES = 250_000
_MAX_POLL_FAILURE_DETAILS = 64
_MAX_TEXT = 256


class CameraStateCollector:
    """Drain a bounded renderer ring and stamp it on the diagnostics session clock."""

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
        self._source: str | None = None
        self._mapping_authority: str | None = None
        self._initial_latest_sequence: int | None = None
        self._latest_sequence: int | None = None
        self._next_sequence: int | None = None
        self._initial_producer_drop_count: int | None = None
        self._latest_producer_drop_count: int | None = None
        self._samples: list[dict[str, object]] = []
        self._gaps: list[dict[str, object]] = []
        self._producer_drop_events: list[tuple[int, int]] = []
        self._capture_drop_events: list[tuple[int, int]] = []
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
        camera = _camera_state(payload.get("camera_state"), payload.get("frame_timing"))
        frequency = camera["counter_frequency_hz"]
        latest = camera["latest_sample_sequence"]
        capacity = camera["sample_capacity"]
        producer_drops = camera["producer_drop_count"]
        samples = camera["samples"]
        frequency = cast(int, frequency)
        latest = cast(int, latest)
        capacity = cast(int, capacity)
        producer_drops = cast(int, producer_drops)
        samples = cast(list[dict[str, object]], samples)

        if self._frequency_hz is None:
            self._frequency_hz = frequency
            self._source = str(camera["source"])
            self._mapping_authority = str(camera["mapping_authority"])
            self._initial_latest_sequence = latest
            self._latest_sequence = latest
            self._next_sequence = latest + 1
            self._initial_producer_drop_count = producer_drops
            self._latest_producer_drop_count = producer_drops
            self._successful_poll_count += 1
            return
        else:
            if frequency != self._frequency_hz:
                raise ValueError("camera-state counter frequency changed during capture")
            if camera["source"] != self._source:
                raise ValueError("camera-state source changed during capture")
            if camera["mapping_authority"] != self._mapping_authority:
                raise ValueError("camera-state mapping authority changed during capture")
            if self._latest_sequence is None or latest < self._latest_sequence:
                raise ValueError("camera-state sample sequence regressed during capture")
            if (
                self._latest_producer_drop_count is None
                or producer_drops < self._latest_producer_drop_count
            ):
                raise ValueError("camera-state producer drop count regressed during capture")
            if producer_drops > self._latest_producer_drop_count:
                self._producer_drop_events.append(
                    (producer_drops - self._latest_producer_drop_count, observed_monotonic_ns)
                )

        next_sequence = self._next_sequence
        if next_sequence is None:
            raise ValueError("camera-state collector was not initialized")
        retained_floor = max(1, latest - capacity + 1)
        if next_sequence < retained_floor:
            self._append_gap(
                next_sequence,
                retained_floor - 1,
                "producer-ring-overwrite",
                observed_monotonic_ns,
            )
            next_sequence = retained_floor
        for sample in samples:
            sequence = int(sample["sequence"])
            if sequence < next_sequence:
                continue
            if sequence > next_sequence:
                self._append_gap(
                    next_sequence,
                    sequence - 1,
                    "producer-sample-gap",
                    observed_monotonic_ns,
                )
            if len(self._samples) < _MAX_CAPTURED_SAMPLES:
                self._samples.append(
                    {
                        **sample,
                        "observed_monotonic_ns": observed_monotonic_ns,
                        "observed_at_utc": observed_at_utc,
                    }
                )
            else:
                self._capture_drop_events.append((1, observed_monotonic_ns))
            next_sequence = sequence + 1
        if next_sequence <= latest:
            self._append_gap(
                next_sequence,
                latest,
                "producer-sample-gap",
                observed_monotonic_ns,
            )
            next_sequence = latest + 1
        self._next_sequence = next_sequence
        self._latest_sequence = latest
        self._latest_producer_drop_count = producer_drops
        self._successful_poll_count += 1

    def record_poll_failure(self, observed_monotonic_ns: int, failure: str) -> None:
        self._poll_failure_count += 1
        if len(self._poll_failures) < _MAX_POLL_FAILURE_DETAILS:
            self._poll_failures.append((observed_monotonic_ns, failure[:2048]))

    def discard_before(self, cutoff_monotonic_ns: int) -> None:
        self._samples = [
            item
            for item in self._samples
            if int(item["observed_monotonic_ns"]) >= cutoff_monotonic_ns
        ]
        self._gaps = [
            item for item in self._gaps if int(item["observed_monotonic_ns"]) >= cutoff_monotonic_ns
        ]
        self._producer_drop_events = [
            event for event in self._producer_drop_events if event[1] >= cutoff_monotonic_ns
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
            or self._source is None
            or self._mapping_authority is None
            or self._initial_latest_sequence is None
            or self._latest_sequence is None
            or self._initial_producer_drop_count is None
            or self._latest_producer_drop_count is None
        ):
            raise ValueError("camera-state collector has no accepted producer snapshot")
        samples = [
            dict(item)
            for item in self._samples
            if int(item["observed_monotonic_ns"]) >= retained_cutoff_monotonic_ns
        ]
        gaps = [
            dict(item)
            for item in self._gaps
            if int(item["observed_monotonic_ns"]) >= retained_cutoff_monotonic_ns
        ]
        producer_drop_delta = sum(
            count
            for count, observed_ns in self._producer_drop_events
            if observed_ns >= retained_cutoff_monotonic_ns
        )
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
        complete = bool(samples) and not (
            gaps
            or producer_drop_delta
            or capture_drop_count
            or poll_failures
            or self._poll_failure_count > len(self._poll_failures)
        )
        return {
            "schema_version": CAMERA_STATE_EVIDENCE_SCHEMA_VERSION,
            "producer_id": "wonderbane-extension.graphics",
            "source_path": str(self._path),
            "process_identity": self._identity.as_dict(),
            "executable_sha256": self._executable_sha256,
            "source": self._source,
            "mapping_authority": self._mapping_authority,
            "clock": {
                "domain": "windows-query-performance-counter",
                "counter_frequency_hz": self._frequency_hz,
            },
            "capture_window": {
                "started_monotonic_ns": started_monotonic_ns,
                "started_at_utc": started_at_utc,
                "ended_monotonic_ns": ended_monotonic_ns,
                "ended_at_utc": ended_at_utc,
                "retained_cutoff_monotonic_ns": retained_cutoff_monotonic_ns,
            },
            "initial_sample_sequence": self._initial_latest_sequence,
            "latest_sample_sequence": self._latest_sequence,
            "sample_count": len(samples),
            "samples": samples,
            "gaps": gaps,
            "producer_drop_count_at_start": self._initial_producer_drop_count,
            "producer_drop_count_at_end": self._latest_producer_drop_count,
            "retained_producer_drop_delta": producer_drop_delta,
            "capture_sample_limit": _MAX_CAPTURED_SAMPLES,
            "capture_sample_drop_count": capture_drop_count,
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


def _camera_state(value: object, frame_timing_value: object) -> dict[str, object]:
    camera = _mapping(value, "camera_state")
    if camera.get("schema_version") != CAMERA_STATE_PRODUCER_SCHEMA_VERSION:
        raise ValueError("camera_state producer schema is unsupported")
    if camera.get("clock") != "windows-query-performance-counter":
        raise ValueError("camera_state clock is unsupported")
    frequency = _positive_integer(camera.get("counter_frequency_hz"), "camera frequency")
    if frequency > 1_000_000_000_000:
        raise ValueError("camera_state counter frequency is outside the bounded range")
    frame_timing = _mapping(frame_timing_value, "frame_timing")
    frame_frequency = _positive_integer(
        frame_timing.get("counter_frequency_hz"), "frame timing frequency"
    )
    if frame_frequency != frequency:
        raise ValueError("camera_state and frame_timing counter frequencies differ")
    latest_present_sequence = _nonnegative_integer(
        frame_timing.get("latest_present_sequence"), "latest present sequence"
    )
    snapshot_counter = _positive_integer(
        frame_timing.get("snapshot_counter"), "frame timing snapshot counter"
    )
    source = camera.get("source")
    if not _bounded_text(source):
        raise ValueError("camera_state source must be bounded non-empty text")
    if camera.get("mapping_authority") != "runtime-observed-fixed-function-state":
        raise ValueError("camera_state mapping authority is unsupported")
    latest = _nonnegative_integer(
        camera.get("latest_sample_sequence"), "camera latest sample sequence"
    )
    oldest = _nonnegative_integer(
        camera.get("oldest_available_sequence"), "camera oldest sample sequence"
    )
    capacity = _positive_integer(camera.get("sample_capacity"), "camera sample capacity")
    if capacity > 1_000_000:
        raise ValueError("camera_state sample capacity is outside the bounded range")
    count = _nonnegative_integer(camera.get("sample_count"), "camera sample count")
    drops = _nonnegative_integer(camera.get("producer_drop_count"), "camera producer drops")
    raw_samples = camera.get("samples")
    if not isinstance(raw_samples, list) or len(raw_samples) > capacity:
        raise ValueError("camera_state samples must be a capacity-bounded list")
    if count != len(raw_samples):
        raise ValueError("camera_state sample_count does not match samples")
    samples: list[dict[str, object]] = []
    previous = 0
    previous_counter = 0
    for raw in raw_samples:
        sample = _camera_sample(raw, latest_present_sequence, snapshot_counter)
        sequence = int(sample["sequence"])
        counter = int(sample["counter"])
        if sequence <= previous or sequence > latest or counter <= previous_counter:
            raise ValueError("camera_state sample sequences and counters are not strictly ordered")
        samples.append(sample)
        previous = sequence
        previous_counter = counter
    if samples:
        if oldest != samples[0]["sequence"]:
            raise ValueError("camera_state oldest sequence does not match samples")
        if latest != samples[-1]["sequence"]:
            raise ValueError("camera_state latest sequence does not match samples")
    elif oldest != 0 or latest != 0:
        raise ValueError("camera_state empty ring must use zero sequence bounds")
    return {
        "counter_frequency_hz": frequency,
        "latest_sample_sequence": latest,
        "mapping_authority": camera["mapping_authority"],
        "producer_drop_count": drops,
        "sample_capacity": capacity,
        "samples": samples,
        "source": source,
    }


def _camera_sample(
    value: object,
    latest_present_sequence: int,
    snapshot_counter: int,
) -> dict[str, object]:
    sample = _mapping(value, "camera sample")
    expected = {
        "sequence",
        "present_sequence",
        "counter",
        "position",
        "forward",
        "up",
        "zoom",
        "vertical_fov_degrees",
        "view_matrix",
        "projection_matrix",
        "viewport",
    }
    if set(sample) != expected:
        raise ValueError("camera sample fields are not exact")
    sequence = _positive_integer(sample.get("sequence"), "camera sequence")
    present_sequence = _positive_integer(
        sample.get("present_sequence"), "camera present sequence"
    )
    counter = _positive_integer(sample.get("counter"), "camera counter")
    if present_sequence > latest_present_sequence:
        raise ValueError("camera present sequence exceeds the producer snapshot")
    if counter > snapshot_counter:
        raise ValueError("camera counter exceeds the producer snapshot anchor")
    position = _finite_vector(sample.get("position"), 3, "camera position")
    forward = _finite_vector(sample.get("forward"), 3, "camera forward")
    norm = sqrt(sum(component * component for component in forward))
    if not 0.999 <= norm <= 1.001:
        raise ValueError("camera forward vector must be normalized")
    up = _finite_vector(sample.get("up"), 3, "camera up")
    up_norm = sqrt(sum(component * component for component in up))
    if not 0.999 <= up_norm <= 1.001:
        raise ValueError("camera up vector must be normalized")
    if abs(sum(left * right for left, right in zip(forward, up, strict=True))) > 0.001:
        raise ValueError("camera forward and up vectors must be orthogonal")
    zoom = sample.get("zoom")
    if (
        isinstance(zoom, bool)
        or not isinstance(zoom, int | float)
        or not isfinite(zoom)
        or not 0 < float(zoom) <= 1_000_000
    ):
        raise ValueError("camera zoom must be finite, positive, and bounded")
    vertical_fov = sample.get("vertical_fov_degrees")
    if (
        isinstance(vertical_fov, bool)
        or not isinstance(vertical_fov, int | float)
        or not isfinite(vertical_fov)
        or not 0 < float(vertical_fov) < 180
    ):
        raise ValueError("camera vertical FOV must be finite and in 0-180 degrees")
    view = _finite_vector(sample.get("view_matrix"), 16, "camera view matrix")
    projection = _finite_vector(
        sample.get("projection_matrix"), 16, "camera projection matrix"
    )
    viewport = sample.get("viewport")
    if (
        not isinstance(viewport, list)
        or len(viewport) != 4
        or any(isinstance(item, bool) or not isinstance(item, int) for item in viewport)
        or viewport[2] <= 0
        or viewport[3] <= 0
    ):
        raise ValueError("camera viewport must be x,y,width,height")
    return {
        "sequence": sequence,
        "present_sequence": present_sequence,
        "counter": counter,
        "position": position,
        "forward": forward,
        "up": up,
        "zoom": float(zoom),
        "vertical_fov_degrees": float(vertical_fov),
        "view_matrix": view,
        "projection_matrix": projection,
        "viewport": list(viewport),
    }


def _finite_vector(value: object, length: int, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{name} must contain exactly {length} values")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float) or not isfinite(item):
            raise ValueError(f"{name} values must be finite numbers")
        if abs(float(item)) > 1_000_000_000:
            raise ValueError(f"{name} values are outside the bounded range")
        result.append(float(item))
    return result


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


def _bounded_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value and len(value) <= _MAX_TEXT


__all__ = [
    "CAMERA_STATE_EVIDENCE_SCHEMA_VERSION",
    "CAMERA_STATE_PRODUCER_SCHEMA_VERSION",
    "CameraStateCollector",
]
