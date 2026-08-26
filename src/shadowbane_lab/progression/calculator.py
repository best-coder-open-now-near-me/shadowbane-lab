"""Current WonderBane progression budgets and sourced proc estimates."""

from __future__ import annotations

from math import floor, sqrt

from shadowbane_lab.progression.model import (
    CharacterProgression,
    ProcEstimate,
    ProcLoadout,
    ProgressionEvaluation,
    ProgressionProfile,
    RuneKind,
    StatLine,
)


class IllegalProgressionError(ValueError):
    """Raised when a character plan exceeds a sourced game constraint."""


def ability_points_for_level(level: int) -> int:
    """WonderBane's current level-earned ability-point pool (creation points excluded)."""

    _level(level)
    if level < 20:
        return (level - 1) * 5
    if level < 30:
        return 90 + (level - 19) * 4
    if level < 40:
        return 130 + (level - 29) * 3
    if level < 50:
        return 160 + (level - 39) * 2
    return 180 + (level - 49)


def rogue_training_points_for_level(level: int) -> int:
    """Non-Human Rogue trains earned through a level, including the level-75 train."""

    _level(level)
    if level <= 10:
        return max(0, level - 1) * 4
    total = 36 + (min(level, 59) - 10) * 10
    if level >= 60:
        total += (min(level, 64) - 59) * 5
    if level >= 65:
        total += (min(level, 69) - 64) * 4
    if level >= 70:
        total += (min(level, 74) - 69) * 3
    if level >= 75:
        total += 2
    return total


def evaluate_progression(
    profile: ProgressionProfile, build: CharacterProgression
) -> ProgressionEvaluation:
    if not isinstance(profile, ProgressionProfile):
        raise ValueError("profile must be a ProgressionProfile")
    if not isinstance(build, CharacterProgression):
        raise ValueError("build must be a CharacterProgression")
    if build.level > profile.limits.maximum_level:
        raise IllegalProgressionError(
            f"level {build.level} exceeds maximum {profile.limits.maximum_level}"
        )
    if len(build.rune_keys) > profile.limits.maximum_runes:
        raise IllegalProgressionError("rune count exceeds the current server limit")

    runes = tuple(profile.rune(key) for key in build.rune_keys)
    disciplines = tuple(item for item in runes if item.kind is RuneKind.DISCIPLINE)
    discipline_limit = (
        profile.limits.disciplines_at_70
        if build.level >= 70
        else profile.limits.disciplines_below_70
    )
    if len(disciplines) > discipline_limit:
        raise IllegalProgressionError(
            f"level {build.level} permits only {discipline_limit} disciplines"
        )
    for rune in runes:
        if build.level < rune.minimum_level:
            raise IllegalProgressionError(f"{rune.name} requires level {rune.minimum_level}")

    identity = profile.identity
    boon = StatLine(*(identity.boon for _ in range(5)))
    no_rune_stats = identity.race_start.plus(
        identity.base_modifiers, boon, build.attribute_adjustments
    )
    for rune in runes:
        for stat_name, actual, required in zip(
            StatLine.names(),
            no_rune_stats.values(),
            rune.minimum_stats.values(),
            strict=True,
        ):
            if actual < required:
                raise IllegalProgressionError(
                    f"{rune.name} requires {stat_name} {required}, got {actual}"
                )

    rune_stats = _sum_stats(tuple(item.stat_grants for item in runes))
    rune_caps = _sum_stats(tuple(item.cap_grants for item in runes))
    stats = no_rune_stats.plus(rune_stats)
    caps = identity.race_caps.plus(rune_caps)
    for stat_name, actual, cap in zip(StatLine.names(), stats.values(), caps.values(), strict=True):
        if actual > cap:
            raise IllegalProgressionError(f"{stat_name} {actual} exceeds cap {cap}")
        if actual < 0:
            raise IllegalProgressionError(f"{stat_name} cannot be negative")

    rune_cost = sum(item.cost for item in runes)
    ability_total = identity.creation_pool + ability_points_for_level(build.level)
    ability_spent = build.attribute_adjustments.total + rune_cost + build.other_ability_points_spent
    if ability_spent > ability_total:
        raise IllegalProgressionError(
            f"ability plan spends {ability_spent}, but only {ability_total} are available"
        )
    training_total = rogue_training_points_for_level(build.level)
    training_spent = sum(item.points for item in build.training)
    if training_spent > training_total:
        raise IllegalProgressionError(
            f"training plan spends {training_spent}, but only {training_total} are available"
        )

    base_levels, profession_levels = _resource_levels(build.level)
    con = stats.constitution
    spi = stats.spirit
    health = _round_positive(
        (
            base_levels * identity.base_resource_factors[0]
            + profession_levels * identity.profession_resource_factors[0]
        )
        * (0.3 + 0.005 * con)
        + con
        + identity.race_resource_bonuses[0]
    )
    mana = _round_positive(
        (
            base_levels * identity.base_resource_factors[1]
            + profession_levels * identity.profession_resource_factors[1]
        )
        * (0.3 + 0.005 * spi)
        + spi
        + identity.race_resource_bonuses[1]
    )
    stamina = _round_positive(
        (
            base_levels * identity.base_resource_factors[2]
            + profession_levels * identity.profession_resource_factors[2]
        )
        * (0.3 + 0.005 * con)
        + con
        + identity.race_resource_bonuses[2]
    )
    return ProgressionEvaluation(
        profile_id=profile.profile_id,
        level=build.level,
        stats=stats,
        caps=caps,
        ability_points_total=ability_total,
        ability_points_spent=ability_spent,
        ability_points_remaining=ability_total - ability_spent,
        training_points_total=training_total,
        training_points_spent=training_spent,
        training_points_remaining=training_total - training_spent,
        health=health,
        mana=mana,
        stamina=stamina,
        baseline_defense=stats.dexterity * 2,
        active_runes=tuple(item.key for item in runes),
    )


def focus_skill_cap(
    *, intelligence: int, primary_stat: int, race_bonus: int = 0, trait_bonus: int = 0
) -> float:
    for value, name in (
        (intelligence, "intelligence"),
        (primary_stat, "primary_stat"),
        (race_bonus, "race_bonus"),
        (trait_bonus, "trait_bonus"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    return 55.0 + intelligence + primary_stat / 10.0 + race_bonus + trait_bonus


def melee_attack_rating(
    *,
    dexterity: int,
    weapon_skill: float,
    weapon_mastery: float,
    enchantment_bonus: float = 0.0,
    stance_modifier: float = 1.0,
) -> float:
    if min(dexterity, weapon_skill, weapon_mastery, enchantment_bonus) < 0:
        raise ValueError("attack-rating inputs must be non-negative")
    if stance_modifier <= 0:
        raise ValueError("stance_modifier must be positive")
    return (
        dexterity / 2.0 + weapon_skill * 4.0 + weapon_mastery * 3.0 + enchantment_bonus
    ) * stance_modifier


def estimate_procs(
    profile: ProgressionProfile,
    stats: StatLine,
    loadout: ProcLoadout,
) -> ProcEstimate:
    weapon = profile.weapon(loadout.weapon_key)
    effects = tuple(profile.proc_effect(key) for key in loadout.proc_effect_keys)
    speed_multiplier = 1.0
    for percent in (
        loadout.alacrity_percent,
        loadout.stance_speed_percent,
        loadout.buff_speed_percent,
    ):
        speed_multiplier *= 1.0 - percent / 100.0
    delay_seconds = max(1.0, weapon.base_speed * speed_multiplier / 10.0)
    hits_per_second = loadout.hands * loadout.successful_hit_rate / delay_seconds

    expected_triggers = 0.0
    expected_damage_rate = 0.0
    weighted_damage = 0.0
    for effect in effects:
        focus = 0.0 if not effect.focus_scaling else 1.0
        minimum, maximum = spell_damage_range(
            intelligence=stats.intelligence,
            spirit=stats.spirit,
            focus=focus,
            base_minimum=effect.base_minimum_damage,
            base_maximum=effect.base_maximum_damage,
        )
        expected_damage = (minimum + maximum) / 2.0
        trigger_rate = hits_per_second * effect.chance_per_successful_hit
        expected_triggers += trigger_rate
        expected_damage_rate += trigger_rate * expected_damage
        weighted_damage += trigger_rate * expected_damage
    damage_per_trigger = weighted_damage / expected_triggers if expected_triggers else 0.0
    return ProcEstimate(
        intelligence=stats.intelligence,
        spirit=stats.spirit,
        delay_seconds_per_hand=delay_seconds,
        successful_hits_per_second=hits_per_second,
        expected_triggers_per_second=expected_triggers,
        expected_proc_damage_per_trigger=damage_per_trigger,
        expected_proc_damage_per_second=expected_damage_rate,
        expected_proc_damage_per_minute=expected_damage_rate * 60.0,
    )


def spell_damage_range(
    *,
    intelligence: int,
    spirit: int,
    focus: float,
    base_minimum: float,
    base_maximum: float,
) -> tuple[float, float]:
    if intelligence < 1 or spirit < 1:
        raise ValueError("intelligence and spirit must be positive")
    if focus < 0 or base_minimum <= 0 or base_maximum < base_minimum:
        raise ValueError("spell damage inputs are invalid")
    minimum_multiplier = (
        0.0045 * intelligence
        + 0.055 * sqrt(intelligence - 0.5)
        + 0.006 * spirit
        + 0.07 * sqrt(spirit - 0.5)
        + 0.02 * focus
    )
    maximum_multiplier = (
        0.0117 * intelligence
        + 0.13 * sqrt(intelligence - 0.5)
        + 0.0024 * spirit
        + 0.021 * sqrt(spirit - 0.5)
        + 0.015 * focus
    )
    return minimum_multiplier * base_minimum, maximum_multiplier * base_maximum


def _resource_levels(level: int) -> tuple[float, float]:
    if level < 10:
        return float(level), 0.0
    if level < 20:
        return float(level), float(level - 9)
    if level < 30:
        return 19.0 + (level - 19) * 0.8, 10.0 + (level - 19) * 0.8
    if level < 40:
        return 27.0 + (level - 29) * 0.6, 18.0 + (level - 29) * 0.6
    if level < 50:
        return 33.0 + (level - 39) * 0.4, 24.0 + (level - 39) * 0.4
    if level < 60:
        return 37.0 + (level - 49) * 0.2, 28.0 + (level - 49) * 0.2
    return 39.0 + (level - 59) * 0.1, 30.0 + (level - 59) * 0.1


def _sum_stats(lines: tuple[StatLine, ...]) -> StatLine:
    return StatLine().plus(*lines)


def _level(level: int) -> None:
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 75:
        raise ValueError("level must be an integer in [1, 75]")


def _round_positive(value: float) -> int:
    """Match JavaScript Math.round used by WonderBane's calculator for positive pools."""

    return floor(value + 0.5)
