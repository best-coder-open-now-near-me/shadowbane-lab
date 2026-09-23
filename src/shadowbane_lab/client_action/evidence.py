"""Finite, versioned evidence persistence for bounded client actions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from .model import (
    CLIENT_ACTION_RESULT_SCHEMA_VERSION,
    ClientActionBoundary,
    ClientActionBoundaryRecord,
    ClientActionResult,
    ClientActionVerification,
)


class ClientActionEvidenceError(RuntimeError):
    """Raised when client-action evidence cannot be validated or persisted safely."""


def save_client_action_evidence(
    path: str | Path,
    result: ClientActionResult,
) -> None:
    if not isinstance(result, ClientActionResult):
        raise ValueError("result must be ClientActionResult")
    evidence_path = Path(path)
    if evidence_path.exists():
        raise ClientActionEvidenceError(
            f"client-action evidence destination already exists: {evidence_path}"
        )
    temporary = evidence_path.with_name(
        f".{evidence_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    try:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(
                result.to_dict(),
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, evidence_path)
        if load_client_action_evidence(evidence_path) != result:
            raise ClientActionEvidenceError(
                "published client-action evidence did not round trip"
            )
    except ClientActionEvidenceError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ClientActionEvidenceError(
            f"could not save client-action evidence: {exc}"
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def load_client_action_evidence(path: str | Path) -> ClientActionResult:
    evidence_path = Path(path)
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClientActionEvidenceError(
            f"could not read client-action evidence: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ClientActionEvidenceError("client-action evidence must be an object")
    try:
        if set(payload) != {
            "schema_version",
            "action_id",
            "action_key",
            "verification",
            "succeeded",
            "terminal_reason",
            "duration_ms",
            "boundaries",
        }:
            raise ValueError("client-action evidence fields are not exact")
        if payload["schema_version"] != CLIENT_ACTION_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported client-action evidence schema version")
        raw_boundaries = payload["boundaries"]
        if not isinstance(raw_boundaries, list):
            raise ValueError("client-action boundaries must be a list")
        boundaries = tuple(_parse_boundary(item) for item in raw_boundaries)
        return ClientActionResult(
            schema_version=payload["schema_version"],
            action_id=payload["action_id"],
            action_key=payload["action_key"],
            verification=ClientActionVerification(payload["verification"]),
            succeeded=payload["succeeded"],
            terminal_reason=payload["terminal_reason"],
            duration_ms=payload["duration_ms"],
            boundaries=boundaries,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ClientActionEvidenceError(
            f"invalid client-action evidence: {exc}"
        ) from exc


def _parse_boundary(payload: object) -> ClientActionBoundaryRecord:
    if not isinstance(payload, dict):
        raise ValueError("client-action boundary must be an object")
    if set(payload) != {"sequence", "at_ms", "boundary", "detail", "evidence"}:
        raise ValueError("client-action boundary fields are not exact")
    evidence = payload["evidence"]
    if not isinstance(evidence, dict):
        raise ValueError("client-action boundary evidence must be an object")
    return ClientActionBoundaryRecord(
        sequence=payload["sequence"],
        at_ms=payload["at_ms"],
        boundary=ClientActionBoundary(payload["boundary"]),
        detail=payload["detail"],
        evidence=dict(evidence),  # type: ignore[arg-type]
    )


__all__ = [
    "ClientActionEvidenceError",
    "load_client_action_evidence",
    "save_client_action_evidence",
]
