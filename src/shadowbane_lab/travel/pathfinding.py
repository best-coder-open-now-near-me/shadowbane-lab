"""Bounded weighted A* over sparse, world-coordinate navigation costs."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from itertools import pairwise
from math import floor, hypot, isfinite, sqrt

from shadowbane_lab.client_observation import NativePlayerPositionObservation
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

    def contains(self, cell: NavigationCell) -> bool:
        return (
            self.minimum.x <= cell.x <= self.maximum.x
            and self.minimum.y <= cell.y <= self.maximum.y
        )

    def traversal_cost(self, cell: NavigationCell) -> float:
        for candidate, cost in self.costs:
            if candidate == cell:
                return cost
        return 1.0

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

    def __init__(self, *, cell_size: float = 20.0) -> None:
        if (
            isinstance(cell_size, bool)
            or not isinstance(cell_size, (int, float))
            or not isfinite(cell_size)
            or cell_size <= 0
        ):
            raise ValueError("cell_size must be finite and positive")
        self._cell_size = float(cell_size)
        self._blocked: set[NavigationCell] = set()
        self._learned_blocked: set[NavigationCell] = set()
        self._costs: dict[NavigationCell, float] = {}

    @property
    def cell_size(self) -> float:
        return self._cell_size

    @property
    def blocked(self) -> frozenset[NavigationCell]:
        return frozenset(self._blocked)

    @property
    def learned_blocked(self) -> frozenset[NavigationCell]:
        """Exact collision cells inferred from live failed movement."""

        return frozenset(self._learned_blocked)

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
            cell = NavigationCell(current.x + step_x, current.y + step_y)
        self.mark_learned_blocked(cell)
        return cell

    def mark_blocked(self, cell: NavigationCell) -> None:
        if not isinstance(cell, NavigationCell):
            raise ValueError("cell must be NavigationCell")
        self._blocked.add(cell)
        self._costs.pop(cell, None)

    def mark_learned_blocked(self, cell: NavigationCell) -> None:
        """Retain one obstacle learned from live movement for future routes."""

        self.mark_blocked(cell)
        self._learned_blocked.add(cell)

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
        if cell in self._blocked:
            raise ValueError("blocked cells cannot also have a traversal cost")
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
            for delta_x in range(-clearance, clearance + 1):
                for delta_y in range(-clearance, clearance + 1):
                    candidate = NavigationCell(obstacle.x + delta_x, obstacle.y + delta_y)
                    if (
                        minimum.x <= candidate.x <= maximum.x
                        and minimum.y <= candidate.y <= maximum.y
                    ):
                        blocked.add(candidate)
        blocked.discard(start)
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
        )


class WeightedAStarPlanner:
    def __init__(self, config: WeightedAStarConfig | None = None) -> None:
        if config is not None and not isinstance(config, WeightedAStarConfig):
            raise ValueError("config must be WeightedAStarConfig")
        self._config = config or WeightedAStarConfig()

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
        cells, expanded, total_cost = self._search(grid, start, goal)
        smoothed = self._smooth(grid, cells)
        waypoint_radius = max(5.0, grid.cell_size * self._config.waypoint_radius_fraction)
        destinations = [
            TravelDestination(*grid.center(cell), arrival_radius=waypoint_radius)
            for cell in smoothed[1:-1]
        ]
        destinations.append(destination)
        return AStarRoute(
            cells=smoothed,
            destinations=tuple(destinations),
            expanded_cells=expanded,
            total_cost=total_cost,
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
        cells, expanded, total_cost = self._search(
            grid,
            start,
            goal,
            allow_partial=True,
        )
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
        return AStarRoute(
            cells=smoothed,
            destinations=tuple(destinations),
            expanded_cells=expanded,
            total_cost=total_cost,
        )

    def _search(
        self,
        grid: NavigationCostGrid,
        start: NavigationCell,
        goal: NavigationCell,
        *,
        allow_partial: bool = False,
    ) -> tuple[tuple[NavigationCell, ...], int, float]:
        if start in grid.blocked or goal in grid.blocked:
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
            if (
                current_heuristic < closest_heuristic
                or (
                    current_heuristic == closest_heuristic
                    and cost_so_far[current] < cost_so_far[closest]
                )
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
            if current == goal:
                return self._reconstruct(came_from, start, current), expanded, cost_so_far[goal]
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
    def _is_boundary_cell(grid: NavigationCostGrid, cell: NavigationCell) -> bool:
        return (
            cell.x in {grid.minimum.x, grid.maximum.x}
            or cell.y in {grid.minimum.y, grid.maximum.y}
        )

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
