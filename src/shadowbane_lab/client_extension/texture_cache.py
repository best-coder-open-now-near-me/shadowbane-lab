"""Deterministic mutation primitives for WonderBane ``Textures.cache`` files.

This module owns the binary write contract used by both reviewed client packages and the
restart-oriented Texture Lab.  It deliberately separates planning from mutation: every plan
is bound to an exact cache digest and contains the bytes needed to verify each target before
and after writing.  Callers choose whether to apply a plan to a disposable copy, an atomic
candidate, or a directly backed-up cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
import zipfile
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.world_data.cache import CacheArchive, CacheResourceEntry

CACHE_HEADER = struct.Struct("<IIII")
CACHE_DIRECTORY_ENTRY = struct.Struct("<IIIII")
TEXTURE_HEADER_BYTES = 26
MAX_REPLACEMENTS = 256
RESOURCE_BACKUP_VERSION = 1


class TextureCacheError(RuntimeError):
    """Raised when a cache replacement cannot be planned or verified exactly."""


@dataclass(frozen=True, slots=True)
class TexturePayloadInfo:
    width: int
    height: int
    channels: int
    header: bytes

    @property
    def mode(self) -> str:
        return {1: "L", 3: "RGB", 4: "RGBA"}[self.channels]


@dataclass(frozen=True, slots=True)
class TextureCacheWrite:
    group_id: int
    resource_id: int
    entry_index: int
    original_data_offset: int
    original_raw_size: int
    original_stored_size: int
    original_stored: bytes
    source_payload_sha256: str
    artifact_path: str
    artifact_sha256: str
    result_payload: bytes
    result_payload_sha256: str
    result_stored: bytes
    width: int
    height: int
    channels: int
    append_required: bool

    @property
    def key(self) -> tuple[int, int]:
        return self.group_id, self.resource_id

    @property
    def directory_offset(self) -> int:
        return CACHE_HEADER.size + self.entry_index * CACHE_DIRECTORY_ENTRY.size

    def as_dict(self, *, include_path: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "entry_index": self.entry_index,
            "dimensions": [self.width, self.height],
            "channels": self.channels,
            "original_data_offset": self.original_data_offset,
            "original_raw_size": self.original_raw_size,
            "original_stored_size": self.original_stored_size,
            "result_stored_size": len(self.result_stored),
            "storage": "append" if self.append_required else "in-place",
            "source_payload_sha256": self.source_payload_sha256,
            "artifact_sha256": self.artifact_sha256,
            "result_payload_sha256": self.result_payload_sha256,
        }
        if include_path:
            value["artifact_path"] = self.artifact_path
        return value


@dataclass(frozen=True, slots=True)
class TextureCachePlan:
    source_cache_sha256: str
    source_cache_size: int
    resource_count: int
    writes: tuple[TextureCacheWrite, ...]

    @property
    def targeted_keys(self) -> frozenset[tuple[int, int]]:
        return frozenset(item.key for item in self.writes)

    def as_dict(self, *, include_paths: bool = True) -> dict[str, object]:
        return {
            "source_cache_sha256": self.source_cache_sha256,
            "source_cache_size": self.source_cache_size,
            "resource_count": self.resource_count,
            "writes": [item.as_dict(include_path=include_paths) for item in self.writes],
        }


@dataclass(frozen=True, slots=True)
class CacheResourceDigest:
    group_id: int
    resource_id: int
    payload_sha256: str
    raw_size: int
    stored_size: int

    @property
    def key(self) -> tuple[int, int]:
        return self.group_id, self.resource_id


@dataclass(frozen=True, slots=True)
class CacheValidation:
    cache_sha256: str
    cache_size: int
    resource_count: int
    data_offset: int
    marker: int
    resources: tuple[CacheResourceDigest, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "cache_sha256": self.cache_sha256,
            "cache_size": self.cache_size,
            "resource_count": self.resource_count,
            "data_offset": self.data_offset,
            "marker": self.marker,
            "resources": [
                {
                    "group_id": item.group_id,
                    "resource_id": item.resource_id,
                    "payload_sha256": item.payload_sha256,
                    "raw_size": item.raw_size,
                    "stored_size": item.stored_size,
                }
                for item in self.resources
            ],
        }


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    candidate = Path(path)
    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise TextureCacheError(f"could not hash file: {candidate}: {exc}") from exc
    return digest.hexdigest()


def parse_texture_payload(payload: bytes) -> TexturePayloadInfo:
    if len(payload) < TEXTURE_HEADER_BYTES:
        raise TextureCacheError("texture payload is smaller than its 26-byte header")
    width, height, channels = struct.unpack_from("<III", payload, 0)
    if width <= 0 or height <= 0:
        raise TextureCacheError("texture payload dimensions must be positive")
    if channels not in {1, 3, 4}:
        raise TextureCacheError(f"unsupported texture channel count {channels}")
    expected = TEXTURE_HEADER_BYTES + width * height * channels
    if len(payload) != expected:
        raise TextureCacheError(
            f"texture payload has {len(payload)} bytes; expected {expected}"
        )
    return TexturePayloadInfo(width, height, channels, payload[:TEXTURE_HEADER_BYTES])


def encode_png_payload(
    path: str | Path,
    source_payload: bytes,
) -> tuple[bytes, TexturePayloadInfo]:
    """Encode a same-sized PNG with the source texture header and channel contract."""

    info = parse_texture_payload(source_payload)
    artifact = Path(path).resolve()
    if not artifact.is_file():
        raise TextureCacheError(f"texture artifact does not exist: {artifact}")
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - packaging dependency failure
        raise TextureCacheError("Pillow is required for PNG texture overlays") from exc
    try:
        with Image.open(artifact) as source:
            source.load()
            if source.format != "PNG":
                raise TextureCacheError(f"texture artifact is not a PNG: {artifact.name}")
            if source.size != (info.width, info.height):
                raise TextureCacheError(
                    f"{artifact.name} is {source.width}x{source.height}; "
                    f"expected {info.width}x{info.height}"
                )
            pixels = (
                source.convert(info.mode)
                .transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                .tobytes()
            )
    except TextureCacheError:
        raise
    except OSError as exc:
        raise TextureCacheError(f"could not decode PNG {artifact}: {exc}") from exc
    return info.header + pixels, info


def entries_by_key(archive: CacheArchive) -> dict[tuple[int, int], CacheResourceEntry]:
    result: dict[tuple[int, int], CacheResourceEntry] = {}
    for entry in archive.entries:
        key = entry.group_id, entry.resource_id
        if key in result:
            raise TextureCacheError(
                f"cache has ambiguous texture resource {entry.group_id}:{entry.resource_id}"
            )
        result[key] = entry
    return result


def read_stored_bytes(path: str | Path, entry: CacheResourceEntry) -> bytes:
    cache = Path(path)
    try:
        with cache.open("rb") as stream:
            stream.seek(entry.data_offset)
            value = stream.read(entry.stored_size)
    except OSError as exc:
        raise TextureCacheError(f"could not read cache resource {entry.index}: {exc}") from exc
    if len(value) != entry.stored_size:
        raise TextureCacheError(f"cache resource {entry.index} is truncated")
    return value


def build_texture_cache_plan(
    cache_path: str | Path,
    artifacts: Mapping[tuple[int, int], str | Path],
) -> TextureCachePlan:
    """Plan deterministic replacement bytes for one exact cache and artifact mapping."""

    cache = Path(cache_path).resolve()
    if not cache.is_file():
        raise TextureCacheError(f"texture cache does not exist: {cache}")
    if not artifacts or len(artifacts) > MAX_REPLACEMENTS:
        raise TextureCacheError("replacement count is outside supported bounds")
    for key in artifacts:
        _validate_key(key)

    source_digest = sha256_file(cache)
    try:
        with CacheArchive(cache) as archive:
            indexed = entries_by_key(archive)
            writes: list[TextureCacheWrite] = []
            for key, artifact_value in sorted(artifacts.items()):
                entry = indexed.get(key)
                if entry is None:
                    raise TextureCacheError(
                        f"cache has no texture resource {key[0]}:{key[1]}"
                    )
                source_payload = archive.read_resource(entry)
                artifact = Path(artifact_value).resolve()
                result_payload, info = encode_png_payload(artifact, source_payload)
                result_stored = (
                    zlib.compress(result_payload, level=9)
                    if entry.is_compressed
                    else result_payload
                )
                writes.append(
                    TextureCacheWrite(
                        group_id=key[0],
                        resource_id=key[1],
                        entry_index=entry.index,
                        original_data_offset=entry.data_offset,
                        original_raw_size=entry.uncompressed_size,
                        original_stored_size=entry.stored_size,
                        original_stored=read_stored_bytes(cache, entry),
                        source_payload_sha256=sha256_bytes(source_payload),
                        artifact_path=str(artifact),
                        artifact_sha256=sha256_file(artifact),
                        result_payload=result_payload,
                        result_payload_sha256=sha256_bytes(result_payload),
                        result_stored=result_stored,
                        width=info.width,
                        height=info.height,
                        channels=info.channels,
                        append_required=len(result_stored) > entry.stored_size,
                    )
                )
            result = TextureCachePlan(
                source_cache_sha256=source_digest,
                source_cache_size=archive.header.file_size,
                resource_count=archive.header.resource_count,
                writes=tuple(writes),
            )
    except TextureCacheError:
        raise
    except (OSError, ValueError, zlib.error) as exc:
        raise TextureCacheError(f"could not plan texture cache replacements: {exc}") from exc
    if sha256_file(cache) != source_digest:
        raise TextureCacheError("texture cache changed while its replacement plan was built")
    return result


def apply_texture_cache_writes(
    cache_path: str | Path,
    *,
    source_cache_sha256: str,
    writes: Sequence[TextureCacheWrite],
) -> tuple[str, int]:
    """Apply a write set and verify the resulting target payloads."""

    cache = Path(cache_path).resolve()
    canonical = _validate_write_set(writes)
    if sha256_file(cache) != source_cache_sha256:
        raise TextureCacheError("texture cache changed after its replacement plan was built")
    try:
        with CacheArchive(cache) as archive:
            indexed = entries_by_key(archive)
            if archive.header.resource_count < len(canonical):
                raise TextureCacheError("texture cache plan has more writes than resources")
            for write in canonical:
                entry = indexed.get(write.key)
                if entry is None:
                    raise TextureCacheError(
                        f"cache has no texture resource {write.group_id}:{write.resource_id}"
                    )
                if (
                    entry.index != write.entry_index
                    or entry.data_offset != write.original_data_offset
                    or entry.uncompressed_size != write.original_raw_size
                    or entry.stored_size != write.original_stored_size
                ):
                    raise TextureCacheError(
                        f"cache directory changed for {write.group_id}:{write.resource_id}"
                    )
                if read_stored_bytes(cache, entry) != write.original_stored:
                    raise TextureCacheError(
                        f"stored source bytes changed for {write.group_id}:{write.resource_id}"
                    )
                if sha256_bytes(archive.read_resource(entry)) != write.source_payload_sha256:
                    raise TextureCacheError(
                        f"source payload changed for {write.group_id}:{write.resource_id}"
                    )
            header = archive.header

        with cache.open("r+b") as stream:
            file_size = header.file_size
            for write in canonical:
                target_offset = file_size if write.append_required else write.original_data_offset
                stream.seek(target_offset)
                stream.write(write.result_stored)
                if write.append_required:
                    file_size += len(write.result_stored)
                stream.seek(write.directory_offset)
                stream.write(
                    CACHE_DIRECTORY_ENTRY.pack(
                        write.group_id,
                        write.resource_id,
                        target_offset,
                        len(write.result_payload),
                        len(write.result_stored),
                    )
                )
            stream.seek(0)
            stream.write(
                CACHE_HEADER.pack(
                    header.resource_count,
                    header.data_offset,
                    file_size,
                    header.marker,
                )
            )
            stream.truncate(file_size)
            stream.flush()
            os.fsync(stream.fileno())

        with CacheArchive(cache) as archive:
            indexed = entries_by_key(archive)
            for write in canonical:
                actual = archive.read_resource(indexed[write.key])
                if sha256_bytes(actual) != write.result_payload_sha256:
                    raise TextureCacheError(
                        f"post-write validation failed for {write.group_id}:{write.resource_id}"
                    )
    except TextureCacheError:
        raise
    except (OSError, ValueError, zlib.error) as exc:
        raise TextureCacheError(f"could not apply texture cache replacements: {exc}") from exc
    return sha256_file(cache), cache.stat().st_size


def apply_texture_cache_plan(
    cache_path: str | Path,
    plan: TextureCachePlan,
) -> tuple[str, int]:
    return apply_texture_cache_writes(
        cache_path,
        source_cache_sha256=plan.source_cache_sha256,
        writes=plan.writes,
    )


def validate_cache(path: str | Path, *, inflate_all: bool = True) -> CacheValidation:
    """Parse a cache, reject ambiguous keys, and optionally hash every inflated payload."""

    cache = Path(path).resolve()
    try:
        with CacheArchive(cache) as archive:
            entries_by_key(archive)
            resources: list[CacheResourceDigest] = []
            if inflate_all:
                for entry in archive.entries:
                    payload = archive.read_resource(entry)
                    resources.append(
                        CacheResourceDigest(
                            group_id=entry.group_id,
                            resource_id=entry.resource_id,
                            payload_sha256=sha256_bytes(payload),
                            raw_size=entry.uncompressed_size,
                            stored_size=entry.stored_size,
                        )
                    )
            return CacheValidation(
                cache_sha256=sha256_file(cache),
                cache_size=archive.header.file_size,
                resource_count=archive.header.resource_count,
                data_offset=archive.header.data_offset,
                marker=archive.header.marker,
                resources=tuple(resources),
            )
    except TextureCacheError:
        raise
    except (OSError, ValueError, zlib.error) as exc:
        raise TextureCacheError(f"texture cache validation failed: {exc}") from exc


def compare_untargeted_payloads(
    baseline_path: str | Path,
    result_path: str | Path,
    targeted_keys: set[tuple[int, int]] | frozenset[tuple[int, int]],
) -> None:
    """Require all resources outside ``targeted_keys`` to remain byte-identical when inflated."""

    try:
        with CacheArchive(Path(baseline_path)) as baseline, CacheArchive(Path(result_path)) as result:
            baseline_entries = entries_by_key(baseline)
            result_entries = entries_by_key(result)
            if baseline_entries.keys() != result_entries.keys():
                raise TextureCacheError("result cache resource keys differ from the baseline")
            if (
                baseline.header.resource_count != result.header.resource_count
                or baseline.header.data_offset != result.header.data_offset
                or baseline.header.marker != result.header.marker
            ):
                raise TextureCacheError("result cache structural header differs from the baseline")
            for key in sorted(baseline_entries):
                if key in targeted_keys:
                    continue
                if baseline.read_resource(baseline_entries[key]) != result.read_resource(
                    result_entries[key]
                ):
                    raise TextureCacheError(
                        f"untargeted texture payload changed for {key[0]}:{key[1]}"
                    )
    except TextureCacheError:
        raise
    except (OSError, ValueError, zlib.error) as exc:
        raise TextureCacheError(f"could not compare texture caches: {exc}") from exc


def copy_file_exact(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    expected_sha256: str | None = None,
    replace: bool = False,
) -> str:
    """Copy one file through a flushed sibling temporary and verify its digest."""

    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()
    if not source.is_file():
        raise TextureCacheError(f"copy source does not exist: {source}")
    if destination.exists() and not replace:
        raise TextureCacheError(f"copy destination already exists: {destination}")
    source_digest = sha256_file(source)
    if expected_sha256 is not None and source_digest != expected_sha256:
        raise TextureCacheError("copy source SHA-256 differs from the expected value")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as input_stream, os.fdopen(descriptor, "wb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if sha256_file(temporary) != source_digest:
            raise TextureCacheError("copied file SHA-256 differs from its source")
        if destination.exists() and not replace:
            raise TextureCacheError(f"copy destination already exists: {destination}")
        os.replace(temporary, destination)
        if sha256_file(destination) != source_digest:
            raise TextureCacheError("published file SHA-256 differs after replacement")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return source_digest


def atomic_replace_exact(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    expected_sha256: str,
) -> str:
    """Publish verified source bytes as ``destination_path`` using a sibling temporary."""

    return copy_file_exact(
        source_path,
        destination_path,
        expected_sha256=expected_sha256,
        replace=True,
    )


def create_resource_backup(
    cache_path: str | Path,
    backup_path: str | Path,
    plan: TextureCachePlan,
) -> Path:
    """Create a compact, exact, create-only rollback archive for one write plan."""

    cache = Path(cache_path).resolve()
    backup = Path(backup_path).resolve()
    if backup.exists():
        raise TextureCacheError(f"backup already exists: {backup}")
    if sha256_file(cache) != plan.source_cache_sha256:
        raise TextureCacheError("texture cache differs from the planned backup source")
    canonical = _validate_write_set(plan.writes)
    try:
        with cache.open("rb") as stream:
            original_header = stream.read(CACHE_HEADER.size)
            records: list[tuple[TextureCacheWrite, bytes]] = []
            for write in canonical:
                stream.seek(write.directory_offset)
                directory = stream.read(CACHE_DIRECTORY_ENTRY.size)
                if len(directory) != CACHE_DIRECTORY_ENTRY.size:
                    raise TextureCacheError("texture cache directory record is truncated")
                records.append((write, directory))
        manifest = {
            "format": "wonderbane-texture-cache-backup",
            "version": RESOURCE_BACKUP_VERSION,
            "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "cache": str(cache),
            "source_cache_sha256": plan.source_cache_sha256,
            "original_file_size": plan.source_cache_size,
            "original_header_hex": original_header.hex(),
            "resources": [
                {
                    "index": write.entry_index,
                    "group_id": write.group_id,
                    "resource_id": write.resource_id,
                    "data_offset": write.original_data_offset,
                    "raw_size": write.original_raw_size,
                    "stored_size": write.original_stored_size,
                    "directory_offset": write.directory_offset,
                    "directory_record_hex": directory.hex(),
                    "stored_blob": f"resources/{write.entry_index}.bin",
                    "stored_sha256": sha256_bytes(write.original_stored),
                }
                for write, directory in records
            ],
        }
        backup.parent.mkdir(parents=True, exist_ok=True)
        temporary = backup.with_name(f".{backup.name}.{os.getpid()}.tmp")
        try:
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
                for write, _ in records:
                    archive.writestr(f"resources/{write.entry_index}.bin", write.original_stored)
            os.replace(temporary, backup)
        finally:
            temporary.unlink(missing_ok=True)
    except TextureCacheError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise TextureCacheError(f"could not create texture backup: {exc}") from exc
    return backup


def restore_resource_backup(
    backup_path: str | Path,
    cache_override: str | Path | None = None,
) -> Path:
    """Restore exact original directory records, stored bytes, header, and file length."""

    backup = Path(backup_path).resolve()
    try:
        with zipfile.ZipFile(backup, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "wonderbane-texture-cache-backup":
                raise TextureCacheError("file is not a WonderBane texture-cache backup")
            if manifest.get("version") != RESOURCE_BACKUP_VERSION:
                raise TextureCacheError(
                    f"unsupported backup version {manifest.get('version')}"
                )
            cache = (
                Path(cache_override).resolve()
                if cache_override is not None
                else Path(str(manifest["cache"])).resolve()
            )
            with cache.open("r+b") as stream:
                for record in manifest["resources"]:
                    stored = archive.read(record["stored_blob"])
                    if sha256_bytes(stored) != record["stored_sha256"]:
                        raise TextureCacheError(
                            f"backup blob for resource {record['resource_id']} is corrupt"
                        )
                    stream.seek(int(record["data_offset"]))
                    stream.write(stored)
                    stream.seek(int(record["directory_offset"]))
                    stream.write(bytes.fromhex(record["directory_record_hex"]))
                stream.seek(0)
                stream.write(bytes.fromhex(manifest["original_header_hex"]))
                stream.truncate(int(manifest["original_file_size"]))
                stream.flush()
                os.fsync(stream.fileno())
        validate_cache(cache)
        expected = manifest.get("source_cache_sha256")
        if isinstance(expected, str) and sha256_file(cache) != expected:
            raise TextureCacheError("restored cache SHA-256 differs from the backup source")
        return cache
    except TextureCacheError:
        raise
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise TextureCacheError(f"could not restore texture backup: {exc}") from exc


def _validate_key(key: object) -> None:
    if (
        not isinstance(key, tuple)
        or len(key) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in key)
        or any(value < 0 or value > 0xFFFFFFFF for value in key)
    ):
        raise TextureCacheError("resource keys must be unsigned (group_id, resource_id) pairs")


def _validate_write_set(
    writes: Sequence[TextureCacheWrite],
) -> tuple[TextureCacheWrite, ...]:
    canonical = tuple(writes)
    if not canonical:
        raise TextureCacheError("texture cache plan contains no writes")
    if any(not isinstance(item, TextureCacheWrite) for item in canonical):
        raise TextureCacheError("texture cache writes contain an unsupported value")
    if tuple(sorted(canonical, key=lambda item: item.key)) != canonical:
        raise TextureCacheError("texture cache writes must use canonical resource-key order")
    if len({item.key for item in canonical}) != len(canonical):
        raise TextureCacheError("texture cache writes contain duplicate resource keys")
    return canonical


__all__ = [
    "CACHE_DIRECTORY_ENTRY",
    "CACHE_HEADER",
    "MAX_REPLACEMENTS",
    "RESOURCE_BACKUP_VERSION",
    "TEXTURE_HEADER_BYTES",
    "CacheResourceDigest",
    "CacheValidation",
    "TextureCacheError",
    "TextureCachePlan",
    "TextureCacheWrite",
    "TexturePayloadInfo",
    "apply_texture_cache_plan",
    "apply_texture_cache_writes",
    "atomic_replace_exact",
    "build_texture_cache_plan",
    "compare_untargeted_payloads",
    "copy_file_exact",
    "create_resource_backup",
    "encode_png_payload",
    "entries_by_key",
    "parse_texture_payload",
    "read_stored_bytes",
    "restore_resource_backup",
    "sha256_bytes",
    "sha256_file",
    "validate_cache",
]
