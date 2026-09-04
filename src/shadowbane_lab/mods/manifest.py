"""Canonical public manifests for restart-oriented Shadowbane asset mods."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shadowbane_lab.integrity import (
    JsonBounds,
    canonical_json_sha256,
    load_strict_json,
    validate_identifier,
    validate_relative_path,
)

ASSET_MOD_MANIFEST_SCHEMA_VERSION = 1
ASSET_MOD_MANIFEST_FILE_NAME = "mod.json"
_TEXTURE_SET_KIND = "texture-set"
_RELAUNCH_ACTIVATION = "relaunch"
_MOD_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9.-]+)?\Z")
_MANIFEST_BOUNDS = JsonBounds(
    maximum_bytes=1024 * 1024,
    maximum_depth=16,
    maximum_nodes=20_000,
    maximum_string_length=16 * 1024,
)


class AssetModManifestError(ValueError):
    """Raised when a public asset-mod manifest is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class TextureSetVariant:
    """One build-specific compiled texture component."""

    content_build_id: str
    texture_patch_manifest: str
    artifact_root: str

    def __post_init__(self) -> None:
        validate_identifier(self.content_build_id, "content_build_id")
        validate_relative_path(
            self.texture_patch_manifest,
            "texture_patch_manifest",
        )
        validate_relative_path(self.artifact_root, "artifact_root")
        if not self.texture_patch_manifest.casefold().endswith(".json"):
            raise AssetModManifestError("texture_patch_manifest must name a JSON file")

    def as_dict(self) -> dict[str, object]:
        return {
            "content_build_id": self.content_build_id,
            "texture_patch_manifest": self.texture_patch_manifest,
            "artifact_root": self.artifact_root,
        }


@dataclass(frozen=True, slots=True)
class TextureSetComponent:
    """A restart-required texture set with one or more client-build variants."""

    component_id: str
    variants: tuple[TextureSetVariant, ...]
    kind: str = field(default=_TEXTURE_SET_KIND, init=False)
    activation: str = field(default=_RELAUNCH_ACTIVATION, init=False)

    def __post_init__(self) -> None:
        _canonical_identifier(self.component_id, "component_id")
        if not self.variants:
            raise AssetModManifestError(
                "texture-set components require at least one variant"
            )
        if any(not isinstance(item, TextureSetVariant) for item in self.variants):
            raise AssetModManifestError(
                "variants must contain TextureSetVariant values"
            )
        build_ids = tuple(item.content_build_id for item in self.variants)
        if len(build_ids) != len(set(build_ids)):
            raise AssetModManifestError(
                "texture-set variants contain duplicate content builds"
            )
        if tuple(sorted(self.variants, key=lambda item: item.content_build_id)) != self.variants:
            raise AssetModManifestError(
                "texture-set variants must use content-build order"
            )

    def variant_for(self, content_build_id: str) -> TextureSetVariant | None:
        return next(
            (
                item
                for item in self.variants
                if item.content_build_id == content_build_id
            ),
            None,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "kind": self.kind,
            "activation": self.activation,
            "variants": [item.as_dict() for item in self.variants],
        }


@dataclass(frozen=True, slots=True)
class AssetModManifest:
    """The stable user-facing identity and component inventory for one asset mod."""

    mod_id: str
    name: str
    version: str
    description: str
    components: tuple[TextureSetComponent, ...]
    schema_version: int = ASSET_MOD_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ASSET_MOD_MANIFEST_SCHEMA_VERSION:
            raise AssetModManifestError(
                "unsupported asset-mod manifest schema version"
            )
        _canonical_identifier(self.mod_id, "mod_id")
        _bounded_text(self.name, "name", maximum=128, allow_empty=False)
        _bounded_text(
            self.description,
            "description",
            maximum=4096,
            allow_empty=True,
        )
        if not isinstance(self.version, str) or _VERSION.fullmatch(self.version) is None:
            raise AssetModManifestError(
                "version must use canonical dotted version syntax"
            )
        if not self.components:
            raise AssetModManifestError(
                "asset mods require at least one component"
            )
        if any(not isinstance(item, TextureSetComponent) for item in self.components):
            raise AssetModManifestError(
                "components contain an unsupported value"
            )
        component_ids = tuple(item.component_id for item in self.components)
        if len(component_ids) != len(set(component_ids)):
            raise AssetModManifestError(
                "asset-mod components contain duplicate IDs"
            )
        if tuple(sorted(self.components, key=lambda item: item.component_id)) != self.components:
            raise AssetModManifestError(
                "asset-mod components must use component_id order"
            )

    @property
    def identity(self) -> str:
        return f"{self.mod_id}@{self.version}"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mod_id": self.mod_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "components": [item.as_dict() for item in self.components],
        }


def load_asset_mod_manifest(path: str | Path) -> AssetModManifest:
    manifest_path = Path(path)
    try:
        payload = load_strict_json(manifest_path, bounds=_MANIFEST_BOUNDS)
        return parse_asset_mod_manifest(payload)
    except AssetModManifestError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise AssetModManifestError(
            f"could not load asset-mod manifest {manifest_path}: {exc}"
        ) from exc


def parse_asset_mod_manifest(value: object) -> AssetModManifest:
    payload = _exact_object(
        value,
        {
            "schema_version",
            "mod_id",
            "name",
            "version",
            "description",
            "components",
        },
        "asset-mod manifest",
    )
    raw_components = payload["components"]
    if not isinstance(raw_components, list):
        raise AssetModManifestError("components must be an array")
    components: list[TextureSetComponent] = []
    for component_index, raw_component in enumerate(raw_components):
        component = _exact_object(
            raw_component,
            {"component_id", "kind", "activation", "variants"},
            f"components[{component_index}]",
        )
        if component["kind"] != _TEXTURE_SET_KIND:
            raise AssetModManifestError(
                "only texture-set components are supported in schema 1"
            )
        if component["activation"] != _RELAUNCH_ACTIVATION:
            raise AssetModManifestError(
                "texture-set components must require relaunch"
            )
        raw_variants = component["variants"]
        if not isinstance(raw_variants, list):
            raise AssetModManifestError("component variants must be an array")
        variants: list[TextureSetVariant] = []
        for variant_index, raw_variant in enumerate(raw_variants):
            variant = _exact_object(
                raw_variant,
                {
                    "content_build_id",
                    "texture_patch_manifest",
                    "artifact_root",
                },
                f"components[{component_index}].variants[{variant_index}]",
            )
            variants.append(
                TextureSetVariant(
                    content_build_id=variant["content_build_id"],  # type: ignore[arg-type]
                    texture_patch_manifest=(
                        variant["texture_patch_manifest"]  # type: ignore[arg-type]
                    ),
                    artifact_root=variant["artifact_root"],  # type: ignore[arg-type]
                )
            )
        components.append(
            TextureSetComponent(
                component_id=component["component_id"],  # type: ignore[arg-type]
                variants=tuple(variants),
            )
        )
    return AssetModManifest(
        schema_version=payload["schema_version"],  # type: ignore[arg-type]
        mod_id=payload["mod_id"],  # type: ignore[arg-type]
        name=payload["name"],  # type: ignore[arg-type]
        version=payload["version"],  # type: ignore[arg-type]
        description=payload["description"],  # type: ignore[arg-type]
        components=tuple(components),
    )


def asset_mod_manifest_sha256(manifest: AssetModManifest) -> str:
    if not isinstance(manifest, AssetModManifest):
        raise TypeError("manifest must be an AssetModManifest")
    return canonical_json_sha256(manifest.as_dict())


def _exact_object(
    value: object,
    expected: set[str],
    context: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) for key in value
    ):
        raise AssetModManifestError(f"{context} must be an object")
    if value.keys() != expected:
        raise AssetModManifestError(f"{context} fields differ from the schema")
    return value


def _canonical_identifier(value: object, field_name: str) -> str:
    validate_identifier(value, field_name)
    if not isinstance(value, str) or _MOD_ID.fullmatch(value) is None:
        raise AssetModManifestError(
            f"{field_name} must use lowercase letters, digits, dot, underscore, or hyphen"
        )
    return value


def _bounded_text(
    value: object,
    field_name: str,
    *,
    maximum: int,
    allow_empty: bool,
) -> str:
    if not isinstance(value, str) or len(value) > maximum or "\0" in value:
        raise AssetModManifestError(f"{field_name} is not bounded text")
    if not allow_empty and not value.strip():
        raise AssetModManifestError(f"{field_name} must not be empty")
    if value != value.strip():
        raise AssetModManifestError(
            f"{field_name} must not have surrounding whitespace"
        )
    return value


__all__ = [
    "ASSET_MOD_MANIFEST_FILE_NAME",
    "ASSET_MOD_MANIFEST_SCHEMA_VERSION",
    "AssetModManifest",
    "AssetModManifestError",
    "TextureSetComponent",
    "TextureSetVariant",
    "asset_mod_manifest_sha256",
    "load_asset_mod_manifest",
    "parse_asset_mod_manifest",
]
