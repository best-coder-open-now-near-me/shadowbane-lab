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
from shadowbane_lab.client_observation.native_health import (
    NATIVE_HEALTH_PROFILE_SCHEMA_VERSION,
    NativeHealthProfileLoadError,
    NativeTargetHealthCompatibilityError,
    NativeTargetHealthError,
    NativeTargetHealthObservation,
    NativeTargetHealthProfile,
    NativeTargetHealthReader,
    NativeTargetHealthReadError,
    ReadOnlyProcessMemory,
    WindowsReadOnlyProcessMemory,
    load_bundled_native_health_profile,
    load_native_health_profile,
    load_native_health_profile_text,
    open_windows_native_target_health_reader,
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
    "NATIVE_HEALTH_PROFILE_SCHEMA_VERSION",
    "NativeHealthProfileLoadError",
    "NativeTargetHealthCompatibilityError",
    "NativeTargetHealthError",
    "NativeTargetHealthObservation",
    "NativeTargetHealthProfile",
    "NativeTargetHealthReadError",
    "NativeTargetHealthReader",
    "ObservationCalibrationLoadError",
    "ObservationDetectionError",
    "PyAutoGuiFrameCapture",
    "RedPixelThreshold",
    "ReadOnlyProcessMemory",
    "RgbFrame",
    "StaticFrameCapture",
    "TargetHealthBarCalibration",
    "TargetHealthBarDetector",
    "TargetStatusObservation",
    "WindowsReadOnlyProcessMemory",
    "load_bundled_native_health_profile",
    "load_native_health_profile",
    "load_native_health_profile_text",
    "load_observation_calibration",
    "load_observation_calibration_text",
    "open_windows_native_target_health_reader",
]
