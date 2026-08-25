"""Typed, bounded action algebra executed by the deterministic simulator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _unique_strings(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


class SubjectRef(StrEnum):
    ACTOR = "actor"
    TARGET = "target"
    OBJECTIVE = "objective"


class PhaseKind(StrEnum):
    WINDUP = "windup"
    ACTIVE = "active"
    RECOVERY = "recovery"


class DeliveryKind(StrEnum):
    IMMEDIATE = "immediate"
    PROJECTILE = "projectile"


class ScalarOperation(StrEnum):
    ADD = "add"
    SET = "set"


class MovementMode(StrEnum):
    WALK = "walk"
    TELEPORT = "teleport"
    PUSH = "push"
    PULL = "pull"


class TagOperation(StrEnum):
    ADD = "add"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class TargetingSpec:
    kind: TargetKind
    allowed_relations: tuple[Relation, ...] = ()
    minimum_range: float = 0.0
    maximum_range: float | None = None
    requires_line_of_sight: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TargetKind):
            raise ValueError("kind must be a TargetKind")
        if len(self.allowed_relations) != len(set(self.allowed_relations)):
            raise ValueError("allowed_relations must not contain duplicates")
        if any(not isinstance(relation, Relation) for relation in self.allowed_relations):
            raise ValueError("allowed_relations must contain Relation values")
        if self.kind is TargetKind.ENTITY and not self.allowed_relations:
            raise ValueError("entity targeting requires at least one allowed relation")
        if self.kind is not TargetKind.ENTITY and self.allowed_relations:
            raise ValueError("allowed_relations are valid only for entity targeting")
        _finite(self.minimum_range, "minimum_range")
        if self.minimum_range < 0:
            raise ValueError("minimum_range must not be negative")
        if self.maximum_range is not None:
            _finite(self.maximum_range, "maximum_range")
            if self.maximum_range < self.minimum_range:
                raise ValueError("maximum_range must be at least minimum_range")
        if not isinstance(self.requires_line_of_sight, bool):
            raise ValueError("requires_line_of_sight must be a boolean")


@dataclass(frozen=True, slots=True)
class ResourceCost:
    resource_key: str
    amount: float

    def __post_init__(self) -> None:
        _identifier(self.resource_key, "resource_key")
        _finite(self.amount, "amount")
        if self.amount <= 0:
            raise ValueError("resource cost amount must be positive")


@dataclass(frozen=True, slots=True)
class DeliverySpec:
    kind: DeliveryKind = DeliveryKind.IMMEDIATE
    projectile_speed_units_per_second: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DeliveryKind):
            raise ValueError("kind must be a DeliveryKind")
        if self.kind is DeliveryKind.PROJECTILE:
            if self.projectile_speed_units_per_second is None:
                raise ValueError("projectile delivery requires a speed")
            _finite(self.projectile_speed_units_per_second, "projectile speed")
            if self.projectile_speed_units_per_second <= 0:
                raise ValueError("projectile speed must be positive")
        elif self.projectile_speed_units_per_second is not None:
            raise ValueError("projectile speed is valid only for projectile delivery")


@dataclass(frozen=True, slots=True)
class ModifyScalar:
    subject: SubjectRef
    scalar_key: str
    operation: ScalarOperation
    amount: float

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _identifier(self.scalar_key, "scalar_key")
        if not isinstance(self.operation, ScalarOperation):
            raise ValueError("operation must be a ScalarOperation")
        _finite(self.amount, "amount")


@dataclass(frozen=True, slots=True)
class DealDamage:
    subject: SubjectRef
    amount: float
    damage_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _finite(self.amount, "amount")
        if self.amount <= 0:
            raise ValueError("damage amount must be positive")
        _identifier(self.damage_type, "damage_type")


@dataclass(frozen=True, slots=True)
class RestoreResource:
    subject: SubjectRef
    resource_key: str
    amount: float

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _identifier(self.resource_key, "resource_key")
        _finite(self.amount, "amount")
        if self.amount <= 0:
            raise ValueError("restoration amount must be positive")


@dataclass(frozen=True, slots=True)
class ModifyTag:
    subject: SubjectRef
    tag: str
    operation: TagOperation

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _identifier(self.tag, "tag")
        if not isinstance(self.operation, TagOperation):
            raise ValueError("operation must be a TagOperation")


@dataclass(frozen=True, slots=True)
class ApplyEffect:
    subject: SubjectRef
    effect_key: str
    duration_ms: int
    magnitude: float = 1.0
    stacking_key: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _identifier(self.effect_key, "effect_key")
        _non_negative_integer(self.duration_ms, "duration_ms")
        if self.duration_ms == 0:
            raise ValueError("effect duration must be positive")
        _finite(self.magnitude, "magnitude")
        if self.stacking_key is not None:
            _identifier(self.stacking_key, "stacking_key")
        _unique_strings(self.tags, "tags")


@dataclass(frozen=True, slots=True)
class RemoveEffect:
    subject: SubjectRef
    effect_key: str | None = None
    matching_tag: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        if (self.effect_key is None) == (self.matching_tag is None):
            raise ValueError("exactly one of effect_key or matching_tag is required")
        if self.effect_key is not None:
            _identifier(self.effect_key, "effect_key")
        if self.matching_tag is not None:
            _identifier(self.matching_tag, "matching_tag")


@dataclass(frozen=True, slots=True)
class MoveEntity:
    subject: SubjectRef
    mode: MovementMode
    distance: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        if not isinstance(self.mode, MovementMode):
            raise ValueError("mode must be a MovementMode")
        if self.distance is not None:
            _finite(self.distance, "distance")
            if self.distance <= 0:
                raise ValueError("distance must be positive")


@dataclass(frozen=True, slots=True)
class TransferItem:
    from_subject: SubjectRef
    to_subject: SubjectRef
    item_id: str | None = None
    quantity: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.from_subject, SubjectRef):
            raise ValueError("from_subject must be a SubjectRef")
        if not isinstance(self.to_subject, SubjectRef):
            raise ValueError("to_subject must be a SubjectRef")
        if self.from_subject is self.to_subject:
            raise ValueError("item transfer subjects must differ")
        if self.item_id is not None:
            _identifier(self.item_id, "item_id")
        if self.quantity is not None:
            _finite(self.quantity, "quantity")
            if self.quantity <= 0:
                raise ValueError("quantity must be positive")


@dataclass(frozen=True, slots=True)
class ModifyObjective:
    subject: SubjectRef
    progress_delta: float

    def __post_init__(self) -> None:
        if self.subject is not SubjectRef.OBJECTIVE:
            raise ValueError("objective progress must use the objective subject")
        _finite(self.progress_delta, "progress_delta")
        if self.progress_delta == 0:
            raise ValueError("progress_delta must not be zero")


EffectPrimitive = (
    ModifyScalar
    | DealDamage
    | RestoreResource
    | ModifyTag
    | ApplyEffect
    | RemoveEffect
    | MoveEntity
    | TransferItem
    | ModifyObjective
)

_EFFECT_TYPES = (
    ModifyScalar,
    DealDamage,
    RestoreResource,
    ModifyTag,
    ApplyEffect,
    RemoveEffect,
    MoveEntity,
    TransferItem,
    ModifyObjective,
)


@dataclass(frozen=True, slots=True)
class ActionPhase:
    kind: PhaseKind
    duration_ms: int
    effects: tuple[EffectPrimitive, ...] = ()
    delivery: DeliverySpec = DeliverySpec()
    interruptible: bool = False
    movement_allowed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PhaseKind):
            raise ValueError("kind must be a PhaseKind")
        _non_negative_integer(self.duration_ms, "duration_ms")
        if not isinstance(self.delivery, DeliverySpec):
            raise ValueError("delivery must be a DeliverySpec")
        if any(not isinstance(effect, _EFFECT_TYPES) for effect in self.effects):
            raise ValueError("effects must contain typed effect primitives")
        if not isinstance(self.interruptible, bool):
            raise ValueError("interruptible must be a boolean")
        if not isinstance(self.movement_allowed, bool):
            raise ValueError("movement_allowed must be a boolean")
        if self.kind is PhaseKind.RECOVERY and self.effects:
            raise ValueError("recovery phases cannot apply effects")
        if self.kind is PhaseKind.RECOVERY and self.delivery.kind is not DeliveryKind.IMMEDIATE:
            raise ValueError("recovery phases cannot have delayed delivery")


@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_key: str
    targeting: TargetingSpec
    phases: tuple[ActionPhase, ...]
    cooldown_ms: int = 0
    costs: tuple[ResourceCost, ...] = ()
    required_actor_tags: tuple[str, ...] = ()
    forbidden_actor_tags: tuple[str, ...] = ()
    features: tuple[NamedScalar, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.action_key, "action_key")
        if not isinstance(self.targeting, TargetingSpec):
            raise ValueError("targeting must be a TargetingSpec")
        if not self.phases:
            raise ValueError("an action requires at least one phase")
        if any(not isinstance(phase, ActionPhase) for phase in self.phases):
            raise ValueError("phases must contain ActionPhase values")
        _non_negative_integer(self.cooldown_ms, "cooldown_ms")
        if any(not isinstance(cost, ResourceCost) for cost in self.costs):
            raise ValueError("costs must contain ResourceCost values")
        cost_resources = tuple(cost.resource_key for cost in self.costs)
        _unique_strings(cost_resources, "cost resource keys")
        _unique_strings(self.required_actor_tags, "required_actor_tags")
        _unique_strings(self.forbidden_actor_tags, "forbidden_actor_tags")
        if set(self.required_actor_tags) & set(self.forbidden_actor_tags):
            raise ValueError("an actor tag cannot be both required and forbidden")
        if any(not isinstance(feature, NamedScalar) for feature in self.features):
            raise ValueError("features must contain NamedScalar values")
        feature_names = tuple(feature.name for feature in self.features)
        _unique_strings(feature_names, "feature names")
        _unique_strings(self.tags, "tags")


class ActionCatalog:
    """Immutable, deterministically ordered collection of compiled actions."""

    def __init__(self, actions: tuple[ActionSpec, ...]) -> None:
        if any(not isinstance(action, ActionSpec) for action in actions):
            raise ValueError("actions must contain ActionSpec values")
        keys = tuple(action.action_key for action in actions)
        _unique_strings(keys, "action keys")
        self._actions = tuple(sorted(actions, key=lambda action: action.action_key))
        self._by_key = {action.action_key: action for action in self._actions}

    @property
    def actions(self) -> tuple[ActionSpec, ...]:
        return self._actions

    def get(self, action_key: str) -> ActionSpec:
        try:
            return self._by_key[action_key]
        except KeyError as exc:
            raise KeyError(f"unknown action key: {action_key}") from exc

    def __len__(self) -> int:
        return len(self._actions)
