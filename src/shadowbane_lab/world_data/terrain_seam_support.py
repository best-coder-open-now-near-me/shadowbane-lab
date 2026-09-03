"""Shared primitives for the read-only TerrainAlpha seam audit."""

from __future__ import annotations

import binascii
import hashlib
import json
import math
import struct
import zlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.integrity import is_reparse_point
from shadowbane_lab.world_data.cache import CacheArchive

TERRAIN_SEAM_AUDIT_SCHEMA_VERSION = 1
TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME = "terrain-seam-audit.json"
MAX_ZONE_CORRELATION_ISSUES = 4096


class TerrainSeamAuditError(ValueError):
    """Raised when a terrain seam audit cannot be completed without guessing."""


def _algorithm_description() -> dict[str, object]:
    return {
        "name": "terrain-seam-audit",
        "version": 1,
        "coordinate_space": "stored TerrainAlpha tile coordinates",
        "axis_x_order": "first tile is left; second tile is right",
        "axis_y_order": "first tile is lower; second tile is upper",
        "border_delta": "second boundary sample minus first boundary sample",
        "first_inward_gradient": (
            "first boundary sample minus its one-sample interior neighbour"
        ),
        "second_inward_gradient": (
            "second boundary sample minus its one-sample interior neighbour"
        ),
        "gradient_discontinuity": (
            "first inward gradient plus second inward gradient; zero is compatible "
            "with equal-and-opposite inward derivatives"
        ),
        "corner_spread": "maximum minus minimum of four touching corner samples",
        "diagnostic_score": (
            "maximum of seam border absolute p95, seam gradient-discontinuity "
            "absolute p95, and corner spread"
        ),
        "interpretation": (
            "neutral byte-space diagnostics; no material normalization, geometry claim, "
            "normal claim, or source mutation"
        ),
    }


def _json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


def _source_identity(source: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in source.items() if key != "path"}


def _archive_source(
    archive: CacheArchive,
    path: Path,
    sha256: str,
) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": sha256,
        "size": path.stat().st_size,
        "resource_count": archive.header.resource_count,
        "data_offset": archive.header.data_offset,
        "marker": archive.header.marker,
    }


def _require_regular_file(path: str | Path, field_name: str) -> Path:
    candidate = Path(path).absolute()
    if not candidate.is_file():
        raise TerrainSeamAuditError(f"{field_name} must name an ordinary file")
    for current in (candidate, *candidate.parents):
        if current.exists() and is_reparse_point(current):
            raise TerrainSeamAuditError(
                f"{field_name} must not cross a link or reparse point"
            )
    return candidate.resolve(strict=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_timestamp(value: datetime | None) -> str:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("created_at must include a timezone")
    return current.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _metric(value: float) -> float:
    return round(value, 6)


def _nearest_rank(sorted_values: Sequence[int], percentile: float) -> int:
    index = max(0, math.ceil(percentile * len(sorted_values)) - 1)
    return sorted_values[index]


def _byte(value: int | float) -> int:
    return max(0, min(255, int(round(value))))


def _encode_rgb_png(width: int, height: int, rows: Sequence[bytes]) -> bytes:
    if len(rows) != height or any(len(row) != width * 3 for row in rows):
        raise TerrainSeamAuditError("PNG rows do not match the requested RGB dimensions")
    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFF_FFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


__all__ = [
    "MAX_ZONE_CORRELATION_ISSUES",
    "TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME",
    "TERRAIN_SEAM_AUDIT_SCHEMA_VERSION",
    "TerrainSeamAuditError",
]
