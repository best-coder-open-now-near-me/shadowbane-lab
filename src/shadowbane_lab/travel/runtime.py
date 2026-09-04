"""Runtime wiring for native position feedback and guarded minimap input."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input import ClientInputAdapter, StopSignal
from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.navigation_inspector.events import DiagnosticObserver, MotionEvent, emit
from shadowbane_lab.protocol import ActionBinding, DecisionMessage, DispatchResult, TargetKind
from shadowbane_lab.travel.model import (
    TravelDecision,
    TravelObservation,
    TravelPhase,
    TravelRunResult,
    TravelRunTraceStep,
)


@runtime_checkable
class PositionSource(Protocol):
    def observe(self) -> NativePlayerPositionObservation: ...


@runtime_checkable
class PlayerVitalsSource(Protocol):
    def observe(self) -> NativePlayerVitalsObservation: ...


@runtime_checkable
class TravelDecisionDispatcher(Protocol):
    def dispatch(self, decision: TravelDecision) -> DispatchResult: ...

    def stop_movement(self, decision: TravelDecision) -> DispatchResult: ...


@runtime_checkable
class TravelControl(Protocol):
    def step(self, observation: TravelObservation) -> TravelDecision: ...

    def stop(
        self,
        reason: str,
        observation: TravelObservation | None = None,
    ) -> TravelDecision: ...


class ClientTravelDecisionDispatcher:
    """Wraps minimap directions in the shared semantic movement contract."""

    def __init__(self, adapter: ClientInputAdapter, *, agent_id: str = "client-self") -> None:
        if not isinstance(adapter, ClientInputAdapter):
            raise ValueError("adapter must be ClientInputAdapter")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self._adapter = adapter
        self._agent_id = agent_id

    def dispatch(self, decision: TravelDecision) -> DispatchResult:
        if not isinstance(decision, TravelDecision):
            raise ValueError("decision must be TravelDecision")
        if decision.minimap_direction is None:
            raise ValueError("travel decision has no minimap direction")
        correlation_id = f"travel:{decision.decision_id}:minimap"
        return self._adapter.dispatch(
            DecisionMessage(
                message_id=f"message:{correlation_id}",
                correlation_id=correlation_id,
                observation_id=f"observation:travel:{decision.decision_id}",
                agent_id=self._agent_id,
                tick=decision.decision_id,
                affordance_id=f"affordance:{correlation_id}",
                action_key=self._adapter_action_key,
                binding=ActionBinding(
                    actor_id=self._agent_id,
                    target_kind=TargetKind.DIRECTION,
                    direction=decision.minimap_direction,
                ),
            )
        )

    def stop_movement(self, decision: TravelDecision) -> DispatchResult:
        if not isinstance(decision, TravelDecision):
            raise ValueError("decision must be TravelDecision")
        if not decision.terminal:
            raise ValueError("movement may be stopped only for a terminal travel decision")
        return self._adapter.dispatch_movement_stop(
            correlation_id=f"travel:{decision.decision_id}:stop"
        )

    @property
    def _adapter_action_key(self) -> str:
        return self._adapter.profile.movement.action_key


class TravelRunner:
    """Poll exact feedback and dispatch bounded minimap click leases."""

    def __init__(
        self,
        *,
        controller: TravelControl,
        position_reader: PositionSource,
        player_vitals_reader: PlayerVitalsSource,
        dispatcher: TravelDecisionDispatcher,
        stop_signal: StopSignal,
        poll_interval_ms: int = 200,
        maximum_consecutive_observation_failures: int = 3,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        observer: DiagnosticObserver | None = None,
    ) -> None:
        if not isinstance(controller, TravelControl):
            raise ValueError("controller must implement TravelControl")
        if not isinstance(position_reader, PositionSource):
            raise ValueError("position_reader must implement PositionSource")
        if not isinstance(player_vitals_reader, PlayerVitalsSource):
            raise ValueError("player_vitals_reader must implement PlayerVitalsSource")
        if not isinstance(dispatcher, TravelDecisionDispatcher):
            raise ValueError("dispatcher must implement TravelDecisionDispatcher")
        if not isinstance(stop_signal, StopSignal):
            raise ValueError("stop_signal must implement StopSignal")
        if (
            isinstance(poll_interval_ms, bool)
            or not isinstance(poll_interval_ms, int)
            or poll_interval_ms <= 0
        ):
            raise ValueError("poll_interval_ms must be a positive integer")
        if (
            isinstance(maximum_consecutive_observation_failures, bool)
            or not isinstance(maximum_consecutive_observation_failures, int)
            or maximum_consecutive_observation_failures <= 0
        ):
            raise ValueError("maximum_consecutive_observation_failures must be a positive integer")
        self._observer = observer
        self._controller = controller
        self._position_reader = position_reader
        self._player_vitals_reader = player_vitals_reader
        self._dispatcher = dispatcher
        self._stop_signal = stop_signal
        self._poll_interval_seconds = poll_interval_ms / 1000.0
        self._maximum_observation_failures = maximum_consecutive_observation_failures
        self._clock = clock
        self._sleeper = sleeper

    def run(self) -> TravelRunResult:
        trace: list[TravelRunTraceStep] = []
        started_at = self._clock()
        last_observation: TravelObservation | None = None
        consecutive_failures = 0
        terminal: TravelDecision | None = None
        stop_input_accepted: bool | None = None
        stop_input_reason: str | None = None
        while terminal is None:
            if self._stop_signal.is_set():
                terminal = self._controller.stop("emergency_stop", last_observation)
                trace.append(self._trace(terminal, last_observation))
                break
            try:
                observation = TravelObservation(
                    now_ms=round((self._clock() - started_at) * 1000),
                    position=self._position_reader.observe(),
                    player=self._player_vitals_reader.observe(),
                )
                last_observation = observation
                decision = self._controller.step(observation)
            except Exception as exc:
                consecutive_failures += 1
                if consecutive_failures < self._maximum_observation_failures:
                    self._sleeper(self._poll_interval_seconds)
                    continue
                message = " ".join(str(exc).split())
                detail = f":{message[:160]}" if message else ""
                terminal = self._controller.stop(
                    f"observation_failure:{type(exc).__name__}{detail}",
                    last_observation,
                )
                trace.append(self._trace(terminal, last_observation))
                break
            consecutive_failures = 0

            accepted = None
            reason = None
            if decision.minimap_direction is not None:
                try:
                    result = self._dispatcher.dispatch(decision)
                except Exception as exc:
                    reason = f"input_failure:{type(exc).__name__}"
                    trace.append(
                        self._trace(
                            decision,
                            observation,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop(reason, observation)
                    trace.append(self._trace(terminal, observation))
                    break
                accepted = result.accepted
                reason = result.reason
                if not result.accepted:
                    trace.append(
                        self._trace(
                            decision,
                            observation,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop("guarded_input_rejected", observation)
                    trace.append(self._trace(terminal, observation))
                    break
            trace.append(
                self._trace(
                    decision,
                    observation,
                    input_accepted=accepted,
                    input_reason=reason,
                )
            )
            if decision.terminal:
                terminal = decision
                if decision.click_count > 0:
                    try:
                        stop_result = self._dispatcher.stop_movement(decision)
                        stop_input_accepted = stop_result.accepted
                        stop_input_reason = stop_result.reason
                    except Exception as exc:
                        stop_input_accepted = False
                        stop_input_reason = f"input_failure:{type(exc).__name__}"
                break
            self._sleeper(self._poll_interval_seconds)

        assert terminal is not None
        assert terminal.terminal_reason is not None
        final_phase = terminal.phase
        terminal_reason = terminal.terminal_reason
        if stop_input_accepted is False:
            final_phase = TravelPhase.STOPPED
            terminal_reason = "movement_stop_rejected"
            self._debug_result("failure", terminal.now_ms, terminal_reason)
        if stop_input_accepted is not None:
            self._debug_result(
                "stop_accepted" if stop_input_accepted else "stop_rejected",
                terminal.now_ms,
                stop_input_reason,
            )
        return TravelRunResult(
            final_phase=final_phase,
            terminal_reason=terminal_reason,
            final_position=None if last_observation is None else last_observation.position,
            clicks=terminal.click_count,
            trace=tuple(trace),
            stop_input_accepted=stop_input_accepted,
            stop_input_reason=stop_input_reason,
        )

    def _trace(
        self,
        decision: TravelDecision,
        observation: TravelObservation | None,
        *,
        input_accepted: bool | None = None,
        input_reason: str | None = None,
    ) -> TravelRunTraceStep:
        if input_accepted is not None:
            self._debug_result(
                "input_accepted" if input_accepted else "input_rejected",
                decision.now_ms,
                input_reason,
            )
        if decision.terminal:
            self._debug_result(
                "completion"
                if decision.phase is TravelPhase.COMPLETE
                else "cancelled"
                if decision.terminal_reason == "emergency_stop"
                else "failure",
                decision.now_ms,
                decision.terminal_reason,
            )
        return TravelRunTraceStep(
            decision=decision,
            position=None if observation is None else observation.position,
            health_fraction=None if observation is None else observation.player.health_fraction,
            input_accepted=input_accepted,
            input_reason=input_reason,
        )

    def _debug_result(self, event: str, now_ms: int, reason: str | None) -> None:
        if self._observer is not None:
            emit(self._observer, MotionEvent("motion", event, "runtime", now_ms, reason=reason))
