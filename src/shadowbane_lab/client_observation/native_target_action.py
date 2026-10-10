"""Exact-image native initiation signals and honest animation telemetry."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.native_health import (
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
)

NATIVE_TARGET_ACTION_PROFILE_SCHEMA_VERSION = 3
_REVIEWED_IMAGES = frozenset({
    "e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8",
    "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e",
    "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5",
    "a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a",
    "051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698",
    "0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d",
    "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903",
    "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
    "1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c",
    "baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9",
})
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-target-action.json"


class NativeTargetActionError(RuntimeError):
    """Base error for guarded native selected-target action observation."""


class NativeTargetActionCompatibilityError(NativeTargetActionError):
    """Raised when the running executable does not match its calibrated build."""


class NativeTargetActionReadError(NativeTargetActionError):
    """Raised when selected-target action state cannot be read safely."""


class NativeTargetActionProfileLoadError(ValueError):
    """Raised when a native selected-target action profile is invalid."""


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
    animation_frame_offset: int
    animation_event_index_offset: int
    target_of_target_pointer_offset: int
    actor_state_pointer_offset: int
    state_mode_offset: int
    state_action_offset: int
    state_initiation_offset: int
    power_protocol_vector_offset: int
    maximum_power_protocol_ids: int
    no_animation_frame_sentinel: int
    maximum_motion_id: int
    maximum_animation_frame: int
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
            (self.animation_frame_offset, "animation_frame_offset"),
            (self.animation_event_index_offset, "animation_event_index_offset"),
            (self.target_of_target_pointer_offset, "target_of_target_pointer_offset"),
            (self.actor_state_pointer_offset, "actor_state_pointer_offset"),
            (self.state_mode_offset, "state_mode_offset"),
            (self.state_action_offset, "state_action_offset"),
            (self.maximum_motion_id, "maximum_motion_id"),
            (self.maximum_animation_frame, "maximum_animation_frame"),
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
            self.animation_frame_offset,
            self.animation_event_index_offset,
            self.target_of_target_pointer_offset,
        )
        if tuple(sorted(offsets)) != offsets or len(set(offsets)) != len(offsets):
            raise ValueError("target-action offsets must be unique and increasing")
        if (
            self.actor_state_pointer_offset % self.pointer_size
            or self.state_mode_offset % self.pointer_size
            or self.state_action_offset != self.state_mode_offset + 8
            or self.actor_state_pointer_offset + self.pointer_size
            > self.target_of_target_pointer_offset
        ):
            raise ValueError("native actor-state offsets do not match the calibrated layout")
        if (self.state_initiation_offset != 0x10
                or self.power_protocol_vector_offset != 0x65C
                or not 1 <= self.maximum_power_protocol_ids <= 256):
            raise ValueError("unsupported initiation observation bounds")
        if self.no_animation_frame_sentinel >= 0:
            raise ValueError("no_animation_frame_sentinel must be negative")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if self.maximum_user_address > 0xFFFFFFFF:
            raise ValueError("maximum_user_address must fit a 32-bit client pointer")
        if self.maximum_user_address <= self.minimum_user_address:
            raise ValueError("maximum_user_address must exceed minimum_user_address")
        if self.schema_version != NATIVE_TARGET_ACTION_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native target-action profile version")


def _validate_initiation(state: int | None, ids: tuple[int, ...] | None) -> None:
    if (state is None) != (ids is None):
        raise ValueError("initiation state and protocol IDs must be observed together")
    if state is not None and (type(state) is not int or not 1 <= state <= 7):
        raise ValueError("initiation state must be uint32")
    if ids is not None and (not isinstance(ids, tuple) or len(ids) > 256
            or any(type(value) is not int or not 0 < value <= 0xFFFFFFFF for value in ids)):
        raise ValueError("protocol IDs must be a bounded tuple of positive uint32 values")


def _validate_animation(motion: int, index: int, frame: int | None) -> None:
    if type(motion) is not int or not 0 <= motion <= 0xFFFFFFFF:
        raise ValueError("motion ID must be uint32")
    if type(index) is not int or not 0 <= index <= 0xFFFFFFFF:
        raise ValueError("animation event index must be uint32")
    if frame is not None and (type(frame) is not int or not 0 <= frame <= 0x7FFFFFFF):
        raise ValueError("animation frame must be nonnegative when observed")


@dataclass(frozen=True, slots=True)
class NativeTargetActionObservation:
    """Stable native initiation signals and animation telemetry; no cast attribution."""

    target_present: bool
    target_token: str | None = None
    targeting_player: bool | None = None
    motion_id: int | None = None
    animation_event_index: int | None = None
    animation_frame: int | None = None
    initiation_state: int | None = None
    power_protocol_ids: tuple[int, ...] | None = None
    mode: int | None = None
    action_state: int | None = None

    def __post_init__(self) -> None:
        if type(self.target_present) is not bool:
            raise ValueError("target_present must be boolean")
        if not self.target_present:
            if any(getattr(self, field) is not None for field in self.__dataclass_fields__
                   if field != "target_present"):
                raise ValueError("an absent target cannot contain action values")
            return
        if not isinstance(self.target_token, str) or not self.target_token.strip():
            raise ValueError("a present target requires an opaque target token")
        if type(self.targeting_player) is not bool:
            raise ValueError("targeting_player must be boolean")
        _validate_animation(self.motion_id, self.animation_event_index, self.animation_frame)
        _validate_initiation(self.initiation_state, self.power_protocol_ids)
        _validate_state(self.mode, self.action_state)

    @property
    def initiation_pending(self) -> bool | None:
        if self.initiation_state is None or self.power_protocol_ids is None:
            return None
        return self.initiation_state == 6 or bool(self.power_protocol_ids)


def _validate_state(mode: int | None, action: int | None) -> None:
    if (mode is None) != (action is None):
        raise ValueError("mode and action state must be observed together")
    if any(v is not None and (type(v) is not int or not 0 <= v <= 0xFFFFFFFF)
           for v in (mode, action)):
        raise ValueError("mode and action state must be uint32")


@dataclass(frozen=True, slots=True)
class NativePlayerActionObservation:
    """Coherent initiation signals, AF8 identity and animation telemetry.

    Protocol IDs retain multiplicity, not a unique cast or effect identity.
    Clear initiation signals are not universal action legality or cleanup proof.
    AF8 does not identify every spell target.
    """

    targeting_selected: bool
    motion_id: int
    animation_event_index: int
    animation_frame: int | None
    selected_target_token: str | None
    action_target_token: str | None
    initiation_state: int | None = None
    power_protocol_ids: tuple[int, ...] | None = None
    mode: int | None = None
    action_state: int | None = None
    selection_observed: bool = True

    def __post_init__(self) -> None:
        if type(self.selection_observed) is not bool or type(self.targeting_selected) is not bool:
            raise ValueError("selection observations must be boolean")
        if not self.selection_observed and self.selected_target_token is not None:
            raise ValueError("unavailable selection cannot contain a token")
        for token in (self.selected_target_token, self.action_target_token):
            if token is not None and (not isinstance(token, str) or not token.strip()):
                raise ValueError("target tokens must be nonempty when present")
        if self.targeting_selected != (self.selected_target_token is not None
                                      and self.action_target_token == self.selected_target_token):
            raise ValueError("targeting_selected must agree with observed target tokens")
        _validate_animation(self.motion_id, self.animation_event_index, self.animation_frame)
        _validate_initiation(self.initiation_state, self.power_protocol_ids)
        _validate_state(self.mode, self.action_state)

    @property
    def initiation_pending(self) -> bool | None:
        if self.initiation_state is None or self.power_protocol_ids is None:
            return None
        return self.initiation_state == 6 or bool(self.power_protocol_ids)

    @property
    def initiation_clear(self) -> bool:
        return self.initiation_pending is False


@dataclass(frozen=True, slots=True)
class _RawTargetActionSnapshot:
    selected: int
    player: int
    selected_vtable: int
    motion_pointer: int
    motion_vtable: int
    motion_id: int
    animation_frame: int
    animation_event_index: int
    target_of_target: int
    state_pointer: int
    mode: int
    action_state: int
    initiation_state: int
    power_protocol_header: tuple[int, int, int]
    power_protocol_ids: tuple[int, ...]


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
        if process.executable_sha256.lower() not in _REVIEWED_IMAGES:
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
            try:
                selected = self._read_pointer(self._selected_pointer_slot, "selected target")
                selection_observed = True
            except NativeTargetActionReadError:
                selected, selection_observed = 0, False
            first = self._read_player_snapshot(player, 0)
            second = self._read_player_snapshot(player, 0)
            if first != second:
                continue
            if self._read_pointer(self._player_pointer_slot, "local player") != player:
                continue
            try:
                selection_observed &= (
                    self._read_pointer(self._selected_pointer_slot, "selected target") == selected
                    and (selected == 0 or self._profile.minimum_user_address <= selected
                         <= self._profile.maximum_user_address - self._profile.pointer_size)
                )
            except NativeTargetActionReadError:
                selection_observed = False
            return replace(
                self._player_observation(
                    replace(second, player=selected if selection_observed else 0),
                ),
                selection_observed=selection_observed,
            )
        raise NativeTargetActionReadError(
            "local-player action changed during every stable-read attempt"
        )

    def observe_character(self, address: int) -> NativeTargetActionObservation:
        """Read a population-owned character address without consulting selection.

        The caller owns native-key validation before and after this detail read.
        This method itself checks stable action data and the local actor pointer.
        """
        if self._closed:
            raise NativeTargetActionReadError("native target-action reader is closed")
        for _ in range(self._stability_attempts):
            player = self._read_pointer(self._player_pointer_slot, "local player")
            first = self._read_snapshot(address, player)
            second = self._read_snapshot(address, player)
            if (first == second
                    and self._read_pointer(self._player_pointer_slot, "local player") == player):
                return self._observation(second)
        raise NativeTargetActionReadError(
            "bound character action changed during every stable-read attempt"
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
        self._require_object_pointer(selected, profile.target_of_target_pointer_offset + 4,
                                     "character")
        self._require_object_pointer(player, 4, "local player")
        vtable = self._read_pointer(selected, "character vtable")
        if vtable != self._character_vtable:
            raise NativeTargetActionReadError("character type is not calibrated")
        motion, motion_id = struct.unpack("<II", self._read_exact(
            selected + profile.current_motion_pointer_offset, 8, "motion"))
        self._require_object_pointer(motion, 4, "motion")
        motion_vtable = self._read_pointer(motion, "motion vtable")
        if motion_vtable != self._motion_vtable or motion_id > profile.maximum_motion_id:
            raise NativeTargetActionReadError("motion is outside calibrated bounds")
        frame = struct.unpack("<i", self._read_exact(
            selected + profile.animation_frame_offset, 4, "animation frame"))[0]
        if not (frame == profile.no_animation_frame_sentinel
                or 0 <= frame <= profile.maximum_animation_frame):
            raise NativeTargetActionReadError("animation frame is outside calibrated bounds")
        index = self._read_pointer(selected + profile.animation_event_index_offset,
                                   "animation event index")
        target = self._read_pointer(selected + profile.target_of_target_pointer_offset, "AF8")
        if target:
            self._require_object_pointer(target, 4, "AF8")
        state = self._read_pointer(selected + profile.actor_state_pointer_offset, "state")
        self._require_object_pointer(state, profile.state_action_offset + 4, "state")
        initiation = self._read_pointer(state + profile.state_initiation_offset, "initiation state")
        if not 1 <= initiation <= 7:
            raise NativeTargetActionReadError("unqualified native initiation state")
        mode = self._read_pointer(state + profile.state_mode_offset, "mode")
        action = self._read_pointer(state + profile.state_action_offset, "action state")
        slot = selected + profile.power_protocol_vector_offset
        header = struct.unpack("<III", self._read_exact(slot, 12, "power protocol header"))
        begin, end, capacity = header
        if header == (0, 0, 0):
            ids = ()
        else:
            self._require_object_pointer(begin, 0, "protocol begin")
            if (not begin <= end <= capacity or (end - begin) % 4 or (capacity - begin) % 4
                    or capacity - begin > profile.maximum_power_protocol_ids * 4):
                raise NativeTargetActionReadError("invalid power protocol bounds")
            self._require_object_pointer(begin, capacity - begin, "protocol capacity")
            data = b"".join(self._read_exact(begin + offset, min(64, end - begin - offset),
                                           "power protocol IDs")
                            for offset in range(0, end - begin, 64))
            ids = struct.unpack(f"<{len(data) // 4}I", data)
            if any(value == 0 for value in ids):
                raise NativeTargetActionReadError("invalid zero power protocol ID")
        if header != struct.unpack("<III", self._read_exact(slot, 12, "power protocol header")):
            raise NativeTargetActionReadError("power protocol storage changed during read")
        return _RawTargetActionSnapshot(selected, player, vtable, motion, motion_vtable,
            motion_id, frame, index, target, state, mode, action, initiation, header, ids)

    def _read_player_snapshot(self, player: int, selected: int) -> _RawTargetActionSnapshot:
        return replace(self._read_snapshot(player, player), player=selected)

    def _observation(self, snapshot: _RawTargetActionSnapshot) -> NativeTargetActionObservation:
        return NativeTargetActionObservation(
            target_present=True, target_token=self._target_token(snapshot.selected),
            targeting_player=snapshot.target_of_target == snapshot.player,
            motion_id=snapshot.motion_id, animation_event_index=snapshot.animation_event_index,
            animation_frame=(None
                if snapshot.animation_frame == self._profile.no_animation_frame_sentinel
                else snapshot.animation_frame),
            mode=snapshot.mode, action_state=snapshot.action_state,
            initiation_state=snapshot.initiation_state,
            power_protocol_ids=snapshot.power_protocol_ids)

    def _player_observation(
        self, snapshot: _RawTargetActionSnapshot,
    ) -> NativePlayerActionObservation:
        return NativePlayerActionObservation(
            targeting_selected=bool(
                snapshot.player and snapshot.target_of_target == snapshot.player),
            motion_id=snapshot.motion_id, animation_event_index=snapshot.animation_event_index,
            animation_frame=(None
                if snapshot.animation_frame == self._profile.no_animation_frame_sentinel
                else snapshot.animation_frame),
            mode=snapshot.mode, action_state=snapshot.action_state,
            initiation_state=snapshot.initiation_state,
            power_protocol_ids=snapshot.power_protocol_ids,
            selected_target_token=self._target_token(snapshot.player) if snapshot.player else None,
            action_target_token=self._target_token(snapshot.target_of_target)
            if snapshot.target_of_target else None)

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
        values = {
            key: (
                _string(data, key)
                if key in strings
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
