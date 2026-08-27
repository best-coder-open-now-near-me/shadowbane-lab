"""Build-guarded, lossless observation of Shadowbane skill and power vectors."""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal, cast

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_TRAINING_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-training.json"
_VECTOR_METADATA_SIZE = 12
_MAX_NATIVE_READ_SIZE = 64


class NativePlayerTrainingError(RuntimeError):
    """Base error for guarded native skill/power observation."""


class NativePlayerTrainingCompatibilityError(NativePlayerTrainingError):
    """Raised when the running executable does not match the calibrated build."""


class NativePlayerTrainingReadError(NativePlayerTrainingError):
    """Raised when a native training vector cannot be read or validated safely."""


class NativeTrainingProfileLoadError(ValueError):
    """Raised when a native training profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeTrainingToken:
    """A stable client token with a simulator-facing semantic name."""

    token: int
    key: str
    display_name: str

    def __post_init__(self) -> None:
        if isinstance(self.token, bool) or not isinstance(self.token, int):
            raise ValueError("token must be an integer")
        if not 0 <= self.token <= 0xFFFFFFFF:
            raise ValueError("token must fit an unsigned 32-bit value")
        for value, field_name in ((self.key, "key"), (self.display_name, "display_name")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class NativePlayerTrainingProfile:
    """Exact executable identity, vector offsets, and known token catalog for one build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    skill_vector_offset: int
    power_vector_offset: int
    vector_entry_size: int
    maximum_skill_count: int
    maximum_power_count: int
    maximum_plausible_rank: int
    minimum_user_address: int
    maximum_user_address: int
    skill_tokens: tuple[NativeTrainingToken, ...]
    power_tokens: tuple[NativeTrainingToken, ...]
    schema_version: int = NATIVE_TRAINING_PROFILE_SCHEMA_VERSION

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
        if self.pointer_size != 4 or self.vector_entry_size != 16:
            raise ValueError("only the verified 32-bit client vector layout is supported")
        for field_name in (
            "player_pointer_rva",
            "skill_vector_offset",
            "power_vector_offset",
            "maximum_skill_count",
            "maximum_power_count",
            "maximum_plausible_rank",
            "minimum_user_address",
            "maximum_user_address",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.skill_vector_offset == self.power_vector_offset:
            raise ValueError("skill and power vector offsets must differ")
        if self.skill_vector_offset % self.pointer_size:
            raise ValueError("skill_vector_offset must be pointer aligned")
        if self.power_vector_offset % self.pointer_size:
            raise ValueError("power_vector_offset must be pointer aligned")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        self._validate_catalog(self.skill_tokens, "skill_tokens")
        self._validate_catalog(self.power_tokens, "power_tokens")
        if self.schema_version != NATIVE_TRAINING_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native training profile version")

    @staticmethod
    def _validate_catalog(tokens: tuple[NativeTrainingToken, ...], field_name: str) -> None:
        if not isinstance(tokens, tuple):
            raise ValueError(f"{field_name} must be a tuple")
        token_values = tuple(item.token for item in tokens)
        keys = tuple(item.key for item in tokens)
        if len(token_values) != len(set(token_values)):
            raise ValueError(f"{field_name} must not contain duplicate tokens")
        if len(keys) != len(set(keys)):
            raise ValueError(f"{field_name} must not contain duplicate keys")


@dataclass(frozen=True, slots=True)
class NativeTrainingEntry:
    """One lossless 16-byte client skill or power record."""

    token: int
    key: str
    display_name: str
    trained_rank: int
    effective_rank: int
    effective_rank_max: int
    catalogued: bool

    def __post_init__(self) -> None:
        if isinstance(self.token, bool) or not isinstance(self.token, int):
            raise ValueError("token must be an integer")
        if not 0 <= self.token <= 0xFFFFFFFF:
            raise ValueError("token must fit an unsigned 32-bit value")
        for value, field_name in ((self.key, "key"), (self.display_name, "display_name")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name in ("trained_rank", "effective_rank", "effective_rank_max"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.effective_rank > self.effective_rank_max:
            raise ValueError("effective_rank cannot exceed effective_rank_max")
        if not isinstance(self.catalogued, bool):
            raise ValueError("catalogued must be a boolean")

    def as_dict(self) -> dict[str, str | int | bool]:
        return {
            "token": self.token,
            "token_hex": f"0x{self.token:08X}",
            "key": self.key,
            "display_name": self.display_name,
            "trained_rank": self.trained_rank,
            "effective_rank": self.effective_rank,
            "effective_rank_max": self.effective_rank_max,
            "catalogued": self.catalogued,
        }


@dataclass(frozen=True, slots=True)
class NativePlayerTrainingObservation:
    skills: tuple[NativeTrainingEntry, ...]
    powers: tuple[NativeTrainingEntry, ...]

    def __post_init__(self) -> None:
        for entries, field_name in ((self.skills, "skills"), (self.powers, "powers")):
            tokens = tuple(item.token for item in entries)
            if len(tokens) != len(set(tokens)):
                raise ValueError(f"{field_name} must not contain duplicate tokens")

    def as_dict(self) -> dict[str, object]:
        return {
            "skills": [entry.as_dict() for entry in self.skills],
            "powers": [entry.as_dict() for entry in self.powers],
        }


@dataclass(frozen=True, slots=True)
class _VectorMetadata:
    start: int
    end: int
    capacity_end: int
    count: int


class NativePlayerTrainingReader:
    """Reads both player vectors only when their metadata and player pointer are stable."""

    def __init__(
        self,
        profile: NativePlayerTrainingProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativePlayerTrainingProfile):
            raise ValueError("profile must be NativePlayerTrainingProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if isinstance(stability_attempts, bool) or not isinstance(stability_attempts, int):
            raise ValueError("stability_attempts must be an integer")
        if stability_attempts <= 0:
            raise ValueError("stability_attempts must be positive")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativePlayerTrainingCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativePlayerTrainingCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativePlayerTrainingCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativePlayerTrainingCompatibilityError("process image base is invalid")
        pointer_slot = process.base_address + profile.player_pointer_rva
        if pointer_slot + profile.pointer_size > profile.maximum_user_address:
            raise NativePlayerTrainingCompatibilityError(
                "calibrated player-pointer slot is outside the 32-bit user range"
            )
        self._profile = profile
        self._process = process
        self._pointer_slot = pointer_slot
        self._skill_catalog = {item.token: item for item in profile.skill_tokens}
        self._power_catalog = {item.token: item for item in profile.power_tokens}
        self._stability_attempts = stability_attempts
        self._closed = False

    @property
    def profile(self) -> NativePlayerTrainingProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativePlayerTrainingObservation:
        if self._closed:
            raise NativePlayerTrainingReadError("native player-training reader is closed")
        profile = self._profile
        for _ in range(self._stability_attempts):
            player_pointer = self._read_pointer()
            self._require_plausible_player_pointer(player_pointer)
            try:
                skill_before = self._read_vector_metadata(
                    player_pointer + profile.skill_vector_offset,
                    maximum_count=profile.maximum_skill_count,
                    vector_name="skill",
                )
                power_before = self._read_vector_metadata(
                    player_pointer + profile.power_vector_offset,
                    maximum_count=profile.maximum_power_count,
                    vector_name="power",
                )
                skill_data = self._read_vector_data(skill_before, "skill")
                power_data = self._read_vector_data(power_before, "power")
                skill_after = self._read_vector_metadata(
                    player_pointer + profile.skill_vector_offset,
                    maximum_count=profile.maximum_skill_count,
                    vector_name="skill",
                )
                power_after = self._read_vector_metadata(
                    player_pointer + profile.power_vector_offset,
                    maximum_count=profile.maximum_power_count,
                    vector_name="power",
                )
            except NativePlayerTrainingReadError:
                if self._read_pointer() != player_pointer:
                    continue
                raise
            except Exception as exc:
                if self._read_pointer() != player_pointer:
                    continue
                raise NativePlayerTrainingReadError(
                    f"could not read player training vectors: {type(exc).__name__}"
                ) from exc
            if self._read_pointer() != player_pointer:
                continue
            if skill_before != skill_after or power_before != power_after:
                continue
            return NativePlayerTrainingObservation(
                skills=self._decode_entries(skill_data, "skill"),
                powers=self._decode_entries(power_data, "power"),
            )
        raise NativePlayerTrainingReadError(
            "player pointer or training-vector metadata changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativePlayerTrainingReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_pointer(self) -> int:
        try:
            value = self._process.read(self._pointer_slot, self._profile.pointer_size)
        except Exception as exc:
            raise NativePlayerTrainingReadError(
                f"could not read player pointer: {type(exc).__name__}"
            ) from exc
        if len(value) != self._profile.pointer_size:
            raise NativePlayerTrainingReadError(
                "native process backend returned a partial player pointer"
            )
        return struct.unpack("<I", value)[0]

    def _require_plausible_player_pointer(self, pointer: int) -> None:
        profile = self._profile
        final_offset = max(profile.skill_vector_offset, profile.power_vector_offset)
        final_offset += _VECTOR_METADATA_SIZE
        if (
            pointer < profile.minimum_user_address
            or pointer + final_offset > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativePlayerTrainingReadError(
                "player pointer is outside the calibrated 32-bit user range"
            )

    def _read_vector_metadata(
        self,
        address: int,
        *,
        maximum_count: int,
        vector_name: str,
    ) -> _VectorMetadata:
        try:
            raw = self._process.read(address, _VECTOR_METADATA_SIZE)
        except Exception as exc:
            raise NativePlayerTrainingReadError(
                f"could not read {vector_name} vector metadata: {type(exc).__name__}"
            ) from exc
        if len(raw) != _VECTOR_METADATA_SIZE:
            raise NativePlayerTrainingReadError(
                f"native process backend returned partial {vector_name} vector metadata"
            )
        start, end, capacity_end = struct.unpack("<III", raw)
        if start == end == capacity_end == 0:
            return _VectorMetadata(0, 0, 0, 0)
        profile = self._profile
        if not start <= end <= capacity_end:
            raise NativePlayerTrainingReadError(f"{vector_name} vector pointers are not ordered")
        if (
            start < profile.minimum_user_address
            or capacity_end > profile.maximum_user_address
            or start % profile.pointer_size
            or end % profile.pointer_size
            or capacity_end % profile.pointer_size
        ):
            raise NativePlayerTrainingReadError(
                f"{vector_name} vector is outside the calibrated 32-bit user range"
            )
        used_bytes = end - start
        capacity_bytes = capacity_end - start
        if used_bytes % profile.vector_entry_size or capacity_bytes % profile.vector_entry_size:
            raise NativePlayerTrainingReadError(f"{vector_name} vector size is not entry aligned")
        count = used_bytes // profile.vector_entry_size
        capacity_count = capacity_bytes // profile.vector_entry_size
        if count > maximum_count or capacity_count > maximum_count:
            raise NativePlayerTrainingReadError(
                f"{vector_name} vector exceeds its calibrated count bound"
            )
        return _VectorMetadata(start, end, capacity_end, count)

    def _read_vector_data(self, metadata: _VectorMetadata, vector_name: str) -> bytes:
        if metadata.count == 0:
            return b""
        expected = metadata.end - metadata.start
        chunks: list[bytes] = []
        cursor = metadata.start
        while cursor < metadata.end:
            chunk_size = min(_MAX_NATIVE_READ_SIZE, metadata.end - cursor)
            try:
                chunk = self._process.read(cursor, chunk_size)
            except Exception as exc:
                raise NativePlayerTrainingReadError(
                    f"could not read {vector_name} vector entries: {type(exc).__name__}"
                ) from exc
            if len(chunk) != chunk_size:
                raise NativePlayerTrainingReadError(
                    f"native process backend returned partial {vector_name} vector entries"
                )
            chunks.append(chunk)
            cursor += chunk_size
        raw = b"".join(chunks)
        if len(raw) != expected:
            raise NativePlayerTrainingReadError(
                f"native process backend returned partial {vector_name} vector entries"
            )
        return raw

    def _decode_entries(
        self,
        raw: bytes,
        vector_kind: Literal["skill", "power"],
    ) -> tuple[NativeTrainingEntry, ...]:
        profile = self._profile
        catalog = self._skill_catalog if vector_kind == "skill" else self._power_catalog
        entries: list[NativeTrainingEntry] = []
        seen_tokens: set[int] = set()
        for offset in range(0, len(raw), profile.vector_entry_size):
            token, trained_rank, effective_rank, effective_rank_max = struct.unpack_from(
                "<IIII", raw, offset
            )
            if token in seen_tokens:
                raise NativePlayerTrainingReadError(
                    f"{vector_kind} vector contains duplicate token 0x{token:08X}"
                )
            seen_tokens.add(token)
            if any(
                rank > profile.maximum_plausible_rank
                for rank in (trained_rank, effective_rank, effective_rank_max)
            ):
                raise NativePlayerTrainingReadError(
                    f"{vector_kind} token 0x{token:08X} has an implausible rank"
                )
            if effective_rank > effective_rank_max:
                raise NativePlayerTrainingReadError(
                    f"{vector_kind} token 0x{token:08X} has inconsistent effective ranks"
                )
            definition = catalog.get(token)
            if definition is None:
                key = f"{vector_kind}_0x{token:08x}"
                display_name = f"Unknown {vector_kind} 0x{token:08X}"
            else:
                key = definition.key
                display_name = definition.display_name
            entries.append(
                NativeTrainingEntry(
                    token=token,
                    key=key,
                    display_name=display_name,
                    trained_rank=trained_rank,
                    effective_rank=effective_rank,
                    effective_rank_max=effective_rank_max,
                    catalogued=definition is not None,
                )
            )
        return tuple(entries)


def open_windows_native_player_training_reader(
    profile: NativePlayerTrainingProfile,
) -> NativePlayerTrainingReader:
    process = WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
    try:
        return NativePlayerTrainingReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_training_profile() -> NativePlayerTrainingProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
    return load_native_training_profile_text(resource.read_text(encoding="utf-8"))


def load_native_training_profile(path: str | Path) -> NativePlayerTrainingProfile:
    return load_native_training_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_training_profile_text(text: str) -> NativePlayerTrainingProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeTrainingProfileLoadError("native training profile is not valid JSON") from exc
    expected = {
        "schema_version",
        "profile_id",
        "executable_name",
        "executable_sha256",
        "pointer_size",
        "player_pointer_rva",
        "skill_vector_offset",
        "power_vector_offset",
        "vector_entry_size",
        "maximum_skill_count",
        "maximum_power_count",
        "maximum_plausible_rank",
        "minimum_user_address",
        "maximum_user_address",
        "skill_tokens",
        "power_tokens",
    }
    try:
        data = _mapping(raw, "native training profile")
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeTrainingProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeTrainingProfileLoadError(f"unknown fields: {', '.join(sorted(unknown))}")
        return NativePlayerTrainingProfile(
            profile_id=_string(data, "profile_id"),
            executable_name=_string(data, "executable_name"),
            executable_sha256=_string(data, "executable_sha256"),
            pointer_size=_integer(data, "pointer_size"),
            player_pointer_rva=_integer(data, "player_pointer_rva"),
            skill_vector_offset=_integer(data, "skill_vector_offset"),
            power_vector_offset=_integer(data, "power_vector_offset"),
            vector_entry_size=_integer(data, "vector_entry_size"),
            maximum_skill_count=_integer(data, "maximum_skill_count"),
            maximum_power_count=_integer(data, "maximum_power_count"),
            maximum_plausible_rank=_integer(data, "maximum_plausible_rank"),
            minimum_user_address=_integer(data, "minimum_user_address"),
            maximum_user_address=_integer(data, "maximum_user_address"),
            skill_tokens=_tokens(data, "skill_tokens"),
            power_tokens=_tokens(data, "power_tokens"),
            schema_version=_integer(data, "schema_version"),
        )
    except NativeTrainingProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeTrainingProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeTrainingProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeTrainingProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeTrainingProfileLoadError(f"{key} must be an integer")
    return value


def _tokens(data: Mapping[str, Any], key: str) -> tuple[NativeTrainingToken, ...]:
    raw = data[key]
    if not isinstance(raw, list):
        raise NativeTrainingProfileLoadError(f"{key} must be an array")
    result: list[NativeTrainingToken] = []
    expected = {"token", "key", "display_name"}
    for index, value in enumerate(raw):
        item = _mapping(value, f"{key}[{index}]")
        missing = expected - set(item)
        unknown = set(item) - expected
        if missing or unknown:
            detail = "missing" if missing else "unknown"
            fields = missing if missing else unknown
            raise NativeTrainingProfileLoadError(
                f"{key}[{index}] has {detail} fields: {', '.join(sorted(fields))}"
            )
        result.append(
            NativeTrainingToken(
                token=_integer(item, "token"),
                key=_string(item, "key"),
                display_name=_string(item, "display_name"),
            )
        )
    return tuple(result)
