"""Strict JSON loading for client calibration profiles."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_input.model import (
    CLIENT_PROFILE_SCHEMA_VERSION,
    ActionInputMapping,
    CalibrationProfile,
    CameraDragMapping,
    ClickActivation,
    ClientTarget,
    DirectionalClickMapping,
    HotkeyActivation,
    KeyActivation,
    MouseButton,
    NormalizedPoint,
    TargetOrder,
)


class CalibrationLoadError(ValueError):
    """Raised when calibration data is malformed or unsupported."""


def load_calibration(path: str | Path) -> CalibrationProfile:
    return load_calibration_text(Path(path).read_text(encoding="utf-8"))


def load_calibration_text(text: str) -> CalibrationProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CalibrationLoadError("calibration profile is not valid JSON") from exc
    try:
        data = _mapping(raw, "calibration profile")
        if _integer(data, "schema_version") != CLIENT_PROFILE_SCHEMA_VERSION:
            raise CalibrationLoadError("unsupported calibration profile version")
        target_data = _object(data, "target")
        movement_data = _object(data, "movement")
        camera_data = _object(data, "camera")
        return CalibrationProfile(
            profile_id=_string(data, "profile_id"),
            target=ClientTarget(
                executable_names=tuple(_strings(target_data, "executable_names")),
                title_pattern=_string(target_data, "title_pattern"),
                reference_width=_integer(target_data, "reference_width"),
                reference_height=_integer(target_data, "reference_height"),
                dpi_scale=_number(target_data, "dpi_scale"),
                size_tolerance_px=_integer(target_data, "size_tolerance_px"),
                dpi_tolerance=_number(target_data, "dpi_tolerance"),
            ),
            actions=tuple(_parse_action(item) for item in _objects(data, "actions")),
            movement=DirectionalClickMapping(
                action_key=_string(movement_data, "action_key"),
                center=_point(_object(movement_data, "center")),
                horizontal_radius=_number(movement_data, "horizontal_radius"),
                vertical_radius=_number(movement_data, "vertical_radius"),
                button=MouseButton(_string(movement_data, "button")),
            ),
            camera=CameraDragMapping(
                anchor=_point(_object(camera_data, "anchor")),
                maximum_horizontal_delta=_number(camera_data, "maximum_horizontal_delta"),
                maximum_vertical_delta=_number(camera_data, "maximum_vertical_delta"),
                duration_ms=_integer(camera_data, "duration_ms"),
                button=MouseButton(_string(camera_data, "button")),
            ),
        )
    except CalibrationLoadError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, KeyError):
            raise CalibrationLoadError(f"missing required field: {exc.args[0]}") from exc
        raise CalibrationLoadError(str(exc)) from exc


def _parse_action(data: Mapping[str, Any]) -> ActionInputMapping:
    activation_data = _object(data, "activation")
    activation_type = _string(activation_data, "type")
    if activation_type == "click":
        activation = ClickActivation(
            point=_point(_object(activation_data, "point")),
            button=MouseButton(_string(activation_data, "button")),
        )
    elif activation_type == "key":
        activation = KeyActivation(_string(activation_data, "key"))
    elif activation_type == "hotkey":
        activation = HotkeyActivation(tuple(_strings(activation_data, "keys")))
    else:
        raise CalibrationLoadError(f"unsupported activation type: {activation_type}")
    return ActionInputMapping(
        action_key=_string(data, "action_key"),
        activation=activation,
        target_order=TargetOrder(_string(data, "target_order")),
        post_activation_delay_ms=_integer(data, "post_activation_delay_ms"),
    )


def _point(data: Mapping[str, Any]) -> NormalizedPoint:
    return NormalizedPoint(x=_number(data, "x"), y=_number(data, "y"))


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _mapping(data[key], key)


def _sequence(data: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = data[key]
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CalibrationLoadError(f"{key} must be an array")
    return value


def _objects(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(value, f"{key} item") for value in _sequence(data, key))


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise CalibrationLoadError(f"{key} must be a non-empty string")
    return value


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = _sequence(data, key)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise CalibrationLoadError(f"{key} must contain non-empty strings")
    return tuple(cast(str, value) for value in values)


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CalibrationLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationLoadError(f"{key} must be a number")
    return float(value)
