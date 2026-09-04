"""Terrain-backed A* ownership for durable long-distance travel."""

from __future__ import annotations

from dataclasses import replace
from math import hypot, sqrt
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.navigation_inspector.events import MotionEvent, emit, measured_position
from shadowbane_lab.travel.controller import TravelController
from shadowbane_lab.travel.model import (
    TravelControllerConfig,
    TravelDecision,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
)
from shadowbane_lab.travel.pathfinding import (
    AStarRouteNotFound,
    NavigationMapSnapshot,
    WeightedAStarPlanner,
)


@runtime_checkable
class TravelNavigationSource(Protocol):
    def observe(
        self,
        position: NativePlayerPositionObservation,
    ) -> NavigationMapSnapshot: ...


class AStarTravelController:
    """Plan terrain waypoints, learn stalls, and replan without resetting leases."""

    def __init__(
        self,
        destination: TravelDestination,
        config: TravelControllerConfig,
        navigation_source: TravelNavigationSource,
        *,
        planner: WeightedAStarPlanner | None = None,
        maximum_replans: int = 12,
        plan_id: str = "go:astar",
    ) -> None:
        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be a TravelDestination")
        if not isinstance(config, TravelControllerConfig):
            raise ValueError("config must be a TravelControllerConfig")
        if not isinstance(navigation_source, TravelNavigationSource):
            raise ValueError("navigation_source must implement TravelNavigationSource")
        if planner is not None and not isinstance(planner, WeightedAStarPlanner):
            raise ValueError("planner must be a WeightedAStarPlanner")
        if (
            isinstance(maximum_replans, bool)
            or not isinstance(maximum_replans, int)
            or maximum_replans <= 0
        ):
            raise ValueError("maximum_replans must be a positive integer")
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        self._destination = destination
        self._config = config
        self._navigation_source = navigation_source
        self._planner = planner or WeightedAStarPlanner()
        self._maximum_replans = maximum_replans
        self._plan_id = plan_id
        self._navigation: NavigationMapSnapshot | None = None
        self._travel: TravelController | None = None
        self._started_at_ms: int | None = None
        self._decision_id = 0
        self._click_count = 0
        self._replan_count = 0
        self._direct_fallback_count = 0
        self._partial_route_count = 0
        self._route_mode: str | None = None
        self._travel_reaches_destination = False
        self._terminal: TravelDecision | None = None

    @property
    def replan_count(self) -> int:
        return self._replan_count

    @property
    def direct_fallback_count(self) -> int:
        return self._direct_fallback_count

    @property
    def partial_route_count(self) -> int:
        return self._partial_route_count

    @property
    def route_mode(self) -> str | None:
        return self._route_mode

    @property
    def navigation_token(self) -> str | None:
        return None if self._navigation is None else self._navigation.token

    @property
    def active_plan(self) -> TravelPlan | None:
        return None if self._travel is None else self._travel.plan

    def step(self, observation: TravelObservation) -> TravelDecision:
        if not isinstance(observation, TravelObservation):
            raise ValueError("observation must be a TravelObservation")
        if self._terminal is not None:
            return self._terminal
        if self._started_at_ms is None:
            self._started_at_ms = observation.now_ms
        if observation.now_ms - self._started_at_ms >= self._config.maximum_session_ms:
            return self._stop("session_timeout", observation)
        if observation.player.health_fraction < self._config.minimum_health_fraction:
            return self._stop("low_player_health", observation)
        if self._click_count >= self._config.maximum_clicks:
            return self._stop("maximum_clicks", observation)

        navigation = self._navigation_source.observe(observation.position)
        if self._travel is None or (
            self._navigation is not None and navigation.token != self._navigation.token
        ):
            self._navigation = navigation
            try:
                (
                    self._travel,
                    self._travel_reaches_destination,
                    self._route_mode,
                ) = self._plan(
                    observation,
                    reason="terrain_refresh",
                    allow_partial_fallback=True,
                )
            except AStarRouteNotFound as exc:
                return self._stop(self._route_failure(exc), observation)

        assert self._travel is not None
        decision = self._travel.step(observation)
        if decision.phase is TravelPhase.COMPLETE and not self._travel_reaches_destination:
            if self._replan_count >= self._maximum_replans:
                return self._stop("maximum_replans", observation)
            try:
                self._travel, self._travel_reaches_destination, self._route_mode = self._plan(
                    observation,
                    reason="frontier_complete",
                    allow_partial_fallback=True,
                )
            except AStarRouteNotFound as exc:
                return self._stop(self._route_failure(exc), observation)
            self._replan_count += 1
            decision = self._travel.step(observation)
        if (
            decision.maneuver is not None
            and decision.maneuver is not TravelManeuver.DIRECT
            and self._replan_count < self._maximum_replans
        ):
            assert self._navigation is not None
            active_waypoint = self._travel.plan.destinations[decision.waypoint_index]
            self._navigation.navigation_map.mark_blocked_ahead(
                observation.position,
                active_waypoint,
            )
            try:
                replacement, reaches_destination, route_mode = self._plan(
                    observation,
                    reason="learned_obstacle",
                    allow_partial_fallback=True,
                )
            except AStarRouteNotFound as exc:
                return self._stop(self._route_failure(exc), observation)
            else:
                self._travel = replacement
                self._travel_reaches_destination = reaches_destination
                self._route_mode = route_mode
                self._replan_count += 1
                decision = self._travel.step(observation)
        return self._translate(decision)

    def stop(
        self,
        reason: str,
        observation: TravelObservation | None = None,
    ) -> TravelDecision:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be non-empty")
        if self._terminal is not None:
            return self._terminal
        return self._stop(reason, observation)

    def _plan(
        self,
        observation: TravelObservation,
        *,
        reason: str,
        allow_partial_fallback: bool,
    ) -> tuple[TravelController, bool, str]:
        assert self._navigation is not None
        self._debug_event("replan", observation, reason)
        planning_destination = self._planning_destination(observation)
        reaches_destination = planning_destination == self._destination
        try:
            route = self._planner.plan(
                self._navigation.navigation_map,
                start_lt=observation.position.lt,
                start_lg=observation.position.lg,
                destination=planning_destination,
            )
        except AStarRouteNotFound:
            if reaches_destination or not allow_partial_fallback:
                raise
            route = self._planner.plan_reachable_frontier(
                self._navigation.navigation_map,
                start_lt=observation.position.lt,
                start_lg=observation.position.lg,
                destination=planning_destination,
            )
            self._partial_route_count += 1
            route_mode = "astar_partial"
        else:
            route_mode = "astar_final" if reaches_destination else "astar_horizon"
        return (
            TravelController(
                TravelPlan(
                    plan_id=(
                        f"{self._plan_id}:{reason}:{self._replan_count}:{self._navigation.token}"
                    ),
                    destinations=route.destinations,
                ),
                self._config,
                observer=self._planner.observer,
            ),
            reaches_destination,
            route_mode,
        )

    def _planning_destination(self, observation: TravelObservation) -> TravelDestination:
        """Project a far goal just beyond the next terrain refresh boundary."""

        assert self._navigation is not None
        window = self._navigation.planning_window
        if window is None or window.contains(self._destination):
            return self._destination
        delta_lt = self._destination.lt - observation.position.lt
        delta_lg = self._destination.lg - observation.position.lg
        distance = hypot(delta_lt, delta_lg)
        if distance == 0:
            return self._destination
        direction_lt = delta_lt / distance
        direction_lg = delta_lg / distance
        offset_lt = observation.position.lt - window.center_lt
        offset_lg = observation.position.lg - window.center_lg
        target_radius = window.refresh_distance + (window.radius - window.refresh_distance) * 0.5
        projection = offset_lt * direction_lt + offset_lg * direction_lg
        discriminant = (
            projection * projection
            + target_radius * target_radius
            - offset_lt * offset_lt
            - offset_lg * offset_lg
        )
        local_radius = max(
            5.0,
            self._navigation.navigation_map.cell_size
            * self._planner.config.waypoint_radius_fraction,
        )
        if discriminant <= 0:
            horizon_distance = max(
                local_radius * 2,
                self._navigation.navigation_map.cell_size * 2,
            )
        else:
            horizon_distance = max(local_radius * 2, -projection + sqrt(discriminant))
        if horizon_distance >= distance:
            return self._destination
        return TravelDestination(
            observation.position.lt + direction_lt * horizon_distance,
            observation.position.lg + direction_lg * horizon_distance,
            arrival_radius=local_radius,
        )

    def _debug_event(self, event: str, observation: TravelObservation | None, reason: str) -> None:
        if self._planner.observer is None:
            return
        try:
            position = None if observation is None else observation.position
            emit(
                self._planner.observer,
                MotionEvent(
                    "motion",
                    event,
                    self._plan_id,
                    0 if observation is None else observation.now_ms,
                    position=None
                    if position is None
                    else measured_position(position),
                    destination=(
                        self._destination.lt,
                        self._destination.lg,
                        self._destination.arrival_radius,
                    ),
                    reason=reason,
                ),
            )
        except Exception:
            pass

    def _stop(
        self,
        reason: str,
        observation: TravelObservation | None,
    ) -> TravelDecision:
        self._debug_event(
            "cancelled" if reason == "emergency_stop" else "failure", observation, reason
        )
        if self._travel is not None:
            internal = self._travel.stop(reason, observation)
            if internal.phase is TravelPhase.STOPPED:
                return self._translate(internal)
        now_ms = 0 if observation is None else observation.now_ms
        distance = (
            0.0 if observation is None else self._destination.distance_from(observation.position)
        )
        self._terminal = TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=now_ms,
            phase=TravelPhase.STOPPED,
            waypoint_index=0,
            distance_remaining=distance,
            click_count=self._click_count,
            terminal_reason=reason,
        )
        return self._terminal

    def _translate(self, decision: TravelDecision) -> TravelDecision:
        if decision.minimap_direction is not None:
            self._click_count += 1
        translated = replace(
            decision,
            decision_id=self._next_decision_id(),
            click_count=self._click_count,
        )
        if translated.terminal:
            self._terminal = translated
        return translated

    def _next_decision_id(self) -> int:
        decision_id = self._decision_id
        self._decision_id += 1
        return decision_id

    @staticmethod
    def _route_failure(exc: AStarRouteNotFound) -> str:
        message = " ".join(str(exc).split())
        return "astar_route_not_found" if not message else f"astar_route_not_found:{message}"
