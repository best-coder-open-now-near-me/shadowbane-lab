"""Read-only, calibrated observations from the guarded game client."""

from shadowbane_lab.client_observation.calibration import (
    ObservationCalibrationLoadError,
    load_observation_calibration,
    load_observation_calibration_text,
)
from shadowbane_lab.client_observation.detector import (
    ObservationDetectionError,
    TargetHealthBarDetector,
)
from shadowbane_lab.client_observation.frame import (
    FrameCapture,
    PyAutoGuiFrameCapture,
    RgbFrame,
    StaticFrameCapture,
)
from shadowbane_lab.client_observation.model import (
    CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION,
    ClientObservationProfile,
    ClientPixelRegion,
    RedPixelThreshold,
    TargetHealthBarCalibration,
    TargetStatusObservation,
)
from shadowbane_lab.client_observation.native_log import (
    NativeCombatLogEntry,
    NativeCombatLogFormatError,
    NativeCombatLogReader,
)
from shadowbane_lab.client_observation.observer import ClientTargetObserver

__all__ = [
    "CLIENT_OBSERVATION_PROFILE_SCHEMA_VERSION",
    "ClientObservationProfile",
    "ClientPixelRegion",
    "ClientTargetObserver",
    "FrameCapture",
    "NativeCombatLogEntry",
    "NativeCombatLogFormatError",
    "NativeCombatLogReader",
    "ObservationCalibrationLoadError",
    "ObservationDetectionError",
    "PyAutoGuiFrameCapture",
    "RedPixelThreshold",
    "RgbFrame",
    "StaticFrameCapture",
    "TargetHealthBarCalibration",
    "TargetHealthBarDetector",
    "TargetStatusObservation",
    "load_observation_calibration",
    "load_observation_calibration_text",
]
