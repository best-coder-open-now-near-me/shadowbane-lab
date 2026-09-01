"""Capture-once, analyze-repeatedly diagnostic tooling."""

from .analysis import analyze_diagnostic_capture, compare_diagnostic_captures
from .camera import (
    CAMERA_STATE_EVIDENCE_SCHEMA_VERSION,
    CAMERA_STATE_PRODUCER_SCHEMA_VERSION,
    CameraStateCollector,
)
from .graphics import (
    GRAPHICS_PRESENT_EVIDENCE_SCHEMA_VERSION,
    GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION,
    GraphicsPresentCollection,
    collect_graphics_present_evidence,
)
from .model import (
    DiagnosticError,
    DiagnosticProfile,
    DiagnosticRequest,
    FileCaptureMode,
    FileChannel,
    TriggerOperator,
    TriggerRule,
)
from .process import ProcessIdentity, ProcessProbe, ProcessSample, WindowsProcessProbe
from .session import (
    DiagnosticCaptureResult,
    SessionClock,
    SystemSessionClock,
    run_diagnostic_capture,
)

__all__ = [
    "CAMERA_STATE_EVIDENCE_SCHEMA_VERSION",
    "CAMERA_STATE_PRODUCER_SCHEMA_VERSION",
    "CameraStateCollector",
    "DiagnosticCaptureResult",
    "DiagnosticError",
    "DiagnosticProfile",
    "DiagnosticRequest",
    "FileCaptureMode",
    "FileChannel",
    "GRAPHICS_PRESENT_EVIDENCE_SCHEMA_VERSION",
    "GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION",
    "GraphicsPresentCollection",
    "ProcessIdentity",
    "ProcessProbe",
    "ProcessSample",
    "SessionClock",
    "SystemSessionClock",
    "TriggerOperator",
    "TriggerRule",
    "WindowsProcessProbe",
    "analyze_diagnostic_capture",
    "compare_diagnostic_captures",
    "collect_graphics_present_evidence",
    "run_diagnostic_capture",
]
