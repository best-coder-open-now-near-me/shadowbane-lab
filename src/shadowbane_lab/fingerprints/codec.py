"""Strict persistence for complete fingerprint envelopes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shadowbane_lab.evidence.codec import save_contract
from shadowbane_lab.integrity import load_strict_json

from .model import (
    Applicability,
    FingerprintEnvelope,
    FingerprintError,
    FingerprintSection,
    SectionName,
)


def save_fingerprint(path: str | Path, value: FingerprintEnvelope) -> None:
    save_contract(path, value)


def load_fingerprint(path: str | Path) -> FingerprintEnvelope:
    try:
        payload = load_strict_json(Path(path))
    except (OSError, ValueError) as exc:
        raise FingerprintError(f"could not load fingerprint: {exc}") from exc
    if not isinstance(payload, dict):
        raise FingerprintError("fingerprint must be a JSON object")
    expected = {
        "schema_version",
        "fingerprint_id",
        "capture_id",
        "captured_at_utc",
        "sections",
    }
    if set(payload) != expected:
        raise FingerprintError("fingerprint fields are not exact")
    raw_sections = payload["sections"]
    if not isinstance(raw_sections, list):
        raise FingerprintError("fingerprint sections must be a JSON array")
    try:
        sections = tuple(_parse_section(item) for item in raw_sections)
        return FingerprintEnvelope(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            fingerprint_id=payload["fingerprint_id"],  # type: ignore[arg-type]
            capture_id=payload["capture_id"],  # type: ignore[arg-type]
            captured_at_utc=payload["captured_at_utc"],  # type: ignore[arg-type]
            sections=sections,
        )
    except (TypeError, ValueError) as exc:
        raise FingerprintError(f"invalid fingerprint: {exc}") from exc


def _parse_section(payload: object) -> FingerprintSection:
    if not isinstance(payload, dict):
        raise ValueError("fingerprint section must be a JSON object")
    expected = {
        "name",
        "applicability",
        "durable",
        "volatile",
        "source_artifact_ids",
        "reason",
        "findings",
    }
    if set(payload) != expected:
        raise ValueError("fingerprint section fields are not exact")
    durable = _mapping(payload["durable"], "durable")
    volatile = _mapping(payload["volatile"], "volatile")
    sources = _strings(payload["source_artifact_ids"], "source_artifact_ids")
    findings = _strings(payload["findings"], "findings")
    return FingerprintSection(
        name=SectionName(payload["name"]),  # type: ignore[arg-type]
        applicability=Applicability(payload["applicability"]),  # type: ignore[arg-type]
        durable=tuple(sorted(durable.items())),
        volatile=tuple(sorted(volatile.items())),
        source_artifact_ids=sources,
        reason=payload["reason"],  # type: ignore[arg-type]
        findings=findings,
    )


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(value)


__all__ = ["load_fingerprint", "save_fingerprint"]
