"""Bounded experiment orchestration over named, guarded step executors."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from time import monotonic
from typing import Any, Protocol

from shadowbane_lab.evidence import (
    ArtifactDescriptor,
    ArtifactKind,
    ArtifactStore,
    EvidenceManifest,
    ManifestTerminalState,
    save_contract,
)
from shadowbane_lab.fingerprints import Applicability, FingerprintEnvelope
from shadowbane_lab.integrity import canonical_json_bytes, canonical_timestamp, validate_finite_json

from .model import (
    CaseError,
    CaseState,
    ExpandedRun,
    ExperimentDefinition,
    ExperimentStep,
    OracleRule,
    OracleSeverity,
    ResearchCase,
    StepKind,
    expand_experiment,
)


@dataclass(frozen=True, slots=True)
class StepOutcome:
    passed: bool
    observations: tuple[tuple[str, Any], ...] = ()
    completed_channels: tuple[str, ...] = ()
    input_count: int = 0
    resource_loss: float = 0.0
    elapsed_seconds: float = 0.0
    stop: bool = False

    def __post_init__(self) -> None:
        names = tuple(name for name, _ in self.observations)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("step observations must use unique canonical keys")
        for _, value in self.observations:
            validate_finite_json(value)
        if self.completed_channels != tuple(sorted(set(self.completed_channels))):
            raise ValueError("completed channels must use canonical ordering")
        if (
            isinstance(self.input_count, bool)
            or not isinstance(self.input_count, int)
            or self.input_count < 0
        ):
            raise ValueError("input_count must be a non-negative integer")
        if (
            isinstance(self.resource_loss, bool)
            or not isinstance(self.resource_loss, int | float)
            or not isfinite(self.resource_loss)
            or self.resource_loss < 0
        ):
            raise ValueError("resource_loss must be non-negative")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, int | float)
            or not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("elapsed_seconds must be finite and non-negative")


class ExperimentStepExecutor(Protocol):
    """Named adapter boundary; definitions cannot carry executable code."""

    executor_id: str
    executor_version: str

    def execute(
        self,
        step: ExperimentStep,
        *,
        run: ExpandedRun,
        context: Mapping[str, Any],
    ) -> StepOutcome: ...


class DryRunExecutor:
    executor_id = "shadowbane-lab.dry-run"
    executor_version = "1"

    def execute(
        self,
        step: ExperimentStep,
        *,
        run: ExpandedRun,
        context: Mapping[str, Any],
    ) -> StepOutcome:
        del run, context
        return StepOutcome(
            passed=True,
            observations=(("dry_run_step", step.kind.value),),
            stop=step.kind is StepKind.STOP,
        )


class RecordedExecutor:
    """Replays finite recorded observations; it never generates desktop input."""

    executor_id = "shadowbane-lab.recorded"
    executor_version = "1"

    def __init__(
        self,
        observations_by_sequence: Mapping[int, Mapping[str, Any]],
        *,
        completed_channels: Iterable[str] = (),
    ) -> None:
        self._observations = {
            int(sequence): tuple(sorted(values.items()))
            for sequence, values in observations_by_sequence.items()
        }
        self._completed = tuple(sorted(set(completed_channels)))
        for values in self._observations.values():
            for _, value in values:
                validate_finite_json(value)

    def execute(
        self,
        step: ExperimentStep,
        *,
        run: ExpandedRun,
        context: Mapping[str, Any],
    ) -> StepOutcome:
        del run, context
        observations = self._observations.get(step.sequence, ())
        return StepOutcome(
            passed=_evaluate_step(step, dict(observations)),
            observations=observations,
            completed_channels=self._completed,
            stop=step.kind is StepKind.STOP,
        )


@dataclass(frozen=True, slots=True)
class RunExecution:
    manifest: EvidenceManifest
    record: dict[str, object]


def validate_case_experiment(
    case: ResearchCase,
    definition: ExperimentDefinition,
    fingerprint: FingerprintEnvelope,
) -> None:
    if case.state not in (CaseState.READY, CaseState.COLLECTING, CaseState.EVIDENCE_COMPLETE):
        raise CaseError("case must be ready, collecting, or evidence-complete to run")
    reference = (definition.experiment_id, definition.revision)
    if reference not in {(item.experiment_id, item.revision) for item in case.experiments}:
        raise CaseError("experiment revision is not referenced by the research case")
    if set(definition.hypothesis_ids) != {item.hypothesis_id for item in case.hypotheses}:
        raise CaseError("experiment hypotheses do not exactly match the case hypotheses")
    available = {
        item.name for item in fingerprint.sections if item.applicability is Applicability.APPLICABLE
    }
    missing = set(case.required_fingerprint_sections) - available
    if missing:
        raise CaseError(
            "fingerprint has non-applicable required sections: "
            + ", ".join(sorted(item.value for item in missing))
        )
    if not set(case.required_capture_channels).issubset(definition.capture.required_channels):
        raise CaseError("experiment does not require every case capture channel")


def execute_run(
    *,
    case: ResearchCase,
    definition: ExperimentDefinition,
    run: ExpandedRun,
    fingerprint: FingerprintEnvelope,
    store: ArtifactStore,
    manifest_path: str,
    executor: ExperimentStepExecutor,
) -> RunExecution:
    validate_case_experiment(case, definition, fingerprint)
    if (
        run.experiment_id != definition.experiment_id
        or run.experiment_revision != definition.revision
    ):
        raise CaseError("expanded run does not belong to this experiment revision")
    step_by_sequence = {item.sequence: item for item in definition.steps}
    sequence = 1
    repeat_counts: dict[int, int] = {}
    observations: dict[str, Any] = dict(run.variables)
    completed_channels: set[str] = set()
    trace: list[dict[str, object]] = []
    total_inputs = 0
    total_loss = 0.0
    reported_elapsed = 0.0
    started = monotonic()
    execution_count = 0
    max_executions = min(1_000_000, len(definition.steps) * 10_001)
    failed = False
    while sequence <= len(definition.steps):
        execution_count += 1
        if execution_count > max_executions:
            raise CaseError("experiment exceeded its bounded step execution limit")
        if monotonic() - started > definition.safety.maximum_duration_seconds:
            raise CaseError("experiment exceeded maximum duration")
        step = step_by_sequence[sequence]
        if step.kind is StepKind.REPEAT:
            parameters = dict(step.parameters)
            count = repeat_counts.get(sequence, 0)
            if count < parameters["count"]:
                repeat_counts[sequence] = count + 1
                sequence = parameters["start_sequence"]
                continue
            repeat_counts.pop(sequence, None)
            sequence += 1
            continue
        outcome = executor.execute(step, run=run, context=observations)
        total_inputs += outcome.input_count
        total_loss += float(outcome.resource_loss)
        reported_elapsed += float(outcome.elapsed_seconds)
        if total_inputs > definition.safety.maximum_input_count:
            raise CaseError("executor exceeded maximum input count")
        if total_loss > definition.safety.maximum_resource_loss:
            raise CaseError("executor exceeded maximum resource loss")
        elapsed = max(monotonic() - started, reported_elapsed)
        if total_inputs and (
            definition.safety.maximum_input_rate_per_second <= 0
            or total_inputs / max(elapsed, 1e-9) > definition.safety.maximum_input_rate_per_second
        ):
            raise CaseError("executor exceeded maximum input rate")
        observations.update(outcome.observations)
        completed_channels.update(outcome.completed_channels)
        trace.append(
            {
                "sequence": step.sequence,
                "kind": step.kind.value,
                "passed": outcome.passed,
                "observations": dict(outcome.observations),
            }
        )
        if not outcome.passed and step.kind is StepKind.ASSERT_PRECONDITION:
            failed = True
            break
        if step.kind is StepKind.BRANCH_ON_OBSERVATION:
            values = dict(step.parameters)
            sequence = values["true_sequence"] if outcome.passed else values["false_sequence"]
        else:
            sequence += 1
        if outcome.stop:
            break
    oracle_results = tuple(_evaluate_oracle(item, observations) for item in definition.oracle)
    if any(
        not passed and severity is OracleSeverity.FAILURE for passed, severity in oracle_results
    ):
        failed = True
    required = tuple(sorted(set(definition.capture.required_channels)))
    completed = tuple(sorted(set(required) & completed_channels))
    missing = tuple(sorted(set(required) - set(completed)))
    terminal = (
        ManifestTerminalState.FAILED
        if failed
        else ManifestTerminalState.COMPLETE
        if not missing
        else ManifestTerminalState.INCOMPLETE
    )
    record: dict[str, object] = {
        "schema_version": 1,
        "case_id": case.case_id,
        "case_revision": case.revision,
        "definition_id": definition.definition_id,
        "fingerprint_id": fingerprint.fingerprint_id,
        "executor_id": executor.executor_id,
        "executor_version": executor.executor_version,
        "run": run.as_dict(),
        "trace": trace,
        "observations": dict(sorted(observations.items())),
        "oracle": [
            {"rule": rule.as_dict(), "passed": result[0]}
            for rule, result in zip(definition.oracle, oracle_results, strict=True)
        ],
        "input_count": total_inputs,
        "resource_loss": total_loss,
        "elapsed_seconds": max(monotonic() - started, reported_elapsed),
        "terminal_state": terminal.value,
        "completed_channels": list(completed),
        "missing_channels": list(missing),
    }
    captured = canonical_timestamp()
    descriptor = store.ingest_bytes(
        canonical_json_bytes(record),
        artifact_kind=ArtifactKind.SIMULATION_RESULT,
        media_type="application/vnd.shadowbane.run-result+json",
        logical_name=f"{run.run_id}.json",
        producer_id=executor.executor_id,
        producer_version=executor.executor_version,
        captured_at_utc=captured,
        metadata=(("definition_id", definition.definition_id),),
    )
    artifacts: tuple[ArtifactDescriptor, ...] = (descriptor,)
    manifest = EvidenceManifest(
        created_at_utc=captured,
        fingerprint_id=fingerprint.fingerprint_id,
        case_id=case.case_id,
        experiment_id=definition.experiment_id,
        run_id=run.run_id,
        artifacts=artifacts,
        terminal_state=terminal,
        required_channels=required,
        completed_channels=completed,
        omissions=missing,
        warnings=() if not failed else ("experiment or oracle failure",),
    )
    save_contract(manifest_path, manifest)
    return RunExecution(manifest=manifest, record=record)


def execute_plan(
    *,
    case: ResearchCase,
    definition: ExperimentDefinition,
    fingerprint: FingerprintEnvelope,
    store: ArtifactStore,
    manifest_directory: str,
    executor: ExperimentStepExecutor,
    execution_nonce: str,
) -> tuple[RunExecution, ...]:
    from pathlib import Path

    directory = Path(manifest_directory)
    runs = expand_experiment(definition, execution_nonce=execution_nonce)
    return tuple(
        execute_run(
            case=case,
            definition=definition,
            run=run,
            fingerprint=fingerprint,
            store=store,
            manifest_path=str(directory / f"{run.run_id}.manifest.json"),
            executor=executor,
        )
        for run in runs
    )


def _evaluate_step(step: ExperimentStep, observations: Mapping[str, Any]) -> bool:
    if step.kind not in (
        StepKind.ASSERT_PRECONDITION,
        StepKind.WAIT_FOR_OBSERVATION,
        StepKind.BRANCH_ON_OBSERVATION,
    ):
        return True
    values = dict(step.parameters)
    field = values.get("field", values.get("predicate"))
    actual = observations.get(str(field))
    return _compare(actual, values.get("operator", "eq"), values.get("expected"), 0.0)


def _evaluate_oracle(
    rule: OracleRule, observations: Mapping[str, Any]
) -> tuple[bool, OracleSeverity]:
    return (
        _compare(
            observations.get(rule.field), rule.operator, rule.expected, rule.absolute_tolerance
        ),
        rule.severity,
    )


def _compare(actual: Any, operator: str, expected: Any, tolerance: float) -> bool:
    try:
        if operator == "eq":
            if isinstance(actual, int | float) and isinstance(expected, int | float):
                return abs(float(actual) - float(expected)) <= tolerance
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "lt":
            return actual < expected
        if operator == "le":
            return actual <= expected
        if operator == "gt":
            return actual > expected
        if operator == "ge":
            return actual >= expected
        if operator == "contains":
            return expected in actual
    except (TypeError, ValueError):
        return False
    return False


__all__ = [
    "DryRunExecutor",
    "ExperimentStepExecutor",
    "RecordedExecutor",
    "RunExecution",
    "StepOutcome",
    "execute_plan",
    "execute_run",
    "validate_case_experiment",
]
