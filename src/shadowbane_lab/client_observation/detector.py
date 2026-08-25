"""Deterministic target-presence and health detection from RGB client frames."""

from __future__ import annotations

from shadowbane_lab.client_observation.frame import RgbFrame
from shadowbane_lab.client_observation.model import (
    ClientObservationProfile,
    TargetStatusObservation,
)


class ObservationDetectionError(RuntimeError):
    """Raised when a frame cannot be interpreted under its calibration."""


class TargetHealthBarDetector:
    def __init__(
        self,
        profile: ClientObservationProfile,
        *,
        expected_width: int,
        expected_height: int,
    ) -> None:
        if not isinstance(profile, ClientObservationProfile):
            raise ValueError("profile must be ClientObservationProfile")
        profile.target_health_bar.region.require_inside(expected_width, expected_height)
        self._profile = profile
        self._expected_width = expected_width
        self._expected_height = expected_height

    def observe(self, frame: RgbFrame) -> TargetStatusObservation:
        if not isinstance(frame, RgbFrame):
            raise ValueError("frame must be RgbFrame")
        if (frame.width, frame.height) != (
            self._expected_width,
            self._expected_height,
        ):
            raise ObservationDetectionError(
                "captured frame dimensions do not match the calibrated client"
            )

        calibration = self._profile.target_health_bar
        region = calibration.region
        threshold = calibration.red_threshold
        filled: list[bool] = []
        red_pixel_count = 0
        for local_x in range(region.width):
            qualifying_pixels = 0
            for local_y in range(region.height):
                red, green, blue = frame.rgb_at(
                    region.left + local_x,
                    region.top + local_y,
                )
                if threshold.matches(red, green, blue):
                    qualifying_pixels += 1
                    red_pixel_count += 1
            filled.append(
                qualifying_pixels >= calibration.minimum_red_pixels_per_column
            )

        leading_filled_columns = 0
        for is_filled in filled:
            if not is_filled:
                break
            leading_filled_columns += 1
        total_filled_columns = sum(filled)
        stray_filled_columns = total_filled_columns - leading_filled_columns
        if stray_filled_columns > calibration.maximum_stray_columns:
            raise ObservationDetectionError(
                "target health fill is not a calibrated left-anchored bar"
            )

        target_present = (
            leading_filled_columns >= calibration.minimum_present_columns
        )
        health_fraction = (
            leading_filled_columns / region.width if target_present else None
        )
        return TargetStatusObservation(
            target_present=target_present,
            health_fraction=health_fraction,
            leading_filled_columns=leading_filled_columns,
            total_filled_columns=total_filled_columns,
            total_columns=region.width,
            red_pixel_count=red_pixel_count,
            stray_filled_columns=stray_filled_columns,
        )
