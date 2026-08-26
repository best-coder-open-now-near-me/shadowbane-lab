"""Build-guarded native observation of the local player's world position."""

from __future__ import annotations

import ctypes
import json
import os
import statistics
import struct
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass
from importlib.resources import files
from math import hypot, isfinite
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_POSITION_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-0889b39a.native-position.json"
_MEM_COMMIT = 0x1000
_MEM_PRIVATE = 0x20000
_PAGE_GUARD = 0x100
_PAGE_NOACCESS = 0x01
_READABLE_PROTECTIONS = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}


class NativePlayerPositionError(RuntimeError):
    """Base error for guarded native player-position observation."""


class NativePlayerPositionCompatibilityError(NativePlayerPositionError):
    """Raised when the running executable does not match its calibrated build."""


class NativePlayerPositionReadError(NativePlayerPositionError):
    """Raised when player position cannot be located or read safely."""


class NativePositionProfileLoadError(ValueError):
    """Raised when a native position profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativePlayerPositionProfile:
    """Exact build identity and transform signature for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    player_altitude_offset: int
    transform_scale_signature: tuple[float, float, float]
    scale_offset: int
    minimum_user_address: int
    maximum_user_address: int
    minimum_world_coordinate: float
    maximum_world_coordinate: float
    minimum_altitude: float
    maximum_altitude: float
    player_altitude_tolerance: float
    cluster_radius: float
    maximum_cluster_spread: float
    minimum_cluster_size: int
    maximum_tracking_delta: float
    maximum_region_size: int
    schema_version: int = NATIVE_POSITION_PROFILE_SCHEMA_VERSION

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
            (self.player_altitude_offset, "player_altitude_offset"),
            (self.scale_offset, "scale_offset"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
            (self.minimum_cluster_size, "minimum_cluster_size"),
            (self.maximum_region_size, "maximum_region_size"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if len(self.transform_scale_signature) != 3 or any(
            not isfinite(value) or value <= 0 for value in self.transform_scale_signature
        ):
            raise ValueError("transform_scale_signature must contain three positive values")
        for minimum, maximum, name in (
            (
                self.minimum_world_coordinate,
                self.maximum_world_coordinate,
                "world coordinate",
            ),
            (self.minimum_altitude, self.maximum_altitude, "altitude"),
        ):
            if not isfinite(minimum) or not isfinite(maximum) or maximum <= minimum:
                raise ValueError(f"{name} bounds must be finite and increasing")
        for value, field_name in (
            (self.player_altitude_tolerance, "player_altitude_tolerance"),
            (self.cluster_radius, "cluster_radius"),
            (self.maximum_cluster_spread, "maximum_cluster_spread"),
            (self.maximum_tracking_delta, "maximum_tracking_delta"),
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be finite and positive")
        if self.maximum_cluster_spread < self.cluster_radius:
            raise ValueError("maximum_cluster_spread cannot be smaller than cluster_radius")
        if self.schema_version != NATIVE_POSITION_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native position profile version")

    @property
    def signature_bytes(self) -> bytes:
        return struct.pack("<fff", *self.transform_scale_signature)


@dataclass(frozen=True, slots=True)
class NativePlayerPositionObservation:
    lt: float
    lg: float
    altitude: float
    transform_count: int

    def __post_init__(self) -> None:
        if any(not isfinite(value) for value in (self.lt, self.lg, self.altitude)):
            raise ValueError("player position values must be finite")
        if (
            isinstance(self.transform_count, bool)
            or not isinstance(self.transform_count, int)
            or self.transform_count <= 0
        ):
            raise ValueError("transform_count must be a positive integer")


@runtime_checkable
class PrivatePatternProcessMemory(ReadOnlyProcessMemory, Protocol):
    def find_private_pattern(
        self,
        pattern: bytes,
        *,
        minimum_address: int,
        maximum_address: int,
        maximum_region_size: int,
    ) -> tuple[int, ...]: ...


class _MemoryBasicInformation(ctypes.Structure):
    _fields_ = (
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    )


class WindowsReadOnlyPositionProcessMemory(WindowsReadOnlyProcessMemory):
    """Read-only Win32 process handle with bounded private-memory signature search."""

    def find_private_pattern(
        self,
        pattern: bytes,
        *,
        minimum_address: int,
        maximum_address: int,
        maximum_region_size: int,
    ) -> tuple[int, ...]:
        if os.name != "nt":
            raise NativePlayerPositionReadError("native position search requires Windows")
        if not pattern:
            raise NativePlayerPositionReadError("position signature must not be empty")
        if not self._handle:
            raise NativePlayerPositionReadError("native process handle is closed")
        kernel32 = self._api.kernel32
        kernel32.VirtualQueryEx.argtypes = (
            wintypes.HANDLE,
            wintypes.LPCVOID,
            ctypes.POINTER(_MemoryBasicInformation),
            ctypes.c_size_t,
        )
        kernel32.VirtualQueryEx.restype = ctypes.c_size_t
        matches: list[int] = []
        cursor = minimum_address
        while cursor < maximum_address:
            info = _MemoryBasicInformation()
            if not kernel32.VirtualQueryEx(
                self._handle,
                ctypes.c_void_p(cursor),
                ctypes.byref(info),
                ctypes.sizeof(info),
            ):
                cursor += 0x1000
                continue
            base = int(info.BaseAddress or cursor)
            size = int(info.RegionSize)
            protection = int(info.Protect) & 0xFF
            readable = (
                info.State == _MEM_COMMIT
                and info.Type == _MEM_PRIVATE
                and protection in _READABLE_PROTECTIONS
                and not (info.Protect & (_PAGE_GUARD | _PAGE_NOACCESS))
                and 0 < size <= maximum_region_size
            )
            if readable:
                data = self._read_region(base, size)
                if data is not None:
                    offset = data.find(pattern)
                    while offset >= 0:
                        matches.append(base + offset)
                        offset = data.find(pattern, offset + 1)
            cursor = max(cursor + 0x1000, base + max(size, 0x1000))
        return tuple(matches)

    def _read_region(self, address: int, size: int) -> bytes | None:
        buffer = (ctypes.c_ubyte * size)()
        received = ctypes.c_size_t()
        if not self._api.kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(received),
        ):
            return None
        return bytes(buffer) if received.value == size else None


class NativePlayerPositionReader:
    """Locates the player's render transforms once, then reads their median position."""

    def __init__(
        self,
        profile: NativePlayerPositionProfile,
        process: PrivatePatternProcessMemory,
    ) -> None:
        if not isinstance(profile, NativePlayerPositionProfile):
            raise ValueError("profile must be NativePlayerPositionProfile")
        if not isinstance(process, PrivatePatternProcessMemory):
            raise ValueError("process must implement PrivatePatternProcessMemory")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativePlayerPositionCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativePlayerPositionCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativePlayerPositionCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        self._profile = profile
        self._process = process
        self._closed = False
        self._last_position: NativePlayerPositionObservation | None = None
        self._transform_addresses = self._locate_player_transforms()

    @property
    def profile(self) -> NativePlayerPositionProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    @property
    def transform_addresses(self) -> tuple[int, ...]:
        return self._transform_addresses

    def observe(self) -> NativePlayerPositionObservation:
        if self._closed:
            raise NativePlayerPositionReadError("native player-position reader is closed")
        candidates = tuple(
            candidate
            for address in self._transform_addresses
            if (candidate := self._read_transform(address)) is not None
        )
        if self._last_position is not None:
            candidates = tuple(
                candidate
                for candidate in candidates
                if hypot(
                    candidate[0] - self._last_position.lt,
                    candidate[1] - self._last_position.lg,
                )
                <= self._profile.maximum_tracking_delta
            )
        if len(candidates) < self._profile.minimum_cluster_size:
            raise NativePlayerPositionReadError(
                "too few calibrated player transforms remained readable"
            )
        observation = self._observation(candidates)
        planar_spread = max(
            hypot(candidate[0] - observation.lt, candidate[1] - observation.lg)
            for candidate in candidates
        )
        if planar_spread > self._profile.maximum_cluster_spread:
            raise NativePlayerPositionReadError(
                "calibrated player transforms no longer agree on one position"
            )
        self._last_position = observation
        return observation

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativePlayerPositionReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _locate_player_transforms(self) -> tuple[int, ...]:
        player_altitude = self._read_player_altitude()
        signature_addresses = self._process.find_private_pattern(
            self._profile.signature_bytes,
            minimum_address=self._profile.minimum_user_address,
            maximum_address=self._profile.maximum_user_address,
            maximum_region_size=self._profile.maximum_region_size,
        )
        candidates = tuple(
            (address, transform)
            for signature_address in signature_addresses
            if (address := signature_address - self._profile.scale_offset) > 0
            if (transform := self._read_transform(address)) is not None
            if abs(transform[2] - player_altitude)
            <= self._profile.player_altitude_tolerance
        )
        clusters = self._clusters(candidates)
        eligible = [
            cluster
            for cluster in clusters
            if len(cluster) >= self._profile.minimum_cluster_size
        ]
        if not eligible:
            raise NativePlayerPositionReadError(
                "player transform signature produced no altitude-matched cluster"
            )
        eligible.sort(
            key=lambda cluster: (
                len(cluster),
                -abs(statistics.median(item[1][2] for item in cluster) - player_altitude),
            ),
            reverse=True,
        )
        if len(eligible) > 1 and len(eligible[0]) == len(eligible[1]):
            raise NativePlayerPositionReadError(
                "player transform signature produced equally strong clusters"
            )
        return tuple(item[0] for item in eligible[0])

    def _read_player_altitude(self) -> float:
        slot = self._process.base_address + self._profile.player_pointer_rva
        try:
            player_pointer = struct.unpack("<I", self._process.read(slot, 4))[0]
            altitude = struct.unpack(
                "<f",
                self._process.read(player_pointer + self._profile.player_altitude_offset, 4),
            )[0]
        except Exception as exc:
            raise NativePlayerPositionReadError(
                f"could not read player altitude anchor: {type(exc).__name__}"
            ) from exc
        if not self._profile.minimum_user_address <= player_pointer <= (
            self._profile.maximum_user_address - self._profile.player_altitude_offset - 4
        ):
            raise NativePlayerPositionReadError("player pointer is outside calibrated bounds")
        if not isfinite(altitude) or not (
            self._profile.minimum_altitude <= altitude <= self._profile.maximum_altitude
        ):
            raise NativePlayerPositionReadError("player altitude anchor is implausible")
        return altitude

    def _read_transform(self, address: int) -> tuple[float, float, float] | None:
        try:
            lt, altitude, negative_lg = struct.unpack("<fff", self._process.read(address, 12))
        except Exception:
            return None
        lg = -negative_lg
        profile = self._profile
        if (
            all(isfinite(value) for value in (lt, lg, altitude))
            and profile.minimum_world_coordinate <= lt <= profile.maximum_world_coordinate
            and profile.minimum_world_coordinate <= lg <= profile.maximum_world_coordinate
            and profile.minimum_altitude <= altitude <= profile.maximum_altitude
        ):
            return lt, lg, altitude
        return None

    def _clusters(
        self,
        candidates: tuple[tuple[int, tuple[float, float, float]], ...],
    ) -> list[list[tuple[int, tuple[float, float, float]]]]:
        remaining = list(candidates)
        clusters: list[list[tuple[int, tuple[float, float, float]]]] = []
        while remaining:
            cluster = [remaining.pop(0)]
            changed = True
            while changed:
                changed = False
                center_lt = statistics.median(item[1][0] for item in cluster)
                center_lg = statistics.median(item[1][1] for item in cluster)
                retained = []
                for item in remaining:
                    if hypot(item[1][0] - center_lt, item[1][1] - center_lg) <= (
                        self._profile.cluster_radius
                    ):
                        cluster.append(item)
                        changed = True
                    else:
                        retained.append(item)
                remaining = retained
            clusters.append(cluster)
        return clusters

    @staticmethod
    def _observation(
        candidates: tuple[tuple[float, float, float], ...],
    ) -> NativePlayerPositionObservation:
        return NativePlayerPositionObservation(
            lt=statistics.median(candidate[0] for candidate in candidates),
            lg=statistics.median(candidate[1] for candidate in candidates),
            altitude=statistics.median(candidate[2] for candidate in candidates),
            transform_count=len(candidates),
        )


def open_windows_native_player_position_reader(
    profile: NativePlayerPositionProfile,
) -> NativePlayerPositionReader:
    process = WindowsReadOnlyPositionProcessMemory.open_unique(profile.executable_name)
    try:
        return NativePlayerPositionReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_position_profile() -> NativePlayerPositionProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_position_profile_text(resource.read_text(encoding="utf-8"))


def load_native_position_profile(path: str | Path) -> NativePlayerPositionProfile:
    return load_native_position_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_position_profile_text(text: str) -> NativePlayerPositionProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativePositionProfileLoadError("native position profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "native position profile")
        expected = {
            "schema_version",
            "profile_id",
            "executable_name",
            "executable_sha256",
            "pointer_size",
            "player_pointer_rva",
            "player_altitude_offset",
            "transform_scale_signature",
            "scale_offset",
            "minimum_user_address",
            "maximum_user_address",
            "minimum_world_coordinate",
            "maximum_world_coordinate",
            "minimum_altitude",
            "maximum_altitude",
            "player_altitude_tolerance",
            "cluster_radius",
            "maximum_cluster_spread",
            "minimum_cluster_size",
            "maximum_tracking_delta",
            "maximum_region_size",
        }
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativePositionProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativePositionProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        signature = data["transform_scale_signature"]
        if not isinstance(signature, list) or len(signature) != 3:
            raise NativePositionProfileLoadError(
                "transform_scale_signature must contain exactly three numbers"
            )
        return NativePlayerPositionProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            player_pointer_rva=_integer(data, "player_pointer_rva"),
            player_altitude_offset=_integer(data, "player_altitude_offset"),
            transform_scale_signature=cast(
                tuple[float, float, float], tuple(_number_value(value) for value in signature)
            ),
            scale_offset=_integer(data, "scale_offset"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            minimum_world_coordinate=_number(data, "minimum_world_coordinate"),
            maximum_world_coordinate=_number(data, "maximum_world_coordinate"),
            minimum_altitude=_number(data, "minimum_altitude"),
            maximum_altitude=_number(data, "maximum_altitude"),
            player_altitude_tolerance=_number(data, "player_altitude_tolerance"),
            cluster_radius=_number(data, "cluster_radius"),
            maximum_cluster_spread=_number(data, "maximum_cluster_spread"),
            minimum_cluster_size=_integer(data, "minimum_cluster_size"),
            maximum_tracking_delta=_number(data, "maximum_tracking_delta"),
            maximum_region_size=_integer(data, "maximum_region_size"),
            schema_version=_integer(data, "schema_version"),
        )
    except NativePositionProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativePositionProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativePositionProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativePositionProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativePositionProfileLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    return _number_value(data[key], key)


def _number_value(value: Any, field_name: str = "value") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativePositionProfileLoadError(f"{field_name} must be a number")
    return float(value)
