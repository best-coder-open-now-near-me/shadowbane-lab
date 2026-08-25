"""Foreground-guarded, read-only target observation."""

from __future__ import annotations

from shadowbane_lab.client_input import (
    CalibrationProfile,
    ForegroundWindowGuard,
    WindowInspector,
)
from shadowbane_lab.client_observation.detector import TargetHealthBarDetector
from shadowbane_lab.client_observation.frame import FrameCapture
from shadowbane_lab.client_observation.model import (
    ClientObservationProfile,
    TargetStatusObservation,
)


class ClientTargetObserver:
    """Captures and interprets one guarded client frame without sending input."""

    def __init__(
        self,
        client_profile: CalibrationProfile,
        observation_profile: ClientObservationProfile,
        inspector: WindowInspector,
        capture: FrameCapture,
    ) -> None:
        if not isinstance(client_profile, CalibrationProfile):
            raise ValueError("client_profile must be CalibrationProfile")
        if not isinstance(observation_profile, ClientObservationProfile):
            raise ValueError("observation_profile must be ClientObservationProfile")
        if observation_profile.client_profile_id != client_profile.profile_id:
            raise ValueError("observation profile does not target this client profile")
        if not isinstance(capture, FrameCapture):
            raise ValueError("capture must implement FrameCapture")
        self._guard = ForegroundWindowGuard(client_profile, inspector)
        self._capture = capture
        self._detector = TargetHealthBarDetector(
            observation_profile,
            expected_width=client_profile.target.reference_width,
            expected_height=client_profile.target.reference_height,
        )

    def observe(self) -> TargetStatusObservation:
        snapshot = self._guard.require_target()
        frame = self._capture.capture(snapshot.client_bounds)
        return self._detector.observe(frame)
