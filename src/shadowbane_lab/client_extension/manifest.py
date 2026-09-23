"""Strict, hash-pinned manifest for one reviewed client-extension patch."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PATCH_MANIFEST_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9.-]+)?\Z")
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_PATCH_SITES = 64
_MAX_SITE_BYTES = 16 * 1024
_MAX_SEARCH_RADIUS = 16 * 1024 * 1024


class PatchManifestError(ValueError):
    """Raised when a client-extension patch manifest is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class SourceExecutable:
    file_name: str
    sha256: str
    length: int
    machine: int
    pointer_size: int

    def __post_init__(self) -> None:
        _file_name(self.file_name, "source.file_name", suffix=".exe")
        _sha256(self.sha256, "source.sha256")
        _positive_integer(self.length, "source.length")
        _positive_integer(self.machine, "source.machine", maximum=0xFFFF)
        if self.pointer_size not in {4, 8}:
            raise PatchManifestError("source.pointer_size must be 4 or 8")

    def as_dict(self) -> dict[str, object]:
        return {
            "file_name": self.file_name,
            "sha256": self.sha256,
            "length": self.length,
            "machine": self.machine,
            "pointer_size": self.pointer_size,
        }


@dataclass(frozen=True, slots=True)
class ExtensionArtifact:
    file_name: str
    sha256: str
    version: str
    machine: int
    bootstrap_export: str

    def __post_init__(self) -> None:
        _file_name(self.file_name, "extension.file_name", suffix=".dll")
        _sha256(self.sha256, "extension.sha256")
        if not isinstance(self.version, str) or _VERSION.fullmatch(self.version) is None:
            raise PatchManifestError("extension.version is not canonical")
        _positive_integer(self.machine, "extension.machine", maximum=0xFFFF)
        if (
            not isinstance(self.bootstrap_export, str)
            or not self.bootstrap_export
            or len(self.bootstrap_export) > 128
            or not self.bootstrap_export.isascii()
            or not self.bootstrap_export.replace("_", "a").isalnum()
        ):
            raise PatchManifestError("extension.bootstrap_export is not a safe ASCII symbol")

    def as_dict(self) -> dict[str, object]:
        return {
            "file_name": self.file_name,
            "sha256": self.sha256,
            "version": self.version,
            "machine": self.machine,
            "bootstrap_export": self.bootstrap_export,
        }


@dataclass(frozen=True, slots=True)
class MaskedSignature:
    """One bounded byte signature where zero mask bits are wildcards."""

    value: bytes
    mask: bytes

    def __post_init__(self) -> None:
        if not self.value or len(self.value) > _MAX_SITE_BYTES:
            raise PatchManifestError("site signature length is outside supported bounds")
        if len(self.value) != len(self.mask):
            raise PatchManifestError("site signature value and mask lengths differ")
        if any(mask not in {0x00, 0xFF} for mask in self.mask):
            raise PatchManifestError("site signature mask bytes must be 00 or ff")
        if not any(self.mask):
            raise PatchManifestError("site signature cannot contain only wildcards")

    @property
    def length(self) -> int:
        return len(self.value)

    def matches(self, candidate: bytes) -> bool:
        return len(candidate) == len(self.value) and all(
            mask == 0 or actual == expected
            for actual, expected, mask in zip(candidate, self.value, self.mask, strict=True)
        )

    def as_text(self) -> str:
        return " ".join(
            "??" if mask == 0 else f"{value:02X}"
            for value, mask in zip(self.value, self.mask, strict=True)
        )


@dataclass(frozen=True, slots=True)
class PatchSite:
    site_id: str
    section: str
    reviewed_rva: int
    expected_original: bytes
    replacement: bytes
    signature: MaskedSignature
    signature_site_offset: int
    search_radius: int

    def __post_init__(self) -> None:
        _identifier(self.site_id, "site_id")
        if (
            not isinstance(self.section, str)
            or not self.section
            or not self.section.isascii()
            or len(self.section) > 8
        ):
            raise PatchManifestError("site.section must be a non-empty ASCII PE section name")
        _non_negative_integer(self.reviewed_rva, "site.reviewed_rva", maximum=0xFFFFFFFF)
        if not self.expected_original or len(self.expected_original) > _MAX_SITE_BYTES:
            raise PatchManifestError("site expected bytes length is outside supported bounds")
        if len(self.expected_original) != len(self.replacement):
            raise PatchManifestError("site replacement must preserve the reviewed byte length")
        if self.expected_original == self.replacement:
            raise PatchManifestError("site replacement must differ from expected original bytes")
        if not isinstance(self.signature, MaskedSignature):
            raise PatchManifestError("site.signature must be a MaskedSignature")
        if (
            isinstance(self.signature_site_offset, bool)
            or not isinstance(self.signature_site_offset, int)
            or abs(self.signature_site_offset) > _MAX_SEARCH_RADIUS
        ):
            raise PatchManifestError("site.signature_site_offset is outside supported bounds")
        signature_patch_start = self.signature_site_offset
        signature_patch_end = signature_patch_start + len(self.expected_original)
        overlap_start = max(0, signature_patch_start)
        overlap_end = min(self.signature.length, signature_patch_end)
        if overlap_start < overlap_end and any(
            self.signature.mask[index] for index in range(overlap_start, overlap_end)
        ):
            raise PatchManifestError(
                "site.signature must wildcard bytes that the patch replaces"
            )
        _non_negative_integer(
            self.search_radius,
            "site.search_radius",
            maximum=_MAX_SEARCH_RADIUS,
        )

    @property
    def length(self) -> int:
        return len(self.expected_original)

    def as_dict(self) -> dict[str, object]:
        return {
            "site_id": self.site_id,
            "section": self.section,
            "reviewed_rva": self.reviewed_rva,
            "expected_original_hex": self.expected_original.hex(),
            "replacement_hex": self.replacement.hex(),
            "signature": self.signature.as_text(),
            "signature_site_offset": self.signature_site_offset,
            "search_radius": self.search_radius,
        }


@dataclass(frozen=True, slots=True)
class PatchManifest:
    patch_id: str
    source: SourceExecutable
    patched_executable_sha256: str
    extension: ExtensionArtifact
    sites: tuple[PatchSite, ...]
    schema_version: int = PATCH_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PATCH_MANIFEST_SCHEMA_VERSION:
            raise PatchManifestError("unsupported patch manifest schema version")
        _identifier(self.patch_id, "patch_id")
        if not isinstance(self.source, SourceExecutable):
            raise PatchManifestError("source must be SourceExecutable")
        _sha256(self.patched_executable_sha256, "patched_executable_sha256")
        if self.patched_executable_sha256 == self.source.sha256:
            raise PatchManifestError("patched executable hash must differ from source")
        if not isinstance(self.extension, ExtensionArtifact):
            raise PatchManifestError("extension must be ExtensionArtifact")
        if self.extension.machine != self.source.machine:
            raise PatchManifestError("extension and source executable machines must match")
        if not self.sites or len(self.sites) > _MAX_PATCH_SITES:
            raise PatchManifestError("patch site count is outside supported bounds")
        if len({site.site_id for site in self.sites}) != len(self.sites):
            raise PatchManifestError("patch manifest contains duplicate site IDs")
        if tuple(sorted(self.sites, key=lambda site: site.site_id)) != self.sites:
            raise PatchManifestError("patch sites must use canonical site_id order")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "patch_id": self.patch_id,
            "source": self.source.as_dict(),
            "patched_executable_sha256": self.patched_executable_sha256,
            "extension": self.extension.as_dict(),
            "sites": [site.as_dict() for site in self.sites],
        }


def load_patch_manifest(path: str | Path) -> PatchManifest:
    manifest_path = Path(path)
    try:
        data = manifest_path.read_bytes()
    except OSError as exc:
        raise PatchManifestError(f"could not read patch manifest: {manifest_path}") from exc
    if len(data) > _MAX_MANIFEST_BYTES:
        raise PatchManifestError("patch manifest exceeds the byte limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PatchManifestError("patch manifest is not valid UTF-8") from exc
    return load_patch_manifest_text(text)


def load_patch_manifest_text(text: str) -> PatchManifest:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PatchManifestError("patch manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PatchManifestError("patch manifest must be a JSON object")
    return _parse_manifest(payload)


def parse_masked_signature(value: object) -> MaskedSignature:
    if not isinstance(value, str) or not value:
        raise PatchManifestError("site.signature must be a non-empty string")
    tokens = value.split(" ")
    if "" in tokens:
        raise PatchManifestError("site.signature must use single-space token separators")
    values = bytearray()
    masks = bytearray()
    for token in tokens:
        if token == "??":
            values.append(0)
            masks.append(0)
            continue
        if len(token) != 2 or token != token.upper():
            raise PatchManifestError("signature bytes must be uppercase two-digit hexadecimal")
        try:
            values.append(int(token, 16))
        except ValueError as exc:
            raise PatchManifestError("signature contains a non-hexadecimal token") from exc
        masks.append(0xFF)
    return MaskedSignature(bytes(values), bytes(masks))


def _parse_manifest(payload: dict[str, object]) -> PatchManifest:
    _fields(
        payload,
        required={
            "schema_version",
            "patch_id",
            "source",
            "patched_executable_sha256",
            "extension",
            "sites",
        },
        context="patch manifest",
    )
    if payload["schema_version"] != PATCH_MANIFEST_SCHEMA_VERSION:
        raise PatchManifestError("unsupported patch manifest schema version")
    source_payload = _object(payload["source"], "source")
    _fields(
        source_payload,
        required={"file_name", "sha256", "length", "machine", "pointer_size"},
        context="source",
    )
    extension_payload = _object(payload["extension"], "extension")
    _fields(
        extension_payload,
        required={"file_name", "sha256", "version", "machine", "bootstrap_export"},
        context="extension",
    )
    raw_sites = payload["sites"]
    if not isinstance(raw_sites, list):
        raise PatchManifestError("sites must be an array")
    sites = tuple(_parse_site(_object(item, "site")) for item in raw_sites)
    try:
        return PatchManifest(
            patch_id=payload["patch_id"],  # type: ignore[arg-type]
            source=SourceExecutable(
                file_name=source_payload["file_name"],  # type: ignore[arg-type]
                sha256=source_payload["sha256"],  # type: ignore[arg-type]
                length=source_payload["length"],  # type: ignore[arg-type]
                machine=source_payload["machine"],  # type: ignore[arg-type]
                pointer_size=source_payload["pointer_size"],  # type: ignore[arg-type]
            ),
            patched_executable_sha256=payload["patched_executable_sha256"],  # type: ignore[arg-type]
            extension=ExtensionArtifact(
                file_name=extension_payload["file_name"],  # type: ignore[arg-type]
                sha256=extension_payload["sha256"],  # type: ignore[arg-type]
                version=extension_payload["version"],  # type: ignore[arg-type]
                machine=extension_payload["machine"],  # type: ignore[arg-type]
                bootstrap_export=extension_payload["bootstrap_export"],  # type: ignore[arg-type]
            ),
            sites=sites,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, PatchManifestError):
            raise
        raise PatchManifestError(str(exc)) from exc


def _parse_site(payload: dict[str, object]) -> PatchSite:
    _fields(
        payload,
        required={
            "site_id",
            "section",
            "reviewed_rva",
            "expected_original_hex",
            "replacement_hex",
            "signature",
            "signature_site_offset",
            "search_radius",
        },
        context="site",
    )
    return PatchSite(
        site_id=payload["site_id"],  # type: ignore[arg-type]
        section=payload["section"],  # type: ignore[arg-type]
        reviewed_rva=payload["reviewed_rva"],  # type: ignore[arg-type]
        expected_original=_hex_bytes(payload["expected_original_hex"], "expected_original_hex"),
        replacement=_hex_bytes(payload["replacement_hex"], "replacement_hex"),
        signature=parse_masked_signature(payload["signature"]),
        signature_site_offset=payload["signature_site_offset"],  # type: ignore[arg-type]
        search_radius=payload["search_radius"],  # type: ignore[arg-type]
    )


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PatchManifestError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise PatchManifestError(f"non-standard JSON constant is forbidden: {value}")


def _fields(payload: dict[str, object], *, required: set[str], context: str) -> None:
    missing = required - payload.keys()
    unknown = payload.keys() - required
    if missing:
        raise PatchManifestError(f"{context} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise PatchManifestError(f"{context} has unknown fields: {', '.join(sorted(unknown))}")


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PatchManifestError(f"{context} must be an object")
    return value


def _identifier(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PatchManifestError(f"{field_name} is not a canonical identifier")


def _file_name(value: object, field_name: str, *, suffix: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or Path(value).name != value
        or "/" in value
        or "\\" in value
        or "\0" in value
        or not value.casefold().endswith(suffix)
    ):
        raise PatchManifestError(f"{field_name} must be a leaf {suffix} file name")


def _sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PatchManifestError(f"{field_name} must be lowercase hexadecimal SHA-256")


def _positive_integer(value: object, field_name: str, *, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PatchManifestError(f"{field_name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise PatchManifestError(f"{field_name} exceeds the supported bound")


def _non_negative_integer(
    value: object,
    field_name: str,
    *,
    maximum: int | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PatchManifestError(f"{field_name} must be a non-negative integer")
    if maximum is not None and value > maximum:
        raise PatchManifestError(f"{field_name} exceeds the supported bound")


def _hex_bytes(value: object, field_name: str) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or len(value) % 2
        or value != value.casefold()
        or len(value) > _MAX_SITE_BYTES * 2
    ):
        raise PatchManifestError(f"{field_name} must be bounded lowercase even-length hex")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise PatchManifestError(f"{field_name} contains non-hexadecimal characters") from exc


__all__ = [
    "PATCH_MANIFEST_SCHEMA_VERSION",
    "ExtensionArtifact",
    "MaskedSignature",
    "PatchManifest",
    "PatchManifestError",
    "PatchSite",
    "SourceExecutable",
    "load_patch_manifest",
    "load_patch_manifest_text",
    "parse_masked_signature",
]
