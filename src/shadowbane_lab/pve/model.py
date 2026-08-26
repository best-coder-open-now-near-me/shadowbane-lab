"""Typed contracts for the bounded PvE controller and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.client_observation import (
    NativeCombatEvent,
    NativeTargetHealthObservation,
)


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


class PvEIntent(StrEnum):
    ACQUIRE_NEXT_MOB = "client.pve.target_next_mobile"
    ATTACK_SELECTED_TARGET = "shadowbane.basic_attack"


class PvEPhase(StrEnum):
    INITIALIZING = "initializing"
    SEEKING = "seeking"
    ENGAGED = "engaged"
    POST_KILL = "post_kill"
    COMPLETE = "complete"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class PvEControllerConfig:
    maximum_kills: int = 1
    maximum_session_ms: int = 120_000
    acquisition_retry_ms: int = 1_000
    acquisition_timeout_ms: int = 15_000
    engagement_timeout_ms: int = 30_000
    stalled_progress_ms: int = 5_000
    selection_loss_grace_ms: int = 750
    post_kill_delay_ms: int = 1_000
    maximum_reengage_attempts: int = 2

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.maximum_kills, "maximum_kills"),
            (self.maximum_session_ms, "maximum_session_ms"),
            (self.acquisition_retry_ms, "acquisition_retry_ms"),
            (self.acquisition_timeout_ms, "acquisition_timeout_ms"),
            (self.engagement_timeout_ms, "engagement_timeout_ms"),
            (self.stalled_progress_ms, "stalled_progress_ms"),
            (self.selection_loss_grace_ms, "selection_loss_grace_ms"),
            (self.post_kill_delay_ms, "post_kill_delay_ms"),
        ):
            _positive_integer(value, field_name)
        _non_negative_integer(self.maximum_reengage_attempts, "maximum_reengage_attempts")
        if self.acquisition_retry_ms > self.acquisition_timeout_ms:
            raise ValueError("acquisition retry cannot exceed acquisition timeout")
        if self.stalled_progress_ms > self.engagement_timeout_ms:
            raise ValueError("stalled progress timeout cannot exceed engagement timeout")
        if self.selection_loss_grace_ms > self.engagement_timeout_ms:
            raise ValueError("selection loss grace cannot exceed engagement timeout")


@dataclass(frozen=True, slots=True)
class PvEObservation:
    now_ms: int
    target: NativeTargetHealthObservation
    combat_events: tuple[NativeCombatEvent, ...] = ()

    def __post_init__(self) -> None:
        _non_negative_integer(self.now_ms, "now_ms")
        if not isinstance(self.target, NativeTargetHealthObservation):
            raise ValueError("target must be NativeTargetHealthObservation")
        if any(not isinstance(event, NativeCombatEvent) for event in self.combat_events):
            raise ValueError("combat_events must contain NativeCombatEvent values")
        sequences = tuple(event.sequence for event in self.combat_events)
        if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
            raise ValueError("combat events must have unique ascending sequences")


@dataclass(frozen=True, slots=True)
class PvEControllerDecision:
    decision_id: int
    now_ms: int
    phase: PvEPhase
    kills: int
    intent: PvEIntent | None = None
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.decision_id, "decision_id")
        _non_negative_integer(self.now_ms, "now_ms")
        _non_negative_integer(self.kills, "kills")
        if not isinstance(self.phase, PvEPhase):
            raise ValueError("phase must be PvEPhase")
        if self.intent is not None and not isinstance(self.intent, PvEIntent):
            raise ValueError("intent must be PvEIntent when present")
        terminal = self.phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)
        if terminal != (self.terminal_reason is not None):
            raise ValueError("terminal phases require exactly one terminal reason")
        if terminal and self.intent is not None:
            raise ValueError("terminal decisions cannot dispatch an intent")

    @property
    def terminal(self) -> bool:
        return self.phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)


@dataclass(frozen=True, slots=True)
class PvERunTraceStep:
    decision: PvEControllerDecision
    target_present: bool
    current_health: float | None
    maximum_health: float | None
    input_accepted: bool | None = None
    input_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PvEControllerDecision):
            raise ValueError("decision must be PvEControllerDecision")
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be a boolean")
        if self.input_accepted is not None and not isinstance(self.input_accepted, bool):
            raise ValueError("input_accepted must be a boolean when present")
        if self.decision.intent is None and self.input_accepted is not None:
            raise ValueError("input outcome requires a dispatched intent")
        if self.input_reason is not None and self.input_accepted is not False:
            raise ValueError("input_reason is valid only for rejected input")


@dataclass(frozen=True, slots=True)
class PvERunResult:
    final_phase: PvEPhase
    terminal_reason: str
    kills: int
    trace: tuple[PvERunTraceStep, ...]

    def __post_init__(self) -> None:
        if self.final_phase not in (PvEPhase.COMPLETE, PvEPhase.STOPPED):
            raise ValueError("PvE run result must be terminal")
        if not isinstance(self.terminal_reason, str) or not self.terminal_reason.strip():
            raise ValueError("terminal_reason must be a non-empty string")
        _non_negative_integer(self.kills, "kills")
        if any(not isinstance(step, PvERunTraceStep) for step in self.trace):
            raise ValueError("trace must contain PvERunTraceStep values")
