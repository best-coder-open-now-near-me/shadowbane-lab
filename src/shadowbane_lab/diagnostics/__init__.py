"""Capture-once, analyze-repeatedly diagnostic tooling."""

from .analysis import analyze_diagnostic_capture, compare_diagnostic_captures
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
    "DiagnosticCaptureResult",
    "DiagnosticError",
    "DiagnosticProfile",
    "DiagnosticRequest",
    "FileCaptureMode",
    "FileChannel",
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
    "run_diagnostic_capture",
]
