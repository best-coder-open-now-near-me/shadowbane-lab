"""Validated inputs for source-derived combat formulas."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")


@dataclass(frozen=True, slots=True)
class WeaponDamageInputs:
    """The ordered inputs used by ``PlayerCharacter.calculateAtrDamageForWeapon``.

    Percentage fields use the server representation: ``0.15`` means plus fifteen percent.
    The model deliberately keeps item-local and character-wide modifiers separate because the
    server applies them on opposite sides of attribute scaling and rounding.
    """

    base_minimum: float
    base_maximum: float
    primary_attribute: int
    secondary_attribute: int
    weapon_skill: float
    weapon_mastery: float
    item_minimum_flat: float = 0.0
    item_maximum_flat: float = 0.0
    item_damage_flat: float = 0.0
    item_minimum_percent: float = 0.0
    item_maximum_percent: float = 0.0
    item_damage_percent: float = 0.0
    character_minimum_flat: float = 0.0
    character_maximum_flat: float = 0.0
    character_damage_flat: float = 0.0
    character_minimum_percent: float = 0.0
    character_maximum_percent: float = 0.0
    character_damage_percent: float = 0.0
    dual_wielding: bool = False
    death_shroud: bool = False

    def __post_init__(self) -> None:
        numeric_fields = (
            "base_minimum",
            "base_maximum",
            "primary_attribute",
            "secondary_attribute",
            "weapon_skill",
            "weapon_mastery",
            "item_minimum_flat",
            "item_maximum_flat",
            "item_damage_flat",
            "item_minimum_percent",
            "item_maximum_percent",
            "item_damage_percent",
            "character_minimum_flat",
            "character_maximum_flat",
            "character_damage_flat",
            "character_minimum_percent",
            "character_maximum_percent",
            "character_damage_percent",
        )
        for field_name in numeric_fields:
            _finite(getattr(self, field_name), field_name)
        if self.base_minimum < 0 or self.base_maximum < self.base_minimum:
            raise ValueError("weapon base damage bounds must be ordered and non-negative")
        for field_name in (
            "primary_attribute",
            "secondary_attribute",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("weapon_skill", "weapon_mastery"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must not be negative")
        if not isinstance(self.dual_wielding, bool) or not isinstance(self.death_shroud, bool):
            raise ValueError("dual_wielding and death_shroud must be booleans")
