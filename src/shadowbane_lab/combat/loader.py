"""Strict JSON loader for complete combat-sheet and progression-build profiles."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.combat.model import (
    CombatSheet,
    CompatibilityStatus,
    SheetModifiers,
    WeaponProcProfile,
    WeaponProfile,
)
from shadowbane_lab.rulesets import CharacterBuild

COMBAT_PROFILE_SCHEMA_VERSION = 1


class CombatProfileLoadError(ValueError):
    pass


def combat_profile_dict(
    sheet: CombatSheet,
    build: CharacterBuild,
) -> dict[str, object]:
    """Encode a validated sheet/build pair in the strict version-1 interchange shape."""

    if not isinstance(sheet, CombatSheet):
        raise ValueError("sheet must be a CombatSheet")
    if not isinstance(build, CharacterBuild):
        raise ValueError("build must be a CharacterBuild")
    weapon = None
    if sheet.weapon is not None:
        weapon = asdict(sheet.weapon)
        weapon["procs"] = [asdict(proc) for proc in sheet.weapon.procs]
    return {
        "schema_version": COMBAT_PROFILE_SCHEMA_VERSION,
        "sheet": {
            "sheet_id": sheet.sheet_id,
            "profession": sheet.profession,
            "level": sheet.level,
            "source": {
                "source_id": sheet.source_id,
                "source_revision": sheet.source_revision,
                "formula_revision": sheet.formula_revision,
                "compatibility": sheet.compatibility.value,
            },
            "attributes": {
                "strength": sheet.strength,
                "dexterity": sheet.dexterity,
                "constitution": sheet.constitution,
                "intelligence": sheet.intelligence,
                "spirit": sheet.spirit,
            },
            "resources": {
                "health": sheet.maximum_health,
                "mana": sheet.maximum_mana,
                "stamina": sheet.maximum_stamina,
            },
            "move_speed": sheet.move_speed,
            "equipment_defense": sheet.equipment_defense,
            "skill_values": dict(sheet.skill_values),
            "power_focus_values": dict(sheet.power_focus_values),
            "resistances": dict(sheet.resistances),
            "passive_defenses": dict(sheet.passive_defenses),
            "modifiers": asdict(sheet.modifiers),
            "weapon": weapon,
            "protection": {
                "type": sheet.protection_type,
                "trains": sheet.protection_trains,
            },
            "tags": list(sheet.tags),
        },
        "build": {
            "profession": build.profession,
            "level": build.level,
            "skill_ranks": dict(build.skill_ranks),
            "power_ranks": dict(build.power_ranks),
            "enabled_power_keys": (
                None
                if build.enabled_power_keys is None
                else list(build.enabled_power_keys)
            ),
        },
    }


def encode_combat_profile(sheet: CombatSheet, build: CharacterBuild) -> str:
    """Return deterministic human-readable JSON suitable for versioning or capture export."""

    return json.dumps(
        combat_profile_dict(sheet, build),
        indent=2,
        sort_keys=True,
    ) + "\n"


def load_combat_profile(path: str | Path) -> tuple[CombatSheet, CharacterBuild]:
    return load_combat_profile_text(Path(path).read_text(encoding="utf-8"))


def load_combat_profile_text(text: str) -> tuple[CombatSheet, CharacterBuild]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CombatProfileLoadError("combat profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "combat profile")
        _exact_keys(data, {"schema_version", "sheet", "build"}, "combat profile")
        if _integer(data, "schema_version") != COMBAT_PROFILE_SCHEMA_VERSION:
            raise CombatProfileLoadError("unsupported combat profile schema version")
        return _sheet(_object(data, "sheet")), _build(_object(data, "build"))
    except CombatProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise CombatProfileLoadError(str(exc)) from exc


def _sheet(data: Mapping[str, Any]) -> CombatSheet:
    expected = {
        "sheet_id",
        "profession",
        "level",
        "source",
        "attributes",
        "resources",
        "move_speed",
        "equipment_defense",
        "skill_values",
        "power_focus_values",
        "resistances",
        "passive_defenses",
        "modifiers",
        "weapon",
        "protection",
        "tags",
    }
    _exact_keys(data, expected, "sheet")
    source = _object(data, "source")
    _exact_keys(
        source,
        {"source_id", "source_revision", "formula_revision", "compatibility"},
        "source",
    )
    attributes = _object(data, "attributes")
    _exact_keys(
        attributes,
        {"strength", "dexterity", "constitution", "intelligence", "spirit"},
        "attributes",
    )
    resources = _object(data, "resources")
    _exact_keys(resources, {"health", "mana", "stamina"}, "resources")
    protection = _object(data, "protection")
    _exact_keys(protection, {"type", "trains"}, "protection")
    return CombatSheet(
        sheet_id=_string(data, "sheet_id"),
        profession=_string(data, "profession"),
        level=_integer(data, "level"),
        source_id=_string(source, "source_id"),
        source_revision=_string(source, "source_revision"),
        formula_revision=_string(source, "formula_revision"),
        compatibility=CompatibilityStatus(_string(source, "compatibility")),
        strength=_integer(attributes, "strength"),
        dexterity=_integer(attributes, "dexterity"),
        constitution=_integer(attributes, "constitution"),
        intelligence=_integer(attributes, "intelligence"),
        spirit=_integer(attributes, "spirit"),
        maximum_health=_number(resources, "health"),
        maximum_mana=_number(resources, "mana"),
        maximum_stamina=_number(resources, "stamina"),
        move_speed=_number(data, "move_speed"),
        equipment_defense=_number(data, "equipment_defense"),
        skill_values=_number_pairs(_object(data, "skill_values")),
        power_focus_values=_number_pairs(_object(data, "power_focus_values")),
        resistances=_number_pairs(_object(data, "resistances")),
        passive_defenses=_number_pairs(_object(data, "passive_defenses")),
        modifiers=_modifiers(_object(data, "modifiers")),
        weapon=_nullable_weapon(data.get("weapon")),
        protection_type=_nullable_string(protection, "type"),
        protection_trains=_integer(protection, "trains"),
        tags=_strings(data, "tags"),
    )


def _modifiers(data: Mapping[str, Any]) -> SheetModifiers:
    fields = {
        "flat_ocv",
        "positive_ocv_percent",
        "negative_ocv_percent",
        "flat_dcv",
        "positive_dcv_percent",
        "negative_dcv_percent",
        "armor_piercing",
    }
    _exact_keys(data, fields, "modifiers")
    return SheetModifiers(**{field: _number(data, field) for field in fields})


def _nullable_weapon(value: Any) -> WeaponProfile | None:
    if value is None:
        return None
    data = _mapping(value, "weapon")
    required = {
        "weapon_key",
        "damage_type",
        "skill_key",
        "mastery_key",
        "base_minimum",
        "base_maximum",
        "speed_tenths",
        "range_units",
        "strength_based",
        "ranged",
        "dual_wielding",
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
        "procs",
    }
    _exact_keys(data, required, "weapon")
    numeric_fields = required - {
        "weapon_key",
        "damage_type",
        "skill_key",
        "mastery_key",
        "strength_based",
        "ranged",
        "dual_wielding",
        "procs",
    }
    return WeaponProfile(
        weapon_key=_string(data, "weapon_key"),
        damage_type=_string(data, "damage_type"),
        skill_key=_string(data, "skill_key"),
        mastery_key=_string(data, "mastery_key"),
        strength_based=_boolean(data, "strength_based"),
        ranged=_boolean(data, "ranged"),
        dual_wielding=_boolean(data, "dual_wielding"),
        procs=tuple(_proc(item) for item in _objects(data, "procs")),
        **{field: _number(data, field) for field in numeric_fields},
    )


def _proc(data: Mapping[str, Any]) -> WeaponProcProfile:
    _exact_keys(
        data,
        {"proc_key", "probability", "minimum", "maximum", "damage_type", "trains"},
        "proc",
    )
    return WeaponProcProfile(
        proc_key=_string(data, "proc_key"),
        probability=_number(data, "probability"),
        minimum=_number(data, "minimum"),
        maximum=_number(data, "maximum"),
        damage_type=_string(data, "damage_type"),
        trains=_integer(data, "trains"),
    )


def _build(data: Mapping[str, Any]) -> CharacterBuild:
    _exact_keys(
        data,
        {"profession", "level", "skill_ranks", "power_ranks", "enabled_power_keys"},
        "build",
    )
    enabled = data["enabled_power_keys"]
    if enabled is not None:
        enabled = _string_sequence(enabled, "enabled_power_keys")
    return CharacterBuild(
        profession=_string(data, "profession"),
        level=_integer(data, "level"),
        skill_ranks=_integer_pairs(_object(data, "skill_ranks")),
        power_ranks=_integer_pairs(_object(data, "power_ranks")),
        enabled_power_keys=cast(tuple[str, ...] | None, enabled),
    )


def _exact_keys(data: Mapping[str, Any], expected: set[str], field_name: str) -> None:
    missing = expected - set(data)
    extra = set(data) - expected
    if missing:
        raise CombatProfileLoadError(
            f"{field_name} is missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise CombatProfileLoadError(
            f"{field_name} has unsupported fields: {', '.join(sorted(extra))}"
        )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CombatProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    try:
        return _mapping(data[key], key)
    except KeyError as exc:
        raise CombatProfileLoadError(f"missing required field: {key}") from exc


def _sequence(data: Mapping[str, Any], key: str) -> Sequence[Any]:
    try:
        value = data[key]
    except KeyError as exc:
        raise CombatProfileLoadError(f"missing required field: {key}") from exc
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CombatProfileLoadError(f"{key} must be an array")
    return value


def _objects(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(item, f"{key} item") for item in _sequence(data, key))


def _string(data: Mapping[str, Any], key: str) -> str:
    try:
        value = data[key]
    except KeyError as exc:
        raise CombatProfileLoadError(f"missing required field: {key}") from exc
    if not isinstance(value, str) or not value.strip():
        raise CombatProfileLoadError(f"{key} must be a non-empty string")
    return value


def _nullable_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CombatProfileLoadError(f"{key} must be a non-empty string or null")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    try:
        value = data[key]
    except KeyError as exc:
        raise CombatProfileLoadError(f"missing required field: {key}") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise CombatProfileLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    try:
        value = data[key]
    except KeyError as exc:
        raise CombatProfileLoadError(f"missing required field: {key}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CombatProfileLoadError(f"{key} must be a number")
    return float(value)


def _boolean(data: Mapping[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise CombatProfileLoadError(f"{key} must be a boolean")
    return value


def _number_pairs(data: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((key, _number(data, key)) for key in data))


def _integer_pairs(data: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((key, _integer(data, key)) for key in data))


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    return _string_sequence(_sequence(data, key), key)


def _string_sequence(value: Sequence[Any], field_name: str) -> tuple[str, ...]:
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise CombatProfileLoadError(f"{field_name} must contain non-empty strings")
    return tuple(cast(str, item) for item in value)
