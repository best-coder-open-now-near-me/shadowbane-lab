"""Runtime wiring for native observations and guarded semantic PvE input."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input import ClientInputAdapter, StopSignal
from shadowbane_lab.client_observation import (
    NativeCombatEventParser,
    NativeCombatLogEntry,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetIdentityReadError,
    NativeTargetPositionObservation,
)
from shadowbane_lab.protocol import ActionBinding, DecisionMessage, DispatchResult
from shadowbane_lab.pve.approach import (
    PvEApproachController,
    PvEApproachStatus,
    PvEApproachUpdate,
)
from shadowbane_lab.pve.controller import PvEController
from shadowbane_lab.pve.model import (
    PvEIntent,
    PvEObservation,
    PvEPhase,
    PvERunResult,
    PvERunTraceStep,
)
from shadowbane_lab.travel.runtime import TravelDecisionDispatcher


@runtime_checkable
class PvEIntentDispatcher(Protocol):
    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult: ...


@runtime_checkable
class TargetHealthSource(Protocol):
    def observe(self) -> NativeTargetHealthObservation: ...


@runtime_checkable
class PlayerVitalsSource(Protocol):
    def observe(self) -> NativePlayerVitalsObservation: ...


@runtime_checkable
class PlayerPositionSource(Protocol):
    def observe(self) -> NativePlayerPositionObservation: ...


@runtime_checkable
class TargetPositionSource(Protocol):
    def observe(self) -> NativeTargetPositionObservation: ...


@runtime_checkable
class TargetActionSource(Protocol):
    def observe(self) -> NativeTargetActionObservation: ...


@runtime_checkable
class PlayerActionSource(Protocol):
    def observe_player(self) -> NativePlayerActionObservation: ...


@runtime_checkable
class TargetIdentitySource(Protocol):
    def observe(self) -> NativeTargetIdentityObservation: ...


@runtime_checkable
class CombatLogSource(Protocol):
    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]: ...


class EmptyCombatLogSource:
    """Supplies no text events when native state is the combat authority."""

    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        return ()


class ClientPvEIntentDispatcher:
    """Wraps PvE intents in the shared semantic decision contract."""

    def __init__(self, adapter: ClientInputAdapter, *, agent_id: str = "client-self") -> None:
        if not isinstance(adapter, ClientInputAdapter):
            raise ValueError("adapter must be ClientInputAdapter")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self._adapter = adapter
        self._agent_id = agent_id

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        if not isinstance(intent, PvEIntent):
            raise ValueError("intent must be PvEIntent")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        correlation_id = f"pve:{sequence}:{intent.value}"
        return self._adapter.dispatch(
            DecisionMessage(
                message_id=f"message:{correlation_id}",
                correlation_id=correlation_id,
                observation_id=f"observation:pve:{sequence}",
                agent_id=self._agent_id,
                tick=sequence,
                affordance_id=f"affordance:pve:{sequence}:{intent.value}",
                action_key=intent.value,
                binding=ActionBinding(actor_id=self._agent_id),
            )
        )


class PvERunner:
    """Polls exact observations, withholding input through bounded read retries."""

    def __init__(
        self,
        *,
        controller: PvEController,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        player_position_reader: PlayerPositionSource | None = None,
        target_position_reader: TargetPositionSource | None = None,
        target_action_reader: TargetActionSource | None = None,
        player_action_reader: PlayerActionSource | None = None,
        target_identity_reader: TargetIdentitySource | None = None,
        combat_log_reader: CombatLogSource,
        dispatcher: PvEIntentDispatcher,
        approach_controller: PvEApproachController | None = None,
        movement_dispatcher: TravelDecisionDispatcher | None = None,
        stop_signal: StopSignal,
        poll_interval_ms: int = 100,
        maximum_consecutive_observation_failures: int = 3,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(controller, PvEController):
            raise ValueError("controller must be PvEController")
        if not isinstance(health_reader, TargetHealthSource):
            raise ValueError("health_reader must implement TargetHealthSource")
        if not isinstance(player_vitals_reader, PlayerVitalsSource):
            raise ValueError("player_vitals_reader must implement PlayerVitalsSource")
        if (player_position_reader is None) != (target_position_reader is None):
            raise ValueError("player and target position readers must be provided together")
        if player_position_reader is not None and not isinstance(
            player_position_reader, PlayerPositionSource
        ):
            raise ValueError("player_position_reader must implement PlayerPositionSource")
        if target_position_reader is not None and not isinstance(
            target_position_reader, TargetPositionSource
        ):
            raise ValueError("target_position_reader must implement TargetPositionSource")
        if target_action_reader is not None and not isinstance(
            target_action_reader, TargetActionSource
        ):
            raise ValueError("target_action_reader must implement TargetActionSource")
        if controller.requires_target_action and target_action_reader is None:
            raise ValueError("configured interrupt policy requires a target action reader")
        if player_action_reader is not None and not isinstance(
            player_action_reader,
            PlayerActionSource,
        ):
            raise ValueError("player_action_reader must implement PlayerActionSource")
        if target_identity_reader is not None and not isinstance(
            target_identity_reader, TargetIdentitySource
        ):
            raise ValueError("target_identity_reader must implement TargetIdentitySource")
        if controller.requires_target_identity and target_identity_reader is None:
            raise ValueError("configured target policy requires a target identity reader")
        if not isinstance(combat_log_reader, CombatLogSource):
            raise ValueError("combat_log_reader must implement CombatLogSource")
        if not isinstance(dispatcher, PvEIntentDispatcher):
            raise ValueError("dispatcher must implement PvEIntentDispatcher")
        if (approach_controller is None) != (movement_dispatcher is None):
            raise ValueError(
                "approach controller and movement dispatcher must be provided together"
            )
        if approach_controller is not None and not isinstance(
            approach_controller, PvEApproachController
        ):
            raise ValueError("approach_controller must be PvEApproachController")
        if movement_dispatcher is not None and not isinstance(
            movement_dispatcher, TravelDecisionDispatcher
        ):
            raise ValueError("movement_dispatcher must implement TravelDecisionDispatcher")
        if approach_controller is not None and player_position_reader is None:
            raise ValueError("approach controller requires player and target position readers")
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
            raise ValueError(
                "maximum_consecutive_observation_failures must be a positive integer"
            )
        self._controller = controller
        self._health_reader = health_reader
        self._player_vitals_reader = player_vitals_reader
        self._player_position_reader = player_position_reader
        self._target_position_reader = target_position_reader
        self._target_action_reader = target_action_reader
        self._player_action_reader = player_action_reader
        self._target_identity_reader = target_identity_reader
        self._combat_log_reader = combat_log_reader
        self._dispatcher = dispatcher
        self._approach_controller = approach_controller
        self._movement_dispatcher = movement_dispatcher
        self._stop_signal = stop_signal
        self._poll_interval_seconds = poll_interval_ms / 1000.0
        self._maximum_consecutive_observation_failures = (
            maximum_consecutive_observation_failures
        )
        self._clock = clock
        self._sleeper = sleeper
        self._parser = NativeCombatEventParser()

    def run(self) -> PvERunResult:
        trace: list[PvERunTraceStep] = []
        started_at = self._clock()
        terminal = None
        last_observation: PvEObservation | None = None
        consecutive_observation_failures = 0
        while terminal is None:
            now_ms = round((self._clock() - started_at) * 1000)
            if self._stop_signal.is_set():
                terminal = self._controller.stop("emergency_stop", now_ms=now_ms)
                trace.append(self._trace(terminal, observation=None))
                break
            try:
                target = self._health_reader.observe()
                target_action = (
                    None
                    if self._target_action_reader is None
                    or not self._controller.target_action_observation_active
                    else self._target_action_reader.observe()
                )
                player_action = (
                    None
                    if self._player_action_reader is None
                    or not self._controller.player_action_observation_active
                    else self._player_action_reader.observe_player()
                )
                target_identity = None
                if self._target_identity_reader is not None:
                    try:
                        target_identity = self._target_identity_reader.observe()
                    except NativeTargetIdentityReadError as exc:
                        if target.target_present:
                            assert target.target_token is not None
                            message = " ".join(str(exc).split())
                            target_identity = NativeTargetIdentityObservation.unavailable(
                                target_token=target.target_token,
                                error=f"{type(exc).__name__}:{message[:160]}",
                            )
                        else:
                            target_identity = NativeTargetIdentityObservation(
                                target_present=False
                            )
                target_position = (
                    None
                    if self._target_position_reader is None
                    else self._target_position_reader.observe()
                )
                player_position = (
                    None
                    if self._player_position_reader is None
                    else self._player_position_reader.observe()
                )
                if not target.target_present:
                    if target_position is not None and target_position.target_present:
                        target_position = NativeTargetPositionObservation(
                            target_present=False
                        )
                    if target_action is not None and target_action.target_present:
                        target_action = NativeTargetActionObservation(target_present=False)
                    if target_identity is not None and target_identity.target_present:
                        target_identity = NativeTargetIdentityObservation(
                            target_present=False
                        )
                player = self._player_vitals_reader.observe()
                events = tuple(
                    self._parser.parse(entry)
                    for entry in self._combat_log_reader.read_new_entries()
                )
                observation = PvEObservation(
                    now_ms=now_ms,
                    target=target,
                    player=player,
                    combat_events=events,
                    player_position=player_position,
                    target_position=target_position,
                    target_action=target_action,
                    player_action=player_action,
                    target_identity=target_identity,
                )
                last_observation = observation
                decision = self._controller.step(observation)
                approach = (
                    None
                    if self._approach_controller is None
                    else self._approach_controller.step(
                        observation,
                        phase=decision.phase,
                        reposition_requested=decision.reposition_requested,
                        camp=decision.camp,
                        return_to_camp=decision.return_to_camp,
                    )
                )
            except Exception as exc:
                consecutive_observation_failures += 1
                if (
                    consecutive_observation_failures
                    < self._maximum_consecutive_observation_failures
                ):
                    self._sleeper(self._poll_interval_seconds)
                    continue
                message = " ".join(str(exc).split())
                detail = f":{message[:160]}" if message else ""
                terminal = self._controller.stop(
                    f"observation_failure:{type(exc).__name__}{detail}",
                    now_ms=now_ms,
                )
                trace.append(self._trace(terminal, observation=None))
                break
            consecutive_observation_failures = 0

            accepted = None
            reason = None
            approach_accepted = None
            approach_reason = None
            movement_stop_accepted = None
            movement_stop_reason = None
            approach_decision = None if approach is None else approach.decision
            if approach_decision is not None and approach_decision.minimap_direction is not None:
                assert self._movement_dispatcher is not None
                try:
                    approach_result = self._movement_dispatcher.dispatch(approach_decision)
                except Exception as exc:
                    approach_reason = f"input_failure:{type(exc).__name__}"
                    trace.append(
                        self._trace(
                            decision,
                            observation=observation,
                            approach=approach,
                            approach_input_accepted=False,
                            approach_input_reason=approach_reason,
                        )
                    )
                    terminal = self._controller.stop(approach_reason, now_ms=now_ms)
                    trace.append(self._trace(terminal, observation=observation))
                    break
                approach_accepted = approach_result.accepted
                approach_reason = approach_result.reason
                if not approach_result.accepted:
                    trace.append(
                        self._trace(
                            decision,
                            observation=observation,
                            approach=approach,
                            approach_input_accepted=False,
                            approach_input_reason=approach_reason,
                        )
                    )
                    terminal = self._controller.stop(
                        "guarded_movement_input_rejected",
                        now_ms=now_ms,
                    )
                    trace.append(self._trace(terminal, observation=observation))
                    break
            if approach_decision is not None and approach_decision.terminal:
                assert self._movement_dispatcher is not None
                if approach_decision.click_count > 0:
                    try:
                        stop_result = self._movement_dispatcher.stop_movement(
                            approach_decision
                        )
                    except Exception as exc:
                        movement_stop_accepted = False
                        movement_stop_reason = f"input_failure:{type(exc).__name__}"
                    else:
                        movement_stop_accepted = stop_result.accepted
                        movement_stop_reason = stop_result.reason
                    if movement_stop_accepted is False:
                        trace.append(
                            self._trace(
                                decision,
                                observation=observation,
                                approach=approach,
                                approach_input_accepted=approach_accepted,
                                approach_input_reason=approach_reason,
                                movement_stop_accepted=False,
                                movement_stop_reason=movement_stop_reason,
                            )
                        )
                        terminal = self._controller.stop(
                            "movement_stop_rejected",
                            now_ms=now_ms,
                        )
                        trace.append(self._trace(terminal, observation=observation))
                        break
            if approach is not None and approach.status is PvEApproachStatus.FAILED:
                assert approach_decision is not None
                terminal_reason = approach_decision.terminal_reason or "unknown"
                trace.append(
                    self._trace(
                        decision,
                        observation=observation,
                        approach=approach,
                        approach_input_accepted=approach_accepted,
                        approach_input_reason=approach_reason,
                        movement_stop_accepted=movement_stop_accepted,
                        movement_stop_reason=movement_stop_reason,
                    )
                )
                recovery = self._controller.recover_from_approach_failure(
                    observation,
                    terminal_reason,
                )
                trace.append(self._trace(recovery, observation=observation))
                if recovery.terminal:
                    terminal = recovery
                    break
                self._sleeper(self._poll_interval_seconds)
                continue
            if decision.intent is not None:
                try:
                    result = self._dispatcher.dispatch(
                        decision.intent,
                        sequence=decision.decision_id,
                    )
                except Exception as exc:
                    reason = f"input_failure:{type(exc).__name__}"
                    trace.append(
                        self._trace(
                            decision,
                            observation=observation,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop(reason, now_ms=now_ms)
                    trace.append(self._trace(terminal, observation=observation))
                    break
                accepted = result.accepted
                reason = result.reason
                if not result.accepted:
                    trace.append(
                        self._trace(
                            decision,
                            observation=observation,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop(
                        "guarded_input_rejected",
                        now_ms=now_ms,
                    )
                    trace.append(self._trace(terminal, observation=observation))
                    break
            trace.append(
                self._trace(
                    decision,
                    observation=observation,
                    input_accepted=accepted,
                    input_reason=reason,
                    approach=approach,
                    approach_input_accepted=approach_accepted,
                    approach_input_reason=approach_reason,
                    movement_stop_accepted=movement_stop_accepted,
                    movement_stop_reason=movement_stop_reason,
                )
            )
            if decision.terminal:
                terminal = decision
                break
            self._sleeper(self._poll_interval_seconds)

        assert terminal is not None
        assert terminal.terminal_reason is not None
        final_phase = terminal.phase
        terminal_reason = terminal.terminal_reason
        if self._approach_controller is not None:
            cleanup = self._approach_controller.cancel("pve_run_terminal")
            cleanup_decision = cleanup.decision
            if cleanup_decision is not None and cleanup_decision.click_count > 0:
                assert self._movement_dispatcher is not None
                try:
                    cleanup_result = self._movement_dispatcher.stop_movement(
                        cleanup_decision
                    )
                except Exception as exc:
                    cleanup_accepted = False
                    cleanup_reason = f"input_failure:{type(exc).__name__}"
                else:
                    cleanup_accepted = cleanup_result.accepted
                    cleanup_reason = cleanup_result.reason
                trace.append(
                    self._trace(
                        terminal,
                        observation=last_observation,
                        approach=cleanup,
                        movement_stop_accepted=cleanup_accepted,
                        movement_stop_reason=cleanup_reason,
                    )
                )
                if not cleanup_accepted:
                    final_phase = PvEPhase.STOPPED
                    terminal_reason = "movement_stop_rejected"
        return PvERunResult(
            final_phase=final_phase,
            terminal_reason=terminal_reason,
            kills=terminal.kills,
            trace=tuple(trace),
        )

    @staticmethod
    def _trace(
        decision,
        *,
        observation: PvEObservation | None,
        input_accepted: bool | None = None,
        input_reason: str | None = None,
        approach: PvEApproachUpdate | None = None,
        approach_input_accepted: bool | None = None,
        approach_input_reason: str | None = None,
        movement_stop_accepted: bool | None = None,
        movement_stop_reason: str | None = None,
    ) -> PvERunTraceStep:
        return PvERunTraceStep(
            decision=decision,
            target_present=False if observation is None else observation.target.target_present,
            current_health=None if observation is None else observation.target.current_health,
            maximum_health=None if observation is None else observation.target.maximum_health,
            player_current_health=(
                None if observation is None else observation.player.current_health
            ),
            player_maximum_health=(
                None if observation is None else observation.player.maximum_health
            ),
            player_current_mana=(None if observation is None else observation.player.current_mana),
            player_maximum_mana=(None if observation is None else observation.player.maximum_mana),
            player_current_stamina=(
                None if observation is None else observation.player.current_stamina
            ),
            player_maximum_stamina=(
                None if observation is None else observation.player.maximum_stamina
            ),
            target_token=None if observation is None else observation.target.target_token,
            player_position=(None if observation is None else observation.player_position),
            target_position=(None if observation is None else observation.target_position),
            target_action=(None if observation is None else observation.target_action),
            player_action=(None if observation is None else observation.player_action),
            target_identity=(None if observation is None else observation.target_identity),
            target_planar_distance=(
                None if observation is None else observation.target_planar_distance
            ),
            target_altitude_delta=(
                None if observation is None else observation.target_altitude_delta
            ),
            target_spatial_distance=(
                None if observation is None else observation.target_spatial_distance
            ),
            combat_events=() if observation is None else observation.combat_events,
            input_accepted=input_accepted,
            input_reason=input_reason,
            approach_status=None if approach is None else approach.status.value,
            approach_decision=None if approach is None else approach.decision,
            approach_input_accepted=approach_input_accepted,
            approach_input_reason=approach_input_reason,
            movement_stop_accepted=movement_stop_accepted,
            movement_stop_reason=movement_stop_reason,
        )
