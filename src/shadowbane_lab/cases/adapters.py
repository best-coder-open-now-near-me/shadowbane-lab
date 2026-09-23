"""Offline-safe capture replay adapters for the representative case families."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shadowbane_lab.evidence import ArtifactKind
from shadowbane_lab.integrity import canonical_json_bytes

from .alignment import align_capture_records
from .capture import CaptureRecord, completed_capture_channels, producer_health
from .model import CaseError, ExpandedRun, ExperimentStep
from .runner import ExecutionControl, ProducedArtifact, StepOutcome


class CaptureReplayExecutor:
    """Converts pre-recorded producer records into ordinary run evidence."""

    executor_version = "1"

    def __init__(
        self,
        executor_id: str,
        records_by_run: Mapping[str, tuple[CaptureRecord, ...]],
        *,
        required_channels: tuple[str, ...],
    ) -> None:
        self.executor_id = executor_id
        self._records_by_run = dict(records_by_run)
        self._required = frozenset(required_channels)
        self._emitted: set[str] = set()

    def execute(
        self,
        step: ExperimentStep,
        *,
        run: ExpandedRun,
        context: Mapping[str, Any],
        control: ExecutionControl,
    ) -> StepOutcome:
        del step, context
        control.check()
        try:
            records = self._records_by_run[run.run_id]
        except KeyError as exc:
            raise CaseError(f"no capture records supplied for {run.run_id}") from exc
        if any(item.run_id != run.run_id for item in records):
            raise CaseError("capture replay records do not match the expanded run ID")
        completed = completed_capture_channels(records)
        observations: dict[str, Any] = {}
        for record in records:
            observations.update(record.payload)
        artifacts: tuple[ProducedArtifact, ...] = ()
        if run.run_id not in self._emitted:
            self._emitted.add(run.run_id)
            stream = {
                "schema_version": 1,
                "records": [item.as_dict() for item in records],
                "producer_health": [item.as_dict() for item in producer_health(records)],
            }
            trace = align_capture_records(records)
            artifacts = (
                ProducedArtifact(
                    canonical_json_bytes(stream),
                    ArtifactKind.NATIVE_EVENT_STREAM,
                    "application/vnd.shadowbane.capture-stream+json",
                    f"{run.run_id}.capture.json",
                    (("run_id", run.run_id),),
                ),
                ProducedArtifact(
                    canonical_json_bytes(trace.as_dict()),
                    ArtifactKind.SEMANTIC_TRACE,
                    "application/vnd.shadowbane.semantic-trace+json",
                    f"{run.run_id}.trace.json",
                    (("trace_id", trace.trace_id),),
                ),
            )
        return StepOutcome(
            passed=True,
            observations=tuple(sorted(observations.items())),
            completed_channels=tuple(sorted(completed)),
            artifacts=artifacts,
        )


def runtime_health_executor(
    records_by_run: Mapping[str, tuple[CaptureRecord, ...]],
) -> CaptureReplayExecutor:
    return CaptureReplayExecutor(
        "shadowbane-lab.runtime-health-replay",
        records_by_run,
        required_channels=("extension_health", "process_metrics", "worker_health"),
    )


def vendor_dialog_executor(
    records_by_run: Mapping[str, tuple[CaptureRecord, ...]],
) -> CaptureReplayExecutor:
    return CaptureReplayExecutor(
        "shadowbane-lab.vendor-dialog-replay",
        records_by_run,
        required_channels=("native_vendor", "network_summary"),
    )


def combat_breakpoint_executor(
    records_by_run: Mapping[str, tuple[CaptureRecord, ...]],
) -> CaptureReplayExecutor:
    return CaptureReplayExecutor(
        "shadowbane-lab.combat-breakpoint-replay",
        records_by_run,
        required_channels=("native_state", "semantic_trace", "simulator_trace"),
    )


__all__ = [
    "CaptureReplayExecutor",
    "combat_breakpoint_executor",
    "runtime_health_executor",
    "vendor_dialog_executor",
]
