"""Deterministic semantic trace alignment with explicit ambiguity findings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.integrity import canonical_json_sha256, create_only_json

from .capture import CaptureRecord, CaptureRecordKind
from .model import CaseError

SEMANTIC_TRACE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SemanticTrace:
    run_id: str
    records: tuple[tuple[str, object], ...]
    findings: tuple[str, ...]
    source_record_ids: tuple[str, ...]
    trace_id: str | None = None
    schema_version: int = SEMANTIC_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_TRACE_SCHEMA_VERSION:
            raise ValueError("unsupported semantic trace schema version")
        if self.findings != tuple(sorted(set(self.findings))):
            raise ValueError("trace findings must use canonical ordering")
        if self.source_record_ids != tuple(sorted(set(self.source_record_ids))):
            raise ValueError("source record IDs must use canonical ordering")
        expected = f"sha256:{canonical_json_sha256(self.content_dict())}"
        if self.trace_id is None:
            object.__setattr__(self, "trace_id", expected)
        elif self.trace_id != expected:
            raise ValueError("trace_id does not match semantic trace content")

    def content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "records": [dict(item) for item in self.records],
            "findings": list(self.findings),
            "source_record_ids": list(self.source_record_ids),
        }

    def as_dict(self) -> dict[str, object]:
        return {"trace_id": self.trace_id, **self.content_dict()}


def align_capture_records(records: tuple[CaptureRecord, ...]) -> SemanticTrace:
    if not records:
        raise CaseError("cannot align an empty capture")
    run_ids = {item.run_id for item in records}
    if len(run_ids) != 1:
        raise CaseError("semantic trace requires exactly one run")
    ordered = tuple(
        sorted(
            records,
            key=lambda item: (
                item.clock_domain_id,
                item.monotonic_ns,
                item.producer_id,
                item.producer_sequence,
                item.record_id or "",
            ),
        )
    )
    domain_origins = {
        domain_id: min(
            item.monotonic_ns for item in ordered if item.clock_domain_id == domain_id
        )
        for domain_id in sorted({item.clock_domain_id for item in ordered})
    }
    marker_correlations = {
        item.correlation_id
        for item in ordered
        if item.kind is CaptureRecordKind.MARKER and item.correlation_id is not None
    }
    findings: set[str] = set()
    aligned: list[tuple[str, object]] = []
    producer_sequences: dict[tuple[str, str], int] = {}
    previous_time: dict[str, int] = {}
    domain_ordinals: dict[str, int] = {}
    if len(domain_origins) > 1:
        findings.add(f"multiple-clock-domains:{len(domain_origins)}")
        findings.add("cross-clock-order-not-total")
    correlation_domains: dict[str, set[str]] = {}
    for record in ordered:
        if record.correlation_id is not None:
            correlation_domains.setdefault(record.correlation_id, set()).add(
                record.clock_domain_id
            )
    for correlation_id, domains in correlation_domains.items():
        if len(domains) > 1:
            findings.add(f"cross-clock-correlation:{correlation_id}")
    for serialization_ordinal, record in enumerate(ordered, start=1):
        producer_key = (record.producer_id, record.clock_domain_id)
        previous = producer_sequences.get(producer_key)
        if previous is not None and record.producer_sequence != previous + 1:
            findings.add(
                f"sequence-gap:{record.producer_id}:{record.clock_domain_id}:"
                f"{previous}->{record.producer_sequence}"
            )
        producer_sequences[producer_key] = record.producer_sequence
        if previous_time.get(record.clock_domain_id) == record.monotonic_ns:
            findings.add(
                f"ambiguous-time:{record.clock_domain_id}:{record.monotonic_ns}"
            )
        previous_time[record.clock_domain_id] = record.monotonic_ns
        domain_ordinals[record.clock_domain_id] = (
            domain_ordinals.get(record.clock_domain_id, 0) + 1
        )
        if record.correlation_id and record.correlation_id not in marker_correlations:
            findings.add(f"unmatched-correlation:{record.correlation_id}")
        for quality in record.quality:
            findings.add(f"quality:{quality.value}:{record.producer_id}:{record.producer_sequence}")
        aligned.append(
            tuple(
                sorted(
                    {
                        "serialization_ordinal": serialization_ordinal,
                        "domain_ordinal": domain_ordinals[record.clock_domain_id],
                        "clock_domain_id": record.clock_domain_id,
                        "clock_domain_offset_ns": (
                            record.monotonic_ns - domain_origins[record.clock_domain_id]
                        ),
                        "captured_at_utc": record.captured_at_utc,
                        "utc_uncertainty_ns": record.utc_uncertainty_ns,
                        "utc_window_start_ns": (
                            _utc_epoch_ns(record.captured_at_utc)
                            - record.utc_uncertainty_ns
                        ),
                        "utc_window_end_ns": (
                            _utc_epoch_ns(record.captured_at_utc)
                            + record.utc_uncertainty_ns
                        ),
                        "global_order": (
                            "single_clock_domain"
                            if len(domain_origins) == 1
                            else "not_asserted"
                        ),
                        "channel_id": record.channel_id,
                        "producer_id": record.producer_id,
                        "producer_sequence": record.producer_sequence,
                        "correlation_id": record.correlation_id,
                        "kind": record.kind.value,
                        "payload": dict(record.payload),
                        "artifact_id": record.artifact_id,
                        "quality": [item.value for item in record.quality],
                        "record_id": record.record_id,
                    }.items()
                )
            )
        )
    if not any(item.kind is CaptureRecordKind.MARKER for item in ordered):
        findings.add("missing-markers")
    return SemanticTrace(
        run_id=ordered[0].run_id,
        records=tuple(aligned),
        findings=tuple(sorted(findings)),
        source_record_ids=tuple(sorted(item.record_id or "" for item in ordered)),
    )


def _utc_epoch_ns(value: str) -> int:
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    return int(parsed.astimezone(UTC).timestamp() * 1_000_000_000)


def save_semantic_trace(path: str | Path, trace: SemanticTrace) -> None:
    try:
        create_only_json(Path(path), trace.as_dict(), make_parents=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CaseError(f"could not save semantic trace: {exc}") from exc


__all__ = ["SemanticTrace", "align_capture_records", "save_semantic_trace"]
