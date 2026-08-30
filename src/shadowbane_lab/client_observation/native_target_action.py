"""Build-guarded, read-only access to selected-target action phases."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.build_compatibility import (
    native_layout_is_compatible,
)
from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_TARGET_ACTION_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-target-action.json"


class NativeTargetActionError(RuntimeError):
    """Base error for guarded native selected-target action observation."""


class NativeTargetActionCompatibilityError(NativeTargetActionError):
    """Raised when the running executable does not match its calibrated build."""


class NativeTargetActionReadError(NativeTargetActionError):
    """Raised when selected-target action state cannot be read safely."""


class NativeTargetActionProfileLoadError(ValueError):
    """Raised when a native selected-target action profile is invalid."""


class NativeTargetActionPhase(StrEnum):
    """Observed phases of the selected character's current native action."""

    IDLE = "idle"
    QUEUED = "queued"
    WINDUP = "windup"
    IMPACT = "impact"
    OTHER_MOTION = "other_motion"


@dataclass(frozen=True, slots=True)
class NativeTargetActionProfile:
    """Exact ArcCharacter action layout for one verified client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    player_pointer_rva: int
    selected_pointer_rva: int
    arc_character_vtable_rva: int
    arc_motion_vtable_rva: int
    current_motion_pointer_offset: int
    current_motion_id_offset: int
    impact_frame_offset: int
    action_pending_offset: int
    target_of_target_pointer_offset: int
    idle_motion_ids: tuple[int, ...]
    observed_attack_motion_ids: tuple[int, ...]
    no_impact_frame_sentinel: int
    maximum_motion_id: int
    maximum_impact_frame: int
    minimum_user_address: int
    maximum_user_address: int
    schema_version: int = NATIVE_TARGET_ACTION_PROFILE_SCHEMA_VERSION

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
            (self.arc_motion_vtable_rva, "arc_motion_vtable_rva"),
            (self.current_motion_pointer_offset, "current_motion_pointer_offset"),
            (self.current_motion_id_offset, "current_motion_id_offset"),
            (self.impact_frame_offset, "impact_frame_offset"),
            (self.action_pending_offset, "action_pending_offset"),
            (self.target_of_target_pointer_offset, "target_of_target_pointer_offset"),
            (self.maximum_motion_id, "maximum_motion_id"),
            (self.maximum_impact_frame, "maximum_impact_frame"),
            (self.minimum_user_address, "minimum_user_address"),
            (self.maximum_user_address, "maximum_user_address"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.current_motion_id_offset != self.current_motion_pointer_offset + 4:
            raise ValueError("current motion ID must follow its pointer")
        offsets = (
            self.current_motion_pointer_offset,
            self.current_motion_id_offset,
            self.impact_frame_offset,
            self.action_pending_offset,
            self.target_of_target_pointer_offset,
        )
        if tuple(sorted(offsets)) != offsets or len(set(offsets)) != len(offsets):
            raise ValueError("target-action offsets must be unique and increasing")
        for values, field_name in (
            (self.idle_motion_ids, "idle_motion_ids"),
            (self.observed_attack_motion_ids, "observed_attack_motion_ids"),
        ):
            if not values or len(set(values)) != len(values):
                raise ValueError(f"{field_name} must contain unique values")
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= self.maximum_motion_id
                for value in values
            ):
                raise ValueError(f"{field_name} contains an invalid motion ID")
        if set(self.idle_motion_ids) & set(self.observed_attack_motion_ids):
            raise ValueError("idle and observed attack motion IDs must not overlap")
        if self.no_impact_frame_sentinel >= 0:
            raise ValueError("no_impact_frame_sentinel must be negative")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.schema_version != NATIVE_TARGET_ACTION_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native target-action profile version")


@dataclass(frozen=True, slots=True)
class NativeTargetActionObservation:
    """One coherent selected-target action snapshot."""

    target_present: bool
    phase: NativeTargetActionPhase | None = None
    target_token: str | None = None
    targeting_player: bool | None = None
    motion_id: int | None = None
    action_pending: bool | None = None
    impact_frame: int | None = None
    action_sequence: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be boolean")
        values = (
            self.phase,
            self.target_token,
            self.targeting_player,
            self.motion_id,
            self.action_pending,
            self.impact_frame,
            self.action_sequence,
        )
        if not self.target_present:
            if any(value is not None for value in values):
                raise ValueError("an absent target cannot contain action values")
            return
        if self.phase is None or not isinstance(self.phase, NativeTargetActionPhase):
            raise ValueError("a present target requires a native action phase")
        if self.target_token is None or not self.target_token.strip():
            raise ValueError("a present target requires an opaque target token")
        if not isinstance(self.targeting_player, bool):
            raise ValueError("targeting_player must be boolean for a present target")
        if isinstance(self.motion_id, bool) or not isinstance(self.motion_id, int):
            raise ValueError("a present target requires an integer motion ID")
        if not isinstance(self.action_pending, bool):
            raise ValueError("action_pending must be boolean for a present target")
        if self.impact_frame is not None and (
            isinstance(self.impact_frame, bool) or not isinstance(self.impact_frame, int)
        ):
            raise ValueError("impact_frame must be an integer when present")
        if (
            isinstance(self.action_sequence, bool)
            or not isinstance(self.action_sequence, int)
            or self.action_sequence < 0
        ):
            raise ValueError("action_sequence must be non-negative for a present target")

    @property
    def interrupt_opportunity(self) -> bool:
        return bool(
            self.target_present
            and self.targeting_player
            and self.phase in (NativeTargetActionPhase.QUEUED, NativeTargetActionPhase.WINDUP)
        )


@dataclass(frozen=True, slots=True)
class NativePlayerActionObservation:
    """One coherent local-player motion/action snapshot."""

    phase: NativeTargetActionPhase
    targeting_selected: bool
    motion_id: int
    action_pending: bool
    impact_frame: int | None
    action_sequence: int
    motion_sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.phase, NativeTargetActionPhase):
            raise ValueError("player action phase must be NativeTargetActionPhase")
        if not isinstance(self.targeting_selected, bool):
            raise ValueError("targeting_selected must be boolean")
        if isinstance(self.motion_id, bool) or not isinstance(self.motion_id, int):
            raise ValueError("player action requires an integer motion ID")
        if not isinstance(self.action_pending, bool):
            raise ValueError("player action_pending must be boolean")
        if self.impact_frame is not None and (
            isinstance(self.impact_frame, bool) or not isinstance(self.impact_frame, int)
        ):
            raise ValueError("player impact_frame must be an integer when present")
        if (
            isinstance(self.action_sequence, bool)
            or not isinstance(self.action_sequence, int)
            or self.action_sequence < 0
        ):
            raise ValueError("player action_sequence must be non-negative")
        if (
            isinstance(self.motion_sequence, bool)
            or not isinstance(self.motion_sequence, int)
            or self.motion_sequence < 0
        ):
            raise ValueError("player motion_sequence must be non-negative")

    @property
    def action_active(self) -> bool:
        return self.phase in (
            NativeTargetActionPhase.QUEUED,
            NativeTargetActionPhase.WINDUP,
        )


@dataclass(frozen=True, slots=True)
class _RawTargetActionSnapshot:
    selected: int
    player: int
    selected_vtable: int
    motion_pointer: int
    motion_vtable: int
    motion_id: int
    impact_frame: int
    action_pending: bool
    target_of_target: int


class NativeTargetActionReader:
    """Reads stable ArcCharacter motion/action transitions without client input."""

    def __init__(
        self,
        profile: NativeTargetActionProfile,
        process: ReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeTargetActionProfile):
            raise ValueError("profile must be NativeTargetActionProfile")
        if not isinstance(process, ReadOnlyProcessMemory):
            raise ValueError("process must implement ReadOnlyProcessMemory")
        if (
            isinstance(stability_attempts, bool)
            or not isinstance(stability_attempts, int)
            or stability_attempts <= 0
        ):
            raise ValueError("stability_attempts must be a positive integer")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeTargetActionCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if not native_layout_is_compatible(
            profile.executable_sha256,
            process.executable_sha256,
        ):
            raise NativeTargetActionCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeTargetActionCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeTargetActionCompatibilityError("process image base is invalid")
        self._profile = profile
        self._process = process
        self._player_pointer_slot = process.base_address + profile.player_pointer_rva
        self._selected_pointer_slot = process.base_address + profile.selected_pointer_rva
        self._character_vtable = process.base_address + profile.arc_character_vtable_rva
        self._motion_vtable = process.base_address + profile.arc_motion_vtable_rva
        for address in (
            self._player_pointer_slot,
            self._selected_pointer_slot,
            self._character_vtable,
            self._motion_vtable,
        ):
            if not profile.minimum_user_address <= address <= profile.maximum_user_address - 4:
                raise NativeTargetActionCompatibilityError(
                    "calibrated target-action address is outside the 32-bit user range"
                )
        self._stability_attempts = stability_attempts
        self._closed = False
        self._last_target = 0
        self._last_action_active = False
        self._last_action_pending = False
        self._action_sequence = 0
        self._last_player_action_active = False
        self._last_player_action_pending = False
        self._last_player_motion_id: int | None = None
        self._player_action_sequence = 0
        self._player_motion_sequence = 0

    @property
    def profile(self) -> NativeTargetActionProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    def observe(self) -> NativeTargetActionObservation:
        if self._closed:
            raise NativeTargetActionReadError("native target-action reader is closed")
        for _ in range(self._stability_attempts):
            selected = self._read_pointer(self._selected_pointer_slot, "selected target")
            if selected == 0:
                self._last_target = 0
                self._last_action_active = False
                self._last_action_pending = False
                return NativeTargetActionObservation(target_present=False)
            player = self._read_pointer(self._player_pointer_slot, "local player")
            try:
                first = self._read_snapshot(selected, player)
                second = self._read_snapshot(selected, player)
            except NativeTargetActionReadError:
                if self._read_pointer(self._selected_pointer_slot, "selected target") != selected:
                    continue
                raise
            if first != second:
                continue
            if (
                self._read_pointer(self._selected_pointer_slot, "selected target") != selected
                or self._read_pointer(self._player_pointer_slot, "local player") != player
            ):
                continue
            return self._observation(second)
        raise NativeTargetActionReadError(
            "selected-target action changed during every stable-read attempt"
        )

    def observe_player(self) -> NativePlayerActionObservation:
        """Read the local player's animation/action state from the same guarded layout."""

        if self._closed:
            raise NativeTargetActionReadError("native target-action reader is closed")
        for _ in range(self._stability_attempts):
            player = self._read_pointer(self._player_pointer_slot, "local player")
            selected = self._read_pointer(self._selected_pointer_slot, "selected target")
            first = self._read_player_snapshot(player, selected)
            second = self._read_player_snapshot(player, selected)
            if first != second:
                continue
            if (
                self._read_pointer(self._player_pointer_slot, "local player") != player
                or self._read_pointer(self._selected_pointer_slot, "selected target") != selected
            ):
                continue
            return self._player_observation(second)
        raise NativeTargetActionReadError(
            "local-player action changed during every stable-read attempt"
        )

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeTargetActionReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _read_snapshot(self, selected: int, player: int) -> _RawTargetActionSnapshot:
        profile = self._profile
        self._require_object_pointer(
            selected,
            profile.target_of_target_pointer_offset + profile.pointer_size,
            "selected target",
        )
        self._require_object_pointer(player, profile.pointer_size, "local player")
        selected_vtable = self._read_pointer(selected, "selected-target vtable")
        if selected_vtable != self._character_vtable:
            raise NativeTargetActionReadError(
                "selected target is not the calibrated ArcCharacter type"
            )
        motion_pointer, motion_id = struct.unpack(
            "<II",
            self._read_exact(
                selected + profile.current_motion_pointer_offset,
                8,
                "current motion and ID",
            ),
        )
        impact_frame = struct.unpack(
            "<i",
            self._read_exact(
                selected + profile.impact_frame_offset,
                4,
                "impact frame",
            ),
        )[0]
        action_pending_raw = self._read_pointer(
            selected + profile.action_pending_offset,
            "action-pending flag",
        )
        target_of_target = self._read_pointer(
            selected + profile.target_of_target_pointer_offset,
            "target-of-target",
        )
        self._require_object_pointer(motion_pointer, profile.pointer_size, "current motion")
        motion_vtable = self._read_pointer(motion_pointer, "current-motion vtable")
        if motion_vtable != self._motion_vtable:
            raise NativeTargetActionReadError(
                "selected target uses an unsupported current-motion type"
            )
        if motion_id > profile.maximum_motion_id:
            raise NativeTargetActionReadError("current motion ID exceeds calibrated bounds")
        if action_pending_raw not in (0, 1):
            raise NativeTargetActionReadError("action-pending flag is not boolean")
        if not (
            impact_frame == profile.no_impact_frame_sentinel
            or 0 <= impact_frame <= profile.maximum_impact_frame
        ):
            raise NativeTargetActionReadError("impact frame is outside calibrated bounds")
        if target_of_target != 0:
            self._require_object_pointer(
                target_of_target,
                profile.pointer_size,
                "target-of-target",
            )
        return _RawTargetActionSnapshot(
            selected=selected,
            player=player,
            selected_vtable=selected_vtable,
            motion_pointer=motion_pointer,
            motion_vtable=motion_vtable,
            motion_id=motion_id,
            impact_frame=impact_frame,
            action_pending=bool(action_pending_raw),
            target_of_target=target_of_target,
        )

    def _read_player_snapshot(
        self,
        player: int,
        selected: int,
    ) -> _RawTargetActionSnapshot:
        profile = self._profile
        self._require_object_pointer(
            player,
            profile.target_of_target_pointer_offset + profile.pointer_size,
            "local player",
        )
        player_vtable = self._read_pointer(player, "local-player vtable")
        if player_vtable != self._character_vtable:
            raise NativeTargetActionReadError(
                "local player is not the calibrated ArcCharacter type"
            )
        motion_pointer, motion_id = struct.unpack(
            "<II",
            self._read_exact(
                player + profile.current_motion_pointer_offset,
                8,
                "local-player current motion and ID",
            ),
        )
        impact_frame = struct.unpack(
            "<i",
            self._read_exact(
                player + profile.impact_frame_offset,
                4,
                "local-player impact frame",
            ),
        )[0]
        action_pending_raw = self._read_pointer(
            player + profile.action_pending_offset,
            "local-player action-pending flag",
        )
        action_target = self._read_pointer(
            player + profile.target_of_target_pointer_offset,
            "local-player action target",
        )
        self._require_object_pointer(motion_pointer, profile.pointer_size, "current motion")
        motion_vtable = self._read_pointer(motion_pointer, "current-motion vtable")
        if motion_vtable != self._motion_vtable:
            raise NativeTargetActionReadError(
                "local player uses an unsupported current-motion type"
            )
        if motion_id > profile.maximum_motion_id:
            raise NativeTargetActionReadError("player motion ID exceeds calibrated bounds")
        if action_pending_raw not in (0, 1):
            raise NativeTargetActionReadError("player action-pending flag is not boolean")
        if not (
            impact_frame == profile.no_impact_frame_sentinel
            or 0 <= impact_frame <= profile.maximum_impact_frame
        ):
            raise NativeTargetActionReadError("player impact frame is outside calibrated bounds")
        if action_target != 0:
            self._require_object_pointer(
                action_target,
                profile.pointer_size,
                "local-player action target",
            )
        return _RawTargetActionSnapshot(
            selected=player,
            player=selected,
            selected_vtable=player_vtable,
            motion_pointer=motion_pointer,
            motion_vtable=motion_vtable,
            motion_id=motion_id,
            impact_frame=impact_frame,
            action_pending=bool(action_pending_raw),
            target_of_target=action_target,
        )

    def _observation(
        self,
        snapshot: _RawTargetActionSnapshot,
    ) -> NativeTargetActionObservation:
        profile = self._profile
        phase = _phase_for_snapshot(profile, snapshot)
        action_active = phase in (
            NativeTargetActionPhase.QUEUED,
            NativeTargetActionPhase.WINDUP,
            NativeTargetActionPhase.IMPACT,
        )
        if snapshot.selected != self._last_target:
            self._last_target = snapshot.selected
            self._last_action_active = False
            self._last_action_pending = False
        new_queue = snapshot.action_pending and not self._last_action_pending
        if new_queue or (action_active and not self._last_action_active):
            self._action_sequence += 1
        self._last_action_active = action_active
        self._last_action_pending = snapshot.action_pending
        return NativeTargetActionObservation(
            target_present=True,
            phase=phase,
            target_token=self._target_token(snapshot.selected),
            targeting_player=snapshot.target_of_target == snapshot.player,
            motion_id=snapshot.motion_id,
            action_pending=snapshot.action_pending,
            impact_frame=(
                None
                if snapshot.impact_frame == profile.no_impact_frame_sentinel
                else snapshot.impact_frame
            ),
            action_sequence=self._action_sequence,
        )

    def _player_observation(
        self,
        snapshot: _RawTargetActionSnapshot,
    ) -> NativePlayerActionObservation:
        profile = self._profile
        phase = _phase_for_snapshot(profile, snapshot)
        action_active = phase in (
            NativeTargetActionPhase.QUEUED,
            NativeTargetActionPhase.WINDUP,
            NativeTargetActionPhase.IMPACT,
        )
        new_queue = snapshot.action_pending and not self._last_player_action_pending
        if new_queue or (action_active and not self._last_player_action_active):
            self._player_action_sequence += 1
        if (
            self._last_player_motion_id is not None
            and snapshot.motion_id != self._last_player_motion_id
        ):
            self._player_motion_sequence += 1
        self._last_player_action_active = action_active
        self._last_player_action_pending = snapshot.action_pending
        self._last_player_motion_id = snapshot.motion_id
        return NativePlayerActionObservation(
            phase=phase,
            targeting_selected=(
                snapshot.player != 0 and snapshot.target_of_target == snapshot.player
            ),
            motion_id=snapshot.motion_id,
            action_pending=snapshot.action_pending,
            impact_frame=(
                None
                if snapshot.impact_frame == profile.no_impact_frame_sentinel
                else snapshot.impact_frame
            ),
            action_sequence=self._player_action_sequence,
            motion_sequence=self._player_motion_sequence,
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
            raise NativeTargetActionReadError(
                f"could not read {label}: {type(exc).__name__}"
            ) from exc
        if len(value) != size:
            raise NativeTargetActionReadError(f"native process backend returned a partial {label}")
        return value

    def _require_object_pointer(self, pointer: int, size: int, label: str) -> None:
        profile = self._profile
        if (
            pointer < profile.minimum_user_address
            or pointer + size > profile.maximum_user_address
            or pointer % profile.pointer_size != 0
        ):
            raise NativeTargetActionReadError(
                f"{label} pointer is outside the calibrated 32-bit user range"
            )

    def _target_token(self, selected: int) -> str:
        digest = hashlib.blake2s(digest_size=12)
        digest.update(self._profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<II", self._process.pid, selected))
        return digest.hexdigest()


def _phase_for_snapshot(
    profile: NativeTargetActionProfile,
    snapshot: _RawTargetActionSnapshot,
) -> NativeTargetActionPhase:
    if snapshot.action_pending:
        return NativeTargetActionPhase.QUEUED
    if snapshot.impact_frame != profile.no_impact_frame_sentinel:
        return NativeTargetActionPhase.IMPACT
    if snapshot.motion_id in profile.observed_attack_motion_ids:
        return NativeTargetActionPhase.WINDUP
    if snapshot.motion_id in profile.idle_motion_ids:
        return NativeTargetActionPhase.IDLE
    return NativeTargetActionPhase.OTHER_MOTION


def open_windows_native_target_action_reader(
    profile: NativeTargetActionProfile,
    *,
    process_id: int | None = None,
) -> NativeTargetActionReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeTargetActionReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_target_action_profile() -> NativeTargetActionProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
    return load_native_target_action_profile_text(resource.read_text(encoding="utf-8"))


def load_native_target_action_profile(path: str | Path) -> NativeTargetActionProfile:
    return load_native_target_action_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_target_action_profile_text(text: str) -> NativeTargetActionProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeTargetActionProfileLoadError(
            "native target-action profile is not valid JSON"
        ) from exc
    try:
        data = _mapping(raw, "native target-action profile")
        expected = set(NativeTargetActionProfile.__dataclass_fields__)
        missing = expected - set(data)
        unknown = set(data) - expected
        if missing:
            raise NativeTargetActionProfileLoadError(
                f"missing required fields: {', '.join(sorted(missing))}"
            )
        if unknown:
            raise NativeTargetActionProfileLoadError(
                f"unknown fields: {', '.join(sorted(unknown))}"
            )
        strings = {"profile_id", "executable_name", "executable_sha256"}
        tuples = {"idle_motion_ids", "observed_attack_motion_ids"}
        values = {
            key: (
                _string(data, key)
                if key in strings
                else _integer_tuple(data, key)
                if key in tuples
                else _integer(data, key)
            )
            for key in expected
        }
        return NativeTargetActionProfile(**values)
    except NativeTargetActionProfileLoadError:
        raise
    except (TypeError, ValueError) as exc:
        raise NativeTargetActionProfileLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NativeTargetActionProfileLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise NativeTargetActionProfileLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise NativeTargetActionProfileLoadError(f"{key} must be an integer")
    return value


def _integer_tuple(data: Mapping[str, Any], key: str) -> tuple[int, ...]:
    value = data[key]
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise NativeTargetActionProfileLoadError(f"{key} must be an integer array")
    return tuple(value)
