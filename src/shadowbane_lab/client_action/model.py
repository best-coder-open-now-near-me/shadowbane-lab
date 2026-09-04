"""Typed lifecycle records for bounded live-client acceptance actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

CLIENT_ACTION_RESULT_SCHEMA_VERSION = 1

ActionEvidenceValue = str | int | float | bool | None


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _evidence(values: dict[str, ActionEvidenceValue]) -> None:
    if not isinstance(values, dict):
        raise ValueError("evidence must be a dictionary")
    for key, value in values.items():
        _identifier(key, "evidence key")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("evidence values must be JSON scalar values")
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("floating-point evidence must be finite")


class ClientActionVerification(StrEnum):
    """The strongest independent oracle used by one action contract."""

    NATIVE_VERIFIED = "native_verified"
    VISUAL_REVIEW_REQUIRED = "visual_review_required"
    UNVERIFIABLE = "unverifiable"


class ClientActionBoundary(StrEnum):
    """Stable boundaries shared by every action lifecycle."""

    STARTED = "started"
    PRECONDITION_PASSED = "precondition_passed"
    INPUT_DISPATCHED = "input_dispatched"
    EFFECT_OBSERVED = "effect_observed"
    CLEANUP_COMPLETED = "cleanup_completed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ClientActionSpec:
    """Static timeout and verification contract for one semantic client action."""

    key: str
    verification: ClientActionVerification
    timeout_ms: int
    poll_interval_ms: int

    def __post_init__(self) -> None:
        _identifier(self.key, "action key")
        if not isinstance(self.verification, ClientActionVerification):
            raise ValueError("verification must be ClientActionVerification")
        for value, field_name in (
            (self.timeout_ms, "timeout_ms"),
            (self.poll_interval_ms, "poll_interval_ms"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.poll_interval_ms > self.timeout_ms:
            raise ValueError("poll interval cannot exceed the action timeout")


@dataclass(frozen=True, slots=True)
class ClientActionCheckpoint:
    """One completed action operation plus compact human-readable evidence."""

    detail: str
    evidence: dict[str, ActionEvidenceValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.detail, "checkpoint detail")
        _evidence(self.evidence)


@dataclass(frozen=True, slots=True)
class ClientActionEffectObservation:
    """A bounded effect poll that either remains pending or proves the postcondition."""

    observed: bool
    checkpoint: ClientActionCheckpoint

    def __post_init__(self) -> None:
        if not isinstance(self.observed, bool):
            raise ValueError("observed must be boolean")
        if not isinstance(self.checkpoint, ClientActionCheckpoint):
            raise ValueError("checkpoint must be ClientActionCheckpoint")


@dataclass(frozen=True, slots=True)
class ClientActionBoundaryRecord:
    """One ordered, elapsed-time-stamped lifecycle boundary."""

    sequence: int
    at_ms: int
    boundary: ClientActionBoundary
    detail: str
    evidence: dict[str, ActionEvidenceValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, field_name in ((self.sequence, "sequence"), (self.at_ms, "at_ms")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.boundary, ClientActionBoundary):
            raise ValueError("boundary must be ClientActionBoundary")
        _identifier(self.detail, "boundary detail")
        _evidence(self.evidence)

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "at_ms": self.at_ms,
            "boundary": self.boundary.value,
            "detail": self.detail,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ClientActionResult:
    """Terminal evidence for one bounded action attempt."""

    action_id: str
    action_key: str
    verification: ClientActionVerification
    succeeded: bool
    terminal_reason: str
    duration_ms: int
    boundaries: tuple[ClientActionBoundaryRecord, ...]
    schema_version: int = CLIENT_ACTION_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CLIENT_ACTION_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported client-action result schema version")
        _identifier(self.action_id, "action_id")
        _identifier(self.action_key, "action_key")
        _identifier(self.terminal_reason, "terminal_reason")
        if not isinstance(self.verification, ClientActionVerification):
            raise ValueError("verification must be ClientActionVerification")
        if not isinstance(self.succeeded, bool):
            raise ValueError("succeeded must be boolean")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int):
            raise ValueError("duration_ms must be an integer")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if not self.boundaries:
            raise ValueError("an action result requires lifecycle boundaries")
        if any(not isinstance(item, ClientActionBoundaryRecord) for item in self.boundaries):
            raise ValueError("boundaries must contain ClientActionBoundaryRecord values")
        sequences = tuple(item.sequence for item in self.boundaries)
        if sequences != tuple(range(len(self.boundaries))):
            raise ValueError("action boundary sequences must be contiguous from zero")
        if self.boundaries[0].boundary is not ClientActionBoundary.STARTED:
            raise ValueError("an action lifecycle must start with the started boundary")
        expected_terminal = (
            ClientActionBoundary.SUCCEEDED if self.succeeded else ClientActionBoundary.FAILED
        )
        if self.boundaries[-1].boundary is not expected_terminal:
            raise ValueError("action terminal boundary does not match its result")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "action_id": self.action_id,
            "action_key": self.action_key,
            "verification": self.verification.value,
            "succeeded": self.succeeded,
            "terminal_reason": self.terminal_reason,
            "duration_ms": self.duration_ms,
            "boundaries": [item.to_dict() for item in self.boundaries],
        }


__all__ = [
    "CLIENT_ACTION_RESULT_SCHEMA_VERSION",
    "ActionEvidenceValue",
    "ClientActionBoundary",
    "ClientActionBoundaryRecord",
    "ClientActionCheckpoint",
    "ClientActionEffectObservation",
    "ClientActionResult",
    "ClientActionSpec",
    "ClientActionVerification",
]
