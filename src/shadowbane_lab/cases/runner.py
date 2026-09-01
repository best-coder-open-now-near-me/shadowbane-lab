"""Bounded experiment orchestration over named, guarded step executors."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
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
    artifacts: tuple[ProducedArtifact, ...] = ()
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


@dataclass(frozen=True, slots=True)
class ProducedArtifact:
    payload: bytes
    artifact_kind: ArtifactKind
    media_type: str
    logical_name: str
    metadata: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes):
            raise ValueError("produced artifact payload must be bytes")
        if not isinstance(self.artifact_kind, ArtifactKind):
            raise ValueError("produced artifact kind is invalid")
        names = tuple(name for name, _ in self.metadata)
        if names != tuple(sorted(set(names))):
            raise ValueError("produced artifact metadata must use canonical keys")
        for _, value in self.metadata:
            validate_finite_json(value)


class ExecutionControl:
    """Per-run authority that reserves irreversible effects before execution."""

    def __init__(
        self,
        *,
        started_monotonic: float,
        deadline_monotonic: float,
        maximum_input_count: int,
        maximum_input_rate_per_second: float,
        maximum_resource_loss: float,
        cancellation_requested: Callable[[], bool],
    ) -> None:
        self.started_monotonic = started_monotonic
        self.deadline_monotonic = deadline_monotonic
        self.maximum_input_count = maximum_input_count
        self.maximum_input_rate_per_second = maximum_input_rate_per_second
        self.maximum_resource_loss = maximum_resource_loss
        self._cancellation_requested = cancellation_requested
        self._reserved_inputs = 0
        self._reserved_resource_loss = 0.0

    @property
    def reserved_inputs(self) -> int:
        return self._reserved_inputs

    @property
    def reserved_resource_loss(self) -> float:
        return self._reserved_resource_loss

    @property
    def remaining_input_count(self) -> int:
        return self.maximum_input_count - self._reserved_inputs

    @property
    def remaining_resource_loss(self) -> float:
        return self.maximum_resource_loss - self._reserved_resource_loss

    def check(self) -> None:
        if self._cancellation_requested():
            raise CaseError("experiment execution was cancelled")
        if monotonic() >= self.deadline_monotonic:
            raise CaseError("experiment exceeded maximum duration")

    def reserve(self, *, input_count: int = 0, resource_loss: float = 0.0) -> None:
        """Reserve declared effects before an adapter performs them."""

        self.check()
        if isinstance(input_count, bool) or not isinstance(input_count, int) or input_count < 0:
            raise ValueError("reserved input_count must be a non-negative integer")
        if (
            isinstance(resource_loss, bool)
            or not isinstance(resource_loss, int | float)
            or not isfinite(resource_loss)
            or resource_loss < 0
        ):
            raise ValueError("reserved resource_loss must be finite and non-negative")
        proposed_inputs = self._reserved_inputs + input_count
        proposed_loss = self._reserved_resource_loss + float(resource_loss)
        if proposed_inputs > self.maximum_input_count:
            raise CaseError("input reservation exceeds maximum input count")
        if proposed_loss > self.maximum_resource_loss:
            raise CaseError("resource reservation exceeds maximum resource loss")
        if input_count and self.maximum_input_rate_per_second <= 0:
            raise CaseError("input reservation is forbidden by the maximum input rate")
        elapsed = max(monotonic() - self.started_monotonic, 1.0)
        if input_count and proposed_inputs / elapsed > self.maximum_input_rate_per_second:
            raise CaseError("input reservation exceeds maximum input rate")
        self._reserved_inputs = proposed_inputs
        self._reserved_resource_loss = proposed_loss


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
        control: ExecutionControl,
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
        control: ExecutionControl,
    ) -> StepOutcome:
        del run, context
        control.check()
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
        control: ExecutionControl,
    ) -> StepOutcome:
        del run, context
        control.check()
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
    cancellation_requested: Callable[[], bool] | None = None,
) -> RunExecution:
    validate_case_experiment(case, definition, fingerprint)
    if (
        run.experiment_id != definition.experiment_id
        or run.experiment_revision != definition.revision
    ):
        raise CaseError("expanded run does not belong to this experiment revision")
    step_by_sequence = {item.sequence: item for item in definition.steps}
    sequence = 1
    active_repeat: tuple[int, int, int, int] | None = None
    observations: dict[str, Any] = dict(run.variables)
    completed_channels: set[str] = set()
    trace: list[dict[str, object]] = []
    produced_artifacts: list[ProducedArtifact] = []
    total_inputs = 0
    total_loss = 0.0
    reported_elapsed = 0.0
    started = monotonic()
    control = ExecutionControl(
        started_monotonic=started,
        deadline_monotonic=started + definition.safety.maximum_duration_seconds,
        maximum_input_count=definition.safety.maximum_input_count,
        maximum_input_rate_per_second=definition.safety.maximum_input_rate_per_second,
        maximum_resource_loss=definition.safety.maximum_resource_loss,
        cancellation_requested=cancellation_requested or (lambda: False),
    )
    execution_count = 0
    max_executions = min(1_000_000, len(definition.steps) * 10_001)
    failed = False
    execution_error: str | None = None
    try:
        while sequence <= len(definition.steps):
            execution_count += 1
            if execution_count > max_executions:
                raise CaseError("experiment exceeded its bounded step execution limit")
            control.check()
            step = step_by_sequence[sequence]
            if step.kind is StepKind.REPEAT:
                if active_repeat is not None:
                    raise CaseError("overlapping repeat execution is not permitted")
                parameters = dict(step.parameters)
                active_repeat = (
                    parameters["start_sequence"],
                    parameters["end_sequence"],
                    parameters["count"],
                    step.sequence,
                )
                sequence = parameters["start_sequence"]
                continue
            before_inputs = control.reserved_inputs
            before_loss = control.reserved_resource_loss
            outcome = executor.execute(
                step,
                run=run,
                context=observations,
                control=control,
            )
            control.check()
            reserved_inputs = control.reserved_inputs - before_inputs
            reserved_loss = control.reserved_resource_loss - before_loss
            if outcome.input_count != reserved_inputs:
                raise CaseError("executor input report does not match its pre-action reservation")
            if float(outcome.resource_loss) != reserved_loss:
                raise CaseError("executor resource report does not match its pre-action reservation")
            total_inputs += outcome.input_count
            total_loss += float(outcome.resource_loss)
            reported_elapsed += float(outcome.elapsed_seconds)
            observations.update(outcome.observations)
            completed_channels.update(outcome.completed_channels)
            produced_artifacts.extend(outcome.artifacts)
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
            if active_repeat is not None and step.sequence == active_repeat[1]:
                start_sequence, end_sequence, remaining, repeat_sequence = active_repeat
                if remaining > 1:
                    active_repeat = (
                        start_sequence,
                        end_sequence,
                        remaining - 1,
                        repeat_sequence,
                    )
                    sequence = start_sequence
                else:
                    active_repeat = None
                    sequence = repeat_sequence + 1
            elif step.kind is StepKind.BRANCH_ON_OBSERVATION:
                values = dict(step.parameters)
                sequence = values["true_sequence"] if outcome.passed else values["false_sequence"]
            else:
                sequence += 1
            if outcome.stop:
                break
    except Exception as exc:
        failed = True
        execution_error = f"{type(exc).__name__}: {exc}"
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
        "execution_error": execution_error,
    }
    captured = canonical_timestamp()
    descriptors = [
        store.ingest_bytes(
            artifact.payload,
            artifact_kind=artifact.artifact_kind,
            media_type=artifact.media_type,
            logical_name=artifact.logical_name,
            producer_id=executor.executor_id,
            producer_version=executor.executor_version,
            captured_at_utc=captured,
            metadata=artifact.metadata,
        )
        for artifact in produced_artifacts
    ]
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
    descriptors.append(descriptor)
    artifacts: tuple[ArtifactDescriptor, ...] = tuple(
        sorted(
            {item.artifact_id: item for item in descriptors}.values(),
            key=lambda item: item.artifact_id or "",
        )
    )
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
        warnings=()
        if not failed
        else tuple(
            sorted(
                {
                    "experiment or oracle failure",
                    *((execution_error,) if execution_error is not None else ()),
                }
            )
        ),
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
    cancellation_requested: Callable[[], bool] | None = None,
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
            cancellation_requested=cancellation_requested,
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
    "ExecutionControl",
    "ExperimentStepExecutor",
    "RecordedExecutor",
    "ProducedArtifact",
    "RunExecution",
    "StepOutcome",
    "execute_plan",
    "execute_run",
    "validate_case_experiment",
]
