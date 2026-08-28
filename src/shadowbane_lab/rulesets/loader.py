"""Strict loader and compiler for version-1 JSON ruleset declarations."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.combat import StackPriority
from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind
from shadowbane_lab.rulesets.model import (
    CompilationStatus,
    CompiledActionRecord,
    CompiledRuleset,
    ConcreteMapping,
    FieldProvenance,
    PowerProgression,
    ProvenanceSource,
    SourceKind,
    TrainingRequirement,
)
from shadowbane_lab.sim import (
    ActionPhase,
    ActionSpec,
    ApplyEffect,
    AttackGate,
    AttackKind,
    DealDamage,
    DeliveryKind,
    DeliverySpec,
    ModifyObjective,
    ModifyScalar,
    ModifyTag,
    MoveEntity,
    MovementMode,
    PhaseKind,
    RemoveEffect,
    ResourceCost,
    RestoreResource,
    ScalarOperation,
    SubjectRef,
    TagOperation,
    TargetingSpec,
    TransferItem,
    TriangularAmount,
    UniformAmount,
    UniformIntegerAmount,
)
from shadowbane_lab.sim.actions import AmountSpec, ChanceGate, EffectPrimitive

RULESET_SOURCE_VERSION = 1


class RulesetLoadError(ValueError):
    """Raised when source data cannot be compiled without guessing."""


def load_shadowbane_vertical_slice(
    *, rank_overrides: Mapping[str, int] | None = None
) -> CompiledRuleset:
    resource = files("shadowbane_lab.rulesets").joinpath("data/shadowbane_vertical_slice_v1.json")
    return load_ruleset_text(
        resource.read_text(encoding="utf-8"), rank_overrides=rank_overrides
    )


def load_ruleset(
    path: str | Path, *, rank_overrides: Mapping[str, int] | None = None
) -> CompiledRuleset:
    return load_ruleset_text(
        Path(path).read_text(encoding="utf-8"), rank_overrides=rank_overrides
    )


def load_ruleset_text(
    text: str, *, rank_overrides: Mapping[str, int] | None = None
) -> CompiledRuleset:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RulesetLoadError("ruleset source is not valid JSON") from exc
    try:
        data = _mapping(raw, "ruleset")
        if _integer(data, "schema_version") != RULESET_SOURCE_VERSION:
            raise RulesetLoadError("unsupported ruleset source version")
        sources = tuple(_parse_source(item) for item in _objects(data, "sources"))
        overrides = dict(rank_overrides or {})
        for action_key, rank in overrides.items():
            if not isinstance(action_key, str) or not action_key.strip():
                raise RulesetLoadError("rank override keys must be non-empty strings")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
                raise RulesetLoadError("rank overrides must be non-negative integers")
        records = tuple(
            _parse_record(item, rank_override=overrides.get(_string(item, "action_key")))
            for item in _objects(data, "actions")
        )
        unknown_overrides = set(overrides) - {record.action_key for record in records}
        if unknown_overrides:
            raise RulesetLoadError(
                f"rank overrides contain unknown actions: {', '.join(sorted(unknown_overrides))}"
            )
        return CompiledRuleset(
            ruleset_id=_string(data, "ruleset_id"),
            sources=sources,
            records=records,
        )
    except RulesetLoadError:
        raise
    except ValueError as exc:
        raise RulesetLoadError(str(exc)) from exc


def _parse_source(data: Mapping[str, Any]) -> ProvenanceSource:
    return ProvenanceSource(
        source_id=_string(data, "source_id"),
        kind=SourceKind(_string(data, "kind")),
        uri=_string(data, "uri"),
        revision=_string(data, "revision"),
        retrieved_on=_string(data, "retrieved_on"),
    )


def _parse_record(
    data: Mapping[str, Any], *, rank_override: int | None = None
) -> CompiledActionRecord:
    rank = _integer(data, "rank") if rank_override is None else rank_override
    status = CompilationStatus(_string(data, "status"))
    progression = _parse_progression(data)
    spec_data = data.get("spec")
    if spec_data is not None and not isinstance(spec_data, Mapping):
        raise RulesetLoadError("spec must be an object or null")
    action = (
        None
        if spec_data is None
        else _parse_action(_mapping(spec_data, "spec"), _string(data, "action_key"), rank)
    )
    mapping_data = _object(data, "concrete")
    mapping = ConcreteMapping(
        server_power_token=_nullable_integer(mapping_data, "server_power_token"),
        server_id_string=_nullable_string(mapping_data, "server_id_string"),
        client_binding_key=_nullable_string(mapping_data, "client_binding_key"),
    )
    provenance = tuple(
        FieldProvenance(
            fields=tuple(_strings(item, "fields")),
            source_id=_string(item, "source_id"),
            locator=_string(item, "locator"),
            note=_optional_string(item, "note"),
        )
        for item in _objects(data, "provenance")
    )
    try:
        return CompiledActionRecord(
            action_key=_string(data, "action_key"),
            display_name=_string(data, "display_name"),
            rank=rank,
            status=status,
            mapping=mapping,
            provenance=provenance,
            unresolved=tuple(_strings(data, "unresolved")),
            action=action,
            progression=progression,
        )
    except ValueError as exc:
        raise RulesetLoadError(str(exc)) from exc


def _parse_progression(data: Mapping[str, Any]) -> PowerProgression | None:
    raw = data.get("progression")
    if raw is None:
        return None
    progression = _mapping(raw, "progression")
    fixed_rank = _nullable_integer(progression, "fixed_rank")
    return PowerProgression(
        professions=tuple(_strings(progression, "professions")),
        granted_level=_integer(progression, "granted_level"),
        maximum_rank=_integer(progression, "maximum_rank"),
        fixed_rank=fixed_rank,
        skill_requirements=_parse_requirements(progression, "skill_requirements"),
        power_requirements=_parse_requirements(progression, "power_requirements"),
    )


def _parse_requirements(
    data: Mapping[str, Any], key: str
) -> tuple[TrainingRequirement, ...]:
    return tuple(
        TrainingRequirement(
            training_key=_string(item, "training_key"),
            minimum_rank=_integer(item, "minimum_rank"),
        )
        for item in _objects(data, key)
    )


def _parse_action(data: Mapping[str, Any], action_key: str, rank: int) -> ActionSpec:
    targeting_data = _object(data, "targeting")
    targeting = TargetingSpec(
        kind=TargetKind(_string(targeting_data, "kind")),
        allowed_relations=tuple(
            Relation(value) for value in _strings(targeting_data, "allowed_relations")
        ),
        minimum_range=_resolved_number(targeting_data.get("minimum_range", 0.0), rank),
        maximum_range=_resolved_nullable_number(targeting_data.get("maximum_range"), rank),
        requires_line_of_sight=_boolean(targeting_data, "requires_line_of_sight"),
    )
    costs = tuple(
        ResourceCost(
            resource_key=_string(item, "resource_key"),
            amount=_resolved_number(_required(item, "amount"), rank),
        )
        for item in _objects(data, "costs")
    )
    phases = tuple(_parse_phase(item, rank) for item in _objects(data, "phases"))
    features = tuple(
        NamedScalar(
            name=_string(item, "name"),
            value=_resolved_number(_required(item, "value"), rank),
        )
        for item in _objects(data, "features")
    )
    return ActionSpec(
        action_key=action_key,
        targeting=targeting,
        phases=phases,
        cooldown_ms=_resolved_integer(_required(data, "cooldown_ms"), rank),
        costs=costs,
        required_actor_tags=tuple(_strings(data, "required_actor_tags")),
        forbidden_actor_tags=tuple(_strings(data, "forbidden_actor_tags")),
        features=features,
        tags=tuple(_strings(data, "tags")),
        cancel_on_damage=_optional_boolean(data, "cancel_on_damage", False),
        cancel_on_stun=_optional_boolean(data, "cancel_on_stun", False),
    )


def _parse_phase(data: Mapping[str, Any], rank: int) -> ActionPhase:
    delivery_data = _object(data, "delivery")
    return ActionPhase(
        kind=PhaseKind(_string(data, "kind")),
        duration_ms=_resolved_integer(_required(data, "duration_ms"), rank),
        effects=tuple(_parse_effect(item, rank) for item in _objects(data, "effects")),
        delivery=DeliverySpec(
            kind=DeliveryKind(_string(delivery_data, "kind")),
            projectile_speed_units_per_second=_resolved_nullable_number(
                delivery_data.get("projectile_speed_units_per_second"), rank
            ),
        ),
        interruptible=_boolean(data, "interruptible"),
        movement_allowed=_boolean(data, "movement_allowed"),
    )


def _parse_effect(data: Mapping[str, Any], rank: int) -> EffectPrimitive:
    operation = _string(data, "op")
    if operation == "chance_gate":
        nested = tuple(_parse_effect(item, rank) for item in _objects(data, "effects"))
        if any(isinstance(effect, (ChanceGate, AttackGate)) for effect in nested):
            raise RulesetLoadError("gates cannot be nested")
        try:
            return ChanceGate(
                chance_key=_string(data, "chance_key"),
                probability=_resolved_number(_required(data, "probability"), rank),
                effects=nested,
            )
        except ValueError as exc:
            raise RulesetLoadError(str(exc)) from exc
    if operation == "attack_gate":
        nested = tuple(_parse_effect(item, rank) for item in _objects(data, "effects"))
        if any(isinstance(effect, (ChanceGate, AttackGate)) for effect in nested):
            raise RulesetLoadError("gates cannot be nested")
        try:
            return AttackGate(
                attack_key=_string(data, "attack_key"),
                kind=AttackKind(_string(data, "kind")),
                attack_rating_key=_string(data, "attack_rating_key"),
                defense_rating_key=_string(data, "defense_rating_key"),
                effects=nested,
                passive_defense_keys=tuple(_strings(data, "passive_defense_keys")),
            )
        except ValueError as exc:
            raise RulesetLoadError(str(exc)) from exc
    if operation == "deal_damage":
        return DealDamage(
            subject=SubjectRef(_string(data, "subject")),
            amount=_resolved_amount(_required(data, "amount"), rank),
            damage_type=_string(data, "damage_type"),
            uses_resistance=_optional_boolean(data, "uses_resistance", False),
            power_trains=_resolved_integer(data.get("power_trains", 0), rank),
        )
    if operation == "restore_resource":
        return RestoreResource(
            subject=SubjectRef(_string(data, "subject")),
            resource_key=_string(data, "resource_key"),
            amount=_resolved_amount(_required(data, "amount"), rank),
        )
    if operation == "modify_scalar":
        return ModifyScalar(
            subject=SubjectRef(_string(data, "subject")),
            scalar_key=_string(data, "scalar_key"),
            operation=ScalarOperation(_string(data, "operation")),
            amount=_resolved_number(_required(data, "amount"), rank),
        )
    if operation == "modify_tag":
        return ModifyTag(
            subject=SubjectRef(_string(data, "subject")),
            tag=_string(data, "tag"),
            operation=TagOperation(_string(data, "operation")),
        )
    if operation == "apply_effect":
        return ApplyEffect(
            subject=SubjectRef(_string(data, "subject")),
            effect_key=_string(data, "effect_key"),
            duration_ms=_resolved_integer(_required(data, "duration_ms"), rank),
            magnitude=_resolved_number(data.get("magnitude", 1.0), rank),
            stacking_key=_nullable_string(data, "stacking_key"),
            tags=tuple(_strings(data, "tags")),
            stack_order=_resolved_integer(data.get("stack_order", 0), rank),
            trains=_resolved_integer(data.get("trains", 0), rank),
            stack_priority=StackPriority(
                str(data.get("stack_priority", StackPriority.ALWAYS.value))
            ),
        )
    if operation == "remove_effect":
        return RemoveEffect(
            subject=SubjectRef(_string(data, "subject")),
            effect_key=_nullable_string(data, "effect_key"),
            matching_tag=_nullable_string(data, "matching_tag"),
        )
    if operation == "move_entity":
        return MoveEntity(
            subject=SubjectRef(_string(data, "subject")),
            mode=MovementMode(_string(data, "mode")),
            distance=_resolved_nullable_number(data.get("distance"), rank),
        )
    if operation == "transfer_item":
        return TransferItem(
            from_subject=SubjectRef(_string(data, "from_subject")),
            to_subject=SubjectRef(_string(data, "to_subject")),
            item_id=_nullable_string(data, "item_id"),
            quantity=_resolved_nullable_number(data.get("quantity"), rank),
        )
    if operation == "modify_objective":
        return ModifyObjective(
            subject=SubjectRef(_string(data, "subject")),
            progress_delta=_resolved_number(_required(data, "progress_delta"), rank),
        )
    raise RulesetLoadError(f"unsupported effect operation: {operation}")


def _resolved_amount(value: Any, rank: int) -> AmountSpec:
    if isinstance(value, Mapping) and "distribution" in value:
        distribution = cast(Mapping[str, Any], value)
        kind = _string(distribution, "distribution")
        try:
            if kind == "uniform":
                return UniformAmount(
                    minimum=_resolved_number(_required(distribution, "minimum"), rank),
                    maximum=_resolved_number(_required(distribution, "maximum"), rank),
                )
            if kind == "triangular":
                return TriangularAmount(
                    minimum=_resolved_number(_required(distribution, "minimum"), rank),
                    maximum=_resolved_number(_required(distribution, "maximum"), rank),
                )
            if kind == "uniform_integer":
                return UniformIntegerAmount(
                    minimum=_resolved_integer(_required(distribution, "minimum"), rank),
                    maximum=_resolved_integer(_required(distribution, "maximum"), rank),
                )
            raise RulesetLoadError("unsupported amount distribution")
        except ValueError as exc:
            raise RulesetLoadError(str(exc)) from exc
    return _resolved_number(value, rank)


def _resolved_number(value: Any, rank: int) -> float:
    if isinstance(value, bool):
        raise RulesetLoadError("numeric values cannot be booleans")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, Mapping):
        curve = cast(Mapping[str, Any], value)
        if _string(curve, "interpolation") != "linear":
            raise RulesetLoadError("only linear rank curves are supported")
        rank_min = _integer(curve, "rank_min")
        rank_max = _integer(curve, "rank_max")
        if not rank_min <= rank <= rank_max or rank_max <= rank_min:
            raise RulesetLoadError("selected rank is outside a valid rank curve")
        value_min = _number(curve, "value_min")
        value_max = _number(curve, "value_max")
        fraction = (rank - rank_min) / (rank_max - rank_min)
        result = value_min + (value_max - value_min) * fraction
    else:
        raise RulesetLoadError("value must be a number or rank curve")
    if not isfinite(result):
        raise RulesetLoadError("resolved values must be finite")
    return result


def _resolved_nullable_number(value: Any, rank: int) -> float | None:
    return None if value is None else _resolved_number(value, rank)


def _resolved_integer(value: Any, rank: int) -> int:
    result = _resolved_number(value, rank)
    rounded = round(result)
    if abs(result - rounded) > 1e-9:
        raise RulesetLoadError("resolved integer field is fractional")
    return rounded


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RulesetLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _required(data: Mapping[str, Any], key: str) -> Any:
    try:
        return data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    try:
        return _mapping(data[key], key)
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc


def _objects(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(item, f"{key} item") for item in _sequence(data, key))


def _sequence(data: Mapping[str, Any], key: str) -> Sequence[Any]:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RulesetLoadError(f"{key} must be an array")
    return value


def _string(data: Mapping[str, Any], key: str) -> str:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if not isinstance(value, str) or not value.strip():
        raise RulesetLoadError(f"{key} must be a non-empty string")
    return value


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = _sequence(data, key)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise RulesetLoadError(f"{key} must contain non-empty strings")
    return tuple(cast(str, value) for value in values)


def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
    return None if key not in data else _nullable_string(data, key)


def _nullable_string(data: Mapping[str, Any], key: str) -> str | None:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise RulesetLoadError(f"{key} must be a non-empty string or null")
    return cast(str | None, value)


def _integer(data: Mapping[str, Any], key: str) -> int:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise RulesetLoadError(f"{key} must be an integer")
    return value


def _nullable_integer(data: Mapping[str, Any], key: str) -> int | None:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise RulesetLoadError(f"{key} must be an integer or null")
    return cast(int | None, value)


def _number(data: Mapping[str, Any], key: str) -> float:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RulesetLoadError(f"{key} must be a number")
    return float(value)


def _boolean(data: Mapping[str, Any], key: str) -> bool:
    try:
        value = data[key]
    except KeyError as exc:
        raise RulesetLoadError(f"missing required field: {key}") from exc
    if not isinstance(value, bool):
        raise RulesetLoadError(f"{key} must be a boolean")
    return value


def _optional_boolean(data: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in data:
        return default
    return _boolean(data, key)
