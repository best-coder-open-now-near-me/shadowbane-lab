"""Canonical JSON codec for protocol version 1."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from shadowbane_lab.protocol.model import (
    PROTOCOL_VERSION,
    ActionBinding,
    Affordance,
    AffordanceSetMessage,
    DecisionMessage,
    EntityKind,
    EntityObservation,
    Event,
    EventBatchMessage,
    NamedScalar,
    ObservationMessage,
    ProtocolMessage,
    Relation,
    TargetKind,
    Vector2,
)


class ProtocolDecodeError(ValueError):
    """Raised when wire data is malformed or unsupported."""


def encode_message(message: ProtocolMessage) -> str:
    """Encode a message as deterministic compact JSON."""

    payload = _message_to_dict(message)
    return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)


def decode_message(payload: str | bytes | bytearray) -> ProtocolMessage:
    """Decode and validate one version-1 protocol message."""

    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolDecodeError("payload is not valid JSON") from exc
    if not isinstance(raw, Mapping):
        raise ProtocolDecodeError("message must be a JSON object")
    data = cast(Mapping[str, Any], raw)
    try:
        if _integer(data, "protocol_version") != PROTOCOL_VERSION:
            raise ProtocolDecodeError("unsupported protocol version")
        message_type = _string(data, "message_type")
        if message_type == "observation":
            return _observation_from_dict(data)
        if message_type == "affordance_set":
            return _affordance_set_from_dict(data)
        if message_type == "decision":
            return _decision_from_dict(data)
        if message_type == "event_batch":
            return _event_batch_from_dict(data)
        raise ProtocolDecodeError(f"unsupported message_type: {message_type}")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ProtocolDecodeError):
            raise
        if isinstance(exc, KeyError):
            raise ProtocolDecodeError(f"missing required field: {exc.args[0]}") from exc
        raise ProtocolDecodeError(str(exc)) from exc


def _message_to_dict(message: ProtocolMessage) -> dict[str, Any]:
    if isinstance(message, ObservationMessage):
        return {
            "protocol_version": message.protocol_version,
            "message_type": "observation",
            "message_id": message.message_id,
            "observation_id": message.observation_id,
            "agent_id": message.agent_id,
            "life_id": message.life_id,
            "tick": message.tick,
            "sim_time_ms": message.sim_time_ms,
            "entities": [_entity_to_dict(item) for item in message.entities],
            "global_scalars": [_scalar_to_dict(item) for item in message.global_scalars],
            "active": message.active,
        }
    if isinstance(message, AffordanceSetMessage):
        return {
            "protocol_version": message.protocol_version,
            "message_type": "affordance_set",
            "message_id": message.message_id,
            "observation_id": message.observation_id,
            "agent_id": message.agent_id,
            "tick": message.tick,
            "affordances": [_affordance_to_dict(item) for item in message.affordances],
        }
    if isinstance(message, DecisionMessage):
        return {
            "protocol_version": message.protocol_version,
            "message_type": "decision",
            "message_id": message.message_id,
            "correlation_id": message.correlation_id,
            "observation_id": message.observation_id,
            "agent_id": message.agent_id,
            "tick": message.tick,
            "affordance_id": message.affordance_id,
            "action_key": message.action_key,
            "binding": _binding_to_dict(message.binding),
        }
    if isinstance(message, EventBatchMessage):
        return {
            "protocol_version": message.protocol_version,
            "message_type": "event_batch",
            "message_id": message.message_id,
            "tick": message.tick,
            "sim_time_ms": message.sim_time_ms,
            "events": [_event_to_dict(item) for item in message.events],
            "life_terminated": list(message.life_terminated),
            "world_terminated": message.world_terminated,
            "truncated": message.truncated,
        }
    raise TypeError(f"unsupported protocol message: {type(message).__name__}")


def _observation_from_dict(data: Mapping[str, Any]) -> ObservationMessage:
    return ObservationMessage(
        message_id=_string(data, "message_id"),
        observation_id=_string(data, "observation_id"),
        agent_id=_string(data, "agent_id"),
        life_id=_string(data, "life_id"),
        tick=_integer(data, "tick"),
        sim_time_ms=_integer(data, "sim_time_ms"),
        entities=tuple(_entity_from_dict(item) for item in _objects(data, "entities")),
        global_scalars=tuple(
            _scalar_from_dict(item) for item in _objects(data, "global_scalars")
        ),
        active=_boolean(data, "active"),
    )


def _affordance_set_from_dict(data: Mapping[str, Any]) -> AffordanceSetMessage:
    return AffordanceSetMessage(
        message_id=_string(data, "message_id"),
        observation_id=_string(data, "observation_id"),
        agent_id=_string(data, "agent_id"),
        tick=_integer(data, "tick"),
        affordances=tuple(
            _affordance_from_dict(item) for item in _objects(data, "affordances")
        ),
    )


def _decision_from_dict(data: Mapping[str, Any]) -> DecisionMessage:
    return DecisionMessage(
        message_id=_string(data, "message_id"),
        correlation_id=_string(data, "correlation_id"),
        observation_id=_string(data, "observation_id"),
        agent_id=_string(data, "agent_id"),
        tick=_integer(data, "tick"),
        affordance_id=_string(data, "affordance_id"),
        action_key=_string(data, "action_key"),
        binding=_binding_from_dict(_object(data, "binding")),
    )


def _event_batch_from_dict(data: Mapping[str, Any]) -> EventBatchMessage:
    return EventBatchMessage(
        message_id=_string(data, "message_id"),
        tick=_integer(data, "tick"),
        sim_time_ms=_integer(data, "sim_time_ms"),
        events=tuple(_event_from_dict(item) for item in _objects(data, "events")),
        life_terminated=tuple(_strings(data, "life_terminated")),
        world_terminated=_boolean(data, "world_terminated"),
        truncated=_boolean(data, "truncated"),
    )


def _vector_to_dict(value: Vector2) -> dict[str, float]:
    return {"x": value.x, "y": value.y}


def _vector_from_dict(data: Mapping[str, Any]) -> Vector2:
    return Vector2(x=_number(data, "x"), y=_number(data, "y"))


def _scalar_to_dict(value: NamedScalar) -> dict[str, Any]:
    return {"name": value.name, "value": value.value}


def _scalar_from_dict(data: Mapping[str, Any]) -> NamedScalar:
    return NamedScalar(name=_string(data, "name"), value=_number(data, "value"))


def _binding_to_dict(value: ActionBinding) -> dict[str, Any]:
    return {
        "actor_id": value.actor_id,
        "target_kind": value.target_kind.value,
        "target_entity_id": value.target_entity_id,
        "position": None if value.position is None else _vector_to_dict(value.position),
        "direction": None if value.direction is None else _vector_to_dict(value.direction),
        "quantity": value.quantity,
        "item_id": value.item_id,
        "objective_id": value.objective_id,
    }


def _binding_from_dict(data: Mapping[str, Any]) -> ActionBinding:
    position = _nullable_object(data, "position")
    direction = _nullable_object(data, "direction")
    return ActionBinding(
        actor_id=_string(data, "actor_id"),
        target_kind=TargetKind(_string(data, "target_kind")),
        target_entity_id=_nullable_string(data, "target_entity_id"),
        position=None if position is None else _vector_from_dict(position),
        direction=None if direction is None else _vector_from_dict(direction),
        quantity=_nullable_number(data, "quantity"),
        item_id=_nullable_string(data, "item_id"),
        objective_id=_nullable_string(data, "objective_id"),
    )


def _entity_to_dict(value: EntityObservation) -> dict[str, Any]:
    return {
        "entity_id": value.entity_id,
        "kind": value.kind.value,
        "relation": value.relation.value,
        "position": _vector_to_dict(value.position),
        "velocity": _vector_to_dict(value.velocity),
        "scalars": [_scalar_to_dict(item) for item in value.scalars],
        "tags": list(value.tags),
    }


def _entity_from_dict(data: Mapping[str, Any]) -> EntityObservation:
    return EntityObservation(
        entity_id=_string(data, "entity_id"),
        kind=EntityKind(_string(data, "kind")),
        relation=Relation(_string(data, "relation")),
        position=_vector_from_dict(_object(data, "position")),
        velocity=_vector_from_dict(_object(data, "velocity")),
        scalars=tuple(_scalar_from_dict(item) for item in _objects(data, "scalars")),
        tags=tuple(_strings(data, "tags")),
    )


def _affordance_to_dict(value: Affordance) -> dict[str, Any]:
    return {
        "affordance_id": value.affordance_id,
        "action_key": value.action_key,
        "binding": _binding_to_dict(value.binding),
        "features": [_scalar_to_dict(item) for item in value.features],
        "tags": list(value.tags),
    }


def _affordance_from_dict(data: Mapping[str, Any]) -> Affordance:
    return Affordance(
        affordance_id=_string(data, "affordance_id"),
        action_key=_string(data, "action_key"),
        binding=_binding_from_dict(_object(data, "binding")),
        features=tuple(_scalar_from_dict(item) for item in _objects(data, "features")),
        tags=tuple(_strings(data, "tags")),
    )


def _event_to_dict(value: Event) -> dict[str, Any]:
    return {
        "event_id": value.event_id,
        "kind": str(value.kind),
        "tick": value.tick,
        "sim_time_ms": value.sim_time_ms,
        "correlation_id": value.correlation_id,
        "source_entity_id": value.source_entity_id,
        "target_entity_id": value.target_entity_id,
        "action_key": value.action_key,
        "scalars": [_scalar_to_dict(item) for item in value.scalars],
        "tags": list(value.tags),
    }


def _event_from_dict(data: Mapping[str, Any]) -> Event:
    return Event(
        event_id=_string(data, "event_id"),
        kind=_string(data, "kind"),
        tick=_integer(data, "tick"),
        sim_time_ms=_integer(data, "sim_time_ms"),
        correlation_id=_nullable_string(data, "correlation_id"),
        source_entity_id=_nullable_string(data, "source_entity_id"),
        target_entity_id=_nullable_string(data, "target_entity_id"),
        action_key=_nullable_string(data, "action_key"),
        scalars=tuple(_scalar_from_dict(item) for item in _objects(data, "scalars")),
        tags=tuple(_strings(data, "tags")),
    )


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ProtocolDecodeError(f"{key} must be a string")
    return value


def _nullable_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data[key]
    if value is not None and not isinstance(value, str):
        raise ProtocolDecodeError(f"{key} must be a string or null")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolDecodeError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolDecodeError(f"{key} must be a number")
    return float(value)


def _nullable_number(data: Mapping[str, Any], key: str) -> float | None:
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolDecodeError(f"{key} must be a number or null")
    return float(value)


def _boolean(data: Mapping[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise ProtocolDecodeError(f"{key} must be a boolean")
    return value


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data[key]
    if not isinstance(value, Mapping):
        raise ProtocolDecodeError(f"{key} must be an object")
    return cast(Mapping[str, Any], value)


def _nullable_object(data: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = data[key]
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ProtocolDecodeError(f"{key} must be an object or null")
    return cast(Mapping[str, Any], value)


def _sequence(data: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = data[key]
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ProtocolDecodeError(f"{key} must be an array")
    return value


def _objects(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    for value in _sequence(data, key):
        if not isinstance(value, Mapping):
            raise ProtocolDecodeError(f"every {key} item must be an object")
        result.append(cast(Mapping[str, Any], value))
    return tuple(result)


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in _sequence(data, key):
        if not isinstance(value, str):
            raise ProtocolDecodeError(f"every {key} item must be a string")
        result.append(value)
    return tuple(result)
