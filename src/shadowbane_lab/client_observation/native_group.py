"""Build-guarded, read-only access to the client's persisted group roster."""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_GROUP_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-0889b39a.native-group.json"
_MAX_READ_SIZE = 64
_GROUP_MEMBER_ROLE = 0x15
_GROUP_LEADER_ROLE = 0x16


class NativeGroupError(RuntimeError):
    """Base error for guarded native group observation."""


class NativeGroupCompatibilityError(NativeGroupError):
    """Raised when the running executable does not match its calibrated build."""


class NativeGroupReadError(NativeGroupError):
    """Raised when the client's persisted group roster cannot be read safely."""


class NativeGroupProfileLoadError(ValueError):
    """Raised when a native group profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeGroupProfile:
    """Exact executable identity and group-roster fields for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    window_pointer_rva: int
    group_manager_offset: int
    split_gold_offset: int
    local_follow_offset: int
    member_list_offset: int
    list_node_next_offset: int
    list_node_value_offset: int
    member_object_type_offset: int
    member_uuid_offset: int
    member_first_name_offset: int
    member_last_name_offset: int
    member_health_percent_offset: int
    member_stamina_percent_offset: int
    member_mana_percent_offset: int
    member_position_x_offset: int
    member_position_y_offset: int
    member_position_z_offset: int
    member_role_offset: int
    member_follow_offset: int
    string_begin_offset: int
    string_end_offset: int
    string_capacity_offset: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_member_name_chars: int
    maximum_members: int
    maximum_absolute_coordinate: float
    schema_version: int = NATIVE_GROUP_PROFILE_SCHEMA_VERSION

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
            (self.window_pointer_rva, "window_pointer_rva"),
            (self.group_manager_offset, "group_manager_offset"),
            (self.split_gold_offset, "split_gold_offset"),
            (self.local_follow_offset, "local_follow_offset"),
            (self.member_list_offset, "member_list_offset"),
            (self.list_node_value_offset, "list_node_value_offset"),
            (self.member_object_type_offset, "member_object_type_offset"),
            (self.member_uuid_offset, "member_uuid_offset"),
            (self.member_first_name_offset, "member_first_name_offset"),
            (self.member_last_name_offset, "member_last_name_offset"),
            (self.member_health_percent_offset, "member_health_percent_offset"),
            (self.member_stamina_percent_offset, "member_stamina_percent_offset"),
            (self.member_mana_percent_offset, "member_mana_percent_offset"),
            (self.member_position_x_offset, "member_position_x_offset"),
            (self.member_position_y_offset, "member_position_y_offset"),
            (self.member_position_z_offset, "member_position_z_offset"),
            (self.member_role_offset, "member_role_offset"),
            (self.member_follow_offset, "member_follow_offset"),
            (self.string_begin_offset, "string_begin_offset"),
            (self.string_end_offset, "string_end_offset"),
            (self.string_capacity_offset, "string_capacity_offset"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
            (self.maximum_member_name_chars, "maximum_member_name_chars"),
            (self.maximum_members, "maximum_members"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.list_node_next_offset != 0:
            raise ValueError("only the verified list-node next-pointer layout is supported")
        if self.list_node_value_offset != self.pointer_size * 2:
            raise ValueError("only the verified list-node value-pointer layout is supported")
        if self.local_follow_offset != self.split_gold_offset + 1:
            raise ValueError("group-manager toggle bytes must be adjacent")
        if self.member_uuid_offset != self.member_object_type_offset + 4:
            raise ValueError("member object key must be two adjacent 32-bit fields")
        if (
            self.member_stamina_percent_offset,
            self.member_mana_percent_offset,
        ) != (
            self.member_health_percent_offset + 4,
            self.member_health_percent_offset + 8,
        ):
            raise ValueError("member resource percentages must be adjacent 32-bit fields")
        if (
            self.member_position_y_offset,
            self.member_position_z_offset,
        ) != (
            self.member_position_x_offset + 4,
            self.member_position_x_offset + 8,
        ):
            raise ValueError("member position must be three adjacent floats")
        if self.member_position_x_offset != self.member_mana_percent_offset + 4:
            raise ValueError("member resources and position must be contiguous")
        if self.member_role_offset != self.member_position_z_offset + 4:
            raise ValueError("member role must immediately follow position")
        if self.member_follow_offset != self.member_role_offset + 4:
            raise ValueError("member follow flag must immediately follow role")
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
        if self.maximum_member_name_chars > 256:
            raise ValueError("maximum_member_name_chars must remain bounded")
        if self.maximum_members > 10:
            raise ValueError("maximum_members cannot exceed Shadowbane's group size")
        if (
            not isfinite(self.maximum_absolute_coordinate)
            or self.maximum_absolute_coordinate <= 0
        ):
            raise ValueError("maximum_absolute_coordinate must be finite and positive")
        if self.schema_version != NATIVE_GROUP_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native group profile version")


@dataclass(frozen=True, slots=True)
class NativeGroupMemberObservation:
    """One member record maintained by ArcGroupManager."""

    first_name: str
    last_name: str
    object_type: int
    object_uuid: int
    health_percent: int
    stamina_percent: int
    mana_percent: int
    lt: float
    lg: float
    altitude: float
    role_code: int
    follow_enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.first_name, str) or not self.first_name.strip():
            raise ValueError("group member first_name must be non-empty")
        if not isinstance(self.last_name, str):
            raise ValueError("group member last_name must be a string")
        for value, field_name in (
            (self.object_type, "object_type"),
            (self.object_uuid, "object_uuid"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for value, field_name in (
            (self.health_percent, "health_percent"),
            (self.stamina_percent, "stamina_percent"),
            (self.mana_percent, "mana_percent"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be between zero and 100")
        if any(not isfinite(value) for value in (self.lt, self.lg, self.altitude)):
            raise ValueError("group member coordinates must be finite")
        if self.role_code not in (0, _GROUP_MEMBER_ROLE, _GROUP_LEADER_ROLE):
            raise ValueError("group member role code is not recognized")
        if not isinstance(self.follow_enabled, bool):
            raise ValueError("follow_enabled must be boolean")

    @property
    def is_leader(self) -> bool:
        return self.role_code == _GROUP_LEADER_ROLE

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)


@dataclass(frozen=True, slots=True)
class NativeGroupObservation:
    """One stable snapshot of the client group manager."""

    split_gold_enabled: bool
    local_follow_enabled: bool
    members: tuple[NativeGroupMemberObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.split_gold_enabled, bool):
            raise ValueError("split_gold_enabled must be boolean")
        if not isinstance(self.local_follow_enabled, bool):
            raise ValueError("local_follow_enabled must be boolean")
        if not isinstance(self.members, tuple):
            raise ValueError("members must be a tuple")
        if any(not isinstance(member, NativeGroupMemberObservation) for member in self.members):
            raise ValueError("members must contain NativeGroupMemberObservation values")
        identities = {(member.object_type, member.object_uuid) for member in self.members}
        if len(identities) != len(self.members):
            raise ValueError("group member identities must be unique")
        if sum(member.is_leader for member in self.members) > 1:
            raise ValueError("group roster cannot contain multiple leaders")

    @property
    def grouped(self) -> bool:
        return bool(self.members)

    @property
    def leader(self) -> NativeGroupMemberObservation | None:
        return next((member for member in self.members if member.is_leader), None)


class NativeGroupReader:
    """Reads group-member coordinates and follow state already maintained by the client."""

    def __init__(
        self,
        profile: NativeGroupProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeGroupProfile):
            raise ValueError("profile must be NativeGroupProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeGroupCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeGroupCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeGroupCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeGroupCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.window_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativeGroupCompatibilityError(
                "calibrated ArcWindowGame pointer lies outside the 32-bit user range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativeGroupProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeGroupObservation:
        if self._closed:
            raise NativeGroupReadError("native group reader is closed")
        last_error: NativeGroupReadError | None = None
        for _ in range(self._stability_attempts):
            try:
                observation, stability = self._read_snapshot()
                if self._snapshot_is_stable(stability):
                    return observation
            except NativeGroupReadError as exc:
                last_error = exc
        if last_error is not None:
            raise NativeGroupReadError(
                "group roster remained unreadable during every stable-read attempt: "
                f"{last_error}"
            ) from last_error
        raise NativeGroupReadError("group roster changed during every stable-read attempt")

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeGroupReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_snapshot(
        self,
    ) -> tuple[
        NativeGroupObservation,
        tuple[int, int, int, int, bytes, tuple[tuple[int, int, int], ...]],
    ]:
        profile = self._profile
        window = self._read_pointer(self._pointer_slot, "ArcWindowGame")
        self._require_object_pointer(
            window,
            profile.group_manager_offset + profile.pointer_size,
            "ArcWindowGame",
        )
        manager_address = window + profile.group_manager_offset
        manager = self._read_pointer(manager_address, "ArcGroupManager")
        self._require_object_pointer(
            manager,
            max(profile.member_list_offset + 4, profile.local_follow_offset + 1),
            "ArcGroupManager",
        )
        toggle_bytes = self._read_exact(
            manager + profile.split_gold_offset,
            2,
            "group-manager toggles",
        )
        if any(value not in (0, 1) for value in toggle_bytes):
            raise NativeGroupReadError("group-manager toggle bytes are not boolean")
        sentinel_address = manager + profile.member_list_offset
        sentinel = self._read_pointer(sentinel_address, "group-list sentinel")
        self._require_object_pointer(
            sentinel,
            profile.list_node_value_offset + profile.pointer_size,
            "group-list sentinel",
        )

        members = []
        links = []
        visited = {sentinel}
        head = self._read_pointer(
            sentinel + profile.list_node_next_offset,
            "group-list head",
        )
        node = head
        while node != sentinel:
            if node in visited:
                raise NativeGroupReadError("group member list contains a cycle")
            if len(members) >= profile.maximum_members:
                raise NativeGroupReadError("group member list exceeds the calibrated size")
            visited.add(node)
            self._require_object_pointer(
                node,
                profile.list_node_value_offset + profile.pointer_size,
                "group-list node",
            )
            next_node = self._read_pointer(
                node + profile.list_node_next_offset,
                "group-list next",
            )
            entry = self._read_pointer(
                node + profile.list_node_value_offset,
                "ArcGrouperEntry",
            )
            self._require_object_pointer(
                entry,
                profile.member_follow_offset + 1,
                "ArcGrouperEntry",
            )
            members.append(self._read_member(entry))
            links.append((node, next_node, entry))
            node = next_node
        return (
            NativeGroupObservation(
                split_gold_enabled=bool(toggle_bytes[0]),
                local_follow_enabled=bool(toggle_bytes[1]),
                members=tuple(members),
            ),
            (window, manager, sentinel, head, toggle_bytes, tuple(links)),
        )

    def _snapshot_is_stable(
        self,
        stability: tuple[
            int,
            int,
            int,
            int,
            bytes,
            tuple[tuple[int, int, int], ...],
        ],
    ) -> bool:
        window, manager, sentinel, head, toggle_bytes, links = stability
        profile = self._profile
        if self._read_pointer(self._pointer_slot, "ArcWindowGame") != window:
            return False
        if (
            self._read_pointer(window + profile.group_manager_offset, "ArcGroupManager")
            != manager
        ):
            return False
        if (
            self._read_pointer(manager + profile.member_list_offset, "group-list sentinel")
            != sentinel
        ):
            return False
        if (
            self._read_exact(
                manager + profile.split_gold_offset,
                2,
                "group-manager toggles",
            )
            != toggle_bytes
        ):
            return False
        if (
            self._read_pointer(
                sentinel + profile.list_node_next_offset,
                "group-list head",
            )
            != head
        ):
            return False
        for node, expected_next, expected_entry in links:
            if (
                self._read_pointer(
                    node + profile.list_node_next_offset,
                    "group-list next",
                )
                != expected_next
            ):
                return False
            if (
                self._read_pointer(
                    node + profile.list_node_value_offset,
                    "ArcGrouperEntry",
                )
                != expected_entry
            ):
                return False
        return True

    def _read_member(self, entry: int) -> NativeGroupMemberObservation:
        profile = self._profile
        object_type, object_uuid = self._read_identifier(
            entry + profile.member_object_type_offset,
            "group-member",
        )
        first_name = self._read_string(
            entry + profile.member_first_name_offset,
            "group-member first name",
        )
        last_name = self._read_string(
            entry + profile.member_last_name_offset,
            "group-member last name",
        )
        if not first_name.strip():
            raise NativeGroupReadError("group-member first name is empty")
        if object_type == 0 or object_uuid == 0:
            raise NativeGroupReadError("group-member identifier contains zero")
        data_start = profile.member_health_percent_offset
        data_size = profile.member_follow_offset - data_start + 1
        first = self._read_exact(entry + data_start, data_size, "group-member state")
        second = self._read_exact(entry + data_start, data_size, "group-member state")
        if first != second:
            raise NativeGroupReadError("group-member state changed during the read")
        health, stamina, mana = struct.unpack_from("<iii", first, 0)
        position_offset = profile.member_position_x_offset - data_start
        native_x, native_y, native_z = struct.unpack_from("<fff", first, position_offset)
        role_offset = profile.member_role_offset - data_start
        follow_offset = profile.member_follow_offset - data_start
        role_code = struct.unpack_from("<I", first, role_offset)[0]
        follow_value = first[follow_offset]
        if any(not 0 <= value <= 100 for value in (health, stamina, mana)):
            raise NativeGroupReadError("group-member resource percentage is out of range")
        if follow_value not in (0, 1):
            raise NativeGroupReadError("group-member follow flag is not boolean")
        if role_code not in (0, _GROUP_MEMBER_ROLE, _GROUP_LEADER_ROLE):
            raise NativeGroupReadError("group-member role code is not recognized")
        if any(
            not isfinite(value) or abs(value) > profile.maximum_absolute_coordinate
            for value in (native_x, native_y, native_z)
        ):
            raise NativeGroupReadError("group-member position is outside calibrated bounds")
        return NativeGroupMemberObservation(
            first_name=first_name,
            last_name=last_name,
            object_type=object_type,
            object_uuid=object_uuid,
            health_percent=health,
            stamina_percent=stamina,
            mana_percent=mana,
            lt=native_x,
            lg=-native_z,
            altitude=native_y,
            role_code=role_code,
            follow_enabled=bool(follow_value),
        )

    def _read_string(self, address: int, label: str) -> str:
        profile = self._profile
        header_size = profile.string_capacity_offset + profile.pointer_size
        first_header = self._read_exact(address, header_size, f"{label} header")
        begin = struct.unpack_from("<I", first_header, profile.string_begin_offset)[0]
        end = struct.unpack_from("<I", first_header, profile.string_end_offset)[0]
        capacity = struct.unpack_from("<I", first_header, profile.string_capacity_offset)[0]
        if (begin, end, capacity) == (0, 0, 0):
            if self._read_exact(address, header_size, f"{label} header") != first_header:
                raise NativeGroupReadError(f"{label} header changed during the read")
            return ""
        if begin == 0 or end < begin or capacity < end + 2:
            raise NativeGroupReadError(f"{label} Core::String pointers are invalid")
        byte_length = end - begin
        if byte_length % 2 != 0:
            raise NativeGroupReadError(f"{label} byte length is not UTF-16 aligned")
        if byte_length > profile.maximum_member_name_chars * 2:
            raise NativeGroupReadError(f"{label} exceeds the calibrated length bound")
        if (
            begin < profile.minimum_user_address
            or capacity > profile.maximum_user_address
            or begin % 2 != 0
        ):
            raise NativeGroupReadError(f"{label} buffer is outside the 32-bit user range")
        raw = self._read_exact(begin, byte_length + 2, f"{label} buffer")
        if raw[-2:] != b"\x00\x00":
            raise NativeGroupReadError(f"{label} buffer is not null terminated")
        if self._read_exact(address, header_size, f"{label} header") != first_header:
            raise NativeGroupReadError(f"{label} header changed during the read")
        try:
            value = raw[:-2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise NativeGroupReadError(f"{label} is not valid UTF-16LE") from exc
        if "\x00" in value or any(ord(character) < 0x20 for character in value):
            raise NativeGroupReadError(f"{label} contains invalid control characters")
        return value

    def _read_identifier(self, address: int, label: str) -> tuple[int, int]:
        first = self._read_exact(address, 8, f"{label} identifier")
        second = self._read_exact(address, 8, f"{label} identifier")
        if first != second:
            raise NativeGroupReadError(f"{label} identifier changed during the read")
        return cast(tuple[int, int], struct.unpack("<II", first))

    def _read_pointer(self, address: int, label: str) -> int:
        return struct.unpack(
            "<I",
            self._read_exact(address, self._profile.pointer_size, f"{label} pointer"),
        )[0]

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        if size <= 0:
            raise NativeGroupReadError(f"{label} read size must be positive")
        chunks = []
        offset = 0
        while offset < size:
            chunk_size = min(_MAX_READ_SIZE, size - offset)
            try:
                chunk = self._process.read(address + offset, chunk_size)
            except Exception as exc:
                raise NativeGroupReadError(
                    f"could not read {label}: {type(exc).__name__}"
                ) from exc
            if len(chunk) != chunk_size:
                raise NativeGroupReadError(
                    f"native process backend returned a partial {label}"
                )
            chunks.append(chunk)
            offset += chunk_size
        return b"".join(chunks)

    def _require_object_pointer(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + size > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeGroupReadError(
                f"{label} pointer is outside the calibrated 32-bit user range"
            )


def open_windows_native_group_reader(profile: NativeGroupProfile) -> NativeGroupReader:
    process = WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
    try:
        return NativeGroupReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_group_profile() -> NativeGroupProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_group_profile_text(resource.read_text(encoding="utf-8"))


def load_native_group_profile(path: str | Path) -> NativeGroupProfile:
    return load_native_group_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_group_profile_text(text: str) -> NativeGroupProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeGroupProfileLoadError("native group profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "native group profile")
        expected = set(NativeGroupProfile.__dataclass_fields__)
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeGroupProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeGroupProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        values = {
            key: (
                _string(data, key)
                if key in {"profile_id", "executable_name", "executable_sha256"}
                else _number(data, key)
                if key == "maximum_absolute_coordinate"
                else _integer(data, key)
            )
            for key in expected
        }
        return NativeGroupProfile(**values)
    except NativeGroupProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeGroupProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeGroupProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeGroupProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeGroupProfileLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeGroupProfileLoadError(f"{key} must be numeric")
    return float(value)
