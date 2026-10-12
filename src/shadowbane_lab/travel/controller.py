"""Closed-loop waypoint controller for guarded minimap travel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from math import hypot

from shadowbane_lab.navigation_inspector.events import (
    MAX_ROUTE_POINTS,
    DiagnosticObserver,
    MotionEvent,
    RouteEvent,
    emit,
    measured_position,
)
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


@dataclass(frozen=True)
class _DispatchCheckpoint:
    """Only proposal-owned follower state; feedback, clock and IDs never rewind."""

    _waypoint_index: int
    _click_count: int
    _attempt_count: int
    _handoff_target: TravelDestination | None
    _last_click_at_ms: int | None
    _last_click_distance: float | None
    _progress_at_ms: int | None
    _last_move_endpoint: Vector2 | None
    _no_progress_clicks: int
    _escape_sequence_count: int
    _escape_step: int
    _escape_phase: _EscapePhase
    _escape_forward: Vector2
    _escape_side_sign: float
    _escape_phase_origin: Vector2
    _escape_phase_origin_distance: float
    _escape_last_position: Vector2
    _escape_no_motion_clicks: int
    _escape_side_switches: int
    _escape_release_distance: float | None
    _escaping: bool
    _terminal: TravelDecision | None


class TravelController:
    def __init__(
        self,
        plan: TravelPlan,
        config: TravelControllerConfig | None = None,
        *,
        observer: DiagnosticObserver | None = None,
        shortcut_clear: Callable[[Vector2, tuple[Vector2, ...]], bool] | None = None,
        final_is_frontier: bool = False,
    ) -> None:
        if not isinstance(plan, TravelPlan):
            raise ValueError("plan must be TravelPlan")
        if config is not None and not isinstance(config, TravelControllerConfig):
            raise ValueError("config must be TravelControllerConfig")
        if not isinstance(final_is_frontier, bool):
            raise ValueError("final_is_frontier must be a boolean")
        self._final_is_frontier = final_is_frontier
        self._shortcut_clear = shortcut_clear
        self._previous_observation: TravelObservation | None = None
        self._progress_at_ms: int | None = None
        self._last_move_endpoint: Vector2 | None = None
        self._observer = observer
        self._debug_start = None
        self._plan = plan
        self._config = config or TravelControllerConfig()
        self._started_at_ms: int | None = None
        self._waypoint_index = 0
        self._decision_id = 0
        self._click_count = 0
        self._attempt_count = 0
        self._handoff_target: TravelDestination | None = None
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
        self._last_observed_position: Vector2 | None = None
        self._ingress_direction = Vector2(0, 0)
        self._terminal: TravelDecision | None = None
        self._proposal: tuple[_DispatchCheckpoint, TravelDecision] | None = None
        self._proposal_checkpoint: _DispatchCheckpoint | None = None
        self._dispatch_paused = False

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
        self._debug_route(observation)
        return self._complete(observation, distance)

    def propose(self, observation: TravelObservation) -> TravelDecision:
        """Stage one decision until the dispatcher acknowledges its submission."""
        if self._proposal is not None:
            raise RuntimeError("previous travel proposal has not been resolved")
        self._proposal_checkpoint = self._checkpoint()
        try:
            decision = self.step(observation)
        except Exception:
            self._restore(self._proposal_checkpoint)
            raise
        else:
            self._proposal = (self._proposal_checkpoint, decision)
            return decision
        finally:
            self._proposal_checkpoint = None

    def _checkpoint(self) -> _DispatchCheckpoint:
        return _DispatchCheckpoint(
            **{field.name: getattr(self, field.name) for field in fields(_DispatchCheckpoint)}
        )

    def _restore(self, checkpoint: _DispatchCheckpoint) -> None:
        for field in fields(checkpoint):
            setattr(self, field.name, getattr(checkpoint, field.name))

    def acknowledge_dispatch(self, decision: TravelDecision) -> None:
        self._require_proposal(decision)
        self._proposal = None

    def defer_dispatch(
        self, decision: TravelDecision, observation: TravelObservation,
    ) -> TravelDecision:
        checkpoint = self._require_proposal(decision)
        self._restore(checkpoint)
        self._proposal = None
        self._pause_progress(observation)
        return replace(
            decision, waypoint_index=self._waypoint_index, click_count=self._click_count,
            minimap_direction=None, click_destination=None, maneuver=None, progress_refresh=False,
            phase=TravelPhase.TRAVELING, terminal_reason=None, arrival_destination=None,
        )

    def _require_proposal(self, decision: TravelDecision) -> _DispatchCheckpoint:
        if self._proposal is None or self._proposal[1] is not decision:
            raise RuntimeError("travel dispatch acknowledgement does not match its proposal")
        return self._proposal[0]

    def observe_deferred(self, observation: TravelObservation) -> TravelDecision:
        """Keep observing safety/session bounds while native cleanup owns the pause."""
        if self._proposal is not None:
            raise RuntimeError("previous travel proposal has not been resolved")
        previous = self._previous_observation
        terminal = self._observe(observation)
        if terminal is not None:
            return terminal
        progress = self._observe_waypoints(previous, observation)
        if isinstance(progress, TravelDecision):
            return progress
        self._pause_progress(observation)
        return self._decision(observation, distance=progress)

    def _pause_progress(self, observation: TravelObservation) -> None:
        # A known native cleanup pause is not evidence of a blocked route. Keep
        # accepted attempt/escape budgets and the certified handoff hint intact.
        self._dispatch_paused = True
        self._last_click_at_ms = None
        self._last_move_endpoint = None
        self._progress_at_ms = observation.now_ms
        self._last_click_distance = self._plan.destinations[self._waypoint_index].distance_from(
            observation.position
        )
        self._no_progress_clicks = 0
        self._escape_last_position = self._screen_position(observation)
        self._escape_no_motion_clicks = 0

    def _observe(self, observation: TravelObservation) -> TravelDecision | None:
        if not isinstance(observation, TravelObservation):
            raise ValueError("observation must be TravelObservation")
        if self._terminal is not None:
            return self._terminal
        previous = self._previous_observation
        if previous is not None and observation.now_ms < previous.now_ms:
            raise ValueError("observation time cannot move backwards")
        self._previous_observation = observation
        self._observe_ingress(observation)
        self._debug_route(observation)
        self._debug_event("observation", observation)
        if self._started_at_ms is None:
            self._started_at_ms = observation.now_ms
            self._debug_event("start", observation)
        if observation.now_ms - self._started_at_ms >= self._config.maximum_session_ms:
            return self._stop("session_timeout", observation)
        if observation.player.health_fraction < self._config.minimum_health_fraction:
            return self._stop("low_player_health", observation)
        return None

    def step(self, observation: TravelObservation) -> TravelDecision:
        previous = self._previous_observation
        terminal = self._observe(observation)
        if terminal is not None:
            return terminal

        progress = self._observe_waypoints(previous, observation)
        if isinstance(progress, TravelDecision):
            if self._proposal_checkpoint is not None:
                # Observed completion of a local frontier survives a deferred
                # proposal for the next leg, just like intermediate passage.
                self._proposal_checkpoint = self._checkpoint()
            return progress
        distance = progress
        resuming = self._dispatch_paused
        if resuming:
            self._pause_progress(observation)
            self._dispatch_paused = False
        if self._proposal_checkpoint is not None:
            # Real observed passage remains true even if the next target is not
            # submitted. Only speculative shortcut/escape advancement is undone.
            self._proposal_checkpoint = self._checkpoint()

        if self._escape_release_distance is not None and (
            self._escape_release_distance - distance >= self._config.escape_budget_reset_progress
        ):
            self._escape_sequence_count = 0
            self._escape_release_distance = None

        if self._attempt_count >= self._config.maximum_clicks:
            return self._stop("maximum_clicks", observation, distance=distance)
        interval_due = self._last_click_at_ms is None or (
            observation.now_ms - self._last_click_at_ms >= self._config.click_interval_ms
        )
        if self._escaping:
            return (
                self._dispatch_escape(observation, distance=distance, observe_motion=not resuming)
                if interval_due else self._decision(observation, distance=distance)
            )

        if (
            self._last_click_distance is not None
            and self._progress_at_ms is not None
            and observation.now_ms - self._progress_at_ms >= self._config.click_interval_ms
        ):
            progress = self._last_click_distance - distance
            self._last_click_distance = distance
            self._progress_at_ms = observation.now_ms
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

        lead = self._motion_lead(previous, observation)
        target, target_index = self._forward_target(observation, lead)
        if target is None:
            return self._stop("route_corridor_blocked", observation, distance=distance)
        remaining = (
            float("inf") if self._last_move_endpoint is None else hypot(
                self._last_move_endpoint.x - observation.position.lt,
                self._last_move_endpoint.y - observation.position.lg,
            )
        )
        changed = self._last_move_endpoint is None or hypot(
            target.x - self._last_move_endpoint.x, target.y - self._last_move_endpoint.y
        ) > 1e-6
        refresh_due = (
            changed and remaining <= lead
            and (self._last_click_at_ms is None or observation.now_ms - self._last_click_at_ms
                 >= self._config.target_refresh_interval_ms)
        )
        if not interval_due and not refresh_due:
            return self._decision(observation, distance=distance)
        shortcut = target_index != self._waypoint_index
        if shortcut:
            handoff_radius = min(
                item.arrival_radius
                for item in self._plan.destinations[self._waypoint_index:target_index]
            )
            self._waypoint_index = target_index
            self._reset_waypoint_progress()
            distance = self._plan.destinations[target_index].distance_from(observation.position)
            self._debug_event("waypoint", observation)
            self._handoff_target = TravelDestination(
                target.x, target.y, handoff_radius
            )
        if not shortcut and self._handoff_target is None:
            return self._dispatch_direct(
                observation, distance=distance, progress_refresh=not interval_due
            )
        return self._dispatch(
            observation, distance=distance,
            direction=Vector2(target.x - observation.position.lt,
                              -(target.y - observation.position.lg)),
            maneuver=TravelManeuver.DIRECT,
            progress_refresh=not interval_due,
        )

    def _observe_waypoints(
        self, previous: TravelObservation | None, observation: TravelObservation,
    ) -> float | TravelDecision:
        if self._handoff_target is not None and (
            self._handoff_target.distance_from(observation.position)
            <= self._handoff_target.arrival_radius
            or self._passed_waypoint(previous, observation, self._handoff_target)
        ):
            self._handoff_target = None
        destination = self._plan.destinations[self._waypoint_index]
        distance = destination.distance_from(observation.position)
        while distance <= destination.arrival_radius or (
            (self._waypoint_index < len(self._plan.destinations) - 1 or self._final_is_frontier)
            and self._passed_waypoint(previous, observation, destination)
        ):
            if self._waypoint_index == len(self._plan.destinations) - 1:
                return self._complete(observation, distance)
            self._waypoint_index += 1
            self._debug_event("waypoint", observation)
            self._reset_waypoint_progress()
            destination = self._plan.destinations[self._waypoint_index]
            distance = destination.distance_from(observation.position)

        return distance

    def _reset_waypoint_progress(self) -> None:
        self._last_click_at_ms = None
        self._last_click_distance = None
        self._progress_at_ms = None
        self._last_move_endpoint = None
        self._handoff_target = None
        self._no_progress_clicks = 0
        self._escape_sequence_count = 0
        self._escape_step = 0
        self._escape_phase = _EscapePhase.BACKUP
        self._escape_release_distance = None
        self._escaping = False

    @staticmethod
    def _passed_waypoint(
        previous: TravelObservation | None, current: TravelObservation,
        destination: TravelDestination,
    ) -> bool:
        if previous is None or current.now_ms <= previous.now_ms:
            return False
        dx = current.position.lt - previous.position.lt
        dy = current.position.lg - previous.position.lg
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return False
        fraction = ((destination.lt - previous.position.lt) * dx
                    + (destination.lg - previous.position.lg) * dy) / length_squared
        # Only a passed intermediate point; final arrival always requires a new
        # in-radius position and the independent arrival confirmation.
        return 0 <= fraction <= 1 and hypot(
            previous.position.lt + fraction * dx - destination.lt,
            previous.position.lg + fraction * dy - destination.lg,
        ) <= destination.arrival_radius

    def _motion_lead(
        self, previous: TravelObservation | None, current: TravelObservation,
    ) -> float:
        lead = min(5.0, self._config.maximum_click_distance)
        if previous is not None and current.now_ms > previous.now_ms:
            elapsed = current.now_ms - previous.now_ms
            motion = hypot(current.position.lt - previous.position.lt,
                           current.position.lg - previous.position.lg)
            lead = max(lead, motion * (elapsed + self._config.target_refresh_lead_ms) / elapsed)
        return min(lead, self._config.maximum_click_distance)

    def _forward_target(
        self, observation: TravelObservation, lead: float,
    ) -> tuple[Vector2 | None, int]:
        start = Vector2(observation.position.lt, observation.position.lg)
        destination = self._plan.destinations[self._waypoint_index]
        distance = destination.distance_from(observation.position)
        scale = min(1.0, self._config.maximum_click_distance / distance) if distance else 0.0
        target = Vector2(start.x + (destination.lt - start.x) * scale,
                         start.y + (destination.lg - start.y) * scale)
        index = self._waypoint_index
        if self._shortcut_clear is None:
            return target, index
        hint = self._handoff_target
        path_to_target = (target,) if hint is None else (Vector2(hint.lt, hint.lg), target)
        if not self._shortcut_clear(start, path_to_target):
            # A partial handoff is still a routing hint until observed passage.
            # Do not replace it with an uncertified ray to the far next waypoint.
            if hint is not None:
                fallback = Vector2(hint.lt, hint.lg)
                if self._shortcut_clear(start, (fallback,)):
                    return fallback, index
            return None, index
        if hint is not None or distance >= lead:
            return target, index
        # Intermediates are routing hints, never independent arrival claims.
        # Only bypass them through the actual route grid's cost/obstacle check.
        path = [Vector2(destination.lt, destination.lg)]
        budget = lead - distance
        for next_index in range(index + 1, len(self._plan.destinations)):
            next_destination = self._plan.destinations[next_index]
            origin = path[-1]
            length = hypot(next_destination.lt - origin.x, next_destination.lg - origin.y)
            scale = min(1.0, budget / length) if length else 1.0
            candidate = Vector2(origin.x + (next_destination.lt - origin.x) * scale,
                                origin.y + (next_destination.lg - origin.y) * scale)
            candidate_path = (*path, candidate)
            if not self._shortcut_clear(start, candidate_path):
                break
            target, index = candidate, next_index
            if length >= budget:
                break
            budget -= length
            path.append(candidate)
        return target, index

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
        progress_refresh: bool = False,
    ) -> TravelDecision:
        click_destination = None
        if direction is not None:
            length = hypot(direction.x, direction.y)
            if maneuver is TravelManeuver.DIRECT:
                click_distance = min(length, self._config.maximum_click_distance)
            elif maneuver is TravelManeuver.ESCAPE_BACKTRACK:
                click_distance = min(
                    self._config.escape_backtrack_distance,
                    self._config.maximum_click_distance,
                )
            else:
                clearance = (
                    self._config.escape_backup_clearance
                    if self._escape_phase is _EscapePhase.BACKUP
                    else self._escape_sweep_clearance()
                    if self._escape_phase is _EscapePhase.SWEEP
                    else self._config.escape_reacquire_progress
                )
                click_distance = min(clearance, self._config.maximum_click_distance)
            if length:
                click_destination = Vector2(
                    observation.position.lt + direction.x / length * click_distance,
                    observation.position.lg - direction.y / length * click_distance,
                )
        decision = TravelDecision(
            decision_id=self._next_decision_id(),
            now_ms=observation.now_ms,
            phase=TravelPhase.TRAVELING,
            waypoint_index=self._waypoint_index,
            distance_remaining=distance,
            click_count=self._click_count,
            minimap_direction=direction,
            click_destination=click_destination,
            maneuver=maneuver,
            progress_refresh=progress_refresh,
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
        progress_refresh: bool = False,
    ) -> TravelDecision:
        self._last_click_at_ms = observation.now_ms
        if not track_destination_progress:
            self._last_click_distance = None
            self._progress_at_ms = None
            self._last_move_endpoint = None
        elif self._progress_at_ms is None:
            self._last_click_distance = distance
            self._progress_at_ms = observation.now_ms
        self._click_count += 1
        if not progress_refresh:
            self._attempt_count += 1
        decision = self._decision(
            observation,
            distance=distance,
            direction=direction,
            maneuver=maneuver,
            progress_refresh=progress_refresh,
        )
        if track_destination_progress:
            self._last_move_endpoint = decision.click_destination
        return decision

    def _dispatch_direct(
        self,
        observation: TravelObservation,
        *,
        distance: float,
        progress_refresh: bool = False,
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
            progress_refresh=progress_refresh,
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
        length = hypot(self._ingress_direction.x, self._ingress_direction.y)
        if length > 0:
            self._escape_forward = self._ingress_direction
        else:
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
        observe_motion: bool = True,
    ) -> TravelDecision:
        if observe_motion:
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
            if self._escape_step == 0:
                direction = Vector2(-forward_x, -forward_y)
                maneuver = TravelManeuver.ESCAPE_BACKTRACK
            else:
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

    def _observe_ingress(self, observation: TravelObservation) -> None:
        position = self._screen_position(observation)
        previous = self._last_observed_position
        if previous is None:
            self._last_observed_position = position
            return
        if self._escaping:
            return
        delta_x = position.x - previous.x
        delta_y = position.y - previous.y
        distance = hypot(delta_x, delta_y)
        if distance >= min(1.0, self._config.minimum_progress):
            self._ingress_direction = Vector2(delta_x / distance, delta_y / distance)
            self._last_observed_position = position

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
            arrival_destination=self._plan.destinations[-1],
        )
        self._debug_event("arrival_candidate", observation, self._terminal)
        return self._terminal

    def _debug_route(self, observation: TravelObservation) -> None:
        if self._observer is None:
            return
        try:
            if self._debug_start is None:
                self._debug_start = (observation.position.lt, observation.position.lg)
            emit(
                self._observer,
                RouteEvent(
                    "route",
                    self._plan.plan_id,
                    self._debug_start,
                    tuple(
                        (p.lt, p.lg, p.arrival_radius)
                        for p in self._plan.destinations[:MAX_ROUTE_POINTS]
                    ),
                    max(0, len(self._plan.destinations) - MAX_ROUTE_POINTS),
                ),
            )
        except Exception:
            pass

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
                    else measured_position(position),
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
