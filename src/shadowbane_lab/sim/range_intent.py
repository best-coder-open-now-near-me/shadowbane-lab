"""Relational range intents that preserve geometry without directional branching."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind
from shadowbane_lab.sim.actions import (
    ActionPhase,
    ActionSpec,
    MoveEntity,
    MovementMode,
    PhaseKind,
    SubjectRef,
    TargetingSpec,
)

CLOSE_RANGE_ACTION_KEY = "sim.range.close"
OPEN_RANGE_ACTION_KEY = "sim.range.open"
RANGE_MINIMUM_FEATURE = "range.minimum"
RANGE_MAXIMUM_FEATURE = "range.maximum"


class RangeRelation(StrEnum):
    TOO_CLOSE = "too_close"
    IN_RANGE = "in_range"
    TOO_FAR = "too_far"


@dataclass(frozen=True, slots=True)
class RangeBand:
    minimum: float = 0.0
    maximum: float = 3.0

    def __post_init__(self) -> None:
        for value, name in ((self.minimum, "minimum"), (self.maximum, "maximum")):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"range {name} must be finite")
        if self.minimum < 0:
            raise ValueError("range minimum must be non-negative")
        if self.maximum <= self.minimum:
            raise ValueError("range maximum must exceed its minimum")

    def classify(self, distance: float) -> RangeRelation:
        if (
            isinstance(distance, bool)
            or not isinstance(distance, (int, float))
            or not isfinite(distance)
            or distance < 0
        ):
            raise ValueError("distance must be finite and non-negative")
        if distance < self.minimum:
            return RangeRelation.TOO_CLOSE
        if distance > self.maximum:
            return RangeRelation.TOO_FAR
        return RangeRelation.IN_RANGE


def close_range_action(
    band: RangeBand,
    *,
    action_key: str = CLOSE_RANGE_ACTION_KEY,
    duration_ms: int = 200,
    allowed_relations: tuple[Relation, ...] = (Relation.ENEMY,),
) -> ActionSpec:
    """Build one target-relative close intent; the environment derives its vector."""

    if not isinstance(band, RangeBand):
        raise ValueError("band must be RangeBand")
    return ActionSpec(
        action_key=action_key,
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=allowed_relations,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=duration_ms,
                effects=(MoveEntity(SubjectRef.ACTOR, MovementMode.WALK),),
            ),
        ),
        features=(NamedScalar(RANGE_MAXIMUM_FEATURE, band.maximum),),
        tags=("movement", "locomotion", "range.close"),
    )


def open_range_action(
    band: RangeBand,
    *,
    action_key: str = OPEN_RANGE_ACTION_KEY,
    duration_ms: int = 200,
    allowed_relations: tuple[Relation, ...] = (Relation.ENEMY,),
) -> ActionSpec:
    """Build one target-relative retreat intent for a ranged combatant."""

    if not isinstance(band, RangeBand):
        raise ValueError("band must be RangeBand")
    if band.minimum <= 0:
        raise ValueError("an open-range band requires a positive minimum")
    return ActionSpec(
        action_key=action_key,
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=allowed_relations,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=duration_ms,
                effects=(MoveEntity(SubjectRef.ACTOR, MovementMode.WALK_AWAY),),
            ),
        ),
        features=(
            NamedScalar(RANGE_MINIMUM_FEATURE, band.minimum),
            NamedScalar(RANGE_MAXIMUM_FEATURE, band.maximum),
        ),
        tags=("movement", "locomotion", "range.open"),
    )
