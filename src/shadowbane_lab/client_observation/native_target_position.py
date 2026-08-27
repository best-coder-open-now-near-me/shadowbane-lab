"""Build-guarded, read-only access to the selected target's native position."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from math import dist, isfinite
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_TARGET_POSITION_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-target-position.json"


class NativeTargetPositionError(RuntimeError):
    """Base error for guarded native selected-target position observation."""


class NativeTargetPositionCompatibilityError(NativeTargetPositionError):
    """Raised when the running executable does not match its calibrated build."""


class NativeTargetPositionReadError(NativeTargetPositionError):
    """Raised when selected-target position cannot be read safely."""


class NativeTargetPositionProfileLoadError(ValueError):
    """Raised when a native selected-target position profile is invalid."""


@dataclass(frozen=True, slots=True)
class NativeTargetPositionProfile:
    """Exact selected-object position layout for one verified client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    selected_pointer_rva: int
    vtable_minimum_rva: int
    vtable_maximum_rva: int
    position_getter_slot_offset: int
    position_getter_rva: int
    position_component_offset: int
    component_value_offset: int
    position_value_offset: int
    minimum_user_address: int
    maximum_user_address: int
    minimum_world_coordinate: float
    maximum_world_coordinate: float
    minimum_altitude: float
    maximum_altitude: float
    maximum_sample_drift: float
    schema_version: int = NATIVE_TARGET_POSITION_PROFILE_SCHEMA_VERSION

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
            (self.selected_pointer_rva, "selected_pointer_rva"),
            (self.vtable_minimum_rva, "vtable_minimum_rva"),
            (self.vtable_maximum_rva, "vtable_maximum_rva"),
            (self.position_getter_slot_offset, "position_getter_slot_offset"),
            (self.position_getter_rva, "position_getter_rva"),
            (self.position_component_offset, "position_component_offset"),
            (self.position_value_offset, "position_value_offset"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if (
            isinstance(self.component_value_offset, bool)
            or not isinstance(self.component_value_offset, int)
            or self.component_value_offset < 0
        ):
            raise ValueError("component_value_offset must be a non-negative integer")
        if self.vtable_minimum_rva >= self.vtable_maximum_rva:
            raise ValueError("vtable RVA range must be increasing")
        if self.position_getter_slot_offset % self.pointer_size != 0:
            raise ValueError("position getter slot must be pointer-aligned")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        for value, field_name in (
            (self.minimum_world_coordinate, "minimum_world_coordinate"),
            (self.maximum_world_coordinate, "maximum_world_coordinate"),
            (self.minimum_altitude, "minimum_altitude"),
            (self.maximum_altitude, "maximum_altitude"),
            (self.maximum_sample_drift, "maximum_sample_drift"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{field_name} must be finite")
        if self.minimum_world_coordinate >= self.maximum_world_coordinate:
            raise ValueError("world-coordinate range must be increasing")
        if self.minimum_altitude >= self.maximum_altitude:
            raise ValueError("altitude range must be increasing")
        if self.maximum_sample_drift <= 0:
            raise ValueError("maximum_sample_drift must be positive")
        if self.schema_version != NATIVE_TARGET_POSITION_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native target-position profile version")


@dataclass(frozen=True, slots=True)
class NativeTargetPositionObservation:
    """One coherent selected-target position snapshot."""

    target_present: bool
    lt: float | None = None
    lg: float | None = None
    altitude: float | None = None
    target_token: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be boolean")
        values = (self.lt, self.lg, self.altitude)
        if not self.target_present:
            if any(value is not None for value in (*values, self.target_token)):
                raise ValueError("an absent target cannot contain position values")
            return
        if any(value is None for value in values):
            raise ValueError("a present target requires LT, LG, and altitude")
        if any(not isfinite(cast(float, value)) for value in values):
            raise ValueError("target coordinates must be finite")
        if self.target_token is None or not self.target_token.strip():
            raise ValueError("a present target requires an opaque target token")


@dataclass(frozen=True, slots=True)
class _TargetPositionSnapshot:
    selected: int
    vtable: int
    getter: int
    component: int
    value: int
    observation: NativeTargetPositionObservation


class NativeTargetPositionReader:
    """Reads the position storage used by the selected object's virtual getter."""

    def __init__(
        self,
        profile: NativeTargetPositionProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeTargetPositionProfile):
            raise ValueError("profile must be NativeTargetPositionProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeTargetPositionCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeTargetPositionCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeTargetPositionCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeTargetPositionCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.selected_pointer_rva
        getter_address = process.base_address + profile.position_getter_rva
        if (
            pointer_slot < profile.minimum_user_address
            or pointer_slot + profile.pointer_size > profile.maximum_user_address
            or getter_address < profile.minimum_user_address
            or getter_address + 5 > profile.maximum_user_address
        ):
            raise NativeTargetPositionCompatibilityError(
                "calibrated target-position addresses are outside the 32-bit user range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._getter_address = getter_address
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativeTargetPositionProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeTargetPositionObservation:
        if self._closed:
            raise NativeTargetPositionReadError("native target-position reader is closed")
        last_error: NativeTargetPositionReadError | None = None
        for _ in range(self._stability_attempts):
            selected = self._read_pointer(self._pointer_slot, "selected target")
            if selected == 0:
                return NativeTargetPositionObservation(target_present=False)
            try:
                snapshot = self._read_snapshot(selected)
                if self._snapshot_is_stable(snapshot):
                    return snapshot.observation
            except NativeTargetPositionReadError as exc:
                last_error = exc
                if self._read_pointer(self._pointer_slot, "selected target") != selected:
                    continue
        if last_error is not None:
            raise NativeTargetPositionReadError(
                "selected-target position remained unreadable during every stable-read "
                f"attempt: {last_error}"
            ) from last_error
        raise NativeTargetPositionReadError(
            "selected-target position changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeTargetPositionReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_snapshot(self, selected: int) -> _TargetPositionSnapshot:
        profile = self._profile
        self._require_object_pointer(
            selected,
            profile.position_component_offset + profile.pointer_size,
            "selected target",
        )
        vtable = self._read_pointer(selected, "selected-target vtable")
        self._require_vtable_pointer(vtable)
        getter = self._read_pointer(
            vtable + profile.position_getter_slot_offset,
            "selected-target position getter",
        )
        if getter != self._getter_address:
            raise NativeTargetPositionReadError(
                "selected target uses an unsupported position-getter implementation"
            )
        component = self._read_pointer(
            selected + profile.position_component_offset,
            "selected-target position component",
        )
        self._require_object_pointer(
            component,
            profile.component_value_offset + profile.pointer_size,
            "selected-target position component",
        )
        value = self._read_pointer(
            component + profile.component_value_offset,
            "selected-target position value",
        )
        self._require_object_pointer(
            value,
            profile.position_value_offset + 12,
            "selected-target position value",
        )
        first = self._read_position(value)
        second = self._read_position(value)
        if dist(first, second) > profile.maximum_sample_drift:
            raise NativeTargetPositionReadError(
                "selected-target position moved beyond the coherent-sample bound"
            )
        native_x, native_y, native_z = second
        observation = self._validated_observation(
            selected,
            lt=native_x,
            lg=-native_z,
            altitude=native_y,
        )
        return _TargetPositionSnapshot(
            selected=selected,
            vtable=vtable,
            getter=getter,
            component=component,
            value=value,
            observation=observation,
        )

    def _snapshot_is_stable(self, snapshot: _TargetPositionSnapshot) -> bool:
        profile = self._profile
        return (
            self._read_pointer(self._pointer_slot, "selected target") == snapshot.selected
            and self._read_pointer(snapshot.selected, "selected-target vtable")
            == snapshot.vtable
            and self._read_pointer(
                snapshot.vtable + profile.position_getter_slot_offset,
                "selected-target position getter",
            )
            == snapshot.getter
            and self._read_pointer(
                snapshot.selected + profile.position_component_offset,
                "selected-target position component",
            )
            == snapshot.component
            and self._read_pointer(
                snapshot.component + profile.component_value_offset,
                "selected-target position value",
            )
            == snapshot.value
        )

    def _read_position(self, value: int) -> tuple[float, float, float]:
        raw = self._read_exact(
            value + self._profile.position_value_offset,
            12,
            "selected-target position",
        )
        position = cast(tuple[float, float, float], struct.unpack("<fff", raw))
        if any(not isfinite(coordinate) for coordinate in position):
            raise NativeTargetPositionReadError("selected-target position is not finite")
        return position

    def _validated_observation(
        self,
        selected: int,
        *,
        lt: float,
        lg: float,
        altitude: float,
    ) -> NativeTargetPositionObservation:
        profile = self._profile
        if not (
            profile.minimum_world_coordinate <= lt <= profile.maximum_world_coordinate
            and profile.minimum_world_coordinate <= lg <= profile.maximum_world_coordinate
        ):
            raise NativeTargetPositionReadError(
                "selected-target LT/LG is outside calibrated world bounds"
            )
        if not profile.minimum_altitude <= altitude <= profile.maximum_altitude:
            raise NativeTargetPositionReadError(
                "selected-target altitude is outside calibrated bounds"
            )
        return NativeTargetPositionObservation(
            target_present=True,
            lt=lt,
            lg=lg,
            altitude=altitude,
            target_token=self._target_token(selected),
        )

    def _read_pointer(self, address: int, label: str) -> int:
        return struct.unpack(
            "<I",
            self._read_exact(address, self._profile.pointer_size, f"{label} pointer"),
        )[0]

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        try:
            value = self._process.read(address, size)
        except Exception as exc:
            raise NativeTargetPositionReadError(
                f"could not read {label}: {type(exc).__name__}"
            ) from exc
        if len(value) != size:
            raise NativeTargetPositionReadError(
                f"native process backend returned a partial {label}"
            )
        return value

    def _require_object_pointer(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + size > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeTargetPositionReadError(
                f"{label} pointer is outside the calibrated 32-bit user range"
            )

    def _require_vtable_pointer(self, pointer: int) -> None:
        profile = self._profile
        minimum = self._process.base_address + profile.vtable_minimum_rva
        maximum = self._process.base_address + profile.vtable_maximum_rva
        if (
            pointer < minimum
            or pointer + profile.position_getter_slot_offset + profile.pointer_size
            > maximum
            or pointer % profile.pointer_size != 0
        ):
            raise NativeTargetPositionReadError(
                "selected-target vtable is outside the calibrated read-only image range"
            )

    def _target_token(self, selected: int) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<II", self._process.pid, selected))
        return digest.hexdigest()


def open_windows_native_target_position_reader(
    profile: NativeTargetPositionProfile,
    *,
    process_id: int | None = None,
) -> NativeTargetPositionReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeTargetPositionReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_target_position_profile() -> NativeTargetPositionProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_target_position_profile_text(resource.read_text(encoding="utf-8"))


def load_native_target_position_profile(
    path: str | Path,
) -> NativeTargetPositionProfile:
    return load_native_target_position_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_target_position_profile_text(
    text: str,
) -> NativeTargetPositionProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeTargetPositionProfileLoadError(
            "native target-position profile is not valid JSON"
        ) from exc
    try:
        data = _mapping(raw, "native target-position profile")
        expected = set(NativeTargetPositionProfile.__dataclass_fields__)
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeTargetPositionProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeTargetPositionProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        values = {
            key: (
                _string(data, key)
                if key in {"profile_id", "executable_name", "executable_sha256"}
                else _number(data, key)
                if key
                in {
                    "minimum_world_coordinate",
                    "maximum_world_coordinate",
                    "minimum_altitude",
                    "maximum_altitude",
                    "maximum_sample_drift",
                }
                else _integer(data, key)
            )
            for key in expected
        }
        return NativeTargetPositionProfile(**values)
    except NativeTargetPositionProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeTargetPositionProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeTargetPositionProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeTargetPositionProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeTargetPositionProfileLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeTargetPositionProfileLoadError(f"{key} must be numeric")
    return float(value)
