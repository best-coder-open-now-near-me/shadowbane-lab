"""Lossless, read-only inspection and PNG export for WonderBane texture caches."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shadowbane_lab.client_extension.texture_cache import (
    TEXTURE_HEADER_BYTES,
    TextureCacheError,
    TexturePayloadInfo,
    entries_by_key,
    parse_texture_payload,
    sha256_bytes,
    sha256_file,
)
from shadowbane_lab.world_data.cache import (
    CacheArchive,
    CacheArchiveFormatError,
    CacheResourceEntry,
)

ORIENTATION = "cache-bottom-up-to-png-top-down"
SUPPORTED_DEPTHS = frozenset({1, 3, 4})


class TextureExportError(TextureCacheError):
    """Raised when a read-only texture operation cannot finish safely."""


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    size: int
    sha256: str
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class TextureResourceInfo:
    entry_index: int
    group_id: int
    resource_id: int
    compressed: bool
    stored_size: int
    uncompressed_size: int
    payload_sha256: str
    width: int
    height: int
    depth: int
    mode: str

    @property
    def key(self) -> tuple[int, int]:
        return self.group_id, self.resource_id

    def as_dict(self) -> dict[str, object]:
        return {
            "entry_index": self.entry_index,
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "compressed": self.compressed,
            "stored_size": self.stored_size,
            "uncompressed_size": self.uncompressed_size,
            "payload_sha256": self.payload_sha256,
            "width": self.width,
            "height": self.height,
            "depth": self.depth,
            "mode": self.mode,
        }


@dataclass(frozen=True, slots=True)
class TextureSkipInfo:
    entry_index: int
    group_id: int
    resource_id: int
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "entry_index": self.entry_index,
            "group_id": self.group_id,
            "resource_id": self.resource_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TextureScanReceipt:
    source_cache_name: str
    source_cache_size: int
    source_cache_sha256: str
    resource_count: int
    textures: tuple[TextureResourceInfo, ...]
    skipped: tuple[TextureSkipInfo, ...]

    def as_dict(self) -> dict[str, object]:
        dimensions = Counter(f"{item.width}x{item.height}" for item in self.textures)
        return {
            "schema_version": 1,
            "source_cache_name": self.source_cache_name,
            "source_cache_size": self.source_cache_size,
            "source_cache_sha256": self.source_cache_sha256,
            "resource_count": self.resource_count,
            "valid_texture_count": len(self.textures),
            "skipped_count": len(self.skipped),
            "depth_counts": _counts(item.depth for item in self.textures),
            "mode_counts": _counts(item.mode for item in self.textures),
            "dimension_counts": dict(sorted(dimensions.items())),
            "textures": [item.as_dict() for item in self.textures],
            "skipped": [item.as_dict() for item in self.skipped],
        }


@dataclass(frozen=True, slots=True)
class TextureExportReceipt:
    source_cache_name: str
    source_cache_size: int
    source_cache_sha256: str
    resource: TextureResourceInfo
    png_file: str
    png_sha256: str
    metadata_file: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_cache_name": self.source_cache_name,
            "source_cache_size": self.source_cache_size,
            "source_cache_sha256": self.source_cache_sha256,
            **self.resource.as_dict(),
            "orientation": ORIENTATION,
            "png_file": self.png_file,
            "png_sha256": self.png_sha256,
            "metadata_file": self.metadata_file,
        }


@dataclass(frozen=True, slots=True)
class TextureSampleEntry:
    resource: TextureResourceInfo
    entropy: float
    variance: float
    edge_density: float
    alpha_coverage: float | None
    thumbnail_sha256: str
    png_file: str
    png_sha256: str
    metadata_file: str

    def as_dict(self) -> dict[str, object]:
        return {
            **self.resource.as_dict(),
            "metrics": {
                "entropy": self.entropy,
                "variance": self.variance,
                "edge_density": self.edge_density,
                "alpha_coverage": self.alpha_coverage,
                "thumbnail_sha256": self.thumbnail_sha256,
            },
            "orientation": ORIENTATION,
            "png_file": self.png_file,
            "png_sha256": self.png_sha256,
            "metadata_file": self.metadata_file,
        }


@dataclass(frozen=True, slots=True)
class TextureSampleReceipt:
    source_cache_name: str
    source_cache_size: int
    source_cache_sha256: str
    resource_count: int
    valid_texture_count: int
    eligible_candidate_count: int
    selected: tuple[TextureSampleEntry, ...]
    output_directory: str
    contact_sheet_file: str
    contact_sheet_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_cache_name": self.source_cache_name,
            "source_cache_size": self.source_cache_size,
            "source_cache_sha256": self.source_cache_sha256,
            "resource_count": self.resource_count,
            "valid_texture_count": self.valid_texture_count,
            "eligible_candidate_count": self.eligible_candidate_count,
            "selected_count": len(self.selected),
            "output_directory": self.output_directory,
            "contact_sheet_file": self.contact_sheet_file,
            "contact_sheet_sha256": self.contact_sheet_sha256,
            "selected": [item.as_dict() for item in self.selected],
        }


def _counts(values: Iterable[object]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _cache_path(path: str | Path) -> Path:
    cache = Path(path).expanduser().resolve()
    if not cache.is_file():
        raise TextureExportError(f"texture cache does not exist: {cache}")
    return cache


def _identity(path: Path) -> _SourceIdentity:
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise TextureExportError("texture cache changed while its identity was read")
    return _SourceIdentity(after.st_size, digest, after.st_mtime_ns)


def _require_unchanged(path: Path, expected: _SourceIdentity) -> None:
    if _identity(path) != expected:
        raise TextureExportError("texture cache changed during a read-only operation")


def _resource_info(
    entry: CacheResourceEntry,
    payload: bytes,
    info: TexturePayloadInfo,
) -> TextureResourceInfo:
    return TextureResourceInfo(
        entry_index=entry.index,
        group_id=entry.group_id,
        resource_id=entry.resource_id,
        compressed=entry.is_compressed,
        stored_size=entry.stored_size,
        uncompressed_size=entry.uncompressed_size,
        payload_sha256=sha256_bytes(payload),
        width=info.width,
        height=info.height,
        depth=info.channels,
        mode=info.mode,
    )


def _reason(error: BaseException) -> str:
    text = " ".join(str(error).split())
    value = f"{type(error).__name__}: {text}" if text else type(error).__name__
    return value[:300]


def _scan(cache: Path, identity: _SourceIdentity) -> TextureScanReceipt:
    textures: list[TextureResourceInfo] = []
    skipped: list[TextureSkipInfo] = []
    try:
        with CacheArchive(cache) as archive:
            entries_by_key(archive)
            resource_count = archive.header.resource_count
            for entry in archive.entries:
                try:
                    payload = archive.read_resource(entry)
                    info = parse_texture_payload(payload)
                except (CacheArchiveFormatError, TextureCacheError, ValueError) as error:
                    skipped.append(
                        TextureSkipInfo(
                            entry.index,
                            entry.group_id,
                            entry.resource_id,
                            _reason(error),
                        )
                    )
                    continue
                textures.append(_resource_info(entry, payload, info))
    except TextureCacheError:
        raise
    except (CacheArchiveFormatError, OSError, ValueError) as error:
        raise TextureExportError(f"could not scan texture cache: {error}") from error
    return TextureScanReceipt(
        cache.name,
        identity.size,
        identity.sha256,
        resource_count,
        tuple(textures),
        tuple(skipped),
    )


def scan_texture_resources(cache_path: str | Path) -> TextureScanReceipt:
    """Return valid textures and concise skip reasons without modifying the source."""

    cache = _cache_path(cache_path)
    identity = _identity(cache)
    receipt = _scan(cache, identity)
    _require_unchanged(cache, identity)
    return receipt


def inspect_texture_resources(
    cache_path: str | Path,
) -> tuple[TextureResourceInfo, ...]:
    return scan_texture_resources(cache_path).textures


def decode_texture_payload(payload: bytes) -> Any:
    """Decode bottom-up cache pixels into a top-down Pillow image."""

    info = parse_texture_payload(payload)
    try:
        from PIL import Image
    except ImportError as error:  # pragma: no cover
        raise TextureExportError("Pillow is required for texture export") from error
    image = Image.frombytes(
        info.mode,
        (info.width, info.height),
        payload[TEXTURE_HEADER_BYTES:],
    )
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def _png_bytes(image: Any) -> bytes:
    output = io.BytesIO()
    image.save(
        output,
        format="PNG",
        optimize=False,
        compress_level=9,
        pnginfo=None,
    )
    return output.getvalue()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_files(files: Sequence[tuple[Path, bytes]], *, overwrite: bool) -> None:
    destinations = tuple(path.resolve() for path, _ in files)
    if len(destinations) != len(set(destinations)):
        raise TextureExportError("texture export output paths must be distinct")
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        existing = next((path for path in destinations if path.exists()), None)
        if existing is not None:
            raise TextureExportError(f"texture export output already exists: {existing}")
    staged: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, (_, value) in zip(destinations, files, strict=True):
            descriptor, name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append((temporary, destination))
        if overwrite:
            for destination in destinations:
                if destination.exists():
                    backup = destination.with_name(f".{destination.name}.backup")
                    if backup.exists():
                        backup.unlink()
                    os.replace(destination, backup)
                    backups.append((destination, backup))
        elif any(path.exists() for path in destinations):
            raise TextureExportError("texture export output appeared during publication")
        for temporary, destination in staged:
            os.replace(temporary, destination)
            published.append(destination)
    except BaseException:
        for destination in reversed(published):
            destination.unlink(missing_ok=True)
        for destination, backup in reversed(backups):
            if backup.exists():
                os.replace(backup, destination)
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        for _, backup in backups:
            backup.unlink(missing_ok=True)


def _entry(
    archive: CacheArchive,
    group_id: int,
    resource_id: int,
) -> CacheResourceEntry:
    entry = entries_by_key(archive).get((group_id, resource_id))
    if entry is None:
        raise TextureExportError(
            f"cache has no texture resource {group_id}:{resource_id}"
        )
    return entry


def export_texture_png(
    cache_path: str | Path,
    group_id: int,
    resource_id: int,
    output_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
    overwrite: bool = False,
) -> TextureExportReceipt:
    """Export one exact texture and a deterministic provenance sidecar."""

    if not 0 <= group_id <= 0xFFFFFFFF or not 0 <= resource_id <= 0xFFFFFFFF:
        raise TextureExportError("texture resource IDs must be unsigned 32-bit integers")
    cache = _cache_path(cache_path)
    png = Path(output_path).expanduser().resolve()
    metadata = (
        Path(metadata_path).expanduser().resolve()
        if metadata_path is not None
        else png.with_suffix(png.suffix + ".json")
    )
    identity = _identity(cache)
    with CacheArchive(cache) as archive:
        entry = _entry(archive, group_id, resource_id)
        payload = archive.read_resource(entry)
        info = parse_texture_payload(payload)
        resource = _resource_info(entry, payload, info)
        image = decode_texture_payload(payload)
    png_value = _png_bytes(image)
    receipt = TextureExportReceipt(
        cache.name,
        identity.size,
        identity.sha256,
        resource,
        png.name,
        sha256_bytes(png_value),
        metadata.name,
    )
    _require_unchanged(cache, identity)
    _atomic_files(
        ((png, png_value), (metadata, _json_bytes(receipt.as_dict()))),
        overwrite=overwrite,
    )
    _require_unchanged(cache, identity)
    return receipt


def _metrics(image: Any) -> tuple[float, float, float, float | None, str] | None:
    from PIL import Image, ImageFilter, ImageStat

    thumbnail = image.copy()
    thumbnail.thumbnail((64, 64), Image.Resampling.BOX)
    gray = thumbnail.convert("L")
    minimum, maximum = gray.getextrema()
    entropy = float(gray.entropy())
    variance = float(ImageStat.Stat(gray).var[0])
    if maximum - minimum <= 1 or entropy < 0.02 or variance < 0.25:
        return None
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_density = float(ImageStat.Stat(edges).mean[0]) / 255.0
    alpha_coverage: float | None = None
    if thumbnail.mode == "RGBA":
        histogram = thumbnail.getchannel("A").histogram()
        alpha_coverage = (sum(histogram) - histogram[0]) / max(1, sum(histogram))
    signature = hashlib.sha256(thumbnail.convert(image.mode).tobytes()).hexdigest()
    return (
        round(entropy, 6),
        round(variance, 6),
        round(edge_density, 6),
        None if alpha_coverage is None else round(alpha_coverage, 6),
        signature,
    )


def _sheet(entries: Sequence[tuple[TextureResourceInfo, Path]]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    columns = 4
    tile_width, tile_height = 240, 190
    image_width, image_height = 216, 144
    rows = max(1, (len(entries) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), (28, 28, 28))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (resource, path) in enumerate(entries):
        left = (index % columns) * tile_width + 12
        top = (index // columns) * tile_height + 10
        with Image.open(path) as source:
            source.load()
            thumbnail = source.copy()
        thumbnail.thumbnail((image_width, image_height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (image_width, image_height), (214, 214, 214))
        checker = ImageDraw.Draw(canvas)
        for y in range(0, image_height, 8):
            for x in range(0, image_width, 8):
                if (x // 8 + y // 8) % 2:
                    checker.rectangle((x, y, x + 7, y + 7), fill=(238, 238, 238))
        offset = (
            (image_width - thumbnail.width) // 2,
            (image_height - thumbnail.height) // 2,
        )
        if thumbnail.mode == "RGBA":
            canvas.paste(thumbnail, offset, thumbnail.getchannel("A"))
        else:
            canvas.paste(thumbnail.convert("RGB"), offset)
        sheet.paste(canvas, (left, top))
        label = (
            f"{resource.group_id}:{resource.resource_id}  "
            f"{resource.width}x{resource.height}  {resource.mode}/{resource.depth}"
        )
        draw.text((left, top + image_height + 7), label, fill=(240, 240, 240), font=font)
    return _png_bytes(sheet)


def export_texture_samples(
    cache_path: str | Path,
    output_directory: str | Path,
    *,
    limit: int = 64,
    minimum_width: int = 128,
    minimum_height: int = 128,
    group_id: int | None = None,
    include_depths: Iterable[int] | None = None,
    overwrite: bool = False,
) -> TextureSampleReceipt:
    """Export deterministic anonymous candidates and a labeled contact sheet."""

    if limit <= 0 or minimum_width <= 0 or minimum_height <= 0:
        raise TextureExportError("sample limit and minimum dimensions must be positive")
    depths = SUPPORTED_DEPTHS if include_depths is None else frozenset(include_depths)
    if not depths or not depths.issubset(SUPPORTED_DEPTHS):
        raise TextureExportError("included depths must be chosen from 1, 3, and 4")
    cache = _cache_path(cache_path)
    destination = Path(output_directory).expanduser().resolve()
    if destination.exists() and not overwrite:
        raise TextureExportError(f"sample output directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    identity = _identity(cache)
    scan = _scan(cache, identity)
    candidates: list[tuple[tuple[object, ...], TextureResourceInfo, tuple[Any, ...]]] = []
    with CacheArchive(cache) as archive:
        indexed = entries_by_key(archive)
        for resource in scan.textures:
            if group_id is not None and resource.group_id != group_id:
                continue
            if resource.depth not in depths:
                continue
            if resource.width < minimum_width or resource.height < minimum_height:
                continue
            payload = archive.read_resource(indexed[resource.key])
            metric = _metrics(decode_texture_payload(payload))
            if metric is None:
                continue
            entropy, variance, edge_density, alpha_coverage, signature = metric
            rank = (
                -(resource.width * resource.height),
                -entropy,
                -variance,
                -edge_density,
                resource.group_id,
                resource.resource_id,
                resource.entry_index,
            )
            candidates.append((rank, resource, metric))
    candidates.sort(key=lambda item: item[0])
    selected_candidates: list[tuple[TextureResourceInfo, tuple[Any, ...]]] = []
    signatures: set[str] = set()
    dimension_counts: Counter[tuple[str, int, int]] = Counter()
    while len(selected_candidates) < limit:
        remaining = [
            item
            for item in candidates
            if item[2][4] not in signatures
        ]
        if not remaining:
            break
        rank, resource, metric = min(
            remaining,
            key=lambda item: (
                dimension_counts[(item[1].mode, item[1].width, item[1].height)],
                item[0],
            ),
        )
        del rank
        signatures.add(metric[4])
        dimension_counts[(resource.mode, resource.width, resource.height)] += 1
        selected_candidates.append((resource, metric))

    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    backup = destination.with_name(f".{destination.name}.backup")
    try:
        textures = staging / "textures"
        metadata = staging / "metadata"
        textures.mkdir()
        metadata.mkdir()
        selected: list[TextureSampleEntry] = []
        sheet_entries: list[tuple[TextureResourceInfo, Path]] = []
        with CacheArchive(cache) as archive:
            indexed = entries_by_key(archive)
            for resource, metric in selected_candidates:
                payload = archive.read_resource(indexed[resource.key])
                if sha256_bytes(payload) != resource.payload_sha256:
                    raise TextureExportError(
                        f"texture payload changed for {resource.group_id}:{resource.resource_id}"
                    )
                value = _png_bytes(decode_texture_payload(payload))
                stem = f"{resource.group_id}-{resource.resource_id}"
                png_relative = Path("textures") / f"{stem}.png"
                metadata_relative = Path("metadata") / f"{stem}.json"
                png_path = staging / png_relative
                png_path.write_bytes(value)
                entry = TextureSampleEntry(
                    resource,
                    metric[0],
                    metric[1],
                    metric[2],
                    metric[3],
                    metric[4],
                    png_relative.as_posix(),
                    sha256_bytes(value),
                    metadata_relative.as_posix(),
                )
                (staging / metadata_relative).write_bytes(
                    _json_bytes(
                        {
                            "schema_version": 1,
                            "source_cache_name": cache.name,
                            "source_cache_size": identity.size,
                            "source_cache_sha256": identity.sha256,
                            **entry.as_dict(),
                        }
                    )
                )
                selected.append(entry)
                sheet_entries.append((resource, png_path))
        contact_sheet = _sheet(sheet_entries)
        contact_sheet_name = "contact-sheet.png"
        (staging / contact_sheet_name).write_bytes(contact_sheet)
        (staging / "texture-index.json").write_bytes(_json_bytes(scan.as_dict()))
        receipt = TextureSampleReceipt(
            cache.name,
            identity.size,
            identity.sha256,
            scan.resource_count,
            len(scan.textures),
            len(candidates),
            tuple(selected),
            destination.name,
            contact_sheet_name,
            sha256_bytes(contact_sheet),
        )
        (staging / "sample-manifest.json").write_bytes(_json_bytes(receipt.as_dict()))
        (staging / "run-receipt.json").write_bytes(
            _json_bytes(
                {
                    **receipt.as_dict(),
                    "source_unchanged": True,
                    "source_size_before": identity.size,
                    "source_size_after": identity.size,
                    "source_sha256_before": identity.sha256,
                    "source_sha256_after": identity.sha256,
                }
            )
        )
        _require_unchanged(cache, identity)
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except BaseException:
            if backup.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        _require_unchanged(cache, identity)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _resource_key(value: str) -> tuple[int, int]:
    group_text, separator, resource_text = value.partition(":")
    try:
        if separator:
            key = int(group_text, 0), int(resource_text, 0)
        else:
            key = 0, int(group_text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "texture key must be RESOURCE or GROUP:RESOURCE"
        ) from error
    if any(value < 0 or value > 0xFFFFFFFF for value in key):
        raise argparse.ArgumentTypeError("texture key values must be unsigned 32-bit integers")
    return key


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("source_cache", type=Path)
    listing.add_argument("--output", type=Path)
    listing.add_argument("--overwrite", action="store_true")
    listing.add_argument("--pretty", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("source_cache", type=Path)
    export.add_argument("resource", type=_resource_key)
    export.add_argument("output_png", type=Path)
    export.add_argument("--metadata", type=Path)
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--pretty", action="store_true")
    samples = commands.add_parser("samples")
    samples.add_argument("source_cache", type=Path)
    samples.add_argument("output_directory", type=Path)
    samples.add_argument("--limit", type=int, default=64)
    samples.add_argument("--min-width", type=int, default=128)
    samples.add_argument("--min-height", type=int, default=128)
    samples.add_argument("--group-id", type=int)
    samples.add_argument(
        "--include-depth",
        type=int,
        choices=tuple(sorted(SUPPORTED_DEPTHS)),
        action="append",
    )
    samples.add_argument("--overwrite", action="store_true")
    samples.add_argument("--pretty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "list":
            payload = scan_texture_resources(arguments.source_cache).as_dict()
            if arguments.output is not None:
                _atomic_files(
                    ((arguments.output.expanduser().resolve(), _json_bytes(payload)),),
                    overwrite=arguments.overwrite,
                )
        elif arguments.command == "export":
            payload = export_texture_png(
                arguments.source_cache,
                arguments.resource[0],
                arguments.resource[1],
                arguments.output_png,
                metadata_path=arguments.metadata,
                overwrite=arguments.overwrite,
            ).as_dict()
        elif arguments.command == "samples":
            payload = export_texture_samples(
                arguments.source_cache,
                arguments.output_directory,
                limit=arguments.limit,
                minimum_width=arguments.min_width,
                minimum_height=arguments.min_height,
                group_id=arguments.group_id,
                include_depths=arguments.include_depth,
                overwrite=arguments.overwrite,
            ).as_dict()
        else:  # pragma: no cover
            raise AssertionError(arguments.command)
    except (OSError, ValueError, TextureCacheError) as error:
        print(f"texture export failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            payload,
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )
    return 0


__all__ = [
    "ORIENTATION",
    "TextureExportError",
    "TextureExportReceipt",
    "TextureResourceInfo",
    "TextureSampleEntry",
    "TextureSampleReceipt",
    "TextureScanReceipt",
    "TextureSkipInfo",
    "decode_texture_payload",
    "export_texture_png",
    "export_texture_samples",
    "inspect_texture_resources",
    "main",
    "scan_texture_resources",
]


if __name__ == "__main__":
    raise SystemExit(main())
