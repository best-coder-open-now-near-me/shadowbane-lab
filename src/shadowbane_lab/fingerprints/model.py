"""Complete stable identity envelopes for controlled Shadowbane executions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from shadowbane_lab.evidence.model import parse_artifact_id
from shadowbane_lab.integrity import (
    canonical_json_sha256,
    validate_finite_json,
    validate_identifier,
)

FINGERPRINT_ENVELOPE_SCHEMA_VERSION = 1
FINGERPRINT_DIFF_SCHEMA_VERSION = 1


class FingerprintError(RuntimeError):
    """Raised when a fingerprint is incomplete or cannot be trusted."""


class SectionName(StrEnum):
    CLIENT = "client"
    RUNTIME = "runtime"
    SERVICE = "service"
    ENVIRONMENT = "environment"
    FIXTURE = "fixture"
    EXECUTION = "execution"


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"


class ImpactState(StrEnum):
    UNAFFECTED = "unaffected"
    REVIEW_REQUIRED = "review_required"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


def _canonical_items(values: tuple[tuple[str, Any], ...], field_name: str) -> None:
    names = tuple(name for name, _ in values)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError(f"{field_name} must use unique canonical keys")
    for name, value in values:
        validate_identifier(name, f"{field_name} key")
        validate_finite_json(value)


@dataclass(frozen=True, slots=True)
class FingerprintSection:
    name: SectionName
    applicability: Applicability
    durable: tuple[tuple[str, Any], ...] = ()
    volatile: tuple[tuple[str, Any], ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    reason: str | None = None
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, SectionName):
            raise ValueError("fingerprint section name must be SectionName")
        if not isinstance(self.applicability, Applicability):
            raise ValueError("fingerprint applicability must be Applicability")
        _canonical_items(self.durable, "durable")
        _canonical_items(self.volatile, "volatile")
        if set(name for name, _ in self.durable) & set(name for name, _ in self.volatile):
            raise ValueError("durable and volatile keys must not overlap")
        if self.source_artifact_ids != tuple(sorted(self.source_artifact_ids)) or len(
            self.source_artifact_ids
        ) != len(set(self.source_artifact_ids)):
            raise ValueError("source artifact IDs must use unique canonical ordering")
        for artifact_id in self.source_artifact_ids:
            parse_artifact_id(artifact_id)
        if self.reason is not None and (not self.reason or len(self.reason) > 2048):
            raise ValueError("section reason must be bounded non-empty text")
        if self.findings != tuple(sorted(self.findings)) or len(self.findings) != len(
            set(self.findings)
        ):
            raise ValueError("section findings must use unique canonical ordering")
        if self.applicability is Applicability.NOT_APPLICABLE:
            if self.durable or self.volatile or self.source_artifact_ids or self.reason is None:
                raise ValueError("not-applicable section requires only an explicit reason")
        elif not self.durable:
            raise ValueError("applicable fingerprint section requires durable identity")

    def identity_dict(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "applicability": self.applicability.value,
            "durable": {name: value for name, value in self.durable},
            "source_artifact_ids": list(self.source_artifact_ids),
            "reason": self.reason,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.identity_dict(),
            "volatile": {name: value for name, value in self.volatile},
            "findings": list(self.findings),
        }


@dataclass(frozen=True, slots=True)
class FingerprintEnvelope:
    captured_at_utc: str
    sections: tuple[FingerprintSection, ...]
    fingerprint_id: str | None = None
    capture_id: str | None = None
    schema_version: int = FINGERPRINT_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FINGERPRINT_ENVELOPE_SCHEMA_VERSION:
            raise ValueError("unsupported fingerprint envelope schema version")
        _timestamp(self.captured_at_utc)
        expected_names = tuple(SectionName)
        actual_names = tuple(section.name for section in self.sections)
        if actual_names != expected_names:
            raise ValueError("fingerprint envelope must contain every section in canonical order")
        expected_fingerprint = f"sha256:{canonical_json_sha256(self.identity_dict())}"
        if self.fingerprint_id is None:
            object.__setattr__(self, "fingerprint_id", expected_fingerprint)
        elif self.fingerprint_id != expected_fingerprint:
            raise ValueError("fingerprint_id does not match durable identity")
        expected_capture = f"sha256:{canonical_json_sha256(self.capture_content_dict())}"
        if self.capture_id is None:
            object.__setattr__(self, "capture_id", expected_capture)
        elif self.capture_id != expected_capture:
            raise ValueError("capture_id does not match complete capture content")

    def identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sections": [section.identity_dict() for section in self.sections],
        }

    def capture_content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "fingerprint_id": self.fingerprint_id,
            "captured_at_utc": self.captured_at_utc,
            "sections": [section.as_dict() for section in self.sections],
        }

    def as_dict(self) -> dict[str, object]:
        return {"capture_id": self.capture_id, **self.capture_content_dict()}


@dataclass(frozen=True, slots=True)
class SectionDifference:
    section: SectionName
    state: ImpactState
    changed_keys: tuple[str, ...]
    reference_applicability: Applicability
    candidate_applicability: Applicability

    def __post_init__(self) -> None:
        if self.changed_keys != tuple(sorted(self.changed_keys)) or len(self.changed_keys) != len(
            set(self.changed_keys)
        ):
            raise ValueError("changed keys must use unique canonical ordering")

    def as_dict(self) -> dict[str, object]:
        return {
            "section": self.section.value,
            "state": self.state.value,
            "changed_keys": list(self.changed_keys),
            "reference_applicability": self.reference_applicability.value,
            "candidate_applicability": self.candidate_applicability.value,
        }


@dataclass(frozen=True, slots=True)
class FingerprintDiff:
    reference_fingerprint_id: str
    candidate_fingerprint_id: str
    differences: tuple[SectionDifference, ...]
    schema_version: int = FINGERPRINT_DIFF_SCHEMA_VERSION

    @property
    def state(self) -> ImpactState:
        states = {item.state for item in self.differences}
        if ImpactState.INVALIDATED in states:
            return ImpactState.INVALIDATED
        if ImpactState.REVIEW_REQUIRED in states:
            return ImpactState.REVIEW_REQUIRED
        if ImpactState.UNKNOWN in states:
            return ImpactState.UNKNOWN
        return ImpactState.UNAFFECTED

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "reference_fingerprint_id": self.reference_fingerprint_id,
            "candidate_fingerprint_id": self.candidate_fingerprint_id,
            "state": self.state.value,
            "differences": [item.as_dict() for item in self.differences],
        }


def _timestamp(value: object) -> None:
    from datetime import datetime

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("captured_at_utc must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("captured_at_utc must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("captured_at_utc must be UTC")


__all__ = [
    "Applicability",
    "FINGERPRINT_DIFF_SCHEMA_VERSION",
    "FINGERPRINT_ENVELOPE_SCHEMA_VERSION",
    "FingerprintDiff",
    "FingerprintEnvelope",
    "FingerprintError",
    "FingerprintSection",
    "ImpactState",
    "SectionDifference",
    "SectionName",
]
