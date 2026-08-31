"""Versioned research-case and bounded experiment contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import product
from math import isfinite
from typing import Any

from shadowbane_lab.evidence.model import parse_artifact_id
from shadowbane_lab.fingerprints import SectionName
from shadowbane_lab.integrity import (
    canonical_json_sha256,
    validate_finite_json,
    validate_identifier,
)

RESEARCH_CASE_SCHEMA_VERSION = 1
EXPERIMENT_DEFINITION_SCHEMA_VERSION = 1


class CaseError(RuntimeError):
    """Raised when a research case or experiment cannot be trusted."""


class CaseState(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    COLLECTING = "collecting"
    EVIDENCE_COMPLETE = "evidence_complete"
    REVIEWED = "reviewed"
    CLOSED = "closed"


class StepKind(StrEnum):
    ASSERT_PRECONDITION = "assert_precondition"
    CAPTURE_MARKER = "capture_marker"
    SEMANTIC_DECISION = "semantic_decision"
    WAIT_FOR_OBSERVATION = "wait_for_observation"
    WAIT_DURATION = "wait_virtual_or_wall_duration"
    REPEAT = "repeat"
    BRANCH_ON_OBSERVATION = "branch_on_observation"
    RECORD_ANNOTATION = "record_annotation"
    STOP = "stop"


class VariableOrder(StrEnum):
    CANONICAL = "canonical"
    SEEDED_SHUFFLE = "seeded_shuffle"


class OracleSeverity(StrEnum):
    WARNING = "warning"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: str
    statement: str
    discriminating_observations: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.hypothesis_id, "hypothesis_id")
        _bounded_text(self.statement, "hypothesis statement", 4096)
        _canonical_strings(self.discriminating_observations, "discriminating observations")
        if not self.discriminating_observations:
            raise ValueError("hypothesis requires at least one discriminating observation")

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "discriminating_observations": list(self.discriminating_observations),
        }


@dataclass(frozen=True, slots=True)
class ExperimentReference:
    experiment_id: str
    revision: int

    def __post_init__(self) -> None:
        validate_identifier(self.experiment_id, "experiment_id")
        _positive_integer(self.revision, "experiment revision", maximum=1_000_000)

    def as_dict(self) -> dict[str, object]:
        return {"experiment_id": self.experiment_id, "revision": self.revision}


@dataclass(frozen=True, slots=True)
class ResearchCase:
    case_id: str
    revision: int
    title: str
    owner: str
    created_at_utc: str
    target_profile: str
    coverage_domains: tuple[str, ...]
    question: str
    hypotheses: tuple[Hypothesis, ...]
    state: CaseState
    blocked_reason: str | None = None
    claim_ids: tuple[str, ...] = ()
    contradiction_groups: tuple[str, ...] = ()
    simulator_bindings: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    required_fingerprint_sections: tuple[SectionName, ...] = ()
    required_capture_channels: tuple[str, ...] = ()
    experiments: tuple[ExperimentReference, ...] = ()
    run_manifest_ids: tuple[str, ...] = ()
    conclusion: str | None = None
    reviewer: str | None = None
    limitations: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    follow_up_case_ids: tuple[str, ...] = ()
    schema_version: int = RESEARCH_CASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_CASE_SCHEMA_VERSION:
            raise ValueError("unsupported research case schema version")
        validate_identifier(self.case_id, "case_id")
        _positive_integer(self.revision, "case revision", maximum=1_000_000)
        _bounded_text(self.title, "case title", 512)
        validate_identifier(self.owner, "case owner")
        _timestamp(self.created_at_utc, "created_at_utc")
        validate_identifier(self.target_profile, "target_profile")
        _canonical_strings(self.coverage_domains, "coverage_domains")
        if not self.coverage_domains:
            raise ValueError("research case requires at least one coverage domain")
        _bounded_text(self.question, "case question", 4096)
        if not self.hypotheses or len(self.hypotheses) < 2:
            raise ValueError("research case requires at least two hypotheses")
        hypothesis_ids = tuple(item.hypothesis_id for item in self.hypotheses)
        if hypothesis_ids != tuple(sorted(hypothesis_ids)) or len(hypothesis_ids) != len(
            set(hypothesis_ids)
        ):
            raise ValueError("hypotheses must use unique canonical IDs")
        if not isinstance(self.state, CaseState):
            raise ValueError("case state must be CaseState")
        if self.blocked_reason is not None:
            _bounded_text(self.blocked_reason, "blocked_reason", 4096)
        for values, name in (
            (self.claim_ids, "claim_ids"),
            (self.contradiction_groups, "contradiction_groups"),
            (self.simulator_bindings, "simulator_bindings"),
            (self.gap_ids, "gap_ids"),
            (self.required_capture_channels, "required_capture_channels"),
            (self.run_manifest_ids, "run_manifest_ids"),
            (self.limitations, "limitations"),
            (self.invalidation_conditions, "invalidation_conditions"),
            (self.follow_up_case_ids, "follow_up_case_ids"),
        ):
            _canonical_strings(values, name)
        section_values = tuple(section.value for section in self.required_fingerprint_sections)
        if section_values != tuple(sorted(section_values)) or len(section_values) != len(
            set(section_values)
        ):
            raise ValueError("required fingerprint sections must use canonical ordering")
        experiment_keys = tuple((item.experiment_id, item.revision) for item in self.experiments)
        if experiment_keys != tuple(sorted(experiment_keys)) or len(experiment_keys) != len(
            set(experiment_keys)
        ):
            raise ValueError("experiment references must use unique canonical ordering")
        for manifest_id in self.run_manifest_ids:
            parse_artifact_id(manifest_id, "run manifest ID")
        if self.conclusion is not None:
            _bounded_text(self.conclusion, "conclusion", 16_384)
        if self.reviewer is not None:
            validate_identifier(self.reviewer, "reviewer")
        if self.state in (CaseState.REVIEWED, CaseState.CLOSED) and (
            self.conclusion is None or self.reviewer is None
        ):
            raise ValueError("reviewed and closed cases require conclusion and reviewer")
        if self.state is CaseState.CLOSED and not self.invalidation_conditions:
            raise ValueError("closed case requires invalidation conditions")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "revision": self.revision,
            "title": self.title,
            "owner": self.owner,
            "created_at_utc": self.created_at_utc,
            "target_profile": self.target_profile,
            "coverage_domains": list(self.coverage_domains),
            "question": self.question,
            "hypotheses": [item.as_dict() for item in self.hypotheses],
            "state": self.state.value,
            "blocked_reason": self.blocked_reason,
            "claim_ids": list(self.claim_ids),
            "contradiction_groups": list(self.contradiction_groups),
            "simulator_bindings": list(self.simulator_bindings),
            "gap_ids": list(self.gap_ids),
            "required_fingerprint_sections": [
                item.value for item in self.required_fingerprint_sections
            ],
            "required_capture_channels": list(self.required_capture_channels),
            "experiments": [item.as_dict() for item in self.experiments],
            "run_manifest_ids": list(self.run_manifest_ids),
            "conclusion": self.conclusion,
            "reviewer": self.reviewer,
            "limitations": list(self.limitations),
            "invalidation_conditions": list(self.invalidation_conditions),
            "follow_up_case_ids": list(self.follow_up_case_ids),
        }


@dataclass(frozen=True, slots=True)
class ExperimentVariable:
    name: str
    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.name, "variable name")
        if not self.values or len(self.values) > 10_000:
            raise ValueError("experiment variable requires 1-10000 values")
        for value in self.values:
            validate_finite_json(value)
        if len({canonical_json_sha256(value) for value in self.values}) != len(self.values):
            raise ValueError("experiment variable values must be unique")

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "values": list(self.values)}


_STEP_FIELDS: dict[StepKind, frozenset[str]] = {
    StepKind.ASSERT_PRECONDITION: frozenset({"predicate", "expected"}),
    StepKind.CAPTURE_MARKER: frozenset({"marker"}),
    StepKind.SEMANTIC_DECISION: frozenset({"action_key", "binding"}),
    StepKind.WAIT_FOR_OBSERVATION: frozenset({"field", "operator", "expected", "timeout_seconds"}),
    StepKind.WAIT_DURATION: frozenset({"duration_seconds", "clock"}),
    StepKind.REPEAT: frozenset({"start_sequence", "end_sequence", "count"}),
    StepKind.BRANCH_ON_OBSERVATION: frozenset(
        {"field", "operator", "expected", "true_sequence", "false_sequence"}
    ),
    StepKind.RECORD_ANNOTATION: frozenset({"text"}),
    StepKind.STOP: frozenset({"reason"}),
}


@dataclass(frozen=True, slots=True)
class ExperimentStep:
    sequence: int
    kind: StepKind
    parameters: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        _positive_integer(self.sequence, "step sequence", maximum=100_000)
        if not isinstance(self.kind, StepKind):
            raise ValueError("step kind must be StepKind")
        names = tuple(name for name, _ in self.parameters)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise ValueError("step parameters must use unique canonical keys")
        if set(names) != _STEP_FIELDS[self.kind]:
            raise ValueError(f"{self.kind.value} step parameters are not exact")
        for _name, value in self.parameters:
            validate_finite_json(value)
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        values = dict(self.parameters)
        if self.kind is StepKind.SEMANTIC_DECISION:
            validate_identifier(values["action_key"], "action_key")
            if not isinstance(values["binding"], dict):
                raise ValueError("semantic decision binding must be an object")
        elif self.kind is StepKind.WAIT_DURATION:
            _positive_number(values["duration_seconds"], "duration_seconds", 86_400)
            if values["clock"] not in ("wall", "virtual"):
                raise ValueError("wait clock must be wall or virtual")
        elif self.kind is StepKind.WAIT_FOR_OBSERVATION:
            _positive_number(values["timeout_seconds"], "timeout_seconds", 86_400)
        elif self.kind is StepKind.REPEAT:
            for field in ("start_sequence", "end_sequence", "count"):
                _positive_integer(values[field], field, maximum=10_000)
            if values["start_sequence"] > values["end_sequence"]:
                raise ValueError("repeat start_sequence must not exceed end_sequence")
        elif self.kind is StepKind.BRANCH_ON_OBSERVATION:
            for field in ("true_sequence", "false_sequence"):
                _positive_integer(values[field], field, maximum=100_000)

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "parameters": {name: value for name, value in self.parameters},
        }


@dataclass(frozen=True, slots=True)
class CapturePolicy:
    required_channels: tuple[str, ...]
    optional_channels: tuple[str, ...] = ()
    pre_window_ms: int = 0
    post_window_ms: int = 0

    def __post_init__(self) -> None:
        _canonical_strings(self.required_channels, "required capture channels")
        _canonical_strings(self.optional_channels, "optional capture channels")
        if set(self.required_channels) & set(self.optional_channels):
            raise ValueError("required and optional capture channels must not overlap")
        for value, name in (
            (self.pre_window_ms, "pre_window_ms"),
            (self.post_window_ms, "post_window_ms"),
        ):
            _non_negative_integer(value, name, maximum=3_600_000)

    def as_dict(self) -> dict[str, object]:
        return {
            "required_channels": list(self.required_channels),
            "optional_channels": list(self.optional_channels),
            "pre_window_ms": self.pre_window_ms,
            "post_window_ms": self.post_window_ms,
        }


@dataclass(frozen=True, slots=True)
class RepetitionPolicy:
    repetitions: int
    seeds: tuple[int, ...]
    order: VariableOrder = VariableOrder.CANONICAL
    ordering_seed: int = 0

    def __post_init__(self) -> None:
        _positive_integer(self.repetitions, "repetitions", maximum=100_000)
        if not self.seeds or len(self.seeds) > 100_000:
            raise ValueError("repetition policy requires 1-100000 seeds")
        for seed in self.seeds:
            _non_negative_integer(seed, "seed", maximum=0xFFFFFFFFFFFFFFFF)
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("repetition seeds must be unique")
        if not isinstance(self.order, VariableOrder):
            raise ValueError("variable order must be VariableOrder")
        _non_negative_integer(self.ordering_seed, "ordering_seed", maximum=0xFFFFFFFFFFFFFFFF)

    def as_dict(self) -> dict[str, object]:
        return {
            "repetitions": self.repetitions,
            "seeds": list(self.seeds),
            "order": self.order.value,
            "ordering_seed": self.ordering_seed,
        }


@dataclass(frozen=True, slots=True)
class OracleRule:
    field: str
    operator: str
    expected: Any
    absolute_tolerance: float
    severity: OracleSeverity

    def __post_init__(self) -> None:
        _bounded_text(self.field, "oracle field", 512)
        if self.operator not in ("eq", "ne", "lt", "le", "gt", "ge", "contains"):
            raise ValueError("unsupported oracle operator")
        validate_finite_json(self.expected)
        _non_negative_number(self.absolute_tolerance, "absolute_tolerance", 1e18)
        if not isinstance(self.severity, OracleSeverity):
            raise ValueError("oracle severity must be OracleSeverity")

    def as_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "operator": self.operator,
            "expected": self.expected,
            "absolute_tolerance": self.absolute_tolerance,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    maximum_duration_seconds: float
    maximum_input_count: int
    maximum_input_rate_per_second: float
    maximum_resource_loss: float
    stop_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        _positive_number(self.maximum_duration_seconds, "maximum_duration_seconds", 86_400)
        _non_negative_integer(self.maximum_input_count, "maximum_input_count", maximum=1_000_000)
        _non_negative_number(
            self.maximum_input_rate_per_second,
            "maximum_input_rate_per_second",
            10_000,
        )
        _non_negative_number(self.maximum_resource_loss, "maximum_resource_loss", 1e18)
        _canonical_strings(self.stop_conditions, "stop_conditions")
        if not self.stop_conditions:
            raise ValueError("safety policy requires at least one stop condition")

    def as_dict(self) -> dict[str, object]:
        return {
            "maximum_duration_seconds": self.maximum_duration_seconds,
            "maximum_input_count": self.maximum_input_count,
            "maximum_input_rate_per_second": self.maximum_input_rate_per_second,
            "maximum_resource_loss": self.maximum_resource_loss,
            "stop_conditions": list(self.stop_conditions),
        }


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    experiment_id: str
    revision: int
    question_type: str
    hypothesis_ids: tuple[str, ...]
    preconditions: tuple[tuple[str, Any], ...]
    variables: tuple[ExperimentVariable, ...]
    steps: tuple[ExperimentStep, ...]
    capture: CapturePolicy
    repetition: RepetitionPolicy
    oracle: tuple[OracleRule, ...]
    safety: SafetyPolicy
    outputs: tuple[str, ...]
    schema_version: int = EXPERIMENT_DEFINITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXPERIMENT_DEFINITION_SCHEMA_VERSION:
            raise ValueError("unsupported experiment definition schema version")
        validate_identifier(self.experiment_id, "experiment_id")
        _positive_integer(self.revision, "experiment revision", maximum=1_000_000)
        validate_identifier(self.question_type, "question_type")
        _canonical_strings(self.hypothesis_ids, "hypothesis_ids")
        if len(self.hypothesis_ids) < 2:
            raise ValueError("experiment requires at least two hypotheses")
        _canonical_items(self.preconditions, "preconditions")
        variable_names = tuple(item.name for item in self.variables)
        if variable_names != tuple(sorted(variable_names)) or len(variable_names) != len(
            set(variable_names)
        ):
            raise ValueError("experiment variables must use unique canonical names")
        if not self.steps:
            raise ValueError("experiment requires at least one step")
        sequences = tuple(item.sequence for item in self.steps)
        if sequences != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("experiment steps must use contiguous one-based sequence")
        if len(self.steps) > 10_000:
            raise ValueError("experiment contains too many steps")
        for step in self.steps:
            if step.kind is StepKind.REPEAT:
                values = dict(step.parameters)
                if values["end_sequence"] >= step.sequence:
                    raise ValueError("repeat may reference only earlier steps")
            if step.kind is StepKind.BRANCH_ON_OBSERVATION:
                values = dict(step.parameters)
                for target in (values["true_sequence"], values["false_sequence"]):
                    if target <= step.sequence or target > len(self.steps):
                        raise ValueError("branch targets must be later valid steps")
        if not isinstance(self.capture, CapturePolicy):
            raise ValueError("capture must be CapturePolicy")
        if not isinstance(self.repetition, RepetitionPolicy):
            raise ValueError("repetition must be RepetitionPolicy")
        _canonical_strings(self.outputs, "outputs")
        if not self.outputs:
            raise ValueError("experiment requires at least one output")

    @property
    def definition_id(self) -> str:
        return f"sha256:{canonical_json_sha256(self.as_dict())}"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "revision": self.revision,
            "question_type": self.question_type,
            "hypothesis_ids": list(self.hypothesis_ids),
            "preconditions": {name: value for name, value in self.preconditions},
            "variables": [item.as_dict() for item in self.variables],
            "steps": [item.as_dict() for item in self.steps],
            "capture": self.capture.as_dict(),
            "repetition": self.repetition.as_dict(),
            "oracle": [item.as_dict() for item in self.oracle],
            "safety": self.safety.as_dict(),
            "outputs": list(self.outputs),
        }


@dataclass(frozen=True, slots=True)
class ExpandedRun:
    run_id: str
    plan_id: str
    experiment_id: str
    experiment_revision: int
    repetition: int
    seed: int
    variables: tuple[tuple[str, Any], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "experiment_id": self.experiment_id,
            "experiment_revision": self.experiment_revision,
            "repetition": self.repetition,
            "seed": self.seed,
            "variables": {name: value for name, value in self.variables},
        }


def expand_experiment(
    definition: ExperimentDefinition,
    *,
    execution_nonce: str,
) -> tuple[ExpandedRun, ...]:
    validate_identifier(execution_nonce, "execution_nonce")
    plan_id = (
        "plan-"
        + canonical_json_sha256(
            {
                "definition_id": definition.definition_id,
                "execution_nonce": execution_nonce,
            }
        )[:32]
    )
    names = tuple(item.name for item in definition.variables)
    combinations = list(product(*(item.values for item in definition.variables)))
    if not combinations:
        combinations = [()]
    if definition.repetition.order is VariableOrder.SEEDED_SHUFFLE:
        import random

        random.Random(definition.repetition.ordering_seed).shuffle(combinations)
    runs: list[ExpandedRun] = []
    for combination in combinations:
        variables = tuple(zip(names, combination, strict=True))
        for repetition in range(1, definition.repetition.repetitions + 1):
            seed = definition.repetition.seeds[(repetition - 1) % len(definition.repetition.seeds)]
            run_id = (
                "run-"
                + canonical_json_sha256(
                    {
                        "plan_id": plan_id,
                        "variables": dict(variables),
                        "repetition": repetition,
                        "seed": seed,
                    }
                )[:32]
            )
            runs.append(
                ExpandedRun(
                    run_id=run_id,
                    plan_id=plan_id,
                    experiment_id=definition.experiment_id,
                    experiment_revision=definition.revision,
                    repetition=repetition,
                    seed=seed,
                    variables=variables,
                )
            )
    if len(runs) > 1_000_000:
        raise ValueError("expanded experiment exceeds one million runs")
    return tuple(runs)


def review_case(
    case: ResearchCase,
    *,
    reviewer: str,
    conclusion: str,
    limitations: tuple[str, ...],
    invalidation_conditions: tuple[str, ...],
    close: bool,
) -> ResearchCase:
    if case.state not in (CaseState.EVIDENCE_COMPLETE, CaseState.REVIEWED):
        raise ValueError("only evidence-complete or reviewed cases can be reviewed")
    return replace(
        case,
        revision=case.revision + 1,
        state=CaseState.CLOSED if close else CaseState.REVIEWED,
        reviewer=reviewer,
        conclusion=conclusion,
        limitations=tuple(sorted(set(limitations))),
        invalidation_conditions=tuple(sorted(set(invalidation_conditions))),
    )


def _bounded_text(value: object, field_name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or "\0" in value or len(value) > maximum:
        raise ValueError(f"{field_name} must be bounded non-empty text")
    return value


def _canonical_strings(values: tuple[str, ...], field_name: str) -> None:
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{field_name} must use unique canonical ordering")
    for value in values:
        _bounded_text(value, field_name, 4096)


def _canonical_items(values: tuple[tuple[str, Any], ...], field_name: str) -> None:
    names = tuple(name for name, _ in values)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError(f"{field_name} must use unique canonical keys")
    for name, value in values:
        validate_identifier(name, field_name)
        validate_finite_json(value)


def _positive_integer(value: object, field_name: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{field_name} must be in [1, {maximum}]")
    return value


def _non_negative_integer(value: object, field_name: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(f"{field_name} must be in [0, {maximum}]")
    return value


def _positive_number(value: object, field_name: str, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or not 0 < value <= maximum
    ):
        raise ValueError(f"{field_name} must be finite in (0, {maximum}]")
    return float(value)


def _non_negative_number(value: object, field_name: str, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or not 0 <= value <= maximum
    ):
        raise ValueError(f"{field_name} must be finite in [0, {maximum}]")
    return float(value)


def _timestamp(value: object, field_name: str) -> None:
    from datetime import datetime

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be UTC")


__all__ = [
    "EXPERIMENT_DEFINITION_SCHEMA_VERSION",
    "RESEARCH_CASE_SCHEMA_VERSION",
    "CapturePolicy",
    "CaseError",
    "CaseState",
    "ExpandedRun",
    "ExperimentDefinition",
    "ExperimentReference",
    "ExperimentStep",
    "ExperimentVariable",
    "Hypothesis",
    "OracleRule",
    "OracleSeverity",
    "RepetitionPolicy",
    "ResearchCase",
    "SafetyPolicy",
    "StepKind",
    "VariableOrder",
    "expand_experiment",
    "review_case",
]
