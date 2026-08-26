"""Build-guarded, read-only access to the local Shadowbane player's vital resources."""

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

NATIVE_VITALS_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-0889b39a.native-vitals.json"


class NativePlayerVitalsError(RuntimeError):
    """Base error for guarded native player-vitals observation."""


class NativePlayerVitalsCompatibilityError(NativePlayerVitalsError):
    """Raised when the running executable does not match its calibrated build."""


class NativePlayerVitalsReadError(NativePlayerVitalsError):
    """Raised when native player values cannot be read or validated safely."""


class NativeVitalsProfileLoadError(ValueError):
    """Raised when a native player-vitals profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativePlayerVitalsProfile:
    """Exact executable identity and player-resource offsets for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    current_health_offset: int
    maximum_health_offset: int
    current_mana_offset: int
    maximum_mana_offset: int
    current_stamina_offset: int
    maximum_stamina_offset: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_plausible_vital: float
    schema_version: int = NATIVE_VITALS_PROFILE_SCHEMA_VERSION

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
        integer_fields = (
            (self.player_pointer_rva, "player_pointer_rva"),
            (self.current_health_offset, "current_health_offset"),
            (self.maximum_health_offset, "maximum_health_offset"),
            (self.current_mana_offset, "current_mana_offset"),
            (self.maximum_mana_offset, "maximum_mana_offset"),
            (self.current_stamina_offset, "current_stamina_offset"),
            (self.maximum_stamina_offset, "maximum_stamina_offset"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
        )
        for value, field_name in integer_fields:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.player_pointer_rva == 0:
            raise ValueError("player_pointer_rva must be positive")
        for current, maximum, name in (
            (self.current_health_offset, self.maximum_health_offset, "health"),
            (self.current_mana_offset, self.maximum_mana_offset, "mana"),
            (self.current_stamina_offset, self.maximum_stamina_offset, "stamina"),
        ):
            if abs(maximum - current) != 4:
                raise ValueError(f"verified current and maximum {name} fields must be adjacent")
        resource_offsets = (
            self.current_mana_offset,
            self.maximum_mana_offset,
            self.current_stamina_offset,
            self.maximum_stamina_offset,
        )
        resource_start = min(resource_offsets)
        if sorted(resource_offsets) != list(range(resource_start, resource_start + 16, 4)):
            raise ValueError("verified mana and stamina fields must form one contiguous block")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if (
            isinstance(self.maximum_plausible_vital, bool)
            or not isinstance(self.maximum_plausible_vital, (int, float))
            or not isfinite(self.maximum_plausible_vital)
            or self.maximum_plausible_vital <= 0
        ):
            raise ValueError("maximum_plausible_vital must be finite and positive")
        if self.schema_version != NATIVE_VITALS_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native vitals profile version")


@dataclass(frozen=True, slots=True)
class NativePlayerVitalsObservation:
    current_health: float
    maximum_health: float
    current_mana: float
    maximum_mana: float
    current_stamina: float
    maximum_stamina: float

    def __post_init__(self) -> None:
        for current, maximum, name in (
            (self.current_health, self.maximum_health, "health"),
            (self.current_mana, self.maximum_mana, "mana"),
            (self.current_stamina, self.maximum_stamina, "stamina"),
        ):
            if not isfinite(current) or not isfinite(maximum):
                raise ValueError(f"player {name} values must be finite")
            if current < 0 or maximum <= 0 or current > maximum:
                raise ValueError(f"player {name} values are outside valid bounds")

    @property
    def health_fraction(self) -> float:
        return self.current_health / self.maximum_health

    @property
    def mana_fraction(self) -> float:
        return self.current_mana / self.maximum_mana

    @property
    def stamina_fraction(self) -> float:
        return self.current_stamina / self.maximum_stamina


class NativePlayerVitalsReader:
    """Decodes stable player vitals from an already opened read-only process."""

    def __init__(
        self,
        profile: NativePlayerVitalsProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativePlayerVitalsProfile):
            raise ValueError("profile must be NativePlayerVitalsProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativePlayerVitalsCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativePlayerVitalsCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativePlayerVitalsCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativePlayerVitalsCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.player_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativePlayerVitalsCompatibilityError(
                "calibrated player pointer lies outside the 32-bit user address range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._health_start_offset = min(
            profile.current_health_offset,
            profile.maximum_health_offset,
        )
        self._resource_start_offset = min(
            profile.current_mana_offset,
            profile.maximum_mana_offset,
            profile.current_stamina_offset,
            profile.maximum_stamina_offset,
        )
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativePlayerVitalsProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativePlayerVitalsObservation:
        if self._closed:
            raise NativePlayerVitalsReadError("native player-vitals reader is closed")
        last_validation_error: NativePlayerVitalsReadError | None = None
        for _ in range(self._stability_attempts):
            player_pointer = self._read_pointer()
            self._require_plausible_player_pointer(player_pointer)
            try:
                health = self._process.read(
                    player_pointer + self._health_start_offset,
                    8,
                )
                resources = self._process.read(
                    player_pointer + self._resource_start_offset,
                    16,
                )
            except Exception as exc:
                if self._read_pointer() != player_pointer:
                    continue
                raise NativePlayerVitalsReadError(
                    f"could not read player vitals: {type(exc).__name__}"
                ) from exc
            if len(health) != 8 or len(resources) != 16:
                raise NativePlayerVitalsReadError(
                    "native process backend returned partial player-vitals values"
                )
            if self._read_pointer() != player_pointer:
                continue
            profile = self._profile
            values = (
                self._float_at(
                    health,
                    profile.current_health_offset - self._health_start_offset,
                ),
                self._float_at(
                    health,
                    profile.maximum_health_offset - self._health_start_offset,
                ),
                self._float_at(
                    resources,
                    profile.current_mana_offset - self._resource_start_offset,
                ),
                self._float_at(
                    resources,
                    profile.maximum_mana_offset - self._resource_start_offset,
                ),
                self._float_at(
                    resources,
                    profile.current_stamina_offset - self._resource_start_offset,
                ),
                self._float_at(
                    resources,
                    profile.maximum_stamina_offset - self._resource_start_offset,
                ),
            )
            try:
                return self._validated_observation(*values)
            except NativePlayerVitalsReadError as exc:
                last_validation_error = exc
        if last_validation_error is not None:
            raise NativePlayerVitalsReadError(
                "player vitals remained invalid during every stable-read attempt: "
                f"{last_validation_error}"
            ) from last_validation_error
        raise NativePlayerVitalsReadError(
            "player pointer changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativePlayerVitalsReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_pointer(self) -> int:
        try:
            value = self._process.read(self._pointer_slot, self._profile.pointer_size)
        except Exception as exc:
            raise NativePlayerVitalsReadError(
                f"could not read player pointer: {type(exc).__name__}"
            ) from exc
        if len(value) != self._profile.pointer_size:
            raise NativePlayerVitalsReadError(
                "native process backend returned a partial player pointer"
            )
        return struct.unpack("<I", value)[0]

    def _require_plausible_player_pointer(self, pointer: int) -> None:
        profile = self._profile
        final_offset = max(
            profile.current_health_offset,
            profile.maximum_health_offset,
            profile.current_mana_offset,
            profile.maximum_mana_offset,
            profile.current_stamina_offset,
            profile.maximum_stamina_offset,
        )
        final_address = pointer + final_offset + 4
        if (
            pointer < profile.minimum_user_address
            or final_address > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativePlayerVitalsReadError(
                "player pointer is outside the calibrated 32-bit user range"
            )

    @staticmethod
    def _float_at(block: bytes, offset: int) -> float:
        return struct.unpack_from("<f", block, offset)[0]

    def _validated_observation(
        self,
        current_health: float,
        maximum_health: float,
        current_mana: float,
        maximum_mana: float,
        current_stamina: float,
        maximum_stamina: float,
    ) -> NativePlayerVitalsObservation:
        maximum_plausible = self._profile.maximum_plausible_vital
        validated = []
        for current, maximum, name in (
            (current_health, maximum_health, "health"),
            (current_mana, maximum_mana, "mana"),
            (current_stamina, maximum_stamina, "stamina"),
        ):
            if (
                not isfinite(current)
                or not isfinite(maximum)
                or current < 0
                or maximum <= 0
                or maximum > maximum_plausible
            ):
                raise NativePlayerVitalsReadError(
                    f"player {name} is outside calibrated plausible bounds"
                )
            tolerance = max(0.001, maximum * 0.00001)
            if current > maximum + tolerance:
                raise NativePlayerVitalsReadError(
                    f"player current {name} exceeds maximum"
                )
            validated.extend((min(current, maximum), maximum))
        return NativePlayerVitalsObservation(*validated)


def open_windows_native_player_vitals_reader(
    profile: NativePlayerVitalsProfile,
) -> NativePlayerVitalsReader:
    process = WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
    try:
        return NativePlayerVitalsReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_vitals_profile() -> NativePlayerVitalsProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_vitals_profile_text(resource.read_text(encoding="utf-8"))


def load_native_vitals_profile(path: str | Path) -> NativePlayerVitalsProfile:
    return load_native_vitals_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_vitals_profile_text(text: str) -> NativePlayerVitalsProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeVitalsProfileLoadError("native vitals profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "native vitals profile")
        expected = {
            "schema_version",
            "profile_id",
            "executable_name",
            "executable_sha256",
            "pointer_size",
            "player_pointer_rva",
            "current_health_offset",
            "maximum_health_offset",
            "current_mana_offset",
            "maximum_mana_offset",
            "current_stamina_offset",
            "maximum_stamina_offset",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_plausible_vital",
        }
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeVitalsProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeVitalsProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        return NativePlayerVitalsProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            player_pointer_rva=_integer(data, "player_pointer_rva"),
            current_health_offset=_integer(data, "current_health_offset"),
            maximum_health_offset=_integer(data, "maximum_health_offset"),
            current_mana_offset=_integer(data, "current_mana_offset"),
            maximum_mana_offset=_integer(data, "maximum_mana_offset"),
            current_stamina_offset=_integer(data, "current_stamina_offset"),
            maximum_stamina_offset=_integer(data, "maximum_stamina_offset"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            maximum_plausible_vital=_number(data, "maximum_plausible_vital"),
            schema_version=_integer(data, "schema_version"),
        )
    except NativeVitalsProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeVitalsProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeVitalsProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeVitalsProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeVitalsProfileLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NativeVitalsProfileLoadError(f"{key} must be a number")
    return float(value)
