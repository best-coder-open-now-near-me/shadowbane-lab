"""Field-level differential comparison with explicit tolerances and gap rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from math import isfinite
from typing import Any

from shadowbane_lab.differential.codec import trace_semantic_view
from shadowbane_lab.differential.model import TransitionTrace


class DifferenceCategory(StrEnum):
    STRUCTURE = "structure"
    TIMING = "timing"
    LEGALITY = "legality"
    RESOURCE = "resource"
    DAMAGE = "damage"
    EFFECT = "effect"
    STACKING = "stacking"
    INTERRUPTION = "interruption"
    COOLDOWN = "cooldown"
    MOVEMENT = "movement"
    TERMINATION = "termination"


class GapStatus(StrEnum):
    OPEN = "open"
    ACCEPTED_APPROXIMATION = "accepted_approximation"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class ComparisonTolerance:
    timing_ms: float = 0.0
    resource: float = 0.0
    damage: float = 0.0
    effect: float = 0.0
    movement: float = 0.0
    default_numeric: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "timing_ms",
            "resource",
            "damage",
            "effect",
            "movement",
            "default_numeric",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a finite non-negative number")

    def for_category(self, category: DifferenceCategory) -> float:
        if category is DifferenceCategory.TIMING:
            return float(self.timing_ms)
        if category is DifferenceCategory.RESOURCE:
            return float(self.resource)
        if category is DifferenceCategory.DAMAGE:
            return float(self.damage)
        if category in {DifferenceCategory.EFFECT, DifferenceCategory.STACKING}:
            return float(self.effect)
        if category is DifferenceCategory.MOVEMENT:
            return float(self.movement)
        return float(self.default_numeric)


@dataclass(frozen=True, slots=True)
class GapEntry:
    gap_id: str
    status: GapStatus
    category: DifferenceCategory
    scenario_pattern: str
    path_pattern: str
    description: str
    action_key: str | None = None
    max_absolute_delta: float | None = None
    evidence_trace_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.gap_id, "gap_id"),
            (self.scenario_pattern, "scenario_pattern"),
            (self.path_pattern, "path_pattern"),
            (self.description, "description"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.status, GapStatus):
            raise ValueError("status must be a GapStatus")
        if not isinstance(self.category, DifferenceCategory):
            raise ValueError("category must be a DifferenceCategory")
        if self.action_key is not None and (
            not isinstance(self.action_key, str) or not self.action_key.strip()
        ):
            raise ValueError("action_key must be a non-empty string or null")
        if self.max_absolute_delta is not None and (
            isinstance(self.max_absolute_delta, bool)
            or not isinstance(self.max_absolute_delta, (int, float))
            or not isfinite(self.max_absolute_delta)
            or self.max_absolute_delta < 0
        ):
            raise ValueError("max_absolute_delta must be finite and non-negative")
        for trace_id in self.evidence_trace_ids:
            if not isinstance(trace_id, str) or not trace_id.strip():
                raise ValueError("evidence trace ids must be non-empty strings")

    def accepts(self, difference: TraceDifference, scenario_id: str) -> bool:
        if self.status is not GapStatus.ACCEPTED_APPROXIMATION:
            return False
        if self.category is not difference.category:
            return False
        if not fnmatchcase(scenario_id, self.scenario_pattern):
            return False
        if not fnmatchcase(difference.path, self.path_pattern):
            return False
        if self.max_absolute_delta is None:
            return True
        return (
            difference.absolute_delta is not None
            and difference.absolute_delta <= self.max_absolute_delta
        )


@dataclass(frozen=True, slots=True)
class GapLedger:
    entries: tuple[GapEntry, ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(entry, GapEntry) for entry in self.entries):
            raise ValueError("entries must contain GapEntry values")
        ids = tuple(entry.gap_id for entry in self.entries)
        if len(ids) != len(set(ids)):
            raise ValueError("gap ids must be unique")

    def accepting_gap(self, difference: TraceDifference, scenario_id: str) -> GapEntry | None:
        return next(
            (entry for entry in self.entries if entry.accepts(difference, scenario_id)),
            None,
        )


@dataclass(frozen=True, slots=True)
class TraceDifference:
    category: DifferenceCategory
    path: str
    expected: Any
    actual: Any
    absolute_delta: float | None = None
    accepted_gap_id: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    expected_trace_id: str
    actual_trace_id: str
    differences: tuple[TraceDifference, ...]

    @property
    def exact(self) -> bool:
        return not self.differences

    @property
    def acceptable(self) -> bool:
        return all(item.accepted_gap_id is not None for item in self.differences)

    @property
    def unexpected(self) -> tuple[TraceDifference, ...]:
        return tuple(item for item in self.differences if item.accepted_gap_id is None)


def compare_traces(
    expected: TransitionTrace,
    actual: TransitionTrace,
    *,
    tolerance: ComparisonTolerance | None = None,
    gap_ledger: GapLedger | None = None,
) -> ComparisonReport:
    effective_tolerance = tolerance or ComparisonTolerance()
    effective_ledger = gap_ledger or GapLedger()
    differences: list[TraceDifference] = []
    _compare_values(
        trace_semantic_view(expected),
        trace_semantic_view(actual),
        path="trace",
        tolerance=effective_tolerance,
        output=differences,
    )
    classified = tuple(
        _classify_against_ledger(item, effective_ledger, expected.metadata.scenario_id)
        for item in differences
    )
    return ComparisonReport(
        expected_trace_id=expected.metadata.trace_id,
        actual_trace_id=actual.metadata.trace_id,
        differences=classified,
    )


def _compare_values(
    expected: Any,
    actual: Any,
    *,
    path: str,
    tolerance: ComparisonTolerance,
    output: list[TraceDifference],
) -> None:
    category = _category_for_path(path)
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual), key=str):
            child_path = f"{path}/{key}"
            if key not in expected:
                output.append(
                    TraceDifference(_category_for_path(child_path), child_path, None, actual[key])
                )
            elif key not in actual:
                output.append(
                    TraceDifference(_category_for_path(child_path), child_path, expected[key], None)
                )
            else:
                _compare_values(
                    expected[key],
                    actual[key],
                    path=child_path,
                    tolerance=tolerance,
                    output=output,
                )
        return
    if isinstance(expected, list) and isinstance(actual, list):
        if expected != actual:
            output.append(TraceDifference(category, path, expected, actual))
        return
    if _is_number(expected) and _is_number(actual):
        delta = abs(float(expected) - float(actual))
        if delta > tolerance.for_category(category):
            output.append(TraceDifference(category, path, expected, actual, delta))
        return
    if type(expected) is not type(actual) or expected != actual:
        output.append(TraceDifference(category, path, expected, actual))


def _classify_against_ledger(
    difference: TraceDifference,
    ledger: GapLedger,
    scenario_id: str,
) -> TraceDifference:
    gap = ledger.accepting_gap(difference, scenario_id)
    if gap is None:
        return difference
    return TraceDifference(
        category=difference.category,
        path=difference.path,
        expected=difference.expected,
        actual=difference.actual,
        absolute_delta=difference.absolute_delta,
        accepted_gap_id=gap.gap_id,
    )


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _category_for_path(path: str) -> DifferenceCategory:
    lower = path.lower()
    if "/affordances/" in lower or "/decisions/" in lower:
        return DifferenceCategory.LEGALITY
    if "interrupted" in lower or "interrupt" in lower:
        return DifferenceCategory.INTERRUPTION
    if "/cooldowns/" in lower:
        return DifferenceCategory.COOLDOWN
    if "/effects/" in lower:
        if "stacking_key" in lower:
            return DifferenceCategory.STACKING
        if "expires_at_ms" in lower:
            return DifferenceCategory.TIMING
        return DifferenceCategory.EFFECT
    if "/position/" in lower or "/velocity/" in lower:
        return DifferenceCategory.MOVEMENT
    if (
        "sim_time_ms" in lower
        or "busy_until_ms" in lower
        or lower.endswith("/tick")
        or "duration_ms" in lower
    ):
        return DifferenceCategory.TIMING
    if "/scalars/health" in lower or "damage_applied" in lower:
        return DifferenceCategory.DAMAGE
    if "/scalars/" in lower or "resource_" in lower:
        return DifferenceCategory.RESOURCE
    if lower.endswith("/alive") or "life_terminated" in lower or "world_terminated" in lower:
        return DifferenceCategory.TERMINATION
    return DifferenceCategory.STRUCTURE
