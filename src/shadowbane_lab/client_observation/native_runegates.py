"""Build-guarded, read-only access to the server-supplied runegate registry."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.build_compatibility import (
    native_layout_is_compatible,
)
from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_RUNEGATE_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-runegates.json"
_MAX_READ_SIZE = 64


class NativeRunegateRegistryError(RuntimeError):
    """Base error for guarded native runegate observation."""


class NativeRunegateRegistryCompatibilityError(NativeRunegateRegistryError):
    """Raised when the running executable does not match its calibrated build."""


class NativeRunegateRegistryReadError(NativeRunegateRegistryError):
    """Raised when the server-supplied runegate registry cannot be read safely."""


class NativeRunegateRegistryProfileLoadError(ValueError):
    """Raised when a native runegate profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeRunegateRegistryProfile:
    """Exact executable identity and runegate-tree fields for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    registry_pointer_rva: int
    registry_tree_offset: int
    tree_head_pointer_offset: int
    head_first_node_offset: int
    node_parent_offset: int
    node_left_offset: int
    node_right_offset: int
    object_type_offset: int
    object_uuid_offset: int
    zone_name_offset: int
    latitude_offset: int
    altitude_offset: int
    longitude_offset: int
    longitude_multiplier: float
    string_begin_offset: int
    string_end_offset: int
    string_capacity_offset: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_zone_name_chars: int
    maximum_runegates: int
    maximum_absolute_coordinate: float
    schema_version: int = NATIVE_RUNEGATE_PROFILE_SCHEMA_VERSION

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
        non_negative_offsets = (
            "tree_head_pointer_offset",
            "node_parent_offset",
        )
        for field_name in (
            "registry_pointer_rva",
            "registry_tree_offset",
            "tree_head_pointer_offset",
            "head_first_node_offset",
            "node_parent_offset",
            "node_left_offset",
            "node_right_offset",
            "object_type_offset",
            "object_uuid_offset",
            "zone_name_offset",
            "latitude_offset",
            "altitude_offset",
            "longitude_offset",
            "string_begin_offset",
            "string_end_offset",
            "string_capacity_offset",
        ):
            value = getattr(self, field_name)
            minimum = 0 if field_name in non_negative_offsets else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                qualifier = "non-negative" if minimum == 0 else "positive"
                raise ValueError(f"{field_name} must be a {qualifier} integer")
        for value, field_name in (
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
            (self.maximum_zone_name_chars, "maximum_zone_name_chars"),
            (self.maximum_runegates, "maximum_runegates"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.registry_pointer_rva == 0:
            raise ValueError("registry_pointer_rva must be positive")
        if (
            self.node_parent_offset,
            self.node_left_offset,
            self.node_right_offset,
        ) != (4, 8, 12):
            raise ValueError("unsupported runegate red-black-tree node layout")
        if self.object_uuid_offset != self.object_type_offset + 4:
            raise ValueError("runegate object key must be two adjacent 32-bit fields")
        if self.zone_name_offset != self.object_uuid_offset + 4:
            raise ValueError("runegate zone name must immediately follow its object key")
        if (
            self.string_begin_offset,
            self.string_end_offset,
            self.string_capacity_offset,
        ) != (4, 8, 12):
            raise ValueError("unsupported Core::String pointer layout")
        if (
            self.altitude_offset,
            self.longitude_offset,
        ) != (self.latitude_offset + 4, self.latitude_offset + 8):
            raise ValueError("runegate coordinates must be three adjacent floats")
        if self.latitude_offset != self.zone_name_offset + 24:
            raise ValueError("runegate coordinates must immediately follow Core::String")
        if self.longitude_multiplier not in (-1.0, 1.0):
            raise ValueError("longitude_multiplier must be -1 or 1")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.maximum_zone_name_chars > 256:
            raise ValueError("maximum_zone_name_chars must remain bounded")
        if self.maximum_runegates > 1024:
            raise ValueError("maximum_runegates must remain bounded")
        if (
            not isfinite(self.maximum_absolute_coordinate)
            or self.maximum_absolute_coordinate <= 0
        ):
            raise ValueError("maximum_absolute_coordinate must be finite and positive")
        if self.schema_version != NATIVE_RUNEGATE_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native runegate profile version")


@dataclass(frozen=True, slots=True)
class NativeRunegateObservation:
    """One runegate record supplied by the active game server."""

    object_type: int
    object_uuid: int
    zone_name: str
    lt: float
    lg: float
    altitude: float

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.object_type, "object_type"),
            (self.object_uuid, "object_uuid"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if not isinstance(self.zone_name, str):
            raise ValueError("zone_name must be a string")
        if any(not isfinite(value) for value in (self.lt, self.lg, self.altitude)):
            raise ValueError("runegate coordinates must be finite")


@dataclass(frozen=True, slots=True)
class NativeRunegateRegistryObservation:
    """One stable snapshot of the server-supplied runegate registry."""

    runegates: tuple[NativeRunegateObservation, ...]
    registry_token: str

    def __post_init__(self) -> None:
        if not isinstance(self.runegates, tuple) or any(
            not isinstance(item, NativeRunegateObservation) for item in self.runegates
        ):
            raise ValueError("runegates must contain NativeRunegateObservation values")
        identities = {(item.object_type, item.object_uuid) for item in self.runegates}
        if len(identities) != len(self.runegates):
            raise ValueError("runegate identities must be unique")
        if not isinstance(self.registry_token, str) or not self.registry_token.strip():
            raise ValueError("registry_token must be non-empty")


class NativeRunegateRegistryReader:
    """Reads the runegate tree populated by the server's CityData message."""

    def __init__(
        self,
        profile: NativeRunegateRegistryProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeRunegateRegistryProfile):
            raise ValueError("profile must be NativeRunegateRegistryProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeRunegateRegistryCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if not native_layout_is_compatible(
            profile.executable_sha256,
            process.executable_sha256,
        ):
            raise NativeRunegateRegistryCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeRunegateRegistryCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeRunegateRegistryCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.registry_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativeRunegateRegistryCompatibilityError(
                "calibrated runegate-registry pointer lies outside the 32-bit user range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativeRunegateRegistryProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeRunegateRegistryObservation:
        if self._closed:
            raise NativeRunegateRegistryReadError("native runegate reader is closed")
        last_error: NativeRunegateRegistryReadError | None = None
        for _ in range(self._stability_attempts):
            try:
                first = self._read_snapshot()
                second = self._read_snapshot()
                if first == second:
                    records, fingerprint = first
                    return NativeRunegateRegistryObservation(
                        runegates=records,
                        registry_token=self._registry_token(fingerprint),
                    )
            except NativeRunegateRegistryReadError as exc:
                last_error = exc
        if last_error is not None:
            raise NativeRunegateRegistryReadError(
                "runegate registry remained unreadable during every stable-read attempt: "
                f"{last_error}"
            ) from last_error
        raise NativeRunegateRegistryReadError(
            "runegate registry changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeRunegateRegistryReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_snapshot(
        self,
    ) -> tuple[
        tuple[NativeRunegateObservation, ...],
        tuple[int, int, int, tuple[tuple[int, bytes], ...]],
    ]:
        profile = self._profile
        registry = self._read_pointer(self._pointer_slot, "runegate registry")
        self._require_object_pointer(
            registry,
            profile.registry_tree_offset + profile.pointer_size,
            "runegate registry",
        )
        tree = registry + profile.registry_tree_offset
        head = self._read_pointer(
            tree + profile.tree_head_pointer_offset,
            "runegate tree head",
        )
        self._require_object_pointer(
            head,
            profile.head_first_node_offset + profile.pointer_size,
            "runegate tree head",
        )
        first = self._read_pointer(
            head + profile.head_first_node_offset,
            "first runegate node",
        )
        if first != head:
            self._require_node_pointer(first, "first runegate node")

        records: list[NativeRunegateObservation] = []
        node_blocks: list[tuple[int, bytes]] = []
        visited = {head}
        node = first
        while node != head:
            if node == 0 or node in visited:
                raise NativeRunegateRegistryReadError(
                    "runegate tree contains a null link or cycle"
                )
            if len(records) >= profile.maximum_runegates:
                raise NativeRunegateRegistryReadError(
                    "runegate tree exceeds the calibrated size bound"
                )
            visited.add(node)
            self._require_node_pointer(node, "runegate node")
            block = self._read_exact(
                node,
                profile.longitude_offset + 4,
                "runegate node",
            )
            node_blocks.append((node, block))
            records.append(self._decode_runegate(node, block))
            node = self._successor(node, head, block)

        identities = {(item.object_type, item.object_uuid) for item in records}
        if len(identities) != len(records):
            raise NativeRunegateRegistryReadError(
                "runegate tree contains duplicate object identities"
            )
        return (
            tuple(records),
            (registry, head, first, tuple(node_blocks)),
        )

    def _decode_runegate(self, node: int, block: bytes) -> NativeRunegateObservation:
        profile = self._profile
        object_type, object_uuid = struct.unpack_from(
            "<II", block, profile.object_type_offset
        )
        if object_type == 0 or object_uuid == 0:
            raise NativeRunegateRegistryReadError(
                "runegate object identity contains zero"
            )
        zone_name = self._read_string(
            node + profile.zone_name_offset,
            "runegate zone name",
        )
        native_lt, altitude, native_lg = struct.unpack_from(
            "<fff", block, profile.latitude_offset
        )
        lt = float(native_lt)
        lg = float(native_lg) * profile.longitude_multiplier
        if any(
            not isfinite(value) or abs(value) > profile.maximum_absolute_coordinate
            for value in (lt, lg, altitude)
        ):
            raise NativeRunegateRegistryReadError(
                "runegate position is outside calibrated bounds"
            )
        return NativeRunegateObservation(
            object_type=object_type,
            object_uuid=object_uuid,
            zone_name=zone_name,
            lt=lt,
            lg=lg,
            altitude=float(altitude),
        )

    def _successor(self, node: int, head: int, block: bytes) -> int:
        profile = self._profile
        right = struct.unpack_from("<I", block, profile.node_right_offset)[0]
        if right:
            self._require_node_pointer(right, "runegate right child")
            candidate = right
            descended: set[int] = set()
            while True:
                if candidate in descended:
                    raise NativeRunegateRegistryReadError(
                        "runegate tree contains a child cycle"
                    )
                descended.add(candidate)
                left = self._read_pointer(
                    candidate + profile.node_left_offset,
                    "runegate left child",
                )
                if left == 0:
                    return candidate
                self._require_node_pointer(left, "runegate left child")
                candidate = left

        parent = struct.unpack_from("<I", block, profile.node_parent_offset)[0]
        climbed: set[int] = set()
        candidate = node
        while parent != head:
            if parent == 0 or parent in climbed:
                raise NativeRunegateRegistryReadError(
                    "runegate tree contains a parent cycle"
                )
            climbed.add(parent)
            self._require_node_pointer(parent, "runegate parent")
            parent_right = self._read_pointer(
                parent + profile.node_right_offset,
                "runegate parent right child",
            )
            if candidate != parent_right:
                return parent
            candidate = parent
            parent = self._read_pointer(
                parent + profile.node_parent_offset,
                "runegate parent",
            )
        return head

    def _read_string(self, address: int, label: str) -> str:
        profile = self._profile
        header_size = profile.string_capacity_offset + profile.pointer_size
        first_header = self._read_exact(address, header_size, f"{label} header")
        begin = struct.unpack_from("<I", first_header, profile.string_begin_offset)[0]
        end = struct.unpack_from("<I", first_header, profile.string_end_offset)[0]
        capacity = struct.unpack_from("<I", first_header, profile.string_capacity_offset)[0]
        if (begin, end, capacity) == (0, 0, 0):
            if self._read_exact(address, header_size, f"{label} header") != first_header:
                raise NativeRunegateRegistryReadError(
                    f"{label} header changed during the read"
                )
            return ""
        if begin == 0 or end < begin or capacity < end + 2:
            raise NativeRunegateRegistryReadError(
                f"{label} Core::String pointers are invalid"
            )
        byte_length = end - begin
        if byte_length % 2 != 0:
            raise NativeRunegateRegistryReadError(
                f"{label} byte length is not UTF-16 aligned"
            )
        if byte_length > profile.maximum_zone_name_chars * 2:
            raise NativeRunegateRegistryReadError(
                f"{label} exceeds the calibrated length bound"
            )
        if (
            begin < profile.minimum_user_address
            or capacity > profile.maximum_user_address
            or begin % 2 != 0
        ):
            raise NativeRunegateRegistryReadError(
                f"{label} buffer is outside the 32-bit user range"
            )
        raw = self._read_exact(begin, byte_length + 2, f"{label} buffer")
        if raw[-2:] != b"\x00\x00":
            raise NativeRunegateRegistryReadError(
                f"{label} buffer is not null terminated"
            )
        if self._read_exact(address, header_size, f"{label} header") != first_header:
            raise NativeRunegateRegistryReadError(
                f"{label} header changed during the read"
            )
        try:
            value = raw[:-2].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            raise NativeRunegateRegistryReadError(
                f"{label} is not valid UTF-16LE"
            ) from exc
        if "\x00" in value or any(ord(character) < 0x20 for character in value):
            raise NativeRunegateRegistryReadError(
                f"{label} contains invalid control characters"
            )
        return value

    def _read_pointer(self, address: int, label: str) -> int:
        return struct.unpack(
            "<I",
            self._read_exact(address, self._profile.pointer_size, f"{label} pointer"),
        )[0]

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        if size <= 0:
            raise NativeRunegateRegistryReadError(f"{label} read size must be positive")
        chunks = []
        offset = 0
        while offset < size:
            chunk_size = min(_MAX_READ_SIZE, size - offset)
            try:
                chunk = self._process.read(address + offset, chunk_size)
            except Exception as exc:
                raise NativeRunegateRegistryReadError(
                    f"could not read {label}: {type(exc).__name__}"
                ) from exc
            if len(chunk) != chunk_size:
                raise NativeRunegateRegistryReadError(
                    f"native process backend returned a partial {label}"
                )
            chunks.append(chunk)
            offset += chunk_size
        return b"".join(chunks)

    def _require_node_pointer(self, pointer: int, label: str) -> None:
        self._require_object_pointer(
            pointer,
            self._profile.longitude_offset + 4,
            label,
        )

    def _require_object_pointer(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + size > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeRunegateRegistryReadError(
                f"{label} pointer is outside the calibrated 32-bit user range"
            )

    def _registry_token(
        self,
        fingerprint: tuple[int, int, int, tuple[tuple[int, bytes], ...]],
    ) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<I", self._process.pid))
        registry, head, first, node_blocks = fingerprint
        digest.update(struct.pack("<III", registry, head, first))
        for node, block in node_blocks:
            digest.update(struct.pack("<I", node))
            digest.update(block)
        return digest.hexdigest()


def open_windows_native_runegate_registry_reader(
    profile: NativeRunegateRegistryProfile,
    *,
    process_id: int | None = None,
) -> NativeRunegateRegistryReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeRunegateRegistryReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_runegate_registry_profile() -> NativeRunegateRegistryProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_runegate_registry_profile_text(resource.read_text(encoding="utf-8"))


def load_native_runegate_registry_profile(
    path: str | Path,
) -> NativeRunegateRegistryProfile:
    return load_native_runegate_registry_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_runegate_registry_profile_text(
    text: str,
) -> NativeRunegateRegistryProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeRunegateRegistryProfileLoadError(
            "native runegate profile is not valid JSON"
        ) from exc
    if not isinstance(raw, Mapping):
        raise NativeRunegateRegistryProfileLoadError(
            "native runegate profile must be an object"
        )
    expected = set(NativeRunegateRegistryProfile.__dataclass_fields__)
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise NativeRunegateRegistryProfileLoadError(
            f"native runegate profile has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise NativeRunegateRegistryProfileLoadError(
            f"native runegate profile is missing fields: {', '.join(sorted(missing))}"
        )
    try:
        return NativeRunegateRegistryProfile(**cast(dict[str, Any], dict(raw)))
    except (TypeError, ValueError) as exc:
        raise NativeRunegateRegistryProfileLoadError(str(exc)) from exc
