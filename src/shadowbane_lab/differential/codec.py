"""Canonical JSON codec for versioned differential traces."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, cast

from shadowbane_lab.differential.model import (
    TRACE_SCHEMA_VERSION,
    CapturedEffect,
    CapturedEntity,
    CapturedState,
    TraceMetadata,
    TraceSource,
    TraceStep,
    TransitionTrace,
)
from shadowbane_lab.protocol import (
    AffordanceSetMessage,
    DecisionMessage,
    EventBatchMessage,
    NamedScalar,
    ProtocolMessage,
    Vector2,
    decode_message,
    encode_message,
)


class TraceDecodeError(ValueError):
    """Raised when a captured trace is malformed or unsupported."""


def encode_trace(trace: TransitionTrace) -> str:
    data = {
        "schema_version": trace.schema_version,
        "metadata": _metadata_to_data(trace.metadata),
        "steps": [_step_to_data(step) for step in trace.steps],
    }
    return json.dumps(data, allow_nan=False, separators=(",", ":"), sort_keys=True)


def decode_trace(payload: str | bytes | bytearray) -> TransitionTrace:
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TraceDecodeError("trace is not valid JSON") from exc
    try:
        data = _mapping(raw, "trace")
        if _integer(data, "schema_version") != TRACE_SCHEMA_VERSION:
            raise TraceDecodeError("unsupported trace schema version")
        return TransitionTrace(
            metadata=_metadata_from_data(_object(data, "metadata")),
            steps=tuple(_step_from_data(item) for item in _objects(data, "steps")),
        )
    except TraceDecodeError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, KeyError):
            raise TraceDecodeError(f"missing required field: {exc.args[0]}") from exc
        raise TraceDecodeError(str(exc)) from exc


def trace_semantic_view(trace: TransitionTrace) -> dict[str, Any]:
    """Return the producer-independent data used by differential comparison."""

    return {
        "ruleset_id": trace.metadata.ruleset_id,
        "ruleset_revision": trace.metadata.ruleset_revision,
        "scenario_id": trace.metadata.scenario_id,
        "tick_duration_ms": trace.metadata.tick_duration_ms,
        "seed": trace.metadata.seed,
        "steps": {str(step.step_index): _step_semantic_data(step) for step in trace.steps},
    }


def _metadata_to_data(metadata: TraceMetadata) -> dict[str, Any]:
    return {
        "trace_id": metadata.trace_id,
        "source": metadata.source.value,
        "ruleset_id": metadata.ruleset_id,
        "ruleset_revision": metadata.ruleset_revision,
        "scenario_id": metadata.scenario_id,
        "tick_duration_ms": metadata.tick_duration_ms,
        "seed": metadata.seed,
        "captured_at": metadata.captured_at,
    }


def _metadata_from_data(data: Mapping[str, Any]) -> TraceMetadata:
    return TraceMetadata(
        trace_id=_string(data, "trace_id"),
        source=TraceSource(_string(data, "source")),
        ruleset_id=_string(data, "ruleset_id"),
        ruleset_revision=_string(data, "ruleset_revision"),
        scenario_id=_string(data, "scenario_id"),
        tick_duration_ms=_integer(data, "tick_duration_ms"),
        seed=_nullable_integer(data, "seed"),
        captured_at=_string(data, "captured_at"),
    )


def _step_to_data(step: TraceStep) -> dict[str, Any]:
    return {
        "step_index": step.step_index,
        "before": _state_to_data(step.before),
        "affordances": [_protocol_to_data(item) for item in step.affordances],
        "decisions": [_protocol_to_data(item) for item in step.decisions],
        "events": _protocol_to_data(step.events),
        "after": _state_to_data(step.after),
    }


def _step_from_data(data: Mapping[str, Any]) -> TraceStep:
    return TraceStep(
        step_index=_integer(data, "step_index"),
        before=_state_from_data(_object(data, "before")),
        affordances=tuple(
            _protocol_from_data(item, AffordanceSetMessage)
            for item in _objects(data, "affordances")
        ),
        decisions=tuple(
            _protocol_from_data(item, DecisionMessage) for item in _objects(data, "decisions")
        ),
        events=_protocol_from_data(_object(data, "events"), EventBatchMessage),
        after=_state_from_data(_object(data, "after")),
    )


def _state_to_data(state: CapturedState) -> dict[str, Any]:
    return {
        "tick": state.tick,
        "sim_time_ms": state.sim_time_ms,
        "entities": [_entity_to_data(entity) for entity in state.entities],
    }


def _state_from_data(data: Mapping[str, Any]) -> CapturedState:
    return CapturedState(
        tick=_integer(data, "tick"),
        sim_time_ms=_integer(data, "sim_time_ms"),
        entities=tuple(_entity_from_data(item) for item in _objects(data, "entities")),
    )


def _entity_to_data(entity: CapturedEntity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "life_id": entity.life_id,
        "position": _vector_to_data(entity.position),
        "velocity": _vector_to_data(entity.velocity),
        "scalars": [_scalar_to_data(item) for item in entity.scalars],
        "tags": list(entity.tags),
        "effects": [_effect_to_data(item) for item in entity.effects],
        "cooldowns": [
            {"action_key": action_key, "ready_at_ms": ready_at_ms}
            for action_key, ready_at_ms in entity.cooldowns
        ],
        "busy_until_ms": entity.busy_until_ms,
        "alive": entity.alive,
    }


def _entity_from_data(data: Mapping[str, Any]) -> CapturedEntity:
    return CapturedEntity(
        entity_id=_string(data, "entity_id"),
        life_id=_string(data, "life_id"),
        position=_vector_from_data(_object(data, "position")),
        velocity=_vector_from_data(_object(data, "velocity")),
        scalars=tuple(_scalar_from_data(item) for item in _objects(data, "scalars")),
        tags=tuple(_strings(data, "tags")),
        effects=tuple(_effect_from_data(item) for item in _objects(data, "effects")),
        cooldowns=tuple(
            (_string(item, "action_key"), _integer(item, "ready_at_ms"))
            for item in _objects(data, "cooldowns")
        ),
        busy_until_ms=_integer(data, "busy_until_ms"),
        alive=_boolean(data, "alive"),
    )


def _effect_to_data(effect: CapturedEffect) -> dict[str, Any]:
    return {
        "effect_key": effect.effect_key,
        "source_entity_id": effect.source_entity_id,
        "magnitude": effect.magnitude,
        "expires_at_ms": effect.expires_at_ms,
        "stacking_key": effect.stacking_key,
        "tags": list(effect.tags),
    }


def _effect_from_data(data: Mapping[str, Any]) -> CapturedEffect:
    return CapturedEffect(
        effect_key=_string(data, "effect_key"),
        source_entity_id=_string(data, "source_entity_id"),
        magnitude=_number(data, "magnitude"),
        expires_at_ms=_integer(data, "expires_at_ms"),
        stacking_key=_nullable_string(data, "stacking_key"),
        tags=tuple(_strings(data, "tags")),
    )


def _step_semantic_data(step: TraceStep) -> dict[str, Any]:
    return {
        "before": _state_semantic_data(step.before),
        "affordances": {
            item.agent_id: _affordance_semantic_data(item) for item in step.affordances
        },
        "decisions": {
            f"{item.agent_id}:{item.correlation_id}": {
                "action_key": item.action_key,
                "binding": _binding_semantic_data(_protocol_to_data(item)["binding"]),
            }
            for item in step.decisions
        },
        "events": _event_batch_semantic_data(step.events),
        "after": _state_semantic_data(step.after),
    }


def _state_semantic_data(state: CapturedState) -> dict[str, Any]:
    return {
        "tick": state.tick,
        "sim_time_ms": state.sim_time_ms,
        "entities": {
            entity.entity_id: {
                "life_id": entity.life_id,
                "position": _vector_to_data(entity.position),
                "velocity": _vector_to_data(entity.velocity),
                "scalars": {item.name: item.value for item in entity.scalars},
                "tags": list(entity.tags),
                "effects": {
                    effect.stacking_key or effect.effect_key: {
                        **_effect_to_data(effect),
                        "tags": sorted(effect.tags),
                    }
                    for effect in entity.effects
                },
                "cooldowns": dict(entity.cooldowns),
                "busy_until_ms": entity.busy_until_ms,
                "alive": entity.alive,
            }
            for entity in state.entities
        },
    }


def _affordance_semantic_data(message: AffordanceSetMessage) -> dict[str, Any]:
    values: dict[str, Any] = {}
    encoded = _protocol_to_data(message)
    for item in message.affordances:
        affordance_data = next(
            data for data in encoded["affordances"] if data["affordance_id"] == item.affordance_id
        )
        binding = _binding_semantic_data(affordance_data["binding"])
        semantic_key = json.dumps(
            {"action_key": item.action_key, "binding": binding},
            separators=(",", ":"),
            sort_keys=True,
        )
        values[semantic_key] = {
            "action_key": item.action_key,
            "binding": binding,
            "features": {feature.name: feature.value for feature in item.features},
            "tags": sorted(item.tags),
        }
    return values


def _event_batch_semantic_data(message: EventBatchMessage) -> dict[str, Any]:
    encoded = _protocol_to_data(message)
    events = {
        f"{index}:{item['kind']}": {
            **{
                key: value
                for key, value in item.items()
                if key not in {"event_id", "kind", "scalars", "tags"}
            },
            "scalars": {scalar["name"]: scalar["value"] for scalar in item["scalars"]},
            "tags": sorted(item["tags"]),
        }
        for index, item in enumerate(encoded["events"])
    }
    return {
        "tick": message.tick,
        "sim_time_ms": message.sim_time_ms,
        "events": events,
        "life_terminated": sorted(message.life_terminated),
        "world_terminated": message.world_terminated,
        "truncated": message.truncated,
    }


def _binding_semantic_data(data: Mapping[str, Any]) -> dict[str, Any]:
    return dict(data)


def _protocol_to_data(message: ProtocolMessage) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(encode_message(message)))


ProtocolType = TypeVar("ProtocolType", AffordanceSetMessage, DecisionMessage, EventBatchMessage)


def _protocol_from_data(data: Mapping[str, Any], expected: type[ProtocolType]) -> ProtocolType:
    message = decode_message(json.dumps(data, allow_nan=False))
    if not isinstance(message, expected):
        raise TraceDecodeError(f"expected {expected.__name__} protocol message")
    return message


def _vector_to_data(value: Vector2) -> dict[str, float]:
    return {"x": value.x, "y": value.y}


def _vector_from_data(data: Mapping[str, Any]) -> Vector2:
    return Vector2(_number(data, "x"), _number(data, "y"))


def _scalar_to_data(value: NamedScalar) -> dict[str, Any]:
    return {"name": value.name, "value": value.value}


def _scalar_from_data(data: Mapping[str, Any]) -> NamedScalar:
    return NamedScalar(_string(data, "name"), _number(data, "value"))


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TraceDecodeError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _mapping(data[key], key)


def _sequence(data: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = data[key]
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TraceDecodeError(f"{key} must be an array")
    return value


def _objects(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(value, f"{key} item") for value in _sequence(data, key))


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise TraceDecodeError(f"{key} must be a non-empty string")
    return value


def _nullable_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data[key]
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise TraceDecodeError(f"{key} must be a non-empty string or null")
    return cast(str | None, value)


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceDecodeError(f"{key} must be an integer")
    return value


def _nullable_integer(data: Mapping[str, Any], key: str) -> int | None:
    value = data[key]
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise TraceDecodeError(f"{key} must be an integer or null")
    return cast(int | None, value)


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceDecodeError(f"{key} must be a number")
    return float(value)


def _boolean(data: Mapping[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TraceDecodeError(f"{key} must be a boolean")
    return value


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = _sequence(data, key)
    if any(not isinstance(value, str) for value in values):
        raise TraceDecodeError(f"{key} must contain strings")
    return tuple(cast(str, value) for value in values)
