"""Immutable exchange, schedule, and environment snapshot records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.protocol import (
    ActionBinding,
    AffordanceSetMessage,
    DecisionMessage,
    ObservationMessage,
)
from shadowbane_lab.sim.actions import EffectPrimitive, WeaponAttackSpec
from shadowbane_lab.sim.clock import ClockSnapshot
from shadowbane_lab.sim.random_source import RandomSnapshot
from shadowbane_lab.sim.state import EntitySnapshot


class ScheduledKind(StrEnum):
    RESOLUTION = "resolution"
    WEAPON_ATTACK = "weapon_attack"
    COMPLETION = "completion"
    EFFECT_EXPIRY = "effect_expiry"


@dataclass(frozen=True, slots=True)
class ScheduledItem:
    due_time_ms: int
    order: int
    kind: ScheduledKind
    actor_id: str
    correlation_id: str
    action_key: str
    binding: ActionBinding | None = None
    phase_duration_ms: int = 0
    effects: tuple[EffectPrimitive, ...] = ()
    weapon_attack: WeaponAttackSpec | None = None
    trigger_key: str | None = None
    effect_entity_id: str | None = None
    effect_storage_key: str | None = None
    expected_effect_key: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.due_time_ms, bool)
            or not isinstance(self.due_time_ms, int)
            or self.due_time_ms < 0
        ):
            raise ValueError("due_time_ms must be a non-negative integer")
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order < 0:
            raise ValueError("order must be a non-negative integer")
        if not isinstance(self.kind, ScheduledKind):
            raise ValueError("kind must be a ScheduledKind")
        for value, name in (
            (self.actor_id, "actor_id"),
            (self.correlation_id, "correlation_id"),
            (self.action_key, "action_key"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if (
            isinstance(self.phase_duration_ms, bool)
            or not isinstance(self.phase_duration_ms, int)
            or self.phase_duration_ms < 0
        ):
            raise ValueError("phase_duration_ms must be a non-negative integer")
        if self.kind is ScheduledKind.RESOLUTION:
            if self.binding is None or not self.effects or self.weapon_attack is not None:
                raise ValueError("resolutions require a binding and effects only")
        elif self.kind is ScheduledKind.WEAPON_ATTACK:
            if self.binding is None or self.weapon_attack is None or self.effects:
                raise ValueError("weapon attacks require a binding and weapon spec only")
        elif self.binding is not None or self.effects or self.weapon_attack is not None:
            raise ValueError("only resolutions and weapon attacks may carry bindings")
        if self.trigger_key is not None:
            if self.kind is not ScheduledKind.RESOLUTION:
                raise ValueError("trigger_key is valid only for effect resolutions")
            if not isinstance(self.trigger_key, str) or not self.trigger_key.strip():
                raise ValueError("trigger_key must be a non-empty string")
        if self.kind is ScheduledKind.EFFECT_EXPIRY:
            for value, name in (
                (self.effect_entity_id, "effect_entity_id"),
                (self.effect_storage_key, "effect_storage_key"),
                (self.expected_effect_key, "expected_effect_key"),
            ):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"effect expiry requires {name}")
        elif any(
            value is not None
            for value in (
                self.effect_entity_id,
                self.effect_storage_key,
                self.expected_effect_key,
            )
        ):
            raise ValueError("only effect expiry items may carry effect identifiers")


@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    clock: ClockSnapshot
    random: RandomSnapshot
    entities: tuple[EntitySnapshot, ...]
    scheduled: tuple[ScheduledItem, ...]
    next_schedule_order: int
    next_event_number: int


@dataclass(frozen=True, slots=True)
class AgentExchange:
    observation: ObservationMessage
    affordances: AffordanceSetMessage

    def decision(
        self,
        affordance_id: str,
        correlation_id: str,
        message_id: str | None = None,
    ) -> DecisionMessage:
        selected = next(
            (
                affordance
                for affordance in self.affordances.affordances
                if affordance.affordance_id == affordance_id
            ),
            None,
        )
        if selected is None:
            raise KeyError(f"unknown affordance id: {affordance_id}")
        return DecisionMessage(
            message_id=message_id or f"message:{correlation_id}",
            correlation_id=correlation_id,
            observation_id=self.observation.observation_id,
            agent_id=self.observation.agent_id,
            tick=self.observation.tick,
            affordance_id=selected.affordance_id,
            action_key=selected.action_key,
            binding=selected.binding,
        )
