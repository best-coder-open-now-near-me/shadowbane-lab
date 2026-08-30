"""Mutable reference state and immutable snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from shadowbane_lab.combat import StackPriority
from shadowbane_lab.protocol import EntityKind, Vector2
from shadowbane_lab.sim.actions import (
    CombatStance,
    DamageBreakpoint,
    EffectModifier,
    PeriodicPulse,
    ResistanceAdjustment,
    ResourceImmunity,
    ScalarMultiplier,
)


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _finite_mapping(values: dict[str, float], field_name: str) -> dict[str, float]:
    copy = dict(values)
    for key, value in copy.items():
        _identifier(key, f"{field_name} key")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{field_name} values must be finite numbers")
    return copy


@dataclass(frozen=True, slots=True)
class ActiveEffectSnapshot:
    effect_key: str
    source_entity_id: str
    instance_id: str | None
    magnitude: float
    expires_at_ms: int
    stacking_key: str | None
    tags: tuple[str, ...]
    modifiers: tuple[EffectModifier, ...]
    modifier_values: tuple[tuple[str, float], ...]
    application_order: int
    stack_order: int
    trains: int
    stack_priority: StackPriority


@dataclass(slots=True)
class ActiveEffectState:
    effect_key: str
    source_entity_id: str
    magnitude: float
    expires_at_ms: int
    instance_id: str | None = None
    stacking_key: str | None = None
    tags: set[str] = field(default_factory=set)
    modifiers: tuple[EffectModifier, ...] = ()
    modifier_values: dict[str, float] = field(default_factory=dict)
    application_order: int = 0
    stack_order: int = 0
    trains: int = 0
    stack_priority: StackPriority = StackPriority.ALWAYS

    def __post_init__(self) -> None:
        _identifier(self.effect_key, "effect_key")
        _identifier(self.source_entity_id, "source_entity_id")
        if self.instance_id is not None:
            _identifier(self.instance_id, "instance_id")
        if (
            isinstance(self.magnitude, bool)
            or not isinstance(self.magnitude, (int, float))
            or not isfinite(self.magnitude)
        ):
            raise ValueError("magnitude must be finite")
        if (
            isinstance(self.expires_at_ms, bool)
            or not isinstance(self.expires_at_ms, int)
            or self.expires_at_ms < 0
        ):
            raise ValueError("expires_at_ms must be a non-negative integer")
        if self.stacking_key is not None:
            _identifier(self.stacking_key, "stacking_key")
        self.tags = set(self.tags)
        for tag in self.tags:
            _identifier(tag, "effect tag")
        if any(
            not isinstance(
                modifier,
                (
                    ResourceImmunity,
                    PeriodicPulse,
                    ResistanceAdjustment,
                    ScalarMultiplier,
                    DamageBreakpoint,
                ),
            )
            for modifier in self.modifiers
        ):
            raise ValueError("modifiers must contain typed effect modifiers")
        self.modifier_values = _finite_mapping(self.modifier_values, "modifier_values")
        expected_modifier_values = {
            modifier.state_key
            for modifier in self.modifiers
            if isinstance(modifier, DamageBreakpoint)
        }
        if set(self.modifier_values) != expected_modifier_values:
            raise ValueError("modifier_values must match stateful effect modifiers")
        if any(value < 0 for value in self.modifier_values.values()):
            raise ValueError("modifier_values must not be negative")
        for value, field_name in (
            (self.application_order, "application_order"),
            (self.stack_order, "stack_order"),
            (self.trains, "trains"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.stack_priority, StackPriority):
            raise ValueError("stack_priority must be a StackPriority")

    def snapshot(self) -> ActiveEffectSnapshot:
        return ActiveEffectSnapshot(
            effect_key=self.effect_key,
            source_entity_id=self.source_entity_id,
            instance_id=self.instance_id,
            magnitude=float(self.magnitude),
            expires_at_ms=self.expires_at_ms,
            stacking_key=self.stacking_key,
            tags=tuple(sorted(self.tags)),
            modifiers=self.modifiers,
            modifier_values=tuple(sorted(self.modifier_values.items())),
            application_order=self.application_order,
            stack_order=self.stack_order,
            trains=self.trains,
            stack_priority=self.stack_priority,
        )

    @classmethod
    def from_snapshot(cls, snapshot: ActiveEffectSnapshot) -> ActiveEffectState:
        return cls(
            effect_key=snapshot.effect_key,
            source_entity_id=snapshot.source_entity_id,
            instance_id=snapshot.instance_id,
            magnitude=snapshot.magnitude,
            expires_at_ms=snapshot.expires_at_ms,
            stacking_key=snapshot.stacking_key,
            tags=set(snapshot.tags),
            modifiers=snapshot.modifiers,
            modifier_values=dict(snapshot.modifier_values),
            application_order=snapshot.application_order,
            stack_order=snapshot.stack_order,
            trains=snapshot.trains,
            stack_priority=snapshot.stack_priority,
        )


@dataclass(frozen=True, slots=True)
class EntitySnapshot:
    entity_id: str
    life_id: str
    kind: EntityKind
    team_id: str | None
    position: Vector2
    velocity: Vector2
    scalars: tuple[tuple[str, float], ...]
    maximums: tuple[tuple[str, float], ...]
    tags: tuple[str, ...]
    action_keys: tuple[str, ...]
    inventory: tuple[tuple[str, float], ...]
    effects: tuple[ActiveEffectSnapshot, ...]
    cooldowns: tuple[tuple[str, int], ...]
    busy_until_ms: int
    stance_multipliers: tuple[tuple[CombatStance, tuple[tuple[str, float], ...]], ...]
    stance: CombatStance
    alive: bool


@dataclass(slots=True)
class EntityState:
    entity_id: str
    life_id: str
    kind: EntityKind
    team_id: str | None
    position: Vector2
    velocity: Vector2 = Vector2(0.0, 0.0)
    scalars: dict[str, float] = field(default_factory=dict)
    maximums: dict[str, float] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    action_keys: tuple[str, ...] = ()
    inventory: dict[str, float] = field(default_factory=dict)
    effects: dict[str, ActiveEffectState] = field(default_factory=dict)
    cooldowns: dict[str, int] = field(default_factory=dict)
    busy_until_ms: int = 0
    stance_multipliers: dict[CombatStance, dict[str, float]] = field(default_factory=dict)
    stance: CombatStance = CombatStance.NORMAL
    alive: bool = True

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "entity_id")
        _identifier(self.life_id, "life_id")
        if not isinstance(self.kind, EntityKind):
            raise ValueError("kind must be an EntityKind")
        if self.team_id is not None:
            _identifier(self.team_id, "team_id")
        if not isinstance(self.position, Vector2) or not isinstance(self.velocity, Vector2):
            raise ValueError("position and velocity must be Vector2 values")
        self.scalars = _finite_mapping(self.scalars, "scalars")
        self.maximums = _finite_mapping(self.maximums, "maximums")
        for key, maximum in self.maximums.items():
            if maximum < 0:
                raise ValueError("maximum values must not be negative")
            if key in self.scalars and self.scalars[key] > maximum:
                raise ValueError(f"scalar {key} exceeds its maximum")
        self.tags = set(self.tags)
        for tag in self.tags:
            _identifier(tag, "tag")
        if len(self.action_keys) != len(set(self.action_keys)):
            raise ValueError("action_keys must not contain duplicates")
        for action_key in self.action_keys:
            _identifier(action_key, "action_key")
        self.inventory = _finite_mapping(self.inventory, "inventory")
        if any(quantity < 0 for quantity in self.inventory.values()):
            raise ValueError("inventory quantities must not be negative")
        self.effects = dict(self.effects)
        for storage_key, effect in self.effects.items():
            _identifier(storage_key, "effect storage key")
            if not isinstance(effect, ActiveEffectState):
                raise ValueError("effects must contain ActiveEffectState values")
            expected_storage_key = effect.stacking_key or effect.effect_key
            if storage_key != expected_storage_key:
                raise ValueError("effect storage keys must match stacking_key or effect_key")
        self.cooldowns = dict(self.cooldowns)
        for action_key, ready_at_ms in self.cooldowns.items():
            _identifier(action_key, "cooldown action key")
            if isinstance(ready_at_ms, bool) or not isinstance(ready_at_ms, int) or ready_at_ms < 0:
                raise ValueError("cooldown timestamps must be non-negative integers")
        if (
            isinstance(self.busy_until_ms, bool)
            or not isinstance(self.busy_until_ms, int)
            or self.busy_until_ms < 0
        ):
            raise ValueError("busy_until_ms must be a non-negative integer")
        normalized_stance_multipliers: dict[CombatStance, dict[str, float]] = {}
        for stance, multipliers in self.stance_multipliers.items():
            if not isinstance(stance, CombatStance):
                try:
                    stance = CombatStance(stance)
                except (TypeError, ValueError) as exc:
                    raise ValueError("stance_multipliers keys must be CombatStance values") from exc
            if stance in {CombatStance.NORMAL, CombatStance.TRAVEL}:
                raise ValueError("stance_multipliers may only define trained combat stances")
            parsed = _finite_mapping(multipliers, "stance multiplier")
            if any(factor <= 0.0 for factor in parsed.values()):
                raise ValueError("stance multiplier factors must be positive")
            missing_scalars = set(parsed) - set(self.scalars)
            if missing_scalars:
                raise ValueError(
                    "stance multipliers reference missing scalars: "
                    + ", ".join(sorted(missing_scalars))
                )
            normalized_stance_multipliers[stance] = parsed
        self.stance_multipliers = normalized_stance_multipliers
        if not isinstance(self.stance, CombatStance):
            raise ValueError("stance must be a CombatStance")
        if not isinstance(self.alive, bool):
            raise ValueError("alive must be a boolean")

    @property
    def effective_tags(self) -> frozenset[str]:
        effect_tags = {
            tag for effect in self.effects.values() for tag in (effect.effect_key, *effect.tags)
        }
        modifier_tags = {
            tag
            for effect in self.effects.values()
            for modifier in effect.modifiers
            for tag in modifier.semantic_tags
        }
        return frozenset(
            self.tags | effect_tags | modifier_tags | {f"stance.{self.stance.value}"}
        )

    def effective_scalar(self, scalar_key: str) -> float:
        """Return a base scalar after all active typed multipliers."""

        _identifier(scalar_key, "scalar_key")
        if scalar_key not in self.scalars:
            raise KeyError(scalar_key)
        factor = self.stance_factor(scalar_key)
        for storage_key in sorted(self.effects):
            effect = self.effects[storage_key]
            for modifier in effect.modifiers:
                if (
                    isinstance(modifier, ScalarMultiplier)
                    and modifier.scalar_key == scalar_key
                ):
                    factor *= modifier.factor
        return float(self.scalars[scalar_key]) * factor

    def stance_factor(
        self,
        scalar_key: str,
        stance: CombatStance | None = None,
    ) -> float:
        """Return the selected stance's multiplier for one scalar channel."""

        _identifier(scalar_key, "scalar_key")
        selected = self.stance if stance is None else stance
        if not isinstance(selected, CombatStance):
            raise ValueError("stance must be a CombatStance")
        return float(self.stance_multipliers.get(selected, {}).get(scalar_key, 1.0))

    def snapshot(self) -> EntitySnapshot:
        return EntitySnapshot(
            entity_id=self.entity_id,
            life_id=self.life_id,
            kind=self.kind,
            team_id=self.team_id,
            position=self.position,
            velocity=self.velocity,
            scalars=tuple(sorted((key, float(value)) for key, value in self.scalars.items())),
            maximums=tuple(sorted((key, float(value)) for key, value in self.maximums.items())),
            tags=tuple(sorted(self.tags)),
            action_keys=tuple(sorted(self.action_keys)),
            inventory=tuple(sorted((key, float(value)) for key, value in self.inventory.items())),
            effects=tuple(self.effects[key].snapshot() for key in sorted(self.effects)),
            cooldowns=tuple(sorted(self.cooldowns.items())),
            busy_until_ms=self.busy_until_ms,
            stance_multipliers=tuple(
                (
                    stance,
                    tuple(sorted((key, float(value)) for key, value in multipliers.items())),
                )
                for stance, multipliers in sorted(
                    self.stance_multipliers.items(), key=lambda item: item[0].value
                )
            ),
            stance=self.stance,
            alive=self.alive,
        )

    @classmethod
    def from_snapshot(cls, snapshot: EntitySnapshot) -> EntityState:
        effects = {
            effect.stacking_key or effect.effect_key: ActiveEffectState.from_snapshot(effect)
            for effect in snapshot.effects
        }
        return cls(
            entity_id=snapshot.entity_id,
            life_id=snapshot.life_id,
            kind=snapshot.kind,
            team_id=snapshot.team_id,
            position=snapshot.position,
            velocity=snapshot.velocity,
            scalars=dict(snapshot.scalars),
            maximums=dict(snapshot.maximums),
            tags=set(snapshot.tags),
            action_keys=snapshot.action_keys,
            inventory=dict(snapshot.inventory),
            effects=effects,
            cooldowns=dict(snapshot.cooldowns),
            busy_until_ms=snapshot.busy_until_ms,
            stance_multipliers={
                stance: dict(multipliers)
                for stance, multipliers in snapshot.stance_multipliers
            },
            stance=snapshot.stance,
            alive=snapshot.alive,
        )

    def clone(self) -> EntityState:
        return EntityState.from_snapshot(self.snapshot())
