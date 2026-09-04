"""Display geometry and swept-circle audit against original navigation cells.

All line coordinates use X=LT, Z=-LG. Only measured trail vertices have world
height. Planned segments stay in the explicitly projected map until a verified
terrain sampler supplies elevation; no player-height plane is invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
from functools import lru_cache
from math import cos, hypot, pi, sin

from .snapshot import Snapshot

MAX_LINES = 16384
MAX_LAYER_LINES = MAX_LINES // 9


class Layer(IntFlag):
    RAW = 1
    FINAL = 2
    CORRIDOR = 4
    PHYSICAL = 8
    LEARNED = 16
    UNCERTAIN = 32
    OBJECTIVE = 64
    TRAIL = 128
    EVENTS = 256


ALL_LAYERS = sum(Layer)
WORLD_HEIGHT = 1
OVERLAP = 2


@dataclass(frozen=True, slots=True)
class Line:
    layer: int
    flags: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class Audit:
    physical_overlap_segments: tuple[int, ...]
    learned_overlap_segments: tuple[int, ...]
    model_truncated: bool
    note: str = (
        "Clearance uses original cells and the stated radius estimate; "
        "clear modeled space is not proof of collision-free terrain."
    )


@dataclass(frozen=True, slots=True)
class Geometry:
    lines: tuple[Line, ...]
    omitted_lines: int
    audit: Audit


def _point_distance2(point: tuple, start: tuple, end: tuple) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    t = (
        0
        if not length2
        else max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2))
    )
    return (point[0] - start[0] - t * dx) ** 2 + (point[1] - start[1] - t * dy) ** 2


def swept_circle_overlaps_cell(
    start: tuple, end: tuple, cell: tuple, size: float, radius: float
) -> bool:
    """Exact segment-to-AABB distance, including rounded corridor end caps."""
    x0, y0 = cell[0] * size, cell[1] * size
    x1, y1 = x0 + size, y0 + size
    if (
        max(start[0], end[0]) + radius < x0
        or min(start[0], end[0]) - radius > x1
        or max(start[1], end[1]) + radius < y0
        or min(start[1], end[1]) - radius > y1
    ):
        return False
    near, far = 0.0, 1.0
    for a, b, low, high in ((start[0], end[0], x0, x1), (start[1], end[1], y0, y1)):
        delta = b - a
        if delta == 0:
            if not low <= a <= high:
                near, far = 1.0, 0.0
                break
        else:
            left, right = sorted(((low - a) / delta, (high - a) / delta))
            near, far = max(near, left), min(far, right)
    if near <= far:
        return True

    def box_distance2(point: tuple) -> float:
        return max(x0 - point[0], 0, point[0] - x1) ** 2 + max(y0 - point[1], 0, point[1] - y1) ** 2

    distance2 = min(
        box_distance2(start),
        box_distance2(end),
        *(
            _point_distance2(corner, start, end)
            for corner in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
        ),
    )
    return distance2 <= radius * radius


def _prepare_geometry(plan, clearance, active, trail, events, route=None) -> Geometry:
    """Worker-only; per-layer budgets keep large map captures from hiding routes."""
    buckets: dict[Layer, list[Line]] = {layer: [] for layer in Layer}
    omitted = 0

    # Reserve a fair share for every layer; dense history cannot hide obstacles.
    def line(layer: Layer, start: tuple, end: tuple, flags: int = 0) -> None:
        nonlocal omitted
        if len(buckets[layer]) == MAX_LAYER_LINES:
            omitted += 1
            return

        def world(point: tuple) -> tuple[float, float, float]:
            return (point[0], point[2] if flags & WORLD_HEIGHT else 0.0, -point[1])

        buckets[layer].append(Line(int(layer), flags, world(start), world(end)))

    def path(layer: Layer, points: tuple, flags: int = 0) -> None:
        for start, end in zip(points, points[1:], strict=False):
            line(layer, start, end, flags)

    def circle(layer: Layer, center: tuple, radius: float, flags: int = 0) -> None:
        nonlocal omitted
        if len(buckets[layer]) == MAX_LAYER_LINES:
            omitted += 24
            return
        points = tuple(
            (center[0] + radius * cos(i * pi / 12), center[1] + radius * sin(i * pi / 12))
            for i in range(25)
        )
        path(layer, points, flags)

    physical_hits: list[int] = []
    learned_hits: list[int] = []
    truncated = False
    execution = route
    if plan is not None:
        path(Layer.RAW, plan.raw_path)
        # The route begins at the real search start and uses the actual issued
        # destinations, including a non-cell-centered final destination.
        route = (
            (execution.start,) + tuple(p[:2] for p in execution.destinations)
            if execution is not None
            else (plan.start,) + tuple(p[:2] for p in plan.destinations)
        )
        path(Layer.FINAL, route)
        radius = clearance.radius
        for index, (start, end) in enumerate(zip(route, route[1:], strict=False)):
            physical = any(
                swept_circle_overlaps_cell(start, end, cell, plan.cell_size, radius)
                for cell in plan.physical_blocked
            )
            learned = any(
                swept_circle_overlaps_cell(start, end, cell, plan.cell_size, radius)
                for cell in plan.learned_blocked
            )
            if physical:
                physical_hits.append(index)
            if learned:
                learned_hits.append(index)
            flags = OVERLAP if physical or learned else 0
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = hypot(dx, dy)
            if length:
                nx, ny = -dy * radius / length, dx * radius / length
                for sign in (-1, 1):
                    line(
                        Layer.CORRIDOR,
                        (start[0] + sign * nx, start[1] + sign * ny),
                        (end[0] + sign * nx, end[1] + sign * ny),
                        flags,
                    )
            circle(Layer.CORRIDOR, start, radius, flags)
            circle(Layer.CORRIDOR, end, radius, flags)
        for layer, cells in (
            (Layer.PHYSICAL, plan.physical_blocked),
            (Layer.LEARNED, plan.learned_blocked),
            (Layer.UNCERTAIN, plan.costs),
        ):
            for x, y, *_ in cells:
                x0, y0 = x * plan.cell_size, y * plan.cell_size
                x1, y1 = x0 + plan.cell_size, y0 + plan.cell_size
                path(layer, ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)))
        circle(Layer.OBJECTIVE, plan.destination, plan.destination[2])
        truncated = bool(
            plan.omitted_map_cells
            or plan.omitted_route_points
            or (execution is not None and execution.omitted_destinations)
        )
    elif execution is not None:
        path(Layer.FINAL, (execution.start,) + tuple(p[:2] for p in execution.destinations))
        circle(Layer.OBJECTIVE, execution.destinations[-1], execution.destinations[-1][2])
        truncated = bool(execution.omitted_destinations)
    if active is not None and active.destination is not None:
        circle(Layer.OBJECTIVE, active.destination, active.destination[2])
        if active.position is not None:
            line(Layer.OBJECTIVE, active.position, active.destination)
    path(Layer.TRAIL, trail, WORLD_HEIGHT)
    for event in events:
        if event.value.position is not None and event.value.event in (
            "stall",
            "failure",
            "escape_planned",
            "replan",
            "completion",
            "cancelled",
        ):
            circle(Layer.EVENTS, event.value.position, max(2.0, clearance.radius))
    result: list[Line] = []
    for layer in (
        Layer.OBJECTIVE,
        Layer.FINAL,
        Layer.TRAIL,
        Layer.EVENTS,
        Layer.RAW,
        Layer.CORRIDOR,
        Layer.PHYSICAL,
        Layer.LEARNED,
        Layer.UNCERTAIN,
    ):
        available = MAX_LINES - len(result)
        result.extend(buckets[layer][:available])
        omitted += max(0, len(buckets[layer]) - available)
    return Geometry(
        tuple(result), omitted, Audit(tuple(physical_hits), tuple(learned_hits), truncated)
    )


@lru_cache(maxsize=4)
def _plan_geometry(plan, clearance, route) -> Geometry:
    # Auditing map cells is plan work. Do it once per immutable plan/radius,
    # not once for every position sample or camera frame.
    return _prepare_geometry(plan, clearance, None, (), (), route)


def prepare_geometry(snapshot: Snapshot) -> Geometry:
    plan = _plan_geometry(snapshot.plan, snapshot.clearance, snapshot.route)
    movement = _prepare_geometry(
        None, snapshot.clearance, snapshot.active, snapshot.trail, snapshot.events
    )
    combined = movement.lines + plan.lines
    return Geometry(
        combined[:MAX_LINES],
        plan.omitted_lines + movement.omitted_lines + max(0, len(combined) - MAX_LINES),
        plan.audit,
    )
