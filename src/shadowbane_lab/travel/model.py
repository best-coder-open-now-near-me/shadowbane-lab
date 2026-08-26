"""Typed travel plans, observations, decisions, and bounded run results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from math import hypot, isfinite

from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.protocol import Vector2

_GO_PATTERN = re.compile(
    r"^\s*/?go\s+"
    r"(?P<lt>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?:\s*,\s*|\s+)"
    r"(?P<lg>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?:\s+(?:radius\s*=\s*)?"
    r"(?P<radius>[+]?(?:\d+(?:\.\d*)?|\.\d+)))?\s*$",
    re.IGNORECASE,
)


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


@dataclass(frozen=True, slots=True)
class TravelDestination:
    lt: float
    lg: float
    arrival_radius: float = 75.0

    def __post_init__(self) -> None:
        _finite(self.lt, "lt")
        _finite(self.lg, "lg")
        _finite(self.arrival_radius, "arrival_radius")
        if self.arrival_radius <= 0:
            raise ValueError("arrival_radius must be positive")

    def distance_from(self, position: NativePlayerPositionObservation) -> float:
        if not isinstance(position, NativePlayerPositionObservation):
            raise ValueError("position must be NativePlayerPositionObservation")
        return hypot(self.lt - position.lt, self.lg - position.lg)


@dataclass(frozen=True, slots=True)
class TravelPlan:
    plan_id: str
    destinations: tuple[TravelDestination, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan_id, str) or not self.plan_id.strip():
            raise ValueError("plan_id must be a non-empty string")
        if not self.destinations:
            raise ValueError("travel plan requires at least one destination")
        if any(not isinstance(item, TravelDestination) for item in self.destinations):
            raise ValueError("destinations must contain TravelDestination values")


def parse_go_command(command: str, *, default_arrival_radius: float = 75.0) -> TravelPlan:
    """Parse ``go LT LG`` or ``/go LT,LG`` into one typed destination."""

    if not isinstance(command, str):
        raise ValueError("go command must be a string")
    _finite(default_arrival_radius, "default_arrival_radius")
    if default_arrival_radius <= 0:
        raise ValueError("default_arrival_radius must be positive")
    match = _GO_PATTERN.fullmatch(command)
    if match is None:
        raise ValueError("go command must use: go LT LG [radius]")
    lt = float(match.group("lt"))
    lg = float(match.group("lg"))
    radius_text = match.group("radius")
    radius = default_arrival_radius if radius_text is None else float(radius_text)
    destination = TravelDestination(lt=lt, lg=lg, arrival_radius=radius)
    return TravelPlan(
        plan_id=f"go:{lt:g}:{lg:g}:{radius:g}",
        destinations=(destination,),
    )


class TravelPhase(StrEnum):
    TRAVELING = "traveling"
    COMPLETE = "complete"
    STOPPED = "stopped"


class TravelManeuver(StrEnum):
    DIRECT = "direct"
    ESCAPE_BACK_LEFT = "escape_back_left"
    ESCAPE_BACK_RIGHT = "escape_back_right"


@dataclass(frozen=True, slots=True)
class TravelControllerConfig:
    maximum_session_ms: int = 300_000
    click_interval_ms: int = 4_000
    maximum_clicks: int = 100
    minimum_progress: float = 25.0
    maximum_no_progress_clicks: int = 3
    maximum_escape_sequences: int = 3
    escape_clicks_per_sequence: int = 4
    escape_lateral_ratio: float = 0.85
    escape_widening_per_sequence: float = 0.5
    minimum_health_fraction: float = 0.5

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.maximum_session_ms, "maximum_session_ms"),
            (self.click_interval_ms, "click_interval_ms"),
            (self.maximum_clicks, "maximum_clicks"),
            (self.maximum_no_progress_clicks, "maximum_no_progress_clicks"),
            (self.escape_clicks_per_sequence, "escape_clicks_per_sequence"),
        ):
            _positive_integer(value, field_name)
        _non_negative_integer(self.maximum_escape_sequences, "maximum_escape_sequences")
        _finite(self.minimum_progress, "minimum_progress")
        if self.minimum_progress <= 0:
            raise ValueError("minimum_progress must be positive")
        for value, field_name in (
            (self.escape_lateral_ratio, "escape_lateral_ratio"),
            (self.escape_widening_per_sequence, "escape_widening_per_sequence"),
        ):
            _finite(value, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        _finite(self.minimum_health_fraction, "minimum_health_fraction")
        if not 0 < self.minimum_health_fraction <= 1:
            raise ValueError("minimum_health_fraction must be in (0, 1]")
        if self.click_interval_ms > self.maximum_session_ms:
            raise ValueError("click_interval_ms cannot exceed maximum_session_ms")


@dataclass(frozen=True, slots=True)
class TravelObservation:
    now_ms: int
    position: NativePlayerPositionObservation
    player: NativePlayerVitalsObservation

    def __post_init__(self) -> None:
        _non_negative_integer(self.now_ms, "now_ms")
        if not isinstance(self.position, NativePlayerPositionObservation):
            raise ValueError("position must be NativePlayerPositionObservation")
        if not isinstance(self.player, NativePlayerVitalsObservation):
            raise ValueError("player must be NativePlayerVitalsObservation")


@dataclass(frozen=True, slots=True)
class TravelDecision:
    decision_id: int
    now_ms: int
    phase: TravelPhase
    waypoint_index: int
    distance_remaining: float
    click_count: int
    minimap_direction: Vector2 | None = None
    maneuver: TravelManeuver | None = None
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.decision_id, "decision_id"),
            (self.now_ms, "now_ms"),
            (self.waypoint_index, "waypoint_index"),
            (self.click_count, "click_count"),
        ):
            _non_negative_integer(value, field_name)
        _finite(self.distance_remaining, "distance_remaining")
        if self.distance_remaining < 0:
            raise ValueError("distance_remaining must not be negative")
        if not isinstance(self.phase, TravelPhase):
            raise ValueError("phase must be TravelPhase")
        if self.minimap_direction is not None and not isinstance(
            self.minimap_direction, Vector2
        ):
            raise ValueError("minimap_direction must be Vector2 when present")
        if self.maneuver is not None and not isinstance(self.maneuver, TravelManeuver):
            raise ValueError("maneuver must be TravelManeuver when present")
        if (self.minimap_direction is None) != (self.maneuver is None):
            raise ValueError("a dispatched minimap direction requires exactly one maneuver")
        terminal = self.phase in (TravelPhase.COMPLETE, TravelPhase.STOPPED)
        if terminal != (self.terminal_reason is not None):
            raise ValueError("terminal travel decisions require a terminal reason")
        if terminal and self.minimap_direction is not None:
            raise ValueError("terminal travel decisions cannot dispatch input")

    @property
    def terminal(self) -> bool:
        return self.phase in (TravelPhase.COMPLETE, TravelPhase.STOPPED)


@dataclass(frozen=True, slots=True)
class TravelRunTraceStep:
    decision: TravelDecision
    position: NativePlayerPositionObservation | None
    health_fraction: float | None
    input_accepted: bool | None = None
    input_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, TravelDecision):
            raise ValueError("decision must be TravelDecision")
        if self.position is not None and not isinstance(
            self.position, NativePlayerPositionObservation
        ):
            raise ValueError("position must be NativePlayerPositionObservation when present")
        if self.health_fraction is not None:
            _finite(self.health_fraction, "health_fraction")
            if not 0 <= self.health_fraction <= 1:
                raise ValueError("health_fraction must be in [0, 1]")
        if self.input_accepted is not None and not isinstance(self.input_accepted, bool):
            raise ValueError("input_accepted must be a boolean when present")
        if self.decision.minimap_direction is None and self.input_accepted is not None:
            raise ValueError("input outcome requires a dispatched minimap direction")
        if self.input_reason is not None and self.input_accepted is not False:
            raise ValueError("input_reason is valid only for rejected input")


@dataclass(frozen=True, slots=True)
class TravelRunResult:
    final_phase: TravelPhase
    terminal_reason: str
    final_position: NativePlayerPositionObservation | None
    clicks: int
    trace: tuple[TravelRunTraceStep, ...]

    def __post_init__(self) -> None:
        if self.final_phase not in (TravelPhase.COMPLETE, TravelPhase.STOPPED):
            raise ValueError("travel run result must be terminal")
        if not isinstance(self.terminal_reason, str) or not self.terminal_reason.strip():
            raise ValueError("terminal_reason must be a non-empty string")
        _non_negative_integer(self.clicks, "clicks")
        if any(not isinstance(step, TravelRunTraceStep) for step in self.trace):
            raise ValueError("trace must contain TravelRunTraceStep values")
