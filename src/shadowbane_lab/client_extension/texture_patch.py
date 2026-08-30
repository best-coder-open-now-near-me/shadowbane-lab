"""Hash-pinned texture-cache overlays for unpublished client packages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from shadowbane_lab.world_data.cache import CacheArchive, CacheResourceEntry

TEXTURE_PATCH_SCHEMA_VERSION = 1
TEXTURE_PATCH_EVIDENCE_SCHEMA_VERSION = 1
_HEADER = struct.Struct("<IIII")
_DIRECTORY_ENTRY = struct.Struct("<IIIII")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_REPLACEMENTS = 256


class TexturePatchError(RuntimeError):
    """Raised when a texture overlay cannot be proven or applied exactly."""


@dataclass(frozen=True, slots=True)
class TextureReplacement:
    group_id: int
    resource_id: int
    artifact_file_name: str
    artifact_sha256: str
    source_payload_sha256: str
    result_payload_sha256: str
    width: int
    height: int
    depth: int

    def __post_init__(self) -> None:
        for value, name in ((self.group_id, "group_id"), (self.resource_id, "resource_id")):
            _unsigned_integer(value, name)
        _file_name(self.artifact_file_name, "artifact_file_name", suffix=".png")
        for value, name in (
            (self.artifact_sha256, "artifact_sha256"),
            (self.source_payload_sha256, "source_payload_sha256"),
            (self.result_payload_sha256, "result_payload_sha256"),
        ):
            _sha256(value, name)
        _positive_integer(self.width, "width")
        _positive_integer(self.height, "height")
        if self.depth not in {1, 3, 4}:
            raise ValueError("depth must be 1, 3, or 4")

    @property
    def key(self) -> tuple[int, int]:
        return self.group_id, self.resource_id

    def as_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "artifact_file_name": self.artifact_file_name,
            "artifact_sha256": self.artifact_sha256,
            "source_payload_sha256": self.source_payload_sha256,
            "result_payload_sha256": self.result_payload_sha256,
            "width": self.width,
            "height": self.height,
            "depth": self.depth,
        }


@dataclass(frozen=True, slots=True)
class TexturePatchManifest:
    patch_id: str
    cache_relative_path: str
    source_cache_sha256: str
    replacements: tuple[TextureReplacement, ...]
    schema_version: int = TEXTURE_PATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TEXTURE_PATCH_SCHEMA_VERSION:
            raise ValueError("unsupported texture-patch schema version")
        if not isinstance(self.patch_id, str) or _IDENTIFIER.fullmatch(self.patch_id) is None:
            raise ValueError("patch_id must be a canonical identifier")
        _relative_path(self.cache_relative_path)
        if PurePosixPath(self.cache_relative_path).name.casefold() != "textures.cache":
            raise ValueError("cache_relative_path must name Textures.cache")
        _sha256(self.source_cache_sha256, "source_cache_sha256")
        if not self.replacements or len(self.replacements) > _MAX_REPLACEMENTS:
            raise ValueError("replacement count is outside supported bounds")
        if any(not isinstance(item, TextureReplacement) for item in self.replacements):
            raise ValueError("replacements must contain TextureReplacement values")
        keys = tuple(item.key for item in self.replacements)
        if len(keys) != len(set(keys)):
            raise ValueError("texture patch contains duplicate resource keys")
        if tuple(sorted(self.replacements, key=lambda item: item.key)) != self.replacements:
            raise ValueError("texture replacements must use canonical resource-key order")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "patch_id": self.patch_id,
            "cache_relative_path": self.cache_relative_path,
            "source_cache_sha256": self.source_cache_sha256,
            "replacements": [item.as_dict() for item in self.replacements],
        }


@dataclass(frozen=True, slots=True)
class TexturePatchWrite:
    replacement: TextureReplacement
    entry_index: int
    original_data_offset: int
    original_stored_size: int
    result_payload: bytes
    result_stored: bytes
    append_required: bool

    def as_dict(self) -> dict[str, object]:
        return {
            **self.replacement.as_dict(),
            "entry_index": self.entry_index,
            "original_data_offset": self.original_data_offset,
            "original_stored_size": self.original_stored_size,
            "result_stored_size": len(self.result_stored),
            "storage": "append" if self.append_required else "in-place",
        }


@dataclass(frozen=True, slots=True)
class TexturePatchPlan:
    patch_id: str
    cache_relative_path: str
    source_cache_sha256: str
    writes: tuple[TexturePatchWrite, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "patch_id": self.patch_id,
            "cache_relative_path": self.cache_relative_path,
            "source_cache_sha256": self.source_cache_sha256,
            "writes": [item.as_dict() for item in self.writes],
        }


@dataclass(frozen=True, slots=True)
class TexturePatchEvidence:
    manifest_sha256: str
    result_cache_sha256: str
    result_cache_size: int
    plan: TexturePatchPlan
    schema_version: int = TEXTURE_PATCH_EVIDENCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "manifest_sha256": self.manifest_sha256,
            "result_cache_sha256": self.result_cache_sha256,
            "result_cache_size": self.result_cache_size,
            "plan": self.plan.as_dict(),
        }


def load_texture_patch_manifest(path: str | Path) -> TexturePatchManifest:
    manifest_path = Path(path)
    try:
        data = manifest_path.read_bytes()
    except OSError as exc:
        raise TexturePatchError(f"could not read texture-patch manifest: {manifest_path}") from exc
    if len(data) > _MAX_MANIFEST_BYTES:
        raise TexturePatchError("texture-patch manifest exceeds the byte limit")
    try:
        payload = json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TexturePatchError("texture-patch manifest is not valid JSON") from exc
    try:
        return parse_texture_patch_manifest(payload)
    except (TypeError, ValueError) as exc:
        raise TexturePatchError(f"invalid texture-patch manifest: {exc}") from exc


def parse_texture_patch_manifest(value: object) -> TexturePatchManifest:
    payload = _exact_object(
        value,
        {
            "schema_version",
            "patch_id",
            "cache_relative_path",
            "source_cache_sha256",
            "replacements",
        },
        "texture patch",
    )
    replacement_values = payload["replacements"]
    if not isinstance(replacement_values, list):
        raise ValueError("replacements must be an array")
    replacements = []
    for index, item in enumerate(replacement_values):
        record = _exact_object(
            item,
            {
                "group_id",
                "resource_id",
                "artifact_file_name",
                "artifact_sha256",
                "source_payload_sha256",
                "result_payload_sha256",
                "width",
                "height",
                "depth",
            },
            f"replacements[{index}]",
        )
        replacements.append(TextureReplacement(**record))  # type: ignore[arg-type]
    return TexturePatchManifest(
        schema_version=payload["schema_version"],  # type: ignore[arg-type]
        patch_id=payload["patch_id"],  # type: ignore[arg-type]
        cache_relative_path=payload["cache_relative_path"],  # type: ignore[arg-type]
        source_cache_sha256=payload["source_cache_sha256"],  # type: ignore[arg-type]
        replacements=tuple(replacements),
    )


def author_texture_patch_manifest(
    cache_path: str | Path,
    artifacts: dict[tuple[int, int], str | Path],
    *,
    patch_id: str,
    cache_relative_path: str = "cache/Textures.cache",
) -> TexturePatchManifest:
    cache = Path(cache_path).resolve()
    with CacheArchive(cache) as archive:
        entries_by_key = _entries_by_key(archive)
        replacements = []
        for key, artifact_value in sorted(artifacts.items()):
            entry = entries_by_key.get(key)
            if entry is None:
                raise TexturePatchError(f"cache has no texture resource {key[0]}:{key[1]}")
            source_payload = archive.read_resource(entry)
            artifact = Path(artifact_value).resolve()
            result_payload, width, height, depth = _encode_png(artifact, source_payload)
            replacements.append(
                TextureReplacement(
                    group_id=key[0],
                    resource_id=key[1],
                    artifact_file_name=artifact.name,
                    artifact_sha256=_sha256_file(artifact),
                    source_payload_sha256=_sha256_bytes(source_payload),
                    result_payload_sha256=_sha256_bytes(result_payload),
                    width=width,
                    height=height,
                    depth=depth,
                )
            )
    return TexturePatchManifest(
        patch_id=patch_id,
        cache_relative_path=cache_relative_path,
        source_cache_sha256=_sha256_file(cache),
        replacements=tuple(replacements),
    )


def build_texture_patch_plan(
    cache_path: str | Path,
    manifest: TexturePatchManifest,
    artifact_directory: str | Path,
) -> TexturePatchPlan:
    cache = Path(cache_path).resolve()
    artifacts = Path(artifact_directory).resolve()
    if _sha256_file(cache) != manifest.source_cache_sha256:
        raise TexturePatchError("texture cache SHA-256 differs from the reviewed manifest")
    writes = []
    with CacheArchive(cache) as archive:
        entries = _entries_by_key(archive)
        for replacement in manifest.replacements:
            entry = entries.get(replacement.key)
            if entry is None:
                key_text = f"{replacement.group_id}:{replacement.resource_id}"
                raise TexturePatchError(f"cache has no texture resource {key_text}")
            source_payload = archive.read_resource(entry)
            if _sha256_bytes(source_payload) != replacement.source_payload_sha256:
                raise TexturePatchError(
                    f"source payload differs for {replacement.group_id}:{replacement.resource_id}"
                )
            artifact = artifacts / replacement.artifact_file_name
            if not artifact.is_file() or _sha256_file(artifact) != replacement.artifact_sha256:
                raise TexturePatchError(
                    f"texture artifact differs from the manifest: {replacement.artifact_file_name}"
                )
            result_payload, width, height, depth = _encode_png(artifact, source_payload)
            if (width, height, depth) != (
                replacement.width,
                replacement.height,
                replacement.depth,
            ):
                raise TexturePatchError("texture dimensions or depth differ from the manifest")
            if _sha256_bytes(result_payload) != replacement.result_payload_sha256:
                raise TexturePatchError(
                    f"result payload differs for {replacement.group_id}:{replacement.resource_id}"
                )
            result_stored = (
                zlib.compress(result_payload, level=9) if entry.is_compressed else result_payload
            )
            writes.append(
                TexturePatchWrite(
                    replacement=replacement,
                    entry_index=entry.index,
                    original_data_offset=entry.data_offset,
                    original_stored_size=entry.stored_size,
                    result_payload=result_payload,
                    result_stored=result_stored,
                    append_required=len(result_stored) > entry.stored_size,
                )
            )
    return TexturePatchPlan(
        patch_id=manifest.patch_id,
        cache_relative_path=manifest.cache_relative_path,
        source_cache_sha256=manifest.source_cache_sha256,
        writes=tuple(writes),
    )


def apply_texture_patch_plan(cache_path: str | Path, plan: TexturePatchPlan) -> None:
    cache = Path(cache_path).resolve()
    if _sha256_file(cache) != plan.source_cache_sha256:
        raise TexturePatchError("texture cache changed after its patch plan was built")
    with cache.open("r+b") as stream:
        header_data = stream.read(_HEADER.size)
        if len(header_data) != _HEADER.size:
            raise TexturePatchError("texture cache header is truncated")
        resource_count, data_offset, file_size, marker = _HEADER.unpack(header_data)
        for write in plan.writes:
            target_offset = file_size if write.append_required else write.original_data_offset
            stream.seek(target_offset)
            stream.write(write.result_stored)
            if write.append_required:
                file_size += len(write.result_stored)
            stream.seek(_HEADER.size + write.entry_index * _DIRECTORY_ENTRY.size)
            stream.write(
                _DIRECTORY_ENTRY.pack(
                    write.replacement.group_id,
                    write.replacement.resource_id,
                    target_offset,
                    len(write.result_payload),
                    len(write.result_stored),
                )
            )
        stream.seek(0)
        stream.write(_HEADER.pack(resource_count, data_offset, file_size, marker))
        stream.truncate(file_size)
        stream.flush()
        os.fsync(stream.fileno())

    with CacheArchive(cache) as archive:
        entries = _entries_by_key(archive)
        for write in plan.writes:
            entry = entries[write.replacement.key]
            if _sha256_bytes(archive.read_resource(entry)) != (
                write.replacement.result_payload_sha256
            ):
                raise TexturePatchError(
                    f"post-write validation failed for {write.replacement.group_id}:"
                    f"{write.replacement.resource_id}"
                )


def build_texture_patch_evidence(
    manifest: TexturePatchManifest,
    plan: TexturePatchPlan,
    result_cache_path: str | Path,
) -> TexturePatchEvidence:
    cache = Path(result_cache_path)
    return TexturePatchEvidence(
        manifest_sha256=texture_patch_manifest_sha256(manifest),
        result_cache_sha256=_sha256_file(cache),
        result_cache_size=cache.stat().st_size,
        plan=plan,
    )


def texture_patch_manifest_sha256(manifest: TexturePatchManifest) -> str:
    data = json.dumps(
        manifest.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return _sha256_bytes(data)


def _encode_png(path: Path, source_payload: bytes) -> tuple[bytes, int, int, int]:
    if len(source_payload) < 26:
        raise TexturePatchError("texture payload is smaller than its 26-byte header")
    width, height, depth = struct.unpack_from("<III", source_payload, 0)
    if depth not in {1, 3, 4} or len(source_payload) != 26 + width * height * depth:
        raise TexturePatchError("texture payload dimensions are inconsistent")
    try:
        from PIL import Image
    except ImportError as exc:
        raise TexturePatchError("Pillow is required for PNG texture overlays") from exc
    with Image.open(path) as source:
        if source.size != (width, height):
            raise TexturePatchError(
                f"{path.name} is {source.width}x{source.height}; expected {width}x{height}"
            )
        mode = {1: "L", 3: "RGB", 4: "RGBA"}[depth]
        pixels = source.convert(mode).transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    return source_payload[:26] + pixels, width, height, depth


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TexturePatchError(f"duplicate texture-patch field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise TexturePatchError(f"forbidden texture-patch constant: {value}")


def _exact_object(value: object, expected: set[str], context: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object")
    missing = expected - value.keys()
    unknown = value.keys() - expected
    if missing or unknown:
        raise ValueError(f"{context} fields differ from the schema")
    return value


def _sha256(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.casefold()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be lowercase hexadecimal SHA-256")


def _file_name(value: object, name: str, *, suffix: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or "/" in value
        or "\\" in value
        or not value.casefold().endswith(suffix)
    ):
        raise ValueError(f"{name} must be a plain {suffix} file name")


def _relative_path(value: object) -> None:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("cache_relative_path must be canonical POSIX form")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("cache_relative_path must remain beneath the client root")


def _entries_by_key(archive: CacheArchive) -> dict[tuple[int, int], CacheResourceEntry]:
    result: dict[tuple[int, int], CacheResourceEntry] = {}
    for entry in archive.entries:
        key = entry.group_id, entry.resource_id
        if key in result:
            raise TexturePatchError(f"cache has ambiguous texture resource {key[0]}:{key[1]}")
        result[key] = entry
    return result


def _unsigned_integer(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} must be an unsigned 32-bit integer")


def _positive_integer(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


__all__ = [
    "TEXTURE_PATCH_EVIDENCE_SCHEMA_VERSION",
    "TEXTURE_PATCH_SCHEMA_VERSION",
    "TexturePatchError",
    "TexturePatchEvidence",
    "TexturePatchManifest",
    "TexturePatchPlan",
    "TexturePatchWrite",
    "TextureReplacement",
    "apply_texture_patch_plan",
    "author_texture_patch_manifest",
    "build_texture_patch_evidence",
    "build_texture_patch_plan",
    "load_texture_patch_manifest",
    "parse_texture_patch_manifest",
    "texture_patch_manifest_sha256",
]
