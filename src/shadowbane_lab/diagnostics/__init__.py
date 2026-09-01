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
from .markers import (
    ObservationMarker,
    ObservationMarkerInbox,
    ObservationPhase,
    submit_observation_marker,
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
from .performance import (
    PERFORMANCE_EVIDENCE_SCHEMA_VERSION,
    PerformanceFrameCollector,
    PerformanceSnapshotSource,
)
from .process import ProcessIdentity, ProcessProbe, ProcessSample, WindowsProcessProbe
from .session import (
    DiagnosticCaptureResult,
    SessionClock,
    SystemSessionClock,
    run_diagnostic_capture,
)
from .timeline import (
    DIAGNOSTIC_TIMELINE_SCHEMA_VERSION,
    build_diagnostic_timeline,
)

__all__ = [
    "CAMERA_STATE_EVIDENCE_SCHEMA_VERSION",
    "CAMERA_STATE_PRODUCER_SCHEMA_VERSION",
    "CameraStateCollector",
    "DiagnosticCaptureResult",
    "DiagnosticError",
    "DIAGNOSTIC_TIMELINE_SCHEMA_VERSION",
    "DiagnosticProfile",
    "DiagnosticRequest",
    "FileCaptureMode",
    "FileChannel",
    "GRAPHICS_PRESENT_EVIDENCE_SCHEMA_VERSION",
    "GRAPHICS_RUNTIME_STATUS_SCHEMA_VERSION",
    "GraphicsPresentCollection",
    "ObservationMarker",
    "ObservationMarkerInbox",
    "ObservationPhase",
    "PERFORMANCE_EVIDENCE_SCHEMA_VERSION",
    "PerformanceFrameCollector",
    "PerformanceSnapshotSource",
    "ProcessIdentity",
    "ProcessProbe",
    "ProcessSample",
    "SessionClock",
    "SystemSessionClock",
    "TriggerOperator",
    "TriggerRule",
    "WindowsProcessProbe",
    "analyze_diagnostic_capture",
    "build_diagnostic_timeline",
    "compare_diagnostic_captures",
    "collect_graphics_present_evidence",
    "run_diagnostic_capture",
    "submit_observation_marker",
]
