"""Strict JSON loader for legal build optimization genomes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shadowbane_lab.progression import StatLine

from .build_model import (
    LEGAL_BUILD_GENOME_SCHEMA_VERSION,
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildGenome,
    SelectedAffix,
)

_GENOME_FIELDS = {
    "schema_version",
    "genome_id",
    "display_name",
    "race_id",
    "base_class_id",
    "promotion_id",
    "level",
    "move_speed",
    "trained_modifiers",
    "rune_ids",
    "skill_ranks",
    "power_ranks",
    "equipment",
}


def load_legal_build_genome(path: str | Path) -> LegalBuildGenome:
    return load_legal_build_genome_text(Path(path).read_text(encoding="utf-8"))


def load_legal_build_genome_text(text: str) -> LegalBuildGenome:
    try:
        data = _mapping(json.loads(text), "legal build genome")
    except (json.JSONDecodeError, TypeError) as exc:
        raise LegalBuildCompileError("legal build genome is not valid JSON") from exc
    _fields(data, _GENOME_FIELDS, "legal build genome")
    if _integer(data["schema_version"], "schema_version") != (
        LEGAL_BUILD_GENOME_SCHEMA_VERSION
    ):
        raise LegalBuildCompileError("unsupported legal build genome schema version")
    trained = _mapping(data["trained_modifiers"], "trained_modifiers")
    _fields(trained, set(StatLine.names()), "trained_modifiers")
    promotion = data["promotion_id"]
    return LegalBuildGenome(
        genome_id=_string(data["genome_id"], "genome_id"),
        display_name=_string(data["display_name"], "display_name"),
        race_id=_integer(data["race_id"], "race_id"),
        base_class_id=_integer(data["base_class_id"], "base_class_id"),
        promotion_id=(
            None if promotion is None else _integer(promotion, "promotion_id")
        ),
        level=_integer(data["level"], "level"),
        move_speed=_number(data["move_speed"], "move_speed"),
        trained_modifiers=StatLine(
            *(
                _integer(trained[name], f"trained_modifiers.{name}")
                for name in StatLine.names()
            )
        ),
        rune_ids=tuple(
            _integer(value, "rune_ids entry")
            for value in _array(data["rune_ids"], "rune_ids")
        ),
        skill_ranks=_rank_mapping(data["skill_ranks"], "skill_ranks"),
        power_ranks=_rank_mapping(data["power_ranks"], "power_ranks"),
        equipment=tuple(
            _equipment(value, index)
            for index, value in enumerate(_array(data["equipment"], "equipment"))
        ),
    )


def _equipment(value: object, index: int) -> EquipmentSelection:
    name = f"equipment[{index}]"
    data = _mapping(value, name)
    _fields(data, {"slot_key", "item_id", "prefix", "suffix"}, name)
    return EquipmentSelection(
        slot_key=_string(data["slot_key"], f"{name}.slot_key"),
        item_id=_integer(data["item_id"], f"{name}.item_id"),
        prefix=_affix(data["prefix"], f"{name}.prefix"),
        suffix=_affix(data["suffix"], f"{name}.suffix"),
    )


def _affix(value: object, name: str) -> SelectedAffix | None:
    if value is None:
        return None
    data = _mapping(value, name)
    _fields(data, {"table_id", "action_id", "roll"}, name)
    roll = data["roll"]
    return SelectedAffix(
        table_id=_integer(data["table_id"], f"{name}.table_id"),
        action_id=_string(data["action_id"], f"{name}.action_id"),
        roll=None if roll is None else _number(roll, f"{name}.roll"),
    )


def _rank_mapping(value: object, name: str) -> tuple[tuple[str, int], ...]:
    data = _mapping(value, name)
    return tuple(
        sorted(
            (
                _string(key, f"{name} key"),
                _integer(rank, f"{name}.{key}"),
            )
            for key, rank in data.items()
        )
    )


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise LegalBuildCompileError(f"{name} must be an object")
    return value


def _array(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise LegalBuildCompileError(f"{name} must be an array")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegalBuildCompileError(f"{name} must be non-empty text")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LegalBuildCompileError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LegalBuildCompileError(f"{name} must be a number")
    return float(value)


def _fields(data: dict[str, Any], expected: set[str], name: str) -> None:
    missing = expected - data.keys()
    unknown = data.keys() - expected
    if missing:
        raise LegalBuildCompileError(
            f"{name} is missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise LegalBuildCompileError(
            f"{name} has unknown fields: {', '.join(sorted(unknown))}"
        )


__all__ = ["load_legal_build_genome", "load_legal_build_genome_text"]
