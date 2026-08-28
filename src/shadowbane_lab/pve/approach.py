"""Obstacle-aware approach coordination for a selected PvE target."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from shadowbane_lab.pve.model import PvEObservation, PvEPhase
from shadowbane_lab.travel import (
    AStarRouteNotFound,
    SparseNavigationMap,
    TravelController,
    TravelControllerConfig,
    TravelDecision,
    TravelDestination,
    TravelObservation,
    TravelPhase,
    TravelPlan,
    WeightedAStarPlanner,
)
from shadowbane_lab.travel.model import TravelManeuver


class PvEApproachStatus(StrEnum):
    IDLE = "idle"
    MOVING = "moving"
    ARRIVED = "arrived"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PvEApproachConfig:
    """Bounds native chase grace and minimap-assisted obstacle recovery."""

    arrival_radius: float = 20.0
    reposition_arrival_radius: float = 3.0
    native_progress_grace_ms: int = 2_500
    native_minimum_progress: float = 8.0
    maximum_astar_replans_per_target: int = 6
    travel: TravelControllerConfig = field(
        default_factory=lambda: TravelControllerConfig(
            maximum_session_ms=25_000,
            click_interval_ms=1_000,
            maximum_clicks=24,
            minimum_progress=8.0,
            maximum_no_progress_clicks=2,
            maximum_escape_sequences=2,
            minimum_health_fraction=0.5,
        )
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.arrival_radius, bool)
            or not isinstance(self.arrival_radius, (int, float))
            or not isfinite(self.arrival_radius)
            or self.arrival_radius <= 0
        ):
            raise ValueError("arrival_radius must be positive")
        if (
            isinstance(self.reposition_arrival_radius, bool)
            or not isinstance(self.reposition_arrival_radius, (int, float))
            or not isfinite(self.reposition_arrival_radius)
            or self.reposition_arrival_radius <= 0
            or self.reposition_arrival_radius >= self.arrival_radius
        ):
            raise ValueError(
                "reposition_arrival_radius must be positive and below arrival_radius"
            )
        if (
            isinstance(self.native_progress_grace_ms, bool)
            or not isinstance(self.native_progress_grace_ms, int)
            or self.native_progress_grace_ms <= 0
        ):
            raise ValueError("native_progress_grace_ms must be a positive integer")
        if (
            isinstance(self.native_minimum_progress, bool)
            or not isinstance(self.native_minimum_progress, (int, float))
            or not isfinite(self.native_minimum_progress)
            or self.native_minimum_progress <= 0
        ):
            raise ValueError("native_minimum_progress must be positive")
        if not isinstance(self.travel, TravelControllerConfig):
            raise ValueError("travel must be TravelControllerConfig")
        if (
            isinstance(self.maximum_astar_replans_per_target, bool)
            or not isinstance(self.maximum_astar_replans_per_target, int)
            or self.maximum_astar_replans_per_target <= 0
        ):
            raise ValueError("maximum_astar_replans_per_target must be positive")


@dataclass(frozen=True, slots=True)
class PvEApproachUpdate:
    status: PvEApproachStatus
    decision: TravelDecision | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, PvEApproachStatus):
            raise ValueError("status must be PvEApproachStatus")
        if self.decision is not None and not isinstance(self.decision, TravelDecision):
            raise ValueError("decision must be TravelDecision when present")
        if self.status is PvEApproachStatus.MOVING and self.decision is None:
            raise ValueError("moving approach updates require a travel decision")
        if self.status is PvEApproachStatus.FAILED and (
            self.decision is None or self.decision.phase is not TravelPhase.STOPPED
        ):
            raise ValueError("failed approach updates require a stopped travel decision")


class PvEApproachController:
    """Lets native chase run first, then reuses travel escape recovery if it stalls."""

    def __init__(
        self,
        config: PvEApproachConfig | None = None,
        *,
        navigation_map: SparseNavigationMap | None = None,
        planner: WeightedAStarPlanner | None = None,
    ) -> None:
        if config is not None and not isinstance(config, PvEApproachConfig):
            raise ValueError("config must be PvEApproachConfig")
        self._config = config or PvEApproachConfig()
        if navigation_map is not None and not isinstance(
            navigation_map, SparseNavigationMap
        ):
            raise ValueError("navigation_map must be SparseNavigationMap")
        if planner is not None and not isinstance(planner, WeightedAStarPlanner):
            raise ValueError("planner must be WeightedAStarPlanner")
        self._navigation_map = navigation_map or SparseNavigationMap()
        self._planner = planner or WeightedAStarPlanner()
        self._target_token: str | None = None
        self._best_distance: float | None = None
        self._last_native_progress_at: int | None = None
        self._travel: TravelController | None = None
        self._terminal_reported = False
        self._last_travel_observation: TravelObservation | None = None
        self._astar_replans = 0
        self._forced_reposition = False

    @property
    def config(self) -> PvEApproachConfig:
        return self._config

    def step(
        self,
        observation: PvEObservation,
        *,
        phase: PvEPhase,
        reposition_requested: bool = False,
    ) -> PvEApproachUpdate:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        if not isinstance(phase, PvEPhase):
            raise ValueError("phase must be PvEPhase")
        if not isinstance(reposition_requested, bool):
            raise ValueError("reposition_requested must be boolean")
        if phase not in (PvEPhase.OPENING, PvEPhase.ENGAGED):
            return self.cancel("combat_phase_changed")
        if (
            not observation.target.target_present
            or observation.target.target_token is None
            or observation.player_position is None
            or observation.target_position is None
            or not observation.target_position.target_present
        ):
            return self.cancel("target_position_unavailable")

        target_token = observation.target.target_token
        distance = observation.target_planar_distance
        assert distance is not None
        self._last_travel_observation = self._travel_observation(observation)
        if self._target_token != target_token:
            if self._travel is not None and not self._travel.terminal:
                return self.cancel("selected_target_changed")
            self._begin_target(target_token, distance, observation.now_ms)

        if (
            reposition_requested
            and distance > self._config.reposition_arrival_radius
        ):
            self._begin_target(
                target_token,
                distance,
                observation.now_ms,
                forced_reposition=True,
            )

        arrival_radius = (
            self._config.reposition_arrival_radius
            if self._forced_reposition
            else self._config.arrival_radius
        )
        destination = self._destination(observation, arrival_radius=arrival_radius)
        if distance <= arrival_radius:
            if self._travel is None or self._terminal_reported:
                self._forced_reposition = False
                return PvEApproachUpdate(PvEApproachStatus.ARRIVED)
            self._travel.update_final_destination(destination)
            decision = self._travel.arrive(self._last_travel_observation)
            self._terminal_reported = True
            self._forced_reposition = False
            return PvEApproachUpdate(PvEApproachStatus.ARRIVED, decision)

        if self._travel is not None and self._travel.terminal:
            self._begin_target(
                target_token,
                distance,
                observation.now_ms,
                forced_reposition=self._forced_reposition,
            )

        assert self._best_distance is not None
        assert self._last_native_progress_at is not None
        if distance <= self._best_distance - self._config.native_minimum_progress:
            self._best_distance = distance
            self._last_native_progress_at = observation.now_ms
        if self._travel is None and not self._forced_reposition and (
            observation.now_ms - self._last_native_progress_at
            < self._config.native_progress_grace_ms
        ):
            return PvEApproachUpdate(PvEApproachStatus.IDLE)
        if self._travel is None:
            self._travel = self._plan_route(observation, destination)
        else:
            self._travel.update_final_destination(destination)
        decision = self._travel.step(self._last_travel_observation)
        if (
            decision.maneuver is not None
            and decision.maneuver is not TravelManeuver.DIRECT
            and self._astar_replans < self._config.maximum_astar_replans_per_target
        ):
            active_waypoint = self._travel.plan.destinations[decision.waypoint_index]
            assert observation.player_position is not None
            self._navigation_map.mark_blocked_ahead(
                observation.player_position,
                active_waypoint,
            )
            try:
                self._travel = self._plan_route(observation, destination)
            except AStarRouteNotFound:
                pass
            else:
                self._astar_replans += 1
                decision = self._travel.step(self._last_travel_observation)
        if decision.phase is TravelPhase.STOPPED:
            self._terminal_reported = True
            return PvEApproachUpdate(PvEApproachStatus.FAILED, decision)
        if decision.phase is TravelPhase.COMPLETE:
            self._terminal_reported = True
            return PvEApproachUpdate(PvEApproachStatus.ARRIVED, decision)
        return PvEApproachUpdate(PvEApproachStatus.MOVING, decision)

    def cancel(self, reason: str) -> PvEApproachUpdate:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("approach cancellation reason must be non-empty")
        if self._travel is None or self._terminal_reported:
            self._reset()
            return PvEApproachUpdate(PvEApproachStatus.IDLE)
        decision = self._travel.stop(reason, self._last_travel_observation)
        self._reset()
        return PvEApproachUpdate(PvEApproachStatus.CANCELLED, decision)

    def _begin_target(
        self,
        target_token: str,
        distance: float,
        now_ms: int,
        *,
        forced_reposition: bool = False,
    ) -> None:
        self._target_token = target_token
        self._best_distance = distance
        self._last_native_progress_at = now_ms
        self._travel = None
        self._terminal_reported = False
        self._astar_replans = 0
        self._forced_reposition = forced_reposition

    def _reset(self) -> None:
        self._target_token = None
        self._best_distance = None
        self._last_native_progress_at = None
        self._travel = None
        self._terminal_reported = False
        self._last_travel_observation = None
        self._astar_replans = 0
        self._forced_reposition = False

    def _plan_route(
        self,
        observation: PvEObservation,
        destination: TravelDestination,
    ) -> TravelController:
        assert observation.player_position is not None
        route = self._planner.plan(
            self._navigation_map,
            start_lt=observation.player_position.lt,
            start_lg=observation.player_position.lg,
            destination=destination,
        )
        assert self._target_token is not None
        return TravelController(
            TravelPlan(
                plan_id=f"pve-approach:{self._target_token}:astar:{self._astar_replans}",
                destinations=route.destinations,
            ),
            self._config.travel,
        )

    def _destination(
        self,
        observation: PvEObservation,
        *,
        arrival_radius: float,
    ) -> TravelDestination:
        assert observation.target_position is not None
        assert observation.target_position.lt is not None
        assert observation.target_position.lg is not None
        return TravelDestination(
            lt=observation.target_position.lt,
            lg=observation.target_position.lg,
            arrival_radius=arrival_radius,
        )

    @staticmethod
    def _travel_observation(observation: PvEObservation) -> TravelObservation:
        if observation.player_position is None:
            raise ValueError("PvE approach requires a player position")
        return TravelObservation(
            now_ms=observation.now_ms,
            position=observation.player_position,
            player=observation.player,
        )
