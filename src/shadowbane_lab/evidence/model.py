"""Versioned immutable contracts for the evidence spine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from shadowbane_lab.integrity import (
    canonical_json_sha256,
    validate_finite_json,
    validate_identifier,
    validate_sha256,
)

ARTIFACT_DESCRIPTOR_SCHEMA_VERSION = 1
EVIDENCE_MANIFEST_SCHEMA_VERSION = 1
VERIFICATION_RECEIPT_SCHEMA_VERSION = 1
MIGRATION_RECEIPT_SCHEMA_VERSION = 1


class EvidenceError(RuntimeError):
    """Raised when evidence is malformed, incomplete, or cannot be trusted."""


class ArtifactKind(StrEnum):
    CLIENT_TREE_MANIFEST = "client_tree_manifest"
    PE_INSPECTION = "pe_inspection"
    BUILD_DIFF = "build_diff"
    RUNTIME_SNAPSHOT = "runtime_snapshot"
    CHARACTER_SNAPSHOT = "character_snapshot"
    SERVICE_SNAPSHOT = "service_snapshot"
    ENVIRONMENT_SNAPSHOT = "environment_snapshot"
    NATIVE_EVENT_STREAM = "native_event_stream"
    SEMANTIC_TRACE = "semantic_trace"
    INPUT_AUDIT = "input_audit"
    CLIENT_LOG = "client_log"
    SCREENSHOT = "screenshot"
    VIDEO = "video"
    PACKET_CAPTURE = "packet_capture"
    PACKET_SUMMARY = "packet_summary"
    PROCESS_METRICS = "process_metrics"
    SIMULATION_RESULT = "simulation_result"
    DIFFERENTIAL_REPORT = "differential_report"
    SOURCE_SNAPSHOT = "source_snapshot"
    ASSET_EXTRACT = "asset_extract"
    COVERAGE_REPORT = "coverage_report"
    IMPACT_REPORT = "impact_report"
    OTHER_REVIEWED = "other_reviewed"


class RedactionState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    REDACTED = "redacted"


class ManifestTerminalState(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    IMPORTED = "imported"


class VerificationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


def artifact_id_for_sha256(digest: str) -> str:
    return f"sha256:{validate_sha256(digest)}"


def parse_artifact_id(value: object, field_name: str = "artifact_id") -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use sha256:<digest>")
    digest = validate_sha256(value[7:], field_name)
    return artifact_id_for_sha256(digest)


def _optional_identifier(value: str | None, field_name: str) -> None:
    if value is not None:
        validate_identifier(value, field_name)


def _canonical_strings(values: tuple[str, ...], field_name: str) -> None:
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{field_name} must use unique canonical ordering")
    for value in values:
        if not isinstance(value, str) or not value or "\0" in value or len(value) > 1024:
            raise ValueError(f"{field_name} entries must be bounded non-empty text")


@dataclass(frozen=True, slots=True)
class Redaction:
    state: RedactionState
    policy_id: str | None = None
    source_artifact_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, RedactionState):
            raise ValueError("redaction state must be RedactionState")
        _optional_identifier(self.policy_id, "redaction.policy_id")
        if self.source_artifact_id is not None:
            parse_artifact_id(self.source_artifact_id, "redaction.source_artifact_id")
        if self.state is RedactionState.NOT_REQUIRED and (
            self.policy_id is not None or self.source_artifact_id is not None
        ):
            raise ValueError("not-required redaction cannot declare a policy or source")
        if self.state is RedactionState.REDACTED and (
            self.policy_id is None or self.source_artifact_id is None
        ):
            raise ValueError("redacted evidence requires policy and source artifact IDs")
        if self.state is RedactionState.PENDING and self.policy_id is None:
            raise ValueError("pending redaction requires a policy ID")

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "policy_id": self.policy_id,
            "source_artifact_id": self.source_artifact_id,
        }


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    sha256: str
    size_bytes: int
    media_type: str
    artifact_kind: ArtifactKind
    logical_name: str
    producer_id: str
    producer_version: str
    captured_at_utc: str | None
    redaction: Redaction
    parents: tuple[str, ...] = ()
    metadata: tuple[tuple[str, Any], ...] = ()
    artifact_id: str | None = None
    schema_version: int = ARTIFACT_DESCRIPTOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ARTIFACT_DESCRIPTOR_SCHEMA_VERSION:
            raise ValueError("unsupported artifact descriptor schema version")
        validate_sha256(self.sha256)
        expected_id = artifact_id_for_sha256(self.sha256)
        if self.artifact_id is None:
            object.__setattr__(self, "artifact_id", expected_id)
        elif parse_artifact_id(self.artifact_id) != expected_id:
            raise ValueError("artifact_id does not match sha256")
        if (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if not isinstance(self.artifact_kind, ArtifactKind):
            raise ValueError("artifact_kind must be ArtifactKind")
        for value, field_name, maximum in (
            (self.media_type, "media_type", 256),
            (self.logical_name, "logical_name", 1024),
            (self.producer_version, "producer_version", 256),
        ):
            if not isinstance(value, str) or not value or "\0" in value or len(value) > maximum:
                raise ValueError(f"{field_name} must be bounded non-empty text")
        validate_identifier(self.producer_id, "producer_id")
        if self.captured_at_utc is not None:
            _validate_timestamp_text(self.captured_at_utc, "captured_at_utc")
        if not isinstance(self.redaction, Redaction):
            raise ValueError("redaction must be Redaction")
        _canonical_strings(self.parents, "parents")
        for parent in self.parents:
            parse_artifact_id(parent, "parent artifact ID")
            if parent == self.artifact_id:
                raise ValueError("artifact cannot be its own parent")
        metadata_names = tuple(name for name, _ in self.metadata)
        if metadata_names != tuple(sorted(metadata_names)) or len(metadata_names) != len(
            set(metadata_names)
        ):
            raise ValueError("metadata must use unique canonical keys")
        for name, value in self.metadata:
            validate_identifier(name, "metadata key")
            validate_finite_json(value)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "artifact_kind": self.artifact_kind.value,
            "logical_name": self.logical_name,
            "producer_id": self.producer_id,
            "producer_version": self.producer_version,
            "captured_at_utc": self.captured_at_utc,
            "redaction": self.redaction.as_dict(),
            "parents": list(self.parents),
            "metadata": {name: value for name, value in self.metadata},
        }


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    created_at_utc: str
    artifacts: tuple[ArtifactDescriptor, ...]
    terminal_state: ManifestTerminalState
    required_channels: tuple[str, ...] = ()
    completed_channels: tuple[str, ...] = ()
    omissions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    fingerprint_id: str | None = None
    case_id: str | None = None
    experiment_id: str | None = None
    run_id: str | None = None
    manifest_id: str | None = None
    schema_version: int = EVIDENCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVIDENCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported evidence manifest schema version")
        _validate_timestamp_text(self.created_at_utc, "created_at_utc")
        if not self.artifacts:
            raise ValueError("evidence manifest must contain at least one artifact")
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if artifact_ids != tuple(sorted(artifact_ids)) or len(artifact_ids) != len(
            set(artifact_ids)
        ):
            raise ValueError("artifacts must use unique canonical artifact-ID ordering")
        if not all(isinstance(item, ArtifactDescriptor) for item in self.artifacts):
            raise ValueError("artifacts must be ArtifactDescriptor values")
        if not isinstance(self.terminal_state, ManifestTerminalState):
            raise ValueError("terminal_state must be ManifestTerminalState")
        for values, name in (
            (self.required_channels, "required_channels"),
            (self.completed_channels, "completed_channels"),
            (self.omissions, "omissions"),
            (self.warnings, "warnings"),
        ):
            _canonical_strings(values, name)
        if not set(self.completed_channels).issubset(self.required_channels):
            raise ValueError("completed channels must be declared required channels")
        missing = set(self.required_channels) - set(self.completed_channels)
        if self.terminal_state is ManifestTerminalState.COMPLETE and missing:
            raise ValueError("complete manifest is missing required capture channels")
        if self.terminal_state is ManifestTerminalState.COMPLETE and self.omissions:
            raise ValueError("complete manifest cannot declare omissions")
        for value, name in (
            (self.fingerprint_id, "fingerprint_id"),
            (self.case_id, "case_id"),
            (self.experiment_id, "experiment_id"),
            (self.run_id, "run_id"),
        ):
            _optional_identifier(value, name)
        expected_id = f"sha256:{canonical_json_sha256(self.content_dict())}"
        if self.manifest_id is None:
            object.__setattr__(self, "manifest_id", expected_id)
        elif self.manifest_id != expected_id:
            raise ValueError("manifest_id does not match canonical manifest content")

    def content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "fingerprint_id": self.fingerprint_id,
            "case_id": self.case_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "terminal_state": self.terminal_state.value,
            "required_channels": list(self.required_channels),
            "completed_channels": list(self.completed_channels),
            "omissions": list(self.omissions),
            "warnings": list(self.warnings),
            "artifacts": [item.as_dict() for item in self.artifacts],
        }

    def as_dict(self) -> dict[str, object]:
        return {"manifest_id": self.manifest_id, **self.content_dict()}


@dataclass(frozen=True, slots=True)
class ArtifactVerification:
    artifact_id: str
    present: bool
    size_matches: bool
    digest_matches: bool
    issue: str | None = None

    def __post_init__(self) -> None:
        parse_artifact_id(self.artifact_id)
        if not all(
            isinstance(value, bool)
            for value in (self.present, self.size_matches, self.digest_matches)
        ):
            raise ValueError("artifact verification flags must be booleans")
        if self.issue is not None and (not self.issue or len(self.issue) > 2048):
            raise ValueError("verification issue must be bounded non-empty text")
        if self.digest_matches and not (self.present and self.size_matches):
            raise ValueError("digest cannot match when artifact is missing or wrong-sized")

    @property
    def passed(self) -> bool:
        return self.present and self.size_matches and self.digest_matches and self.issue is None

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "present": self.present,
            "size_matches": self.size_matches,
            "digest_matches": self.digest_matches,
            "issue": self.issue,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    manifest_id: str
    verified_at_utc: str
    verifier_id: str
    verifier_version: str
    store_id: str
    results: tuple[ArtifactVerification, ...]
    receipt_id: str | None = None
    schema_version: int = VERIFICATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != VERIFICATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported verification receipt schema version")
        parse_artifact_id(self.manifest_id, "manifest_id")
        _validate_timestamp_text(self.verified_at_utc, "verified_at_utc")
        validate_identifier(self.verifier_id, "verifier_id")
        validate_identifier(self.store_id, "store_id")
        if not self.verifier_version or len(self.verifier_version) > 256:
            raise ValueError("verifier_version must be bounded non-empty text")
        result_ids = tuple(item.artifact_id for item in self.results)
        if result_ids != tuple(sorted(result_ids)) or len(result_ids) != len(set(result_ids)):
            raise ValueError("verification results must use unique canonical artifact ordering")
        expected = f"sha256:{canonical_json_sha256(self.content_dict())}"
        if self.receipt_id is None:
            object.__setattr__(self, "receipt_id", expected)
        elif self.receipt_id != expected:
            raise ValueError("receipt_id does not match receipt content")

    @property
    def status(self) -> VerificationStatus:
        return (
            VerificationStatus.PASS
            if self.results and all(item.passed for item in self.results)
            else VerificationStatus.FAIL
        )

    def content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "verified_at_utc": self.verified_at_utc,
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "store_id": self.store_id,
            "status": self.status.value,
            "results": [item.as_dict() for item in self.results],
        }

    def as_dict(self) -> dict[str, object]:
        return {"receipt_id": self.receipt_id, **self.content_dict()}


@dataclass(frozen=True, slots=True)
class MigrationReceipt:
    imported_at_utc: str
    importer_id: str
    importer_version: str
    source_labels: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    manifest_id: str
    receipt_id: str | None = None
    schema_version: int = MIGRATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MIGRATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported migration receipt schema version")
        _validate_timestamp_text(self.imported_at_utc, "imported_at_utc")
        validate_identifier(self.importer_id, "importer_id")
        if not self.importer_version or len(self.importer_version) > 256:
            raise ValueError("importer_version must be bounded non-empty text")
        _canonical_strings(self.source_labels, "source_labels")
        _canonical_strings(self.source_artifact_ids, "source_artifact_ids")
        for artifact_id in self.source_artifact_ids:
            parse_artifact_id(artifact_id)
        parse_artifact_id(self.manifest_id, "manifest_id")
        expected = f"sha256:{canonical_json_sha256(self.content_dict())}"
        if self.receipt_id is None:
            object.__setattr__(self, "receipt_id", expected)
        elif self.receipt_id != expected:
            raise ValueError("receipt_id does not match migration receipt content")

    def content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "imported_at_utc": self.imported_at_utc,
            "importer_id": self.importer_id,
            "importer_version": self.importer_version,
            "source_labels": list(self.source_labels),
            "source_artifact_ids": list(self.source_artifact_ids),
            "manifest_id": self.manifest_id,
        }

    def as_dict(self) -> dict[str, object]:
        return {"receipt_id": self.receipt_id, **self.content_dict()}


def _validate_timestamp_text(value: object, field_name: str) -> None:
    from datetime import datetime

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be UTC")


__all__ = [
    "ARTIFACT_DESCRIPTOR_SCHEMA_VERSION",
    "EVIDENCE_MANIFEST_SCHEMA_VERSION",
    "MIGRATION_RECEIPT_SCHEMA_VERSION",
    "VERIFICATION_RECEIPT_SCHEMA_VERSION",
    "ArtifactDescriptor",
    "ArtifactKind",
    "ArtifactVerification",
    "EvidenceError",
    "EvidenceManifest",
    "ManifestTerminalState",
    "MigrationReceipt",
    "Redaction",
    "RedactionState",
    "VerificationReceipt",
    "VerificationStatus",
    "artifact_id_for_sha256",
    "parse_artifact_id",
]
