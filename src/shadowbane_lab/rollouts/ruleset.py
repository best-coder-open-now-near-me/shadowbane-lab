"""Strict assembly of the Assassin-versus-Warlock rollout ruleset."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any, cast

from shadowbane_lab.rulesets import CompiledRuleset, RulesetLoadError, load_ruleset_text

_BASE_RESOURCE = "data/shadowbane_vertical_slice_v1.json"
_EXTENSION_RESOURCE = "data/assassin_warlock_progression_v1.json"


def load_assassin_warlock_duel_ruleset(
    *, rank_overrides: Mapping[str, int] | None = None
) -> CompiledRuleset:
    """Compile the base slice plus the reviewed Assassin/Warlock duel extension."""

    base = _load_json(_BASE_RESOURCE)
    extension = _load_json(_EXTENSION_RESOURCE)
    if _integer(extension, "schema_version") != 1:
        raise RulesetLoadError("unsupported Assassin/Warlock extension version")
    base_ruleset_id = _string(base, "ruleset_id")
    if _string(extension, "base_ruleset_id") != base_ruleset_id:
        raise RulesetLoadError("Assassin/Warlock extension targets another base ruleset")

    base_actions = _object_array(base, "actions")
    additional_actions = _object_array(extension, "additional_actions")
    base_keys = {_string(item, "action_key") for item in base_actions}
    additional_keys = tuple(_string(item, "action_key") for item in additional_actions)
    if len(additional_keys) != len(set(additional_keys)):
        raise RulesetLoadError("Assassin/Warlock extension action keys must be unique")
    overlap = base_keys & set(additional_keys)
    if overlap:
        raise RulesetLoadError(
            f"Assassin/Warlock extension duplicates base actions: {', '.join(sorted(overlap))}"
        )

    merged = dict(base)
    merged["ruleset_id"] = _string(extension, "extension_id")
    merged["actions"] = [*base_actions, *additional_actions]
    return load_ruleset_text(json.dumps(merged), rank_overrides=rank_overrides)


def progression_milestones() -> tuple[int, ...]:
    """Return reviewed level breakpoints where either profession gains a power."""

    extension = _load_json(_EXTENSION_RESOURCE)
    values = extension.get("milestone_levels")
    if not isinstance(values, list) or not values:
        raise RulesetLoadError("milestone_levels must be a non-empty array")
    milestones: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RulesetLoadError("milestone levels must be positive integers")
        milestones.append(value)
    if len(milestones) != len(set(milestones)):
        raise RulesetLoadError("milestone levels must be unique")
    return tuple(milestones)


def _load_json(resource_name: str) -> dict[str, Any]:
    resource = files("shadowbane_lab.rulesets").joinpath(resource_name)
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RulesetLoadError(f"{resource_name} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RulesetLoadError(f"{resource_name} must contain an object")
    return cast(dict[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RulesetLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RulesetLoadError(f"{key} must be an integer")
    return value


def _object_array(data: Mapping[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = data.get(key)
    if not isinstance(value, list):
        raise RulesetLoadError(f"{key} must be an array")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RulesetLoadError(f"{key} must contain objects")
        result.append(cast(dict[str, Any], item))
    return tuple(result)
