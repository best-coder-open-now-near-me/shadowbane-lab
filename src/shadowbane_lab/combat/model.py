"""Validated inputs for source-derived combat formulas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from shadowbane_lab.combat.types import CombatStance, DamageType, ResistanceType


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _non_negative(value: float, field_name: str) -> None:
    _finite(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _numeric_pairs(
    values: tuple[tuple[str, float], ...], field_name: str, *, non_negative: bool
) -> None:
    keys = tuple(key for key, _ in values)
    if len(keys) != len(set(keys)):
        raise ValueError(f"{field_name} must not contain duplicate keys")
    for key, value in values:
        _identifier(key, f"{field_name} key")
        if non_negative:
            _non_negative(value, f"{field_name} value")
        else:
            _finite(value, f"{field_name} value")


class CompatibilityStatus(StrEnum):
    LIVE_VERIFIED = "live_verified"
    SOURCE_REVISION_ACCEPTED = "source_revision_accepted"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class SheetModifiers:
    flat_ocv: float = 0.0
    positive_ocv_percent: float = 0.0
    negative_ocv_percent: float = 0.0
    flat_dcv: float = 0.0
    positive_dcv_percent: float = 0.0
    negative_dcv_percent: float = 0.0
    armor_piercing: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "flat_ocv",
            "positive_ocv_percent",
            "negative_ocv_percent",
            "flat_dcv",
            "positive_dcv_percent",
            "negative_dcv_percent",
            "armor_piercing",
        ):
            _finite(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class StanceModifiers:
    """Independent percentage channels published for one trained stance rank."""

    attack_percent: float = 0.0
    defense_percent: float = 0.0
    damage_dealt_percent: float = 0.0
    weapon_delay_percent: float = 0.0
    movement_percent: float = 0.0
    stamina_recovery_percent: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "attack_percent",
            "defense_percent",
            "damage_dealt_percent",
            "weapon_delay_percent",
            "movement_percent",
            "stamina_recovery_percent",
        ):
            value = getattr(self, field_name)
            _finite(value, field_name)
            if value <= -1.0:
                raise ValueError(f"{field_name} must leave a positive multiplier")


@dataclass(frozen=True, slots=True)
class StanceProfile:
    """Source-pinned modifiers for one base/promotion stance power."""

    profile_key: str
    stance: CombatStance
    rank: int
    source_id: str
    source_revision: str
    modifiers: StanceModifiers = StanceModifiers()

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.profile_key, "profile_key"),
            (self.source_id, "source_id"),
            (self.source_revision, "source_revision"),
        ):
            _identifier(value, field_name)
        if not isinstance(self.stance, CombatStance):
            try:
                object.__setattr__(self, "stance", CombatStance(self.stance))
            except (TypeError, ValueError) as exc:
                raise ValueError("stance must be a CombatStance") from exc
        if self.stance in {CombatStance.NORMAL, CombatStance.TRAVEL}:
            raise ValueError("trained stance profiles must be offensive, defensive, or precise")
        _non_negative_integer(self.rank, "rank")
        if self.rank == 0:
            raise ValueError("stance rank must be positive")
        if not isinstance(self.modifiers, StanceModifiers):
            raise ValueError("modifiers must be StanceModifiers")


@dataclass(frozen=True, slots=True)
class WeaponProcProfile:
    proc_key: str
    probability: float
    minimum: float
    maximum: float
    damage_type: DamageType
    trains: int = 0

    def __post_init__(self) -> None:
        _identifier(self.proc_key, "proc_key")
        if not isinstance(self.damage_type, DamageType):
            try:
                object.__setattr__(self, "damage_type", DamageType(self.damage_type))
            except (TypeError, ValueError) as exc:
                raise ValueError("damage_type must be a DamageType") from exc
        if self.damage_type is DamageType.UNKNOWN:
            raise ValueError("weapon procs require a known damage type")
        _finite(self.probability, "probability")
        if not 0.0 < self.probability <= 1.0:
            raise ValueError("proc probability must be in (0, 1]")
        _finite(self.minimum, "minimum")
        _finite(self.maximum, "maximum")
        if self.minimum <= 0 or self.maximum <= self.minimum:
            raise ValueError("proc damage bounds must be positive and ordered")
        _non_negative_integer(self.trains, "trains")


@dataclass(frozen=True, slots=True)
class WeaponProfile:
    weapon_key: str
    damage_type: DamageType
    skill_key: str
    mastery_key: str
    base_minimum: float
    base_maximum: float
    speed_tenths: float
    range_units: float
    strength_based: bool
    ranged: bool = False
    dual_wielding: bool = False
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
    weapon_speed_percent: float = 0.0
    attack_delay_percent: float = 0.0
    procs: tuple[WeaponProcProfile, ...] = ()

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.weapon_key, "weapon_key"),
            (self.skill_key, "skill_key"),
            (self.mastery_key, "mastery_key"),
        ):
            _identifier(value, field_name)
        if not isinstance(self.damage_type, DamageType):
            try:
                object.__setattr__(self, "damage_type", DamageType(self.damage_type))
            except (TypeError, ValueError) as exc:
                raise ValueError("damage_type must be a DamageType") from exc
        if self.damage_type is DamageType.UNKNOWN:
            raise ValueError("weapons require a known damage type")
        for field_name in (
            "base_minimum",
            "base_maximum",
            "speed_tenths",
            "range_units",
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
            "weapon_speed_percent",
            "attack_delay_percent",
        ):
            _finite(getattr(self, field_name), field_name)
        if self.base_minimum < 0 or self.base_maximum <= self.base_minimum:
            raise ValueError("weapon damage bounds must be positive and ordered")
        if self.speed_tenths <= 0 or self.range_units <= 0:
            raise ValueError("weapon speed and range must be positive")
        if not isinstance(self.strength_based, bool):
            raise ValueError("strength_based must be a boolean")
        if not isinstance(self.ranged, bool) or not isinstance(self.dual_wielding, bool):
            raise ValueError("ranged and dual_wielding must be booleans")
        if any(not isinstance(proc, WeaponProcProfile) for proc in self.procs):
            raise ValueError("procs must contain WeaponProcProfile values")
        proc_keys = tuple(proc.proc_key for proc in self.procs)
        if len(proc_keys) != len(set(proc_keys)):
            raise ValueError("proc keys must not contain duplicates")


@dataclass(frozen=True, slots=True)
class CombatSheet:
    """Complete runtime inputs for one combatant; no game values are inferred at execution."""

    sheet_id: str
    profession: str
    level: int
    source_id: str
    source_revision: str
    formula_revision: str
    compatibility: CompatibilityStatus
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    spirit: int
    maximum_health: float
    maximum_mana: float
    maximum_stamina: float
    move_speed: float
    equipment_defense: float
    skill_values: tuple[tuple[str, float], ...]
    power_focus_values: tuple[tuple[str, float], ...]
    resistances: tuple[tuple[str, float], ...]
    passive_defenses: tuple[tuple[str, float], ...]
    modifiers: SheetModifiers = SheetModifiers()
    stance_profiles: tuple[StanceProfile, ...] = ()
    weapon: WeaponProfile | None = None
    off_hand_weapon: WeaponProfile | None = None
    protection_type: DamageType | None = None
    protection_trains: int = 0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.sheet_id, "sheet_id"),
            (self.profession, "profession"),
            (self.source_id, "source_id"),
            (self.source_revision, "source_revision"),
            (self.formula_revision, "formula_revision"),
        ):
            _identifier(value, field_name)
        if not isinstance(self.compatibility, CompatibilityStatus):
            raise ValueError("compatibility must be a CompatibilityStatus")
        _non_negative_integer(self.level, "level")
        if self.level == 0:
            raise ValueError("level must be positive")
        for field_name in (
            "strength",
            "dexterity",
            "constitution",
            "intelligence",
            "spirit",
        ):
            _non_negative_integer(getattr(self, field_name), field_name)
        for field_name in (
            "maximum_health",
            "maximum_mana",
            "maximum_stamina",
            "move_speed",
        ):
            value = getattr(self, field_name)
            _finite(value, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
        _non_negative(self.equipment_defense, "equipment_defense")
        _numeric_pairs(self.skill_values, "skill_values", non_negative=True)
        _numeric_pairs(self.power_focus_values, "power_focus_values", non_negative=True)
        _numeric_pairs(self.resistances, "resistances", non_negative=False)
        normalized_resistances: list[tuple[str, float]] = []
        for key, value in self.resistances:
            try:
                normalized_key = ResistanceType(key).value
            except (TypeError, ValueError) as exc:
                raise ValueError(f"unknown resistance type: {key}") from exc
            normalized_resistances.append((normalized_key, value))
        _numeric_pairs(self.passive_defenses, "passive_defenses", non_negative=True)
        if any(value > 75 for _, value in self.passive_defenses):
            raise ValueError("passive defense chances must not exceed 75")
        if not isinstance(self.modifiers, SheetModifiers):
            raise ValueError("modifiers must be a SheetModifiers")
        if any(not isinstance(profile, StanceProfile) for profile in self.stance_profiles):
            raise ValueError("stance_profiles must contain StanceProfile values")
        stance_keys = tuple(profile.stance for profile in self.stance_profiles)
        if len(stance_keys) != len(set(stance_keys)):
            raise ValueError("stance_profiles must not repeat a stance")
        profile_keys = {profile.profile_key for profile in self.stance_profiles}
        if len(profile_keys) > 1:
            raise ValueError("stance_profiles must share one profile_key")
        if self.weapon is not None and not isinstance(self.weapon, WeaponProfile):
            raise ValueError("weapon must be a WeaponProfile or null")
        if self.off_hand_weapon is not None and not isinstance(self.off_hand_weapon, WeaponProfile):
            raise ValueError("off_hand_weapon must be a WeaponProfile or null")
        if self.off_hand_weapon is not None and self.weapon is None:
            raise ValueError("off_hand_weapon requires a main-hand weapon")
        if self.off_hand_weapon is not None and (
            not self.weapon.dual_wielding or not self.off_hand_weapon.dual_wielding
        ):
            raise ValueError("both weapon profiles must mark a dual-wield loadout")
        if self.protection_type is not None:
            if not isinstance(self.protection_type, DamageType):
                try:
                    object.__setattr__(self, "protection_type", DamageType(self.protection_type))
                except (TypeError, ValueError) as exc:
                    raise ValueError("protection_type must be a DamageType") from exc
            if self.protection_type is DamageType.UNKNOWN:
                raise ValueError("protection requires a known damage type")
        _non_negative_integer(self.protection_trains, "protection_trains")
        if self.protection_type is None and self.protection_trains != 0:
            raise ValueError("protection_trains requires protection_type")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")
        for tag in self.tags:
            _identifier(tag, "tag")
        object.__setattr__(self, "resistances", tuple(sorted(normalized_resistances)))
        for field_name in ("skill_values", "power_focus_values", "passive_defenses"):
            object.__setattr__(self, field_name, tuple(sorted(getattr(self, field_name))))
        object.__setattr__(
            self,
            "stance_profiles",
            tuple(sorted(self.stance_profiles, key=lambda profile: profile.stance.value)),
        )
        object.__setattr__(self, "tags", tuple(sorted(self.tags)))

    def skill_value(self, skill_key: str) -> float:
        try:
            return dict(self.skill_values)[skill_key]
        except KeyError as exc:
            raise ValueError(f"combat sheet is missing skill value {skill_key}") from exc

    def power_focus(self, action_key: str) -> float:
        try:
            return dict(self.power_focus_values)[action_key]
        except KeyError as exc:
            raise ValueError(f"combat sheet is missing power focus {action_key}") from exc


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
