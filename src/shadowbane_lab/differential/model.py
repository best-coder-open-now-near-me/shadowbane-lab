"""Immutable semantic traces used for simulator-to-emulator comparison."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from shadowbane_lab.protocol import (
    AffordanceSetMessage,
    DecisionMessage,
    EventBatchMessage,
    NamedScalar,
    Vector2,
)

TRACE_SCHEMA_VERSION = 1


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _unique_named_scalars(values: tuple[NamedScalar, ...]) -> None:
    if any(not isinstance(value, NamedScalar) for value in values):
        raise ValueError("scalars must contain NamedScalar values")
    names = tuple(value.name for value in values)
    if len(names) != len(set(names)):
        raise ValueError("scalar names must be unique")


class TraceSource(StrEnum):
    REFERENCE_SIMULATOR = "reference_simulator"
    EMULATOR_SERVER = "emulator_server"
    CLIENT_OBSERVATION = "client_observation"


@dataclass(frozen=True, slots=True)
class TraceMetadata:
    trace_id: str
    source: TraceSource
    ruleset_id: str
    ruleset_revision: str
    scenario_id: str
    tick_duration_ms: int
    seed: int | None
    captured_at: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.trace_id, "trace_id"),
            (self.ruleset_id, "ruleset_id"),
            (self.ruleset_revision, "ruleset_revision"),
            (self.scenario_id, "scenario_id"),
            (self.captured_at, "captured_at"),
        ):
            _identifier(value, field_name)
        if not isinstance(self.source, TraceSource):
            raise ValueError("source must be a TraceSource")
        _non_negative_integer(self.tick_duration_ms, "tick_duration_ms")
        if self.tick_duration_ms == 0:
            raise ValueError("tick_duration_ms must be positive")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or null")


@dataclass(frozen=True, slots=True)
class CapturedEffect:
    effect_key: str
    source_entity_id: str
    magnitude: float
    expires_at_ms: int
    stacking_key: str | None
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.effect_key, "effect_key")
        _identifier(self.source_entity_id, "source_entity_id")
        if (
            isinstance(self.magnitude, bool)
            or not isinstance(self.magnitude, (int, float))
            or not isfinite(self.magnitude)
        ):
            raise ValueError("magnitude must be finite")
        _non_negative_integer(self.expires_at_ms, "expires_at_ms")
        if self.stacking_key is not None:
            _identifier(self.stacking_key, "stacking_key")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("effect tags must be unique")
        for tag in self.tags:
            _identifier(tag, "effect tag")


@dataclass(frozen=True, slots=True)
class CapturedEntity:
    entity_id: str
    life_id: str
    position: Vector2
    velocity: Vector2
    scalars: tuple[NamedScalar, ...]
    tags: tuple[str, ...]
    effects: tuple[CapturedEffect, ...]
    cooldowns: tuple[tuple[str, int], ...]
    busy_until_ms: int
    alive: bool

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "entity_id")
        _identifier(self.life_id, "life_id")
        if not isinstance(self.position, Vector2) or not isinstance(self.velocity, Vector2):
            raise ValueError("position and velocity must be Vector2 values")
        _unique_named_scalars(self.scalars)
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("entity tags must be unique")
        for tag in self.tags:
            _identifier(tag, "entity tag")
        if any(not isinstance(effect, CapturedEffect) for effect in self.effects):
            raise ValueError("effects must contain CapturedEffect values")
        effect_keys = tuple(effect.stacking_key or effect.effect_key for effect in self.effects)
        if len(effect_keys) != len(set(effect_keys)):
            raise ValueError("effect storage keys must be unique")
        cooldown_keys = tuple(action_key for action_key, _ in self.cooldowns)
        if len(cooldown_keys) != len(set(cooldown_keys)):
            raise ValueError("cooldown action keys must be unique")
        for action_key, ready_at_ms in self.cooldowns:
            _identifier(action_key, "cooldown action key")
            _non_negative_integer(ready_at_ms, "cooldown ready_at_ms")
        _non_negative_integer(self.busy_until_ms, "busy_until_ms")
        if not isinstance(self.alive, bool):
            raise ValueError("alive must be a boolean")


@dataclass(frozen=True, slots=True)
class CapturedState:
    tick: int
    sim_time_ms: int
    entities: tuple[CapturedEntity, ...]

    def __post_init__(self) -> None:
        _non_negative_integer(self.tick, "tick")
        _non_negative_integer(self.sim_time_ms, "sim_time_ms")
        if any(not isinstance(entity, CapturedEntity) for entity in self.entities):
            raise ValueError("entities must contain CapturedEntity values")
        entity_ids = tuple(entity.entity_id for entity in self.entities)
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("captured entity ids must be unique")


@dataclass(frozen=True, slots=True)
class TraceStep:
    step_index: int
    before: CapturedState
    affordances: tuple[AffordanceSetMessage, ...]
    decisions: tuple[DecisionMessage, ...]
    events: EventBatchMessage
    after: CapturedState

    def __post_init__(self) -> None:
        _non_negative_integer(self.step_index, "step_index")
        if not isinstance(self.before, CapturedState) or not isinstance(self.after, CapturedState):
            raise ValueError("before and after must be CapturedState values")
        if self.after.tick < self.before.tick or self.after.sim_time_ms < self.before.sim_time_ms:
            raise ValueError("trace step time must not run backwards")
        if any(not isinstance(item, AffordanceSetMessage) for item in self.affordances):
            raise ValueError("affordances must contain AffordanceSetMessage values")
        agent_ids = tuple(item.agent_id for item in self.affordances)
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("trace step affordance agents must be unique")
        if any(not isinstance(item, DecisionMessage) for item in self.decisions):
            raise ValueError("decisions must contain DecisionMessage values")
        if not isinstance(self.events, EventBatchMessage):
            raise ValueError("events must be an EventBatchMessage")


@dataclass(frozen=True, slots=True)
class TransitionTrace:
    metadata: TraceMetadata
    steps: tuple[TraceStep, ...]
    schema_version: int = TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TRACE_SCHEMA_VERSION:
            raise ValueError("unsupported trace schema version")
        if not isinstance(self.metadata, TraceMetadata):
            raise ValueError("metadata must be TraceMetadata")
        if any(not isinstance(step, TraceStep) for step in self.steps):
            raise ValueError("steps must contain TraceStep values")
        expected = tuple(range(len(self.steps)))
        actual = tuple(step.step_index for step in self.steps)
        if actual != expected:
            raise ValueError("trace step indices must be contiguous from zero")
