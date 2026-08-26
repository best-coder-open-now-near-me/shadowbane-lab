"""Versioned semantic messages shared by policies and execution adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

PROTOCOL_VERSION = 1


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_non_negative(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")


def _require_unique(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for value in values:
        _require_identifier(value, field_name)


class EntityKind(StrEnum):
    ACTOR = "actor"
    PET = "pet"
    SUMMON = "summon"
    STRUCTURE = "structure"
    OBJECTIVE = "objective"
    ITEM = "item"
    PROJECTILE = "projectile"


class Relation(StrEnum):
    SELF = "self"
    ALLY = "ally"
    ENEMY = "enemy"
    NEUTRAL = "neutral"


class TargetKind(StrEnum):
    NONE = "none"
    SELF = "self"
    ENTITY = "entity"
    POSITION = "position"
    DIRECTION = "direction"


class EventKind(StrEnum):
    ACTION_STARTED = "action_started"
    ACTION_REJECTED = "action_rejected"
    ACTION_COMPLETED = "action_completed"
    TARGET_CHANGED = "target_changed"
    MOVEMENT_CHANGED = "movement_changed"
    DAMAGE_APPLIED = "damage_applied"
    CHANCE_RESOLVED = "chance_resolved"
    RESOURCE_RESTORED = "resource_restored"
    EFFECT_ADDED = "effect_added"
    EFFECT_REMOVED = "effect_removed"
    ENTITY_SPAWNED = "entity_spawned"
    ENTITY_DIED = "entity_died"
    OBJECTIVE_CHANGED = "objective_changed"


@dataclass(frozen=True, slots=True)
class Vector2:
    x: float
    y: float

    def __post_init__(self) -> None:
        _require_finite(self.x, "x")
        _require_finite(self.y, "y")


@dataclass(frozen=True, slots=True)
class NamedScalar:
    name: str
    value: float

    def __post_init__(self) -> None:
        _require_identifier(self.name, "name")
        _require_finite(self.value, "value")


@dataclass(frozen=True, slots=True)
class ActionBinding:
    """Parameters bound to one semantic action candidate."""

    actor_id: str
    target_kind: TargetKind = TargetKind.NONE
    target_entity_id: str | None = None
    position: Vector2 | None = None
    direction: Vector2 | None = None
    quantity: float | None = None
    item_id: str | None = None
    objective_id: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.actor_id, "actor_id")
        if not isinstance(self.target_kind, TargetKind):
            raise ValueError("target_kind must be a TargetKind")

        if self.target_kind is TargetKind.ENTITY:
            if self.target_entity_id is None:
                raise ValueError("entity targets require target_entity_id")
            _require_identifier(self.target_entity_id, "target_entity_id")
        elif self.target_entity_id is not None:
            raise ValueError("target_entity_id is valid only for entity targets")

        if self.target_kind is TargetKind.POSITION:
            if self.position is None:
                raise ValueError("position targets require position")
        elif self.position is not None:
            raise ValueError("position is valid only for position targets")

        if self.target_kind is TargetKind.DIRECTION:
            if self.direction is None:
                raise ValueError("direction targets require direction")
        elif self.direction is not None:
            raise ValueError("direction is valid only for direction targets")

        if self.quantity is not None:
            _require_finite(self.quantity, "quantity")
            if self.quantity <= 0:
                raise ValueError("quantity must be positive")
        if self.item_id is not None:
            _require_identifier(self.item_id, "item_id")
        if self.objective_id is not None:
            _require_identifier(self.objective_id, "objective_id")


@dataclass(frozen=True, slots=True)
class EntityObservation:
    entity_id: str
    kind: EntityKind
    relation: Relation
    position: Vector2
    velocity: Vector2 = Vector2(0.0, 0.0)
    scalars: tuple[NamedScalar, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.entity_id, "entity_id")
        if not isinstance(self.kind, EntityKind):
            raise ValueError("kind must be an EntityKind")
        if not isinstance(self.relation, Relation):
            raise ValueError("relation must be a Relation")
        _require_unique(self.tags, "tags")
        scalar_names = tuple(scalar.name for scalar in self.scalars)
        _require_unique(scalar_names, "scalar names")


@dataclass(frozen=True, slots=True)
class ObservationMessage:
    message_id: str
    observation_id: str
    agent_id: str
    life_id: str
    tick: int
    sim_time_ms: int
    entities: tuple[EntityObservation, ...]
    global_scalars: tuple[NamedScalar, ...] = ()
    active: bool = True
    protocol_version: int = field(default=PROTOCOL_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.message_id, "message_id")
        _require_identifier(self.observation_id, "observation_id")
        _require_identifier(self.agent_id, "agent_id")
        _require_identifier(self.life_id, "life_id")
        _require_non_negative(self.tick, "tick")
        _require_non_negative(self.sim_time_ms, "sim_time_ms")
        if not isinstance(self.active, bool):
            raise ValueError("active must be a boolean")
        entity_ids = tuple(entity.entity_id for entity in self.entities)
        _require_unique(entity_ids, "entity ids")
        if self.agent_id not in entity_ids:
            raise ValueError("entities must include the observing agent")
        observing_entity = next(
            entity for entity in self.entities if entity.entity_id == self.agent_id
        )
        if observing_entity.relation is not Relation.SELF:
            raise ValueError("the observing agent must have the self relation")
        self_entities = tuple(
            entity for entity in self.entities if entity.relation is Relation.SELF
        )
        if len(self_entities) != 1:
            raise ValueError("an observation must contain exactly one self entity")
        scalar_names = tuple(scalar.name for scalar in self.global_scalars)
        _require_unique(scalar_names, "global scalar names")


@dataclass(frozen=True, slots=True)
class Affordance:
    affordance_id: str
    action_key: str
    binding: ActionBinding
    features: tuple[NamedScalar, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.affordance_id, "affordance_id")
        _require_identifier(self.action_key, "action_key")
        _require_unique(self.tags, "tags")
        feature_names = tuple(feature.name for feature in self.features)
        _require_unique(feature_names, "feature names")


@dataclass(frozen=True, slots=True)
class AffordanceSetMessage:
    message_id: str
    observation_id: str
    agent_id: str
    tick: int
    affordances: tuple[Affordance, ...]
    protocol_version: int = field(default=PROTOCOL_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.message_id, "message_id")
        _require_identifier(self.observation_id, "observation_id")
        _require_identifier(self.agent_id, "agent_id")
        _require_non_negative(self.tick, "tick")
        affordance_ids = tuple(item.affordance_id for item in self.affordances)
        _require_unique(affordance_ids, "affordance ids")
        for affordance in self.affordances:
            if affordance.binding.actor_id != self.agent_id:
                raise ValueError("every affordance must be bound to the message agent")


@dataclass(frozen=True, slots=True)
class DecisionMessage:
    message_id: str
    correlation_id: str
    observation_id: str
    agent_id: str
    tick: int
    affordance_id: str
    action_key: str
    binding: ActionBinding
    protocol_version: int = field(default=PROTOCOL_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.message_id, "message_id")
        _require_identifier(self.correlation_id, "correlation_id")
        _require_identifier(self.observation_id, "observation_id")
        _require_identifier(self.agent_id, "agent_id")
        _require_identifier(self.affordance_id, "affordance_id")
        _require_identifier(self.action_key, "action_key")
        _require_non_negative(self.tick, "tick")
        if self.binding.actor_id != self.agent_id:
            raise ValueError("decision binding must be bound to the message agent")


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    kind: str
    tick: int
    sim_time_ms: int
    correlation_id: str | None = None
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    action_key: str | None = None
    scalars: tuple[NamedScalar, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "event_id")
        _require_identifier(self.kind, "kind")
        _require_non_negative(self.tick, "tick")
        _require_non_negative(self.sim_time_ms, "sim_time_ms")
        for field_name in (
            "correlation_id",
            "source_entity_id",
            "target_entity_id",
            "action_key",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)
        _require_unique(self.tags, "tags")
        scalar_names = tuple(scalar.name for scalar in self.scalars)
        _require_unique(scalar_names, "scalar names")


@dataclass(frozen=True, slots=True)
class EventBatchMessage:
    message_id: str
    tick: int
    sim_time_ms: int
    events: tuple[Event, ...]
    life_terminated: tuple[str, ...] = ()
    world_terminated: bool = False
    truncated: bool = False
    protocol_version: int = field(default=PROTOCOL_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.message_id, "message_id")
        _require_non_negative(self.tick, "tick")
        _require_non_negative(self.sim_time_ms, "sim_time_ms")
        _require_unique(self.life_terminated, "life_terminated")
        if not isinstance(self.world_terminated, bool):
            raise ValueError("world_terminated must be a boolean")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be a boolean")
        event_ids = tuple(event.event_id for event in self.events)
        _require_unique(event_ids, "event ids")


ProtocolMessage = ObservationMessage | AffordanceSetMessage | DecisionMessage | EventBatchMessage
