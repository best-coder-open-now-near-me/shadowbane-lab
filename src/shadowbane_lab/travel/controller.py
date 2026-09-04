"""Closed-loop waypoint controller for guarded minimap travel."""

from __future__ import annotations

from enum import StrEnum
from math import hypot

from shadowbane_lab.navigation_inspector.events import DiagnosticObserver, MotionEvent, emit
from shadowbane_lab.protocol import Vector2
from shadowbane_lab.travel.model import (
    TravelControllerConfig,
    TravelDecision,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    TravelPlan,
)


class _EscapePhase(StrEnum):
    BACKUP = "backup"
    SWEEP = "sweep"
    BYPASS = "bypass"


class TravelController:
    def __init__(
        self,
        plan: TravelPlan,
        config: TravelControllerConfig | None = None,
        *,
        observer: DiagnosticObserver | None = None,
    ) -> None:
        if not isinstance(plan, TravelPlan):
            raise ValueError("plan must be TravelPlan")
        if config is not None and not isinstance(config, TravelControllerConfig):
            raise ValueError("config must be TravelControllerConfig")
        self._observer = observer
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
        self._escape_phase = _EscapePhase.BACKUP
        self._escape_forward = Vector2(0, 0)
        self._escape_side_sign = 1.0
        self._escape_phase_origin = Vector2(0, 0)
        self._escape_phase_origin_distance = 0.0
        self._escape_last_position = Vector2(0, 0)
        self._escape_no_motion_clicks = 0
        self._escape_side_switches = 0
        self._escape_release_distance: float | None = None
        self._escaping = False
        self._terminal: TravelDecision | None = None

    @property
    def plan(self) -> TravelPlan:
        return self._plan

    @property
    def config(self) -> TravelControllerConfig:
        return self._config

    @property
    def terminal(self) -> bool:
        return self._terminal is not None

    def update_single_destination(self, destination: TravelDestination) -> None:
        """Retarget a one-way plan without discarding obstacle-recovery state."""

        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be TravelDestination")
        if len(self._plan.destinations) != 1 or self._waypoint_index != 0:
            raise RuntimeError("only an active single-destination plan may be retargeted")
        self._plan = TravelPlan(
            plan_id=self._plan.plan_id,
            destinations=(destination,),
        )

    def update_final_destination(self, destination: TravelDestination) -> None:
        """Move the final goal of an active route while preserving completed waypoints."""

        if not isinstance(destination, TravelDestination):
            raise ValueError("destination must be TravelDestination")
        if self._terminal is not None:
            raise RuntimeError("a terminal travel route cannot be retargeted")
        destinations = (*self._plan.destinations[:-1], destination)
        self._plan = TravelPlan(plan_id=self._plan.plan_id, destinations=destinations)

    def arrive(self, observation: TravelObservation) -> TravelDecision:
        """Complete a dynamic route when its moving goal is independently reached."""

        if not isinstance(observation, TravelObservation):
            raise ValueError("observation must be TravelObservation")
        final = self._plan.destinations[-1]
        distance = final.distance_from(observation.position)
        if distance > final.arrival_radius:
            raise ValueError("final destination has not been reached")
        return self._complete(observation, distance)

    def step(self, observation: TravelObservation) -> TravelDecision:
        if not isinstance(observation, TravelObservation):
            raise ValueError("observation must be TravelObservation")
        if self._terminal is not None:
            return self._terminal
        self._debug_event("observation", observation)
        if self._started_at_ms is None:
            self._started_at_ms = observation.now_ms
            self._debug_event("start", observation)
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
            self._debug_event("waypoint", observation)
            self._last_click_at_ms = None
            self._last_click_distance = None
            self._no_progress_clicks = 0
            self._escape_sequence_count = 0
            self._escape_step = 0
            self._escape_phase = _EscapePhase.BACKUP
            self._escape_release_distance = None
            self._escaping = False
            destination = self._plan.destinations[self._waypoint_index]
            distance = destination.distance_from(observation.position)

        if self._escape_release_distance is not None and (
            self._escape_release_distance - distance >= self._config.escape_budget_reset_progress
        ):
            self._escape_sequence_count = 0
            self._escape_release_distance = None

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
                self._begin_escape(observation, distance=distance)
                self._no_progress_clicks = 0
                self._last_click_distance = None
                return self._dispatch_escape(observation, distance=distance)

        return self._dispatch_direct(observation, distance=distance)

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
        self._debug_event("cancelled", observation, self._terminal, reason=reason)
        return self._terminal

    def _decision(
        self,
        observation: TravelObservation,
        *,
        distance: float,
        direction: Vector2 | None = None,
        maneuver: TravelManeuver | None = None,
    ) -> TravelDecision:
        decision = TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=observation.now_ms,
            phase=TravelPhase.TRAVELING,
            waypoint_index=self._waypoint_index,
            distance_remaining=distance,
            click_count=self._click_count,
            minimap_direction=direction,
            maneuver=maneuver,
        )

        if direction is not None:
            self._debug_event(
                "command_requested",
                observation,
                decision,
                reason=None if maneuver is None else maneuver.value,
            )
        return decision

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

    def _dispatch_direct(
        self,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> TravelDecision:
        destination = self._plan.destinations[self._waypoint_index]
        return self._dispatch(
            observation,
            distance=distance,
            direction=Vector2(
                destination.lt - observation.position.lt,
                -(destination.lg - observation.position.lg),
            ),
            maneuver=TravelManeuver.DIRECT,
        )

    def _begin_escape(
        self,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> None:
        self._debug_event("stall", observation)
        destination = self._plan.destinations[self._waypoint_index]
        delta_lt = destination.lt - observation.position.lt
        screen_delta_lg = -(destination.lg - observation.position.lg)
        length = hypot(delta_lt, screen_delta_lg)
        if length == 0:
            self._escape_forward = Vector2(0, 0)
        else:
            self._escape_forward = Vector2(delta_lt / length, screen_delta_lg / length)
        self._escape_side_sign = 1.0 if self._escape_sequence_count % 2 else -1.0
        self._escape_phase = _EscapePhase.BACKUP
        self._escape_step = 0
        self._escape_side_switches = 0
        self._reset_escape_phase_feedback(observation, distance=distance)
        self._escaping = True
        self._debug_event("escape_planned", observation)

    def _dispatch_escape(
        self,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> TravelDecision:
        self._observe_escape_motion(observation)
        if self._escape_step > 0 and (
            self._escape_phase_origin_distance - distance >= self._config.escape_reacquire_progress
        ):
            return self._reacquire_direct(observation, distance=distance)

        if self._escape_no_motion_clicks >= (self._config.maximum_escape_phase_no_motion_clicks):
            if self._escape_phase is _EscapePhase.BACKUP:
                self._transition_escape_phase(
                    _EscapePhase.SWEEP,
                    observation,
                    distance=distance,
                )
            elif self._escape_phase is _EscapePhase.SWEEP:
                if self._escape_side_switches < self._config.maximum_escape_side_switches:
                    self._escape_side_switches += 1
                    self._escape_side_sign *= -1
                    self._reset_escape_phase_feedback(observation, distance=distance)
                else:
                    self._transition_escape_phase(
                        _EscapePhase.BYPASS,
                        observation,
                        distance=distance,
                    )
            else:
                if self._escape_sequence_count >= self._config.maximum_escape_sequences:
                    return self._stop(
                        "no_progress_after_escape",
                        observation,
                        distance=distance,
                    )
                self._escape_sequence_count += 1
                self._begin_escape(observation, distance=distance)

        phase_progress = self._escape_phase_progress(observation)
        if self._escape_phase is _EscapePhase.BACKUP and (
            phase_progress >= self._config.escape_backup_clearance
            or self._escape_step >= self._escape_phase_clicks()
        ):
            self._transition_escape_phase(
                _EscapePhase.SWEEP,
                observation,
                distance=distance,
            )
        elif self._escape_phase is _EscapePhase.SWEEP and (
            phase_progress >= self._escape_sweep_clearance()
            or self._escape_step >= self._escape_phase_clicks()
        ):
            self._transition_escape_phase(
                _EscapePhase.BYPASS,
                observation,
                distance=distance,
            )
        elif self._escape_phase is _EscapePhase.BYPASS and (
            self._escape_step >= self._escape_phase_clicks()
        ):
            return self._reacquire_direct(observation, distance=distance)

        forward_x = self._escape_forward.x
        forward_y = self._escape_forward.y
        if forward_x == 0 and forward_y == 0:
            return self._complete(observation, distance)
        perpendicular_x = -forward_y
        perpendicular_y = forward_x
        side_sign = self._escape_side_sign

        if self._escape_phase is _EscapePhase.BACKUP:
            zig_sign = side_sign if self._escape_step % 2 == 0 else -side_sign
            lateral = self._config.escape_backup_lateral_ratio
            direction = Vector2(
                -forward_x + zig_sign * lateral * perpendicular_x,
                -forward_y + zig_sign * lateral * perpendicular_y,
            )
            maneuver = (
                TravelManeuver.ESCAPE_BACK_LEFT
                if zig_sign > 0
                else TravelManeuver.ESCAPE_BACK_RIGHT
            )
        elif self._escape_phase is _EscapePhase.SWEEP:
            reverse = self._config.escape_sweep_reverse_ratio
            direction = Vector2(
                side_sign * perpendicular_x - reverse * forward_x,
                side_sign * perpendicular_y - reverse * forward_y,
            )
            maneuver = (
                TravelManeuver.ESCAPE_SWEEP_LEFT
                if side_sign > 0
                else TravelManeuver.ESCAPE_SWEEP_RIGHT
            )
        else:
            lateral = self._config.escape_bypass_lateral_ratio
            direction = Vector2(
                forward_x + side_sign * lateral * perpendicular_x,
                forward_y + side_sign * lateral * perpendicular_y,
            )
            maneuver = (
                TravelManeuver.ESCAPE_BYPASS_LEFT
                if side_sign > 0
                else TravelManeuver.ESCAPE_BYPASS_RIGHT
            )

        self._escape_step += 1
        return self._dispatch(
            observation,
            distance=distance,
            direction=direction,
            maneuver=maneuver,
            track_destination_progress=False,
        )

    def _escape_phase_clicks(self) -> int:
        widening = (
            self._escape_sequence_count - 1
        ) * self._config.escape_widening_clicks_per_sequence
        if self._escape_phase is _EscapePhase.BACKUP:
            return self._config.escape_backup_clicks
        if self._escape_phase is _EscapePhase.SWEEP:
            return self._config.escape_sweep_clicks + widening
        return self._config.escape_bypass_clicks + widening

    def _escape_sweep_clearance(self) -> float:
        return self._config.escape_sweep_clearance + (
            (self._escape_sequence_count - 1) * self._config.escape_widening_clearance_per_sequence
        )

    def _observe_escape_motion(self, observation: TravelObservation) -> None:
        if self._escape_step == 0:
            return
        position = self._screen_position(observation)
        movement = hypot(
            position.x - self._escape_last_position.x,
            position.y - self._escape_last_position.y,
        )
        if movement < self._config.escape_minimum_motion:
            self._escape_no_motion_clicks += 1
        else:
            self._escape_no_motion_clicks = 0
        self._escape_last_position = position

    def _escape_phase_progress(self, observation: TravelObservation) -> float:
        position = self._screen_position(observation)
        delta_x = position.x - self._escape_phase_origin.x
        delta_y = position.y - self._escape_phase_origin.y
        forward_x = self._escape_forward.x
        forward_y = self._escape_forward.y
        if self._escape_phase is _EscapePhase.BACKUP:
            return -(delta_x * forward_x + delta_y * forward_y)
        if self._escape_phase is _EscapePhase.SWEEP:
            perpendicular_x = -forward_y * self._escape_side_sign
            perpendicular_y = forward_x * self._escape_side_sign
            return delta_x * perpendicular_x + delta_y * perpendicular_y
        return self._escape_phase_origin_distance - self._distance_for(observation)

    def _transition_escape_phase(
        self,
        phase: _EscapePhase,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> None:
        self._escape_phase = phase
        self._reset_escape_phase_feedback(observation, distance=distance)

    def _reset_escape_phase_feedback(
        self,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> None:
        position = self._screen_position(observation)
        self._escape_phase_origin = position
        self._escape_phase_origin_distance = distance
        self._escape_last_position = position
        self._escape_step = 0
        self._escape_no_motion_clicks = 0

    def _reacquire_direct(
        self,
        observation: TravelObservation,
        *,
        distance: float,
    ) -> TravelDecision:
        self._escaping = False
        self._escape_phase = _EscapePhase.BACKUP
        self._escape_step = 0
        self._no_progress_clicks = 0
        self._escape_release_distance = distance
        return self._dispatch_direct(observation, distance=distance)

    def _distance_for(self, observation: TravelObservation) -> float:
        destination = self._plan.destinations[self._waypoint_index]
        return destination.distance_from(observation.position)

    @staticmethod
    def _screen_position(observation: TravelObservation) -> Vector2:
        return Vector2(observation.position.lt, -observation.position.lg)

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
        self._debug_event("failure", observation, self._terminal, reason=reason)
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
        self._debug_event("completion", observation, self._terminal)
        return self._terminal

    def _debug_event(
        self,
        event: str,
        observation: TravelObservation | None,
        decision: TravelDecision | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        if self._observer is None:
            return
        try:
            position = None if observation is None else observation.position
            destination = self._plan.destinations[self._waypoint_index]
            emit(
                self._observer,
                MotionEvent(
                    kind="motion",
                    event=event,
                    plan_id=self._plan.plan_id,
                    now_ms=(self._started_at_ms or 0)
                    if observation is None
                    else observation.now_ms,
                    position=None
                    if position is None
                    else (position.lt, position.lg, position.altitude),
                    waypoint_index=self._waypoint_index,
                    destination=(destination.lt, destination.lg, destination.arrival_radius),
                    direction=None
                    if decision is None or decision.minimap_direction is None
                    else (
                        decision.minimap_direction.x,
                        decision.minimap_direction.y,
                    ),
                    reason=reason,
                ),
            )
        except Exception:
            pass

    def _next_decision_id(self) -> int:
        decision_id = self._decision_id
        self._decision_id += 1
        return decision_id
