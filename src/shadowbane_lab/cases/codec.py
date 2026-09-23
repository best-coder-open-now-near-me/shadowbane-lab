"""Strict codecs and create-only persistence for research contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shadowbane_lab.integrity import create_only_json, load_strict_json

from .model import (
    CapturePolicy,
    CaseError,
    CaseState,
    ExperimentDefinition,
    ExperimentReference,
    ExperimentStep,
    ExperimentVariable,
    Hypothesis,
    OracleRule,
    OracleSeverity,
    RepetitionPolicy,
    ResearchCase,
    SafetyPolicy,
    StepKind,
    VariableOrder,
)


def save_case(path: str | Path, case: ResearchCase) -> None:
    _save(path, case.as_dict(), "research case")


def save_experiment(path: str | Path, definition: ExperimentDefinition) -> None:
    _save(path, definition.as_dict(), "experiment definition")


def load_case(path: str | Path) -> ResearchCase:
    return parse_case(_load(path, "research case"))


def load_experiment(path: str | Path) -> ExperimentDefinition:
    return parse_experiment(_load(path, "experiment definition"))


def parse_case(payload: object) -> ResearchCase:
    value = _object(payload, "research case")
    _exact(
        value,
        {
            "schema_version",
            "case_id",
            "revision",
            "title",
            "owner",
            "created_at_utc",
            "target_profile",
            "coverage_domains",
            "question",
            "hypotheses",
            "state",
            "blocked_reason",
            "claim_ids",
            "contradiction_groups",
            "simulator_bindings",
            "gap_ids",
            "required_fingerprint_sections",
            "required_capture_channels",
            "experiments",
            "run_manifest_ids",
            "conclusion",
            "reviewer",
            "limitations",
            "invalidation_conditions",
            "follow_up_case_ids",
        },
        "research case",
    )
    hypotheses: list[Hypothesis] = []
    for item in _list(value["hypotheses"], "hypotheses"):
        entry = _object(item, "hypothesis")
        _exact(entry, {"hypothesis_id", "statement", "discriminating_observations"}, "hypothesis")
        hypotheses.append(
            Hypothesis(
                hypothesis_id=entry["hypothesis_id"],  # type: ignore[arg-type]
                statement=entry["statement"],  # type: ignore[arg-type]
                discriminating_observations=_strings(
                    entry["discriminating_observations"], "discriminating observations"
                ),
            )
        )
    experiments: list[ExperimentReference] = []
    for item in _list(value["experiments"], "experiments"):
        entry = _object(item, "experiment reference")
        _exact(entry, {"experiment_id", "revision"}, "experiment reference")
        experiments.append(
            ExperimentReference(
                experiment_id=entry["experiment_id"],  # type: ignore[arg-type]
                revision=entry["revision"],  # type: ignore[arg-type]
            )
        )
    try:
        from shadowbane_lab.fingerprints import SectionName

        return ResearchCase(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            case_id=value["case_id"],  # type: ignore[arg-type]
            revision=value["revision"],  # type: ignore[arg-type]
            title=value["title"],  # type: ignore[arg-type]
            owner=value["owner"],  # type: ignore[arg-type]
            created_at_utc=value["created_at_utc"],  # type: ignore[arg-type]
            target_profile=value["target_profile"],  # type: ignore[arg-type]
            coverage_domains=_strings(value["coverage_domains"], "coverage domains"),
            question=value["question"],  # type: ignore[arg-type]
            hypotheses=tuple(hypotheses),
            state=CaseState(value["state"]),  # type: ignore[arg-type]
            blocked_reason=_optional_string(value["blocked_reason"], "blocked reason"),
            claim_ids=_strings(value["claim_ids"], "claim IDs"),
            contradiction_groups=_strings(value["contradiction_groups"], "contradictions"),
            simulator_bindings=_strings(value["simulator_bindings"], "simulator bindings"),
            gap_ids=_strings(value["gap_ids"], "gap IDs"),
            required_fingerprint_sections=tuple(
                SectionName(item)
                for item in _strings(value["required_fingerprint_sections"], "fingerprint sections")
            ),
            required_capture_channels=_strings(value["required_capture_channels"], "channels"),
            experiments=tuple(experiments),
            run_manifest_ids=_strings(value["run_manifest_ids"], "run manifest IDs"),
            conclusion=_optional_string(value["conclusion"], "conclusion"),
            reviewer=_optional_string(value["reviewer"], "reviewer"),
            limitations=_strings(value["limitations"], "limitations"),
            invalidation_conditions=_strings(
                value["invalidation_conditions"], "invalidation conditions"
            ),
            follow_up_case_ids=_strings(value["follow_up_case_ids"], "follow-up case IDs"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CaseError(f"invalid research case: {exc}") from exc


def parse_experiment(payload: object) -> ExperimentDefinition:
    value = _object(payload, "experiment definition")
    _exact(
        value,
        {
            "schema_version",
            "experiment_id",
            "revision",
            "question_type",
            "hypothesis_ids",
            "preconditions",
            "variables",
            "steps",
            "capture",
            "repetition",
            "oracle",
            "safety",
            "outputs",
        },
        "experiment definition",
    )
    variables: list[ExperimentVariable] = []
    for item in _list(value["variables"], "variables"):
        entry = _object(item, "experiment variable")
        _exact(entry, {"name", "values"}, "experiment variable")
        variables.append(
            ExperimentVariable(
                name=entry["name"],  # type: ignore[arg-type]
                values=tuple(_list(entry["values"], "variable values")),
            )
        )
    steps: list[ExperimentStep] = []
    for item in _list(value["steps"], "steps"):
        entry = _object(item, "experiment step")
        _exact(entry, {"sequence", "kind", "parameters"}, "experiment step")
        parameters = _object(entry["parameters"], "step parameters")
        steps.append(
            ExperimentStep(
                sequence=entry["sequence"],  # type: ignore[arg-type]
                kind=StepKind(entry["kind"]),  # type: ignore[arg-type]
                parameters=tuple(sorted(parameters.items())),
            )
        )
    capture_value = _object(value["capture"], "capture policy")
    _exact(
        capture_value,
        {"required_channels", "optional_channels", "pre_window_ms", "post_window_ms"},
        "capture policy",
    )
    repetition_value = _object(value["repetition"], "repetition policy")
    _exact(
        repetition_value,
        {"repetitions", "seeds", "order", "ordering_seed"},
        "repetition policy",
    )
    oracle: list[OracleRule] = []
    for item in _list(value["oracle"], "oracle"):
        entry = _object(item, "oracle rule")
        _exact(
            entry,
            {"field", "operator", "expected", "absolute_tolerance", "severity"},
            "oracle rule",
        )
        oracle.append(
            OracleRule(
                field=entry["field"],  # type: ignore[arg-type]
                operator=entry["operator"],  # type: ignore[arg-type]
                expected=entry["expected"],
                absolute_tolerance=entry["absolute_tolerance"],  # type: ignore[arg-type]
                severity=OracleSeverity(entry["severity"]),  # type: ignore[arg-type]
            )
        )
    safety_value = _object(value["safety"], "safety policy")
    _exact(
        safety_value,
        {
            "maximum_duration_seconds",
            "maximum_input_count",
            "maximum_input_rate_per_second",
            "maximum_resource_loss",
            "stop_conditions",
        },
        "safety policy",
    )
    try:
        return ExperimentDefinition(
            schema_version=value["schema_version"],  # type: ignore[arg-type]
            experiment_id=value["experiment_id"],  # type: ignore[arg-type]
            revision=value["revision"],  # type: ignore[arg-type]
            question_type=value["question_type"],  # type: ignore[arg-type]
            hypothesis_ids=_strings(value["hypothesis_ids"], "hypothesis IDs"),
            preconditions=tuple(sorted(_object(value["preconditions"], "preconditions").items())),
            variables=tuple(variables),
            steps=tuple(steps),
            capture=CapturePolicy(
                required_channels=_strings(capture_value["required_channels"], "required channels"),
                optional_channels=_strings(capture_value["optional_channels"], "optional channels"),
                pre_window_ms=capture_value["pre_window_ms"],  # type: ignore[arg-type]
                post_window_ms=capture_value["post_window_ms"],  # type: ignore[arg-type]
            ),
            repetition=RepetitionPolicy(
                repetitions=repetition_value["repetitions"],  # type: ignore[arg-type]
                seeds=tuple(_integers(repetition_value["seeds"], "seeds")),
                order=VariableOrder(repetition_value["order"]),  # type: ignore[arg-type]
                ordering_seed=repetition_value["ordering_seed"],  # type: ignore[arg-type]
            ),
            oracle=tuple(oracle),
            safety=SafetyPolicy(
                maximum_duration_seconds=safety_value["maximum_duration_seconds"],  # type: ignore[arg-type]
                maximum_input_count=safety_value["maximum_input_count"],  # type: ignore[arg-type]
                maximum_input_rate_per_second=safety_value["maximum_input_rate_per_second"],  # type: ignore[arg-type]
                maximum_resource_loss=safety_value["maximum_resource_loss"],  # type: ignore[arg-type]
                stop_conditions=_strings(safety_value["stop_conditions"], "stop conditions"),
            ),
            outputs=_strings(value["outputs"], "outputs"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CaseError(f"invalid experiment definition: {exc}") from exc


def _save(path: str | Path, payload: object, name: str) -> None:
    try:
        create_only_json(Path(path), payload, make_parents=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CaseError(f"could not save {name}: {exc}") from exc


def _load(path: str | Path, name: str) -> object:
    try:
        return load_strict_json(Path(path))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise CaseError(f"could not load {name}: {exc}") from exc


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CaseError(f"{name} must be an object")
    return value


def _list(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise CaseError(f"{name} must be an array")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    items = _list(value, name)
    if not all(isinstance(item, str) for item in items):
        raise CaseError(f"{name} must contain only strings")
    return tuple(items)


def _integers(value: object, name: str) -> tuple[int, ...]:
    items = _list(value, name)
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in items):
        raise CaseError(f"{name} must contain only integers")
    return tuple(items)


def _optional_string(value: object, name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise CaseError(f"{name} must be text or null")
    return value


def _exact(value: dict[str, Any], fields: set[str], name: str) -> None:
    missing = fields - set(value)
    extra = set(value) - fields
    if missing or extra:
        raise CaseError(
            f"{name} fields are not exact; missing={sorted(missing)}, extra={sorted(extra)}"
        )


__all__ = [
    "load_case",
    "load_experiment",
    "parse_case",
    "parse_experiment",
    "save_case",
    "save_experiment",
]
