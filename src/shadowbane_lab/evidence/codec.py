"""Strict codecs and create-only persistence for evidence contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shadowbane_lab.integrity import create_only_json, load_strict_json

from .model import (
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactVerification,
    EvidenceError,
    EvidenceManifest,
    ManifestTerminalState,
    MigrationReceipt,
    Redaction,
    RedactionState,
    VerificationReceipt,
)


def save_contract(path: str | Path, value: object) -> None:
    as_dict = getattr(value, "as_dict", None)
    if not callable(as_dict):
        raise TypeError("evidence contract must provide as_dict()")
    try:
        create_only_json(Path(path), as_dict(), make_parents=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise EvidenceError(f"could not save evidence contract: {exc}") from exc


def load_manifest(path: str | Path) -> EvidenceManifest:
    return parse_manifest(_load_object(path, "evidence manifest"))


def load_verification_receipt(path: str | Path) -> VerificationReceipt:
    return parse_verification_receipt(_load_object(path, "verification receipt"))


def load_migration_receipt(path: str | Path) -> MigrationReceipt:
    return parse_migration_receipt(_load_object(path, "migration receipt"))


def parse_artifact(payload: object) -> ArtifactDescriptor:
    value = _object(payload, "artifact descriptor")
    _exact(
        value,
        {
            "schema_version",
            "artifact_id",
            "sha256",
            "size_bytes",
            "media_type",
            "artifact_kind",
            "logical_name",
            "producer_id",
            "producer_version",
            "captured_at_utc",
            "redaction",
            "parents",
            "metadata",
        },
        "artifact descriptor",
    )
    redaction = _object(value["redaction"], "artifact redaction")
    _exact(redaction, {"state", "policy_id", "source_artifact_id"}, "artifact redaction")
    metadata = _object(value["metadata"], "artifact metadata")
    try:
        return ArtifactDescriptor(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            artifact_id=value["artifact_id"],  # type: ignore[arg-type]
            sha256=value["sha256"],  # type: ignore[arg-type]
            size_bytes=value["size_bytes"],  # type: ignore[arg-type]
            media_type=value["media_type"],  # type: ignore[arg-type]
            artifact_kind=ArtifactKind(value["artifact_kind"]),  # type: ignore[arg-type]
            logical_name=value["logical_name"],  # type: ignore[arg-type]
            producer_id=value["producer_id"],  # type: ignore[arg-type]
            producer_version=value["producer_version"],  # type: ignore[arg-type]
            captured_at_utc=value["captured_at_utc"],  # type: ignore[arg-type]
            redaction=Redaction(
                state=RedactionState(redaction["state"]),  # type: ignore[arg-type]
                policy_id=redaction["policy_id"],  # type: ignore[arg-type]
                source_artifact_id=redaction["source_artifact_id"],  # type: ignore[arg-type]
            ),
            parents=_strings(value["parents"], "parents"),
            metadata=tuple(sorted(metadata.items())),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid artifact descriptor: {exc}") from exc


def parse_manifest(payload: object) -> EvidenceManifest:
    value = _object(payload, "evidence manifest")
    _exact(
        value,
        {
            "schema_version",
            "manifest_id",
            "created_at_utc",
            "fingerprint_id",
            "case_id",
            "experiment_id",
            "run_id",
            "terminal_state",
            "required_channels",
            "completed_channels",
            "omissions",
            "warnings",
            "artifacts",
        },
        "evidence manifest",
    )
    try:
        artifacts = tuple(parse_artifact(item) for item in _list(value["artifacts"], "artifacts"))
        return EvidenceManifest(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            manifest_id=value["manifest_id"],  # type: ignore[arg-type]
            created_at_utc=value["created_at_utc"],  # type: ignore[arg-type]
            fingerprint_id=value["fingerprint_id"],  # type: ignore[arg-type]
            case_id=value["case_id"],  # type: ignore[arg-type]
            experiment_id=value["experiment_id"],  # type: ignore[arg-type]
            run_id=value["run_id"],  # type: ignore[arg-type]
            terminal_state=ManifestTerminalState(value["terminal_state"]),  # type: ignore[arg-type]
            required_channels=_strings(value["required_channels"], "required_channels"),
            completed_channels=_strings(value["completed_channels"], "completed_channels"),
            omissions=_strings(value["omissions"], "omissions"),
            warnings=_strings(value["warnings"], "warnings"),
            artifacts=artifacts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError(f"invalid evidence manifest: {exc}") from exc


def parse_verification_receipt(payload: object) -> VerificationReceipt:
    value = _object(payload, "verification receipt")
    _exact(
        value,
        {
            "schema_version",
            "receipt_id",
            "manifest_id",
            "verified_at_utc",
            "verifier_id",
            "verifier_version",
            "store_id",
            "status",
            "results",
        },
        "verification receipt",
    )
    results: list[ArtifactVerification] = []
    for item in _list(value["results"], "verification results"):
        result = _object(item, "artifact verification")
        _exact(
            result,
            {
                "artifact_id",
                "present",
                "size_matches",
                "digest_matches",
                "issue",
                "passed",
            },
            "artifact verification",
        )
        parsed = ArtifactVerification(
            artifact_id=result["artifact_id"],  # type: ignore[arg-type]
            present=result["present"],  # type: ignore[arg-type]
            size_matches=result["size_matches"],  # type: ignore[arg-type]
            digest_matches=result["digest_matches"],  # type: ignore[arg-type]
            issue=result["issue"],  # type: ignore[arg-type]
        )
        if result["passed"] is not parsed.passed:
            raise EvidenceError("artifact verification passed flag does not match fields")
        results.append(parsed)
    try:
        receipt = VerificationReceipt(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            receipt_id=value["receipt_id"],  # type: ignore[arg-type]
            manifest_id=value["manifest_id"],  # type: ignore[arg-type]
            verified_at_utc=value["verified_at_utc"],  # type: ignore[arg-type]
            verifier_id=value["verifier_id"],  # type: ignore[arg-type]
            verifier_version=value["verifier_version"],  # type: ignore[arg-type]
            store_id=value["store_id"],  # type: ignore[arg-type]
            results=tuple(results),
        )
        if value["status"] != receipt.status.value:
            raise ValueError("receipt status does not match verification results")
        return receipt
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid verification receipt: {exc}") from exc


def parse_migration_receipt(payload: object) -> MigrationReceipt:
    value = _object(payload, "migration receipt")
    _exact(
        value,
        {
            "schema_version",
            "receipt_id",
            "imported_at_utc",
            "importer_id",
            "importer_version",
            "source_labels",
            "source_artifact_ids",
            "manifest_id",
        },
        "migration receipt",
    )
    try:
        return MigrationReceipt(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            receipt_id=value["receipt_id"],  # type: ignore[arg-type]
            imported_at_utc=value["imported_at_utc"],  # type: ignore[arg-type]
            importer_id=value["importer_id"],  # type: ignore[arg-type]
            importer_version=value["importer_version"],  # type: ignore[arg-type]
            source_labels=_strings(value["source_labels"], "source_labels"),
            source_artifact_ids=_strings(value["source_artifact_ids"], "source_artifact_ids"),
            manifest_id=value["manifest_id"],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"invalid migration receipt: {exc}") from exc


def _load_object(path: str | Path, label: str) -> dict[str, Any]:
    try:
        return _object(load_strict_json(Path(path)), label)
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError(f"could not load {label}: {exc}") from exc


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(f"{label} must be a JSON array")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    items = _list(value, label)
    if any(not isinstance(item, str) for item in items):
        raise EvidenceError(f"{label} must contain only strings")
    return tuple(items)


def _exact(payload: dict[str, Any], expected: set[str], label: str) -> None:
    missing = expected - payload.keys()
    extra = payload.keys() - expected
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if extra:
            details.append("unknown " + ", ".join(sorted(extra)))
        raise EvidenceError(f"{label} fields are not exact: {'; '.join(details)}")


__all__ = [
    "load_manifest",
    "load_migration_receipt",
    "load_verification_receipt",
    "parse_artifact",
    "parse_manifest",
    "parse_migration_receipt",
    "parse_verification_receipt",
    "save_contract",
]
