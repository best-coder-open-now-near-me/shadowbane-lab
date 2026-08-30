"""Typed, versioned calibration and read-only client observations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION = 1


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _channel(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError(f"{field_name} must be an integer in [0, 255]")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


@dataclass(frozen=True, slots=True)
class ClientPixelRegion:
    """Integer pixel bounds relative to the guarded client area."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        _non_negative_integer(self.left, "left")
        _non_negative_integer(self.top, "top")
        _positive_integer(self.width, "width")
        _positive_integer(self.height, "height")

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def require_inside(self, width: int, height: int) -> None:
        _positive_integer(width, "client width")
        _positive_integer(height, "client height")
        if self.right > width or self.bottom > height:
            raise ValueError("pixel region must remain inside client bounds")


@dataclass(frozen=True, slots=True)
class RedPixelThreshold:
    minimum_red: int
    red_to_green_ratio: float
    red_to_blue_ratio: float

    def __post_init__(self) -> None:
        _channel(self.minimum_red, "minimum_red")
        for value, field_name in (
            (self.red_to_green_ratio, "red_to_green_ratio"),
            (self.red_to_blue_ratio, "red_to_blue_ratio"),
        ):
            _finite(value, field_name)
            if value < 1.0:
                raise ValueError(f"{field_name} must be at least 1.0")

    def matches(self, red: int, green: int, blue: int) -> bool:
        for value, field_name in (
            (red, "red"),
            (green, "green"),
            (blue, "blue"),
        ):
            _channel(value, field_name)
        return (
            red >= self.minimum_red
            and red >= green * self.red_to_green_ratio
            and red >= blue * self.red_to_blue_ratio
        )


@dataclass(frozen=True, slots=True)
class TargetHealthBarCalibration:
    region: ClientPixelRegion
    red_threshold: RedPixelThreshold
    minimum_red_pixels_per_column: int
    minimum_present_columns: int
    maximum_stray_columns: int

    def __post_init__(self) -> None:
        if not isinstance(self.region, ClientPixelRegion):
            raise ValueError("region must be ClientPixelRegion")
        if not isinstance(self.red_threshold, RedPixelThreshold):
            raise ValueError("red_threshold must be RedPixelThreshold")
        _positive_integer(
            self.minimum_red_pixels_per_column,
            "minimum_red_pixels_per_column",
        )
        if self.minimum_red_pixels_per_column > self.region.height:
            raise ValueError("minimum red pixels per column cannot exceed region height")
        _positive_integer(self.minimum_present_columns, "minimum_present_columns")
        if self.minimum_present_columns > self.region.width:
            raise ValueError("minimum present columns cannot exceed region width")
        _non_negative_integer(self.maximum_stray_columns, "maximum_stray_columns")
        if self.maximum_stray_columns >= self.region.width:
            raise ValueError("maximum stray columns must be smaller than region width")


@dataclass(frozen=True, slots=True)
class ClientObservationProfile:
    profile_id: str
    client_profile_id: str
    target_health_bar: TargetHealthBarCalibration
    schema_version: int = CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.profile_id, "profile_id")
        _identifier(self.client_profile_id, "client_profile_id")
        if self.schema_version != CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION:
            raise ValueError("unsupported client observation profile version")
        if not isinstance(self.target_health_bar, TargetHealthBarCalibration):
            raise ValueError("target_health_bar must be TargetHealthBarCalibration")


@dataclass(frozen=True, slots=True)
class TargetStatusObservation:
    target_present: bool
    health_fraction: float | None
    leading_filled_columns: int
    total_filled_columns: int
    total_columns: int
    red_pixel_count: int
    stray_filled_columns: int

    def __post_init__(self) -> None:
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be a boolean")
        for value, field_name in (
            (self.leading_filled_columns, "leading_filled_columns"),
            (self.total_filled_columns, "total_filled_columns"),
            (self.red_pixel_count, "red_pixel_count"),
            (self.stray_filled_columns, "stray_filled_columns"),
        ):
            _non_negative_integer(value, field_name)
        _positive_integer(self.total_columns, "total_columns")
        if self.leading_filled_columns > self.total_filled_columns:
            raise ValueError("leading filled columns cannot exceed total filled columns")
        if self.total_filled_columns > self.total_columns:
            raise ValueError("filled columns cannot exceed total columns")
        if self.stray_filled_columns != (self.total_filled_columns - self.leading_filled_columns):
            raise ValueError("stray filled columns are inconsistent")
        if self.target_present:
            if self.health_fraction is None:
                raise ValueError("present target requires a health fraction")
            _finite(self.health_fraction, "health_fraction")
            if not 0.0 < self.health_fraction <= 1.0:
                raise ValueError("health_fraction must be in (0, 1]")
        elif self.health_fraction is not None:
            raise ValueError("absent target must not have a health fraction")
