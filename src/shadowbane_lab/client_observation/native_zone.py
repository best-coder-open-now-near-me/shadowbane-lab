"""Build-guarded, read-only access to the client's resolved current zone."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_ZONE_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-0889b39a.native-zone.json"
_MAX_READ_SIZE = 64


class NativeCurrentZoneError(RuntimeError):
    """Base error for guarded native current-zone observation."""


class NativeCurrentZoneCompatibilityError(NativeCurrentZoneError):
    """Raised when the running executable does not match its calibrated build."""


class NativeCurrentZoneReadError(NativeCurrentZoneError):
    """Raised when the client-resolved current zone cannot be read safely."""


class NativeZoneProfileLoadError(ValueError):
    """Raised when a native current-zone profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeCurrentZoneProfile:
    """Exact executable identity and current-zone fields for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    current_zone_offset: int
    parent_zone_offset: int
    zone_name_offset: int
    string_begin_offset: int
    string_end_offset: int
    string_capacity_offset: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_zone_name_chars: int
    maximum_parent_depth: int
    schema_version: int = NATIVE_ZONE_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.profile_id, "profile_id"),
            (self.executable_name, "executable_name"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        digest = self.executable_sha256.lower()
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal digest")
        if self.pointer_size != 4:
            raise ValueError("only the verified 32-bit Shadowbane client is supported")
        for value, field_name in (
            (self.player_pointer_rva, "player_pointer_rva"),
            (self.current_zone_offset, "current_zone_offset"),
            (self.parent_zone_offset, "parent_zone_offset"),
            (self.zone_name_offset, "zone_name_offset"),
            (self.string_begin_offset, "string_begin_offset"),
            (self.string_end_offset, "string_end_offset"),
            (self.string_capacity_offset, "string_capacity_offset"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
            (self.maximum_zone_name_chars, "maximum_zone_name_chars"),
            (self.maximum_parent_depth, "maximum_parent_depth"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.player_pointer_rva == 0:
            raise ValueError("player_pointer_rva must be positive")
        if (
            self.string_begin_offset,
            self.string_end_offset,
            self.string_capacity_offset,
        ) != (4, 8, 12):
            raise ValueError("unsupported Core::String pointer layout")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.maximum_zone_name_chars > 1024:
            raise ValueError("maximum_zone_name_chars must remain bounded")
        if self.maximum_parent_depth > 64:
            raise ValueError("maximum_parent_depth must remain bounded")
        if self.schema_version != NATIVE_ZONE_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native zone profile version")


@dataclass(frozen=True, slots=True)
class NativeCurrentZoneObservation:
    """One stable client-resolved current-zone identity."""

    name: str
    zone_token: str
    name_source_depth: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("zone name must be a non-empty string")
        if not isinstance(self.zone_token, str) or not self.zone_token.strip():
            raise ValueError("zone_token must be a non-empty string")
        if (
            isinstance(self.name_source_depth, bool)
            or not isinstance(self.name_source_depth, int)
            or self.name_source_depth < 0
        ):
            raise ValueError("name_source_depth must be a non-negative integer")


class NativeCurrentZoneReader:
    """Reads the current zone object already selected by the game client."""

    def __init__(
        self,
        profile: NativeCurrentZoneProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeCurrentZoneProfile):
            raise ValueError("profile must be NativeCurrentZoneProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeCurrentZoneCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeCurrentZoneCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeCurrentZoneCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeCurrentZoneCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.player_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativeCurrentZoneCompatibilityError(
                "calibrated player pointer lies outside the 32-bit user address range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativeCurrentZoneProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeCurrentZoneObservation:
        if self._closed:
            raise NativeCurrentZoneReadError("native current-zone reader is closed")
        last_error: NativeCurrentZoneReadError | None = None
        for _ in range(self._stability_attempts):
            try:
                player_pointer = self._read_pointer(self._pointer_slot, "player")
                self._require_object_pointer(
                    player_pointer,
                    self._profile.current_zone_offset + self._profile.pointer_size,
                    "player",
                )
                zone_pointer_address = player_pointer + self._profile.current_zone_offset
                zone_pointer = self._read_pointer(zone_pointer_address, "current-zone")
                self._require_zone_pointer(zone_pointer)
                name, source_depth = self._resolved_name(zone_pointer)
                if self._read_pointer(self._pointer_slot, "player") != player_pointer:
                    continue
                if self._read_pointer(zone_pointer_address, "current-zone") != zone_pointer:
                    continue
                return NativeCurrentZoneObservation(
                    name=name,
                    zone_token=self._zone_token(zone_pointer),
                    name_source_depth=source_depth,
                )
            except NativeCurrentZoneReadError as exc:
                last_error = exc
        if last_error is not None:
            raise NativeCurrentZoneReadError(
                "current zone remained unreadable during every stable-read attempt: "
                f"{last_error}"
            ) from last_error
        raise NativeCurrentZoneReadError(
            "current zone changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeCurrentZoneReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _resolved_name(self, current_zone_pointer: int) -> tuple[str, int]:
        zone_pointer = current_zone_pointer
        visited: set[int] = set()
        for depth in range(self._profile.maximum_parent_depth + 1):
            if zone_pointer in visited:
                raise NativeCurrentZoneReadError("current-zone parent chain contains a cycle")
            visited.add(zone_pointer)
            name = self._read_zone_name(zone_pointer)
            if name:
                return name, depth
            if depth == self._profile.maximum_parent_depth:
                break
            zone_pointer = self._read_pointer(
                zone_pointer + self._profile.parent_zone_offset,
                "parent-zone",
            )
            if zone_pointer == 0:
                break
            self._require_zone_pointer(zone_pointer)
        raise NativeCurrentZoneReadError(
            "current-zone parent chain contains no non-empty zone name"
        )

    def _read_zone_name(self, zone_pointer: int) -> str:
        profile = self._profile
        string_address = zone_pointer + profile.zone_name_offset
        header_size = profile.string_capacity_offset + profile.pointer_size
        first_header = self._read_exact(string_address, header_size, "zone-name header")
        begin = struct.unpack_from("<I", first_header, profile.string_begin_offset)[0]
        end = struct.unpack_from("<I", first_header, profile.string_end_offset)[0]
        capacity = struct.unpack_from("<I", first_header, profile.string_capacity_offset)[0]
        if begin == 0 or end < begin or capacity < end + 2:
            raise NativeCurrentZoneReadError("zone-name Core::String pointers are invalid")
        byte_length = end - begin
        if byte_length % 2 != 0:
            raise NativeCurrentZoneReadError("zone-name byte length is not UTF-16 aligned")
        if byte_length > profile.maximum_zone_name_chars * 2:
            raise NativeCurrentZoneReadError("zone name exceeds the calibrated length bound")
        if (
            begin < profile.minimum_user_address
            or capacity > profile.maximum_user_address
            or begin % 2 != 0
        ):
            raise NativeCurrentZoneReadError(
                "zone-name buffer is outside the calibrated 32-bit user range"
            )
        raw = self._read_exact(begin, byte_length + 2, "zone-name buffer")
        if raw[-2:] != b"\x00\x00":
            raise NativeCurrentZoneReadError("zone-name buffer is not null terminated")
        second_header = self._read_exact(string_address, header_size, "zone-name header")
        if second_header != first_header:
            raise NativeCurrentZoneReadError("zone-name header changed during the read")
        try:
            name = raw[:-2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise NativeCurrentZoneReadError("zone name is not valid UTF-16LE") from exc
        if "\x00" in name or any(ord(character) < 0x20 for character in name):
            raise NativeCurrentZoneReadError("zone name contains invalid control characters")
        return name

    def _read_pointer(self, address: int, label: str) -> int:
        value = self._read_exact(address, self._profile.pointer_size, f"{label} pointer")
        return struct.unpack("<I", value)[0]

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        if size <= 0:
            raise NativeCurrentZoneReadError(f"{label} read size must be positive")
        chunks = []
        offset = 0
        while offset < size:
            chunk_size = min(_MAX_READ_SIZE, size - offset)
            try:
                chunk = self._process.read(address + offset, chunk_size)
            except Exception as exc:
                raise NativeCurrentZoneReadError(
                    f"could not read {label}: {type(exc).__name__}"
                ) from exc
            if len(chunk) != chunk_size:
                raise NativeCurrentZoneReadError(
                    f"native process backend returned a partial {label}"
                )
            chunks.append(chunk)
            offset += chunk_size
        return b"".join(chunks)

    def _require_zone_pointer(self, pointer: int) -> None:
        profile = self._profile
        final_offset = max(
            profile.parent_zone_offset + profile.pointer_size,
            profile.zone_name_offset + profile.string_capacity_offset + profile.pointer_size,
        )
        self._require_object_pointer(pointer, final_offset, "current-zone")

    def _require_object_pointer(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + size > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeCurrentZoneReadError(
                f"{label} pointer is outside the calibrated 32-bit user range"
            )

    def _zone_token(self, zone_pointer: int) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<II", self._process.pid, zone_pointer))
        return digest.hexdigest()


def open_windows_native_current_zone_reader(
    profile: NativeCurrentZoneProfile,
) -> NativeCurrentZoneReader:
    process = WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
    try:
        return NativeCurrentZoneReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_zone_profile() -> NativeCurrentZoneProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_zone_profile_text(resource.read_text(encoding="utf-8"))


def load_native_zone_profile(path: str | Path) -> NativeCurrentZoneProfile:
    return load_native_zone_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_zone_profile_text(text: str) -> NativeCurrentZoneProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeZoneProfileLoadError("native zone profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "native zone profile")
        expected = {
            "schema_version",
            "profile_id",
            "executable_name",
            "executable_sha256",
            "pointer_size",
            "player_pointer_rva",
            "current_zone_offset",
            "parent_zone_offset",
            "zone_name_offset",
            "string_begin_offset",
            "string_end_offset",
            "string_capacity_offset",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_zone_name_chars",
            "maximum_parent_depth",
        }
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeZoneProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeZoneProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        return NativeCurrentZoneProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            player_pointer_rva=_integer(data, "player_pointer_rva"),
            current_zone_offset=_integer(data, "current_zone_offset"),
            parent_zone_offset=_integer(data, "parent_zone_offset"),
            zone_name_offset=_integer(data, "zone_name_offset"),
            string_begin_offset=_integer(data, "string_begin_offset"),
            string_end_offset=_integer(data, "string_end_offset"),
            string_capacity_offset=_integer(data, "string_capacity_offset"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            maximum_zone_name_chars=_integer(data, "maximum_zone_name_chars"),
            maximum_parent_depth=_integer(data, "maximum_parent_depth"),
            schema_version=_integer(data, "schema_version"),
        )
    except NativeZoneProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeZoneProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeZoneProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeZoneProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeZoneProfileLoadError(f"{key} must be an integer")
    return value
