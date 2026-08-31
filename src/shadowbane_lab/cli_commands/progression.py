"""Progression import command implementations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.progression import (
    CalculatorReviewStatus,
    WonderbaneCalculatorImportError,
    capture_wonderbane_calculator_snapshot,
    import_wonderbane_calculator_snapshot,
)

from .common import _error


def _import_wonderbane_calculator(
    snapshot_path: Path | None,
    output_directory: Path,
    *,
    download: bool,
    retrieved_at_text: str | None,
    as_json: bool,
) -> int:
    try:
        retrieved_at = _parse_retrieved_at(retrieved_at_text)
        if download:
            artifacts = capture_wonderbane_calculator_snapshot(
                output_directory,
                retrieved_at=retrieved_at,
            )
        else:
            if snapshot_path is None:
                raise WonderbaneCalculatorImportError(
                    "calculator import requires --snapshot or --download"
                )
            artifacts = import_wonderbane_calculator_snapshot(
                snapshot_path,
                output_directory,
                retrieved_at=retrieved_at,
            )
    except (OSError, ValueError, WonderbaneCalculatorImportError) as exc:
        return _error(f"WonderBane calculator import failed: {exc}", as_json=as_json)

    catalog = artifacts.catalog
    payload = {
        "ok": catalog.review_status is CalculatorReviewStatus.ACCEPTED,
        "review_status": catalog.review_status.value,
        "evidence_status": catalog.evidence_status,
        "snapshot_path": str(artifacts.snapshot_path),
        "snapshot_sha256": catalog.snapshot_sha256,
        "manifest_path": str(artifacts.manifest_path),
        "catalog_path": str(artifacts.catalog_path),
        "declaration_sha256": catalog.declaration_sha256,
        "review_profile_id": catalog.review_profile_id,
        "counts": catalog.to_dict()["counts"],
        "unresolved_references": list(catalog.unresolved_references),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Snapshot: {artifacts.snapshot_path}")
        print(f"SHA-256: {catalog.snapshot_sha256}")
        print(f"Catalog: {artifacts.catalog_path}")
        print(f"Review: {catalog.review_status.value}")
        counts = payload["counts"]
        print(
            "Records: "
            f"{counts['race_records']} race/sex, "
            f"{counts['base_classes']} bases, "
            f"{counts['promotions']} promotions, "
            f"{counts['runes']} runes"
        )
    return 0 if catalog.review_status is CalculatorReviewStatus.ACCEPTED else 2


def _parse_retrieved_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WonderbaneCalculatorImportError("retrieved-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise WonderbaneCalculatorImportError("retrieved-at must include a UTC offset")
    return parsed.astimezone(UTC)
