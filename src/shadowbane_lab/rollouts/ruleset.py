"""Strict assembly of the source-pinned WonderBane guide-duel ruleset."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any, cast

from shadowbane_lab.rulesets import CompiledRuleset, RulesetLoadError, load_ruleset_text

_BASE_RESOURCE = "data/shadowbane_vertical_slice_v1.json"
_EXTENSION_RESOURCES = (
    "data/assassin_warlock_progression_v1.json",
    "data/assassin_shadow_mantle_v1.json",
    "data/wonderbane_sundancer_deflock_v1.json",
    "data/wonderbane_elf_druid_v1.json",
)
_PROMOTED_BASE_ACTIONS = frozenset({"shadowbane.assassin.shadow_mantle"})


def load_wonderbane_guide_duel_ruleset(
    *, rank_overrides: Mapping[str, int] | None = None
) -> CompiledRuleset:
    """Compile the base slice plus every reviewed guide-duel extension."""

    base = _load_json(_BASE_RESOURCE)
    merged = dict(base)
    merged_sources = list(_object_array(base, "sources"))
    known_source_ids = {_string(item, "source_id") for item in merged_sources}
    merged_actions = list(_object_array(base, "actions"))
    known_keys = {_string(item, "action_key") for item in merged_actions}
    current_ruleset_id = _string(base, "ruleset_id")

    for resource_name in _EXTENSION_RESOURCES:
        extension = _load_json(resource_name)
        if _integer(extension, "schema_version") != 1:
            raise RulesetLoadError("unsupported guide-duel extension version")
        if _string(extension, "base_ruleset_id") != current_ruleset_id:
            raise RulesetLoadError("guide-duel extension targets another base ruleset")

        additional_sources = tuple(
            cast(dict[str, Any], item)
            for item in extension.get("additional_sources", [])
            if isinstance(item, dict)
        )
        if len(additional_sources) != len(extension.get("additional_sources", [])):
            raise RulesetLoadError("additional_sources must contain objects")
        additional_source_ids = tuple(_string(item, "source_id") for item in additional_sources)
        if len(additional_source_ids) != len(set(additional_source_ids)):
            raise RulesetLoadError("extension source ids must be unique")
        source_overlap = known_source_ids & set(additional_source_ids)
        if source_overlap:
            raise RulesetLoadError(
                "extension duplicates existing sources: " + ", ".join(sorted(source_overlap))
            )
        merged_sources.extend(additional_sources)
        known_source_ids.update(additional_source_ids)

        additional_actions = _object_array(extension, "additional_actions")
        additional_keys = tuple(_string(item, "action_key") for item in additional_actions)
        if len(additional_keys) != len(set(additional_keys)):
            raise RulesetLoadError("guide-duel extension action keys must be unique")
        overlap = known_keys & set(additional_keys)
        unexpected_overlap = overlap - _PROMOTED_BASE_ACTIONS
        if unexpected_overlap:
            raise RulesetLoadError(
                f"guide-duel extension duplicates existing actions: "
                f"{', '.join(sorted(unexpected_overlap))}"
            )
        merged_actions.extend(
            item for item in additional_actions if _string(item, "action_key") not in overlap
        )
        known_keys.update(additional_keys)
        current_ruleset_id = _string(extension, "extension_id")

    merged["ruleset_id"] = current_ruleset_id
    merged["sources"] = merged_sources
    merged["actions"] = merged_actions
    return load_ruleset_text(json.dumps(merged), rank_overrides=rank_overrides)


def load_assassin_warlock_duel_ruleset(
    *, rank_overrides: Mapping[str, int] | None = None
) -> CompiledRuleset:
    """Compatibility alias for the now three-build guide-duel ruleset."""

    return load_wonderbane_guide_duel_ruleset(rank_overrides=rank_overrides)


def progression_milestones() -> tuple[int, ...]:
    """Return reviewed level breakpoints where either profession gains a power."""

    milestones: set[int] = set()
    for resource_name in _EXTENSION_RESOURCES:
        extension = _load_json(resource_name)
        values = extension.get("milestone_levels")
        if not isinstance(values, list) or not values:
            raise RulesetLoadError("milestone_levels must be a non-empty array")
        extension_milestones: list[int] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise RulesetLoadError("milestone levels must be positive integers")
            extension_milestones.append(value)
        if len(extension_milestones) != len(set(extension_milestones)):
            raise RulesetLoadError("milestone levels must be unique within an extension")
        milestones.update(extension_milestones)
    return tuple(sorted(milestones))


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
