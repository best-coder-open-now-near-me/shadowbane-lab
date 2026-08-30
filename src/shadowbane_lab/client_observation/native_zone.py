"""Build-guarded, read-only access to the client's resolved current zone."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from math import isclose, isfinite, sqrt
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.build_compatibility import (
    native_layout_is_compatible,
)
from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_ZONE_PROFILE_SCHEMA_VERSION = 3
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-zone.json"
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
    template_group_offset: int
    template_id_offset: int
    object_type_offset: int
    object_uuid_offset: int
    geometry_bounds_offset: int
    geometry_rotation_offset: int
    geometry_absolute_center_offset: int
    geometry_local_center_offset: int
    geometry_radius_offset: int
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
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal digest")
        if self.pointer_size != 4:
            raise ValueError("only the verified 32-bit Shadowbane client is supported")
        for value, field_name in (
            (self.player_pointer_rva, "player_pointer_rva"),
            (self.current_zone_offset, "current_zone_offset"),
            (self.parent_zone_offset, "parent_zone_offset"),
            (self.zone_name_offset, "zone_name_offset"),
            (self.template_group_offset, "template_group_offset"),
            (self.template_id_offset, "template_id_offset"),
            (self.object_type_offset, "object_type_offset"),
            (self.object_uuid_offset, "object_uuid_offset"),
            (self.geometry_bounds_offset, "geometry_bounds_offset"),
            (self.geometry_rotation_offset, "geometry_rotation_offset"),
            (self.geometry_absolute_center_offset, "geometry_absolute_center_offset"),
            (self.geometry_local_center_offset, "geometry_local_center_offset"),
            (self.geometry_radius_offset, "geometry_radius_offset"),
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
        if abs(self.template_id_offset - self.template_group_offset) != 4:
            raise ValueError("zone template key must be two adjacent 32-bit fields")
        if self.object_uuid_offset != self.object_type_offset + 4:
            raise ValueError("zone object key must be two adjacent 32-bit fields")
        if self.geometry_rotation_offset != self.geometry_bounds_offset + 24:
            raise ValueError("zone rotation must immediately follow the six-float bounds")
        if self.geometry_absolute_center_offset != self.geometry_rotation_offset + 16:
            raise ValueError("zone absolute center must immediately follow its quaternion")
        if self.geometry_local_center_offset != self.geometry_absolute_center_offset + 8:
            raise ValueError("zone local center must immediately follow its absolute center")
        if self.geometry_radius_offset <= self.geometry_local_center_offset + 8:
            raise ValueError("zone radius fields must follow its center fields")
        if self.schema_version != NATIVE_ZONE_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native zone profile version")


@dataclass(frozen=True, slots=True)
class NativeZoneGeometry:
    """Stable runtime placement and local bounds for one active ArcGameZone."""

    minimum_local_x: float
    minimum_local_z: float
    maximum_local_x: float
    maximum_local_z: float
    rotation_w: float
    rotation_x: float
    rotation_y: float
    rotation_z: float
    absolute_center_x: float
    absolute_center_z: float
    local_center_x: float
    local_center_z: float
    radius_x: float
    radius_z: float

    def __post_init__(self) -> None:
        for value in (
            self.minimum_local_x,
            self.minimum_local_z,
            self.maximum_local_x,
            self.maximum_local_z,
            self.rotation_w,
            self.rotation_x,
            self.rotation_y,
            self.rotation_z,
            self.absolute_center_x,
            self.absolute_center_z,
            self.local_center_x,
            self.local_center_z,
            self.radius_x,
            self.radius_z,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError("zone geometry values must be finite numbers")
        if self.radius_x <= 0 or self.radius_z <= 0:
            raise ValueError("zone radii must be positive")
        if self.minimum_local_x >= self.maximum_local_x:
            raise ValueError("zone local x bounds must be ordered")
        if self.minimum_local_z >= self.maximum_local_z:
            raise ValueError("zone local z bounds must be ordered")
        for actual, expected in (
            (self.minimum_local_x, self.local_center_x - self.radius_x),
            (self.maximum_local_x, self.local_center_x + self.radius_x),
            (self.minimum_local_z, self.local_center_z - self.radius_z),
            (self.maximum_local_z, self.local_center_z + self.radius_z),
        ):
            if not isclose(actual, expected, rel_tol=0.0, abs_tol=0.25):
                raise ValueError("zone bounds do not match its center and radii")
        quaternion_norm = sqrt(
            self.rotation_w * self.rotation_w
            + self.rotation_x * self.rotation_x
            + self.rotation_y * self.rotation_y
            + self.rotation_z * self.rotation_z
        )
        if not isclose(quaternion_norm, 1.0, rel_tol=0.0, abs_tol=0.01):
            raise ValueError("zone rotation quaternion is not normalized")

    @property
    def center_lt(self) -> float:
        return self.absolute_center_x

    @property
    def center_lg(self) -> float:
        return -self.absolute_center_z


@dataclass(frozen=True, slots=True)
class NativeZoneIdentity:
    """Cache and server-instance identity for one zone in the active parent chain."""

    depth: int
    name: str
    template_group_id: int
    template_id: int
    object_type: int
    object_uuid: int
    geometry: NativeZoneGeometry

    def __post_init__(self) -> None:
        if isinstance(self.depth, bool) or not isinstance(self.depth, int) or self.depth < 0:
            raise ValueError("zone depth must be a non-negative integer")
        if not isinstance(self.name, str):
            raise ValueError("zone identity name must be a string")
        for value, field_name in (
            (self.template_group_id, "template_group_id"),
            (self.object_type, "object_type"),
            (self.object_uuid, "object_uuid"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if (
            isinstance(self.template_id, bool)
            or not isinstance(self.template_id, int)
            or self.template_id < 0
        ):
            raise ValueError("template_id must be a non-negative integer")
        if not isinstance(self.geometry, NativeZoneGeometry):
            raise ValueError("zone identity geometry must be NativeZoneGeometry")

    @property
    def cache_resolvable(self) -> bool:
        """Whether this runtime zone exposes a concrete CZone resource ID."""
        return self.template_id != 0


@dataclass(frozen=True, slots=True)
class NativeCurrentZoneObservation:
    """One stable client-resolved current-zone identity."""

    name: str
    zone_token: str
    name_source_depth: int
    chain: tuple[NativeZoneIdentity, ...]

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
        if not isinstance(self.chain, tuple) or not self.chain:
            raise ValueError("zone chain must contain at least the current zone")
        if tuple(identity.depth for identity in self.chain) != tuple(range(len(self.chain))):
            raise ValueError("zone chain depths must be contiguous from the current zone")
        if self.name_source_depth >= len(self.chain):
            raise ValueError("name_source_depth must identify an entry in the zone chain")
        if self.chain[self.name_source_depth].name != self.name:
            raise ValueError("resolved zone name must match its source entry")

    @property
    def current(self) -> NativeZoneIdentity:
        return self.chain[0]


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
        if not native_layout_is_compatible(
            profile.executable_sha256,
            process.executable_sha256,
        ):
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
                chain = self._read_zone_chain(zone_pointer)
                name, source_depth = self._resolved_name(chain)
                if self._read_pointer(self._pointer_slot, "player") != player_pointer:
                    continue
                if self._read_pointer(zone_pointer_address, "current-zone") != zone_pointer:
                    continue
                return NativeCurrentZoneObservation(
                    name=name,
                    zone_token=self._zone_token(zone_pointer),
                    name_source_depth=source_depth,
                    chain=chain,
                )
            except NativeCurrentZoneReadError as exc:
                last_error = exc
        if last_error is not None:
            raise NativeCurrentZoneReadError(
                f"current zone remained unreadable during every stable-read attempt: {last_error}"
            ) from last_error
        raise NativeCurrentZoneReadError("current zone changed during every stable-read attempt")

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeCurrentZoneReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_zone_chain(self, current_zone_pointer: int) -> tuple[NativeZoneIdentity, ...]:
        zone_pointer = current_zone_pointer
        visited: set[int] = set()
        chain = []
        for depth in range(self._profile.maximum_parent_depth + 1):
            if zone_pointer in visited:
                raise NativeCurrentZoneReadError("current-zone parent chain contains a cycle")
            visited.add(zone_pointer)
            name = self._read_zone_name(zone_pointer)
            template_group_id, template_id = self._read_identifier_fields(
                zone_pointer,
                self._profile.template_group_offset,
                self._profile.template_id_offset,
                "zone-template",
            )
            object_type, object_uuid = self._read_identifier_fields(
                zone_pointer,
                self._profile.object_type_offset,
                self._profile.object_uuid_offset,
                "zone-object",
            )
            geometry = self._read_zone_geometry(zone_pointer)
            chain.append(
                NativeZoneIdentity(
                    depth=depth,
                    name=name,
                    template_group_id=template_group_id,
                    template_id=template_id,
                    object_type=object_type,
                    object_uuid=object_uuid,
                    geometry=geometry,
                )
            )
            if depth == self._profile.maximum_parent_depth:
                break
            zone_pointer = self._read_pointer(
                zone_pointer + self._profile.parent_zone_offset,
                "parent-zone",
            )
            if zone_pointer == 0:
                break
            self._require_zone_pointer(zone_pointer)
        return tuple(chain)

    def _resolved_name(
        self,
        chain: tuple[NativeZoneIdentity, ...],
    ) -> tuple[str, int]:
        for identity in chain:
            if identity.name:
                return identity.name, identity.depth
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

    def _read_identifier_fields(
        self,
        object_pointer: int,
        first_offset: int,
        second_offset: int,
        label: str,
    ) -> tuple[int, int]:
        begin_offset = min(first_offset, second_offset)
        size = max(first_offset, second_offset) - begin_offset + 4
        address = object_pointer + begin_offset
        first = self._read_exact(address, size, f"{label} identifier")
        second = self._read_exact(address, size, f"{label} identifier")
        if first != second:
            raise NativeCurrentZoneReadError(f"{label} identifier changed during the read")
        return (
            struct.unpack_from("<I", first, first_offset - begin_offset)[0],
            struct.unpack_from("<I", first, second_offset - begin_offset)[0],
        )

    def _read_zone_geometry(self, zone_pointer: int) -> NativeZoneGeometry:
        profile = self._profile
        begin_offset = profile.geometry_bounds_offset
        size = profile.geometry_radius_offset + 8 - begin_offset
        address = zone_pointer + begin_offset
        first = self._read_exact(address, size, "zone geometry")
        second = self._read_exact(address, size, "zone geometry")
        if first != second:
            raise NativeCurrentZoneReadError("zone geometry changed during the read")

        def value(offset: int) -> float:
            return struct.unpack_from("<f", first, offset - begin_offset)[0]

        bounds = profile.geometry_bounds_offset
        rotation = profile.geometry_rotation_offset
        absolute_center = profile.geometry_absolute_center_offset
        local_center = profile.geometry_local_center_offset
        radius = profile.geometry_radius_offset
        try:
            return NativeZoneGeometry(
                minimum_local_x=value(bounds),
                minimum_local_z=value(bounds + 8),
                maximum_local_x=value(bounds + 12),
                maximum_local_z=value(bounds + 20),
                rotation_w=value(rotation),
                rotation_x=value(rotation + 4),
                rotation_y=value(rotation + 8),
                rotation_z=value(rotation + 12),
                absolute_center_x=value(absolute_center),
                absolute_center_z=value(absolute_center + 4),
                local_center_x=value(local_center),
                local_center_z=value(local_center + 4),
                radius_x=value(radius + 4),
                radius_z=value(radius),
            )
        except ValueError as exc:
            raise NativeCurrentZoneReadError(f"zone geometry is invalid: {exc}") from exc

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
            max(profile.template_group_offset, profile.template_id_offset) + 4,
            profile.object_uuid_offset + 4,
            profile.geometry_radius_offset + 8,
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
    *,
    process_id: int | None = None,
) -> NativeCurrentZoneReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeCurrentZoneReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_zone_profile() -> NativeCurrentZoneProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
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
            "template_group_offset",
            "template_id_offset",
            "object_type_offset",
            "object_uuid_offset",
            "geometry_bounds_offset",
            "geometry_rotation_offset",
            "geometry_absolute_center_offset",
            "geometry_local_center_offset",
            "geometry_radius_offset",
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
            raise NativeZoneProfileLoadError(f"unknown fields: {', '.join(sorted(unknown))}")
        return NativeCurrentZoneProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            player_pointer_rva=_integer(data, "player_pointer_rva"),
            current_zone_offset=_integer(data, "current_zone_offset"),
            parent_zone_offset=_integer(data, "parent_zone_offset"),
            zone_name_offset=_integer(data, "zone_name_offset"),
            template_group_offset=_integer(data, "template_group_offset"),
            template_id_offset=_integer(data, "template_id_offset"),
            object_type_offset=_integer(data, "object_type_offset"),
            object_uuid_offset=_integer(data, "object_uuid_offset"),
            geometry_bounds_offset=_integer(data, "geometry_bounds_offset"),
            geometry_rotation_offset=_integer(data, "geometry_rotation_offset"),
            geometry_absolute_center_offset=_integer(data, "geometry_absolute_center_offset"),
            geometry_local_center_offset=_integer(data, "geometry_local_center_offset"),
            geometry_radius_offset=_integer(data, "geometry_radius_offset"),
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
