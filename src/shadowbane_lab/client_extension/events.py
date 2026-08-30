"""Versioned shared-memory events emitted by one exact client extension lifetime."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from math import isfinite

EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION = 1
EXTENSION_EVENT_CHANNEL_MAGIC = b"WBEXTV1\0"
EXTENSION_EVENT_CHANNEL_HEADER_SIZE = 80
EXTENSION_EVENT_CHANNEL_SLOT_SIZE = 80
EXTENSION_EVENT_CHANNEL_CAPACITY = 64
EXTENSION_EVENT_CHANNEL_SIZE = (
    EXTENSION_EVENT_CHANNEL_HEADER_SIZE
    + EXTENSION_EVENT_CHANNEL_SLOT_SIZE * EXTENSION_EVENT_CHANNEL_CAPACITY
)
EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION = 1 << 0
EXTENSION_EVENT_CHANNEL_FLAG_TAGGED_TEST_INPUT = 1 << 1

_HEADER = struct.Struct("<8s6I4QIIQ")
_SLOT = struct.Struct("<QIIQQddQiiii8x")
_MAX_WORLD_COORDINATE = float(0xFFFFFFFF)


class ExtensionEventError(ValueError):
    """Raised when an extension event channel violates its versioned contract."""


class ExtensionEventKind(IntEnum):
    WORLD_MAP_DESTINATION = 1


class ExtensionPointerButtonCode(IntEnum):
    LEFT = 1
    RIGHT = 2


class ExtensionPointerButton(StrEnum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class ExtensionEventChannelHeader:
    """Stable channel metadata plus producer/consumer sequence counters."""

    process_id: int
    process_creation_filetime_utc: int
    write_sequence: int
    read_sequence: int
    dropped_event_count: int
    producer_error: int
    capability_flags: int
    consumer_process_id: int = 0
    consumer_heartbeat_tick: int = 0
    schema_version: int = EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION
    header_size: int = EXTENSION_EVENT_CHANNEL_HEADER_SIZE
    slot_size: int = EXTENSION_EVENT_CHANNEL_SLOT_SIZE
    capacity: int = EXTENSION_EVENT_CHANNEL_CAPACITY

    def __post_init__(self) -> None:
        if self.schema_version != EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION:
            raise ExtensionEventError("unsupported extension event channel version")
        if self.header_size != EXTENSION_EVENT_CHANNEL_HEADER_SIZE:
            raise ExtensionEventError("extension event header size is unsupported")
        if self.slot_size != EXTENSION_EVENT_CHANNEL_SLOT_SIZE:
            raise ExtensionEventError("extension event slot size is unsupported")
        if self.capacity != EXTENSION_EVENT_CHANNEL_CAPACITY:
            raise ExtensionEventError("extension event capacity is unsupported")
        _bounded_positive(self.process_id, "process_id", 0xFFFFFFFF)
        _bounded_positive(
            self.process_creation_filetime_utc,
            "process_creation_filetime_utc",
            0xFFFFFFFFFFFFFFFF,
        )
        for value, field_name, maximum in (
            (self.write_sequence, "write_sequence", 0xFFFFFFFFFFFFFFFF),
            (self.read_sequence, "read_sequence", 0xFFFFFFFFFFFFFFFF),
            (self.dropped_event_count, "dropped_event_count", 0xFFFFFFFFFFFFFFFF),
            (self.producer_error, "producer_error", 0xFFFFFFFF),
            (self.capability_flags, "capability_flags", 0xFFFFFFFF),
            (self.consumer_process_id, "consumer_process_id", 0xFFFFFFFF),
            (
                self.consumer_heartbeat_tick,
                "consumer_heartbeat_tick",
                0xFFFFFFFFFFFFFFFF,
            ),
        ):
            _bounded_nonnegative(value, field_name, maximum)
        if self.write_sequence < self.read_sequence:
            raise ExtensionEventError("extension event sequences move backwards")
        if self.write_sequence - self.read_sequence > self.capacity:
            raise ExtensionEventError("extension event channel exceeds its bounded capacity")
        unknown_flags = self.capability_flags & ~(
            EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION
            | EXTENSION_EVENT_CHANNEL_FLAG_TAGGED_TEST_INPUT
        )
        if unknown_flags:
            raise ExtensionEventError("extension event channel has unknown capabilities")
        if (self.consumer_process_id == 0) != (self.consumer_heartbeat_tick == 0):
            raise ExtensionEventError("extension event consumer lease is incomplete")

    @property
    def pending_count(self) -> int:
        return self.write_sequence - self.read_sequence


@dataclass(frozen=True, slots=True)
class ExtensionWorldMapDestinationEvent:
    """One immutable map destination captured inside the owning game process."""

    sequence: int
    process_id: int
    process_creation_filetime_utc: int
    captured_at_filetime_utc: int
    window_handle: int
    button: ExtensionPointerButton
    lt: float
    lg: float
    snapshot_token: str
    desktop_screen_x: int
    desktop_screen_y: int
    client_x: int
    client_y: int
    kind: str = "world_map_destination"
    schema_version: int = EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION:
            raise ExtensionEventError("unsupported extension event version")
        if self.kind != "world_map_destination":
            raise ExtensionEventError("unsupported extension event kind")
        _bounded_positive(self.sequence, "sequence", 0xFFFFFFFFFFFFFFFF)
        _bounded_positive(self.process_id, "process_id", 0xFFFFFFFF)
        _bounded_positive(
            self.process_creation_filetime_utc,
            "process_creation_filetime_utc",
            0xFFFFFFFFFFFFFFFF,
        )
        _bounded_positive(
            self.captured_at_filetime_utc,
            "captured_at_filetime_utc",
            0xFFFFFFFFFFFFFFFF,
        )
        if self.captured_at_filetime_utc < self.process_creation_filetime_utc:
            raise ExtensionEventError("extension event predates its process lifetime")
        _bounded_positive(self.window_handle, "window_handle", 0xFFFFFFFFFFFFFFFF)
        if not isinstance(self.button, ExtensionPointerButton):
            raise ExtensionEventError("button must be an ExtensionPointerButton")
        for value, field_name in ((self.lt, "lt"), (self.lg, "lg")):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ExtensionEventError(f"{field_name} must be numeric")
            if not isfinite(value) or not 0.0 <= value <= _MAX_WORLD_COORDINATE:
                raise ExtensionEventError(
                    f"{field_name} must be a finite non-negative world coordinate"
                )
        if (
            not isinstance(self.snapshot_token, str)
            or len(self.snapshot_token) != 16
            or any(character not in "0123456789abcdef" for character in self.snapshot_token)
        ):
            raise ExtensionEventError("snapshot_token must be 16 lowercase hexadecimal digits")
        for value, field_name in (
            (self.desktop_screen_x, "desktop_screen_x"),
            (self.desktop_screen_y, "desktop_screen_y"),
            (self.client_x, "client_x"),
            (self.client_y, "client_y"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ExtensionEventError(f"{field_name} must be an integer")
            if not -(1 << 31) <= value < (1 << 31):
                raise ExtensionEventError(f"{field_name} must fit signed 32-bit storage")

    @property
    def process_identity(self) -> tuple[int, int]:
        return self.process_id, self.process_creation_filetime_utc

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "sequence": self.sequence,
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.process_creation_filetime_utc,
            "captured_at_filetime_utc": self.captured_at_filetime_utc,
            "window_handle": self.window_handle,
            "button": self.button.value,
            "lt": self.lt,
            "lg": self.lg,
            "snapshot_token": self.snapshot_token,
            "desktop_screen_x": self.desktop_screen_x,
            "desktop_screen_y": self.desktop_screen_y,
            "client_x": self.client_x,
            "client_y": self.client_y,
        }


@dataclass(frozen=True, slots=True)
class ExtensionEventChannelSnapshot:
    """One coherent bounded read of the channel header and committed slots."""

    header: ExtensionEventChannelHeader
    events: tuple[ExtensionWorldMapDestinationEvent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.header, ExtensionEventChannelHeader):
            raise ExtensionEventError("header must be ExtensionEventChannelHeader")
        if not isinstance(self.events, tuple) or any(
            not isinstance(event, ExtensionWorldMapDestinationEvent) for event in self.events
        ):
            raise ExtensionEventError("events must contain extension events")
        if len(self.events) != self.header.pending_count:
            raise ExtensionEventError("event count differs from channel sequence counters")


def extension_event_mapping_name(
    process_id: int,
    process_creation_filetime_utc: int,
) -> str:
    _bounded_positive(process_id, "process_id", 0xFFFFFFFF)
    _bounded_positive(
        process_creation_filetime_utc,
        "process_creation_filetime_utc",
        0xFFFFFFFFFFFFFFFF,
    )
    return f"Local\\ShadowbaneLab.Extension.Events.{process_id}.{process_creation_filetime_utc}"


def extension_event_signal_name(
    process_id: int,
    process_creation_filetime_utc: int,
) -> str:
    _bounded_positive(process_id, "process_id", 0xFFFFFFFF)
    _bounded_positive(
        process_creation_filetime_utc,
        "process_creation_filetime_utc",
        0xFFFFFFFFFFFFFFFF,
    )
    return f"Local\\ShadowbaneLab.Extension.Signal.{process_id}.{process_creation_filetime_utc}"


def parse_extension_event_channel(
    payload: bytes | bytearray | memoryview,
    *,
    expected_process_id: int,
    expected_process_creation_filetime_utc: int,
) -> ExtensionEventChannelSnapshot:
    """Validate one complete shared-memory image without advancing its consumer."""

    source = bytes(payload)
    if len(source) != EXTENSION_EVENT_CHANNEL_SIZE:
        raise ExtensionEventError("extension event channel has an unexpected size")
    (
        magic,
        schema_version,
        header_size,
        slot_size,
        capacity,
        process_id,
        capability_flags,
        process_creation_filetime_utc,
        write_sequence,
        read_sequence,
        dropped_event_count,
        producer_error,
        consumer_process_id,
        consumer_heartbeat_tick,
    ) = _HEADER.unpack_from(source)
    if magic != EXTENSION_EVENT_CHANNEL_MAGIC:
        raise ExtensionEventError("extension event channel magic is invalid")
    header = ExtensionEventChannelHeader(
        schema_version=schema_version,
        header_size=header_size,
        slot_size=slot_size,
        capacity=capacity,
        process_id=process_id,
        capability_flags=capability_flags,
        process_creation_filetime_utc=process_creation_filetime_utc,
        write_sequence=write_sequence,
        read_sequence=read_sequence,
        dropped_event_count=dropped_event_count,
        producer_error=producer_error,
        consumer_process_id=consumer_process_id,
        consumer_heartbeat_tick=consumer_heartbeat_tick,
    )
    if header.process_id != expected_process_id:
        raise ExtensionEventError("extension event channel belongs to another process")
    if header.process_creation_filetime_utc != expected_process_creation_filetime_utc:
        raise ExtensionEventError("extension event channel belongs to another process lifetime")
    events: list[ExtensionWorldMapDestinationEvent] = []
    for sequence in range(header.read_sequence + 1, header.write_sequence + 1):
        slot_index = (sequence - 1) % header.capacity
        offset = header.header_size + slot_index * header.slot_size
        events.append(_parse_world_map_slot(source, offset, sequence, header))
    return ExtensionEventChannelSnapshot(header=header, events=tuple(events))


def _parse_world_map_slot(
    source: bytes,
    offset: int,
    expected_sequence: int,
    header: ExtensionEventChannelHeader,
) -> ExtensionWorldMapDestinationEvent:
    (
        committed_sequence,
        kind_code,
        button_code,
        captured_at_filetime_utc,
        window_handle,
        lt,
        lg,
        snapshot_hash,
        desktop_screen_x,
        desktop_screen_y,
        client_x,
        client_y,
    ) = _SLOT.unpack_from(source, offset)
    if committed_sequence != expected_sequence:
        raise ExtensionEventError("extension event slot is not coherently committed")
    try:
        kind = ExtensionEventKind(kind_code)
    except ValueError as exc:
        raise ExtensionEventError("extension event kind is unknown") from exc
    if kind is not ExtensionEventKind.WORLD_MAP_DESTINATION:
        raise ExtensionEventError("extension event kind is unsupported")
    try:
        button = ExtensionPointerButton(
            {
                ExtensionPointerButtonCode.LEFT: "left",
                ExtensionPointerButtonCode.RIGHT: "right",
            }[ExtensionPointerButtonCode(button_code)]
        )
    except (KeyError, ValueError) as exc:
        raise ExtensionEventError("extension pointer button is unknown") from exc
    return ExtensionWorldMapDestinationEvent(
        sequence=expected_sequence,
        process_id=header.process_id,
        process_creation_filetime_utc=header.process_creation_filetime_utc,
        captured_at_filetime_utc=captured_at_filetime_utc,
        window_handle=window_handle,
        button=button,
        lt=lt,
        lg=lg,
        snapshot_token=f"{snapshot_hash:016x}",
        desktop_screen_x=desktop_screen_x,
        desktop_screen_y=desktop_screen_y,
        client_x=client_x,
        client_y=client_y,
    )


def _bounded_positive(value: object, field_name: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise ExtensionEventError(f"{field_name} must be a bounded positive integer")


def _bounded_nonnegative(value: object, field_name: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ExtensionEventError(f"{field_name} must be a bounded non-negative integer")


__all__ = [
    "EXTENSION_EVENT_CHANNEL_CAPACITY",
    "EXTENSION_EVENT_CHANNEL_FLAG_WORLD_MAP_DESTINATION",
    "EXTENSION_EVENT_CHANNEL_FLAG_TAGGED_TEST_INPUT",
    "EXTENSION_EVENT_CHANNEL_HEADER_SIZE",
    "EXTENSION_EVENT_CHANNEL_MAGIC",
    "EXTENSION_EVENT_CHANNEL_SCHEMA_VERSION",
    "EXTENSION_EVENT_CHANNEL_SIZE",
    "EXTENSION_EVENT_CHANNEL_SLOT_SIZE",
    "ExtensionEventChannelHeader",
    "ExtensionEventChannelSnapshot",
    "ExtensionEventError",
    "ExtensionEventKind",
    "ExtensionPointerButton",
    "ExtensionPointerButtonCode",
    "ExtensionWorldMapDestinationEvent",
    "extension_event_mapping_name",
    "extension_event_signal_name",
    "parse_extension_event_channel",
]
