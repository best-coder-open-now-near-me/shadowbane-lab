"""Differential trace capture, comparison, and simulator-gap tracking."""

from shadowbane_lab.differential.codec import (
    TraceDecodeError,
    decode_trace,
    encode_trace,
    trace_semantic_view,
)
from shadowbane_lab.differential.compare import (
    ComparisonReport,
    ComparisonTolerance,
    DifferenceCategory,
    GapEntry,
    GapLedger,
    GapStatus,
    TraceDifference,
    compare_traces,
)
from shadowbane_lab.differential.ledger import (
    GAP_LEDGER_SCHEMA_VERSION,
    GapLedgerLoadError,
    load_bundled_gap_ledger,
    load_gap_ledger,
    load_gap_ledger_text,
)
from shadowbane_lab.differential.model import (
    TRACE_SCHEMA_VERSION,
    CapturedEffect,
    CapturedEntity,
    CapturedState,
    TraceMetadata,
    TraceSource,
    TraceStep,
    TransitionTrace,
)
from shadowbane_lab.differential.recorder import ReferenceTraceRecorder

__all__ = [
    "GAP_LEDGER_SCHEMA_VERSION",
    "TRACE_SCHEMA_VERSION",
    "CapturedEffect",
    "CapturedEntity",
    "CapturedState",
    "ComparisonReport",
    "ComparisonTolerance",
    "DifferenceCategory",
    "GapEntry",
    "GapLedger",
    "GapLedgerLoadError",
    "GapStatus",
    "ReferenceTraceRecorder",
    "TraceDecodeError",
    "TraceDifference",
    "TraceMetadata",
    "TraceSource",
    "TraceStep",
    "TransitionTrace",
    "compare_traces",
    "decode_trace",
    "encode_trace",
    "load_bundled_gap_ledger",
    "load_gap_ledger",
    "load_gap_ledger_text",
    "trace_semantic_view",
]
