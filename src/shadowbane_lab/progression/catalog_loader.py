"""Strict loader for versioned build-identity catalogs."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from shadowbane_lab.progression.catalog import (
    BaseClassProfile,
    CatalogVariantStatus,
    CharacterSex,
    CoverageEntry,
    CoverageStatus,
    DisciplineProfile,
    GameCatalog,
    ProfessionProfile,
    RaceProfile,
)
from shadowbane_lab.progression.model import SourceReference, StatLine

CATALOG_SCHEMA_VERSION = 1


class GameCatalogLoadError(ValueError):
    """Raised when catalog data cannot be loaded without guessing."""


def load_shadowbane_legacy_catalog() -> GameCatalog:
    resource = files("shadowbane_lab.progression").joinpath(
        "data/shadowbane_legacy_catalog_v1.json"
    )
    return load_game_catalog_text(resource.read_text(encoding="utf-8"))


def load_game_catalog(path: str | Path) -> GameCatalog:
    return load_game_catalog_text(Path(path).read_text(encoding="utf-8"))


def load_game_catalog_text(text: str) -> GameCatalog:
    try:
        raw = json.loads(text)
        data = _mapping(raw, "catalog")
        if _integer(data, "schema_version") != CATALOG_SCHEMA_VERSION:
            raise GameCatalogLoadError("unsupported game catalog schema version")
        return GameCatalog(
            catalog_id=_string(data, "catalog_id"),
            target_variant=_string(data, "target_variant"),
            variant_status=CatalogVariantStatus(_string(data, "variant_status")),
            retrieved_on=_string(data, "retrieved_on"),
            sources=tuple(_source(item) for item in _mappings(data, "sources")),
            coverage=tuple(_coverage(item) for item in _mappings(data, "coverage")),
            base_classes=tuple(
                _base_class(item) for item in _mappings(data, "base_classes")
            ),
            races=tuple(_race(item) for item in _mappings(data, "races")),
            professions=tuple(
                _profession(item) for item in _mappings(data, "professions")
            ),
            disciplines=tuple(
                _discipline(item) for item in _mappings(data, "disciplines")
            ),
        )
    except GameCatalogLoadError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GameCatalogLoadError(f"invalid game catalog: {exc}") from exc


def _source(data: dict[str, Any]) -> SourceReference:
    return SourceReference(
        source_id=_string(data, "source_id"),
        kind=_string(data, "kind"),
        uri=_string(data, "uri"),
        revision=_string(data, "revision"),
    )


def _coverage(data: dict[str, Any]) -> CoverageEntry:
    return CoverageEntry(
        domain=_string(data, "domain"),
        status=CoverageStatus(_string(data, "status")),
        note=_string(data, "note"),
    )


def _base_class(data: dict[str, Any]) -> BaseClassProfile:
    return BaseClassProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        source_id=_string(data, "source_id"),
    )


def _race(data: dict[str, Any]) -> RaceProfile:
    return RaceProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        creation_cost=_integer(data, "creation_cost"),
        starting_attributes=_stats(data, "starting_attributes"),
        maximum_attributes=_stats(data, "maximum_attributes"),
        allowed_base_class_keys=tuple(_strings(data, "allowed_base_class_keys")),
        racial_discipline_keys=tuple(_strings(data, "racial_discipline_keys")),
        allowed_sexes=tuple(
            CharacterSex(value) for value in _strings(data, "allowed_sexes")
        ),
        source_id=_string(data, "source_id"),
    )


def _profession(data: dict[str, Any]) -> ProfessionProfile:
    return ProfessionProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        promotion_level=_integer(data, "promotion_level"),
        allowed_base_class_keys=tuple(_strings(data, "allowed_base_class_keys")),
        allowed_race_keys=tuple(_strings(data, "allowed_race_keys")),
        allowed_sexes=tuple(
            CharacterSex(value) for value in _strings(data, "allowed_sexes")
        ),
        source_id=_string(data, "source_id"),
    )


def _discipline(data: dict[str, Any]) -> DisciplineProfile:
    return DisciplineProfile(
        key=_string(data, "key"),
        name=_string(data, "name"),
        racial_access_keys=tuple(_strings(data, "racial_access_keys")),
        source_id=_string(data, "source_id"),
    )


def _stats(data: dict[str, Any], key: str) -> StatLine:
    values = data.get(key)
    if not isinstance(values, list) or len(values) != 5:
        raise TypeError(f"{key} must be a five-integer array")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError(f"{key} must be a five-integer array")
    return StatLine.from_values(tuple(values))


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


def _strings(data: dict[str, Any], key: str) -> tuple[str, ...]:
    values = data.get(key)
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise TypeError(f"{key} must be a string array")
    return tuple(values)


def _integer(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value
