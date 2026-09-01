"""Complete execution fingerprint capture, persistence, and comparison."""

from .capture import FingerprintCaptureInputs, capture_fingerprint
from .codec import load_fingerprint, save_fingerprint
from .compare import compare_fingerprints
from .model import (
    Applicability,
    FingerprintDiff,
    FingerprintEnvelope,
    FingerprintError,
    FingerprintSection,
    ImpactState,
    SectionDifference,
    SectionName,
)

__all__ = [
    "Applicability",
    "FingerprintCaptureInputs",
    "FingerprintDiff",
    "FingerprintEnvelope",
    "FingerprintError",
    "FingerprintSection",
    "ImpactState",
    "SectionDifference",
    "SectionName",
    "capture_fingerprint",
    "compare_fingerprints",
    "load_fingerprint",
    "save_fingerprint",
]
