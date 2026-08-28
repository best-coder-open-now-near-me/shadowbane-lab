"""Typed, bounded action algebra executed by the deterministic simulator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from shadowbane_lab.combat import DamageType, ResistanceType, StackPriority
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


class AttackKind(StrEnum):
    BASIC = "basic"
    POWER = "power"


class CombatStance(StrEnum):
    NORMAL = "normal"
    OFFENSIVE = "offensive"
    DEFENSIVE = "defensive"
    PRECISE = "precise"
    TRAVEL = "travel"


class AreaOrigin(StrEnum):
    ACTOR = "actor"
    TARGET = "target"


@dataclass(frozen=True, slots=True)
class UniformAmount:
    """Concrete continuous uniform amount resolved from the environment's seeded RNG."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        _finite(self.minimum, "minimum")
        _finite(self.maximum, "maximum")
        if self.minimum <= 0:
            raise ValueError("uniform amount minimum must be positive")
        if self.maximum <= self.minimum:
            raise ValueError("uniform amount maximum must be greater than minimum")

    @property
    def expected(self) -> float:
        return (self.minimum + self.maximum) / 2.0


@dataclass(frozen=True, slots=True)
class TriangularAmount:
    """Two-uniform centered amount used by Shadowbane weapon and health effects."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        _finite(self.minimum, "minimum")
        _finite(self.maximum, "maximum")
        if self.minimum <= 0:
            raise ValueError("triangular amount minimum must be positive")
        if self.maximum <= self.minimum:
            raise ValueError("triangular amount maximum must be greater than minimum")

    @property
    def expected(self) -> float:
        return (self.minimum + self.maximum) / 2.0


@dataclass(frozen=True, slots=True)
class UniformIntegerAmount:
    """Concrete inclusive integer amount resolved from the environment's seeded RNG."""

    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        for value, name in ((self.minimum, "minimum"), (self.maximum, "maximum")):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"uniform integer amount {name} must be an integer")
        if self.minimum <= 0:
            raise ValueError("uniform integer amount minimum must be positive")
        if self.maximum <= self.minimum:
            raise ValueError("uniform integer amount maximum must be greater than minimum")
        if self.maximum - self.minimum >= 1 << 32:
            raise ValueError("uniform integer amount span must fit the random source")

    @property
    def expected(self) -> float:
        return (self.minimum + self.maximum) / 2.0


@dataclass(frozen=True, slots=True)
class WeightedAmount:
    """Positive discrete outcomes with integer weights resolved by the seeded RNG."""

    outcomes: tuple[tuple[float, int], ...]

    def __post_init__(self) -> None:
        if not self.outcomes:
            raise ValueError("weighted amount requires at least one outcome")
        if tuple(sorted(self.outcomes)) != self.outcomes:
            raise ValueError("weighted amount outcomes must be sorted")
        values = tuple(item[0] for item in self.outcomes)
        if len(values) != len(set(values)):
            raise ValueError("weighted amount outcome values must be unique")
        for value, weight in self.outcomes:
            _finite(value, "weighted amount outcome")
            if value <= 0:
                raise ValueError("weighted amount outcomes must be positive")
            if isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0:
                raise ValueError("weighted amount weights must be positive integers")
        if self.total_weight > 1 << 32:
            raise ValueError("weighted amount total weight must fit the random source")

    @property
    def total_weight(self) -> int:
        return sum(weight for _, weight in self.outcomes)

    @property
    def expected(self) -> float:
        return (
            sum(value * weight for value, weight in self.outcomes)
            / self.total_weight
        )


AmountSpec = float | UniformAmount | TriangularAmount | UniformIntegerAmount | WeightedAmount


def _positive_amount(value: AmountSpec, field_name: str) -> None:
    if isinstance(value, (UniformAmount, TriangularAmount, UniformIntegerAmount, WeightedAmount)):
        return
    _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


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
    amount: AmountSpec
    damage_type: DamageType
    uses_resistance: bool = False
    power_trains: int = 0
    source_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _positive_amount(self.amount, "damage amount")
        if not isinstance(self.damage_type, DamageType):
            try:
                object.__setattr__(self, "damage_type", DamageType(self.damage_type))
            except (TypeError, ValueError) as exc:
                raise ValueError("damage_type must be a DamageType") from exc
        if not isinstance(self.uses_resistance, bool):
            raise ValueError("uses_resistance must be a boolean")
        if self.damage_type is DamageType.UNKNOWN and self.uses_resistance:
            raise ValueError("unknown damage cannot use resistance")
        _non_negative_integer(self.power_trains, "power_trains")
        if self.source_key is not None:
            _identifier(self.source_key, "source_key")


@dataclass(frozen=True, slots=True)
class RestoreResource:
    subject: SubjectRef
    resource_key: str
    amount: AmountSpec
    uses_resistance: bool = False
    power_trains: int = 0
    resistance_type: ResistanceType | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, SubjectRef):
            raise ValueError("subject must be a SubjectRef")
        _identifier(self.resource_key, "resource_key")
        _positive_amount(self.amount, "restoration amount")
        if not isinstance(self.uses_resistance, bool):
            raise ValueError("uses_resistance must be a boolean")
        _non_negative_integer(self.power_trains, "power_trains")
        if self.uses_resistance:
            if self.resistance_type is None:
                raise ValueError("resisted restoration requires resistance_type")
            if not isinstance(self.resistance_type, ResistanceType):
                try:
                    object.__setattr__(
                        self,
                        "resistance_type",
                        ResistanceType(self.resistance_type),
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "resistance_type must be a ResistanceType"
                    ) from exc
        elif self.resistance_type is not None:
            raise ValueError("resistance_type requires uses_resistance")


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


PeriodicDirectEffectPrimitive = ModifyScalar | DealDamage | RestoreResource | ModifyTag
_PERIODIC_DIRECT_EFFECT_TYPES = (ModifyScalar, DealDamage, RestoreResource, ModifyTag)


@dataclass(frozen=True, slots=True)
class PeriodicPulse:
    """Apply a bounded direct-effect bundle at fixed intervals while its effect is active."""

    periodic_key: str
    interval_ms: int
    tick_count: int
    effects: tuple[PeriodicDirectEffectPrimitive, ...]

    def __post_init__(self) -> None:
        _identifier(self.periodic_key, "periodic_key")
        _non_negative_integer(self.interval_ms, "interval_ms")
        if self.interval_ms == 0:
            raise ValueError("periodic interval must be positive")
        _non_negative_integer(self.tick_count, "tick_count")
        if self.tick_count == 0:
            raise ValueError("periodic tick count must be positive")
        if not self.effects:
            raise ValueError("periodic pulse requires at least one direct effect")
        if any(
            not isinstance(effect, _PERIODIC_DIRECT_EFFECT_TYPES)
            for effect in self.effects
        ):
            raise ValueError("periodic pulse effects must be nonrecursive direct effects")

    @property
    def duration_ms(self) -> int:
        return self.interval_ms * self.tick_count

    @property
    def semantic_tags(self) -> tuple[str, ...]:
        return (f"periodic.{self.periodic_key}",)


@dataclass(frozen=True, slots=True)
class ResourceImmunity:
    """Prevent restoration of one resource by effects at or below the carrier's trains."""

    resource_key: str

    def __post_init__(self) -> None:
        _identifier(self.resource_key, "resource_key")

    @property
    def semantic_tags(self) -> tuple[str, ...]:
        return (f"immunity.resource.{self.resource_key}",)


@dataclass(frozen=True, slots=True)
class ResistanceAdjustment:
    """Adjust one damage resistance channel while the carrying effect is active."""

    damage_type: DamageType
    amount: float

    def __post_init__(self) -> None:
        if not isinstance(self.damage_type, DamageType):
            try:
                object.__setattr__(self, "damage_type", DamageType(self.damage_type))
            except (TypeError, ValueError) as exc:
                raise ValueError("damage_type must be a DamageType") from exc
        if self.damage_type is DamageType.UNKNOWN:
            raise ValueError("resistance adjustments require a known damage type")
        _finite(self.amount, "resistance adjustment")
        if self.amount == 0:
            raise ValueError("resistance adjustment must not be zero")

    @property
    def semantic_tags(self) -> tuple[str, ...]:
        return (f"modifier.resistance.{self.damage_type.value}",)


@dataclass(frozen=True, slots=True)
class ScalarMultiplier:
    """Multiply one base scalar while the carrying effect is active."""

    scalar_key: str
    factor: float

    def __post_init__(self) -> None:
        _identifier(self.scalar_key, "scalar_key")
        _finite(self.factor, "scalar multiplier factor")
        if self.factor < 0:
            raise ValueError("scalar multiplier factor must not be negative")

    @property
    def semantic_tags(self) -> tuple[str, ...]:
        return (f"modifier.scalar_multiplier.{self.scalar_key}",)


@dataclass(frozen=True, slots=True)
class DamageBreakpoint:
    """Remove the carrying effect after cumulative matching damage exceeds a threshold."""

    breakpoint_key: str
    threshold: float
    damage_types: tuple[DamageType, ...]

    def __post_init__(self) -> None:
        _identifier(self.breakpoint_key, "breakpoint_key")
        _finite(self.threshold, "damage breakpoint threshold")
        if self.threshold <= 0:
            raise ValueError("damage breakpoint threshold must be positive")
        if not self.damage_types:
            raise ValueError("damage breakpoint requires at least one damage type")
        normalized: list[DamageType] = []
        for damage_type in self.damage_types:
            try:
                value = DamageType(damage_type)
            except (TypeError, ValueError) as exc:
                raise ValueError("damage_types must contain DamageType values") from exc
            if value is DamageType.UNKNOWN:
                raise ValueError("damage breakpoints require known damage types")
            normalized.append(value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("damage breakpoint types must not contain duplicates")
        object.__setattr__(self, "damage_types", tuple(normalized))

    @property
    def state_key(self) -> str:
        return f"damage_breakpoint.{self.breakpoint_key}"

    @property
    def semantic_tags(self) -> tuple[str, ...]:
        return (f"breakpoint.damage.{self.breakpoint_key}",)


EffectModifier = (
    ResourceImmunity
    | PeriodicPulse
    | ResistanceAdjustment
    | ScalarMultiplier
    | DamageBreakpoint
)
_EFFECT_MODIFIER_TYPES = (
    ResourceImmunity,
    PeriodicPulse,
    ResistanceAdjustment,
    ScalarMultiplier,
    DamageBreakpoint,
)


@dataclass(frozen=True, slots=True)
class ApplyEffect:
    subject: SubjectRef
    effect_key: str
    duration_ms: int
    magnitude: float = 1.0
    stacking_key: str | None = None
    tags: tuple[str, ...] = ()
    modifiers: tuple[EffectModifier, ...] = ()
    stack_order: int = 0
    trains: int = 0
    stack_priority: StackPriority = StackPriority.ALWAYS

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
        if any(
            not isinstance(modifier, _EFFECT_MODIFIER_TYPES)
            for modifier in self.modifiers
        ):
            raise ValueError("modifiers must contain typed effect modifiers")
        modifier_keys = tuple(
            tag for modifier in self.modifiers for tag in modifier.semantic_tags
        )
        _unique_strings(modifier_keys, "effect modifier keys")
        if any(
            isinstance(modifier, PeriodicPulse)
            and modifier.duration_ms > self.duration_ms
            for modifier in self.modifiers
        ):
            raise ValueError("periodic pulses must complete within the effect duration")
        _non_negative_integer(self.stack_order, "stack_order")
        _non_negative_integer(self.trains, "trains")
        if not isinstance(self.stack_priority, StackPriority):
            raise ValueError("stack_priority must be a StackPriority")


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


@dataclass(frozen=True, slots=True)
class ChangeStance:
    subject: SubjectRef
    stance: CombatStance

    def __post_init__(self) -> None:
        if self.subject is not SubjectRef.ACTOR:
            raise ValueError("stance changes must use the actor subject")
        if not isinstance(self.stance, CombatStance):
            raise ValueError("stance must be a CombatStance")


DirectEffectPrimitive = (
    ModifyScalar
    | DealDamage
    | RestoreResource
    | ModifyTag
    | ApplyEffect
    | RemoveEffect
    | MoveEntity
    | TransferItem
    | ModifyObjective
    | ChangeStance
)

_DIRECT_EFFECT_TYPES = (
    ModifyScalar,
    DealDamage,
    RestoreResource,
    ModifyTag,
    ApplyEffect,
    RemoveEffect,
    MoveEntity,
    TransferItem,
    ModifyObjective,
    ChangeStance,
)


@dataclass(frozen=True, slots=True)
class ChanceGate:
    """Resolve one seeded probability and apply a bounded direct-effect bundle on success."""

    chance_key: str
    probability: float
    effects: tuple[DirectEffectPrimitive, ...]

    def __post_init__(self) -> None:
        _identifier(self.chance_key, "chance_key")
        _finite(self.probability, "probability")
        if not 0.0 < self.probability <= 1.0:
            raise ValueError("probability must be in (0, 1]")
        if not self.effects:
            raise ValueError("chance gate requires at least one direct effect")
        if any(not isinstance(effect, _DIRECT_EFFECT_TYPES) for effect in self.effects):
            raise ValueError("chance gate effects must contain direct effect primitives")


@dataclass(frozen=True, slots=True)
class AttackGate:
    """Resolve source-derived hit and optional passive-defense rolls before effects."""

    attack_key: str
    kind: AttackKind
    attack_rating_key: str
    defense_rating_key: str
    effects: tuple[DirectEffectPrimitive | ChanceGate, ...]
    passive_defense_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.attack_key, "attack_key")
        if not isinstance(self.kind, AttackKind):
            raise ValueError("kind must be an AttackKind")
        _identifier(self.attack_rating_key, "attack_rating_key")
        _identifier(self.defense_rating_key, "defense_rating_key")
        if not self.effects:
            raise ValueError("attack gate requires at least one direct effect")
        if any(
            not isinstance(effect, (*_DIRECT_EFFECT_TYPES, ChanceGate))
            for effect in self.effects
        ):
            raise ValueError("attack gate effects must contain direct effects or chance gates")
        _unique_strings(self.passive_defense_keys, "passive_defense_keys")


@dataclass(frozen=True, slots=True)
class AreaEffect:
    """Apply one effect bundle to every eligible entity around an explicit origin."""

    origin: AreaOrigin
    radius: float
    allowed_relations: tuple[Relation, ...]
    effects: tuple[DirectEffectPrimitive | ChanceGate | AttackGate, ...]
    maximum_targets: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, AreaOrigin):
            raise ValueError("origin must be an AreaOrigin")
        _finite(self.radius, "radius")
        if self.radius <= 0:
            raise ValueError("area radius must be positive")
        if not self.allowed_relations:
            raise ValueError("area effects require at least one allowed relation")
        if len(self.allowed_relations) != len(set(self.allowed_relations)):
            raise ValueError("area allowed_relations must not contain duplicates")
        if any(not isinstance(item, Relation) for item in self.allowed_relations):
            raise ValueError("area allowed_relations must contain Relation values")
        if not self.effects:
            raise ValueError("area effects require at least one nested effect")
        if any(
            not isinstance(effect, (*_DIRECT_EFFECT_TYPES, ChanceGate, AttackGate))
            for effect in self.effects
        ):
            raise ValueError("area effects must contain direct effects or gates")
        if self.maximum_targets is not None and (
            isinstance(self.maximum_targets, bool)
            or not isinstance(self.maximum_targets, int)
            or self.maximum_targets < 1
        ):
            raise ValueError("maximum_targets must be a positive integer or null")


EffectPrimitive = DirectEffectPrimitive | ChanceGate | AttackGate | AreaEffect

_EFFECT_TYPES = (*_DIRECT_EFFECT_TYPES, ChanceGate, AttackGate, AreaEffect)


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
    hit_roll: AttackKind | None = None
    cancel_on_damage: bool = False
    cancel_on_stun: bool = False

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
        if self.hit_roll is not None and not isinstance(self.hit_roll, AttackKind):
            raise ValueError("hit_roll must be an AttackKind or null")
        if not isinstance(self.cancel_on_damage, bool):
            raise ValueError("cancel_on_damage must be a boolean")
        if not isinstance(self.cancel_on_stun, bool):
            raise ValueError("cancel_on_stun must be a boolean")
        if (self.cancel_on_damage or self.cancel_on_stun) and not any(
            phase.interruptible for phase in self.phases
        ):
            raise ValueError("cancellable actions require an interruptible phase")
        area_effects = tuple(
            effect
            for phase in self.phases
            for effect in phase.effects
            if isinstance(effect, AreaEffect)
        )
        if any(effect.origin is AreaOrigin.ACTOR for effect in area_effects):
            if self.targeting.kind is not TargetKind.SELF:
                raise ValueError("actor-centered area effects require self targeting")
        if any(effect.origin is AreaOrigin.TARGET for effect in area_effects):
            if self.targeting.kind not in {TargetKind.ENTITY, TargetKind.POSITION}:
                raise ValueError("target-area effects require entity or position targeting")
        hostile_target = (
            self.targeting.kind is TargetKind.ENTITY
            and Relation.ENEMY in self.targeting.allowed_relations
        ) or any(Relation.ENEMY in effect.allowed_relations for effect in area_effects)
        if self.hit_roll is not None and not hostile_target:
            raise ValueError("hit rolls require a hostile entity or area target")


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
