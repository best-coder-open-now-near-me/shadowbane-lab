"""Version 1 cross-language wire contract for the optional in-client viewer.

The producer writes odd sequence, body/header, then even sequence. Readers copy
once, compare the sequence again, validate the complete frame checksum and fail
closed. Shared mappings are leases, never durable stores or movement commands.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from math import isfinite

from .geometry import ALL_LAYERS, MAX_LINES, OVERLAP, WORLD_HEIGHT, Geometry, Layer, Line
from .snapshot import MAX_CAPTURE_BYTES, Snapshot

MAGIC = 0x494E4257  # WBNI
VERSION = 1
HEADER = struct.Struct("<6I8Q6I4f")
LINE = struct.Struct("<II6f")
SEQUENCE_OFFSET = 12
CHECKSUM_OFFSET = 100
MAX_FRAME_BYTES = HEADER.size + MAX_LINES * LINE.size + MAX_CAPTURE_BYTES
LEASE_MS = 2000
SAMPLE_MS = 2000
ENABLED = 1
FROZEN = 2
XRAY = 4
UNKNOWN_HEIGHT = 8
KNOWN_FLAGS = ENABLED | FROZEN | XRAY | UNKNOWN_HEIGHT


def zone_identity(token: str | None) -> int:
    if not token:
        return 0
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "little") or 1


def mapping_name(pid: int, creation: int) -> str:
    return f"Local\\WonderBaneNavigation-{pid}-{creation}"


@dataclass(frozen=True, slots=True)
class Frame:
    sequence: int
    process_id: int
    process_creation: int
    session_id: int
    zone_id: int
    map_revision: int
    route_revision: int
    sampled_ms: int
    lease_ms: int
    live_zone_id: int
    flags: int
    layer_mask: int
    omitted_lines: int
    status: int
    center_lt: float
    center_lg: float
    view_radius: float
    lines: tuple[Line, ...]
    capture: bytes


def encode_frame(
    snapshot: Snapshot,
    geometry: Geometry,
    *,
    sequence: int,
    lease_ms: int,
    live_zone: str | None,
    enabled: bool = True,
    xray: bool = False,
    layers: int = ALL_LAYERS,
) -> bytes:
    if not 0 < sequence <= 0xFFFFFFFE or sequence % 2:
        raise ValueError("published sequence must be a nonzero even uint32")
    if len(geometry.lines) > MAX_LINES or layers < 0 or layers & ~ALL_LAYERS:
        raise ValueError("invalid geometry capacity or layers")
    capture = snapshot.to_bytes()
    flags = (
        UNKNOWN_HEIGHT
        | (ENABLED if enabled else 0)
        | (FROZEN if snapshot.frozen else 0)
        | (XRAY if xray else 0)
    )
    center = (
        snapshot.trail[-1][:2]
        if snapshot.trail
        else snapshot.plan.start
        if snapshot.plan
        else (0.0, 0.0)
    )
    radius = max(
        [50.0]
        + [
            max(abs(p[0] - center[0]), abs(-p[2] - center[1])) + 10
            for line in geometry.lines
            for p in (line.start, line.end)
        ]
    )
    body = (
        b"".join(
            LINE.pack(line.layer, line.flags, *line.start, *line.end) for line in geometry.lines
        )
        + capture
    )
    identity = snapshot.identity
    values = (
        MAGIC,
        VERSION,
        HEADER.size + len(body),
        sequence,
        identity.process_id,
        flags,
        identity.process_creation_filetime,
        snapshot.session_id,
        zone_identity(snapshot.context.zone_token),
        snapshot.map_revision,
        snapshot.route_revision,
        snapshot.sampled_ms,
        lease_ms,
        zone_identity(live_zone),
        len(geometry.lines),
        geometry.omitted_lines,
        len(capture),
        0,
        int(layers),
        int(geometry.audit.model_truncated),
        *center,
        radius,
        0.0,
    )
    result = bytearray(HEADER.pack(*values) + body)
    struct.pack_into("<I", result, CHECKSUM_OFFSET, zlib.crc32(result))
    return bytes(result)


def decode_frame(
    payload: bytes,
    *,
    process_id: int,
    process_creation: int,
    now_ms: int,
    sequence_after: int | None = None,
    expected_session: int | None = None,
    expected_zone: int | None = None,
) -> Frame:
    if not HEADER.size <= len(payload) <= MAX_FRAME_BYTES:
        raise ValueError("invalid frame size")
    (
        magic,
        version,
        size,
        sequence,
        pid,
        flags,
        creation,
        session,
        zone,
        map_revision,
        route_revision,
        sampled_ms,
        lease_ms,
        live_zone,
        count,
        omitted,
        capture_size,
        checksum,
        layers,
        status,
        center_lt,
        center_lg,
        radius,
        reserved,
    ) = HEADER.unpack_from(payload)
    if magic != MAGIC or version != VERSION or size != len(payload):
        raise ValueError("unsupported frame header")
    if not sequence or sequence % 2 or (sequence_after is not None and sequence != sequence_after):
        raise ValueError("torn frame sequence")
    if pid != process_id or creation != process_creation or not pid or not creation:
        raise ValueError("frame belongs to another process")
    if not session or (expected_session is not None and session != expected_session):
        raise ValueError("frame belongs to another session")
    if not zone or zone != live_zone or (expected_zone is not None and zone != expected_zone):
        raise ValueError("frame zone unavailable or changed")
    if flags & ~KNOWN_FLAGS or layers & ~ALL_LAYERS or status & ~1 or reserved != 0:
        raise ValueError("unsupported frame flags")
    if (
        count > MAX_LINES
        or capture_size > MAX_CAPTURE_BYTES
        or size != HEADER.size + count * LINE.size + capture_size
    ):
        raise ValueError("frame capacity mismatch")
    if (
        not all(isfinite(x) and abs(x) <= 1e9 for x in (center_lt, center_lg, radius))
        or radius <= 0
    ):
        raise ValueError("invalid projected viewport")
    if not 0 <= now_ms - lease_ms <= LEASE_MS:
        raise ValueError("producer lease expired")
    if sampled_ms > lease_ms or (not flags & FROZEN and now_ms - sampled_ms > SAMPLE_MS):
        raise ValueError("sample is stale")
    checked = bytearray(payload)
    struct.pack_into("<I", checked, CHECKSUM_OFFSET, 0)
    if zlib.crc32(checked) != checksum:
        raise ValueError("frame checksum mismatch")
    lines = []
    for offset in range(HEADER.size, HEADER.size + count * LINE.size, LINE.size):
        layer, line_flags, *points = LINE.unpack_from(payload, offset)
        if layer not in {int(value) for value in Layer} or line_flags & ~(WORLD_HEIGHT | OVERLAP):
            raise ValueError("invalid line flags")
        if not all(isfinite(x) and abs(x) <= 1e9 for x in points):
            raise ValueError("invalid line coordinate")
        if line_flags & WORLD_HEIGHT and layer != Layer.TRAIL:
            raise ValueError("unverified world height")
        lines.append(Line(layer, line_flags, tuple(points[:3]), tuple(points[3:])))
    return Frame(
        sequence,
        pid,
        creation,
        session,
        zone,
        map_revision,
        route_revision,
        sampled_ms,
        lease_ms,
        live_zone,
        flags,
        layers,
        omitted,
        status,
        center_lt,
        center_lg,
        radius,
        tuple(lines),
        payload[HEADER.size + count * LINE.size :],
    )
