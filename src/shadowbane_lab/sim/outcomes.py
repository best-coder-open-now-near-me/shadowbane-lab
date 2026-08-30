"""Typed results produced by primitive effect execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class EffectOutcomeKind(StrEnum):
    """Closed result vocabulary for primitive effect execution."""

    APPLIED = "applied"
    REFRESHED = "refreshed"
    BLOCKED_IMMUNITY = "blocked_immunity"
    BLOCKED_STACK = "blocked_stack"
    RESISTED = "resisted"
    MISSED = "missed"
    NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class EffectOutcome:
    """Auditable result of one primitive effect attempt."""

    kind: EffectOutcomeKind
    primitive_kind: str
    subject_entity_id: str | None = None
    effect_key: str | None = None
    magnitude: float = 0.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EffectOutcomeKind):
            raise ValueError("kind must be an EffectOutcomeKind")
        if not isinstance(self.primitive_kind, str) or not self.primitive_kind.strip():
            raise ValueError("primitive_kind must be a non-empty string")
        for value, field_name in (
            (self.subject_entity_id, "subject_entity_id"),
            (self.effect_key, "effect_key"),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or null")
        if (
            isinstance(self.magnitude, bool)
            or not isinstance(self.magnitude, (int, float))
            or not isfinite(self.magnitude)
        ):
            raise ValueError("magnitude must be finite")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")
        for tag in self.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("tags must contain non-empty strings")
