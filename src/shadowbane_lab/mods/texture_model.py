"""Immutable records for deterministic texture-profile compilation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.client_extension.texture_cache import TextureCachePlan
from shadowbane_lab.integrity import (
    canonical_json_sha256,
    validate_identifier,
    validate_relative_path,
    validate_sha256,
)

from .package import AssetModPackage

TEXTURE_PROFILE_SCHEMA_VERSION = 1
TEXTURE_PROFILE_RECEIPT_FILE_NAME = "texture-profile.json"


class TextureProfileError(RuntimeError):
    """Raised when selected texture mods cannot produce a trustworthy profile."""


class TextureProfileConflictError(TextureProfileError):
    """Raised when selected mods require different results for one resource."""

    def __init__(self, conflicts: Sequence[TextureConflict]) -> None:
        self.conflicts = tuple(conflicts)
        if not self.conflicts:
            raise ValueError(
                "texture conflict errors require at least one conflict"
            )
        summary = ", ".join(
            f"{item.group_id}:{item.resource_id}"
            for item in self.conflicts
        )
        super().__init__(
            f"texture profile has unresolved conflicts: {summary}"
        )


@dataclass(frozen=True, slots=True)
class TextureProvider:
    """One mod component's verified claim over a texture resource."""

    provider_id: str
    mod_id: str
    mod_version: str
    component_id: str
    patch_manifest_sha256: str
    group_id: int
    resource_id: int
    source_payload_sha256: str
    result_payload_sha256: str
    artifact_sha256: str
    artifact_path: str
    artifact_relative_path: str
    width: int
    height: int
    channels: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider_id, "provider_id"),
            (self.mod_id, "mod_id"),
            (self.component_id, "component_id"),
        ):
            validate_identifier(value, name)
        for value, name in (
            (self.patch_manifest_sha256, "patch_manifest_sha256"),
            (self.source_payload_sha256, "source_payload_sha256"),
            (self.result_payload_sha256, "result_payload_sha256"),
            (self.artifact_sha256, "artifact_sha256"),
        ):
            validate_sha256(value, name)
        for value, name in (
            (self.group_id, "group_id"),
            (self.resource_id, "resource_id"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an unsigned integer")
            if not 0 <= value <= 0xFFFFFFFF:
                raise ValueError(
                    f"{name} must fit an unsigned 32-bit integer"
                )
        if not isinstance(self.mod_version, str) or not self.mod_version:
            raise ValueError("mod_version must be non-empty text")
        if not Path(self.artifact_path).is_absolute():
            raise ValueError("artifact_path must be absolute")
        validate_relative_path(
            self.artifact_relative_path,
            "artifact_relative_path",
        )
        if (
            isinstance(self.width, bool)
            or isinstance(self.height, bool)
            or not isinstance(self.width, int)
            or not isinstance(self.height, int)
            or self.width <= 0
            or self.height <= 0
            or self.channels not in {1, 3, 4}
        ):
            raise ValueError(
                "texture dimensions or channel count are unsupported"
            )

    @property
    def key(self) -> tuple[int, int]:
        return self.group_id, self.resource_id

    @property
    def result_signature(self) -> tuple[object, ...]:
        return (
            self.source_payload_sha256,
            self.result_payload_sha256,
            self.width,
            self.height,
            self.channels,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "mod_id": self.mod_id,
            "mod_version": self.mod_version,
            "component_id": self.component_id,
            "patch_manifest_sha256": self.patch_manifest_sha256,
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "source_payload_sha256": self.source_payload_sha256,
            "result_payload_sha256": self.result_payload_sha256,
            "artifact_sha256": self.artifact_sha256,
            "artifact_relative_path": self.artifact_relative_path,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
        }


@dataclass(frozen=True, slots=True)
class TextureConflict:
    """All distinct providers competing for one cache resource."""

    group_id: int
    resource_id: int
    providers: tuple[TextureProvider, ...]

    def __post_init__(self) -> None:
        if len(self.providers) < 2:
            raise ValueError(
                "texture conflicts require at least two providers"
            )
        if any(
            not isinstance(item, TextureProvider) for item in self.providers
        ):
            raise ValueError(
                "texture conflicts contain an unsupported provider"
            )
        expected = (self.group_id, self.resource_id)
        if any(item.key != expected for item in self.providers):
            raise ValueError(
                "texture conflict providers target different resources"
            )
        if len({item.result_signature for item in self.providers}) < 2:
            raise ValueError("identical texture results are not a conflict")

    def as_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "providers": [item.as_dict() for item in self.providers],
        }


@dataclass(frozen=True, slots=True)
class TextureProfilePlan:
    """One combined write plan compiled from an exact pristine cache."""

    profile_id: str
    content_build_id: str
    source_cache_path: str
    source_cache_sha256: str
    packages: tuple[AssetModPackage, ...]
    selected: tuple[TextureProvider, ...]
    cache_plan: TextureCachePlan
    schema_version: int = TEXTURE_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TEXTURE_PROFILE_SCHEMA_VERSION:
            raise ValueError(
                "unsupported texture-profile schema version"
            )
        validate_identifier(self.profile_id, "profile_id")
        validate_identifier(self.content_build_id, "content_build_id")
        validate_sha256(self.source_cache_sha256, "source_cache_sha256")
        if not Path(self.source_cache_path).is_absolute():
            raise ValueError("source_cache_path must be absolute")
        if not self.packages or not self.selected:
            raise ValueError(
                "texture profiles require packages and selected resources"
            )
        if any(
            not isinstance(item, AssetModPackage) for item in self.packages
        ):
            raise ValueError(
                "texture-profile packages contain an unsupported value"
            )
        if any(
            not isinstance(item, TextureProvider) for item in self.selected
        ):
            raise ValueError(
                "selected texture resources contain an unsupported value"
            )
        if not isinstance(self.cache_plan, TextureCachePlan):
            raise ValueError("cache_plan must be a TextureCachePlan")
        if (
            tuple(sorted(self.packages, key=lambda item: item.identity))
            != self.packages
        ):
            raise ValueError(
                "texture-profile packages must use identity order"
            )
        if (
            tuple(sorted(self.selected, key=lambda item: item.key))
            != self.selected
        ):
            raise ValueError(
                "selected texture resources must use resource-key order"
            )
        if len({item.key for item in self.selected}) != len(self.selected):
            raise ValueError(
                "selected texture resources contain duplicate keys"
            )
        if self.cache_plan.source_cache_sha256 != self.source_cache_sha256:
            raise ValueError(
                "cache plan source digest differs from the texture profile"
            )
        if self.cache_plan.targeted_keys != self.targeted_keys:
            raise ValueError(
                "cache plan targets differ from the selected providers"
            )

    @property
    def targeted_keys(self) -> frozenset[tuple[int, int]]:
        return frozenset(item.key for item in self.selected)

    @property
    def profile_sha256(self) -> str:
        return canonical_json_sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "content_build_id": self.content_build_id,
            "source_cache_sha256": self.source_cache_sha256,
            "packages": [item.as_dict() for item in self.packages],
            "selected_resources": [
                item.as_dict() for item in self.selected
            ],
        }


__all__ = [
    "TEXTURE_PROFILE_RECEIPT_FILE_NAME",
    "TEXTURE_PROFILE_SCHEMA_VERSION",
    "TextureConflict",
    "TextureProfileConflictError",
    "TextureProfileError",
    "TextureProfilePlan",
    "TextureProvider",
]
