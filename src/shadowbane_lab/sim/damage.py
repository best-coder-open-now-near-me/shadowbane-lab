"""Typed values for the canonical post-roll damage transaction."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from shadowbane_lab.combat import DamageType


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    return float(value)


def _non_negative(value: float, field_name: str) -> float:
    result = _finite(value, field_name)
    if result < 0.0:
        raise ValueError(f"{field_name} must not be negative")
    return result


@dataclass(frozen=True, slots=True)
class DamageTransaction:
    """One normalized damage commitment after the attack and resistance stages.

    ``requested`` is damage after source-side output modifiers. ``post_resistance``
    is the amount entering shared absorbers and health application. Resistance is
    normalized to percentage points even when a compatibility adapter reads a
    fractional scalar. ``breakpoint_amount`` remains explicit because historical
    breakpoint evidence is post-resistance while later shield ordering still needs
    differential verification.
    """

    damage_type: str
    requested: float
    post_resistance: float
    resistance_percent: float = 0.0
    armor_piercing: float = 0.0
    breakpoint_damage_type: DamageType | None = None
    breakpoint_amount: float = 0.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.damage_type, "damage_type")
        object.__setattr__(self, "requested", _non_negative(self.requested, "requested"))
        object.__setattr__(
            self,
            "post_resistance",
            _non_negative(self.post_resistance, "post_resistance"),
        )
        object.__setattr__(
            self,
            "resistance_percent",
            _finite(self.resistance_percent, "resistance_percent"),
        )
        object.__setattr__(
            self,
            "armor_piercing",
            _finite(self.armor_piercing, "armor_piercing"),
        )
        if self.breakpoint_damage_type is not None and not isinstance(
            self.breakpoint_damage_type, DamageType
        ):
            raise ValueError("breakpoint_damage_type must be a DamageType or null")
        object.__setattr__(
            self,
            "breakpoint_amount",
            _non_negative(self.breakpoint_amount, "breakpoint_amount"),
        )
        if self.breakpoint_damage_type is None and self.breakpoint_amount != 0.0:
            raise ValueError("breakpoint_amount requires a typed breakpoint damage channel")
        tags = tuple(dict.fromkeys(self.tags))
        for tag in tags:
            _identifier(tag, "damage tag")
        object.__setattr__(self, "tags", tags)

    @property
    def resistance_fraction(self) -> float:
        return self.resistance_percent / 100.0

    @property
    def resisted(self) -> float:
        return self.requested - self.post_resistance


@dataclass(frozen=True, slots=True)
class DamageResolution:
    """Immutable result of committing one :class:`DamageTransaction`."""

    transaction: DamageTransaction
    absorbed: float
    health_before: float
    health_after: float

    def __post_init__(self) -> None:
        if not isinstance(self.transaction, DamageTransaction):
            raise ValueError("transaction must be a DamageTransaction")
        object.__setattr__(self, "absorbed", _non_negative(self.absorbed, "absorbed"))
        object.__setattr__(
            self,
            "health_before",
            _non_negative(self.health_before, "health_before"),
        )
        object.__setattr__(
            self,
            "health_after",
            _non_negative(self.health_after, "health_after"),
        )
        if self.health_after > self.health_before:
            raise ValueError("damage resolution cannot increase health")
        if self.absorbed > self.transaction.post_resistance:
            raise ValueError("absorbed damage cannot exceed post-resistance damage")

    @property
    def post_absorption(self) -> float:
        return self.transaction.post_resistance - self.absorbed

    @property
    def effective(self) -> float:
        return self.health_before - self.health_after
