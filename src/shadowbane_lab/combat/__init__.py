"""Source-pinned Shadowbane combat formulas and build-sheet models."""

from shadowbane_lab.combat.formulas import (
    StackPriority,
    defense_rating,
    effective_resistance,
    melee_hit_chance_percent,
    power_attack_rating,
    power_hit_chance_percent,
    resisted_amount,
    should_overwrite_effect,
    spell_amount_bounds,
    triangular_roll,
    weapon_attack_rating,
    weapon_damage_bounds,
)
from shadowbane_lab.combat.model import WeaponDamageInputs

__all__ = [
    "StackPriority",
    "WeaponDamageInputs",
    "defense_rating",
    "effective_resistance",
    "melee_hit_chance_percent",
    "power_attack_rating",
    "power_hit_chance_percent",
    "resisted_amount",
    "should_overwrite_effect",
    "spell_amount_bounds",
    "triangular_roll",
    "weapon_attack_rating",
    "weapon_damage_bounds",
]
