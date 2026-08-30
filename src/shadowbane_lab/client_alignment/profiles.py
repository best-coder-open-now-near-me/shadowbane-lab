"""Inventory hash-pinned native profiles and their calibrated RVA anchors."""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from shadowbane_lab.client_alignment.model import CalibratedAnchor, ProfileInventory
from shadowbane_lab.client_observation.build_compatibility import native_layout_is_compatible

_MAX_PROFILE_BYTES = 1_048_576
_MAX_PROFILE_FILES = 512
_SHA256_LENGTH = 64


class ProfileInventoryError(ValueError):
    """Raised when a native profile cannot be inventoried safely."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileInventoryError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ProfileInventoryError(f"{field_name} must be text")
    digest = value.casefold()
    if len(digest) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ProfileInventoryError(f"{field_name} must be a SHA-256 digest")
    return digest


def _signature(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileInventoryError(f"{field_name} must be hexadecimal text")
    normalized = value.strip().replace(" ", "").casefold()
    if not normalized or len(normalized) % 2:
        raise ProfileInventoryError(f"{field_name} must contain complete bytes")
    if any(character not in "0123456789abcdef" for character in normalized):
        raise ProfileInventoryError(f"{field_name} must contain only hexadecimal digits")
    return normalized


def _reject_constant(value: str) -> None:
    raise ProfileInventoryError(f"non-standard JSON number: {value}")


def _load_json(resource: Traversable) -> Any:
    try:
        text = resource.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProfileInventoryError(f"could not read profile: {resource.name}") from exc
    if len(text.encode("utf-8")) > _MAX_PROFILE_BYTES:
        raise ProfileInventoryError(f"profile exceeds {_MAX_PROFILE_BYTES} bytes: {resource.name}")
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ProfileInventoryError(f"profile is not valid JSON: {resource.name}") from exc


def _child_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]" if parent else f"[{key}]"
    return f"{parent}.{key}" if parent else key


def _walk_rvas(value: Any, path: str = "") -> Iterator[tuple[str, int, str | None]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = _child_path(path, key)
            if key == "rva" or key.endswith("_rva"):
                if isinstance(child, bool) or not isinstance(child, int) or child < 0:
                    raise ProfileInventoryError(f"{child_path} must be a non-negative integer")
                if key == "rva":
                    signature_value = value.get("signature_hex")
                    signature_path = _child_path(path, "signature_hex")
                else:
                    signature_key = f"{key[:-4]}_signature_hex"
                    signature_value = value.get(signature_key)
                    signature_path = _child_path(path, signature_key)
                signature = _signature(signature_value, signature_path)
                yield child_path, child, signature
            yield from _walk_rvas(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_rvas(child, _child_path(path, index))


def _profile_resources(directory: str | Path | Traversable | None) -> tuple[Traversable, ...]:
    root: Traversable
    if directory is None:
        root = files("shadowbane_lab.client_observation.data")
    elif isinstance(directory, (str, Path)):
        root = Path(directory)
    else:
        root = directory
    try:
        resources = tuple(
            sorted(
                (
                    child
                    for child in root.iterdir()
                    if child.is_file() and child.name.casefold().endswith(".json")
                ),
                key=lambda resource: resource.name.casefold(),
            )
        )
    except OSError as exc:
        raise ProfileInventoryError(f"could not enumerate profile directory: {root}") from exc
    if len(resources) > _MAX_PROFILE_FILES:
        raise ProfileInventoryError(
            f"profile directory contains more than {_MAX_PROFILE_FILES} JSON files"
        )
    return resources


def inventory_native_profiles(
    reference_executable_sha256: str,
    *,
    directory: str | Path | Traversable | None = None,
) -> ProfileInventory:
    """Collect native profiles and calibrated RVAs applicable to *reference*.

    A profile is applicable when its exact executable digest matches the reference or the
    repository's reviewed compatibility registry places both digests in one native-layout family.
    """

    reference_digest = _sha256(reference_executable_sha256, "reference_executable_sha256")
    resources = _profile_resources(directory)
    native_profile_count = 0
    applicable_profile_count = 0
    anchors: list[CalibratedAnchor] = []

    for resource in resources:
        payload = _load_json(resource)
        if not isinstance(payload, dict):
            continue
        if "executable_sha256" not in payload or "profile_id" not in payload:
            continue
        native_profile_count += 1
        profile_id = payload["profile_id"]
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ProfileInventoryError(f"{resource.name}.profile_id must be non-empty text")
        executable_digest = _sha256(
            payload["executable_sha256"], f"{resource.name}.executable_sha256"
        )
        if not native_layout_is_compatible(executable_digest, reference_digest):
            continue
        applicable_profile_count += 1
        pointer_size = payload.get("pointer_size", 1)
        if isinstance(pointer_size, bool) or pointer_size not in {1, 2, 4, 8}:
            raise ProfileInventoryError(
                f"{resource.name}.pointer_size must be one of 1, 2, 4, or 8"
            )
        for field_path, rva, signature_hex in _walk_rvas(payload):
            anchors.append(
                CalibratedAnchor(
                    profile_id=profile_id,
                    profile_file=resource.name,
                    executable_sha256=executable_digest,
                    field_path=field_path,
                    rva_start=rva,
                    length=pointer_size if signature_hex is None else len(signature_hex) // 2,
                    signature_hex=signature_hex,
                )
            )

    anchors.sort(
        key=lambda anchor: (
            anchor.rva_start,
            anchor.profile_id.casefold(),
            anchor.profile_file.casefold(),
            anchor.field_path,
        )
    )
    return ProfileInventory(
        profile_files_scanned=len(resources),
        native_profile_count=native_profile_count,
        applicable_profile_count=applicable_profile_count,
        anchors=tuple(anchors),
    )


__all__ = ["ProfileInventoryError", "inventory_native_profiles"]
