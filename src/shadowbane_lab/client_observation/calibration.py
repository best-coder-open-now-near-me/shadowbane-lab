"""Strict JSON loading for client-observation calibration profiles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.client_observation.model import (
    CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION,
    ClientObservationProfile,
    ClientPixelRegion,
    RedPixelThreshold,
    TargetHealthBarCalibration,
)


class ObservationCalibrationLoadError(ValueError):
    """Raised when observation calibration is malformed or unsupported."""


def load_observation_calibration(path: str | Path) -> ClientObservationProfile:
    return load_observation_calibration_text(Path(path).read_text(encoding="utf-8"))


def load_observation_calibration_text(text: str) -> ClientObservationProfile:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ObservationCalibrationLoadError(
            "observation calibration profile is not valid JSON"
        ) from exc
    try:
        data = _mapping(raw, "observation calibration profile")
        if _integer(data, "schema_version") != CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION:
            raise ObservationCalibrationLoadError(
                "unsupported client observation profile version"
            )
        health = _object(data, "target_health_bar")
        region = _object(health, "region")
        threshold = _object(health, "red_threshold")
        return ClientObservationProfile(
            profile_id=_string(data, "profile_id"),
            client_profile_id=_string(data, "client_profile_id"),
            target_health_bar=TargetHealthBarCalibration(
                region=ClientPixelRegion(
                    left=_integer(region, "left"),
                    top=_integer(region, "top"),
                    width=_integer(region, "width"),
                    height=_integer(region, "height"),
                ),
                red_threshold=RedPixelThreshold(
                    minimum_red=_integer(threshold, "minimum_red"),
                    red_to_green_ratio=_number(threshold, "red_to_green_ratio"),
                    red_to_blue_ratio=_number(threshold, "red_to_blue_ratio"),
                ),
                minimum_red_pixels_per_column=_integer(
                    health, "minimum_red_pixels_per_column"
                ),
                minimum_present_columns=_integer(health, "minimum_present_columns"),
                maximum_stray_columns=_integer(health, "maximum_stray_columns"),
            ),
        )
    except ObservationCalibrationLoadError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, KeyError):
            raise ObservationCalibrationLoadError(
                f"missing required field: {exc.args[0]}"
            ) from exc
        raise ObservationCalibrationLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ObservationCalibrationLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _mapping(data[key], key)


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ObservationCalibrationLoadError(f"{key} must be a non-empty string")
    return value


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ObservationCalibrationLoadError(f"{key} must be an integer")
    return value


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationCalibrationLoadError(f"{key} must be a number")
    return float(value)
