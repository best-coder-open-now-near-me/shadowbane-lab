"""Strict loader for the bundled WonderBane progression slice."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from shadowbane_lab.progression.model import (
    IdentityProfile,
    ProcEffectProfile,
    ProgressionLimits,
    ProgressionProfile,
    RuneKind,
    RuneProfile,
    SourceReference,
    StatLine,
    TrainingTarget,
    WeaponProfile,
)


class ProgressionProfileLoadError(ValueError):
    """Raised when a progression profile is structurally invalid."""


def load_wonderbane_irekei_proc_profile() -> ProgressionProfile:
    resource = files("shadowbane_lab.progression").joinpath("data/wonderbane_irekei_proc_v1.json")
    try:
        data = json.loads(resource.read_text(encoding="utf-8"))
        return _profile(_mapping(data, "root"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProgressionProfileLoadError(f"invalid bundled progression profile: {exc}") from exc


def _profile(data: dict[str, Any]) -> ProgressionProfile:
    if _integer(data, "schema_version") != 1:
        raise ValueError("unsupported progression schema version")
    identity_data = _mapping(data.get("identity"), "identity")
    limits_data = _mapping(data.get("limits"), "limits")
    return ProgressionProfile(
        profile_id=_string(data, "profile_id"),
        retrieved_on=_string(data, "retrieved_on"),
        sources=tuple(_source(item) for item in _mappings(data, "sources")),
        identity=IdentityProfile(
            race=_string(identity_data, "race"),
            base_class=_string(identity_data, "base_class"),
            profession=_string(identity_data, "profession"),
            race_start=_stats(identity_data, "race_start"),
            race_caps=_stats(identity_data, "race_caps"),
            creation_pool=_integer(identity_data, "creation_pool"),
            race_resource_bonuses=_triple(identity_data, "race_resource_bonuses"),
            base_modifiers=_stats(identity_data, "base_modifiers"),
            base_resource_factors=_triple(identity_data, "base_resource_factors"),
            profession_resource_factors=_triple(identity_data, "profession_resource_factors"),
            boon=_integer(identity_data, "boon"),
        ),
        limits=ProgressionLimits(
            maximum_level=_integer(limits_data, "maximum_level"),
            maximum_runes=_integer(limits_data, "maximum_runes"),
            disciplines_below_70=_integer(limits_data, "disciplines_below_70"),
            disciplines_at_70=_integer(limits_data, "disciplines_at_70"),
        ),
        runes=tuple(_rune(item) for item in _mappings(data, "runes")),
        weapons=tuple(_weapon(item) for item in _mappings(data, "weapons")),
        proc_effects=tuple(_proc_effect(item) for item in _mappings(data, "proc_effects")),
        training_targets=tuple(
            TrainingTarget(
                key=_string(item, "key"),
                target=_integer(item, "target"),
                priority=_integer(item, "priority"),
                minimum_level=_integer(item, "minimum_level"),
            )
            for item in _mappings(data, "training_targets")
        ),
    )


def _source(data: dict[str, Any]) -> SourceReference:
    return SourceReference(
        source_id=_string(data, "source_id"),
        kind=_string(data, "kind"),
        uri=_string(data, "uri"),
        revision=_string(data, "revision"),
    )


def _rune(data: dict[str, Any]) -> RuneProfile:
    return RuneProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        kind=RuneKind(_string(data, "kind")),
        cost=_integer(data, "cost"),
        minimum_level=_integer(data, "minimum_level"),
        stat_grants=_stats(data, "stat_grants"),
        cap_grants=_stats(data, "cap_grants"),
        minimum_stats=_stats(data, "minimum_stats"),
        source_id=_string(data, "source_id"),
    )


def _weapon(data: dict[str, Any]) -> WeaponProfile:
    return WeaponProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        required_unarmed=_integer(data, "required_unarmed"),
        base_minimum_damage=_number(data, "base_minimum_damage"),
        base_maximum_damage=_number(data, "base_maximum_damage"),
        base_speed=_number(data, "base_speed"),
        source_id=_string(data, "source_id"),
    )


def _proc_effect(data: dict[str, Any]) -> ProcEffectProfile:
    focus_scaling = data.get("focus_scaling")
    if not isinstance(focus_scaling, bool):
        raise TypeError("focus_scaling must be a boolean")
    return ProcEffectProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        chance_per_successful_hit=_number(data, "chance_per_successful_hit"),
        base_minimum_damage=_number(data, "base_minimum_damage"),
        base_maximum_damage=_number(data, "base_maximum_damage"),
        focus_scaling=focus_scaling,
        source_id=_string(data, "source_id"),
    )


def _stats(data: dict[str, Any], key: str) -> StatLine:
    values = data.get(key)
    if not isinstance(values, list) or len(values) != 5:
        raise TypeError(f"{key} must be a five-integer array")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError(f"{key} must be a five-integer array")
    return StatLine.from_values(tuple(values))


def _triple(data: dict[str, Any], key: str) -> tuple[int, int, int]:
    values = data.get(key)
    if not isinstance(values, list) or len(values) != 3:
        raise TypeError(f"{key} must be a three-integer array")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError(f"{key} must be a three-integer array")
    return values[0], values[1], values[2]


def _mappings(data: dict[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    values = data.get(key)
    if not isinstance(values, list):
        raise TypeError(f"{key} must be an array")
    return tuple(_mapping(value, f"{key} item") for value in values)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} must be an object")
    return value


def _string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _integer(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _number(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a number")
    return float(value)
