"""Build-guarded, read-only access to stable local-player progression fields."""

from __future__ import annotations

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

NATIVE_PROGRESSION_CORE_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-progression-core.json"
_MAX_NATIVE_READ_SIZE = 64


class NativePlayerProgressionCoreError(RuntimeError):
    """Base error for guarded native progression-core observation."""


class NativePlayerProgressionCoreCompatibilityError(NativePlayerProgressionCoreError):
    """Raised when the running executable does not match the calibrated build."""


class NativePlayerProgressionCoreReadError(NativePlayerProgressionCoreError):
    """Raised when native progression fields cannot be read or validated safely."""


class NativeProgressionCoreProfileLoadError(ValueError):
    """Raised when a native progression-core profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativePlayerProgressionCoreProfile:
    """Exact executable identity and stable player-progression offsets for one build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    training_points_offset: int
    ability_points_offset: int
    level_offset: int
    left_attack_rating_offset: int
    right_attack_rating_offset: int
    defense_offset: int
    minimum_user_address: int
    maximum_user_address: int
    maximum_level: int
    maximum_plausible_points: int
    maximum_plausible_rating: int
    schema_version: int = NATIVE_PROGRESSION_CORE_PROFILE_SCHEMA_VERSION

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
        for field_name in (
            "player_pointer_rva",
            "training_points_offset",
            "ability_points_offset",
            "level_offset",
            "left_attack_rating_offset",
            "right_attack_rating_offset",
            "defense_offset",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_level",
            "maximum_plausible_points",
            "maximum_plausible_rating",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        offsets = self.value_offsets
        if len(offsets) != len(set(offsets)):
            raise ValueError("progression-core value offsets must be unique")
        if any(offset % 4 for offset in offsets):
            raise ValueError("progression-core value offsets must be four-byte aligned")
        if self.right_attack_rating_offset != self.left_attack_rating_offset + 4:
            raise ValueError("verified left and right attack ratings must be adjacent")
        if self.defense_offset != self.right_attack_rating_offset + 4:
            raise ValueError("verified defense must follow the attack-rating fields")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.schema_version != NATIVE_PROGRESSION_CORE_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native progression-core profile version")

    @property
    def value_offsets(self) -> tuple[int, ...]:
        return (
            self.training_points_offset,
            self.ability_points_offset,
            self.level_offset,
            self.left_attack_rating_offset,
            self.right_attack_rating_offset,
            self.defense_offset,
        )


@dataclass(frozen=True, slots=True)
class NativePlayerProgressionCoreObservation:
    level: int
    unspent_ability_points: int
    unspent_training_points: int
    left_attack_rating: int
    right_attack_rating: int
    defense: int

    def __post_init__(self) -> None:
        if isinstance(self.level, bool) or not isinstance(self.level, int) or self.level < 1:
            raise ValueError("level must be a positive integer")
        for field_name in (
            "unspent_ability_points",
            "unspent_training_points",
            "left_attack_rating",
            "right_attack_rating",
            "defense",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")

    def as_dict(self) -> dict[str, int]:
        return {
            "level": self.level,
            "unspent_ability_points": self.unspent_ability_points,
            "unspent_training_points": self.unspent_training_points,
            "left_attack_rating": self.left_attack_rating,
            "right_attack_rating": self.right_attack_rating,
            "defense": self.defense,
        }


class NativePlayerProgressionCoreReader:
    """Decodes stable progression fields from an already opened read-only process."""

    def __init__(
        self,
        profile: NativePlayerProgressionCoreProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativePlayerProgressionCoreProfile):
            raise ValueError("profile must be NativePlayerProgressionCoreProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativePlayerProgressionCoreCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativePlayerProgressionCoreCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativePlayerProgressionCoreCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativePlayerProgressionCoreCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.player_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativePlayerProgressionCoreCompatibilityError(
                "calibrated player-pointer slot is outside the 32-bit user range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativePlayerProgressionCoreProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativePlayerProgressionCoreObservation:
        if self._closed:
            raise NativePlayerProgressionCoreReadError("native player-progression reader is closed")
        profile = self._profile
        first_offset = min(profile.value_offsets)
        final_offset = max(profile.value_offsets) + 4
        for _ in range(self._stability_attempts):
            player_pointer = self._read_pointer()
            self._require_plausible_player_pointer(player_pointer, final_offset)
            try:
                block = self._read_bounded(
                    player_pointer + first_offset, final_offset - first_offset
                )
            except Exception as exc:
                if self._read_pointer() != player_pointer:
                    continue
                raise NativePlayerProgressionCoreReadError(
                    f"could not read player progression: {type(exc).__name__}"
                ) from exc
            if len(block) != final_offset - first_offset:
                raise NativePlayerProgressionCoreReadError(
                    "native process backend returned partial progression values"
                )
            if self._read_pointer() != player_pointer:
                continue

            values = {
                offset: struct.unpack_from("<i", block, offset - first_offset)[0]
                for offset in profile.value_offsets
            }
            return self._validated_observation(
                level=values[profile.level_offset],
                unspent_ability_points=values[profile.ability_points_offset],
                unspent_training_points=values[profile.training_points_offset],
                left_attack_rating=values[profile.left_attack_rating_offset],
                right_attack_rating=values[profile.right_attack_rating_offset],
                defense=values[profile.defense_offset],
            )
        raise NativePlayerProgressionCoreReadError(
            "player pointer changed during every stable-read attempt"
        )

    def _read_bounded(self, address: int, size: int) -> bytes:
        chunks: list[bytes] = []
        consumed = 0
        while consumed < size:
            chunk_size = min(_MAX_NATIVE_READ_SIZE, size - consumed)
            chunk = self._process.read(address + consumed, chunk_size)
            if len(chunk) != chunk_size:
                raise NativePlayerProgressionCoreReadError(
                    "native process backend returned partial progression values"
                )
            chunks.append(chunk)
            consumed += chunk_size
        return b"".join(chunks)

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativePlayerProgressionCoreReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_pointer(self) -> int:
        try:
            value = self._process.read(self._pointer_slot, self._profile.pointer_size)
        except Exception as exc:
            raise NativePlayerProgressionCoreReadError(
                f"could not read player pointer: {type(exc).__name__}"
            ) from exc
        if len(value) != self._profile.pointer_size:
            raise NativePlayerProgressionCoreReadError(
                "native process backend returned a partial player pointer"
            )
        return struct.unpack("<I", value)[0]

    def _require_plausible_player_pointer(self, pointer: int, final_offset: int) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + final_offset > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativePlayerProgressionCoreReadError(
                "player pointer is outside the calibrated 32-bit user range"
            )

    def _validated_observation(
        self,
        *,
        level: int,
        unspent_ability_points: int,
        unspent_training_points: int,
        left_attack_rating: int,
        right_attack_rating: int,
        defense: int,
    ) -> NativePlayerProgressionCoreObservation:
        profile = self._profile
        if not 1 <= level <= profile.maximum_level:
            raise NativePlayerProgressionCoreReadError(
                "player level is outside calibrated plausible bounds"
            )
        for value, name in (
            (unspent_ability_points, "ability points"),
            (unspent_training_points, "training points"),
        ):
            if not 0 <= value <= profile.maximum_plausible_points:
                raise NativePlayerProgressionCoreReadError(
                    f"player {name} are outside calibrated plausible bounds"
                )
        for value, name in (
            (left_attack_rating, "left attack rating"),
            (right_attack_rating, "right attack rating"),
            (defense, "defense"),
        ):
            if not 0 <= value <= profile.maximum_plausible_rating:
                raise NativePlayerProgressionCoreReadError(
                    f"player {name} is outside calibrated plausible bounds"
                )
        return NativePlayerProgressionCoreObservation(
            level=level,
            unspent_ability_points=unspent_ability_points,
            unspent_training_points=unspent_training_points,
            left_attack_rating=left_attack_rating,
            right_attack_rating=right_attack_rating,
            defense=defense,
        )


def open_windows_native_player_progression_core_reader(
    profile: NativePlayerProgressionCoreProfile,
) -> NativePlayerProgressionCoreReader:
    process = WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
    try:
        return NativePlayerProgressionCoreReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_progression_core_profile() -> NativePlayerProgressionCoreProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
    return load_native_progression_core_profile_text(resource.read_text(encoding="utf-8"))


def load_native_progression_core_profile(
    path: str | Path,
) -> NativePlayerProgressionCoreProfile:
    return load_native_progression_core_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_progression_core_profile_text(
    text: str,
) -> NativePlayerProgressionCoreProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeProgressionCoreProfileLoadError(
            "native progression-core profile is not valid JSON"
        ) from exc
    expected = {
        "schema_version",
        "profile_id",
        "executable_name",
        "executable_sha256",
        "pointer_size",
        "player_pointer_rva",
        "training_points_offset",
        "ability_points_offset",
        "level_offset",
        "left_attack_rating_offset",
        "right_attack_rating_offset",
        "defense_offset",
        "minimum_user_address",
        "maximum_user_address",
        "maximum_level",
        "maximum_plausible_points",
        "maximum_plausible_rating",
    }
    try:
        data = _mapping(raw, "native progression-core profile")
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeProgressionCoreProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeProgressionCoreProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        return NativePlayerProgressionCoreProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            player_pointer_rva=_integer(data, "player_pointer_rva"),
            training_points_offset=_integer(data, "training_points_offset"),
            ability_points_offset=_integer(data, "ability_points_offset"),
            level_offset=_integer(data, "level_offset"),
            left_attack_rating_offset=_integer(data, "left_attack_rating_offset"),
            right_attack_rating_offset=_integer(data, "right_attack_rating_offset"),
            defense_offset=_integer(data, "defense_offset"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            maximum_level=_integer(data, "maximum_level"),
            maximum_plausible_points=_integer(data, "maximum_plausible_points"),
            maximum_plausible_rating=_integer(data, "maximum_plausible_rating"),
            schema_version=_integer(data, "schema_version"),
        )
    except NativeProgressionCoreProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeProgressionCoreProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeProgressionCoreProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeProgressionCoreProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeProgressionCoreProfileLoadError(f"{key} must be an integer")
    return value
