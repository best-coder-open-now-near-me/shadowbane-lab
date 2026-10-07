"""Build-guarded, read-only enumeration of loaded Shadowbane characters."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from math import isfinite
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.build_compatibility import (
    native_layout_is_compatible,
)
from shadowbane_lab.client_observation.native_health import (
    BlockReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_registry import (
    NativeObjectRegistryProfile,
    NativeObjectRegistryReader,
    NativeObjectRegistryReadError,
    NativeObjectRegistrySnapshotChanged,
    NativeRegistrySnapshot,
)
from shadowbane_lab.client_observation.native_target_action import (
    NativeTargetActionObservation,
    NativeTargetActionReader,
    NativeTargetActionReadError,
)

NATIVE_CHARACTER_POPULATION_PROFILE_SCHEMA_VERSION = 4
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-character-population.json"


class NativeCharacterPopulationError(RuntimeError):
    """Base error for guarded native character-population observation."""


class NativeCharacterPopulationCompatibilityError(NativeCharacterPopulationError):
    """Raised when the running executable does not match its population profile."""


class NativeCharacterPopulationReadError(NativeCharacterPopulationError):
    """Raised when the loaded character population cannot be read safely."""


class NativeCharacterPopulationSnapshotChanged(NativeCharacterPopulationReadError):
    """Registry rereads disagreed; no population from this transaction is usable."""


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
    object_type_offset: int
    object_uuid_offset: int
    player_object_uuid: int
    npc_object_uuid: int
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
    pet_data_descriptor_rva: int
    descriptor_key_offset: int
    sparse_value_pointer_offset: int
    maximum_sparse_table_bits: int
    registry_profile: NativeObjectRegistryProfile
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
            (self.object_type_offset, "object_type_offset"),
            (self.object_uuid_offset, "object_uuid_offset"),
            (self.player_object_uuid, "player_object_uuid"),
            (self.npc_object_uuid, "npc_object_uuid"),
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
            (self.pet_data_descriptor_rva, "pet_data_descriptor_rva"),
            (self.descriptor_key_offset, "descriptor_key_offset"),
            (self.sparse_value_pointer_offset, "sparse_value_pointer_offset"),
            (self.maximum_sparse_table_bits, "maximum_sparse_table_bits"),
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
        if self.object_uuid_offset != self.object_type_offset + 4:
            raise ValueError("character object key must be two adjacent 32-bit fields")
        if self.player_object_uuid == self.npc_object_uuid:
            raise ValueError("player and NPC object UUID classes must differ")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if (not isinstance(self.registry_profile, NativeObjectRegistryProfile)
                or self.registry_profile.executable_name != self.executable_name
                or self.registry_profile.pointer_size != self.pointer_size
                or self.registry_profile.object_key_offset != self.object_type_offset
                or self.registry_profile.minimum_user_address != self.minimum_user_address
                or self.registry_profile.maximum_user_address != self.maximum_user_address):
            raise ValueError("population and registry profile geometry must agree")
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
            self.object_uuid_offset + 4,
            self.maximum_health_offset + 4,
            self.position_component_offset + self.pointer_size,
            self.action_target_pointer_offset + self.pointer_size,
            self.sparse_data_offset + self.pointer_size * 2,
        )


class NativeCharacterKind(StrEnum):
    """Structurally calibrated live ArcCharacter category."""

    PLAYER = "player"
    NPC = "npc"
    PET = "pet"
    UNKNOWN = "unknown"


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
    object_key: NativeObjectKey | None = None
    character_kind: NativeCharacterKind = NativeCharacterKind.UNKNOWN
    owner_object_key: NativeObjectKey | None = None

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
        if self.object_key is not None:
            if not isinstance(self.object_key, NativeObjectKey):
                raise ValueError("character object_key must be NativeObjectKey when present")
            if self.object_key.is_null:
                raise ValueError("character object_key must be non-null when present")
        if not isinstance(self.character_kind, NativeCharacterKind):
            raise ValueError("character_kind must be NativeCharacterKind")
        if self.owner_object_key is not None:
            if not isinstance(self.owner_object_key, NativeObjectKey):
                raise ValueError("owner_object_key must be NativeObjectKey when present")
            if not self.owner_object_key.object_type or not self.owner_object_key.object_uuid:
                raise ValueError("owner_object_key must contain two nonzero fields")
            if self.owner_object_key == self.object_key:
                raise ValueError("character cannot own itself")
            if self.character_kind != NativeCharacterKind.PET:
                raise ValueError("character with a pet owner must have PET kind")

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
                ("pet", self.character_kind == NativeCharacterKind.PET),
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
    # Successful registry-backed observation revision; not an engine lifetime/generation.
    scan_generation: int
    rejected_candidates: int
    local_player_object_key: NativeObjectKey | None = None
    selection_observed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.selection_observed, bool):
            raise ValueError("selection_observed must be boolean")
        if not self.selection_observed and self.selected_target_token is not None:
            raise ValueError("unavailable selection cannot contain a token")
        tokens = tuple(character.token for character in self.characters)
        if len(tokens) != len(set(tokens)):
            raise ValueError("character population tokens must be unique")
        object_keys = tuple(
            character.object_key
            for character in self.characters
            if character.object_key is not None
        )
        if len(object_keys) != len(set(object_keys)):
            raise ValueError("character population object keys must be unique")
        if self.local_player_object_key is not None:
            if not isinstance(self.local_player_object_key, NativeObjectKey):
                raise ValueError("local_player_object_key must be NativeObjectKey when present")
            if self.local_player_object_key.is_null:
                raise ValueError("local_player_object_key must be non-null when present")
            if self.local_player_object_key in object_keys:
                raise ValueError("local player object key must not appear in character population")
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


@dataclass(frozen=True, slots=True)
class NativeCharacterDetailObservation:
    """Fresh population-owned character state with optional native action detail."""

    character: NativeCharacterObservation
    action: NativeTargetActionObservation | None

    def __post_init__(self) -> None:
        if not isinstance(self.character, NativeCharacterObservation):
            raise ValueError("character detail requires a native character")
        if self.action is not None and (
            not isinstance(self.action, NativeTargetActionObservation)
            or not self.action.target_present or self.action.target_token != self.character.token
        ):
            raise ValueError("character action detail resolved a different object")


class NativeCharacterPopulationReader:
    """Reads registry-owned ArcCharacters and refreshes their exact native fields."""

    def __init__(
        self,
        profile: NativeCharacterPopulationProfile,
        process: BlockReadOnlyProcessMemory,
    ) -> None:
        if not isinstance(profile, NativeCharacterPopulationProfile):
            raise ValueError("profile must be NativeCharacterPopulationProfile")
        if not isinstance(process, BlockReadOnlyProcessMemory):
            raise ValueError("process must support guarded native reads")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeCharacterPopulationCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if not native_layout_is_compatible(
            profile.executable_sha256,
            process.executable_sha256,
        ):
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
        try:
            self._registry = NativeObjectRegistryReader(profile.registry_profile, process)
        except NativeObjectRegistryReadError as exc:
            raise NativeCharacterPopulationCompatibilityError(str(exc)) from exc
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
                ("pet", profile.pet_data_descriptor_rva),
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
        registry = self._capture_registry()
        player = self._read_pointer(self._player_slot, "local player")
        try:
            selected = self._read_pointer(self._selected_slot, "selected target")
            selection_observed = (
                selected == 0 or self._profile.minimum_user_address <= selected
                <= self._profile.maximum_user_address - self._profile.pointer_size
            )
        except NativeCharacterPopulationReadError:
            selected, selection_observed = 0, False
        player_block = self._read_object_block(player, "local player")
        if struct.unpack_from("<I", player_block)[0] != self._character_vtable:
            raise NativeCharacterPopulationReadError(
                "local player is not the calibrated ArcCharacter type"
            )
        player_action_target = struct.unpack_from(
            "<I", player_block, self._profile.action_target_pointer_offset
        )[0]
        if player_action_target:
            self._require_pointer(
                player_action_target, self._profile.pointer_size, "local player action target"
            )
        player_object_key = self._read_object_key(player_block, "local player")
        self._require_registered_actor(registry, player, player_object_key)
        characters: list[NativeCharacterObservation] = []
        rejected = 0
        for entry in registry.objects:
            self._check_registry_budget(registry)
            address = entry.address
            if entry.vtable != self._character_vtable or address == player:
                continue
            try:
                character = self._read_character(address)
                if character.object_key != entry.key:
                    raise NativeCharacterPopulationReadError(
                        "registered character identity changed"
                    )
            except NativeCharacterPopulationReadError:
                rejected += 1
                continue
            self._check_registry_budget(registry)
            characters.append(character)
        character_keys = tuple(character.object_key for character in characters)
        if len(character_keys) != len(set(character_keys)):
            raise NativeCharacterPopulationReadError(
                "loaded character object identities are duplicated"
            )
        if player_object_key in character_keys:
            raise NativeCharacterPopulationReadError(
                "local player object identity appears in loaded character population"
            )
        if self._read_pointer(self._player_slot, "local player") != player:
            raise NativeCharacterPopulationReadError("local player changed during population read")
        try:
            selection_observed &= (
                self._read_pointer(self._selected_slot, "selected target") == selected
            )
        except NativeCharacterPopulationReadError:
            selection_observed = False
        player_verification = self._read_object_block(player, "local player verification")
        if struct.unpack_from("<I", player_verification)[0] != self._character_vtable:
            raise NativeCharacterPopulationReadError(
                "local player type changed during population read"
            )
        if (
            self._read_object_key(player_verification, "local player verification")
            != player_object_key
        ):
            raise NativeCharacterPopulationReadError(
                "local player identity changed during population read"
            )
        if struct.unpack_from(
            "<I", player_verification, self._profile.action_target_pointer_offset
        )[0] != player_action_target:
            raise NativeCharacterPopulationReadError(
                "local player action target changed during population read"
            )
        self._verify_registry(registry)
        if self.observe_actor_identity() != (
            self._token(player), player_object_key,
            self._token(player_action_target) if player_action_target else None,
        ):
            raise NativeCharacterPopulationReadError(
                "local actor changed during registry verification"
            )
        self._check_registry_budget(registry)
        self._scan_generation += 1
        characters.sort(key=lambda character: character.token)
        return NativeCharacterPopulationObservation(
            characters=tuple(characters),
            selected_target_token=(
                self._token(selected) if selected and selection_observed else None
            ),
            selection_observed=selection_observed,
            player_action_target_token=(
                self._token(player_action_target) if player_action_target else None
            ),
            scan_generation=self._scan_generation,
            rejected_candidates=rejected,
            local_player_object_key=player_object_key,
        )

    def observe_actor_identity(self) -> tuple[str, NativeObjectKey, str | None]:
        """Read the local actor binding and AF8 through the canonical population layout.

        This identity boundary deliberately never reads UI selection.
        """
        if self._closed:
            raise NativeCharacterPopulationReadError("native population reader is closed")
        player = self._read_pointer(self._player_slot, "local player")
        first = self._read_object_block(player, "local actor identity")
        second = self._read_object_block(player, "local actor identity verification")
        key = self._read_object_key(first, "local actor")
        action = struct.unpack_from("<I", first, self._profile.action_target_pointer_offset)[0]
        if action:
            self._require_pointer(action, self._profile.pointer_size, "local action target")
        if (struct.unpack_from("<I", first)[0] != self._character_vtable
                or struct.unpack_from("<I", second)[0] != self._character_vtable
                or self._read_object_key(second, "local actor verification") != key
                or struct.unpack_from("<I", second, self._profile.action_target_pointer_offset)[0]
                != action or self._read_pointer(self._player_slot, "local player") != player):
            raise NativeCharacterPopulationReadError("local actor identity changed during read")
        return self._token(player), key, self._token(action) if action else None

    def resolve_actor_address(self, *, local_key: NativeObjectKey, token: str) -> int:
        """Fresh canonical actor hint, without selecting or inventing a target."""
        if (not isinstance(local_key, NativeObjectKey) or local_key.is_null
                or local_key.object_uuid != 53 or not isinstance(token, str) or not token):
            raise ValueError("actor resolution requires exact player key and token")
        registry = self._capture_registry()
        before = self.observe_actor_identity()
        address = self._read_pointer(self._player_slot, "local player")
        if before[:2] != (token, local_key) or self._token(address) != token:
            raise NativeCharacterPopulationReadError("actor resolution identity differs")
        self._require_registered_actor(registry, address, local_key)
        self._verify_registry(registry)
        if (self.observe_actor_identity()[:2] != (token, local_key)
                or self._read_pointer(self._player_slot, "local player") != address):
            raise NativeCharacterPopulationReadError("actor changed during address resolution")
        self._check_registry_budget(registry)
        return address

    def resolve_combat_addresses(
        self, *, local_key: NativeObjectKey, target_token: str, target_key: NativeObjectKey,
    ) -> tuple[int, int]:
        """Return fresh comparison hints for the exact canonical actor/target.

        Tokens stay opaque. Only freshly verified registry members
        may resolve; the native receiver independently resolves and retains the
        keys, then compares these hints without dereferencing them.
        """
        if (not isinstance(local_key, NativeObjectKey)
                or not isinstance(target_key, NativeObjectKey)
                or not isinstance(target_token, str) or not target_token
                or local_key.is_null or target_key.is_null or local_key == target_key):
            raise ValueError("combat address resolution requires distinct exact object identities")
        registry = self._capture_registry()
        actor_before = self.observe_actor_identity()
        actor_address = self._read_pointer(self._player_slot, "local player")
        if (actor_before[1] != local_key or local_key.object_uuid != 53
                or self._token(actor_address) != actor_before[0]):
            raise NativeCharacterPopulationReadError("combat actor identity is no longer current")
        self._require_registered_actor(registry, actor_address, local_key)
        matches = [entry.address for entry in registry.objects
                   if entry.vtable == self._character_vtable and entry.key == target_key
                   and self._token(entry.address) == target_token]
        if len(matches) != 1 or matches[0] == actor_address:
            raise NativeCharacterPopulationReadError("combat target is not a canonical candidate")
        target_address = matches[0]
        for _ in range(2):
            target = self._read_character(target_address)
            if target.object_key != target_key or target.token != target_token:
                raise NativeCharacterPopulationReadError("combat target identity changed")
        actor_after = self.observe_actor_identity()
        if (actor_after[:2] != actor_before[:2]
                or self._read_pointer(self._player_slot, "local player") != actor_address):
            raise NativeCharacterPopulationReadError("combat actor changed during resolution")
        self._verify_registry(registry)
        if self.observe_actor_identity() != actor_before:
            raise NativeCharacterPopulationReadError(
                "local actor changed during registry verification"
            )
        self._check_registry_budget(registry)
        return actor_address, target_address

    def observe_character_detail(
        self, token: str, object_key: NativeObjectKey, reader: NativeTargetActionReader,
    ) -> NativeCharacterDetailObservation | None:
        """Refresh an exact registry member, without decoding tokens or reading selection.

        Addresses remain owned here. The action reader receives an address only
        inside a key-checked read transaction; replacement or disappearance yields
        unavailable detail, never a selected-target fallback.
        """
        if not isinstance(reader, NativeTargetActionReader) or reader.process_id != self.process_id:
            raise ValueError("bound action reader must use the population process")
        if not isinstance(token, str) or not token or not isinstance(object_key, NativeObjectKey):
            raise ValueError("bound action requires an exact token and object key")
        registry = self._capture_registry()
        actor_before = self.observe_actor_identity()
        actor_address = self._read_pointer(self._player_slot, "local player")
        self._require_registered_actor(registry, actor_address, actor_before[1])
        if self._token(actor_address) != actor_before[0]:
            raise NativeCharacterPopulationReadError("local actor changed before bound action read")
        address = next((entry.address for entry in registry.objects
                        if entry.vtable == self._character_vtable and entry.key == object_key
                        and self._token(entry.address) == token), None)
        if address is None:
            return None
        try:
            before = self._read_character(address)
            if before.object_key != object_key:
                return None
            try:
                action = reader.observe_character(address)
            except NativeTargetActionReadError:
                action = None
            after = self._read_character(address)
            if after.object_key != object_key:
                return None
            if action is not None and action.target_token != token:
                raise ValueError("bound action reader returned a different object")
        except NativeCharacterPopulationReadError:
            return None
        if self.observe_actor_identity() != actor_before:
            raise NativeCharacterPopulationReadError("local actor changed during bound action read")
        self._verify_registry(registry)
        if self.observe_actor_identity() != actor_before:
            raise NativeCharacterPopulationReadError(
                "local actor changed during registry verification"
            )
        self._check_registry_budget(registry)
        return NativeCharacterDetailObservation(after, action)

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeCharacterPopulationReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _capture_registry(self) -> NativeRegistrySnapshot:
        if self._closed:
            raise NativeCharacterPopulationReadError("native population reader is closed")
        try:
            snapshot = self._registry.capture()
        except NativeObjectRegistrySnapshotChanged as exc:
            raise NativeCharacterPopulationSnapshotChanged(str(exc)) from exc
        except NativeObjectRegistryReadError as exc:
            raise NativeCharacterPopulationReadError(str(exc)) from exc
        if sum(entry.vtable == self._character_vtable for entry in snapshot.objects) > (
            self._profile.maximum_candidate_characters
        ):
            raise NativeCharacterPopulationReadError("registered character limit was exceeded")
        return snapshot

    def _verify_registry(self, snapshot: NativeRegistrySnapshot) -> None:
        try:
            self._registry.verify(snapshot)
        except NativeObjectRegistrySnapshotChanged as exc:
            raise NativeCharacterPopulationSnapshotChanged(str(exc)) from exc
        except NativeObjectRegistryReadError as exc:
            raise NativeCharacterPopulationReadError(str(exc)) from exc

    def _check_registry_budget(self, snapshot: NativeRegistrySnapshot) -> None:
        try:
            self._registry.check_budget(snapshot)
        except NativeObjectRegistryReadError as exc:
            raise NativeCharacterPopulationReadError(str(exc)) from exc

    def _require_registered_actor(
        self, snapshot: NativeRegistrySnapshot, address: int, key: NativeObjectKey,
    ) -> None:
        if not any(entry.address == address and entry.key == key
                   and entry.vtable == self._character_vtable for entry in snapshot.objects):
            raise NativeCharacterPopulationReadError("local actor is not an exact registry member")

    def _read_character(self, address: int) -> NativeCharacterObservation:
        profile = self._profile
        block = self._read_object_block(address, "ArcCharacter candidate")
        if struct.unpack_from("<I", block)[0] != self._character_vtable:
            raise NativeCharacterPopulationReadError("candidate vtable changed")
        object_key = self._read_object_key(block, "candidate")
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
        roles, owner_key = self._read_sparse_values(buckets, table_bits)
        if owner_key == object_key:
            raise NativeCharacterPopulationReadError("candidate cannot own itself")
        action_target = struct.unpack_from("<I", block, profile.action_target_pointer_offset)[0]
        if action_target:
            self._require_pointer(action_target, profile.pointer_size, "action target")
        if self._read_pointer(address, "candidate vtable") != self._character_vtable:
            raise NativeCharacterPopulationReadError("candidate changed during population read")
        verified_block = self._read_object_block(address, "ArcCharacter candidate verification")
        if self._read_object_key(verified_block, "candidate verification") != object_key:
            raise NativeCharacterPopulationReadError("candidate identity changed during read")
        if struct.unpack_from("<I", verified_block, profile.action_target_pointer_offset)[0] != (
            action_target
        ):
            raise NativeCharacterPopulationReadError("candidate action target changed during read")
        if struct.unpack_from("<II", verified_block, profile.sparse_data_offset) != (
            buckets, table_bits
        ):
            raise NativeCharacterPopulationReadError("candidate sparse header changed during read")
        if self._read_sparse_values(buckets, table_bits) != (roles, owner_key):
            raise NativeCharacterPopulationReadError("candidate sparse values changed during read")
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
            object_key=object_key,
            character_kind=(
                NativeCharacterKind.PET
                if owner_key is not None else self._character_kind(object_key)
            ),
            owner_object_key=owner_key,
        )

    def _read_object_key(self, block: bytes, label: str) -> NativeObjectKey:
        object_type, object_uuid = struct.unpack_from(
            "<II", block, self._profile.object_type_offset
        )
        key = NativeObjectKey(object_type, object_uuid)
        if key.is_null or object_type == 0 or object_uuid == 0:
            raise NativeCharacterPopulationReadError(f"{label} object identity contains zero")
        return key

    def _character_kind(self, object_key: NativeObjectKey) -> NativeCharacterKind:
        if object_key.object_uuid == self._profile.player_object_uuid:
            return NativeCharacterKind.PLAYER
        if object_key.object_uuid == self._profile.npc_object_uuid:
            return NativeCharacterKind.NPC
        return NativeCharacterKind.UNKNOWN

    def _read_sparse_values(
        self, buckets: int, table_bits: int
    ) -> tuple[dict[str, bool], NativeObjectKey | None]:
        profile = self._profile
        if table_bits > profile.maximum_sparse_table_bits:
            raise NativeCharacterPopulationReadError("sparse-data table exceeds calibrated bound")
        values = dict.fromkeys(self._descriptor_keys, False)
        owner_key = None
        if buckets == 0:
            return values, owner_key
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
            if role == "pet":
                # petData stores the owner key inline; unlike boolean descriptors,
                # its second word is a UUID class, NOT a pointer to another value.
                self._require_pointer(value_node, 8, "pet owner key")
                raw_owner = self._read_exact(value_node, 8, "pet owner key")
                owner_key = NativeObjectKey(*struct.unpack("<II", raw_owner))
                if not owner_key.object_type or not owner_key.object_uuid:
                    raise NativeCharacterPopulationReadError("pet owner key contains zero")
                if self._read_exact(value_node, 8, "pet owner verification") != raw_owner:
                    raise NativeCharacterPopulationReadError("pet owner changed during read")
                values[role] = True
                continue
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
        if self._read_exact(buckets, table_size, "sparse table verification") != table:
            raise NativeCharacterPopulationReadError("sparse table changed during read")
        return values, owner_key

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
            read = self._process.read if size <= 64 else self._process.read_block
            value = read(address, size)
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
            process,
        )
    except Exception:
        process.close()
        raise


def load_bundled_native_character_population_profile() -> NativeCharacterPopulationProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
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
        values = dict(raw)
        registry = values["registry_profile"]
        if not isinstance(registry, dict):
            raise ValueError("registry_profile must be an object")
        registry = dict(registry)
        if not isinstance(registry.get("executable_sha256s"), list):
            raise ValueError("registry executable_sha256s must be an array")
        registry["executable_sha256s"] = tuple(registry["executable_sha256s"])
        values["registry_profile"] = NativeObjectRegistryProfile(**registry)
        return NativeCharacterPopulationProfile(**cast(dict[str, Any], values))
    except (TypeError, ValueError) as exc:
        raise NativeCharacterPopulationProfileLoadError(str(exc)) from exc
