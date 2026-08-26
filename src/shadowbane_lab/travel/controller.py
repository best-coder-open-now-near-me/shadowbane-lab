"""Closed-loop waypoint controller for guarded minimap travel."""

from __future__ import annotations

from math import hypot

from shadowbane_lab.protocol import Vector2
from shadowbane_lab.travel.model import (
    TravelControllerConfig,
    TravelDecision,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
)


class TravelController:
    def __init__(self, plan: TravelPlan, config: TravelControllerConfig | None = None) -> None:
        if not isinstance(plan, TravelPlan):
            raise ValueError("plan must be TravelPlan")
        if config is not None and not isinstance(config, TravelControllerConfig):
            raise ValueError("config must be TravelControllerConfig")
        self._plan = plan
        self._config = config or TravelControllerConfig()
        self._started_at_ms: int | None = None
        self._waypoint_index = 0
        self._decision_id = 0
        self._click_count = 0
        self._last_click_at_ms: int | None = None
        self._last_click_distance: float | None = None
        self._no_progress_clicks = 0
        self._escape_sequence_count = 0
        self._escape_step = 0
        self._escaping = False
        self._terminal: TravelDecision | None = None

    @property
    def plan(self) -> TravelPlan:
        return self._plan

    @property
    def config(self) -> TravelControllerConfig:
        return self._config

    def step(self, observation: TravelObservation) -> TravelDecision:
        if not isinstance(observation, TravelObservation):
            raise ValueError("observation must be TravelObservation")
        if self._terminal is not None:
            return self._terminal
        if self._started_at_ms is None:
            self._started_at_ms = observation.now_ms
        elapsed = observation.now_ms - self._started_at_ms
        if elapsed < 0:
            raise ValueError("observation time cannot move backwards")
        if elapsed >= self._config.maximum_session_ms:
            return self._stop("session_timeout", observation)
        if observation.player.health_fraction < self._config.minimum_health_fraction:
            return self._stop("low_player_health", observation)

        destination = self._plan.destinations[self._waypoint_index]
        distance = destination.distance_from(observation.position)
        while distance <= destination.arrival_radius:
            if self._waypoint_index == len(self._plan.destinations) - 1:
                return self._complete(observation, distance)
            self._waypoint_index += 1
            self._last_click_at_ms = None
            self._last_click_distance = None
            self._no_progress_clicks = 0
            self._escape_step = 0
            self._escaping = False
            destination = self._plan.destinations[self._waypoint_index]
            distance = destination.distance_from(observation.position)

        if self._click_count >= self._config.maximum_clicks:
            return self._stop("maximum_clicks", observation, distance=distance)
        if self._last_click_at_ms is not None and (
            observation.now_ms - self._last_click_at_ms < self._config.click_interval_ms
        ):
            return self._decision(observation, distance=distance)

        if self._escaping:
            return self._dispatch_escape(observation, distance=distance)

        if self._last_click_distance is not None:
            progress = self._last_click_distance - distance
            if progress < self._config.minimum_progress:
                self._no_progress_clicks += 1
            else:
                self._no_progress_clicks = 0
            if self._no_progress_clicks >= self._config.maximum_no_progress_clicks:
                if self._escape_sequence_count >= self._config.maximum_escape_sequences:
                    return self._stop(
                        (
                            "no_progress"
                            if self._config.maximum_escape_sequences == 0
                            else "no_progress_after_escape"
                        ),
                        observation,
                        distance=distance,
                    )
                self._escape_sequence_count += 1
                self._escape_step = 0
                self._escaping = True
                self._no_progress_clicks = 0
                self._last_click_distance = None
                return self._dispatch_escape(observation, distance=distance)

        delta_lt = destination.lt - observation.position.lt
        delta_lg = destination.lg - observation.position.lg
        return self._dispatch(
            observation,
            distance=distance,
            direction=Vector2(delta_lt, -delta_lg),
            maneuver=TravelManeuver.DIRECT,
        )

    def stop(self, reason: str, observation: TravelObservation | None = None) -> TravelDecision:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        if self._terminal is not None:
            return self._terminal
        if observation is None:
            now_ms = self._started_at_ms or 0
            distance = 0.0
        else:
            now_ms = observation.now_ms
            destination = self._plan.destinations[self._waypoint_index]
            distance = destination.distance_from(observation.position)
        self._terminal = TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=now_ms,
            phase=TravelPhase.STOPPED,
            waypoint_index=self._waypoint_index,
            distance_remaining=distance,
            click_count=self._click_count,
            terminal_reason=reason,
        )
        return self._terminal

    def _decision(
        self,
        observation: TravelObservation,
        *,
        distance: float,
        direction: Vector2 | None = None,
        maneuver: TravelManeuver | None = None,
    ) -> TravelDecision:
        return TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=observation.now_ms,
            phase=TravelPhase.TRAVELING,
            waypoint_index=self._waypoint_index,
            distance_remaining=distance,
            click_count=self._click_count,
            minimap_direction=direction,
            maneuver=maneuver,
        )

    def _dispatch(
        self,
        observation: TravelObservation,
        *,
        distance: float,
        direction: Vector2,
        maneuver: TravelManeuver,
        track_destination_progress: bool = True,
    ) -> TravelDecision:
        self._last_click_at_ms = observation.now_ms
        self._last_click_distance = distance if track_destination_progress else None
        self._click_count += 1
        return self._decision(
            observation,
            distance=distance,
            direction=direction,
            maneuver=maneuver,
        )

    def _dispatch_escape(
        self,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> TravelDecision:
        destination = self._plan.destinations[self._waypoint_index]
        delta_lt = destination.lt - observation.position.lt
        screen_delta_lg = -(destination.lg - observation.position.lg)
        length = hypot(delta_lt, screen_delta_lg)
        if length == 0:
            return self._complete(observation, distance)
        forward_x = delta_lt / length
        forward_y = screen_delta_lg / length
        backward_x = -forward_x
        backward_y = -forward_y
        perpendicular_x = -forward_y
        perpendicular_y = forward_x
        initial_sign = 1.0 if self._escape_sequence_count % 2 else -1.0
        sign = initial_sign if self._escape_step % 2 == 0 else -initial_sign
        lateral = self._config.escape_lateral_ratio + (
            (self._escape_sequence_count - 1)
            * self._config.escape_widening_per_sequence
        )
        maneuver = (
            TravelManeuver.ESCAPE_BACK_LEFT
            if sign > 0
            else TravelManeuver.ESCAPE_BACK_RIGHT
        )
        self._escape_step += 1
        if self._escape_step >= self._config.escape_clicks_per_sequence:
            self._escaping = False
            self._escape_step = 0
        return self._dispatch(
            observation,
            distance=distance,
            direction=Vector2(
                backward_x + sign * lateral * perpendicular_x,
                backward_y + sign * lateral * perpendicular_y,
            ),
            maneuver=maneuver,
            track_destination_progress=False,
        )

    def _stop(
        self,
        reason: str,
        observation: TravelObservation,
        *,
        distance: float | None = None,
    ) -> TravelDecision:
        if distance is None:
            destination = self._plan.destinations[self._waypoint_index]
            distance = destination.distance_from(observation.position)
        self._terminal = TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=observation.now_ms,
            phase=TravelPhase.STOPPED,
            waypoint_index=self._waypoint_index,
            distance_remaining=distance,
            click_count=self._click_count,
            terminal_reason=reason,
        )
        return self._terminal

    def _complete(self, observation: TravelObservation, distance: float) -> TravelDecision:
        self._terminal = TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=observation.now_ms,
            phase=TravelPhase.COMPLETE,
            waypoint_index=self._waypoint_index,
            distance_remaining=distance,
            click_count=self._click_count,
            terminal_reason="destination_reached",
        )
        return self._terminal

    def _next_decision_id(self) -> int:
        decision_id = self._decision_id
        self._decision_id += 1
        return decision_id
