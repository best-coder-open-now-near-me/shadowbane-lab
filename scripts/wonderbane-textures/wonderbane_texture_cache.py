#!/usr/bin/env python3
"""Plan, install, and exactly restore PNG replacements in a WonderBane texture cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import zipfile
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

HEADER = struct.Struct("<IIII")
DIRECTORY_ENTRY = struct.Struct("<IIIII")
BACKUP_VERSION = 1


@dataclass(frozen=True)
class CacheHeader:
    resource_count: int
    data_offset: int
    file_size: int
    marker: int


@dataclass(frozen=True)
class CacheEntry:
    index: int
    group_id: int
    resource_id: int
    data_offset: int
    raw_size: int
    stored_size: int

    @property
    def directory_offset(self) -> int:
        return HEADER.size + self.index * DIRECTORY_ENTRY.size

    @property
    def compressed(self) -> bool:
        return self.raw_size != self.stored_size


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_layout(path: Path) -> tuple[CacheHeader, tuple[CacheEntry, ...]]:
    actual_size = path.stat().st_size
    with path.open("rb") as stream:
        header_bytes = stream.read(HEADER.size)
        if len(header_bytes) != HEADER.size:
            raise ValueError("cache is smaller than its 16-byte header")
        header = CacheHeader(*HEADER.unpack(header_bytes))
        expected_directory_end = HEADER.size + header.resource_count * DIRECTORY_ENTRY.size
        if header.data_offset < expected_directory_end:
            raise ValueError("cache directory overlaps its resource data")
        if header.file_size != actual_size:
            raise ValueError(
                f"cache header size is {header.file_size}, but file size is {actual_size}"
            )
        entries = []
        for index in range(header.resource_count):
            record = stream.read(DIRECTORY_ENTRY.size)
            if len(record) != DIRECTORY_ENTRY.size:
                raise ValueError(f"cache directory ends at entry {index}")
            group_id, resource_id, data_offset, raw_size, stored_size = DIRECTORY_ENTRY.unpack(
                record
            )
            if data_offset < header.data_offset or data_offset + stored_size > actual_size:
                raise ValueError(f"resource {index} points outside the cache")
            entries.append(
                CacheEntry(index, group_id, resource_id, data_offset, raw_size, stored_size)
            )
    return header, tuple(entries)


def read_stored(path: Path, entry: CacheEntry) -> bytes:
    with path.open("rb") as stream:
        stream.seek(entry.data_offset)
        stored = stream.read(entry.stored_size)
    if len(stored) != entry.stored_size:
        raise ValueError(f"resource {entry.index} is truncated")
    return stored


def inflate(entry: CacheEntry, stored: bytes) -> bytes:
    payload = zlib.decompress(stored) if entry.compressed else stored
    if len(payload) != entry.raw_size:
        raise ValueError(
            f"resource {entry.index} decoded to {len(payload)} bytes; expected {entry.raw_size}"
        )
    return payload


def encode_png(path: Path, original_payload: bytes) -> tuple[bytes, dict[str, object]]:
    if len(original_payload) < 26:
        raise ValueError("texture payload is smaller than its 26-byte header")
    width, height, depth = struct.unpack_from("<III", original_payload, 0)
    if depth not in (1, 3, 4):
        raise ValueError(f"unsupported texture depth {depth}")
    expected_size = 26 + width * height * depth
    if len(original_payload) != expected_size:
        raise ValueError(
            f"texture payload has {len(original_payload)} bytes; expected {expected_size}"
        )
    with Image.open(path) as source:
        if source.size != (width, height):
            raise ValueError(f"{path} is {source.width}x{source.height}; expected {width}x{height}")
        mode = {1: "L", 3: "RGB", 4: "RGBA"}[depth]
        image = source.convert(mode).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        pixels = image.tobytes()
    payload = original_payload[:26] + pixels
    return payload, {
        "width": width,
        "height": height,
        "depth": depth,
        "mode": mode,
        "png": str(path.resolve()),
    }


def replacement_argument(value: str) -> tuple[int, Path]:
    identifier, separator, filename = value.partition("=")
    if not separator or not identifier.strip() or not filename.strip():
        raise argparse.ArgumentTypeError("replacement must be RESOURCE_ID=PNG")
    try:
        resource_id = int(identifier, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid resource id {identifier!r}") from exc
    path = Path(filename).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"replacement PNG does not exist: {path}")
    return resource_id, path


def prepare(
    cache: Path,
    group_id: int,
    requested: list[tuple[int, Path]],
) -> tuple[CacheHeader, tuple[CacheEntry, ...], list[dict[str, object]]]:
    header, entries = read_layout(cache)
    by_key = {(entry.group_id, entry.resource_id): entry for entry in entries}
    if len(requested) != len({resource_id for resource_id, _ in requested}):
        raise ValueError("each resource id may be replaced only once")
    plans = []
    for resource_id, png in requested:
        entry = by_key.get((group_id, resource_id))
        if entry is None:
            raise ValueError(f"cache has no resource {group_id}:{resource_id}")
        original_stored = read_stored(cache, entry)
        original_payload = inflate(entry, original_stored)
        replacement_payload, texture = encode_png(png, original_payload)
        replacement_stored = (
            zlib.compress(replacement_payload, level=9) if entry.compressed else replacement_payload
        )
        plans.append(
            {
                "entry": entry,
                "texture": texture,
                "original_stored": original_stored,
                "original_payload_sha256": sha256_bytes(original_payload),
                "replacement_payload": replacement_payload,
                "replacement_payload_sha256": sha256_bytes(replacement_payload),
                "replacement_stored": replacement_stored,
                "storage": "in-place" if len(replacement_stored) <= entry.stored_size else "append",
            }
        )
    return header, entries, plans


def public_plan(
    cache: Path, header: CacheHeader, plans: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "cache": str(cache.resolve()),
        "cache_size": header.file_size,
        "resource_count": header.resource_count,
        "replacements": [
            {
                "group_id": plan["entry"].group_id,
                "resource_id": plan["entry"].resource_id,
                "index": plan["entry"].index,
                "dimensions": [plan["texture"]["width"], plan["texture"]["height"]],
                "depth": plan["texture"]["depth"],
                "png": plan["texture"]["png"],
                "original_stored_size": plan["entry"].stored_size,
                "replacement_stored_size": len(plan["replacement_stored"]),
                "storage": plan["storage"],
                "original_payload_sha256": plan["original_payload_sha256"],
                "replacement_payload_sha256": plan["replacement_payload_sha256"],
            }
            for plan in plans
        ],
    }


def write_backup(
    backup: Path,
    cache: Path,
    header: CacheHeader,
    plans: list[dict[str, object]],
) -> None:
    if backup.exists():
        raise FileExistsError(f"backup already exists: {backup}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with cache.open("rb") as stream:
        original_header = stream.read(HEADER.size)
        records = []
        for plan in plans:
            entry = plan["entry"]
            stream.seek(entry.directory_offset)
            directory_record = stream.read(DIRECTORY_ENTRY.size)
            records.append((entry, directory_record, plan["original_stored"]))

    manifest = {
        "format": "wonderbane-texture-cache-backup",
        "version": BACKUP_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "cache": str(cache.resolve()),
        "original_file_size": header.file_size,
        "original_header_hex": original_header.hex(),
        "resources": [
            {
                "index": entry.index,
                "group_id": entry.group_id,
                "resource_id": entry.resource_id,
                "data_offset": entry.data_offset,
                "raw_size": entry.raw_size,
                "stored_size": entry.stored_size,
                "directory_offset": entry.directory_offset,
                "directory_record_hex": directory.hex(),
                "stored_blob": f"resources/{entry.index}.bin",
                "stored_sha256": sha256_bytes(stored),
            }
            for entry, directory, stored in records
        ],
    }
    temporary = backup.with_name(f"{backup.name}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            for entry, _, stored in records:
                archive.writestr(f"resources/{entry.index}.bin", stored)
        os.replace(temporary, backup)
    finally:
        if temporary.exists():
            temporary.unlink()


def restore_stream(stream, manifest: dict[str, object], archive: zipfile.ZipFile) -> None:
    for record in manifest["resources"]:
        stored = archive.read(record["stored_blob"])
        if sha256_bytes(stored) != record["stored_sha256"]:
            raise ValueError(f"backup blob for resource {record['resource_id']} is corrupt")
        stream.seek(int(record["data_offset"]))
        stream.write(stored)
        stream.seek(int(record["directory_offset"]))
        stream.write(bytes.fromhex(record["directory_record_hex"]))
    stream.seek(0)
    stream.write(bytes.fromhex(manifest["original_header_hex"]))
    stream.truncate(int(manifest["original_file_size"]))
    stream.flush()
    os.fsync(stream.fileno())


def install(cache: Path, backup: Path, header: CacheHeader, plans: list[dict[str, object]]) -> None:
    write_backup(backup, cache, header, plans)
    with zipfile.ZipFile(backup, "r") as backup_archive:
        manifest = json.loads(backup_archive.read("manifest.json"))
        try:
            with cache.open("r+b") as stream:
                file_size = header.file_size
                for plan in plans:
                    entry = plan["entry"]
                    stored = plan["replacement_stored"]
                    if len(stored) <= entry.stored_size:
                        data_offset = entry.data_offset
                    else:
                        data_offset = file_size
                        file_size += len(stored)
                    stream.seek(data_offset)
                    stream.write(stored)
                    stream.seek(entry.directory_offset)
                    stream.write(
                        DIRECTORY_ENTRY.pack(
                            entry.group_id,
                            entry.resource_id,
                            data_offset,
                            len(plan["replacement_payload"]),
                            len(stored),
                        )
                    )
                stream.seek(0)
                stream.write(
                    HEADER.pack(
                        header.resource_count,
                        header.data_offset,
                        file_size,
                        header.marker,
                    )
                )
                stream.truncate(file_size)
                stream.flush()
                os.fsync(stream.fileno())

            _, installed_entries = read_layout(cache)
            by_key = {(entry.group_id, entry.resource_id): entry for entry in installed_entries}
            for plan in plans:
                key = (plan["entry"].group_id, plan["entry"].resource_id)
                installed = by_key[key]
                actual = inflate(installed, read_stored(cache, installed))
                if sha256_bytes(actual) != plan["replacement_payload_sha256"]:
                    raise ValueError(
                        f"post-install validation failed for resource {key[0]}:{key[1]}"
                    )
        except Exception:
            with cache.open("r+b") as stream:
                restore_stream(stream, manifest, backup_archive)
            raise


def restore(backup: Path, cache_override: Path | None) -> Path:
    with zipfile.ZipFile(backup, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "wonderbane-texture-cache-backup":
            raise ValueError("file is not a WonderBane texture-cache backup")
        if manifest.get("version") != BACKUP_VERSION:
            raise ValueError(f"unsupported backup version {manifest.get('version')}")
        cache = cache_override or Path(manifest["cache"])
        with cache.open("r+b") as stream:
            restore_stream(stream, manifest, archive)
    read_layout(cache)
    return cache


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("plan", "install"):
        command = commands.add_parser(name)
        command.add_argument("cache", type=Path)
        command.add_argument("replacements", nargs="+", type=replacement_argument)
        command.add_argument("--group-id", type=int, default=0)
        if name == "install":
            command.add_argument("--backup", type=Path, required=True)
            command.add_argument("--confirm-client-closed", action="store_true")
    restore_command = commands.add_parser("restore")
    restore_command.add_argument("backup", type=Path)
    restore_command.add_argument("--cache", type=Path)
    restore_command.add_argument("--confirm-client-closed", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "restore":
        if not args.confirm_client_closed:
            raise ValueError("restore requires --confirm-client-closed")
        cache = restore(args.backup, args.cache)
        print(
            json.dumps(
                {"restored": str(cache.resolve()), "backup": str(args.backup.resolve())}, indent=2
            )
        )
        return 0

    cache = args.cache.resolve()
    if not cache.is_file():
        raise FileNotFoundError(cache)
    header, _, plans = prepare(cache, args.group_id, args.replacements)
    output = public_plan(cache, header, plans)
    if args.command == "plan":
        print(json.dumps(output, indent=2))
        return 0
    if not args.confirm_client_closed:
        raise ValueError("install requires --confirm-client-closed")
    install(cache, args.backup.resolve(), header, plans)
    output["installed"] = True
    output["backup"] = str(args.backup.resolve())
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
