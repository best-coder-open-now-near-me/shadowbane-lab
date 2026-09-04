"""Synchronized capture records and producer-health accounting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from shadowbane_lab.evidence.model import parse_artifact_id
from shadowbane_lab.integrity import (
    canonical_json_sha256,
    create_only_json,
    load_strict_json,
    validate_finite_json,
    validate_identifier,
)

from .model import CaseError, _timestamp

CAPTURE_RECORD_SCHEMA_VERSION = 1
CAPTURE_STREAM_SCHEMA_VERSION = 1


class CaptureRecordKind(StrEnum):
    MARKER = "marker"
    OBSERVATION = "observation"
    EVENT = "event"
    ARTIFACT_REFERENCE = "artifact_reference"
    PRODUCER_HEALTH = "producer_health"


class CaptureQuality(StrEnum):
    DROPPED = "dropped"
    PARTIAL = "partial"
    DELAYED = "delayed"
    RECONSTRUCTED = "reconstructed"


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    run_id: str
    channel_id: str
    producer_id: str
    producer_version: str
    clock_domain_id: str
    monotonic_ns: int
    utc_uncertainty_ns: int
    captured_at_utc: str
    producer_sequence: int
    kind: CaptureRecordKind
    payload: tuple[tuple[str, Any], ...] = ()
    correlation_id: str | None = None
    artifact_id: str | None = None
    quality: tuple[CaptureQuality, ...] = ()
    record_id: str | None = None
    schema_version: int = CAPTURE_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CAPTURE_RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported capture record schema version")
        for value, name in (
            (self.run_id, "run_id"),
            (self.channel_id, "channel_id"),
            (self.producer_id, "producer_id"),
            (self.clock_domain_id, "clock_domain_id"),
        ):
            validate_identifier(value, name)
        if not self.producer_version or len(self.producer_version) > 256:
            raise ValueError("producer_version must be bounded non-empty text")
        if (
            isinstance(self.monotonic_ns, bool)
            or not isinstance(self.monotonic_ns, int)
            or self.monotonic_ns < 0
        ):
            raise ValueError("monotonic_ns must be a non-negative integer")
        if (
            isinstance(self.utc_uncertainty_ns, bool)
            or not isinstance(self.utc_uncertainty_ns, int)
            or not 0 <= self.utc_uncertainty_ns <= 86_400_000_000_000
        ):
            raise ValueError("utc_uncertainty_ns must be a bounded non-negative integer")
        _timestamp(self.captured_at_utc, "captured_at_utc")
        if (
            isinstance(self.producer_sequence, bool)
            or not isinstance(self.producer_sequence, int)
            or not 1 <= self.producer_sequence <= 0x7FFFFFFFFFFFFFFF
        ):
            raise ValueError("producer_sequence must be a positive bounded integer")
        if not isinstance(self.kind, CaptureRecordKind):
            raise ValueError("capture record kind is invalid")
        names = tuple(name for name, _ in self.payload)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("capture payload must use unique canonical keys")
        for _, value in self.payload:
            validate_finite_json(value)
        if self.correlation_id is not None:
            validate_identifier(self.correlation_id, "correlation_id")
        if self.artifact_id is not None:
            parse_artifact_id(self.artifact_id)
        if self.kind is CaptureRecordKind.ARTIFACT_REFERENCE and self.artifact_id is None:
            raise ValueError("artifact-reference record requires artifact_id")
        if self.kind is not CaptureRecordKind.ARTIFACT_REFERENCE and self.artifact_id is not None:
            raise ValueError("only artifact-reference records may carry artifact_id")
        quality_values = tuple(item.value for item in self.quality)
        if quality_values != tuple(sorted(set(quality_values))):
            raise ValueError("capture quality must use unique canonical ordering")
        expected = f"sha256:{canonical_json_sha256(self.content_dict())}"
        if self.record_id is None:
            object.__setattr__(self, "record_id", expected)
        elif self.record_id != expected:
            raise ValueError("record_id does not match canonical capture content")

    def content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "channel_id": self.channel_id,
            "producer_id": self.producer_id,
            "producer_version": self.producer_version,
            "clock_domain_id": self.clock_domain_id,
            "monotonic_ns": self.monotonic_ns,
            "utc_uncertainty_ns": self.utc_uncertainty_ns,
            "captured_at_utc": self.captured_at_utc,
            "producer_sequence": self.producer_sequence,
            "correlation_id": self.correlation_id,
            "kind": self.kind.value,
            "payload": {name: value for name, value in self.payload},
            "artifact_id": self.artifact_id,
            "quality": [item.value for item in self.quality],
        }

    def as_dict(self) -> dict[str, object]:
        return {"record_id": self.record_id, **self.content_dict()}


@dataclass(frozen=True, slots=True)
class ProducerHealth:
    run_id: str
    producer_id: str
    clock_domain_id: str
    channel_ids: tuple[str, ...]
    received_records: int
    reported_drops: int
    sequence_gaps: int
    partial_records: int
    delayed_records: int
    first_monotonic_ns: int | None
    last_monotonic_ns: int | None

    @property
    def healthy(self) -> bool:
        return not (self.reported_drops or self.sequence_gaps or self.partial_records)

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "producer_id": self.producer_id,
            "clock_domain_id": self.clock_domain_id,
            "channel_ids": list(self.channel_ids),
            "received_records": self.received_records,
            "reported_drops": self.reported_drops,
            "sequence_gaps": self.sequence_gaps,
            "partial_records": self.partial_records,
            "delayed_records": self.delayed_records,
            "first_monotonic_ns": self.first_monotonic_ns,
            "last_monotonic_ns": self.last_monotonic_ns,
            "healthy": self.healthy,
        }


def producer_health(records: tuple[CaptureRecord, ...]) -> tuple[ProducerHealth, ...]:
    if not records:
        return ()
    run_ids = {item.run_id for item in records}
    if len(run_ids) != 1:
        raise CaseError("producer health requires records from exactly one run")
    grouped: dict[tuple[str, str], list[CaptureRecord]] = {}
    for record in records:
        grouped.setdefault((record.producer_id, record.clock_domain_id), []).append(record)
    health: list[ProducerHealth] = []
    for (producer_id, clock_domain_id), values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda item: item.producer_sequence)
        sequences = [item.producer_sequence for item in ordered]
        gaps = sum(
            max(0, current - previous - 1)
            for previous, current in zip(sequences, sequences[1:], strict=False)
        )
        monotonic = [item.monotonic_ns for item in ordered]
        if monotonic != sorted(monotonic):
            gaps += 1
        health.append(
            ProducerHealth(
                run_id=ordered[0].run_id,
                producer_id=producer_id,
                clock_domain_id=clock_domain_id,
                channel_ids=tuple(sorted({item.channel_id for item in ordered})),
                received_records=len(ordered),
                reported_drops=sum(CaptureQuality.DROPPED in item.quality for item in ordered),
                sequence_gaps=gaps,
                partial_records=sum(CaptureQuality.PARTIAL in item.quality for item in ordered),
                delayed_records=sum(CaptureQuality.DELAYED in item.quality for item in ordered),
                first_monotonic_ns=min(monotonic),
                last_monotonic_ns=max(monotonic),
            )
        )
    return tuple(health)


def completed_capture_channels(records: tuple[CaptureRecord, ...]) -> tuple[str, ...]:
    health = producer_health(records)
    unhealthy = {
        (item.producer_id, item.clock_domain_id) for item in health if not item.healthy
    }
    return tuple(
        sorted(
            {
                record.channel_id
                for record in records
                if (record.producer_id, record.clock_domain_id) not in unhealthy
                and not record.quality
            }
        )
    )


def save_capture_records(path: str | Path, records: tuple[CaptureRecord, ...]) -> None:
    _validate_stream(records)
    try:
        create_only_json(
            Path(path),
            {
                "schema_version": CAPTURE_STREAM_SCHEMA_VERSION,
                "records": [item.as_dict() for item in records],
                "producer_health": [item.as_dict() for item in producer_health(records)],
            },
            make_parents=True,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CaseError(f"could not save capture records: {exc}") from exc


def load_capture_records(path: str | Path) -> tuple[CaptureRecord, ...]:
    try:
        value = load_strict_json(Path(path))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CaseError(f"could not load capture records: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "records",
        "producer_health",
    }:
        raise CaseError("capture stream fields are not exact")
    if value["schema_version"] != CAPTURE_STREAM_SCHEMA_VERSION:
        raise CaseError("unsupported capture stream schema version")
    if not isinstance(value["records"], list) or not isinstance(value["producer_health"], list):
        raise CaseError("capture stream records and health must be arrays")
    records = tuple(parse_capture_record(item) for item in value["records"])
    expected_health = [item.as_dict() for item in producer_health(records)]
    if value["producer_health"] != expected_health:
        raise CaseError("capture stream producer health does not match records")
    _validate_stream(records)
    return records


def parse_capture_record(payload: object) -> CaptureRecord:
    if not isinstance(payload, dict):
        raise CaseError("capture record must be an object")
    expected = {
        "schema_version",
        "record_id",
        "run_id",
        "channel_id",
        "producer_id",
        "producer_version",
        "clock_domain_id",
        "monotonic_ns",
        "utc_uncertainty_ns",
        "captured_at_utc",
        "producer_sequence",
        "correlation_id",
        "kind",
        "payload",
        "artifact_id",
        "quality",
    }
    if set(payload) != expected:
        raise CaseError("capture record fields are not exact")
    values = payload["payload"]
    quality = payload["quality"]
    if not isinstance(values, dict) or not isinstance(quality, list):
        raise CaseError("capture payload must be an object and quality must be an array")
    try:
        return CaptureRecord(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            record_id=payload["record_id"],  # type: ignore[arg-type]
            run_id=payload["run_id"],  # type: ignore[arg-type]
            channel_id=payload["channel_id"],  # type: ignore[arg-type]
            producer_id=payload["producer_id"],  # type: ignore[arg-type]
            producer_version=payload["producer_version"],  # type: ignore[arg-type]
            clock_domain_id=payload["clock_domain_id"],  # type: ignore[arg-type]
            monotonic_ns=payload["monotonic_ns"],  # type: ignore[arg-type]
            utc_uncertainty_ns=payload["utc_uncertainty_ns"],  # type: ignore[arg-type]
            captured_at_utc=payload["captured_at_utc"],  # type: ignore[arg-type]
            producer_sequence=payload["producer_sequence"],  # type: ignore[arg-type]
            correlation_id=payload["correlation_id"],  # type: ignore[arg-type]
            kind=CaptureRecordKind(payload["kind"]),  # type: ignore[arg-type]
            payload=tuple(sorted(values.items())),
            artifact_id=payload["artifact_id"],  # type: ignore[arg-type]
            quality=tuple(CaptureQuality(item) for item in quality),
        )
    except (TypeError, ValueError) as exc:
        raise CaseError(f"invalid capture record: {exc}") from exc


def _validate_stream(records: tuple[CaptureRecord, ...]) -> None:
    if not records or len(records) > 1_000_000:
        raise CaseError("capture stream requires 1-1000000 records")
    run_ids = {item.run_id for item in records}
    if len(run_ids) != 1:
        raise CaseError("capture stream must contain exactly one run")
    record_ids = tuple(item.record_id for item in records)
    if len(record_ids) != len(set(record_ids)):
        raise CaseError("capture stream contains duplicate records")


__all__ = [
    "CAPTURE_RECORD_SCHEMA_VERSION",
    "CaptureQuality",
    "CaptureRecord",
    "CaptureRecordKind",
    "ProducerHealth",
    "completed_capture_channels",
    "load_capture_records",
    "parse_capture_record",
    "producer_health",
    "save_capture_records",
]
