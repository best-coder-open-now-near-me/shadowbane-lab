"""Build-guarded, read-only access to Shadowbane's native message HUD stream."""

from __future__ import annotations

import json
import re
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from shadowbane_lab.client_observation.native_health import (
    NativeMemoryRegion,
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.client_observation.native_log import NativeCombatLogEntry

NATIVE_MESSAGE_HUD_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-0889b39a.native-message-hud.json"
_HUD_MARKER = re.compile(r"\^\\c(?P<color>\d{9})")


class NativeMessageHudError(RuntimeError):
    """Base error for guarded native message-HUD observation."""


class NativeMessageHudCompatibilityError(NativeMessageHudError):
    """Raised when the running executable does not match its calibrated build."""


class NativeMessageHudReadError(NativeMessageHudError):
    """Raised when a native HUD stream cannot be located or read stably."""


class NativeMessageHudProfileLoadError(ValueError):
    """Raised when a native message-HUD profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeMessageHudProfile:
    """Exact build identity and structural limits for one native message HUD."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_scan_address: int
    scan_memory_type: int
    scan_protection: int
    channel_colors: tuple[str, ...]
    minimum_markers_per_buffer: int
    maximum_marker_gap_bytes: int
    maximum_prefix_slack_bytes: int
    maximum_transcript_characters: int
    maximum_candidate_buffers: int
    schema_version: int = NATIVE_MESSAGE_HUD_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.profile_id, "profile_id"),
            (self.executable_name, "executable_name"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        digest = self.executable_sha256.lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal digest")
        if self.pointer_size != 4:
            raise ValueError("only the verified 32-bit Shadowbane client is supported")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if not self.minimum_user_address < self.maximum_scan_address <= self.maximum_user_address:
            raise ValueError("maximum_scan_address must lie inside the calibrated user range")
        for value, field_name in (
            (self.scan_memory_type, "scan_memory_type"),
            (self.scan_protection, "scan_protection"),
            (self.minimum_markers_per_buffer, "minimum_markers_per_buffer"),
            (self.maximum_marker_gap_bytes, "maximum_marker_gap_bytes"),
            (self.maximum_prefix_slack_bytes, "maximum_prefix_slack_bytes"),
            (self.maximum_transcript_characters, "maximum_transcript_characters"),
            (self.maximum_candidate_buffers, "maximum_candidate_buffers"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.minimum_markers_per_buffer < 2:
            raise ValueError("minimum_markers_per_buffer must be at least two")
        if not self.channel_colors or len(set(self.channel_colors)) != len(
            self.channel_colors
        ):
            raise ValueError("channel_colors must contain unique values")
        if any(re.fullmatch(r"\d{9}", color) is None for color in self.channel_colors):
            raise ValueError("channel_colors must use nine decimal digits")
        if self.schema_version != NATIVE_MESSAGE_HUD_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native message-HUD profile version")


@runtime_checkable
class ScanningReadOnlyProcessMemory(ReadOnlyProcessMemory, Protocol):
    def read_block(self, address: int, size: int) -> bytes: ...

    def query_region(self, address: int) -> NativeMemoryRegion: ...

    def find_all(
        self,
        needles: tuple[bytes, ...],
        *,
        memory_type: int | None = None,
        protection: int | None = None,
        maximum_results_per_needle: int = 20_000,
        maximum_address: int | None = None,
    ) -> Mapping[bytes, tuple[int, ...]]: ...

    def find_pointer_values_near(
        self,
        targets: tuple[int, ...],
        *,
        maximum_offset: int,
        memory_type: int | None = None,
        protection: int | None = None,
        maximum_results_per_target: int = 1_000,
        maximum_address: int | None = None,
    ) -> Mapping[int, tuple[tuple[int, int], ...]]: ...


@dataclass(frozen=True, slots=True)
class _HudRecord:
    color: str
    message: str


@dataclass(frozen=True, slots=True)
class _StringMetadata:
    allocator: int
    begin: int
    end: int
    capacity: int


class NativeMessageHudReader:
    """Incrementally reads exact messages from a structurally validated HUD string."""

    def __init__(
        self,
        profile: NativeMessageHudProfile,
        process: ScanningReadOnlyProcessMemory,
        *,
        start_at_end: bool = True,
        stability_attempts: int = 3,
        timestamp_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(profile, NativeMessageHudProfile):
            raise ValueError("profile must be NativeMessageHudProfile")
        if not isinstance(process, ScanningReadOnlyProcessMemory):
            raise ValueError("process must implement ScanningReadOnlyProcessMemory")
        if (
            isinstance(stability_attempts, bool)
            or not isinstance(stability_attempts, int)
            or stability_attempts <= 0
        ):
            raise ValueError("stability_attempts must be a positive integer")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeMessageHudCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeMessageHudCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeMessageHudCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        self._profile = profile
        self._process = process
        self._start_at_end = start_at_end
        self._stability_attempts = stability_attempts
        self._timestamp_factory = timestamp_factory or (lambda: time.strftime("%H:%M:%S"))
        self._pointer_field_address: int | None = None
        self._previous_records: tuple[_HudRecord, ...] | None = None
        self._next_sequence = 0
        self._closed = False

    @property
    def profile(self) -> NativeMessageHudProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    @property
    def attached(self) -> bool:
        return self._pointer_field_address is not None

    def attach(self) -> None:
        """Discover and validate the unique native HUD string for this process."""

        if self._closed:
            raise NativeMessageHudReadError("native message-HUD reader is closed")
        self._pointer_field_address = self._discover_pointer_field()
        records = self._read_stable_records(self._pointer_field_address)
        if self._previous_records is None and self._start_at_end:
            self._previous_records = records

    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        """Return messages appended to the HUD since the previous stable read."""

        if self._closed:
            raise NativeMessageHudReadError("native message-HUD reader is closed")
        if self._pointer_field_address is None:
            self.attach()
        assert self._pointer_field_address is not None
        try:
            current = self._read_stable_records(self._pointer_field_address)
        except NativeMessageHudReadError:
            self._pointer_field_address = self._discover_pointer_field()
            current = self._read_stable_records(self._pointer_field_address)

        previous = self._previous_records
        if previous is None:
            emitted = () if self._start_at_end else current
        elif not current:
            emitted = ()
        else:
            overlap = _largest_record_overlap(previous, current)
            if previous and not overlap:
                raise NativeMessageHudReadError(
                    "native message HUD changed without a trustworthy record overlap"
                )
            emitted = current[overlap:]
        self._previous_records = current

        timestamp = self._timestamp_factory()
        entries = tuple(
            NativeCombatLogEntry(
                sequence=self._next_sequence + index,
                timestamp=timestamp,
                message=record.message,
            )
            for index, record in enumerate(emitted)
        )
        self._next_sequence += len(entries)
        return entries

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeMessageHudReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _discover_pointer_field(self) -> int:
        profile = self._profile
        encoded_prefix = "^\\c".encode("utf-16-le")
        try:
            marker_hits = self._process.find_all(
                (encoded_prefix,),
                memory_type=profile.scan_memory_type,
                protection=profile.scan_protection,
                maximum_address=profile.maximum_scan_address,
            )[encoded_prefix]
        except Exception as exc:
            raise NativeMessageHudReadError(
                f"native message marker scan failed: {type(exc).__name__}"
            ) from exc
        clusters = _marker_clusters(
            marker_hits,
            maximum_gap=profile.maximum_marker_gap_bytes,
            minimum_count=profile.minimum_markers_per_buffer,
        )
        candidates: dict[int, tuple[_HudRecord, ...]] = {}
        for cluster in clusters:
            candidate = self._candidate_run(cluster[0])
            if candidate is None:
                continue
            start, records = candidate
            candidates[start] = records
            if len(candidates) > profile.maximum_candidate_buffers:
                raise NativeMessageHudReadError(
                    "native message scan resolved too many candidate buffers"
                )
        if not candidates:
            raise NativeMessageHudReadError(
                "no structurally plausible native message-HUD buffers were found"
            )

        try:
            pointer_hits = self._process.find_pointer_values_near(
                tuple(candidates),
                maximum_offset=profile.maximum_prefix_slack_bytes,
                memory_type=profile.scan_memory_type,
                protection=profile.scan_protection,
                maximum_results_per_target=1_000,
                maximum_address=profile.maximum_scan_address,
            )
        except Exception as exc:
            raise NativeMessageHudReadError(
                f"native message owner scan failed: {type(exc).__name__}"
            ) from exc
        valid_fields: list[int] = []
        for start in candidates:
            for reference, begin in pointer_hits[start]:
                if reference % profile.pointer_size:
                    continue
                try:
                    metadata = self._read_metadata(reference)
                    records = self._read_stable_records(reference)
                except NativeMessageHudReadError:
                    continue
                if (
                    metadata.begin == begin
                    and metadata.begin <= start < metadata.end
                    and len(records) >= profile.minimum_markers_per_buffer
                ):
                    valid_fields.append(reference)
        unique_fields = tuple(sorted(set(valid_fields)))
        if len(unique_fields) != 1:
            raise NativeMessageHudReadError(
                "native message-HUD owner resolution was ambiguous: "
                f"found {len(unique_fields)} validated fields"
            )
        return unique_fields[0]

    def _candidate_run(self, marker_address: int) -> tuple[int, tuple[_HudRecord, ...]] | None:
        profile = self._profile
        try:
            region = self._process.query_region(marker_address)
        except Exception:
            return None
        maximum_bytes = profile.maximum_transcript_characters * 2
        region_end = region.base_address + region.size
        window_start = max(region.base_address, marker_address - maximum_bytes)
        window_end = min(region_end, marker_address + maximum_bytes)
        try:
            payload = self._process.read_block(window_start, window_end - window_start)
            start_offset, end_offset = _utf16_run_containing(
                payload,
                marker_address - window_start,
            )
            text = payload[start_offset:end_offset].decode("utf-16-le", errors="strict")
        except (UnicodeError, ValueError, NativeMessageHudReadError):
            return None
        records = _parse_hud_records(text, profile.channel_colors)
        if len(records) < profile.minimum_markers_per_buffer:
            return None
        return window_start + start_offset, records

    def _read_stable_records(self, pointer_field_address: int) -> tuple[_HudRecord, ...]:
        for _ in range(self._stability_attempts):
            before = self._read_metadata(pointer_field_address)
            text_size = before.end - before.begin
            try:
                payload = self._process.read_block(before.begin, text_size)
            except Exception as exc:
                try:
                    changed = self._read_metadata(pointer_field_address) != before
                except NativeMessageHudReadError:
                    changed = True
                if changed:
                    continue
                raise NativeMessageHudReadError(
                    f"native message payload read failed: {type(exc).__name__}"
                ) from exc
            after = self._read_metadata(pointer_field_address)
            if before != after:
                continue
            try:
                text = payload.decode("utf-16-le", errors="strict")
            except UnicodeDecodeError as exc:
                raise NativeMessageHudReadError(
                    "native message payload is not valid UTF-16LE"
                ) from exc
            records = _parse_hud_records(text, self._profile.channel_colors)
            if len(records) < self._profile.minimum_markers_per_buffer:
                raise NativeMessageHudReadError(
                    "native message payload no longer contains the calibrated channels"
                )
            return records
        raise NativeMessageHudReadError(
            "native message string changed during every stable-read attempt"
        )

    def _read_metadata(self, pointer_field_address: int) -> _StringMetadata:
        try:
            payload = self._process.read(pointer_field_address - 4, 16)
        except Exception as exc:
            raise NativeMessageHudReadError(
                f"native message metadata read failed: {type(exc).__name__}"
            ) from exc
        if len(payload) != 16:
            raise NativeMessageHudReadError("native message metadata read was partial")
        metadata = _StringMetadata(*struct.unpack("<IIII", payload))
        self._validate_metadata(metadata)
        return metadata

    def _validate_metadata(self, metadata: _StringMetadata) -> None:
        profile = self._profile
        maximum_bytes = profile.maximum_transcript_characters * 2
        values = (metadata.allocator, metadata.begin, metadata.end, metadata.capacity)
        if any(
            value < profile.minimum_user_address or value > profile.maximum_user_address
            for value in values
        ):
            raise NativeMessageHudReadError(
                "native message string metadata lies outside the calibrated user range"
            )
        if metadata.allocator % profile.pointer_size or metadata.begin % 2:
            raise NativeMessageHudReadError("native message string metadata is misaligned")
        if not metadata.begin < metadata.end <= metadata.capacity:
            raise NativeMessageHudReadError("native message string bounds are invalid")
        if (metadata.end - metadata.begin) % 2:
            raise NativeMessageHudReadError("native message string length is not UTF-16 aligned")
        if metadata.capacity - metadata.begin > maximum_bytes:
            raise NativeMessageHudReadError(
                "native message string exceeds the calibrated capacity bound"
            )


def open_windows_native_message_hud_reader(
    profile: NativeMessageHudProfile,
    *,
    process_id: int | None = None,
    start_at_end: bool = True,
) -> NativeMessageHudReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeMessageHudReader(profile, process, start_at_end=start_at_end)
    except Exception:
        process.close()
        raise


def load_bundled_native_message_hud_profile() -> NativeMessageHudProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_message_hud_profile_text(resource.read_text(encoding="utf-8"))


def load_native_message_hud_profile(path: str | Path) -> NativeMessageHudProfile:
    return load_native_message_hud_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_message_hud_profile_text(text: str) -> NativeMessageHudProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeMessageHudProfileLoadError(
            "native message-HUD profile is not valid JSON"
        ) from exc
    try:
        data = _mapping(raw, "native message-HUD profile")
        expected = {
            "schema_version",
            "profile_id",
            "executable_name",
            "executable_sha256",
            "pointer_size",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_scan_address",
            "scan_memory_type",
            "scan_protection",
            "channel_colors",
            "minimum_markers_per_buffer",
            "maximum_marker_gap_bytes",
            "maximum_prefix_slack_bytes",
            "maximum_transcript_characters",
            "maximum_candidate_buffers",
        }
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeMessageHudProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeMessageHudProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        if _integer(data, "schema_version") != NATIVE_MESSAGE_HUD_PROFILE_SCHEMA_VERSION:
            raise NativeMessageHudProfileLoadError(
                "unsupported native message-HUD profile version"
            )
        colors = data["channel_colors"]
        if not isinstance(colors, list) or any(not isinstance(item, str) for item in colors):
            raise NativeMessageHudProfileLoadError("channel_colors must be a string array")
        return NativeMessageHudProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            maximum_scan_address=_integer(data, "maximum_scan_address"),
            scan_memory_type=_integer(data, "scan_memory_type"),
            scan_protection=_integer(data, "scan_protection"),
            channel_colors=tuple(colors),
            minimum_markers_per_buffer=_integer(data, "minimum_markers_per_buffer"),
            maximum_marker_gap_bytes=_integer(data, "maximum_marker_gap_bytes"),
            maximum_prefix_slack_bytes=_integer(data, "maximum_prefix_slack_bytes"),
            maximum_transcript_characters=_integer(data, "maximum_transcript_characters"),
            maximum_candidate_buffers=_integer(data, "maximum_candidate_buffers"),
        )
    except NativeMessageHudProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeMessageHudProfileLoadError(str(exc)) from exc


def _marker_clusters(
    addresses: tuple[int, ...],
    *,
    maximum_gap: int,
    minimum_count: int,
) -> tuple[tuple[int, ...], ...]:
    if not addresses:
        return ()
    clusters: list[tuple[int, ...]] = []
    current = [addresses[0]]
    for address in addresses[1:]:
        if address - current[-1] <= maximum_gap:
            current.append(address)
        else:
            if len(current) >= minimum_count:
                clusters.append(tuple(current))
            current = [address]
    if len(current) >= minimum_count:
        clusters.append(tuple(current))
    return tuple(clusters)


def _utf16_run_containing(payload: bytes, center: int) -> tuple[int, int]:
    if center < 0 or center + 2 > len(payload):
        raise ValueError("UTF-16 probe lies outside its payload")
    start = center
    while start - 2 >= 0 and _valid_utf16_unit(payload[start - 2 : start]):
        start -= 2
    end = center
    while end + 2 <= len(payload) and _valid_utf16_unit(payload[end : end + 2]):
        end += 2
    if end <= start:
        raise ValueError("UTF-16 probe did not resolve a text run")
    return start, end


def _valid_utf16_unit(value: bytes) -> bool:
    unit = int.from_bytes(value, "little")
    return unit in (9, 10, 13) or 0x20 <= unit <= 0xFFFD


def _parse_hud_records(text: str, channel_colors: tuple[str, ...]) -> tuple[_HudRecord, ...]:
    markers = tuple(_HUD_MARKER.finditer(text))
    accepted = set(channel_colors)
    records: list[_HudRecord] = []
    for index, marker in enumerate(markers):
        color = marker.group("color")
        if color not in accepted:
            continue
        has_following_marker = index + 1 < len(markers)
        end = markers[index + 1].start() if has_following_marker else len(text)
        raw_message = text[marker.end() : end]
        if not has_following_marker and not raw_message.endswith(("\r", "\n")):
            continue
        message = raw_message.strip("\x00\r\n")
        if message:
            records.append(_HudRecord(color=color, message=message))
    return tuple(records)


def _largest_record_overlap(
    previous: tuple[_HudRecord, ...],
    current: tuple[_HudRecord, ...],
) -> int:
    maximum = min(len(previous), len(current))
    for count in range(maximum, 0, -1):
        if previous[-count:] == current[:count]:
            return count
    return 0


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeMessageHudProfileLoadError(f"{label} must be an object")
    return value


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeMessageHudProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeMessageHudProfileLoadError(f"{key} must be an integer")
    return value
