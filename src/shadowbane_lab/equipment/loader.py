"""Strict loader for the bundled equipment optimization catalog."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from shadowbane_lab.equipment.model import (
    AffixModifier,
    AffixPool,
    AffixPoolEntry,
    AffixPosition,
    AffixRoute,
    BaseItem,
    EquipmentCatalog,
    ItemRequirement,
)

SCHEMA_VERSION = 1


class EquipmentCatalogLoadError(ValueError):
    """Raised when equipment catalog data cannot be loaded without guessing."""


def load_bundled_equipment_catalog() -> EquipmentCatalog:
    resource = files("shadowbane_lab.equipment").joinpath(
        "data/wonderbane_equipment_candidate_v1.json"
    )
    return load_equipment_catalog_text(resource.read_text(encoding="utf-8"))


def load_equipment_catalog(path: str | Path) -> EquipmentCatalog:
    return load_equipment_catalog_text(Path(path).read_text(encoding="utf-8"))


def load_equipment_catalog_text(text: str) -> EquipmentCatalog:
    try:
        data = _mapping(json.loads(text), "catalog")
        if _integer(data, "schema_version") != SCHEMA_VERSION:
            raise EquipmentCatalogLoadError("unsupported equipment catalog schema version")
        return EquipmentCatalog(
            catalog_id=_string(data, "catalog_id"),
            target_variant=_string(data, "target_variant"),
            status=_string(data, "status"),
            retrieved_on=_string(data, "retrieved_on"),
            sources=tuple(_mapping(item, "source") for item in _list(data, "sources")),
            coverage=_mapping(data["coverage"], "coverage"),
            current_client=_mapping(data["current_client"], "current_client"),
            base_items=tuple(_base_item(item) for item in _mappings(data, "base_items")),
            modifiers=tuple(_modifier(item) for item in _mappings(data, "modifiers")),
            pools=tuple(_pool(item) for item in _mappings(data, "pools")),
            routes=tuple(_route(item) for item in _mappings(data, "routes")),
        )
    except EquipmentCatalogLoadError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EquipmentCatalogLoadError(f"invalid equipment catalog: {exc}") from exc


def _base_item(data: dict[str, Any]) -> BaseItem:
    return BaseItem(
        item_id=_integer(data, "item_id"),
        name=_string(data, "name"),
        historical_name=_string(data, "historical_name"),
        item_type=_string(data, "item_type"),
        durability=_number(data, "durability"),
        equip_flags=_integer(data, "equip_flags"),
        restrict_flags=_integer(data, "restrict_flags"),
        value=_integer(data, "value"),
        weight=_integer(data, "weight"),
        skill_required=_string(data, "skill_required", allow_empty=True),
        skill_percent_required=_integer(data, "skill_percent_required"),
        mastery=_optional_string(data, "mastery"),
        slash_resist=_number(data, "slash_resist"),
        crush_resist=_number(data, "crush_resist"),
        pierce_resist=_number(data, "pierce_resist"),
        block_modifier=_number(data, "block_modifier"),
        defense=_integer(data, "defense"),
        dexterity_penalty=_number(data, "dexterity_penalty"),
        damage_type=_optional_string(data, "damage_type"),
        speed=_number(data, "speed"),
        range=_number(data, "range"),
        minimum_damage=_integer(data, "minimum_damage"),
        maximum_damage=_integer(data, "maximum_damage"),
        two_handed=_boolean(data, "two_handed"),
        strength_based=_boolean(data, "strength_based"),
        parry_bonus=_number(data, "parry_bonus"),
        modifier_table_id=_integer(data, "modifier_table_id"),
        item_hash_id=_integer(data, "item_hash_id"),
        current_name_verified=_boolean(data, "current_name_verified"),
        requirements=tuple(
            ItemRequirement(
                kind=_integer(item, "kind"),
                required=_boolean(item, "required"),
                token=_integer(item, "token"),
            )
            for item in _mappings(data, "requirements")
        ),
    )


def _modifier(data: dict[str, Any]) -> AffixModifier:
    return AffixModifier(
        table_id=_integer(data, "table_id"),
        table_name=_string(data, "table_name"),
        minimum_roll=_number(data, "minimum_roll"),
        maximum_roll=_number(data, "maximum_roll"),
        action_id=_string(data, "action_id"),
        level=_integer(data, "level"),
        value=_integer(data, "value"),
        current_prefix_name=_optional_string(data, "current_prefix_name"),
        current_suffix_name=_optional_string(data, "current_suffix_name"),
    )


def _pool(data: dict[str, Any]) -> AffixPool:
    return AffixPool(
        pool_id=_integer(data, "pool_id"),
        name=_string(data, "name"),
        positions=tuple(AffixPosition(value) for value in _strings(data, "positions")),
        entries=tuple(
            AffixPoolEntry(
                minimum_roll=_integer(item, "minimum_roll"),
                maximum_roll=_integer(item, "maximum_roll"),
                modifier_table_id=_integer(item, "modifier_table_id"),
                modifier_table_name=_string(item, "modifier_table_name"),
            )
            for item in _mappings(data, "entries")
        ),
    )


def _route(data: dict[str, Any]) -> AffixRoute:
    return AffixRoute(
        generation_table_id=_integer(data, "generation_table_id"),
        generation_table_name=_string(data, "generation_table_name"),
        item_table_id=_integer(data, "item_table_id"),
        item_table_name=_string(data, "item_table_name"),
        item_id=_integer(data, "item_id"),
        prefix_pool_id=_optional_integer(data, "prefix_pool_id"),
        suffix_pool_id=_optional_integer(data, "suffix_pool_id"),
    )


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EquipmentCatalogLoadError(f"{label} must be an object")
    return value


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data[key]
    if not isinstance(value, list):
        raise EquipmentCatalogLoadError(f"{key} must be an array")
    return value


def _mappings(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [_mapping(item, f"{key} entry") for item in _list(data, key)]


def _string(data: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = data[key]
    if not isinstance(value, str) or (not allow_empty and not value):
        raise EquipmentCatalogLoadError(f"{key} must be a string")
    return value


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data[key]
    if value is not None and not isinstance(value, str):
        raise EquipmentCatalogLoadError(f"{key} must be a string or null")
    return value


def _integer(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise EquipmentCatalogLoadError(f"{key} must be an integer")
    return value


def _optional_integer(data: dict[str, Any], key: str) -> int | None:
    value = data[key]
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise EquipmentCatalogLoadError(f"{key} must be an integer or null")
    return value


def _number(data: dict[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EquipmentCatalogLoadError(f"{key} must be a number")
    return float(value)


def _boolean(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise EquipmentCatalogLoadError(f"{key} must be a boolean")
    return value


def _strings(data: dict[str, Any], key: str) -> list[str]:
    values = _list(data, key)
    if any(not isinstance(value, str) for value in values):
        raise EquipmentCatalogLoadError(f"{key} must contain strings")
    return values
