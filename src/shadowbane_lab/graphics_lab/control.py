"""Versioned shared-memory client for live WonderBane graphics parameters."""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import struct
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

CONTROL_MAGIC = 0x43474257
CONTROL_SCHEMA_VERSION = 2
CONTROL_STRUCTURE_SIZE = 256
CONTROL_HEADER = struct.Struct("<6I4iI25f2I26I")
CONTROL_PARAMETER_OFFSET = 40
CONTROL_PARAMETER_END = 152
CONTROL_DESIRED_SEQUENCE_OFFSET = 24

BANDED_LIGHTING = 1 << 0
DEPTH_CONTOURS = 1 << 1
FEATURE_ACCENTS = 1 << 2
ADAPTIVE_OUTLINES = 1 << 3
KNOWN_FLAGS = BANDED_LIGHTING | DEPTH_CONTOURS | FEATURE_ACCENTS | ADAPTIVE_OUTLINES

DEPTH_CONTOUR_LEGACY = 0
DEPTH_CONTOUR_SUSTAINED = 1
KNOWN_DEPTH_CONTOUR_MODES = {DEPTH_CONTOUR_LEGACY, DEPTH_CONTOUR_SUSTAINED}

DEPTH_CONTOUR_DEBUG_NONE = 0
DEPTH_CONTOUR_DEBUG_RESPONSE = 1
DEPTH_CONTOUR_DEBUG_SUSTAINED_RESPONSE = 2
DEPTH_CONTOUR_DEBUG_SUPPORT = 3
DEPTH_CONTOUR_DEBUG_REJECTED = 4
KNOWN_DEPTH_CONTOUR_DEBUG_MODES = {
    DEPTH_CONTOUR_DEBUG_NONE,
    DEPTH_CONTOUR_DEBUG_RESPONSE,
    DEPTH_CONTOUR_DEBUG_SUSTAINED_RESPONSE,
    DEPTH_CONTOUR_DEBUG_SUPPORT,
    DEPTH_CONTOUR_DEBUG_REJECTED,
}

DEFAULT_SUSTAINED_EDGE_THRESHOLD = 0.055


@dataclass(frozen=True)
class GraphicsParameters:
    flags: int
    dark_scene_outline: tuple[float, float, float]
    dark_scene_outline_strength: float
    bright_scene_ink_alpha: float
    depth_edge_threshold: float
    band_thresholds: tuple[float, float, float]
    band_colors: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    vertex_tint_gamma: float
    distant_highlight_compression: float
    feature_outline_width: float
    sustained_edge_threshold: float
    depth_contour_mode: int
    depth_contour_debug_mode: int

    def validate(self) -> None:
        if self.flags < 0 or self.flags & ~KNOWN_FLAGS:
            raise ValueError("graphics flags contain an unknown bit")
        _validate_color(self.dark_scene_outline, "dark_scene_outline")
        _validate_range(
            self.dark_scene_outline_strength,
            0.0,
            1.0,
            "dark_scene_outline_strength",
        )
        _validate_range(
            self.bright_scene_ink_alpha, 0.0, 1.0, "bright_scene_ink_alpha"
        )
        _validate_range(self.depth_edge_threshold, 0.005, 0.5, "depth_edge_threshold")
        if (
            len(self.band_thresholds) != 3
            or not 0.0
            < self.band_thresholds[0]
            < self.band_thresholds[1]
            < self.band_thresholds[2]
            < 1.0
        ):
            raise ValueError("band_thresholds must be three strictly increasing values")
        if len(self.band_colors) != 4:
            raise ValueError("band_colors must contain exactly four colors")
        for index, color in enumerate(self.band_colors):
            _validate_color(color, f"band_colors[{index}]")
        _validate_range(self.vertex_tint_gamma, 0.25, 2.5, "vertex_tint_gamma")
        _validate_range(
            self.distant_highlight_compression,
            0.0,
            1.0,
            "distant_highlight_compression",
        )
        _validate_range(self.feature_outline_width, 0.5, 3.0, "feature_outline_width")
        _validate_range(
            self.sustained_edge_threshold,
            0.005,
            0.5,
            "sustained_edge_threshold",
        )
        if self.depth_contour_mode not in KNOWN_DEPTH_CONTOUR_MODES:
            raise ValueError("depth_contour_mode is unsupported")
        if self.depth_contour_debug_mode not in KNOWN_DEPTH_CONTOUR_DEBUG_MODES:
            raise ValueError("depth_contour_debug_mode is unsupported")

    def to_json(self) -> dict[str, object]:
        self.validate()
        return {
            "flags": self.flags,
            "dark_scene_outline": list(self.dark_scene_outline),
            "dark_scene_outline_strength": self.dark_scene_outline_strength,
            "bright_scene_ink_alpha": self.bright_scene_ink_alpha,
            "depth_edge_threshold": self.depth_edge_threshold,
            "band_thresholds": list(self.band_thresholds),
            "band_colors": [list(color) for color in self.band_colors],
            "vertex_tint_gamma": self.vertex_tint_gamma,
            "distant_highlight_compression": self.distant_highlight_compression,
            "feature_outline_width": self.feature_outline_width,
            "sustained_edge_threshold": self.sustained_edge_threshold,
            "depth_contour_mode": self.depth_contour_mode,
            "depth_contour_debug_mode": self.depth_contour_debug_mode,
        }

    @classmethod
    def from_json(
        cls,
        value: object,
        *,
        allow_legacy_contour_defaults: bool = False,
    ) -> GraphicsParameters:
        if not isinstance(value, dict):
            raise ValueError("graphics parameters must be an object")
        try:
            parameters = cls(
                flags=_integer(value, "flags"),
                dark_scene_outline=_triple(value, "dark_scene_outline"),
                dark_scene_outline_strength=_number(
                    value, "dark_scene_outline_strength"
                ),
                bright_scene_ink_alpha=_number(value, "bright_scene_ink_alpha"),
                depth_edge_threshold=_number(value, "depth_edge_threshold"),
                band_thresholds=_triple(value, "band_thresholds"),
                band_colors=_four_colors(value, "band_colors"),
                vertex_tint_gamma=_number(value, "vertex_tint_gamma"),
                distant_highlight_compression=_number(
                    value, "distant_highlight_compression"
                ),
                feature_outline_width=_number(value, "feature_outline_width"),
                sustained_edge_threshold=(
                    _optional_number(
                        value,
                        "sustained_edge_threshold",
                        DEFAULT_SUSTAINED_EDGE_THRESHOLD,
                    )
                    if allow_legacy_contour_defaults
                    else _number(value, "sustained_edge_threshold")
                ),
                depth_contour_mode=(
                    _optional_integer(
                        value, "depth_contour_mode", DEPTH_CONTOUR_LEGACY
                    )
                    if allow_legacy_contour_defaults
                    else _integer(value, "depth_contour_mode")
                ),
                depth_contour_debug_mode=(
                    _optional_integer(
                        value,
                        "depth_contour_debug_mode",
                        DEPTH_CONTOUR_DEBUG_NONE,
                    )
                    if allow_legacy_contour_defaults
                    else _integer(value, "depth_contour_debug_mode")
                ),
            )
        except KeyError as error:
            raise ValueError(f"missing graphics parameter {error.args[0]!r}") from error
        parameters.validate()
        return parameters


DEFAULT_PARAMETERS = GraphicsParameters(
    flags=BANDED_LIGHTING | DEPTH_CONTOURS | FEATURE_ACCENTS | ADAPTIVE_OUTLINES,
    dark_scene_outline=(0.52, 0.56, 0.70),
    dark_scene_outline_strength=0.28,
    bright_scene_ink_alpha=0.86,
    depth_edge_threshold=0.055,
    band_thresholds=(0.22, 0.43, 0.66),
    band_colors=(
        (0.23, 0.24, 0.26),
        (0.54, 0.58, 0.65),
        (0.78, 0.81, 0.84),
        (1.00, 0.99, 0.95),
    ),
    vertex_tint_gamma=0.78,
    distant_highlight_compression=0.45,
    feature_outline_width=1.35,
    sustained_edge_threshold=DEFAULT_SUSTAINED_EDGE_THRESHOLD,
    depth_contour_mode=DEPTH_CONTOUR_LEGACY,
    depth_contour_debug_mode=DEPTH_CONTOUR_DEBUG_NONE,
)


def normalize_fixed_accent_controls(parameters: GraphicsParameters) -> GraphicsParameters:
    """Represent the existing renderer's effective accent state without a fake width knob.

    Legacy widths below one suppress accents; every other accepted width draws
    one pixel. Keep that appearance when a legacy preset enters the panel. This
    does not rewrite preset files or publish a live update by itself.
    """
    parameters.validate()
    flags = parameters.flags
    if parameters.feature_outline_width < 1.0:
        flags &= ~FEATURE_ACCENTS
    return replace(parameters, flags=flags, feature_outline_width=1.0)


@dataclass(frozen=True)
class GraphicsControlTarget:
    process_id: int
    process_creation_filetime_utc: int
    executable_path: Path
    executable_sha256: str
    mapping_name: str
    status_path: Path

    @property
    def label(self) -> str:
        return f"sb.exe · PID {self.process_id}"


@dataclass(frozen=True)
class GraphicsControlSnapshot:
    parameters: GraphicsParameters
    desired_sequence: int
    applied_sequence: int
    rejected_sequence: int
    last_error: int


def _validate_range(value: float, minimum: float, maximum: float, name: str) -> None:
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")


def _clamp_transport_range(
    value: float,
    minimum: float,
    maximum: float,
    name: str,
) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    tolerance = max(1e-7, max(abs(minimum), abs(maximum)) * 1e-7)
    if value < minimum:
        if value >= minimum - tolerance:
            return minimum
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    if value > maximum:
        if value <= maximum + tolerance:
            return maximum
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def _validate_color(color: tuple[float, float, float], name: str) -> None:
    if len(color) != 3:
        raise ValueError(f"{name} must have exactly three channels")
    for channel in color:
        _validate_range(channel, 0.0, 1.5, name)


def _number(value: dict[str, object], key: str) -> float:
    item = value[key]
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(item)


def _integer(value: dict[str, object], key: str) -> int:
    item = value[key]
    if isinstance(item, bool) or not isinstance(item, int):
        raise ValueError(f"{key} must be an integer")
    return item


def _optional_number(
    value: dict[str, object], key: str, default: float
) -> float:
    if key not in value:
        return default
    return _number(value, key)


def _optional_integer(
    value: dict[str, object], key: str, default: int
) -> int:
    if key not in value:
        return default
    return _integer(value, key)


def _triple(value: dict[str, object], key: str) -> tuple[float, float, float]:
    item = value[key]
    if not isinstance(item, list) or len(item) != 3:
        raise ValueError(f"{key} must contain exactly three numbers")
    result = []
    for channel in item:
        if isinstance(channel, bool) or not isinstance(channel, (int, float)):
            raise ValueError(f"{key} must contain only numbers")
        result.append(float(channel))
    return result[0], result[1], result[2]


def _four_colors(
    value: dict[str, object], key: str
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    item = value[key]
    if not isinstance(item, list) or len(item) != 4:
        raise ValueError(f"{key} must contain exactly four colors")
    colors = []
    for index, color in enumerate(item):
        colors.append(_triple({"color": color}, "color"))
        _validate_color(colors[-1], f"{key}[{index}]")
    return colors[0], colors[1], colors[2], colors[3]


def _parameter_floats(parameters: GraphicsParameters) -> tuple[float, ...]:
    return (
        *parameters.dark_scene_outline,
        parameters.dark_scene_outline_strength,
        parameters.bright_scene_ink_alpha,
        parameters.depth_edge_threshold,
        *parameters.band_thresholds,
        *(channel for color in parameters.band_colors for channel in color),
        parameters.vertex_tint_gamma,
        parameters.distant_highlight_compression,
        parameters.feature_outline_width,
        parameters.sustained_edge_threshold,
    )


def pack_control_block(
    target: GraphicsControlTarget,
    parameters: GraphicsParameters,
    *,
    desired_sequence: int = 2,
    applied_sequence: int = 2,
    rejected_sequence: int = 0,
    last_error: int = 0,
) -> bytes:
    parameters.validate()
    if desired_sequence <= 0 or desired_sequence & 1:
        raise ValueError("desired_sequence must be a positive even integer")
    creation = target.process_creation_filetime_utc
    return CONTROL_HEADER.pack(
        CONTROL_MAGIC,
        CONTROL_SCHEMA_VERSION,
        CONTROL_STRUCTURE_SIZE,
        target.process_id,
        creation & 0xFFFFFFFF,
        creation >> 32,
        desired_sequence,
        applied_sequence,
        rejected_sequence,
        last_error,
        parameters.flags,
        *_parameter_floats(parameters),
        parameters.depth_contour_mode,
        parameters.depth_contour_debug_mode,
        *([0] * 26),
    )


def unpack_control_block(data: bytes, target: GraphicsControlTarget) -> GraphicsControlSnapshot:
    values = _unpack_control_values(data, target)
    desired, applied, rejected, last_error = values[6:10]
    flags = values[10]
    floats = values[11:36]
    parameters = GraphicsParameters(
        flags=flags,
        dark_scene_outline=(floats[0], floats[1], floats[2]),
        dark_scene_outline_strength=floats[3],
        bright_scene_ink_alpha=floats[4],
        depth_edge_threshold=_clamp_transport_range(
            floats[5],
            0.005,
            0.5,
            "depth_edge_threshold",
        ),
        band_thresholds=(floats[6], floats[7], floats[8]),
        band_colors=(
            (floats[9], floats[10], floats[11]),
            (floats[12], floats[13], floats[14]),
            (floats[15], floats[16], floats[17]),
            (floats[18], floats[19], floats[20]),
        ),
        vertex_tint_gamma=floats[21],
        distant_highlight_compression=floats[22],
        feature_outline_width=floats[23],
        sustained_edge_threshold=_clamp_transport_range(
            floats[24],
            0.005,
            0.5,
            "sustained_edge_threshold",
        ),
        depth_contour_mode=int(values[36]),
        depth_contour_debug_mode=int(values[37]),
    )
    parameters.validate()
    return GraphicsControlSnapshot(
        parameters=parameters,
        desired_sequence=desired,
        applied_sequence=applied,
        rejected_sequence=rejected,
        last_error=last_error & 0xFFFFFFFF,
    )


def _unpack_control_values(
    data: bytes, target: GraphicsControlTarget
) -> tuple[int | float, ...]:
    if len(data) != CONTROL_STRUCTURE_SIZE:
        raise ValueError("graphics control block has the wrong size")
    values = CONTROL_HEADER.unpack(data)
    magic, schema, size, process_id, creation_low, creation_high = values[:6]
    if magic != CONTROL_MAGIC or schema != CONTROL_SCHEMA_VERSION or size != 256:
        raise ValueError("graphics control block has an unsupported ABI")
    creation = creation_low | (creation_high << 32)
    if process_id != target.process_id or creation != target.process_creation_filetime_utc:
        raise ValueError("graphics control block belongs to a different client")
    return values


def _status_root(local_app_data: Path | None) -> Path:
    if local_app_data is not None:
        return local_app_data / "ShadowbaneLab" / "client-extension"
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise RuntimeError("LOCALAPPDATA is not available")
    return Path(value) / "ShadowbaneLab" / "client-extension"


def discover_graphics_targets(
    local_app_data: Path | None = None,
    *,
    identity_validator: Callable[[GraphicsControlTarget], bool] | None = None,
) -> tuple[GraphicsControlTarget, ...]:
    validator = verify_target_identity if identity_validator is None else identity_validator
    targets: list[GraphicsControlTarget] = []
    root = _status_root(local_app_data)
    if not root.is_dir():
        return ()
    for path in sorted(root.glob("graphics-status-*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("producer_id") != "wonderbane-extension.graphics":
                continue
            identity = payload["process_identity"]
            controls = payload["live_controls"]
            if not isinstance(identity, dict) or not isinstance(controls, dict):
                continue
            mapping_name = controls.get("mapping_name")
            executable_sha256 = payload.get("executable_sha256")
            if (
                controls.get("available") is not True
                or controls.get("schema_version") != CONTROL_SCHEMA_VERSION
                or not isinstance(mapping_name, str)
            ):
                continue
            if (
                not isinstance(executable_sha256, str)
                or len(executable_sha256) != 64
                or any(character not in "0123456789abcdef" for character in executable_sha256)
            ):
                continue
            target = GraphicsControlTarget(
                process_id=int(identity["process_id"]),
                process_creation_filetime_utc=int(
                    identity["process_creation_filetime_utc"]
                ),
                executable_path=Path(str(identity["executable_path"])),
                executable_sha256=executable_sha256,
                mapping_name=mapping_name,
                status_path=path,
            )
            if validator(target):
                targets.append(target)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    unique: dict[tuple[int, int], GraphicsControlTarget] = {}
    for target in targets:
        unique[(target.process_id, target.process_creation_filetime_utc)] = target
    return tuple(unique.values())


if os.name == "nt":
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    ]
    _kernel32.GetProcessTimes.restype = wintypes.BOOL
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.OpenFileMappingW.restype = wintypes.HANDLE
    _kernel32.MapViewOfFile.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    _kernel32.MapViewOfFile.restype = ctypes.c_void_p
    _kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _kernel32.UnmapViewOfFile.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _kernel32.ReleaseMutex.restype = wintypes.BOOL


def verify_target_identity(target: GraphicsControlTarget) -> bool:
    if not target_process_is_alive(target):
        return False
    digest = hashlib.sha256()
    try:
        with target.executable_path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        return False
    return digest.hexdigest() == target.executable_sha256


def target_process_is_alive(target: GraphicsControlTarget) -> bool:
    if os.name != "nt":
        return False
    process_query_limited_information = 0x1000
    handle = _kernel32.OpenProcess(
        process_query_limited_information, False, target.process_id
    )
    if not handle:
        return False
    try:
        creation = _FileTime()
        exit_time = _FileTime()
        kernel_time = _FileTime()
        user_time = _FileTime()
        if not _kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return False
        creation_value = creation.low | (creation.high << 32)
        if creation_value != target.process_creation_filetime_utc:
            return False
        capacity = wintypes.DWORD(32768)
        path_buffer = ctypes.create_unicode_buffer(capacity.value)
        if not _kernel32.QueryFullProcessImageNameW(
            handle, 0, path_buffer, ctypes.byref(capacity)
        ):
            return False
        if Path(path_buffer.value).resolve() != target.executable_path.resolve():
            return False
    finally:
        _kernel32.CloseHandle(handle)
    return True


class GraphicsControlClient:
    """Exact-process shared-memory writer with sequence acknowledgement."""

    def __init__(self, target: GraphicsControlTarget) -> None:
        if os.name != "nt":
            raise OSError("WonderBane graphics controls require Windows")
        self.target = target
        file_map_all_access = 0x000F001F
        self._mapping = _kernel32.OpenFileMappingW(
            file_map_all_access, False, target.mapping_name
        )
        if not self._mapping:
            raise OSError(ctypes.get_last_error(), "could not open graphics control mapping")
        self._address = _kernel32.MapViewOfFile(
            self._mapping, file_map_all_access, 0, 0, CONTROL_STRUCTURE_SIZE
        )
        if not self._address:
            error = ctypes.get_last_error()
            _kernel32.CloseHandle(self._mapping)
            self._mapping = None
            raise OSError(error, "could not map graphics control block")
        mutex_name = (
            f"Local\\WonderBaneGraphicsControlWriter-{target.process_id}-"
            f"{target.process_creation_filetime_utc}"
        )
        self._mutex = _kernel32.CreateMutexW(None, False, mutex_name)
        if not self._mutex:
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "could not create graphics control writer mutex")
        try:
            self._read_values()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        mutex = getattr(self, "_mutex", None)
        if mutex:
            _kernel32.CloseHandle(mutex)
            self._mutex = None
        address = getattr(self, "_address", None)
        if address:
            _kernel32.UnmapViewOfFile(address)
            self._address = None
        mapping = getattr(self, "_mapping", None)
        if mapping:
            _kernel32.CloseHandle(mapping)
            self._mapping = None

    def __enter__(self) -> GraphicsControlClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def read(self) -> GraphicsControlSnapshot:
        if not self._address:
            raise RuntimeError("graphics control client is closed")
        data = ctypes.string_at(self._address, CONTROL_STRUCTURE_SIZE)
        return unpack_control_block(data, self.target)

    def write(self, parameters: GraphicsParameters) -> int:
        return self._write_parameters(parameters, require_valid_current=True)

    def restore_reviewed_baseline(self) -> int:
        """Replace invalid live parameters without bypassing ABI or identity checks."""
        return self._write_parameters(
            DEFAULT_PARAMETERS,
            require_valid_current=False,
        )

    def _read_values(self) -> tuple[int | float, ...]:
        if not self._address:
            raise RuntimeError("graphics control client is closed")
        data = ctypes.string_at(self._address, CONTROL_STRUCTURE_SIZE)
        return _unpack_control_values(data, self.target)

    def _write_parameters(
        self,
        parameters: GraphicsParameters,
        *,
        require_valid_current: bool,
    ) -> int:
        parameters.validate()
        wait_object_0 = 0
        wait_abandoned = 0x80
        wait_result = _kernel32.WaitForSingleObject(self._mutex, 2000)
        if wait_result not in (wait_object_0, wait_abandoned):
            raise TimeoutError("another Graphics Lab writer held the client control lock")
        try:
            values = self._read_values()
            if require_valid_current:
                self.read()
            desired, applied, rejected, last_error = (
                int(value) for value in values[6:10]
            )
            next_sequence = max(
                desired,
                applied,
                rejected,
                0,
            ) + 2
            if next_sequence >= 0x7FFFFFFE:
                next_sequence = 2
            packed = pack_control_block(
                self.target,
                parameters,
                desired_sequence=next_sequence,
                applied_sequence=applied,
                rejected_sequence=rejected,
                last_error=last_error,
            )
            sequence = ctypes.c_int32.from_address(
                self._address + CONTROL_DESIRED_SEQUENCE_OFFSET
            )
            sequence.value = next_sequence - 1
            ctypes.memmove(
                self._address + CONTROL_PARAMETER_OFFSET,
                packed[CONTROL_PARAMETER_OFFSET:CONTROL_PARAMETER_END],
                CONTROL_PARAMETER_END - CONTROL_PARAMETER_OFFSET,
            )
            sequence.value = next_sequence
            return next_sequence
        finally:
            _kernel32.ReleaseMutex(self._mutex)


assert CONTROL_HEADER.size == CONTROL_STRUCTURE_SIZE
DEFAULT_PARAMETERS.validate()
