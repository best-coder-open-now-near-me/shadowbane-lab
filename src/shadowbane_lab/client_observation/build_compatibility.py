"""Reviewed native-layout compatibility across exact WonderBane client builds."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

_REGISTRY_NAME = "wonderbane-native-layout-compatibility-v1.json"
_SHA256_LENGTH = 64


class NativeLayoutCompatibilityRegistryError(ValueError):
    """Raised when the bundled compatibility registry is malformed."""


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise NativeLayoutCompatibilityRegistryError(f"{field_name} must be text")
    digest = value.casefold()
    if len(digest) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise NativeLayoutCompatibilityRegistryError(
            f"{field_name} must be a 64-character hexadecimal digest"
        )
    return digest


@lru_cache(maxsize=1)
def _equivalence_classes() -> dict[str, tuple[str, frozenset[str]]]:
    resource = files("shadowbane_lab.client_observation.data").joinpath(_REGISTRY_NAME)
    try:
        payload: Any = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NativeLayoutCompatibilityRegistryError(
            "could not load the native-layout compatibility registry"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "families"}:
        raise NativeLayoutCompatibilityRegistryError(
            "native-layout compatibility registry has unexpected fields"
        )
    if payload["schema_version"] != 1:
        raise NativeLayoutCompatibilityRegistryError(
            "unsupported native-layout compatibility registry version"
        )
    families = payload["families"]
    if not isinstance(families, list) or not families:
        raise NativeLayoutCompatibilityRegistryError(
            "native-layout compatibility registry must contain families"
        )
    by_digest: dict[str, tuple[str, frozenset[str]]] = {}
    for index, family in enumerate(families):
        if not isinstance(family, dict):
            raise NativeLayoutCompatibilityRegistryError(f"families[{index}] must be an object")
        required = {
            "family_id",
            "canonical_executable_sha256",
            "compatible_executable_sha256s",
            "validation",
        }
        if set(family) != required:
            raise NativeLayoutCompatibilityRegistryError(f"families[{index}] has unexpected fields")
        family_id = family["family_id"]
        if not isinstance(family_id, str) or not family_id.strip():
            raise NativeLayoutCompatibilityRegistryError(
                f"families[{index}].family_id must be non-empty text"
            )
        canonical = _sha256(
            family["canonical_executable_sha256"],
            f"families[{index}].canonical_executable_sha256",
        )
        compatible = family["compatible_executable_sha256s"]
        if not isinstance(compatible, list):
            raise NativeLayoutCompatibilityRegistryError(
                f"families[{index}].compatible_executable_sha256s must be a list"
            )
        digests = frozenset(
            [canonical]
            + [
                _sha256(value, f"families[{index}].compatible_executable_sha256s")
                for value in compatible
            ]
        )
        if len(digests) != len(compatible) + 1:
            raise NativeLayoutCompatibilityRegistryError(
                f"families[{index}] contains duplicate executable digests"
            )
        validation = family["validation"]
        if not isinstance(validation, dict) or not validation:
            raise NativeLayoutCompatibilityRegistryError(
                f"families[{index}].validation must be a non-empty object"
            )
        for digest in digests:
            if digest in by_digest:
                raise NativeLayoutCompatibilityRegistryError(
                    "an executable digest belongs to multiple native-layout families"
                )
            by_digest[digest] = (canonical, digests)
    return by_digest


def native_layout_is_compatible(
    calibrated_executable_sha256: str,
    observed_executable_sha256: str,
) -> bool:
    """Return whether two reviewed builds share the calibrated native layout."""

    calibrated = _sha256(calibrated_executable_sha256, "calibrated_executable_sha256")
    observed = _sha256(observed_executable_sha256, "observed_executable_sha256")
    if calibrated == observed:
        return True
    family = _equivalence_classes().get(calibrated)
    return family is not None and observed in family[1]


def canonical_native_layout_sha256(executable_sha256: str) -> str:
    """Return the canonical calibrated digest for a reviewed layout family."""

    digest = _sha256(executable_sha256, "executable_sha256")
    family = _equivalence_classes().get(digest)
    return digest if family is None else family[0]


__all__ = [
    "NativeLayoutCompatibilityRegistryError",
    "canonical_native_layout_sha256",
    "native_layout_is_compatible",
]
