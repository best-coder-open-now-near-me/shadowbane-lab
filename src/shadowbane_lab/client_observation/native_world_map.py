"""Build-guarded, read-only access to the native world-map projection."""

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
    WindowsReadOnlyProcessMemory,
)
from shadowbane_lab.client_observation.native_message_hud import (
    ScanningReadOnlyProcessMemory,
)

NATIVE_WORLD_MAP_PROFILE_SCHEMA_VERSION = 1
_BUNDLED_PROFILE_NAME = "wonderbane-ef43784b.native-world-map.json"


class NativeWorldMapError(RuntimeError):
    """Base error for guarded native world-map observation."""


class NativeWorldMapCompatibilityError(NativeWorldMapError):
    """Raised when the running executable does not match its calibrated build."""


class NativeWorldMapReadError(NativeWorldMapError):
    """Raised when the world-map HUD cannot be located or read stably."""


class NativeWorldMapProfileLoadError(ValueError):
    """Raised when a native world-map profile is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class NativeWorldMapProfile:
    """Exact build identity and ArcWorldMapHud fields for one client build."""

    profile_id: str
    executable_name: str
    executable_sha256: str
    pointer_size: int
    object_vtable_rva: int
    control_vtable_rva: int
    world_definition_pointer_rva: int
    rectangle_offset: int
    hidden_offset: int
    left_padding_offset: int
    top_padding_offset: int
    right_padding_offset: int
    bottom_padding_offset: int
    zoom_offset: int
    map_texture_pointer_offset: int
    horizontal_pan_offset: int
    vertical_pan_offset: int
    world_length_tiles_offset: int
    world_width_tiles_offset: int
    world_coordinate_scale: float
    minimum_user_address: int
    maximum_user_address: int
    maximum_scan_address: int
    scan_memory_type: int
    scan_protection: int
    maximum_candidates: int
    minimum_map_pixels: int
    maximum_map_pixels: int
    minimum_zoom: float
    maximum_zoom: float
    maximum_world_tiles: int
    schema_version: int = NATIVE_WORLD_MAP_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.profile_id, "profile_id"),
            (self.executable_name, "executable_name"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        digest = self.executable_sha256.casefold()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("executable_sha256 must be a 64-character hexadecimal digest")
        if self.pointer_size != 4:
            raise ValueError("only the verified 32-bit Shadowbane client is supported")
        positive_integers = (
            "object_vtable_rva",
            "control_vtable_rva",
            "world_definition_pointer_rva",
            "rectangle_offset",
            "hidden_offset",
            "left_padding_offset",
            "top_padding_offset",
            "right_padding_offset",
            "bottom_padding_offset",
            "zoom_offset",
            "map_texture_pointer_offset",
            "horizontal_pan_offset",
            "vertical_pan_offset",
            "world_length_tiles_offset",
            "world_width_tiles_offset",
            "minimum_user_address",
            "maximum_user_address",
            "maximum_scan_address",
            "scan_memory_type",
            "scan_protection",
            "maximum_candidates",
            "minimum_map_pixels",
            "maximum_map_pixels",
            "maximum_world_tiles",
        )
        for field_name in positive_integers:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.rectangle_offset != self.pointer_size * 2:
            raise ValueError("only the verified ArcWorldMapHud rectangle layout is supported")
        ordered_offsets = (
            self.left_padding_offset,
            self.top_padding_offset,
            self.right_padding_offset,
            self.bottom_padding_offset,
            self.zoom_offset,
            self.map_texture_pointer_offset,
            self.horizontal_pan_offset,
            self.vertical_pan_offset,
        )
        if tuple(sorted(ordered_offsets)) != ordered_offsets:
            raise ValueError("world-map member offsets must be strictly increasing")
        if self.minimum_user_address < 0x10000:
            raise ValueError("minimum_user_address must exclude the null-allocation region")
        if not (
            self.minimum_user_address
            < self.maximum_scan_address
            <= self.maximum_user_address
            <= 0xFFFFFFFF
        ):
            raise ValueError("native world-map address bounds are invalid")
        if self.maximum_candidates > 64:
            raise ValueError("maximum_candidates must remain tightly bounded")
        if self.minimum_map_pixels >= self.maximum_map_pixels:
            raise ValueError("map pixel bounds must be increasing")
        for value, field_name in (
            (self.world_coordinate_scale, "world_coordinate_scale"),
            (self.minimum_zoom, "minimum_zoom"),
            (self.maximum_zoom, "maximum_zoom"),
        ):
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be finite and positive")
        if self.minimum_zoom >= self.maximum_zoom:
            raise ValueError("zoom bounds must be increasing")
        if self.schema_version != NATIVE_WORLD_MAP_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported native world-map profile version")


@dataclass(frozen=True, slots=True)
class NativeWorldMapPoint:
    """One world destination resolved from an accepted world-map pixel."""

    lt: float
    lg: float

    def __post_init__(self) -> None:
        if not isfinite(self.lt) or not isfinite(self.lg):
            raise ValueError("world-map coordinates must be finite")


@dataclass(frozen=True, slots=True)
class NativeWorldMapObservation:
    """Stable projection state for the active ArcWorldMapHud instance."""

    is_open: bool
    left: int
    top: int
    right: int
    bottom: int
    left_padding: int
    top_padding: int
    right_padding: int
    bottom_padding: int
    zoom: float
    horizontal_pan: int
    vertical_pan: int
    world_length: float
    world_width: float
    snapshot_token: str

    def __post_init__(self) -> None:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("world-map rectangle must have positive area")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (
                self.left_padding,
                self.top_padding,
                self.right_padding,
                self.bottom_padding,
            )
        ):
            raise ValueError("world-map paddings must be non-negative integers")
        if not isfinite(self.zoom) or self.zoom <= 0:
            raise ValueError("world-map zoom must be finite and positive")
        if any(
            not isfinite(value) or value <= 0 for value in (self.world_length, self.world_width)
        ):
            raise ValueError("world-map dimensions must be finite and positive")
        if not isinstance(self.snapshot_token, str) or not self.snapshot_token:
            raise ValueError("snapshot_token must be non-empty")
        if self.content_width <= 0 or self.content_height <= 0:
            raise ValueError("world-map content rectangle must have positive area")

    @property
    def content_width(self) -> int:
        return self.right - self.left - self.left_padding - self.right_padding

    @property
    def content_height(self) -> int:
        return self.bottom - self.top - self.top_padding - self.bottom_padding

    def resolve_screen_point(self, screen_x: int, screen_y: int) -> NativeWorldMapPoint:
        """Apply the client's inverse world-map transform to one screen pixel."""

        for value, field_name in ((screen_x, "screen_x"), (screen_y, "screen_y")):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        if not self.is_open:
            raise NativeWorldMapReadError("world map is not open")
        if not (self.left <= screen_x < self.right and self.top <= screen_y < self.bottom):
            raise NativeWorldMapReadError("pointer is outside the world map")

        local_x = screen_x - self.left
        local_y = screen_y - self.top
        projected_x = (
            (local_x + self.horizontal_pan) / self.zoom - self.left_padding
        ) / self.content_width
        projected_y = (
            (local_y + self.vertical_pan) / self.zoom - self.top_padding
        ) / self.content_height
        lt = projected_x * self.world_length
        lg = (1.0 - projected_y) * self.world_width
        tolerance = max(self.world_length, self.world_width) * 1e-6
        if not (
            -tolerance <= lt <= self.world_length + tolerance
            and -tolerance <= lg <= self.world_width + tolerance
        ):
            raise NativeWorldMapReadError("pointer is outside the projected world")
        return NativeWorldMapPoint(
            lt=min(self.world_length, max(0.0, lt)),
            lg=min(self.world_width, max(0.0, lg)),
        )


class NativeWorldMapReader:
    """Discovers and reads the unique native world-map HUD without mutation."""

    def __init__(
        self,
        profile: NativeWorldMapProfile,
        process: ScanningReadOnlyProcessMemory,
        *,
        stability_attempts: int = 3,
    ) -> None:
        if not isinstance(profile, NativeWorldMapProfile):
            raise ValueError("profile must be NativeWorldMapProfile")
        if not isinstance(process, ScanningReadOnlyProcessMemory):
            raise ValueError("process must implement ScanningReadOnlyProcessMemory")
        if (
            isinstance(stability_attempts, bool)
            or not isinstance(stability_attempts, int)
            or stability_attempts <= 0
        ):
            raise ValueError("stability_attempts must be a positive integer")
        if process.executable_name.casefold() != profile.executable_name.casefold():
            raise NativeWorldMapCompatibilityError(
                f"expected {profile.executable_name}, found {process.executable_name}"
            )
        if not native_layout_is_compatible(
            profile.executable_sha256,
            process.executable_sha256,
        ):
            raise NativeWorldMapCompatibilityError(
                "running Shadowbane executable does not match the calibrated SHA-256"
            )
        if process.pointer_size != profile.pointer_size:
            raise NativeWorldMapCompatibilityError(
                "running Shadowbane pointer size does not match the calibrated build"
            )
        if process.base_address <= 0:
            raise NativeWorldMapCompatibilityError("process image base is invalid")
        self._profile = profile
        self._process = process
        self._stability_attempts = stability_attempts
        self._object_address: int | None = None
        self._closed = False

    @property
    def profile(self) -> NativeWorldMapProfile:
        return self._profile

    @property
    def process_id(self) -> int:
        return self._process.pid

    @property
    def attached(self) -> bool:
        return self._object_address is not None

    def attach(self) -> None:
        if self._closed:
            raise NativeWorldMapReadError("native world-map reader is closed")
        self._object_address = self._discover_object()

    def observe(self) -> NativeWorldMapObservation:
        if self._closed:
            raise NativeWorldMapReadError("native world-map reader is closed")
        if self._object_address is None:
            self.attach()
        assert self._object_address is not None
        last_error: NativeWorldMapReadError | None = None
        for _ in range(self._stability_attempts):
            try:
                first = self._read_snapshot(self._object_address)
                second = self._read_snapshot(self._object_address)
                if first == second:
                    return self._observation(self._object_address, first)
            except NativeWorldMapReadError as exc:
                last_error = exc
                break
        if last_error is not None:
            self._object_address = None
            raise last_error
        raise NativeWorldMapReadError(
            "world-map projection changed during every stable-read attempt"
        )

    def resolve_screen_point(self, screen_x: int, screen_y: int) -> NativeWorldMapPoint:
        return self.observe().resolve_screen_point(screen_x, screen_y)

    def close(self) -> None:
        if not self._closed:
            self._process.close()
            self._closed = True

    def __enter__(self) -> NativeWorldMapReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _discover_object(self) -> int:
        profile = self._profile
        expected_vtable = self._process.base_address + profile.object_vtable_rva
        needle = struct.pack("<I", expected_vtable)
        try:
            hits = self._process.find_all(
                (needle,),
                memory_type=profile.scan_memory_type,
                protection=profile.scan_protection,
                maximum_results_per_needle=profile.maximum_candidates,
                maximum_address=profile.maximum_scan_address,
            )[needle]
        except Exception as exc:
            raise NativeWorldMapReadError(
                f"native world-map scan failed: {type(exc).__name__}"
            ) from exc
        candidates: list[tuple[int, NativeWorldMapObservation]] = []
        rejected: list[str] = []
        for address in hits:
            if address % profile.pointer_size:
                continue
            try:
                observation = self._observation(address, self._read_snapshot(address))
            except NativeWorldMapReadError as exc:
                if len(rejected) < 3:
                    rejected.append(f"{address:#x}: {exc}")
                continue
            candidates.append((address, observation))
        unique = tuple(
            sorted(
                {address: observation for address, observation in candidates}.items()
            )
        )
        if len(unique) == 1:
            return unique[0][0]
        active = tuple(address for address, observation in unique if observation.is_open)
        if len(active) == 1:
            return active[0]
        if len(unique) != 1:
            detail = "" if not rejected else f"; samples: {'; '.join(rejected)}"
            raise NativeWorldMapReadError(
                "native world-map owner resolution was ambiguous: "
                f"found {len(unique)} validated objects from {len(hits)} vtable matches"
                f" ({len(active)} active)"
                f"{detail}"
            )
        raise AssertionError("unreachable world-map owner resolution state")

    def _read_snapshot(self, address: int) -> bytes:
        profile = self._profile
        size = profile.vertical_pan_offset + 4
        if address < profile.minimum_user_address or address + size > profile.maximum_user_address:
            raise NativeWorldMapReadError(
                "world-map object lies outside the calibrated 32-bit user range"
            )
        try:
            payload = self._process.read_block(address, size)
        except Exception as exc:
            raise NativeWorldMapReadError(
                f"could not read world-map object: {type(exc).__name__}"
            ) from exc
        if len(payload) != size:
            raise NativeWorldMapReadError(
                "native process backend returned a partial world-map object"
            )
        return payload

    def _observation(self, address: int, payload: bytes) -> NativeWorldMapObservation:
        profile = self._profile
        object_vtable, control_vtable = struct.unpack_from("<II", payload)
        if object_vtable != self._process.base_address + profile.object_vtable_rva:
            raise NativeWorldMapReadError("world-map object vtable changed")
        if control_vtable != self._process.base_address + profile.control_vtable_rva:
            raise NativeWorldMapReadError("world-map control vtable is unsupported")
        left, top, right, bottom = struct.unpack_from("<iiii", payload, profile.rectangle_offset)
        width = right - left
        height = bottom - top
        if not (
            profile.minimum_map_pixels <= width <= profile.maximum_map_pixels
            and profile.minimum_map_pixels <= height <= profile.maximum_map_pixels
        ):
            raise NativeWorldMapReadError("world-map rectangle is outside calibrated bounds")
        hidden = payload[profile.hidden_offset]
        if hidden not in (0, 1):
            raise NativeWorldMapReadError("world-map hidden flag is invalid")
        paddings = tuple(
            struct.unpack_from("<i", payload, offset)[0]
            for offset in (
                profile.left_padding_offset,
                profile.top_padding_offset,
                profile.right_padding_offset,
                profile.bottom_padding_offset,
            )
        )
        if any(value < 0 for value in paddings):
            raise NativeWorldMapReadError("world-map padding is negative")
        if paddings[0] + paddings[2] >= width or paddings[1] + paddings[3] >= height:
            raise NativeWorldMapReadError("world-map padding consumes its content area")
        zoom = struct.unpack_from("<f", payload, profile.zoom_offset)[0]
        if not isfinite(zoom) or not profile.minimum_zoom <= zoom <= profile.maximum_zoom:
            raise NativeWorldMapReadError("world-map zoom is outside calibrated bounds")
        texture_pointer = struct.unpack_from("<I", payload, profile.map_texture_pointer_offset)[0]
        if texture_pointer and (
            texture_pointer < profile.minimum_user_address
            or texture_pointer > profile.maximum_user_address
            or texture_pointer % profile.pointer_size
        ):
            raise NativeWorldMapReadError("world-map texture pointer is invalid")
        horizontal_pan = struct.unpack_from("<i", payload, profile.horizontal_pan_offset)[0]
        vertical_pan = struct.unpack_from("<i", payload, profile.vertical_pan_offset)[0]
        maximum_pan = profile.maximum_map_pixels * int(profile.maximum_zoom) * 4
        if abs(horizontal_pan) > maximum_pan or abs(vertical_pan) > maximum_pan:
            raise NativeWorldMapReadError("world-map pan is outside calibrated bounds")
        world_length, world_width, world_definition = self._read_world_dimensions()
        digest = hashlib.blake2s(digest_size=12)
        digest.update(profile.executable_sha256.encode("ascii"))
        digest.update(struct.pack("<III", self._process.pid, address, world_definition))
        digest.update(payload)
        return NativeWorldMapObservation(
            is_open=hidden == 0 and texture_pointer != 0,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            left_padding=paddings[0],
            top_padding=paddings[1],
            right_padding=paddings[2],
            bottom_padding=paddings[3],
            zoom=zoom,
            horizontal_pan=horizontal_pan,
            vertical_pan=vertical_pan,
            world_length=world_length,
            world_width=world_width,
            snapshot_token=digest.hexdigest(),
        )

    def _read_world_dimensions(self) -> tuple[float, float, int]:
        profile = self._profile
        slot = self._process.base_address + profile.world_definition_pointer_rva
        try:
            pointer_bytes = self._process.read(slot, profile.pointer_size)
            if len(pointer_bytes) != profile.pointer_size:
                raise NativeWorldMapReadError(
                    "native process backend returned a partial world-definition pointer"
                )
            pointer = struct.unpack("<I", pointer_bytes)[0]
            final_offset = max(
                profile.world_length_tiles_offset,
                profile.world_width_tiles_offset,
            )
            if (
                pointer < profile.minimum_user_address
                or pointer + final_offset + 4 > profile.maximum_user_address
                or pointer % profile.pointer_size
            ):
                raise NativeWorldMapReadError("world-definition pointer is invalid")
            first = self._process.read_block(pointer, final_offset + 4)
            second = self._process.read_block(pointer, final_offset + 4)
        except NativeWorldMapReadError:
            raise
        except Exception as exc:
            raise NativeWorldMapReadError(
                f"could not read world dimensions: {type(exc).__name__}"
            ) from exc
        if first != second:
            raise NativeWorldMapReadError("world dimensions changed during the read")
        length_tiles = struct.unpack_from("<i", first, profile.world_length_tiles_offset)[0]
        width_tiles = struct.unpack_from("<i", first, profile.world_width_tiles_offset)[0]
        if not (
            0 < length_tiles <= profile.maximum_world_tiles
            and 0 < width_tiles <= profile.maximum_world_tiles
        ):
            raise NativeWorldMapReadError("world dimensions are outside calibrated bounds")
        return (
            length_tiles * profile.world_coordinate_scale,
            width_tiles * profile.world_coordinate_scale,
            pointer,
        )


def open_windows_native_world_map_reader(
    profile: NativeWorldMapProfile,
    *,
    process_id: int | None = None,
) -> NativeWorldMapReader:
    process = (
        WindowsReadOnlyProcessMemory.open_unique(profile.executable_name)
        if process_id is None
        else WindowsReadOnlyProcessMemory.open_for_process(
            profile.executable_name,
            process_id,
        )
    )
    try:
        return NativeWorldMapReader(profile, process)
    except Exception:
        process.close()
        raise


def load_bundled_native_world_map_profile() -> NativeWorldMapProfile:
    resource = files("shadowbane_lab.client_observation").joinpath("data", _BUNDLED_PROFILE_NAME)
    return load_native_world_map_profile_text(resource.read_text(encoding="utf-8"))


def load_native_world_map_profile(path: str | Path) -> NativeWorldMapProfile:
    return load_native_world_map_profile_text(Path(path).read_text(encoding="utf-8"))


def load_native_world_map_profile_text(text: str) -> NativeWorldMapProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeWorldMapProfileLoadError("native world-map profile is not valid JSON") from exc
    if not isinstance(raw, Mapping):
        raise NativeWorldMapProfileLoadError("native world-map profile must be an object")
    expected = set(NativeWorldMapProfile.__dataclass_fields__)
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise NativeWorldMapProfileLoadError(
            f"native world-map profile has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise NativeWorldMapProfileLoadError(
            f"native world-map profile is missing fields: {', '.join(sorted(missing))}"
        )
    try:
        return NativeWorldMapProfile(**cast(dict[str, Any], dict(raw)))
    except (TypeError, ValueError) as exc:
        raise NativeWorldMapProfileLoadError(str(exc)) from exc
