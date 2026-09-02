"""Coherent PvE observation assembly and fail-closed runtime stage boundaries."""

from __future__ import annotations

from collections import deque
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_observation import (
    NativeCombatEventParser,
    NativeTargetActionObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetIdentityReadError,
    NativeTargetPositionObservation,
)
from shadowbane_lab.pve.approach import PvEApproachStatus
from shadowbane_lab.pve.model import (
    PvEObservation,
    PvEPhase,
    PvERunResult,
    PvERunTraceStep,
)
from shadowbane_lab.pve.runtime import (
    CharacterPopulationSource,
    CombatLogSource,
    PlayerActionSource,
    PlayerPositionSource,
    PlayerVitalsSource,
    TargetActionSource,
    TargetHealthSource,
    TargetIdentitySource,
    TargetPositionSource,
)
from shadowbane_lab.pve.runtime import (
    PvERunner as _BasePvERunner,
)


class PvEObservationCoherenceError(RuntimeError):
    """Raised when native channels do not describe one stable selected target."""


@runtime_checkable
class PvEObservationSource(Protocol):
    """Build one controller-ready observation from an explicit channel request."""

    def observe(
        self,
        *,
        now_ms: int,
        target_action_active: bool,
        player_action_active: bool,
    ) -> PvEObservation: ...


class NativePvEObservationSource:
    """Assemble native channels behind one selected-target stability boundary.

    Process-backed target-health readers are sampled at the beginning and end of
    each frame. Tape and sequence readers have no process identity and are treated
    as already atomic, preserving deterministic replay and existing test fixtures.
    """

    def __init__(
        self,
        *,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        combat_log_reader: CombatLogSource,
        player_position_reader: PlayerPositionSource | None = None,
        target_position_reader: TargetPositionSource | None = None,
        target_action_reader: TargetActionSource | None = None,
        player_action_reader: PlayerActionSource | None = None,
        target_identity_reader: TargetIdentitySource | None = None,
        population_reader: CharacterPopulationSource | None = None,
    ) -> None:
        if not isinstance(health_reader, TargetHealthSource):
            raise ValueError("health_reader must implement TargetHealthSource")
        if not isinstance(player_vitals_reader, PlayerVitalsSource):
            raise ValueError("player_vitals_reader must implement PlayerVitalsSource")
        if not isinstance(combat_log_reader, CombatLogSource):
            raise ValueError("combat_log_reader must implement CombatLogSource")
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
        if player_action_reader is not None and not isinstance(
            player_action_reader, PlayerActionSource
        ):
            raise ValueError("player_action_reader must implement PlayerActionSource")
        if target_identity_reader is not None and not isinstance(
            target_identity_reader, TargetIdentitySource
        ):
            raise ValueError("target_identity_reader must implement TargetIdentitySource")
        if population_reader is not None and not isinstance(
            population_reader, CharacterPopulationSource
        ):
            raise ValueError("population_reader must implement CharacterPopulationSource")

        process_ids = {
            process_id
            for reader in (
                health_reader,
                player_vitals_reader,
                player_position_reader,
                target_position_reader,
                target_action_reader,
                player_action_reader,
                target_identity_reader,
                population_reader,
                combat_log_reader,
            )
            if (process_id := self._process_id(reader)) is not None
        }
        if len(process_ids) > 1:
            raise ValueError("native PvE observation readers resolved different processes")

        self._health_reader = health_reader
        self._player_vitals_reader = player_vitals_reader
        self._player_position_reader = player_position_reader
        self._target_position_reader = target_position_reader
        self._target_action_reader = target_action_reader
        self._player_action_reader = player_action_reader
        self._target_identity_reader = target_identity_reader
        self._population_reader = population_reader
        self._combat_log_reader = combat_log_reader
        self._parser = NativeCombatEventParser()
        self._selection_boundary_enabled = self._process_id(health_reader) is not None

    @property
    def selection_boundary_enabled(self) -> bool:
        """Whether the source performs the second process-backed target sample."""

        return self._selection_boundary_enabled

    def observe(
        self,
        *,
        now_ms: int,
        target_action_active: bool,
        player_action_active: bool,
    ) -> PvEObservation:
        if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
            raise ValueError("now_ms must be a non-negative integer")
        if not isinstance(target_action_active, bool):
            raise ValueError("target_action_active must be boolean")
        if not isinstance(player_action_active, bool):
            raise ValueError("player_action_active must be boolean")

        target = self._health_reader.observe()
        population = (
            None if self._population_reader is None else self._population_reader.observe()
        )
        target_action = (
            None
            if self._target_action_reader is None or not target_action_active
            else self._target_action_reader.observe()
        )
        player_action = (
            None
            if self._player_action_reader is None or not player_action_active
            else self._player_action_reader.observe_player()
        )
        target_identity = self._observe_target_identity(target)
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
        player = self._player_vitals_reader.observe()

        if self._selection_boundary_enabled:
            boundary = self._health_reader.observe()
            if not self._same_selection(target, boundary):
                raise PvEObservationCoherenceError(
                    "selected target changed during native PvE frame assembly"
                )
            target = boundary

        if not target.target_present:
            target_position = self._absent_target_position(target_position)
            target_action = self._absent_target_action(target_action)
            target_identity = self._absent_target_identity(target_identity)

        events = tuple(
            self._parser.parse(entry)
            for entry in self._combat_log_reader.read_new_entries()
        )
        return PvEObservation(
            now_ms=now_ms,
            target=target,
            player=player,
            combat_events=events,
            player_position=player_position,
            target_position=target_position,
            target_action=target_action,
            player_action=player_action,
            target_identity=target_identity,
            population=population,
        )

    def _observe_target_identity(
        self,
        target: NativeTargetHealthObservation,
    ) -> NativeTargetIdentityObservation | None:
        if self._target_identity_reader is None:
            return None
        try:
            return self._target_identity_reader.observe()
        except NativeTargetIdentityReadError as exc:
            if not target.target_present:
                return NativeTargetIdentityObservation(target_present=False)
            assert target.target_token is not None
            message = " ".join(str(exc).split())
            return NativeTargetIdentityObservation.unavailable(
                target_token=target.target_token,
                error=f"{type(exc).__name__}:{message[:160]}",
            )

    @staticmethod
    def _same_selection(
        first: NativeTargetHealthObservation,
        second: NativeTargetHealthObservation,
    ) -> bool:
        return (
            first.target_present == second.target_present
            and first.target_token == second.target_token
        )

    @staticmethod
    def _absent_target_position(
        value: NativeTargetPositionObservation | None,
    ) -> NativeTargetPositionObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetPositionObservation(target_present=False)

    @staticmethod
    def _absent_target_action(
        value: NativeTargetActionObservation | None,
    ) -> NativeTargetActionObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetActionObservation(target_present=False)

    @staticmethod
    def _absent_target_identity(
        value: NativeTargetIdentityObservation | None,
    ) -> NativeTargetIdentityObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetIdentityObservation(target_present=False)

    @staticmethod
    def _process_id(reader: object | None) -> int | None:
        if reader is None:
            return None
        value = getattr(reader, "process_id", None)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value


class PvERunner(_BasePvERunner):
    """Run PvE with coherent observations and explicit failure-stage taxonomy."""

    def run(self) -> PvERunResult:
        trace: list[PvERunTraceStep] | deque[PvERunTraceStep]
        if self._maximum_retained_trace_steps is None:
            trace = []
        else:
            trace = deque(maxlen=self._maximum_retained_trace_steps)
        total_steps = 0

        def record(step: PvERunTraceStep) -> None:
            nonlocal total_steps
            trace.append(step)
            total_steps += 1
            if self._trace_sink is not None:
                self._trace_sink(step)

        observation_source = NativePvEObservationSource(
            health_reader=self._health_reader,
            player_vitals_reader=self._player_vitals_reader,
            player_position_reader=self._player_position_reader,
            target_position_reader=self._target_position_reader,
            target_action_reader=self._target_action_reader,
            player_action_reader=self._player_action_reader,
            target_identity_reader=self._target_identity_reader,
            population_reader=self._population_reader,
            combat_log_reader=self._combat_log_reader,
        )

        started_at = self._clock()
        terminal = None
        last_observation: PvEObservation | None = None
        consecutive_observation_failures = 0
        while terminal is None:
            now_ms = round((self._clock() - started_at) * 1000)
            if self._stop_signal.is_set():
                terminal = self._controller.stop("emergency_stop", now_ms=now_ms)
                record(self._trace(terminal, observation=None))
                break

            try:
                observation = observation_source.observe(
                    now_ms=now_ms,
                    target_action_active=self._controller.target_action_observation_active,
                    player_action_active=self._controller.player_action_observation_active,
                )
            except Exception as exc:
                consecutive_observation_failures += 1
                if (
                    consecutive_observation_failures
                    < self._maximum_consecutive_observation_failures
                ):
                    self._sleeper(self._poll_interval_seconds)
                    continue
                prefix = (
                    "observation_coherence_failure"
                    if isinstance(exc, PvEObservationCoherenceError)
                    else "observation_failure"
                )
                terminal = self._controller.stop(
                    self._failure_reason(prefix, exc),
                    now_ms=now_ms,
                )
                record(self._trace(terminal, observation=None))
                break

            consecutive_observation_failures = 0
            last_observation = observation
            try:
                decision = self._controller.step(observation)
            except Exception as exc:
                terminal = self._controller.stop(
                    self._failure_reason("decision_failure", exc),
                    now_ms=now_ms,
                )
                record(self._trace(terminal, observation=observation))
                break

            try:
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
                record(self._trace(decision, observation=observation))
                terminal = self._controller.stop(
                    self._failure_reason("approach_failure", exc),
                    now_ms=now_ms,
                )
                record(self._trace(terminal, observation=observation))
                break

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
                    record(
                        self._trace(
                            decision,
                            observation=observation,
                            approach=approach,
                            approach_input_accepted=False,
                            approach_input_reason=approach_reason,
                        )
                    )
                    terminal = self._controller.stop(approach_reason, now_ms=now_ms)
                    record(self._trace(terminal, observation=observation))
                    break
                approach_accepted = approach_result.accepted
                approach_reason = approach_result.reason
                if not approach_result.accepted:
                    record(
                        self._trace(
                            decision,
                            observation=observation,
                            approach=approach,
                            approach_input_accepted=False,
                            approach_input_reason=approach_reason,
                        )
                    )
                    stop_reason = (
                        "emergency_stop"
                        if self._stop_signal.is_set()
                        else "guarded_movement_input_rejected"
                    )
                    terminal = self._controller.stop(stop_reason, now_ms=now_ms)
                    record(self._trace(terminal, observation=observation))
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
                        record(
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
                        stop_reason = (
                            "emergency_stop"
                            if self._stop_signal.is_set()
                            else "movement_stop_rejected"
                        )
                        terminal = self._controller.stop(stop_reason, now_ms=now_ms)
                        record(self._trace(terminal, observation=observation))
                        break
            if approach is not None and approach.status is PvEApproachStatus.FAILED:
                assert approach_decision is not None
                terminal_reason = approach_decision.terminal_reason or "unknown"
                record(
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
                record(self._trace(recovery, observation=observation))
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
                    record(
                        self._trace(
                            decision,
                            observation=observation,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop(reason, now_ms=now_ms)
                    record(self._trace(terminal, observation=observation))
                    break
                accepted = result.accepted
                reason = result.reason
                if not result.accepted:
                    record(
                        self._trace(
                            decision,
                            observation=observation,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    stop_reason = (
                        "emergency_stop"
                        if self._stop_signal.is_set()
                        else "guarded_input_rejected"
                    )
                    terminal = self._controller.stop(stop_reason, now_ms=now_ms)
                    record(self._trace(terminal, observation=observation))
                    break
            record(
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
                record(
                    self._trace(
                        terminal,
                        observation=last_observation,
                        approach=cleanup,
                        movement_stop_accepted=cleanup_accepted,
                        movement_stop_reason=cleanup_reason,
                    )
                )
                if not cleanup_accepted and not self._stop_signal.is_set():
                    final_phase = PvEPhase.STOPPED
                    terminal_reason = "movement_stop_rejected"
        return PvERunResult(
            final_phase=final_phase,
            terminal_reason=terminal_reason,
            kills=terminal.kills,
            trace=tuple(trace),
            total_steps=total_steps,
            trace_truncated=total_steps > len(trace),
        )

    @staticmethod
    def _failure_reason(prefix: str, exc: Exception) -> str:
        message = " ".join(str(exc).split())
        detail = f":{message[:160]}" if message else ""
        return f"{prefix}:{type(exc).__name__}{detail}"
