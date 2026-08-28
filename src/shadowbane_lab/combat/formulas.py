"""Pure ports of combat formulas pinned in the evidence manifest.

These functions preserve the source's operation order and Java truncation behavior.  They do
not claim that a WonderBane deployment uses an unchanged MagicBane revision; callers must keep
that compatibility boundary in their provenance and validate representative outputs live.
"""

from __future__ import annotations

import struct
from enum import StrEnum
from math import isfinite, pow

from shadowbane_lab.combat.model import WeaponDamageInputs


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    return float(value)


def _non_negative(value: float, field_name: str) -> float:
    result = _finite(value, field_name)
    if result < 0:
        raise ValueError(f"{field_name} must not be negative")
    return result


def _non_negative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _fraction(value: float, field_name: str) -> float:
    result = _finite(value, field_name)
    if not 0.0 <= result < 1.0:
        raise ValueError(f"{field_name} must be in [0, 1)")
    return result


def _f32(value: float) -> float:
    """Round a Python number at a Java ``float`` assignment/operation boundary."""

    return struct.unpack("<f", struct.pack("<f", value))[0]


def _java_int(value: float) -> int:
    """Java floating-point to int conversion for finite, in-range combat values."""

    return int(value)


def melee_hit_chance_percent(attack_rating: float, defense_rating: float) -> int:
    """Return the integer basic-attack hit chance used before passive defenses."""

    attack = _non_negative(attack_rating, "attack_rating")
    defense = _non_negative(defense_rating, "defense_rating")
    difference = _f32(attack - defense)
    if difference > 100.0:
        return 94
    if difference < -100.0:
        return 4
    # ``0.45`` is a Java double literal, so the float difference is promoted here.
    return _java_int((0.45 * difference) + 49)


def power_hit_chance_percent(attack_rating: float, defense_rating: float) -> int:
    """Return the integer hit chance for powers whose data requires a hit roll."""

    attack = _non_negative(attack_rating, "attack_rating")
    defense = _non_negative(defense_rating, "defense_rating")
    if attack > defense or defense == 0.0:
        return 94
    ratio = _f32(attack / defense)
    if ratio <= _f32(0.8):
        return 4
    return _java_int(_f32(_f32(450.0) * _f32(ratio - _f32(0.8)))) + 4


def weapon_attack_rating(
    weapon_skill: float,
    weapon_mastery: float,
    strength: int,
    dexterity: int,
    *,
    flat_ocv: float = 0.0,
    positive_ocv_percent: float = 0.0,
    negative_ocv_percent: float = 0.0,
    death_shroud: bool = False,
) -> int:
    """Compile the displayed attack rating for one weapon hand."""

    values = {
        "weapon_skill": weapon_skill,
        "weapon_mastery": weapon_mastery,
        "flat_ocv": flat_ocv,
        "positive_ocv_percent": positive_ocv_percent,
        "negative_ocv_percent": negative_ocv_percent,
    }
    parsed = {key: _finite(value, key) for key, value in values.items()}
    strength = _non_negative_integer(strength, "strength")
    dexterity = _non_negative_integer(dexterity, "dexterity")
    if any(parsed[key] < 0 for key in ("weapon_skill", "weapon_mastery")):
        raise ValueError("skills must not be negative")
    if death_shroud:
        return 0
    attack = _f32(_java_int(parsed["weapon_skill"]) * 4.0)
    attack = _f32(attack + _java_int(parsed["weapon_mastery"]) * 3.0)
    attack = _f32(attack + max(strength, dexterity) // 2)
    attack = _f32(attack + parsed["flat_ocv"])
    attack = _f32(attack * _f32(1.0 + parsed["positive_ocv_percent"]))
    attack = _f32(attack * _f32(1.0 + parsed["negative_ocv_percent"]))
    return _java_int(max(1.0, _f32(attack + _f32(0.5))))


def power_attack_rating(
    focus: float,
    dexterity: int,
    *,
    flat_ocv: float = 0.0,
    positive_ocv_percent: float = 0.0,
    negative_ocv_percent: float = 0.0,
) -> float:
    """Compile the floating attack rating used by a trained or quick-mastery power skill."""

    focus = _non_negative(focus, "focus")
    dexterity = _non_negative_integer(dexterity, "dexterity")
    flat_ocv = _finite(flat_ocv, "flat_ocv")
    positive = _finite(positive_ocv_percent, "positive_ocv_percent")
    negative = _finite(negative_ocv_percent, "negative_ocv_percent")
    attack = _f32(_java_int(focus) * 7.0 + dexterity // 2)
    attack = _f32(attack + flat_ocv)
    attack = _f32(attack * _f32(1.0 + positive))
    return _f32(attack * _f32(1.0 + negative))


def defense_rating(
    dexterity: int,
    equipment_defense: float,
    *,
    flat_dcv: float = 0.0,
    positive_dcv_percent: float = 0.0,
    negative_dcv_percent: float = 0.0,
    death_shroud: bool = False,
) -> int:
    """Compile defense after equipment, flat bonuses, and ordered percent modifiers."""

    dexterity = _non_negative_integer(dexterity, "dexterity")
    equipment = _finite(equipment_defense, "equipment_defense")
    flat = _finite(flat_dcv, "flat_dcv")
    positive = _finite(positive_dcv_percent, "positive_dcv_percent")
    negative = _finite(negative_dcv_percent, "negative_dcv_percent")
    if death_shroud:
        return 0
    defense = _f32(dexterity * 2.0)
    defense = _f32(defense + equipment)
    defense = _f32(defense + _java_int(flat))
    defense = float(_java_int(_f32(defense * _f32(1.0 + positive))))
    defense = float(_java_int(_f32(defense * _f32(1.0 + negative))))
    defense = max(1.0, defense)
    return _java_int(_f32(defense + _f32(0.5)))


def weapon_damage_bounds(inputs: WeaponDamageInputs) -> tuple[int, int]:
    """Compile one hand's post-stat minimum and maximum weapon damage."""

    if not isinstance(inputs, WeaponDamageInputs):
        raise ValueError("inputs must be WeaponDamageInputs")
    minimum = inputs.base_minimum + inputs.item_minimum_flat + inputs.item_damage_flat
    maximum = inputs.base_maximum + inputs.item_maximum_flat + inputs.item_damage_flat
    minimum *= 1.0 + inputs.item_minimum_percent + inputs.item_damage_percent
    maximum *= 1.0 + inputs.item_maximum_percent + inputs.item_damage_percent
    if inputs.dual_wielding:
        minimum *= _f32(0.7)
        maximum *= _f32(0.7)

    skill_total = _java_int(inputs.weapon_skill) + _java_int(inputs.weapon_mastery)
    minimum_scale = (
        _f32(0.0315) * pow(inputs.primary_attribute, _f32(0.75))
        + _f32(0.042) * pow(inputs.secondary_attribute, _f32(0.75))
        + _f32(0.01) * skill_total
    )
    maximum_scale = (
        _f32(0.0785) * pow(inputs.primary_attribute, _f32(0.75))
        + _f32(0.016) * pow(inputs.secondary_attribute, _f32(0.75))
        + _f32(0.0075) * skill_total
    )
    minimum = float(_java_int(_f32(_f32(minimum * minimum_scale) + _f32(0.5))))
    maximum = float(_java_int(_f32(_f32(maximum * maximum_scale) + _f32(0.5))))
    if inputs.death_shroud:
        minimum = _f32(minimum * _f32(0.5))
        maximum = _f32(maximum * _f32(0.5))
    minimum += inputs.character_minimum_flat + inputs.character_damage_flat
    maximum += inputs.character_maximum_flat + inputs.character_damage_flat
    minimum *= 1.0 + inputs.character_minimum_percent + inputs.character_damage_percent
    maximum *= 1.0 + inputs.character_maximum_percent + inputs.character_damage_percent
    return _java_int(minimum), _java_int(maximum)


def spell_amount_bounds(
    base_minimum: float,
    base_maximum: float,
    intelligence: float,
    spirit: float,
    focus: float,
) -> tuple[int, int]:
    """Scale a health-effect base range for a player source."""

    base_minimum = _finite(base_minimum, "base_minimum")
    base_maximum = _finite(base_maximum, "base_maximum")
    if base_maximum < base_minimum:
        raise ValueError("spell amount bounds must be ordered")
    intelligence = max(1.0, _finite(intelligence, "intelligence"))
    spirit = max(1.0, _finite(spirit, "spirit"))
    focus = _non_negative(focus, "focus")

    int_min = _f32(pow(_f32(intelligence), _f32(0.75)))
    spi_min = _f32(pow(_f32(spirit), _f32(0.75)))
    minimum_scale = _f32(_f32(int_min * _f32(0.0311)) + _f32(_f32(0.02) * _java_int(focus)))
    minimum_scale = _f32(minimum_scale + _f32(spi_min * _f32(0.0416)))
    maximum_scale = _f32(_f32(int_min * _f32(0.0785)) + _f32(_f32(0.015) * _java_int(focus)))
    maximum_scale = _f32(maximum_scale + _f32(spi_min * _f32(0.0157)))
    minimum = _java_int(_f32(_f32(_f32(base_minimum) * minimum_scale) + _f32(0.5)))
    maximum = _java_int(_f32(_f32(_f32(base_maximum) * maximum_scale) + _f32(0.5)))
    return minimum, maximum


def triangular_roll(minimum: float, maximum: float, first_roll: float, second_roll: float) -> float:
    """Resolve the two-uniform centered roll used by weapon and health-effect damage."""

    minimum = _finite(minimum, "minimum")
    maximum = _finite(maximum, "maximum")
    if maximum < minimum:
        raise ValueError("triangular roll bounds must be ordered")
    first = _fraction(first_roll, "first_roll")
    second = _fraction(second_roll, "second_roll")
    span = _f32(maximum - minimum)
    rolled = _f32(first * span)
    rolled = _f32(_f32(rolled + _f32(second * span)) * _f32(0.5))
    return _f32(rolled + minimum)


def effective_resistance(
    resistance: float,
    *,
    protection_trains: int = 0,
    incoming_trains: int = 0,
    protection_applies: bool = False,
) -> float:
    """Apply matching protection and the server's upper-only 75% resistance cap."""

    amount = _finite(resistance, "resistance")
    for value, field_name in (
        (protection_trains, "protection_trains"),
        (incoming_trains, "incoming_trains"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
    if not isinstance(protection_applies, bool):
        raise ValueError("protection_applies must be a boolean")
    if incoming_trains > 0 and protection_applies:
        amount += max(0.0, 50.0 + protection_trains - incoming_trains)
    return min(75.0, amount)


def resisted_amount(amount: float, resistance: float, armor_piercing: float = 0.0) -> float:
    """Apply resistance and armor piercing after any fortitude absorption."""

    amount = _finite(amount, "amount")
    resistance = effective_resistance(resistance)
    armor_piercing = _finite(armor_piercing, "armor_piercing")
    return _f32(_f32(amount) * _f32(_f32(1.0 - resistance * _f32(0.01)) + armor_piercing))


class StackPriority(StrEnum):
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    ALWAYS = "always"
    GREATER_THAN = "greater_than"


def should_overwrite_effect(
    *,
    incoming_order: int,
    existing_order: int,
    incoming_trains: int,
    existing_trains: int,
    priority: StackPriority,
    same_power: bool = False,
) -> bool:
    """Return whether an incoming action replaces the same stack-type slot."""

    for value, field_name in (
        (incoming_order, "incoming_order"),
        (existing_order, "existing_order"),
        (incoming_trains, "incoming_trains"),
        (existing_trains, "existing_trains"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
    if not isinstance(priority, StackPriority):
        raise ValueError("priority must be a StackPriority")
    if not isinstance(same_power, bool):
        raise ValueError("same_power must be a boolean")
    if incoming_order != existing_order:
        return incoming_order > existing_order
    if priority is StackPriority.ALWAYS:
        return True
    if priority is StackPriority.GREATER_THAN_OR_EQUAL:
        return incoming_trains >= existing_trains
    return incoming_trains > existing_trains or same_power
