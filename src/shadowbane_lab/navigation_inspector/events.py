"""Immutable diagnostic events; failures never enter the navigation control path."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

MAX_ROUTE_POINTS = 4096
MAX_MAP_CELLS = 4096

Point2 = tuple[float, float]
Destination = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class PlanEvent:
    """The actual search result, including the unexpanded physical map evidence.

    LT/LG are world coordinates. Blocker tuples are cell indices; their bounds
    are [index * cell_size, (index + 1) * cell_size]. An omitted sample is counted
    explicitly so consumers cannot interpret an incomplete map as clear space.
    """

    kind: Literal["plan"]
    start: Point2
    destination: Destination
    cell_size: float
    planner_clearance_cells: int
    raw_path: tuple[Point2, ...]
    smoothed_path: tuple[Point2, ...]
    destinations: tuple[Destination, ...]
    physical_blocked: tuple[tuple[int, int], ...]
    learned_blocked: tuple[tuple[int, int], ...]
    costs: tuple[tuple[int, int, float], ...]
    expanded_cells: int
    total_cost: float
    mode: Literal["complete", "frontier", "failed"]
    failure_reason: str | None
    omitted_route_points: int = 0
    omitted_map_cells: int = 0


@dataclass(frozen=True, slots=True)
class MotionEvent:
    """An observation or decision emitted by its controller owner.

    command_requested is a controller intent, not proof that input was accepted
    or that movement occurred. Position samples are the movement authority.
    """

    kind: Literal["motion"]
    event: str
    plan_id: str
    now_ms: int
    position: tuple[float, float, float] | None = None
    waypoint_index: int | None = None
    destination: Destination | None = None
    direction: Point2 | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ContextEvent:
    """Observed zone and map identity; navigation evidence is not collision geometry."""

    kind: Literal["context"]
    zone_token: str | None
    map_token: str
    obstacle_provenance: str
    height_provenance: str = "unknown: final world elevation is not observed"


@dataclass(frozen=True, slots=True)
class RouteEvent:
    """The route currently owned by movement, independent of the latest search."""

    kind: Literal["route"]
    plan_id: str
    start: Point2
    destinations: tuple[Destination, ...]
    omitted_destinations: int = 0


DiagnosticEvent = PlanEvent | MotionEvent | ContextEvent | RouteEvent
DiagnosticObserver = Callable[[DiagnosticEvent], None]


def emit(observer: DiagnosticObserver | None, event: DiagnosticEvent) -> None:
    """Diagnostics are optional and must never abort a navigation decision."""
    if observer is not None:
        try:
            observer(event)
        except Exception:
            # Transport, UI and third-party observers do not own movement policy.
            pass
