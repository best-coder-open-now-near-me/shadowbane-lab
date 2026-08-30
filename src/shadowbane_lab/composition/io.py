"""Versioned JSON interchange for package catalogs and build blueprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shadowbane_lab.composition.model import (
    BodyDelta,
    BodyValues,
    BuildBlueprint,
    CompositionError,
    SourcePackage,
    SourcePackageCatalog,
    SourcePackageKind,
    canonical_json,
)


class CompositionFormatError(CompositionError):
    """Raised when a composition artifact does not match schema version 1."""


def load_source_package_catalog(path: str | Path) -> SourcePackageCatalog:
    return load_source_package_catalog_text(Path(path).read_text(encoding="utf-8"))


def load_source_package_catalog_text(text: str) -> SourcePackageCatalog:
    raw = _json_object(text, "source package catalog")
    _schema_version(raw, "source package catalog")
    packages_raw = raw.get("packages")
    if not isinstance(packages_raw, list):
        raise CompositionFormatError("packages must be an array")
    return SourcePackageCatalog(
        catalog_id=_required_string(raw, "catalog_id", "catalog"),
        packages=tuple(
            _parse_source_package(value, index)
            for index, value in enumerate(packages_raw)
        ),
        slot_limits=tuple(sorted(_integer_mapping(raw, "slot_limits", "catalog").items())),
    )


def dump_source_package_catalog(catalog: SourcePackageCatalog) -> str:
    if not isinstance(catalog, SourcePackageCatalog):
        raise CompositionFormatError("catalog must be a SourcePackageCatalog")
    return canonical_json(
        {
            "schema_version": 1,
            "catalog_id": catalog.catalog_id,
            "slot_limits": dict(sorted(catalog.slot_limits)),
            "packages": [
                _source_package_payload(package)
                for package in sorted(catalog.packages, key=lambda item: item.package_id)
            ],
        }
    )


def load_build_blueprint(path: str | Path) -> BuildBlueprint:
    return load_build_blueprint_text(Path(path).read_text(encoding="utf-8"))


def load_build_blueprint_text(text: str) -> BuildBlueprint:
    raw = _json_object(text, "build blueprint")
    _schema_version(raw, "build blueprint")
    body = _optional_object(raw, "base_body", "blueprint")
    direct = _optional_object(raw, "direct_grants", "blueprint")
    return BuildBlueprint(
        blueprint_id=_required_string(raw, "blueprint_id", "blueprint"),
        display_name=_required_string(raw, "display_name", "blueprint"),
        requested_package_ids=_string_array(
            raw,
            "requested_package_ids",
            "blueprint",
        ),
        base_body=BodyValues(
            health=_number(body, "health", 500.0, "base_body"),
            mana=_number(body, "mana", 300.0, "base_body"),
            stamina=_number(body, "stamina", 200.0, "base_body"),
            move_speed=_number(body, "move_speed", 15.0, "base_body"),
        ),
        direct_action_keys=_string_array(
            direct,
            "action_keys",
            "direct_grants",
        ),
        direct_tags=_string_array(direct, "tags", "direct_grants"),
        direct_persistent_trigger_keys=_string_array(
            direct,
            "persistent_trigger_keys",
            "direct_grants",
        ),
        base_scalars=tuple(sorted(_number_mapping(raw, "scalars", "blueprint").items())),
        attributes=tuple(sorted(_number_mapping(raw, "attributes", "blueprint").items())),
        training=tuple(sorted(_number_mapping(raw, "training", "blueprint").items())),
        metadata=tuple(sorted(_string_mapping(raw, "metadata", "blueprint").items())),
        notes=_string_array(raw, "notes", "blueprint"),
    )


def dump_build_blueprint(blueprint: BuildBlueprint) -> str:
    if not isinstance(blueprint, BuildBlueprint):
        raise CompositionFormatError("blueprint must be a BuildBlueprint")
    return canonical_json(
        {
            "schema_version": 1,
            "blueprint_id": blueprint.blueprint_id,
            "display_name": blueprint.display_name,
            "requested_package_ids": list(blueprint.requested_package_ids),
            "base_body": blueprint.base_body.as_dict(),
            "direct_grants": {
                "action_keys": list(blueprint.direct_action_keys),
                "tags": list(blueprint.direct_tags),
                "persistent_trigger_keys": list(
                    blueprint.direct_persistent_trigger_keys
                ),
            },
            "scalars": dict(blueprint.base_scalars),
            "attributes": dict(blueprint.attributes),
            "training": dict(blueprint.training),
            "metadata": dict(blueprint.metadata),
            "notes": list(blueprint.notes),
        }
    )


def _parse_source_package(raw: Any, index: int) -> SourcePackage:
    if not isinstance(raw, dict):
        raise CompositionFormatError(f"packages[{index}] must be an object")
    path = f"packages[{index}]"
    grants = _optional_object(raw, "grants", path)
    body = _optional_object(grants, "body_delta", f"{path}.grants")
    kind_raw = _required_string(raw, "kind", path)
    try:
        kind = SourcePackageKind(kind_raw)
    except ValueError as exc:
        raise CompositionFormatError(f"{path}.kind is unknown: {kind_raw}") from exc
    slot = raw.get("selection_slot")
    if slot is not None and (not isinstance(slot, str) or not slot.strip()):
        raise CompositionFormatError(f"{path}.selection_slot must be a string or null")
    return SourcePackage(
        package_id=_required_string(raw, "package_id", path),
        display_name=_required_string(raw, "display_name", path),
        kind=kind,
        selection_slot=slot,
        action_keys=_string_array(grants, "action_keys", f"{path}.grants"),
        tags=_string_array(grants, "tags", f"{path}.grants"),
        persistent_trigger_keys=_string_array(
            grants,
            "persistent_trigger_keys",
            f"{path}.grants",
        ),
        training_access_keys=_string_array(
            grants,
            "training_access_keys",
            f"{path}.grants",
        ),
        body_delta=BodyDelta(
            health=_number(body, "health", 0.0, f"{path}.grants.body_delta"),
            mana=_number(body, "mana", 0.0, f"{path}.grants.body_delta"),
            stamina=_number(body, "stamina", 0.0, f"{path}.grants.body_delta"),
            move_speed=_number(
                body,
                "move_speed",
                0.0,
                f"{path}.grants.body_delta",
            ),
        ),
        scalar_deltas=tuple(
            sorted(
                _number_mapping(
                    grants,
                    "scalars",
                    f"{path}.grants",
                ).items()
            )
        ),
        attribute_deltas=tuple(
            sorted(
                _number_mapping(
                    grants,
                    "attributes",
                    f"{path}.grants",
                ).items()
            )
        ),
        requires=_string_array(raw, "requires", path),
        conflicts=_string_array(raw, "conflicts", path),
        metadata=tuple(sorted(_string_mapping(raw, "metadata", path).items())),
    )


def _source_package_payload(package: SourcePackage) -> dict[str, object]:
    return {
        "package_id": package.package_id,
        "display_name": package.display_name,
        "kind": package.kind.value,
        "selection_slot": package.selection_slot,
        "grants": {
            "action_keys": list(package.action_keys),
            "tags": list(package.tags),
            "persistent_trigger_keys": list(package.persistent_trigger_keys),
            "training_access_keys": list(package.training_access_keys),
            "body_delta": package.body_delta.as_dict(),
            "scalars": dict(package.scalar_deltas),
            "attributes": dict(package.attribute_deltas),
        },
        "requires": list(package.requires),
        "conflicts": list(package.conflicts),
        "metadata": dict(package.metadata),
    }


def _json_object(text: str, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CompositionFormatError(f"{label} is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise CompositionFormatError(f"{label} must be an object")
    return raw


def _schema_version(raw: dict[str, Any], label: str) -> None:
    if raw.get("schema_version") != 1:
        raise CompositionFormatError(f"{label} must use schema_version 1")


def _required_string(raw: dict[str, Any], key: str, path: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CompositionFormatError(f"{path}.{key} must be a non-empty string")
    return value


def _optional_object(raw: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise CompositionFormatError(f"{path}.{key} must be an object")
    return value


def _string_array(raw: dict[str, Any], key: str, path: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CompositionFormatError(f"{path}.{key} must be an array of strings")
    if len(value) != len(set(value)):
        raise CompositionFormatError(f"{path}.{key} must not contain duplicates")
    return tuple(value)


def _number_mapping(raw: dict[str, Any], key: str, path: str) -> dict[str, float]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise CompositionFormatError(f"{path}.{key} must be an object")
    parsed: dict[str, float] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not item_key.strip():
            raise CompositionFormatError(f"{path}.{key} keys must be non-empty strings")
        if isinstance(item_value, bool) or not isinstance(item_value, (int, float)):
            raise CompositionFormatError(f"{path}.{key}.{item_key} must be numeric")
        parsed[item_key] = float(item_value)
    return parsed


def _integer_mapping(raw: dict[str, Any], key: str, path: str) -> dict[str, int]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise CompositionFormatError(f"{path}.{key} must be an object")
    parsed: dict[str, int] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not item_key.strip():
            raise CompositionFormatError(f"{path}.{key} keys must be non-empty strings")
        if isinstance(item_value, bool) or not isinstance(item_value, int):
            raise CompositionFormatError(f"{path}.{key}.{item_key} must be an integer")
        parsed[item_key] = item_value
    return parsed


def _string_mapping(raw: dict[str, Any], key: str, path: str) -> dict[str, str]:
    value = raw.get(key, {})
    if not isinstance(value, dict) or any(
        not isinstance(item_key, str)
        or not item_key.strip()
        or not isinstance(item_value, str)
        or not item_value.strip()
        for item_key, item_value in value.items()
    ):
        raise CompositionFormatError(
            f"{path}.{key} must map non-empty strings to non-empty strings"
        )
    return dict(value)


def _number(
    raw: dict[str, Any],
    key: str,
    default: float,
    path: str,
) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompositionFormatError(f"{path}.{key} must be numeric")
    return float(value)
