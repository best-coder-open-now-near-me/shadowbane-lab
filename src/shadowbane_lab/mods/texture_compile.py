"""Resolve public texture packages into one pristine-cache write plan."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from shadowbane_lab.client_extension.texture_cache import (
    TextureCacheError,
    TextureCachePlan,
    build_texture_cache_plan,
    sha256_file,
)
from shadowbane_lab.client_extension.texture_patch import (
    TexturePatchError,
    build_texture_patch_plan,
    load_texture_patch_manifest,
    texture_patch_manifest_sha256,
)
from shadowbane_lab.integrity import (
    is_reparse_point,
    resolve_within_root,
    validate_identifier,
)

from .package import AssetModPackage
from .texture_model import (
    TextureConflict,
    TextureProfileConflictError,
    TextureProfileError,
    TextureProfilePlan,
    TextureProvider,
)


def compile_texture_profile(
    source_cache_path: str | Path,
    packages: Sequence[AssetModPackage],
    *,
    content_build_id: str,
    profile_id: str,
    resolutions: Mapping[tuple[int, int], str] | None = None,
) -> TextureProfilePlan:
    """Resolve selected packages and compile one plan against the pristine cache."""

    validate_identifier(content_build_id, "content_build_id")
    validate_identifier(profile_id, "profile_id")
    source_cache = Path(source_cache_path).resolve()
    if (
        not source_cache.is_file()
        or source_cache.name.casefold() != "textures.cache"
    ):
        raise TextureProfileError(
            "source_cache_path must name an existing Textures.cache"
        )
    raw_packages = tuple(packages)
    if not raw_packages:
        raise TextureProfileError(
            "at least one asset-mod package is required"
        )
    if any(not isinstance(item, AssetModPackage) for item in raw_packages):
        raise TextureProfileError("packages contain an unsupported value")
    canonical_packages = tuple(
        sorted(raw_packages, key=lambda item: item.identity)
    )
    mod_ids = tuple(item.manifest.mod_id for item in canonical_packages)
    if len(mod_ids) != len(set(mod_ids)):
        raise TextureProfileError(
            "only one selected version of each mod is permitted"
        )
    source_digest = sha256_file(source_cache)
    providers: defaultdict[
        tuple[int, int],
        list[TextureProvider],
    ] = defaultdict(list)
    try:
        for package in canonical_packages:
            _collect_package_providers(
                source_cache,
                source_digest,
                package,
                content_build_id,
                providers,
            )
        selected = _resolve_providers(providers, resolutions or {})
        artifacts = {
            item.key: Path(item.artifact_path) for item in selected
        }
        cache_plan = build_texture_cache_plan(source_cache, artifacts)
        _cross_check_cache_plan(cache_plan, selected)
    except TextureProfileError:
        raise
    except (
        OSError,
        TextureCacheError,
        TexturePatchError,
        TypeError,
        ValueError,
    ) as exc:
        raise TextureProfileError(
            f"could not compile texture profile: {exc}"
        ) from exc
    if sha256_file(source_cache) != source_digest:
        raise TextureProfileError(
            "source cache changed while the profile was compiled"
        )
    return TextureProfilePlan(
        profile_id=profile_id,
        content_build_id=content_build_id,
        source_cache_path=str(source_cache),
        source_cache_sha256=source_digest,
        packages=canonical_packages,
        selected=selected,
        cache_plan=cache_plan,
    )


def _collect_package_providers(
    source_cache: Path,
    source_digest: str,
    package: AssetModPackage,
    content_build_id: str,
    providers: defaultdict[tuple[int, int], list[TextureProvider]],
) -> None:
    root = Path(package.root)
    for component in package.manifest.components:
        variant = component.variant_for(content_build_id)
        if variant is None:
            raise TextureProfileError(
                f"{package.identity}:{component.component_id} does not support "
                f"content build {content_build_id}"
            )
        patch_path = resolve_within_root(
            root,
            variant.texture_patch_manifest,
        )
        artifact_root = resolve_within_root(root, variant.artifact_root)
        if not patch_path.is_file():
            raise TextureProfileError(
                f"texture patch manifest does not exist: {patch_path}"
            )
        if not artifact_root.is_dir() or is_reparse_point(artifact_root):
            raise TextureProfileError(
                f"texture artifact root is not a directory: {artifact_root}"
            )
        patch_manifest = load_texture_patch_manifest(patch_path)
        if patch_manifest.source_cache_sha256 != source_digest:
            raise TextureProfileError(
                f"{package.identity}:{component.component_id} targets "
                "a different source cache"
            )
        patch_plan = build_texture_patch_plan(
            source_cache,
            patch_manifest,
            artifact_root,
        )
        patch_digest = texture_patch_manifest_sha256(patch_manifest)
        provider_id = (
            f"{package.manifest.mod_id}:{component.component_id}"
        )
        for write in patch_plan.writes:
            replacement = write.replacement
            artifact_path = (
                artifact_root / replacement.artifact_file_name
            )
            relative = artifact_path.relative_to(root).as_posix()
            providers[replacement.key].append(
                TextureProvider(
                    provider_id=provider_id,
                    mod_id=package.manifest.mod_id,
                    mod_version=package.manifest.version,
                    component_id=component.component_id,
                    patch_manifest_sha256=patch_digest,
                    group_id=replacement.group_id,
                    resource_id=replacement.resource_id,
                    source_payload_sha256=(
                        replacement.source_payload_sha256
                    ),
                    result_payload_sha256=(
                        replacement.result_payload_sha256
                    ),
                    artifact_sha256=replacement.artifact_sha256,
                    artifact_path=str(artifact_path),
                    artifact_relative_path=relative,
                    width=replacement.width,
                    height=replacement.height,
                    channels=replacement.depth,
                )
            )


def _resolve_providers(
    providers: Mapping[
        tuple[int, int],
        Sequence[TextureProvider],
    ],
    resolutions: Mapping[tuple[int, int], str],
) -> tuple[TextureProvider, ...]:
    normalized_resolutions: dict[tuple[int, int], str] = {}
    for key, provider_id in resolutions.items():
        _validate_resource_key(key)
        validate_identifier(
            provider_id,
            "texture conflict provider_id",
        )
        normalized_resolutions[key] = provider_id
    selected: list[TextureProvider] = []
    conflicts: list[TextureConflict] = []
    used_resolutions: set[tuple[int, int]] = set()
    for key in sorted(providers):
        candidates = tuple(
            sorted(
                providers[key],
                key=lambda item: (
                    item.provider_id,
                    item.mod_version,
                    item.patch_manifest_sha256,
                ),
            )
        )
        signatures = {
            item.result_signature for item in candidates
        }
        if len(signatures) == 1:
            selected.append(candidates[0])
            continue
        requested = normalized_resolutions.get(key)
        if requested is None:
            conflicts.append(
                TextureConflict(key[0], key[1], candidates)
            )
            continue
        matches = tuple(
            item
            for item in candidates
            if item.provider_id == requested
        )
        if len(matches) != 1:
            raise TextureProfileError(
                f"resolution for {key[0]}:{key[1]} does not name "
                "exactly one provider"
            )
        selected.append(matches[0])
        used_resolutions.add(key)
    if conflicts:
        raise TextureProfileConflictError(conflicts)
    unused = sorted(
        normalized_resolutions.keys() - used_resolutions
    )
    if unused:
        text = ", ".join(
            f"{group}:{resource}" for group, resource in unused
        )
        raise TextureProfileError(
            f"texture conflict resolutions were not used: {text}"
        )
    if not selected:
        raise TextureProfileError(
            "selected packages provide no texture resources"
        )
    return tuple(selected)


def _cross_check_cache_plan(
    cache_plan: TextureCachePlan,
    selected: Sequence[TextureProvider],
) -> None:
    expected = {item.key: item for item in selected}
    if cache_plan.targeted_keys != frozenset(expected):
        raise TextureProfileError(
            "combined cache plan targets differ from selected resources"
        )
    for write in cache_plan.writes:
        provider = expected[write.key]
        if (
            write.source_payload_sha256
            != provider.source_payload_sha256
            or write.result_payload_sha256
            != provider.result_payload_sha256
            or write.artifact_sha256 != provider.artifact_sha256
            or (write.width, write.height, write.channels)
            != (provider.width, provider.height, provider.channels)
        ):
            raise TextureProfileError(
                f"combined cache plan differs for "
                f"{write.group_id}:{write.resource_id}"
            )


def _validate_resource_key(key: object) -> None:
    if (
        not isinstance(key, tuple)
        or len(key) != 2
        or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in key
        )
        or any(item < 0 or item > 0xFFFFFFFF for item in key)
    ):
        raise TextureProfileError(
            "texture conflict keys must be unsigned integer pairs"
        )


__all__ = ["compile_texture_profile"]
