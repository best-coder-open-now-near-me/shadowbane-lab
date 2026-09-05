"""Bounded weighted A* over sparse, world-coordinate navigation costs."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field, replace
from itertools import pairwise
from math import floor, hypot, inf, isclose, isfinite, sqrt
from typing import Literal

from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.navigation_inspector.events import (
    MAX_MAP_CELLS,
    MAX_ROUTE_POINTS,
    DiagnosticObserver,
    PlanEvent,
    emit,
)
from shadowbane_lab.travel.model import TravelDestination


@dataclass(frozen=True, order=True, slots=True)
class NavigationCell:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class WeightedAStarConfig:
    heuristic_weight: float = 1.1
    maximum_expansions: int = 8_000
    planning_margin_cells: int = 8
    obstacle_clearance_cells: int = 1
    waypoint_radius_fraction: float = 0.4

    def __post_init__(self) -> None:
        if (
            isinstance(self.heuristic_weight, bool)
            or not isinstance(self.heuristic_weight, (int, float))
            or not isfinite(self.heuristic_weight)
            or self.heuristic_weight < 1
        ):
            raise ValueError("heuristic_weight must be finite and at least one")
        for value, field_name in (
            (self.maximum_expansions, "maximum_expansions"),
            (self.planning_margin_cells, "planning_margin_cells"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if (
            isinstance(self.obstacle_clearance_cells, bool)
            or not isinstance(self.obstacle_clearance_cells, int)
            or self.obstacle_clearance_cells < 0
        ):
            raise ValueError("obstacle_clearance_cells must be a non-negative integer")
        if (
            isinstance(self.waypoint_radius_fraction, bool)
            or not isinstance(self.waypoint_radius_fraction, (int, float))
            or not isfinite(self.waypoint_radius_fraction)
            or not 0 < self.waypoint_radius_fraction < 1
        ):
            raise ValueError("waypoint_radius_fraction must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class NavigationCostGrid:
    cell_size: float
    minimum: NavigationCell
    maximum: NavigationCell
    blocked: frozenset[NavigationCell] = frozenset()
    costs: tuple[tuple[NavigationCell, float], ...] = ()
    physical_blocked: frozenset[NavigationCell] = frozenset()
    _cost_index: dict[NavigationCell, float] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.cell_size, bool)
            or not isinstance(self.cell_size, (int, float))
            or not isfinite(self.cell_size)
            or self.cell_size <= 0
        ):
            raise ValueError("cell_size must be finite and positive")
        if not isinstance(self.minimum, NavigationCell) or not isinstance(
            self.maximum, NavigationCell
        ):
            raise ValueError("grid bounds must be NavigationCell values")
        if self.minimum.x > self.maximum.x or self.minimum.y > self.maximum.y:
            raise ValueError("grid minimum must not exceed maximum")
        if any(not self.contains(cell) for cell in self.blocked):
            raise ValueError("blocked cells must lie inside the grid")
        seen: set[NavigationCell] = set()
        for cell, cost in self.costs:
            if not isinstance(cell, NavigationCell) or not self.contains(cell):
                raise ValueError("cost cells must lie inside the grid")
            if cell in seen:
                raise ValueError("cost cells must be unique")
            if (
                isinstance(cost, bool)
                or not isinstance(cost, (int, float))
                or not isfinite(cost)
                or cost < 1
            ):
                raise ValueError("traversal costs must be finite and at least one")
            seen.add(cell)
        object.__setattr__(self, "_cost_index", dict(self.costs))

    def contains(self, cell: NavigationCell) -> bool:
        return (
            self.minimum.x <= cell.x <= self.maximum.x
            and self.minimum.y <= cell.y <= self.maximum.y
        )

    def traversal_cost(self, cell: NavigationCell) -> float:
        return self._cost_index.get(cell, 1.0)

    def cell_for(self, lt: float, lg: float) -> NavigationCell:
        return NavigationCell(floor(lt / self.cell_size), floor(lg / self.cell_size))

    def center(self, cell: NavigationCell) -> tuple[float, float]:
        return (
            (cell.x + 0.5) * self.cell_size,
            (cell.y + 0.5) * self.cell_size,
        )


@dataclass(frozen=True, slots=True)
class AStarRoute:
    cells: tuple[NavigationCell, ...]
    destinations: tuple[TravelDestination, ...]
    expanded_cells: int
    total_cost: float

    def __post_init__(self) -> None:
        if not self.cells or not self.destinations:
            raise ValueError("A* route must contain cells and destinations")
        if (
            isinstance(self.expanded_cells, bool)
            or not isinstance(self.expanded_cells, int)
            or self.expanded_cells <= 0
        ):
            raise ValueError("expanded_cells must be a positive integer")
        if not isfinite(self.total_cost) or self.total_cost < 0:
            raise ValueError("total_cost must be finite and non-negative")


class AStarRouteNotFound(RuntimeError):
    """Raised when bounded A* cannot connect the requested endpoints."""


@dataclass(frozen=True, slots=True)
class NavigationPlanningWindow:
    """Bounded terrain coverage around one active navigation refresh origin."""

    center_lt: float
    center_lg: float
    radius: float
    refresh_distance: float

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.center_lt, "center_lt"),
            (self.center_lg, "center_lg"),
            (self.radius, "radius"),
            (self.refresh_distance, "refresh_distance"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{field_name} must be finite")
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        if not 0 < self.refresh_distance < self.radius:
            raise ValueError("refresh_distance must be in (0, radius)")

    def contains(self, destination: TravelDestination) -> bool:
        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be a TravelDestination")
        return (
            hypot(
                destination.lt - self.center_lt,
                destination.lg - self.center_lg,
            )
            <= self.radius
        )


@dataclass(frozen=True, slots=True)
class NavigationMapSnapshot:
    """One revision of the sparse global navigation map available to a route."""

    token: str
    navigation_map: SparseNavigationMap
    planning_window: NavigationPlanningWindow | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not self.token.strip():
            raise ValueError("navigation snapshot token must be non-empty")
        if not isinstance(self.navigation_map, SparseNavigationMap):
            raise ValueError("navigation snapshot requires a SparseNavigationMap")
        if self.planning_window is not None and not isinstance(
            self.planning_window,
            NavigationPlanningWindow,
        ):
            raise ValueError("planning_window must be a NavigationPlanningWindow or None")


class SparseNavigationMap:
    """Persistent learned obstacles and costs keyed in global LT/LG cells."""

    def __init__(self, *, cell_size: float = 20.0, refinement_factor: int = 2) -> None:
        if (
            isinstance(cell_size, bool)
            or not isinstance(cell_size, (int, float))
            or not isfinite(cell_size)
            or cell_size <= 0
        ):
            raise ValueError("cell_size must be finite and positive")
        if (
            isinstance(refinement_factor, bool)
            or not isinstance(refinement_factor, int)
            or refinement_factor < 2
        ):
            raise ValueError("refinement_factor must be an integer of at least two")
        self._cell_size = float(cell_size)
        self._refinement_factor = refinement_factor
        self._blocked: set[NavigationCell] = set()
        self._structural_blocked: set[NavigationCell] = set()
        self._learned_blocked: set[NavigationCell] = set()
        self._refined_learned_blocked: set[NavigationCell] = set()
        self._costs: dict[NavigationCell, float] = {}

    @property
    def cell_size(self) -> float:
        return self._cell_size

    @property
    def refinement_factor(self) -> int:
        return self._refinement_factor

    @property
    def refined_cell_size(self) -> float:
        return self._cell_size / self._refinement_factor

    @property
    def blocked(self) -> frozenset[NavigationCell]:
        return frozenset(self._blocked)

    @property
    def learned_blocked(self) -> frozenset[NavigationCell]:
        """Coarse cells containing collision evidence from failed movement."""

        return frozenset(self._learned_blocked)

    @property
    def refined_learned_blocked(self) -> frozenset[NavigationCell]:
        """Precise fine cells inferred from live failed movement."""

        return frozenset(self._refined_learned_blocked)

    def cell_for(self, lt: float, lg: float) -> NavigationCell:
        return NavigationCell(floor(lt / self._cell_size), floor(lg / self._cell_size))

    def center(self, cell: NavigationCell) -> tuple[float, float]:
        if not isinstance(cell, NavigationCell):
            raise ValueError("cell must be NavigationCell")
        return (
            (cell.x + 0.5) * self._cell_size,
            (cell.y + 0.5) * self._cell_size,
        )

    def mark_blocked_ahead(
        self,
        position: NativePlayerPositionObservation,
        destination: TravelDestination,
    ) -> NavigationCell:
        if not isinstance(position, NativePlayerPositionObservation):
            raise ValueError("position must be NativePlayerPositionObservation")
        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be TravelDestination")
        delta_lt = destination.lt - position.lt
        delta_lg = destination.lg - position.lg
        length = hypot(delta_lt, delta_lg)
        if length == 0:
            raise ValueError("cannot infer an obstacle without a movement direction")
        probe_distance = self._cell_size * 0.75
        cell = self.cell_for(
            position.lt + delta_lt / length * probe_distance,
            position.lg + delta_lg / length * probe_distance,
        )
        current = self.cell_for(position.lt, position.lg)
        if cell == current:
            step_x = 0 if delta_lt == 0 else (1 if delta_lt > 0 else -1)
            step_y = 0 if delta_lg == 0 else (1 if delta_lg > 0 else -1)
            boundary_lt = (current.x + (1 if step_x > 0 else 0)) * self._cell_size
            boundary_lg = (current.y + (1 if step_y > 0 else 0)) * self._cell_size
            crossing_lt = abs((boundary_lt - position.lt) / delta_lt) if step_x else inf
            crossing_lg = abs((boundary_lg - position.lg) / delta_lg) if step_y else inf
            if isclose(crossing_lt, crossing_lg, rel_tol=1e-9, abs_tol=1e-12):
                cell = NavigationCell(current.x + step_x, current.y + step_y)
            elif crossing_lt < crossing_lg:
                cell = NavigationCell(current.x + step_x, current.y)
            else:
                cell = NavigationCell(current.x, current.y + step_y)
        refined = self._refined_cell_entered(
            cell,
            position.lt,
            position.lg,
            delta_lt / length,
            delta_lg / length,
        )
        self.mark_refined_learned_blocked(cell, refined)
        return cell

    def mark_blocked(self, cell: NavigationCell) -> None:
        if not isinstance(cell, NavigationCell):
            raise ValueError("cell must be NavigationCell")
        self._blocked.add(cell)
        self._structural_blocked.add(cell)
        self._costs.pop(cell, None)

    def mark_learned_blocked(self, cell: NavigationCell) -> None:
        """Retain coarse collision evidence whose exact subcell is unavailable."""

        if not isinstance(cell, NavigationCell):
            raise ValueError("cell must be NavigationCell")
        self._blocked.add(cell)
        self._learned_blocked.add(cell)
        self._refined_learned_blocked.update(self._refined_children(cell))

    def mark_refined_learned_blocked(
        self,
        cell: NavigationCell,
        refined_cell: NavigationCell,
    ) -> None:
        """Retain a collision at fine precision while preserving coarse routing."""

        if not isinstance(cell, NavigationCell) or not isinstance(refined_cell, NavigationCell):
            raise ValueError("cell and refined_cell must be NavigationCell values")
        if self._coarse_parent(refined_cell) != cell:
            raise ValueError("refined learned blocker must belong to its coarse cell")
        self._blocked.add(cell)
        self._learned_blocked.add(cell)
        self._refined_learned_blocked.add(refined_cell)

    def refined_navigation_map(self) -> SparseNavigationMap:
        """Build a fine planning view without inventing gaps in known walls.

        Structural blockers occupy every child cell. A live collision blocks only
        the measured child cell. Terrain and foliage costs stay traversable and
        are copied to every child so tactical routes may still cross them.
        """

        refined = SparseNavigationMap(
            cell_size=self.refined_cell_size,
            refinement_factor=self._refinement_factor,
        )
        for cell in self._structural_blocked:
            for child in self._refined_children(cell):
                refined._blocked.add(child)
                refined._structural_blocked.add(child)
        children_by_parent: dict[NavigationCell, set[NavigationCell]] = {}
        for child in self._refined_learned_blocked:
            children_by_parent.setdefault(self._coarse_parent(child), set()).add(child)
        for cell in self._learned_blocked:
            if cell in self._structural_blocked:
                continue
            children = children_by_parent.get(cell)
            if not children:
                children = set(self._refined_children(cell))
            for child in children:
                refined._blocked.add(child)
                refined._learned_blocked.add(child)
        for cell, cost in self._costs.items():
            for child in self._refined_children(cell):
                if child not in refined._blocked:
                    refined._costs[child] = cost
        return refined

    def _refined_children(self, cell: NavigationCell) -> tuple[NavigationCell, ...]:
        origin_x = cell.x * self._refinement_factor
        origin_y = cell.y * self._refinement_factor
        return tuple(
            NavigationCell(origin_x + delta_x, origin_y + delta_y)
            for delta_x in range(self._refinement_factor)
            for delta_y in range(self._refinement_factor)
        )

    def _coarse_parent(self, cell: NavigationCell) -> NavigationCell:
        return NavigationCell(
            cell.x // self._refinement_factor,
            cell.y // self._refinement_factor,
        )

    def _refined_cell_entered(
        self,
        cell: NavigationCell,
        start_lt: float,
        start_lg: float,
        direction_lt: float,
        direction_lg: float,
    ) -> NavigationCell:
        minimum_lt = cell.x * self._cell_size
        maximum_lt = minimum_lt + self._cell_size
        minimum_lg = cell.y * self._cell_size
        maximum_lg = minimum_lg + self._cell_size
        crossings = [0.0]
        if direction_lt > 0:
            crossings.append((minimum_lt - start_lt) / direction_lt)
        elif direction_lt < 0:
            crossings.append((maximum_lt - start_lt) / direction_lt)
        if direction_lg > 0:
            crossings.append((minimum_lg - start_lg) / direction_lg)
        elif direction_lg < 0:
            crossings.append((maximum_lg - start_lg) / direction_lg)
        entry_distance = max(crossings)
        epsilon = self.refined_cell_size * 1e-6
        refined = NavigationCell(
            floor((start_lt + direction_lt * (entry_distance + epsilon)) / self.refined_cell_size),
            floor((start_lg + direction_lg * (entry_distance + epsilon)) / self.refined_cell_size),
        )
        if self._coarse_parent(refined) != cell:
            raise RuntimeError("refined collision inference left the selected coarse cell")
        return refined

    def set_cost(self, cell: NavigationCell, cost: float) -> None:
        if not isinstance(cell, NavigationCell):
            raise ValueError("cell must be NavigationCell")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not isfinite(cost)
            or cost < 1
        ):
            raise ValueError("cost must be finite and at least one")
        if cell in self._structural_blocked:
            raise ValueError("structural blockers cannot also have a traversal cost")
        self._costs[cell] = float(cost)

    def local_grid(
        self,
        start: NavigationCell,
        goal: NavigationCell,
        config: WeightedAStarConfig,
    ) -> NavigationCostGrid:
        if not isinstance(start, NavigationCell) or not isinstance(goal, NavigationCell):
            raise ValueError("start and goal must be NavigationCell values")
        if not isinstance(config, WeightedAStarConfig):
            raise ValueError("config must be WeightedAStarConfig")
        margin = config.planning_margin_cells
        minimum = NavigationCell(min(start.x, goal.x) - margin, min(start.y, goal.y) - margin)
        maximum = NavigationCell(max(start.x, goal.x) + margin, max(start.y, goal.y) + margin)
        blocked: set[NavigationCell] = set()
        clearance = config.obstacle_clearance_cells
        for obstacle in self._blocked:
            if not (
                minimum.x - clearance <= obstacle.x <= maximum.x + clearance
                and minimum.y - clearance <= obstacle.y <= maximum.y + clearance
            ):
                continue
            for delta_x in range(-clearance, clearance + 1):
                for delta_y in range(-clearance, clearance + 1):
                    candidate = NavigationCell(obstacle.x + delta_x, obstacle.y + delta_y)
                    if (
                        minimum.x <= candidate.x <= maximum.x
                        and minimum.y <= candidate.y <= maximum.y
                    ):
                        blocked.add(candidate)
        # Permit escape from the occupied start cell and preserve the existing
        # free-destination clearance exception, never erase a physical endpoint.
        blocked.discard(start)
        if goal not in self._blocked:
            blocked.discard(goal)
        costs = tuple(
            sorted(
                (cell, cost)
                for cell, cost in self._costs.items()
                if (
                    minimum.x <= cell.x <= maximum.x
                    and minimum.y <= cell.y <= maximum.y
                    and cell not in blocked
                )
            )
        )
        return NavigationCostGrid(
            cell_size=self._cell_size,
            minimum=minimum,
            maximum=maximum,
            blocked=frozenset(blocked),
            costs=costs,
            physical_blocked=frozenset(
                cell
                for cell in self._blocked
                if (minimum.x <= cell.x <= maximum.x and minimum.y <= cell.y <= maximum.y)
            ),
        )


class WeightedAStarPlanner:
    def __init__(
        self,
        config: WeightedAStarConfig | None = None,
        *,
        observer: DiagnosticObserver | None = None,
    ) -> None:
        if config is not None and not isinstance(config, WeightedAStarConfig):
            raise ValueError("config must be WeightedAStarConfig")
        self._config = config or WeightedAStarConfig()
        self._observer = observer

    @property
    def observer(self) -> DiagnosticObserver | None:
        return self._observer

    @property
    def config(self) -> WeightedAStarConfig:
        return self._config

    def plan(
        self,
        navigation_map: SparseNavigationMap,
        *,
        start_lt: float,
        start_lg: float,
        destination: TravelDestination,
    ) -> AStarRoute:
        if not isinstance(navigation_map, SparseNavigationMap):
            raise ValueError("navigation_map must be SparseNavigationMap")
        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be TravelDestination")
        start = navigation_map.cell_for(start_lt, start_lg)
        goal = navigation_map.cell_for(destination.lt, destination.lg)
        grid = navigation_map.local_grid(start, goal, self._config)
        try:
            if (
                goal in navigation_map.blocked
                and hypot(destination.lt - start_lt, destination.lg - start_lg)
                <= destination.arrival_radius
            ):
                # Arrival is already satisfied without entering a blocked cell.
                cells, expanded, total_cost = (start,), 1, 0.0
                endpoint = TravelDestination(start_lt, start_lg, destination.arrival_radius)
            else:
                blocked_destination = destination if goal in navigation_map.blocked else None
                cells, expanded, total_cost = self._search(
                    grid, start, goal, arrival_region=blocked_destination
                )
                point = self._arrival_point(grid, cells[-1], destination)
                endpoint = (
                    destination
                    if blocked_destination is None
                    else TravelDestination(
                        *point,
                        arrival_radius=min(
                            grid.cell_size * 0.1,
                            (
                                destination.arrival_radius
                                - hypot(point[0] - destination.lt, point[1] - destination.lg)
                            )
                            * 0.5,
                            point[0] - cells[-1].x * grid.cell_size,
                            (cells[-1].x + 1) * grid.cell_size - point[0],
                            point[1] - cells[-1].y * grid.cell_size,
                            (cells[-1].y + 1) * grid.cell_size - point[1],
                        ),
                    )
                )
        except AStarRouteNotFound as exc:
            self._emit_plan(
                navigation_map,
                grid,
                start_lt,
                start_lg,
                destination,
                (),
                (),
                (),
                0,
                0.0,
                "failed",
                str(exc),
            )
            raise
        smoothed = self._smooth(grid, cells)
        waypoint_radius = max(5.0, grid.cell_size * self._config.waypoint_radius_fraction)
        destinations = [
            TravelDestination(*grid.center(cell), arrival_radius=waypoint_radius)
            for cell in smoothed[1:-1]
        ]
        if endpoint != destination and len(smoothed) > 1:
            destinations.append(
                TravelDestination(*grid.center(smoothed[-1]), arrival_radius=waypoint_radius)
            )
        destinations.append(endpoint)
        self._emit_plan(
            navigation_map,
            grid,
            start_lt,
            start_lg,
            destination,
            cells,
            smoothed,
            tuple(destinations),
            expanded,
            total_cost,
            "complete",
            None,
        )
        return AStarRoute(
            cells=smoothed,
            destinations=tuple(destinations),
            expanded_cells=expanded,
            total_cost=total_cost,
        )

    def plan_refined(
        self,
        navigation_map: SparseNavigationMap,
        *,
        start_lt: float,
        start_lg: float,
        destination: TravelDestination,
        maximum_distance: float | None = None,
    ) -> AStarRoute:
        """Plan on the fine collision grid, optionally for one local route slice."""

        if not isinstance(navigation_map, SparseNavigationMap):
            raise ValueError("navigation_map must be SparseNavigationMap")
        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be TravelDestination")
        if maximum_distance is not None and (
            isinstance(maximum_distance, bool)
            or not isinstance(maximum_distance, (int, float))
            or not isfinite(maximum_distance)
            or maximum_distance <= 0
        ):
            raise ValueError("maximum_distance must be finite and positive when present")
        refined_destination = destination
        distance = hypot(destination.lt - start_lt, destination.lg - start_lg)
        if maximum_distance is not None and distance > maximum_distance:
            direction_lt = (destination.lt - start_lt) / distance
            direction_lg = (destination.lg - start_lg) / distance
            refined_destination = TravelDestination(
                start_lt + direction_lt * maximum_distance,
                start_lg + direction_lg * maximum_distance,
                arrival_radius=max(
                    5.0,
                    navigation_map.refined_cell_size * self._config.waypoint_radius_fraction,
                ),
            )
        refined_map = navigation_map.refined_navigation_map()
        refined_config = replace(
            self._config,
            planning_margin_cells=(
                self._config.planning_margin_cells * navigation_map.refinement_factor
            ),
            obstacle_clearance_cells=max(1, self._config.obstacle_clearance_cells),
        )
        return WeightedAStarPlanner(
            refined_config,
            observer=self._observer,
        ).plan(
            refined_map,
            start_lt=start_lt,
            start_lg=start_lg,
            destination=refined_destination,
        )

    def plan_reachable_frontier(
        self,
        navigation_map: SparseNavigationMap,
        *,
        start_lt: float,
        start_lg: float,
        destination: TravelDestination,
    ) -> AStarRoute:
        """Route to a safely reachable planning-window edge without crossing a barrier.

        The closest cell to a blocked goal is commonly the near face of the
        obstacle.  Stopping there leaves the next bounded plan with the same
        disconnected grid.  Prefer a reachable edge cell instead so the next
        local window can slide laterally and reveal a route around large
        structures.  Search and expansion limits remain unchanged.
        """

        if not isinstance(navigation_map, SparseNavigationMap):
            raise ValueError("navigation_map must be SparseNavigationMap")
        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be TravelDestination")
        start = navigation_map.cell_for(start_lt, start_lg)
        goal = navigation_map.cell_for(destination.lt, destination.lg)
        grid = navigation_map.local_grid(start, goal, self._config)
        try:
            cells, expanded, total_cost = self._search(
                grid,
                start,
                goal,
                allow_partial=True,
            )
        except AStarRouteNotFound as exc:
            self._emit_plan(
                navigation_map,
                grid,
                start_lt,
                start_lg,
                destination,
                (),
                (),
                (),
                0,
                0.0,
                "failed",
                str(exc),
            )
            raise
        smoothed = self._smooth(grid, cells)
        waypoint_radius = max(5.0, grid.cell_size * self._config.waypoint_radius_fraction)
        frontier = smoothed[-1]
        frontier_destination = (
            destination
            if frontier == goal
            else TravelDestination(
                *grid.center(frontier),
                arrival_radius=waypoint_radius,
            )
        )
        destinations = [
            TravelDestination(*grid.center(cell), arrival_radius=waypoint_radius)
            for cell in smoothed[1:-1]
        ]
        destinations.append(frontier_destination)
        self._emit_plan(
            navigation_map,
            grid,
            start_lt,
            start_lg,
            destination,
            cells,
            smoothed,
            tuple(destinations),
            expanded,
            total_cost,
            "complete" if frontier == goal else "frontier",
            None,
        )
        return AStarRoute(
            cells=smoothed,
            destinations=tuple(destinations),
            expanded_cells=expanded,
            total_cost=total_cost,
        )

    def _emit_plan(
        self,
        navigation_map: SparseNavigationMap,
        grid: NavigationCostGrid,
        start_lt: float,
        start_lg: float,
        destination: TravelDestination,
        cells: tuple[NavigationCell, ...],
        smoothed: tuple[NavigationCell, ...],
        destinations: tuple[TravelDestination, ...],
        expanded: int,
        total_cost: float,
        mode: Literal["complete", "frontier", "failed"],
        failure_reason: str | None,
    ) -> None:
        if self._observer is None:
            return
        try:
            # Use physical cells, never the planner's clearance-expanded grid.
            learned = navigation_map.learned_blocked
            physical = tuple(
                sorted(cell for cell in navigation_map.blocked - learned if grid.contains(cell))
            )
            learned = tuple(sorted(cell for cell in learned if grid.contains(cell)))
            costs = grid.costs
            emit(
                self._observer,
                PlanEvent(
                    kind="plan",
                    start=(start_lt, start_lg),
                    destination=(destination.lt, destination.lg, destination.arrival_radius),
                    cell_size=grid.cell_size,
                    planner_clearance_cells=self._config.obstacle_clearance_cells,
                    raw_path=tuple(grid.center(cell) for cell in cells[:MAX_ROUTE_POINTS]),
                    smoothed_path=tuple(grid.center(cell) for cell in smoothed[:MAX_ROUTE_POINTS]),
                    destinations=tuple(
                        (item.lt, item.lg, item.arrival_radius)
                        for item in destinations[:MAX_ROUTE_POINTS]
                    ),
                    physical_blocked=tuple((cell.x, cell.y) for cell in physical[:MAX_MAP_CELLS]),
                    learned_blocked=tuple((cell.x, cell.y) for cell in learned[:MAX_MAP_CELLS]),
                    costs=tuple((cell.x, cell.y, cost) for cell, cost in costs[:MAX_MAP_CELLS]),
                    expanded_cells=expanded,
                    total_cost=total_cost,
                    mode=mode,
                    failure_reason=failure_reason,
                    omitted_route_points=sum(
                        max(0, len(items) - MAX_ROUTE_POINTS)
                        for items in (cells, smoothed, destinations)
                    ),
                    omitted_map_cells=sum(
                        max(0, len(items) - MAX_MAP_CELLS) for items in (physical, learned, costs)
                    ),
                ),
            )
        except Exception:
            # Preparing diagnostics also cannot change a successful route result.
            pass

    def _search(
        self,
        grid: NavigationCostGrid,
        start: NavigationCell,
        goal: NavigationCell,
        *,
        allow_partial: bool = False,
        arrival_region: TravelDestination | None = None,
    ) -> tuple[tuple[NavigationCell, ...], int, float]:
        if start in grid.blocked or (
            goal in grid.blocked and not allow_partial and arrival_region is None
        ):
            raise AStarRouteNotFound("A* endpoint is blocked")
        frontier: list[tuple[float, int, NavigationCell]] = []
        order = 0
        heapq.heappush(frontier, (0.0, order, start))
        came_from: dict[NavigationCell, NavigationCell] = {}
        cost_so_far = {start: 0.0}
        expanded = 0
        closest = start
        closest_heuristic = self._heuristic(start, goal)
        boundary_frontier: NavigationCell | None = None
        boundary_key: tuple[float, float, int, int] | None = None
        while frontier:
            _, _, current = heapq.heappop(frontier)
            expanded += 1
            current_heuristic = self._heuristic(current, goal)
            if current_heuristic < closest_heuristic or (
                current_heuristic == closest_heuristic
                and cost_so_far[current] < cost_so_far[closest]
            ):
                closest = current
                closest_heuristic = current_heuristic
            if current != start and self._is_boundary_cell(grid, current):
                candidate_key = (
                    current_heuristic,
                    cost_so_far[current],
                    current.x,
                    current.y,
                )
                if boundary_key is None or candidate_key < boundary_key:
                    boundary_frontier = current
                    boundary_key = candidate_key
            if expanded > self._config.maximum_expansions:
                partial = boundary_frontier or (closest if closest != start else None)
                if allow_partial and partial is not None:
                    return (
                        self._reconstruct(came_from, start, partial),
                        expanded,
                        cost_so_far[partial],
                    )
                raise AStarRouteNotFound("A* expansion budget exhausted")
            arrived = (
                current == goal
                and current not in grid.blocked
                and (arrival_region is None or current not in grid.physical_blocked)
            )
            if arrival_region is not None and current not in grid.physical_blocked:
                point = self._arrival_point(grid, current, arrival_region)
                arrived = (
                    hypot(point[0] - arrival_region.lt, point[1] - arrival_region.lg)
                    < arrival_region.arrival_radius
                )
            if arrived:
                return self._reconstruct(came_from, start, current), expanded, cost_so_far[current]
            for neighbor, step_cost in self._neighbors(grid, current):
                new_cost = cost_so_far[current] + step_cost * grid.traversal_cost(neighbor)
                if new_cost >= cost_so_far.get(neighbor, float("inf")):
                    continue
                cost_so_far[neighbor] = new_cost
                came_from[neighbor] = current
                order += 1
                priority = new_cost + self._config.heuristic_weight * self._heuristic(
                    neighbor, goal
                )
                heapq.heappush(frontier, (priority, order, neighbor))
        partial = boundary_frontier or (closest if closest != start else None)
        if allow_partial and partial is not None:
            return (
                self._reconstruct(came_from, start, partial),
                expanded,
                cost_so_far[partial],
            )
        raise AStarRouteNotFound("A* found no route inside the planning window")

    @staticmethod
    def _arrival_point(
        grid: NavigationCostGrid, cell: NavigationCell, destination: TravelDestination
    ) -> tuple[float, float]:
        # Keep the endpoint strictly inside the reachable cell. A small arrival
        # region may intersect a cell without containing its center.
        inset = grid.cell_size * 1e-6
        nearest = (
            min(
                max(destination.lt, cell.x * grid.cell_size + inset),
                (cell.x + 1) * grid.cell_size - inset,
            ),
            min(
                max(destination.lg, cell.y * grid.cell_size + inset),
                (cell.y + 1) * grid.cell_size - inset,
            ),
        )
        center = grid.center(cell)
        distance = hypot(nearest[0] - destination.lt, nearest[1] - destination.lg)
        towards_center = hypot(center[0] - nearest[0], center[1] - nearest[1])
        fraction = (
            min(0.5, max(0.0, destination.arrival_radius - distance) / (2 * towards_center))
            if towards_center
            else 0.0
        )
        return (
            nearest[0] + fraction * (center[0] - nearest[0]),
            nearest[1] + fraction * (center[1] - nearest[1]),
        )

    @staticmethod
    def _is_boundary_cell(grid: NavigationCostGrid, cell: NavigationCell) -> bool:
        return cell.x in {grid.minimum.x, grid.maximum.x} or cell.y in {
            grid.minimum.y,
            grid.maximum.y,
        }

    @staticmethod
    def _reconstruct(
        came_from: dict[NavigationCell, NavigationCell],
        start: NavigationCell,
        endpoint: NavigationCell,
    ) -> tuple[NavigationCell, ...]:
        path = [endpoint]
        current = endpoint
        while current != start:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return tuple(path)

    @staticmethod
    def _neighbors(
        grid: NavigationCostGrid,
        cell: NavigationCell,
    ) -> tuple[tuple[NavigationCell, float], ...]:
        result = []
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                if delta_x == 0 and delta_y == 0:
                    continue
                neighbor = NavigationCell(cell.x + delta_x, cell.y + delta_y)
                if not grid.contains(neighbor) or neighbor in grid.blocked:
                    continue
                if delta_x and delta_y:
                    side_x = NavigationCell(cell.x + delta_x, cell.y)
                    side_y = NavigationCell(cell.x, cell.y + delta_y)
                    if side_x in grid.blocked or side_y in grid.blocked:
                        continue
                    step_cost = sqrt(2)
                else:
                    step_cost = 1.0
                result.append((neighbor, step_cost))
        return tuple(result)

    @staticmethod
    def _heuristic(first: NavigationCell, second: NavigationCell) -> float:
        delta_x = abs(first.x - second.x)
        delta_y = abs(first.y - second.y)
        return max(delta_x, delta_y) + (sqrt(2) - 1) * min(delta_x, delta_y)

    def _smooth(
        self,
        grid: NavigationCostGrid,
        cells: tuple[NavigationCell, ...],
    ) -> tuple[NavigationCell, ...]:
        if len(cells) <= 2:
            return cells
        result = [cells[0]]
        anchor = 0
        while anchor < len(cells) - 1:
            candidate = len(cells) - 1
            while candidate > anchor + 1 and not self._shortcut_preserves_cost(
                grid,
                cells[anchor : candidate + 1],
            ):
                candidate -= 1
            result.append(cells[candidate])
            anchor = candidate
        return tuple(result)

    @staticmethod
    def _shortcut_preserves_cost(
        grid: NavigationCostGrid,
        original: tuple[NavigationCell, ...],
    ) -> bool:
        shortcut_cost = WeightedAStarPlanner._line_cost(
            grid,
            original[0],
            original[-1],
        )
        if shortcut_cost is None:
            return False
        original_cost = 0.0
        for previous, cell in pairwise(original):
            diagonal = previous.x != cell.x and previous.y != cell.y
            original_cost += (sqrt(2) if diagonal else 1.0) * grid.traversal_cost(cell)
        return shortcut_cost <= original_cost + 1e-9

    @staticmethod
    def _line_cost(
        grid: NavigationCostGrid,
        start: NavigationCell,
        end: NavigationCell,
    ) -> float | None:
        x, y = start.x, start.y
        delta_x = abs(end.x - x)
        delta_y = abs(end.y - y)
        step_x = 1 if x < end.x else -1
        step_y = 1 if y < end.y else -1
        error = delta_x - delta_y
        cost = 0.0
        while True:
            cell = NavigationCell(x, y)
            if cell in grid.blocked:
                return None
            if x == end.x and y == end.y:
                return cost
            doubled = 2 * error
            previous_x, previous_y = x, y
            if doubled > -delta_y:
                error -= delta_y
                x += step_x
            if doubled < delta_x:
                error += delta_x
                y += step_y
            if x != previous_x and y != previous_y:
                if (
                    NavigationCell(x, previous_y) in grid.blocked
                    or NavigationCell(previous_x, y) in grid.blocked
                ):
                    return None
            next_cell = NavigationCell(x, y)
            diagonal = x != previous_x and y != previous_y
            cost += (sqrt(2) if diagonal else 1.0) * grid.traversal_cost(next_cell)
