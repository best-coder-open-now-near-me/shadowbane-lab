"""Bounded frame, cache-I/O, and texture-upload telemetry from one client lifetime."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, StrEnum

PERFORMANCE_TELEMETRY_SCHEMA_VERSION = 2
PERFORMANCE_TELEMETRY_MAGIC = b"WBPERF2\0"
PERFORMANCE_TELEMETRY_HEADER_SIZE = 128
PERFORMANCE_TELEMETRY_SLOT_SIZE = 96
PERFORMANCE_TELEMETRY_CAPACITY = 8192
PERFORMANCE_TELEMETRY_SIZE = (
    PERFORMANCE_TELEMETRY_HEADER_SIZE
    + PERFORMANCE_TELEMETRY_SLOT_SIZE * PERFORMANCE_TELEMETRY_CAPACITY
)
PERFORMANCE_TELEMETRY_HOOK_COUNT = 20
PERFORMANCE_FRAME_HOOK_COUNT = 0
PERFORMANCE_FRAME_CAPABILITY = 1 << 0
PERFORMANCE_CACHE_READ_CAPABILITY = 1 << 1
PERFORMANCE_TEXTURE_UPLOAD_CAPABILITY = 1 << 2
PERFORMANCE_AGGREGATE_FLAG = 1 << 3
PERFORMANCE_FULL_CAPABILITY = (
    PERFORMANCE_FRAME_CAPABILITY
    | PERFORMANCE_CACHE_READ_CAPABILITY
    | PERFORMANCE_TEXTURE_UPLOAD_CAPABILITY
)
PERFORMANCE_AGGREGATE_CAPABILITY = (
    PERFORMANCE_FULL_CAPABILITY | PERFORMANCE_AGGREGATE_FLAG
)
PERFORMANCE_SUCCESS_FLAG = 1 << 0
PERFORMANCE_WIN32_IO_FLAG = 1 << 1
PERFORMANCE_STDIO_IO_FLAG = 1 << 2
PERFORMANCE_PIXELS_PRESENT_FLAG = 1 << 3
PERFORMANCE_KNOWN_FLAGS = (
    PERFORMANCE_SUCCESS_FLAG
    | PERFORMANCE_WIN32_IO_FLAG
    | PERFORMANCE_STDIO_IO_FLAG
    | PERFORMANCE_PIXELS_PRESENT_FLAG
)
UNKNOWN_CACHE_OFFSET = 0xFFFFFFFFFFFFFFFF

_HEADER = struct.Struct("<8s6I11Q2I")
_SLOT = struct.Struct("<QIIQQII7Q")


class PerformanceTelemetryError(ValueError):
    """Raised when a performance mapping violates its versioned contract."""


class PerformanceRecordKind(StrEnum):
    FRAME_GAP = "frame_gap"
    CACHE_READ = "cache_read"
    TEXTURE_IMAGE = "texture_image"
    TEXTURE_SUB_IMAGE = "texture_sub_image"
    FRAME_SUMMARY = "frame_summary"

class CacheArchive(StrEnum):
    NONE = "none"
    TEXTURES = "Textures.cache"
    MESH = "Mesh.cache"
    RENDER = "Render.cache"
    OBJECTS = "CObjects.cache"
    ZONES = "CZone.cache"
    TERRAIN_ALPHA = "TerrainAlpha.cache"
    TILE = "Tile.cache"
    OTHER = "other.cache"


class _PerformanceRecordCode(IntEnum):
    FRAME_GAP = 1
    CACHE_READ = 2
    TEXTURE_IMAGE = 3
    TEXTURE_SUB_IMAGE = 4
    FRAME_SUMMARY = 5

_RECORD_KIND = {
    _PerformanceRecordCode.FRAME_GAP: PerformanceRecordKind.FRAME_GAP,
    _PerformanceRecordCode.CACHE_READ: PerformanceRecordKind.CACHE_READ,
    _PerformanceRecordCode.TEXTURE_IMAGE: PerformanceRecordKind.TEXTURE_IMAGE,
    _PerformanceRecordCode.TEXTURE_SUB_IMAGE: PerformanceRecordKind.TEXTURE_SUB_IMAGE,
    _PerformanceRecordCode.FRAME_SUMMARY: PerformanceRecordKind.FRAME_SUMMARY,
}
_ARCHIVE_KIND = {
    0: CacheArchive.NONE,
    1: CacheArchive.TEXTURES,
    2: CacheArchive.MESH,
    3: CacheArchive.RENDER,
    4: CacheArchive.OBJECTS,
    5: CacheArchive.ZONES,
    6: CacheArchive.TERRAIN_ALPHA,
    7: CacheArchive.TILE,
    255: CacheArchive.OTHER,
}


@dataclass(frozen=True, slots=True)
class PerformanceTelemetryHeader:
    process_id: int
    capability_flags: int
    process_creation_filetime_utc: int
    qpc_frequency: int
    started_qpc: int
    write_sequence: int
    overwritten_record_count: int
    frame_count: int
    slow_frame_count: int
    cache_read_count: int
    cache_read_bytes: int
    texture_upload_count: int
    texture_upload_bytes: int
    producer_error: int
    active_hook_count: int

    def __post_init__(self) -> None:
        for value, name, allow_zero in (
            (self.process_id, "process_id", False),
            (self.capability_flags, "capability_flags", False),
            (self.process_creation_filetime_utc, "process_creation_filetime_utc", False),
            (self.qpc_frequency, "qpc_frequency", False),
            (self.started_qpc, "started_qpc", False),
            (self.write_sequence, "write_sequence", True),
            (self.overwritten_record_count, "overwritten_record_count", True),
            (self.frame_count, "frame_count", True),
            (self.slow_frame_count, "slow_frame_count", True),
            (self.cache_read_count, "cache_read_count", True),
            (self.cache_read_bytes, "cache_read_bytes", True),
            (self.texture_upload_count, "texture_upload_count", True),
            (self.texture_upload_bytes, "texture_upload_bytes", True),
            (self.producer_error, "producer_error", True),
            (self.active_hook_count, "active_hook_count", True),
        ):
            minimum = 0 if allow_zero else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise PerformanceTelemetryError(f"{name} is outside its bounded range")
        expected_overwritten = max(0, self.write_sequence - PERFORMANCE_TELEMETRY_CAPACITY)
        if self.overwritten_record_count != expected_overwritten:
            raise PerformanceTelemetryError("overwritten record count is inconsistent")
        if self.slow_frame_count > self.frame_count:
            raise PerformanceTelemetryError("slow frame count exceeds total frame count")
        if self.capability_flags not in {
            PERFORMANCE_FRAME_CAPABILITY,
            PERFORMANCE_FULL_CAPABILITY,
            PERFORMANCE_AGGREGATE_CAPABILITY,
        }:
            raise PerformanceTelemetryError("capability flags do not identify a reviewed profile")
        maximum_hooks = (
            PERFORMANCE_TELEMETRY_HOOK_COUNT
            if self.capability_flags
            in {PERFORMANCE_FULL_CAPABILITY, PERFORMANCE_AGGREGATE_CAPABILITY}
            else PERFORMANCE_FRAME_HOOK_COUNT
        )
        if self.active_hook_count > maximum_hooks:
            raise PerformanceTelemetryError("active hook count exceeds the reviewed hook set")

    def ticks_to_milliseconds(self, ticks: int) -> float:
        return ticks * 1000.0 / self.qpc_frequency

    def as_dict(self) -> dict[str, int | str]:
        return {
            "process_id": self.process_id,
            "capability_flags": self.capability_flags,
            "profile": (
                "aggregate"
                if self.capability_flags == PERFORMANCE_AGGREGATE_CAPABILITY
                else "full"
                    if self.capability_flags == PERFORMANCE_FULL_CAPABILITY
                    else "frame"
            ),
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "qpc_frequency": self.qpc_frequency,
            "started_qpc": self.started_qpc,
            "write_sequence": self.write_sequence,
            "overwritten_record_count": self.overwritten_record_count,
            "frame_count": self.frame_count,
            "slow_frame_count": self.slow_frame_count,
            "cache_read_count": self.cache_read_count,
            "cache_read_bytes": self.cache_read_bytes,
            "texture_upload_count": self.texture_upload_count,
            "texture_upload_bytes": self.texture_upload_bytes,
            "producer_error": self.producer_error,
            "active_hook_count": self.active_hook_count,
        }


@dataclass(frozen=True, slots=True)
class PerformanceRecord:
    sequence: int
    kind: PerformanceRecordKind
    flags: int
    started_qpc: int
    duration_qpc: int
    thread_id: int
    archive: CacheArchive
    byte_count: int
    argument0: int
    argument1: int
    argument2: int
    frame_interval_qpc: int
    pipeline_gap_qpc: int
    reserved: int

    @property
    def succeeded(self) -> bool:
        return bool(self.flags & PERFORMANCE_SUCCESS_FLAG)

    def as_dict(self, header: PerformanceTelemetryHeader) -> dict[str, object]:
        result: dict[str, object] = {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "thread_id": self.thread_id,
            "at_ms": header.ticks_to_milliseconds(self.started_qpc - header.started_qpc),
            "duration_ms": header.ticks_to_milliseconds(self.duration_qpc),
            "succeeded": self.succeeded,
        }
        if self.kind is PerformanceRecordKind.FRAME_GAP:
            result["frame_interval_ms"] = header.ticks_to_milliseconds(
                self.frame_interval_qpc
            )
            result["present_ms"] = header.ticks_to_milliseconds(self.duration_qpc)
        elif self.kind is PerformanceRecordKind.FRAME_SUMMARY:
            frame_time_ms = (
                None
                if self.frame_interval_qpc == 0
                else header.ticks_to_milliseconds(self.frame_interval_qpc)
            )
            result.update(
                {
                    "frame_time_ms": frame_time_ms,
                    "frame_interval_ms": frame_time_ms,
                    "present_ms": header.ticks_to_milliseconds(self.duration_qpc),
                    "cache_reads": {
                        "count": self.argument0,
                        "bytes": self.byte_count,
                        "total_time_ms": header.ticks_to_milliseconds(self.argument1),
                    },
                    "texture_uploads": {
                        "count": self.argument2,
                        "bytes": self.reserved,
                        "total_time_ms": header.ticks_to_milliseconds(
                            self.pipeline_gap_qpc
                        ),
                    },
                }
            )
        elif self.kind is PerformanceRecordKind.CACHE_READ:
            result.update(
                {
                    "archive": self.archive.value,
                    "transport": (
                        "win32"
                        if self.flags & PERFORMANCE_WIN32_IO_FLAG
                        else "stdio"
                    ),
                    "offset": None if self.argument0 == UNKNOWN_CACHE_OFFSET else self.argument0,
                    "requested_bytes": self.argument1,
                    "completed_bytes": self.byte_count,
                    "status_code": self.argument2,
                }
            )
        else:
            width = self.argument0 & 0xFFFFFFFF
            height = self.argument0 >> 32
            internal_format = self.argument1 & 0xFFFFFFFF
            result.update(
                {
                    "archive_before_upload": (
                        None if self.archive is CacheArchive.NONE else self.archive.value
                    ),
                    "estimated_bytes": self.byte_count,
                    "width": width,
                    "height": height,
                    "internal_format": internal_format,
                    "format": self.argument1 >> 32,
                    "target": self.argument2 & 0xFFFFFFFF,
                    "level": (self.argument2 >> 32) & 0xFFFF,
                    "type": (self.argument2 >> 48) & 0xFFFF,
                    "pixels_present": bool(self.flags & PERFORMANCE_PIXELS_PRESENT_FLAG),
                    "read_to_upload_ms": header.ticks_to_milliseconds(
                        self.pipeline_gap_qpc
                    ),
                }
            )
        return result


@dataclass(frozen=True, slots=True)
class PerformanceTelemetrySnapshot:
    header: PerformanceTelemetryHeader
    records: tuple[PerformanceRecord, ...]

    def as_dict(self) -> dict[str, object]:
        converted = tuple(record.as_dict(self.header) for record in self.records)

        def maximum(field: str) -> float:
            values = [
                float(record[field])
                for record in converted
                if field in record and record[field] is not None
            ]
            return max(values, default=0.0)

        return {
            "schema_version": PERFORMANCE_TELEMETRY_SCHEMA_VERSION,
            "header": self.header.as_dict(),
            "summary": {
                "retained_record_count": len(converted),
                "max_frame_interval_ms": maximum("frame_interval_ms"),
                "max_cache_read_ms": max(
                    (
                        float(record["duration_ms"])
                        for record in converted
                        if record["kind"] == PerformanceRecordKind.CACHE_READ.value
                    ),
                    default=0.0,
                ),
                "max_texture_upload_ms": max(
                    (
                        float(record["duration_ms"])
                        for record in converted
                        if record["kind"]
                        in {
                            PerformanceRecordKind.TEXTURE_IMAGE.value,
                            PerformanceRecordKind.TEXTURE_SUB_IMAGE.value,
                        }
                    ),
                    default=0.0,
                ),
                "max_read_to_upload_ms": maximum("read_to_upload_ms"),
            },
            "records": list(converted),
        }


def performance_telemetry_mapping_name(
    process_id: int,
    process_creation_filetime_utc: int,
) -> str:
    _bounded_positive(process_id, "process_id", 0xFFFFFFFF)
    _bounded_positive(
        process_creation_filetime_utc,
        "process_creation_filetime_utc",
        0xFFFFFFFFFFFFFFFF,
    )
    return (
        "Local\\ShadowbaneLab.Extension.Performance."
        f"{process_id}.{process_creation_filetime_utc}"
    )


def parse_performance_telemetry(
    payload: bytes | bytearray | memoryview,
    *,
    expected_process_id: int,
    expected_process_creation_filetime_utc: int,
) -> PerformanceTelemetrySnapshot:
    source = bytes(payload)
    if len(source) != PERFORMANCE_TELEMETRY_SIZE:
        raise PerformanceTelemetryError("performance telemetry has an unexpected size")
    unpacked = _HEADER.unpack_from(source)
    (
        magic,
        schema_version,
        header_size,
        slot_size,
        capacity,
        process_id,
        capability_flags,
        creation,
        qpc_frequency,
        started_qpc,
        write_sequence,
        overwritten_record_count,
        frame_count,
        slow_frame_count,
        cache_read_count,
        cache_read_bytes,
        texture_upload_count,
        texture_upload_bytes,
        producer_error,
        active_hook_count,
    ) = unpacked
    if magic != PERFORMANCE_TELEMETRY_MAGIC:
        raise PerformanceTelemetryError("performance telemetry magic is invalid")
    if (
        schema_version != PERFORMANCE_TELEMETRY_SCHEMA_VERSION
        or header_size != PERFORMANCE_TELEMETRY_HEADER_SIZE
        or slot_size != PERFORMANCE_TELEMETRY_SLOT_SIZE
        or capacity != PERFORMANCE_TELEMETRY_CAPACITY
        or capability_flags
            not in {
                PERFORMANCE_FRAME_CAPABILITY,
                PERFORMANCE_FULL_CAPABILITY,
                PERFORMANCE_AGGREGATE_CAPABILITY,
            }
    ):
        raise PerformanceTelemetryError("performance telemetry layout is unsupported")
    header = PerformanceTelemetryHeader(
        process_id=process_id,
        capability_flags=capability_flags,
        process_creation_filetime_utc=creation,
        qpc_frequency=qpc_frequency,
        started_qpc=started_qpc,
        write_sequence=write_sequence,
        overwritten_record_count=overwritten_record_count,
        frame_count=frame_count,
        slow_frame_count=slow_frame_count,
        cache_read_count=cache_read_count,
        cache_read_bytes=cache_read_bytes,
        texture_upload_count=texture_upload_count,
        texture_upload_bytes=texture_upload_bytes,
        producer_error=producer_error,
        active_hook_count=active_hook_count,
    )
    if header.process_id != expected_process_id:
        raise PerformanceTelemetryError("performance telemetry belongs to another process")
    if header.process_creation_filetime_utc != expected_process_creation_filetime_utc:
        raise PerformanceTelemetryError(
            "performance telemetry belongs to another process lifetime"
        )
    records: list[PerformanceRecord] = []
    first_sequence = max(1, header.write_sequence - PERFORMANCE_TELEMETRY_CAPACITY + 1)
    for sequence in range(first_sequence, header.write_sequence + 1):
        slot_index = (sequence - 1) % PERFORMANCE_TELEMETRY_CAPACITY
        offset = PERFORMANCE_TELEMETRY_HEADER_SIZE + slot_index * PERFORMANCE_TELEMETRY_SLOT_SIZE
        records.append(_parse_record(source, offset, sequence, header))
    return PerformanceTelemetrySnapshot(header=header, records=tuple(records))


def _parse_record(
    source: bytes,
    offset: int,
    sequence: int,
    header: PerformanceTelemetryHeader,
) -> PerformanceRecord:
    (
        committed_sequence,
        kind_code,
        flags,
        started_qpc,
        duration_qpc,
        thread_id,
        archive_code,
        byte_count,
        argument0,
        argument1,
        argument2,
        frame_interval_qpc,
        pipeline_gap_qpc,
        reserved,
    ) = _SLOT.unpack_from(source, offset)
    if committed_sequence != sequence:
        raise PerformanceTelemetryError("performance record is not coherently committed")
    try:
        kind = _RECORD_KIND[_PerformanceRecordCode(kind_code)]
        archive = _ARCHIVE_KIND[archive_code]
    except (KeyError, ValueError) as exc:
        raise PerformanceTelemetryError("performance record kind is unknown") from exc
    if flags & ~PERFORMANCE_KNOWN_FLAGS:
        raise PerformanceTelemetryError("performance record contains unsupported flags")
    if started_qpc < header.started_qpc or thread_id == 0:
        raise PerformanceTelemetryError("performance record timing is invalid")
    if kind is PerformanceRecordKind.CACHE_READ and archive is CacheArchive.NONE:
        raise PerformanceTelemetryError("cache read does not identify an archive")
    if kind is PerformanceRecordKind.FRAME_GAP and (
        archive is not CacheArchive.NONE or frame_interval_qpc == 0
    ):
        raise PerformanceTelemetryError("frame gap record is inconsistent")
    if kind is PerformanceRecordKind.FRAME_SUMMARY:
        if (
            header.capability_flags != PERFORMANCE_AGGREGATE_CAPABILITY
            or archive is not CacheArchive.NONE
            or flags & ~PERFORMANCE_SUCCESS_FLAG
        ):
            raise PerformanceTelemetryError("frame summary record is inconsistent")
    elif reserved != 0:
        raise PerformanceTelemetryError("performance record reserved field is nonzero")
    if (
        header.capability_flags == PERFORMANCE_AGGREGATE_CAPABILITY
        and kind is not PerformanceRecordKind.FRAME_SUMMARY
    ):
        raise PerformanceTelemetryError("aggregate profile contains a detailed event")
    if (
        header.capability_flags != PERFORMANCE_AGGREGATE_CAPABILITY
        and kind is PerformanceRecordKind.FRAME_SUMMARY
    ):
        raise PerformanceTelemetryError("detailed profile contains a frame summary")
    return PerformanceRecord(
        sequence=sequence,
        kind=kind,
        flags=flags,
        started_qpc=started_qpc,
        duration_qpc=duration_qpc,
        thread_id=thread_id,
        archive=archive,
        byte_count=byte_count,
        argument0=argument0,
        argument1=argument1,
        argument2=argument2,
        frame_interval_qpc=frame_interval_qpc,
        pipeline_gap_qpc=pipeline_gap_qpc,
        reserved=reserved,
    )


def _bounded_positive(value: object, field_name: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise PerformanceTelemetryError(f"{field_name} must be a bounded positive integer")


__all__ = [
    "CacheArchive",
    "PERFORMANCE_AGGREGATE_CAPABILITY",
    "PERFORMANCE_AGGREGATE_FLAG",
    "PERFORMANCE_CACHE_READ_CAPABILITY",
    "PERFORMANCE_FRAME_CAPABILITY",
    "PERFORMANCE_FRAME_HOOK_COUNT",
    "PERFORMANCE_FULL_CAPABILITY",
    "PERFORMANCE_PIXELS_PRESENT_FLAG",
    "PERFORMANCE_STDIO_IO_FLAG",
    "PERFORMANCE_SUCCESS_FLAG",
    "PERFORMANCE_TELEMETRY_CAPACITY",
    "PERFORMANCE_TELEMETRY_HEADER_SIZE",
    "PERFORMANCE_TELEMETRY_HOOK_COUNT",
    "PERFORMANCE_TELEMETRY_MAGIC",
    "PERFORMANCE_TELEMETRY_SCHEMA_VERSION",
    "PERFORMANCE_TELEMETRY_SIZE",
    "PERFORMANCE_TELEMETRY_SLOT_SIZE",
    "PERFORMANCE_TEXTURE_UPLOAD_CAPABILITY",
    "PERFORMANCE_WIN32_IO_FLAG",
    "PerformanceRecord",
    "PerformanceRecordKind",
    "PerformanceTelemetryError",
    "PerformanceTelemetryHeader",
    "PerformanceTelemetrySnapshot",
    "parse_performance_telemetry",
    "performance_telemetry_mapping_name",
]
