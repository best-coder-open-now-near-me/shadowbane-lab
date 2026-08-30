"""Authoritative action execution and scheduled-work lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from shadowbane_lab.protocol import ActionBinding
from shadowbane_lab.sim.actions import EffectPrimitive, PhaseKind


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


class ActionExecutionStatus(StrEnum):
    STARTED = "started"
    ACTIVE = "active"
    RELEASED = "released"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class PayloadReleaseStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    RELEASED = "released"


class ContinuationPolicy(StrEnum):
    """What owns scheduled work after its source state changes."""

    SOURCE_BOUND = "source_bound"
    DETACH_ON_RELEASE = "detach_on_release"
    EFFECT_INSTANCE_BOUND = "effect_instance_bound"
    TARGET_LIFE_BOUND = "target_life_bound"
    WORLD_BOUND = "world_bound"


@dataclass(frozen=True, slots=True)
class ActionExecutionSnapshot:
    correlation_id: str
    actor_entity_id: str
    actor_life_id: str
    target_life_id: str | None
    action_key: str
    binding: ActionBinding
    phase_index: int
    phase_kind: PhaseKind
    phase_started_at_ms: int
    phase_ends_at_ms: int
    status: ActionExecutionStatus
    phase_interruptible: bool
    movement_allowed: bool
    payload_release_status: PayloadReleaseStatus
    released_phase_indexes: tuple[int, ...]
    cancel_token: str
    cancel_on_damage: bool
    cancel_on_stun: bool
    pending_triggered_effects: tuple[EffectPrimitive, ...]
    trigger_payload_scheduled: bool


@dataclass(slots=True)
class ActionExecutionState:
    correlation_id: str
    actor_entity_id: str
    actor_life_id: str
    target_life_id: str | None
    action_key: str
    binding: ActionBinding
    phase_index: int
    phase_kind: PhaseKind
    phase_started_at_ms: int
    phase_ends_at_ms: int
    status: ActionExecutionStatus = ActionExecutionStatus.STARTED
    phase_interruptible: bool = False
    movement_allowed: bool = True
    payload_release_status: PayloadReleaseStatus = PayloadReleaseStatus.NOT_APPLICABLE
    released_phase_indexes: set[int] = field(default_factory=set)
    cancel_token: str = ""
    cancel_on_damage: bool = False
    cancel_on_stun: bool = False
    pending_triggered_effects: tuple[EffectPrimitive, ...] = ()
    trigger_payload_scheduled: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.correlation_id, "correlation_id"),
            (self.actor_entity_id, "actor_entity_id"),
            (self.actor_life_id, "actor_life_id"),
            (self.action_key, "action_key"),
            (self.cancel_token, "cancel_token"),
        ):
            _identifier(value, name)
        if self.target_life_id is not None:
            _identifier(self.target_life_id, "target_life_id")
        if not isinstance(self.binding, ActionBinding):
            raise ValueError("binding must be an ActionBinding")
        _non_negative_integer(self.phase_index, "phase_index")
        if not isinstance(self.phase_kind, PhaseKind):
            raise ValueError("phase_kind must be a PhaseKind")
        _non_negative_integer(self.phase_started_at_ms, "phase_started_at_ms")
        _non_negative_integer(self.phase_ends_at_ms, "phase_ends_at_ms")
        if self.phase_ends_at_ms < self.phase_started_at_ms:
            raise ValueError("phase_ends_at_ms must not precede phase_started_at_ms")
        if not isinstance(self.status, ActionExecutionStatus):
            raise ValueError("status must be an ActionExecutionStatus")
        if not isinstance(self.payload_release_status, PayloadReleaseStatus):
            raise ValueError("payload_release_status must be a PayloadReleaseStatus")
        for value, name in (
            (self.phase_interruptible, "phase_interruptible"),
            (self.movement_allowed, "movement_allowed"),
            (self.cancel_on_damage, "cancel_on_damage"),
            (self.cancel_on_stun, "cancel_on_stun"),
            (self.trigger_payload_scheduled, "trigger_payload_scheduled"),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
        self.released_phase_indexes = set(self.released_phase_indexes)
        for phase_index in self.released_phase_indexes:
            _non_negative_integer(phase_index, "released phase index")
        self.pending_triggered_effects = tuple(self.pending_triggered_effects)

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            ActionExecutionStatus.COMPLETED,
            ActionExecutionStatus.INTERRUPTED,
        }

    @property
    def current_phase_released(self) -> bool:
        return self.phase_index in self.released_phase_indexes

    def snapshot(self) -> ActionExecutionSnapshot:
        return ActionExecutionSnapshot(
            correlation_id=self.correlation_id,
            actor_entity_id=self.actor_entity_id,
            actor_life_id=self.actor_life_id,
            target_life_id=self.target_life_id,
            action_key=self.action_key,
            binding=self.binding,
            phase_index=self.phase_index,
            phase_kind=self.phase_kind,
            phase_started_at_ms=self.phase_started_at_ms,
            phase_ends_at_ms=self.phase_ends_at_ms,
            status=self.status,
            phase_interruptible=self.phase_interruptible,
            movement_allowed=self.movement_allowed,
            payload_release_status=self.payload_release_status,
            released_phase_indexes=tuple(sorted(self.released_phase_indexes)),
            cancel_token=self.cancel_token,
            cancel_on_damage=self.cancel_on_damage,
            cancel_on_stun=self.cancel_on_stun,
            pending_triggered_effects=self.pending_triggered_effects,
            trigger_payload_scheduled=self.trigger_payload_scheduled,
        )

    @classmethod
    def from_snapshot(cls, snapshot: ActionExecutionSnapshot) -> ActionExecutionState:
        return cls(
            correlation_id=snapshot.correlation_id,
            actor_entity_id=snapshot.actor_entity_id,
            actor_life_id=snapshot.actor_life_id,
            target_life_id=snapshot.target_life_id,
            action_key=snapshot.action_key,
            binding=snapshot.binding,
            phase_index=snapshot.phase_index,
            phase_kind=snapshot.phase_kind,
            phase_started_at_ms=snapshot.phase_started_at_ms,
            phase_ends_at_ms=snapshot.phase_ends_at_ms,
            status=snapshot.status,
            phase_interruptible=snapshot.phase_interruptible,
            movement_allowed=snapshot.movement_allowed,
            payload_release_status=snapshot.payload_release_status,
            released_phase_indexes=set(snapshot.released_phase_indexes),
            cancel_token=snapshot.cancel_token,
            cancel_on_damage=snapshot.cancel_on_damage,
            cancel_on_stun=snapshot.cancel_on_stun,
            pending_triggered_effects=snapshot.pending_triggered_effects,
            trigger_payload_scheduled=snapshot.trigger_payload_scheduled,
        )
