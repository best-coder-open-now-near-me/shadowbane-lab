"""Build-guarded, read-only enumeration of loaded Shadowbane characters."""

from __future__ import annotations

import hashlib
import json
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.native_health import (
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.client_observation.native_message_hud import (
    ScanningReadOnlyProcessMemory,
)

NATIVE_CHARACTER_POPULATION_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-character-population.json"


class NativeCharacterPopulationError(RuntimeError):
    """Base error for guarded native character-population observation."""


class NativeCharacterPopulationCompatibilityError(NativeCharacterPopulationError):
    """Raised when the running executable does not match its population profile."""


class NativeCharacterPopulationReadError(NativeCharacterPopulationError):
    """Raised when the loaded character population cannot be read safely."""


class NativeCharacterPopulationProfileLoadError(ValueError):
    """Raised when a native character-population profile is malformed."""


@dataclass(frozen=True, slots=True)
class NativeCharacterPopulationProfile:
    """Exact build identity and ArcCharacter pool layout for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    selected_pointer_rva: int
    arc_character_vtable_rva: int
    current_health_offset: int
    maximum_health_offset: int
    position_component_offset: int
    component_value_offset: int
    position_value_offset: int
    action_target_pointer_offset: int
    sparse_data_offset: int
    merchant_data_descriptor_rva: int
    shopkeeper_descriptor_rva: int
    banker_descriptor_rva: int
    trainer_descriptor_rva: int
    minion_descriptor_rva: int
    descriptor_key_offset: int
    sparse_value_pointer_offset: int
    maximum_sparse_table_bits: int
    scan_memory_type: int
    scan_protection: int
    maximum_scan_address: int
    maximum_candidate_characters: int
    minimum_user_address: int
    maximum_user_address: int
    minimum_world_coordinate: float
    maximum_world_coordinate: float
    minimum_altitude: float
    maximum_altitude: float
    schema_version: int = NATIVE_CHARACTER_POPULATION_PROFILE_SCHEMA_VERSION

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
            (self.selected_pointer_rva, "selected_pointer_rva"),
            (self.arc_character_vtable_rva, "arc_character_vtable_rva"),
            (self.current_health_offset, "current_health_offset"),
            (self.maximum_health_offset, "maximum_health_offset"),
            (self.position_component_offset, "position_component_offset"),
            (self.action_target_pointer_offset, "action_target_pointer_offset"),
            (self.sparse_data_offset, "sparse_data_offset"),
            (self.merchant_data_descriptor_rva, "merchant_data_descriptor_rva"),
            (self.shopkeeper_descriptor_rva, "shopkeeper_descriptor_rva"),
            (self.banker_descriptor_rva, "banker_descriptor_rva"),
            (self.trainer_descriptor_rva, "trainer_descriptor_rva"),
            (self.minion_descriptor_rva, "minion_descriptor_rva"),
            (self.descriptor_key_offset, "descriptor_key_offset"),
            (self.sparse_value_pointer_offset, "sparse_value_pointer_offset"),
            (self.maximum_sparse_table_bits, "maximum_sparse_table_bits"),
            (self.scan_memory_type, "scan_memory_type"),
            (self.scan_protection, "scan_protection"),
            (self.maximum_scan_address, "maximum_scan_address"),
            (self.maximum_candidate_characters, "maximum_candidate_characters"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        for value, field_name in (
            (self.component_value_offset, "component_value_offset"),
            (self.position_value_offset, "position_value_offset"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.maximum_health_offset != self.current_health_offset + 4:
            raise ValueError("maximum health must immediately follow current health")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if not self.minimum_user_address < self.maximum_scan_address <= self.maximum_user_address:
            raise ValueError("maximum_scan_address must lie inside the calibrated user range")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit pointer")
        if not self.minimum_world_coordinate < self.maximum_world_coordinate:
            raise ValueError("world coordinate bounds are invalid")
        if not self.minimum_altitude < self.maximum_altitude:
            raise ValueError("altitude bounds are invalid")
        if self.schema_version != NATIVE_CHARACTER_POPULATION_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native character-population profile version")

    @property
    def object_read_size(self) -> int:
        return max(
            self.maximum_health_offset + 4,
            self.position_component_offset + self.pointer_size,
            self.action_target_pointer_offset + self.pointer_size,
            self.sparse_data_offset + self.pointer_size * 2,
        )


@dataclass(frozen=True, slots=True)
class NativeCharacterObservation:
    """One loaded ArcCharacter resolved without selecting it."""

    token: str
    current_health: float
    maximum_health: float
    lt: float
    lg: float
    altitude: float
    merchant: bool
    shopkeeper: bool
    banker: bool
    trainer: bool
    minion: bool
    action_target_token: str | None = None

    def __post_init__(self) -> None:
        if not self.token.strip():
            raise ValueError("character token must be non-empty")
        for value, field_name in (
            (self.current_health, "current_health"),
            (self.maximum_health, "maximum_health"),
            (self.lt, "lt"),
            (self.lg, "lg"),
            (self.altitude, "altitude"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"character {field_name} must be finite")
        if self.current_health < 0 or self.maximum_health <= 0:
            raise ValueError("character health values are outside valid bounds")
        if self.current_health > self.maximum_health:
            raise ValueError("character current health cannot exceed maximum health")
        for value in (self.merchant, self.shopkeeper, self.banker, self.trainer, self.minion):
            if not isinstance(value, bool):
                raise ValueError("character role flags must be boolean")
        if self.action_target_token is not None and not self.action_target_token.strip():
            raise ValueError("action_target_token must be non-empty when present")

    @property
    def alive(self) -> bool:
        return self.current_health > 0

    @property
    def protected_roles(self) -> tuple[str, ...]:
        return tuple(
            role
            for role, enabled in (
                ("merchant", self.merchant),
                ("shopkeeper", self.shopkeeper),
                ("banker", self.banker),
                ("trainer", self.trainer),
                ("minion", self.minion),
            )
            if enabled
        )

    @property
    def attack_eligible(self) -> bool:
        return self.alive and not self.protected_roles


@dataclass(frozen=True, slots=True)
class NativeCharacterPopulationObservation:
    """One coherent loaded-character frame plus independent target channels."""

    characters: tuple[NativeCharacterObservation, ...]
    selected_target_token: str | None
    player_action_target_token: str | None
    scan_generation: int
    rejected_candidates: int

    def __post_init__(self) -> None:
        tokens = tuple(character.token for character in self.characters)
        if len(tokens) != len(set(tokens)):
            raise ValueError("character population tokens must be unique")
        if self.selected_target_token is not None and not self.selected_target_token.strip():
            raise ValueError("selected_target_token must be non-empty when present")
        if (
            self.player_action_target_token is not None
            and not self.player_action_target_token.strip()
        ):
            raise ValueError("player_action_target_token must be non-empty when present")
        for value, field_name in (
            (self.scan_generation, "scan_generation"),
            (self.rejected_candidates, "rejected_candidates"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be non-negative")


class NativeCharacterPopulationReader:
    """Enumerates ArcCharacter objects and then refreshes their exact native fields."""

    def __init__(
        self,
        profile: NativeCharacterPopulationProfile,
        process: ScanningReadOnlyProcessMemory,
        *,
        rescan_interval_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(profile, NativeCharacterPopulationProfile):
            raise ValueError("profile must be NativeCharacterPopulationProfile")
        if not isinstance(process, ScanningReadOnlyProcessMemory):
            raise ValueError("process must support guarded native scans")
        if (
            isinstance(rescan_interval_seconds, bool)
            or not isinstance(rescan_interval_seconds, (int, float))
            or not isfinite(rescan_interval_seconds)
            or rescan_interval_seconds <= 0
        ):
            raise ValueError("rescan_interval_seconds must be positive and finite")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeCharacterPopulationCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if process.executable_sha256.casefold() != profile.executable_sha256.casefold():
            raise NativeCharacterPopulationCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeCharacterPopulationCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        self._profile = profile
        self._process = process
        self._player_slot = process.base_address + profile.player_pointer_rva
        self._selected_slot = process.base_address + profile.selected_pointer_rva
        self._character_vtable = process.base_address + profile.arc_character_vtable_rva
        self._rescan_interval_seconds = float(rescan_interval_seconds)
        self._clock = clock
        self._candidate_addresses: tuple[int, ...] = ()
        self._last_scan_at: float | None = None
        self._scan_generation = 0
        self._closed = False
        self._descriptor_keys = {
            role: self._read_descriptor_key(rva, role)
            for role, rva in (
                ("merchant", profile.merchant_data_descriptor_rva),
                ("shopkeeper", profile.shopkeeper_descriptor_rva),
                ("banker", profile.banker_descriptor_rva),
                ("trainer", profile.trainer_descriptor_rva),
                ("minion", profile.minion_descriptor_rva),
            )
        }
        if len(set(self._descriptor_keys.values())) != len(self._descriptor_keys):
            raise NativeCharacterPopulationCompatibilityError(
                "calibrated sparse role descriptors do not have unique keys"
            )

    @property
    def profile(self) -> NativeCharacterPopulationProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeCharacterPopulationObservation:
        if self._closed:
            raise NativeCharacterPopulationReadError("native population reader is closed")
        now = self._clock()
        if self._last_scan_at is None or now - self._last_scan_at >= self._rescan_interval_seconds:
            self._scan_candidates(now)
        player = self._read_pointer(self._player_slot, "local player")
        selected = self._read_pointer(self._selected_slot, "selected target")
        player_block = self._read_object_block(player, "local player")
        if struct.unpack_from("<I", player_block)[0] != self._character_vtable:
            raise NativeCharacterPopulationReadError(
                "local player is not the calibrated ArcCharacter type"
            )
        player_action_target = struct.unpack_from(
            "<I", player_block, self._profile.action_target_pointer_offset
        )[0]
        characters: list[NativeCharacterObservation] = []
        rejected = 0
        for address in self._candidate_addresses:
            if address == player:
                continue
            try:
                character = self._read_character(address)
            except NativeCharacterPopulationReadError:
                rejected += 1
                continue
            characters.append(character)
        if self._read_pointer(self._player_slot, "local player") != player:
            raise NativeCharacterPopulationReadError("local player changed during population read")
        if self._read_pointer(self._selected_slot, "selected target") != selected:
            raise NativeCharacterPopulationReadError("selection changed during population read")
        characters.sort(key=lambda character: character.token)
        return NativeCharacterPopulationObservation(
            characters=tuple(characters),
            selected_target_token=self._token(selected) if selected else None,
            player_action_target_token=(
                self._token(player_action_target) if player_action_target else None
            ),
            scan_generation=self._scan_generation,
            rejected_candidates=rejected,
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeCharacterPopulationReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _scan_candidates(self, now: float) -> None:
        needle = struct.pack("<I", self._character_vtable)
        hits = self._process.find_all(
            (needle,),
            memory_type=self._profile.scan_memory_type,
            protection=self._profile.scan_protection,
            maximum_results_per_needle=self._profile.maximum_candidate_characters,
            maximum_address=self._profile.maximum_scan_address,
        )[needle]
        candidates = tuple(
            address
            for address in hits
            if address % self._profile.pointer_size == 0
            and self._profile.minimum_user_address <= address < self._profile.maximum_user_address
        )
        if len(candidates) > self._profile.maximum_candidate_characters:
            raise NativeCharacterPopulationReadError(
                "native character candidate limit was exceeded"
            )
        self._candidate_addresses = candidates
        self._last_scan_at = now
        self._scan_generation += 1

    def _read_character(self, address: int) -> NativeCharacterObservation:
        profile = self._profile
        block = self._read_object_block(address, "ArcCharacter candidate")
        if struct.unpack_from("<I", block)[0] != self._character_vtable:
            raise NativeCharacterPopulationReadError("candidate vtable changed")
        current, maximum = struct.unpack_from("<ff", block, profile.current_health_offset)
        if not isfinite(current) or not isfinite(maximum) or maximum <= 0:
            raise NativeCharacterPopulationReadError("candidate health is structurally invalid")
        tolerance = max(0.001, maximum * 0.00001)
        if current > maximum + tolerance:
            raise NativeCharacterPopulationReadError("candidate current health exceeds maximum")
        component = struct.unpack_from("<I", block, profile.position_component_offset)[0]
        self._require_pointer(component, profile.pointer_size, "position component")
        value_pointer = self._read_pointer(
            component + profile.component_value_offset,
            "position value",
        )
        self._require_pointer(value_pointer, profile.position_value_offset + 12, "position value")
        x, altitude, z = struct.unpack(
            "<fff",
            self._read_exact(value_pointer + profile.position_value_offset, 12, "position"),
        )
        if not all(isfinite(value) for value in (x, altitude, z)):
            raise NativeCharacterPopulationReadError("candidate position is not finite")
        if not (
            profile.minimum_world_coordinate <= x <= profile.maximum_world_coordinate
            and -profile.maximum_world_coordinate <= z <= -profile.minimum_world_coordinate
            and profile.minimum_altitude <= altitude <= profile.maximum_altitude
        ):
            raise NativeCharacterPopulationReadError("candidate position is outside world bounds")
        buckets, table_bits = struct.unpack_from("<II", block, profile.sparse_data_offset)
        roles = self._read_sparse_values(buckets, table_bits)
        action_target = struct.unpack_from("<I", block, profile.action_target_pointer_offset)[0]
        if action_target:
            self._require_pointer(action_target, profile.pointer_size, "action target")
        if self._read_pointer(address, "candidate vtable") != self._character_vtable:
            raise NativeCharacterPopulationReadError("candidate changed during population read")
        return NativeCharacterObservation(
            token=self._token(address),
            current_health=max(0.0, min(current, maximum)),
            maximum_health=maximum,
            lt=x,
            lg=-z,
            altitude=altitude,
            merchant=roles["merchant"],
            shopkeeper=roles["shopkeeper"],
            banker=roles["banker"],
            trainer=roles["trainer"],
            minion=roles["minion"],
            action_target_token=self._token(action_target) if action_target else None,
        )

    def _read_sparse_values(self, buckets: int, table_bits: int) -> dict[str, bool]:
        profile = self._profile
        if table_bits > profile.maximum_sparse_table_bits:
            raise NativeCharacterPopulationReadError("sparse-data table exceeds calibrated bound")
        values = dict.fromkeys(self._descriptor_keys, False)
        if buckets == 0:
            return values
        table_size = (1 << table_bits) * 8
        self._require_pointer(buckets, table_size, "sparse-data bucket table")
        table = self._read_exact(buckets, table_size, "sparse-data bucket table")
        roles_by_key = {key: role for role, key in self._descriptor_keys.items()}
        nodes: dict[str, int] = {}
        for key, value_node in struct.iter_unpack("<II", table):
            role = roles_by_key.get(key)
            if role is None:
                continue
            if role == "merchant":
                values[role] = True
            elif role in nodes:
                raise NativeCharacterPopulationReadError("sparse role key is duplicated")
            else:
                nodes[role] = value_node
        for role, value_node in nodes.items():
            self._require_pointer(
                value_node,
                profile.sparse_value_pointer_offset + profile.pointer_size,
                f"{role} sparse value node",
            )
            value_pointer = self._read_pointer(
                value_node + profile.sparse_value_pointer_offset,
                f"{role} sparse value",
            )
            self._require_pointer(value_pointer, 1, f"{role} sparse value")
            raw = self._read_exact(value_pointer, 1, f"{role} role flag")[0]
            if raw not in (0, 1):
                raise NativeCharacterPopulationReadError(f"{role} role flag is not boolean")
            values[role] = bool(raw)
        return values

    def _read_descriptor_key(self, rva: int, role: str) -> int:
        address = self._process.base_address + rva + self._profile.descriptor_key_offset
        try:
            key = self._read_pointer(address, f"{role} descriptor key")
        except NativeCharacterPopulationReadError as exc:
            raise NativeCharacterPopulationCompatibilityError(str(exc)) from exc
        if key in (0, 0xFFFFFFFF):
            raise NativeCharacterPopulationCompatibilityError(
                f"calibrated {role} descriptor key is invalid"
            )
        return key

    def _read_object_block(self, address: int, label: str) -> bytes:
        self._require_pointer(address, self._profile.object_read_size, label)
        try:
            value = self._process.read_block(address, self._profile.object_read_size)
        except Exception as exc:
            raise NativeCharacterPopulationReadError(
                f"could not read {label}: {type(exc).__name__}"
            ) from exc
        if len(value) != self._profile.object_read_size:
            raise NativeCharacterPopulationReadError(f"partial {label} read")
        return value

    def _read_pointer(self, address: int, label: str) -> int:
        return struct.unpack("<I", self._read_exact(address, 4, f"{label} pointer"))[0]

    def _read_exact(self, address: int, size: int, label: str) -> bytes:
        try:
            value = self._process.read(address, size)
        except Exception as exc:
            raise NativeCharacterPopulationReadError(
                f"could not read {label}: {type(exc).__name__}"
            ) from exc
        if len(value) != size:
            raise NativeCharacterPopulationReadError(f"partial {label} read")
        return value

    def _require_pointer(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + size > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeCharacterPopulationReadError(
                f"{label} pointer is outside the calibrated 32-bit user range"
            )

    def _token(self, pointer: int) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<II", self._process.pid, pointer))
        return digest.hexdigest()


def open_windows_native_character_population_reader(
    profile: NativeCharacterPopulationProfile,
    *,
    process_id: int | None = None,
) -> NativeCharacterPopulationReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(profile.executable_name, process_id)
    )
    try:
        return NativeCharacterPopulationReader(
            profile,
            cast(ScanningReadOnlyProcessMemory, process),
        )
    except Exception:
        process.close()
        raise


def load_bundled_native_character_population_profile() -> NativeCharacterPopulationProfile:
    resource = files("shadowbane_lab.client_observation").joinpath(
        "data", _BUNDLED_PROFILE_NAME
    )
    return load_native_character_population_profile_text(resource.read_text(encoding="utf-8"))


def load_native_character_population_profile(
    path: str | Path,
) -> NativeCharacterPopulationProfile:
    return load_native_character_population_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_character_population_profile_text(
    text: str,
) -> NativeCharacterPopulationProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeCharacterPopulationProfileLoadError(
            "native character-population profile is not valid JSON"
        ) from exc
    if not isinstance(raw, Mapping):
        raise NativeCharacterPopulationProfileLoadError(
            "native character-population profile must be an object"
        )
    expected = set(NativeCharacterPopulationProfile.__dataclass_fields__)
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise NativeCharacterPopulationProfileLoadError(
            f"native character-population profile has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise NativeCharacterPopulationProfileLoadError(
            f"native character-population profile is missing fields: {', '.join(sorted(missing))}"
        )
    try:
        return NativeCharacterPopulationProfile(**cast(dict[str, Any], dict(raw)))
    except (TypeError, ValueError) as exc:
        raise NativeCharacterPopulationProfileLoadError(str(exc)) from exc
