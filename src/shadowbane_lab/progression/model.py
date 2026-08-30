"""Typed progression and proc-estimation records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.combat import DamageType


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _integer(value: int, field_name: str, *, minimum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")


@dataclass(frozen=True, slots=True)
class StatLine:
    strength: int = 0
    dexterity: int = 0
    constitution: int = 0
    intelligence: int = 0
    spirit: int = 0

    def __post_init__(self) -> None:
        for name, value in zip(self.names(), self.values(), strict=True):
            _integer(value, name)

    @staticmethod
    def names() -> tuple[str, ...]:
        return ("strength", "dexterity", "constitution", "intelligence", "spirit")

    def values(self) -> tuple[int, ...]:
        return (
            self.strength,
            self.dexterity,
            self.constitution,
            self.intelligence,
            self.spirit,
        )

    @classmethod
    def from_values(cls, values: tuple[int, ...]) -> StatLine:
        if len(values) != 5:
            raise ValueError("stat lines require five values")
        return cls(*values)

    def plus(self, *others: StatLine) -> StatLine:
        values = self.values()
        for other in others:
            if not isinstance(other, StatLine):
                raise ValueError("stat additions require StatLine values")
            values = tuple(left + right for left, right in zip(values, other.values(), strict=True))
        return StatLine.from_values(values)

    @property
    def total(self) -> int:
        return sum(self.values())

    def as_dict(self) -> dict[str, int]:
        return dict(zip(self.names(), self.values(), strict=True))


class RuneKind(StrEnum):
    DISCIPLINE = "discipline"
    STAT = "stat"


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_id: str
    kind: str
    uri: str
    revision: str

    def __post_init__(self) -> None:
        for name in ("source_id", "kind", "uri", "revision"):
            _identifier(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class RuneProfile:
    key: str
    name: str
    kind: RuneKind
    cost: int
    minimum_level: int
    stat_grants: StatLine
    cap_grants: StatLine
    minimum_stats: StatLine
    source_id: str

    def __post_init__(self) -> None:
        for value, name in ((self.key, "key"), (self.name, "name"), (self.source_id, "source_id")):
            _identifier(value, name)
        if not isinstance(self.kind, RuneKind):
            raise ValueError("kind must be a RuneKind")
        _integer(self.cost, "cost", minimum=0)
        _integer(self.minimum_level, "minimum_level", minimum=1)
        for name in ("stat_grants", "cap_grants", "minimum_stats"):
            if not isinstance(getattr(self, name), StatLine):
                raise ValueError(f"{name} must be a StatLine")


@dataclass(frozen=True, slots=True)
class WeaponProfile:
    key: str
    name: str
    required_unarmed: int
    base_minimum_damage: float
    base_maximum_damage: float
    base_speed: float
    source_id: str

    def __post_init__(self) -> None:
        for value, name in ((self.key, "key"), (self.name, "name"), (self.source_id, "source_id")):
            _identifier(value, name)
        _integer(self.required_unarmed, "required_unarmed", minimum=0)
        for value, name in (
            (self.base_minimum_damage, "base_minimum_damage"),
            (self.base_maximum_damage, "base_maximum_damage"),
            (self.base_speed, "base_speed"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.base_maximum_damage < self.base_minimum_damage:
            raise ValueError("maximum weapon damage must not be below minimum damage")


@dataclass(frozen=True, slots=True)
class ProcEffectProfile:
    key: str
    name: str
    chance_per_successful_hit: float
    base_minimum_damage: float
    base_maximum_damage: float
    focus_scaling: bool
    damage_type: DamageType
    source_id: str

    def __post_init__(self) -> None:
        for value, name in ((self.key, "key"), (self.name, "name"), (self.source_id, "source_id")):
            _identifier(value, name)
        if not 0.0 <= self.chance_per_successful_hit <= 1.0:
            raise ValueError("proc chance must be between zero and one")
        if self.base_minimum_damage <= 0 or self.base_maximum_damage < self.base_minimum_damage:
            raise ValueError("proc base damage range is invalid")
        if not isinstance(self.focus_scaling, bool):
            raise ValueError("focus_scaling must be a boolean")
        if not isinstance(self.damage_type, DamageType):
            raise ValueError("damage_type must be a DamageType")
        if self.damage_type is DamageType.UNKNOWN:
            raise ValueError("proc effects require a known damage type")


@dataclass(frozen=True, slots=True)
class TrainingTarget:
    key: str
    target: int
    priority: int
    minimum_level: int

    def __post_init__(self) -> None:
        _identifier(self.key, "key")
        _integer(self.target, "target", minimum=0)
        _integer(self.priority, "priority", minimum=1)
        _integer(self.minimum_level, "minimum_level", minimum=1)


@dataclass(frozen=True, slots=True)
class IdentityProfile:
    race: str
    base_class: str
    profession: str
    race_start: StatLine
    race_caps: StatLine
    creation_pool: int
    race_resource_bonuses: tuple[int, int, int]
    base_modifiers: StatLine
    base_resource_factors: tuple[int, int, int]
    profession_resource_factors: tuple[int, int, int]
    boon: int

    def __post_init__(self) -> None:
        for name in ("race", "base_class", "profession"):
            _identifier(getattr(self, name), name)
        _integer(self.creation_pool, "creation_pool", minimum=0)
        _integer(self.boon, "boon")
        for name in (
            "race_resource_bonuses",
            "base_resource_factors",
            "profession_resource_factors",
        ):
            values = getattr(self, name)
            if len(values) != 3:
                raise ValueError(f"{name} requires health, mana, and stamina values")
            for value in values:
                _integer(value, name)


@dataclass(frozen=True, slots=True)
class ProgressionLimits:
    maximum_level: int
    maximum_runes: int
    disciplines_below_70: int
    disciplines_at_70: int

    def __post_init__(self) -> None:
        for name in (
            "maximum_level",
            "maximum_runes",
            "disciplines_below_70",
            "disciplines_at_70",
        ):
            _integer(getattr(self, name), name, minimum=1)


@dataclass(frozen=True, slots=True)
class ProgressionProfile:
    profile_id: str
    retrieved_on: str
    sources: tuple[SourceReference, ...]
    identity: IdentityProfile
    limits: ProgressionLimits
    runes: tuple[RuneProfile, ...]
    weapons: tuple[WeaponProfile, ...]
    proc_effects: tuple[ProcEffectProfile, ...]
    training_targets: tuple[TrainingTarget, ...]

    def __post_init__(self) -> None:
        _identifier(self.profile_id, "profile_id")
        _identifier(self.retrieved_on, "retrieved_on")
        source_ids = tuple(item.source_id for item in self.sources)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source ids must be unique")
        known_sources = set(source_ids)
        for records, name in (
            (self.runes, "runes"),
            (self.weapons, "weapons"),
            (self.proc_effects, "proc_effects"),
        ):
            keys = tuple(item.key for item in records)
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name} keys must be unique")
            for item in records:
                if item.source_id not in known_sources:
                    raise ValueError(f"{name} references unknown source {item.source_id}")

    def rune(self, key: str) -> RuneProfile:
        return _by_key(self.runes, key, "rune")

    def weapon(self, key: str) -> WeaponProfile:
        return _by_key(self.weapons, key, "weapon")

    def proc_effect(self, key: str) -> ProcEffectProfile:
        return _by_key(self.proc_effects, key, "proc effect")


def _by_key(records: tuple[object, ...], key: str, kind: str):
    try:
        return next(item for item in records if item.key == key)
    except StopIteration as exc:
        raise KeyError(f"unknown {kind}: {key}") from exc


@dataclass(frozen=True, slots=True)
class TrainingInvestment:
    key: str
    points: int

    def __post_init__(self) -> None:
        _identifier(self.key, "key")
        _integer(self.points, "points", minimum=0)


@dataclass(frozen=True, slots=True)
class CharacterProgression:
    level: int
    attribute_adjustments: StatLine = StatLine()
    rune_keys: tuple[str, ...] = ()
    training: tuple[TrainingInvestment, ...] = ()
    other_ability_points_spent: int = 0

    def __post_init__(self) -> None:
        _integer(self.level, "level", minimum=1)
        _integer(
            self.other_ability_points_spent,
            "other_ability_points_spent",
            minimum=0,
        )
        if len(self.rune_keys) != len(set(self.rune_keys)):
            raise ValueError("rune_keys must not contain duplicates")
        if len(tuple(item.key for item in self.training)) != len(
            set(item.key for item in self.training)
        ):
            raise ValueError("training keys must not contain duplicates")


@dataclass(frozen=True, slots=True)
class ProgressionEvaluation:
    profile_id: str
    level: int
    stats: StatLine
    caps: StatLine
    ability_points_total: int
    ability_points_spent: int
    ability_points_remaining: int
    training_points_total: int
    training_points_spent: int
    training_points_remaining: int
    health: int
    mana: int
    stamina: int
    baseline_defense: int
    active_runes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "level": self.level,
            "stats": self.stats.as_dict(),
            "caps": self.caps.as_dict(),
            "ability_points": {
                "total": self.ability_points_total,
                "spent": self.ability_points_spent,
                "remaining": self.ability_points_remaining,
            },
            "training_points": {
                "total": self.training_points_total,
                "spent": self.training_points_spent,
                "remaining": self.training_points_remaining,
            },
            "resources": {
                "health": self.health,
                "mana": self.mana,
                "stamina": self.stamina,
                "baseline_defense": self.baseline_defense,
            },
            "active_runes": list(self.active_runes),
        }


@dataclass(frozen=True, slots=True)
class ProcLoadout:
    weapon_key: str
    proc_effect_keys: tuple[str, ...]
    hands: int = 2
    successful_hit_rate: float = 1.0
    alacrity_percent: float = 0.0
    stance_speed_percent: float = 0.0
    buff_speed_percent: float = 0.0

    def __post_init__(self) -> None:
        _identifier(self.weapon_key, "weapon_key")
        if not self.proc_effect_keys:
            raise ValueError("at least one proc effect is required")
        _integer(self.hands, "hands", minimum=1)
        if self.hands > 2:
            raise ValueError("hands must not exceed two")
        if not 0.0 <= self.successful_hit_rate <= 1.0:
            raise ValueError("successful_hit_rate must be between zero and one")
        for value, name in (
            (self.alacrity_percent, "alacrity_percent"),
            (self.stance_speed_percent, "stance_speed_percent"),
            (self.buff_speed_percent, "buff_speed_percent"),
        ):
            if not 0.0 <= value < 100.0:
                raise ValueError(f"{name} must be in [0, 100)")


@dataclass(frozen=True, slots=True)
class ProcEstimate:
    intelligence: int
    spirit: int
    delay_seconds_per_hand: float
    successful_hits_per_second: float
    expected_triggers_per_second: float
    expected_proc_damage_per_trigger: float
    expected_proc_damage_per_second: float
    expected_proc_damage_per_minute: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "intelligence": self.intelligence,
            "spirit": self.spirit,
            "delay_seconds_per_hand": self.delay_seconds_per_hand,
            "successful_hits_per_second": self.successful_hits_per_second,
            "expected_triggers_per_second": self.expected_triggers_per_second,
            "expected_proc_damage_per_trigger": self.expected_proc_damage_per_trigger,
            "expected_proc_damage_per_second": self.expected_proc_damage_per_second,
            "expected_proc_damage_per_minute": self.expected_proc_damage_per_minute,
        }
