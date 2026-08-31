"""Versioned contracts for produced-build runtime consistency evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

RUNTIME_SUITE_SCHEMA_VERSION = 1
RUNTIME_RESULT_SCHEMA_VERSION = 1
RUNTIME_CAPTURE_SCHEMA_VERSION = 1
RUNTIME_BASELINE_SCHEMA_VERSION = 1
RUNTIME_REPORT_SCHEMA_VERSION = 1


class RuntimeConsistencyError(RuntimeError):
    """Raised when runtime consistency evidence cannot be trusted."""


class Severity(StrEnum):
    WARNING = "warning"
    FAILURE = "failure"


class MetricDirection(StrEnum):
    TWO_SIDED = "two_sided"
    INCREASE = "increase"
    DECREASE = "decrease"


class SlotScope(StrEnum):
    FIRST = "first"
    ALL = "all"


class GateStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


def validate_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError(f"{field_name} must be non-empty text without NUL")
    if len(value) > 256:
        raise ValueError(f"{field_name} must be at most 256 characters")
    return value


def validate_sha256(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def validate_json(value: object, field_name: str = "value") -> None:
    try:
        json.dumps(value, allow_nan=False, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite JSON: {exc}") from exc


def canonical_sha256(value: object) -> str:
    validate_json(value)
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _finite_non_negative(value: object, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{field_name} must be finite and non-negative")
    return float(value)


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _string_map(values: tuple[tuple[str, str], ...], field_name: str) -> None:
    names = tuple(name for name, _ in values)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError(f"{field_name} must use unique canonical sorted names")
    for name, value in values:
        validate_identifier(name, f"{field_name} name")
        validate_identifier(value, f"{field_name}.{name}")


def _number_map(values: tuple[tuple[str, float], ...], field_name: str) -> None:
    names = tuple(name for name, _ in values)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError(f"{field_name} must use unique canonical sorted names")
    for name, value in values:
        validate_identifier(name, f"{field_name} name")
        _finite_non_negative(value, f"{field_name}.{name}")


def _counter_map(values: tuple[tuple[str, int], ...], field_name: str) -> None:
    names = tuple(name for name, _ in values)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise ValueError(f"{field_name} must use unique canonical sorted names")
    for name, value in values:
        validate_identifier(name, f"{field_name} name")
        _non_negative_integer(value, f"{field_name}.{name}")


@dataclass(frozen=True, slots=True)
class MetricPolicy:
    direction: MetricDirection = MetricDirection.TWO_SIDED
    absolute_tolerance: float = 0.0
    relative_tolerance: float = 0.0
    mad_multiplier: float = 6.0
    severity: Severity = Severity.FAILURE

    def __post_init__(self) -> None:
        if not isinstance(self.direction, MetricDirection):
            raise ValueError("metric direction must be a MetricDirection")
        if not isinstance(self.severity, Severity):
            raise ValueError("metric severity must be a Severity")
        for name in ("absolute_tolerance", "relative_tolerance", "mad_multiplier"):
            _finite_non_negative(getattr(self, name), name)

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction.value,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "mad_multiplier": self.mad_multiplier,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class CounterPolicy:
    maximum_increase: int = 0
    maximum_value: int | None = None
    severity: Severity = Severity.FAILURE

    def __post_init__(self) -> None:
        _non_negative_integer(self.maximum_increase, "maximum_increase")
        if self.maximum_value is not None:
            _non_negative_integer(self.maximum_value, "maximum_value")
        if not isinstance(self.severity, Severity):
            raise ValueError("counter severity must be a Severity")

    def as_dict(self) -> dict[str, object]:
        return {
            "maximum_increase": self.maximum_increase,
            "maximum_value": self.maximum_value,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class RuntimeScenario:
    scenario_id: str
    command: tuple[str, ...]
    timeout_seconds: float
    slot_scope: SlotScope
    metric_policies: tuple[tuple[str, MetricPolicy], ...]
    counter_policies: tuple[tuple[str, CounterPolicy], ...]

    def __post_init__(self) -> None:
        validate_identifier(self.scenario_id, "scenario_id")
        if not self.command or any(
            not isinstance(item, str) or not item or "\0" in item for item in self.command
        ):
            raise ValueError("scenario command must contain non-empty arguments without NUL")
        if len(self.command) > 128:
            raise ValueError("scenario command contains too many arguments")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 86_400
        ):
            raise ValueError("scenario timeout_seconds must be in (0, 86400]")
        if not isinstance(self.slot_scope, SlotScope):
            raise ValueError("scenario slot_scope must be a SlotScope")
        metric_names = tuple(name for name, _ in self.metric_policies)
        counter_names = tuple(name for name, _ in self.counter_policies)
        if metric_names != tuple(sorted(metric_names)) or len(metric_names) != len(
            set(metric_names)
        ):
            raise ValueError("scenario metric policies must use unique canonical sorted names")
        if counter_names != tuple(sorted(counter_names)) or len(counter_names) != len(
            set(counter_names)
        ):
            raise ValueError("scenario counter policies must use unique canonical sorted names")
        if "pipeline.wall_duration_ms" not in metric_names:
            raise ValueError("scenario metric policies must declare pipeline.wall_duration_ms")
        for name, policy in self.metric_policies:
            validate_identifier(name, "metric policy name")
            if not isinstance(policy, MetricPolicy):
                raise ValueError("metric policy values must be MetricPolicy objects")
        for name, policy in self.counter_policies:
            validate_identifier(name, "counter policy name")
            if not isinstance(policy, CounterPolicy):
                raise ValueError("counter policy values must be CounterPolicy objects")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "command": list(self.command),
            "timeout_seconds": self.timeout_seconds,
            "slot_scope": self.slot_scope.value,
            "metric_policies": {name: policy.as_dict() for name, policy in self.metric_policies},
            "counter_policies": {name: policy.as_dict() for name, policy in self.counter_policies},
        }


@dataclass(frozen=True, slots=True)
class RuntimeSuite:
    suite_id: str
    suite_revision: str
    environment_id: str
    minimum_repetitions: int
    scenarios: tuple[RuntimeScenario, ...]
    schema_version: int = RUNTIME_SUITE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SUITE_SCHEMA_VERSION:
            raise ValueError("unsupported runtime suite schema version")
        validate_identifier(self.suite_id, "suite_id")
        validate_identifier(self.suite_revision, "suite_revision")
        validate_identifier(self.environment_id, "environment_id")
        if (
            isinstance(self.minimum_repetitions, bool)
            or not isinstance(self.minimum_repetitions, int)
            or not 1 <= self.minimum_repetitions <= 10_000
        ):
            raise ValueError("minimum_repetitions must be in [1, 10000]")
        if not self.scenarios or any(
            not isinstance(item, RuntimeScenario) for item in self.scenarios
        ):
            raise ValueError("runtime suite must contain scenarios")
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        if scenario_ids != tuple(sorted(scenario_ids)) or len(scenario_ids) != len(
            set(scenario_ids)
        ):
            raise ValueError("runtime suite scenarios must use unique canonical sorted IDs")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "suite_revision": self.suite_revision,
            "environment_id": self.environment_id,
            "minimum_repetitions": self.minimum_repetitions,
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
        }

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class DeploymentSlotIdentity:
    client_id: str
    package_working_tree_sha256: str
    executable_sha256: str
    extension_sha256: str

    def __post_init__(self) -> None:
        validate_identifier(self.client_id, "client_id")
        for name in (
            "package_working_tree_sha256",
            "executable_sha256",
            "extension_sha256",
        ):
            validate_sha256(getattr(self, name), name)

    def as_dict(self) -> dict[str, object]:
        return {
            "client_id": self.client_id,
            "package_working_tree_sha256": self.package_working_tree_sha256,
            "executable_sha256": self.executable_sha256,
            "extension_sha256": self.extension_sha256,
        }


@dataclass(frozen=True, slots=True)
class DeploymentIdentity:
    deployment_id: str
    deployment_kind: str
    baseline_tree_sha256: str
    repository_revision: str
    patch_id: str
    patch_manifest_sha256: str
    resolution: str
    slots: tuple[DeploymentSlotIdentity, ...]

    def __post_init__(self) -> None:
        for name in ("deployment_id", "deployment_kind", "repository_revision", "patch_id"):
            validate_identifier(getattr(self, name), name)
        validate_sha256(self.baseline_tree_sha256, "baseline_tree_sha256")
        validate_sha256(self.patch_manifest_sha256, "patch_manifest_sha256")
        validate_identifier(self.resolution, "resolution")
        if not self.slots or any(
            not isinstance(item, DeploymentSlotIdentity) for item in self.slots
        ):
            raise ValueError("deployment identity must contain slots")
        ids = tuple(item.client_id for item in self.slots)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("deployment slots must use unique canonical sorted client IDs")

    def as_dict(self) -> dict[str, object]:
        return {
            "deployment_id": self.deployment_id,
            "deployment_kind": self.deployment_kind,
            "baseline_tree_sha256": self.baseline_tree_sha256,
            "repository_revision": self.repository_revision,
            "patch_id": self.patch_id,
            "patch_manifest_sha256": self.patch_manifest_sha256,
            "resolution": self.resolution,
            "slots": [slot.as_dict() for slot in self.slots],
        }

    @property
    def build_fingerprint(self) -> str:
        return canonical_sha256(
            {
                "baseline_tree_sha256": self.baseline_tree_sha256,
                "repository_revision": self.repository_revision,
                "patch_id": self.patch_id,
                "patch_manifest_sha256": self.patch_manifest_sha256,
                "resolution": self.resolution,
                "slots": [slot.as_dict() for slot in self.slots],
            }
        )


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    passed: bool
    terminal_reason: str
    semantic: object
    metrics: tuple[tuple[str, float], ...]
    counters: tuple[tuple[str, int], ...]
    schema_version: int = RUNTIME_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported runtime scenario result schema version")
        validate_identifier(self.scenario_id, "scenario_id")
        if not isinstance(self.passed, bool):
            raise ValueError("scenario result passed must be boolean")
        validate_identifier(self.terminal_reason, "terminal_reason")
        validate_json(self.semantic, "scenario result semantic")
        _number_map(self.metrics, "scenario result metrics")
        _counter_map(self.counters, "scenario result counters")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "terminal_reason": self.terminal_reason,
            "semantic": self.semantic,
            "metrics": dict(self.metrics),
            "counters": dict(self.counters),
        }


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    scenario_id: str
    client_id: str
    repetition: int
    passed: bool
    terminal_reason: str
    command_exit_code: int | None
    semantic: object | None
    metrics: tuple[tuple[str, float], ...]
    counters: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        validate_identifier(self.scenario_id, "scenario_id")
        validate_identifier(self.client_id, "client_id")
        _non_negative_integer(self.repetition, "repetition")
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be boolean")
        validate_identifier(self.terminal_reason, "terminal_reason")
        if self.command_exit_code is not None and (
            isinstance(self.command_exit_code, bool) or not isinstance(self.command_exit_code, int)
        ):
            raise ValueError("command_exit_code must be an integer or null")
        if self.semantic is not None:
            validate_json(self.semantic, "semantic")
        _number_map(self.metrics, "metrics")
        _counter_map(self.counters, "counters")
        if self.passed and (self.command_exit_code != 0 or self.semantic is None):
            raise ValueError("passed observations require exit code zero and semantic evidence")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "client_id": self.client_id,
            "repetition": self.repetition,
            "passed": self.passed,
            "terminal_reason": self.terminal_reason,
            "command_exit_code": self.command_exit_code,
            "semantic": self.semantic,
            "semantic_sha256": (None if self.semantic is None else canonical_sha256(self.semantic)),
            "metrics": dict(self.metrics),
            "counters": dict(self.counters),
        }


@dataclass(frozen=True, slots=True)
class RuntimeCapture:
    capture_id: str
    captured_at_utc: str
    suite_id: str
    suite_revision: str
    suite_fingerprint: str
    environment_id: str
    requested_repetitions: int
    deployment: DeploymentIdentity
    host: tuple[tuple[str, str], ...]
    observations: tuple[RuntimeObservation, ...]
    schema_version: int = RUNTIME_CAPTURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_CAPTURE_SCHEMA_VERSION:
            raise ValueError("unsupported runtime capture schema version")
        for name in (
            "capture_id",
            "captured_at_utc",
            "suite_id",
            "suite_revision",
            "environment_id",
        ):
            validate_identifier(getattr(self, name), name)
        validate_sha256(self.suite_fingerprint, "suite_fingerprint")
        if (
            isinstance(self.requested_repetitions, bool)
            or not isinstance(self.requested_repetitions, int)
            or self.requested_repetitions <= 0
        ):
            raise ValueError("requested_repetitions must be positive")
        if not isinstance(self.deployment, DeploymentIdentity):
            raise ValueError("deployment must be a DeploymentIdentity")
        _string_map(self.host, "host")
        if not self.observations or any(
            not isinstance(item, RuntimeObservation) for item in self.observations
        ):
            raise ValueError("runtime capture must contain observations")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "capture_id": self.capture_id,
            "captured_at_utc": self.captured_at_utc,
            "suite_id": self.suite_id,
            "suite_revision": self.suite_revision,
            "suite_fingerprint": self.suite_fingerprint,
            "environment_id": self.environment_id,
            "requested_repetitions": self.requested_repetitions,
            "deployment": self.deployment.as_dict(),
            "build_fingerprint": self.deployment.build_fingerprint,
            "host": dict(self.host),
            "observation_count": len(self.observations),
            "observations": [item.as_dict() for item in self.observations],
        }


@dataclass(frozen=True, slots=True)
class Distribution:
    count: int
    minimum: float
    percentile_05: float
    median: float
    percentile_95: float
    maximum: float
    median_absolute_deviation: float

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count <= 0:
            raise ValueError("distribution count must be positive")
        values = (
            self.minimum,
            self.percentile_05,
            self.median,
            self.percentile_95,
            self.maximum,
            self.median_absolute_deviation,
        )
        for index, value in enumerate(values):
            _finite_non_negative(value, f"distribution value {index}")
        if not (
            self.minimum <= self.percentile_05 <= self.median <= self.percentile_95 <= self.maximum
        ):
            raise ValueError("distribution quantiles must be ordered")

    def as_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "minimum": self.minimum,
            "percentile_05": self.percentile_05,
            "median": self.median,
            "percentile_95": self.percentile_95,
            "maximum": self.maximum,
            "median_absolute_deviation": self.median_absolute_deviation,
        }


@dataclass(frozen=True, slots=True)
class ScenarioBaseline:
    scenario_id: str
    semantic: object
    metric_distributions: tuple[tuple[str, Distribution], ...]
    counter_distributions: tuple[tuple[str, Distribution], ...]

    def __post_init__(self) -> None:
        validate_identifier(self.scenario_id, "scenario_id")
        validate_json(self.semantic, "baseline semantic")
        for values, field_name in (
            (self.metric_distributions, "metric_distributions"),
            (self.counter_distributions, "counter_distributions"),
        ):
            names = tuple(name for name, _ in values)
            if names != tuple(sorted(names)) or len(names) != len(set(names)):
                raise ValueError(f"{field_name} must use canonical unique sorted names")
            for name, distribution in values:
                validate_identifier(name, f"{field_name} name")
                if not isinstance(distribution, Distribution):
                    raise ValueError(f"{field_name} values must be Distribution objects")

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "semantic": self.semantic,
            "semantic_sha256": canonical_sha256(self.semantic),
            "metric_distributions": {
                name: value.as_dict() for name, value in self.metric_distributions
            },
            "counter_distributions": {
                name: value.as_dict() for name, value in self.counter_distributions
            },
        }


@dataclass(frozen=True, slots=True)
class RuntimeBaseline:
    baseline_id: str
    promoted_at_utc: str
    suite: RuntimeSuite
    source_capture_ids: tuple[str, ...]
    accepted_build_fingerprints: tuple[str, ...]
    scenarios: tuple[ScenarioBaseline, ...]
    schema_version: int = RUNTIME_BASELINE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_BASELINE_SCHEMA_VERSION:
            raise ValueError("unsupported runtime baseline schema version")
        validate_identifier(self.baseline_id, "baseline_id")
        validate_identifier(self.promoted_at_utc, "promoted_at_utc")
        if not isinstance(self.suite, RuntimeSuite):
            raise ValueError("baseline suite must be a RuntimeSuite")
        if not self.source_capture_ids:
            raise ValueError("baseline must name source captures")
        for value in self.source_capture_ids:
            validate_identifier(value, "source_capture_id")
        for value in self.accepted_build_fingerprints:
            validate_sha256(value, "accepted_build_fingerprint")
        scenario_ids = tuple(item.scenario_id for item in self.scenarios)
        expected_ids = tuple(item.scenario_id for item in self.suite.scenarios)
        if scenario_ids != expected_ids:
            raise ValueError("baseline scenarios must exactly match its suite")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "baseline_id": self.baseline_id,
            "promoted_at_utc": self.promoted_at_utc,
            "suite": self.suite.as_dict(),
            "suite_fingerprint": self.suite.fingerprint,
            "source_capture_ids": list(self.source_capture_ids),
            "accepted_build_fingerprints": list(self.accepted_build_fingerprints),
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
        }


@dataclass(frozen=True, slots=True)
class Anomaly:
    severity: Severity
    category: str
    scenario_id: str | None
    field: str
    expected: object
    actual: object
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            raise ValueError("anomaly severity must be a Severity")
        validate_identifier(self.category, "anomaly category")
        if self.scenario_id is not None:
            validate_identifier(self.scenario_id, "anomaly scenario_id")
        validate_identifier(self.field, "anomaly field")
        validate_identifier(self.detail, "anomaly detail")
        validate_json(self.expected, "anomaly expected")
        validate_json(self.actual, "anomaly actual")

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "scenario_id": self.scenario_id,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    baseline_id: str
    capture_id: str
    compared_at_utc: str
    build_fingerprint: str
    anomalies: tuple[Anomaly, ...]
    schema_version: int = RUNTIME_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_REPORT_SCHEMA_VERSION:
            raise ValueError("unsupported runtime report schema version")
        for name in ("baseline_id", "capture_id", "compared_at_utc"):
            validate_identifier(getattr(self, name), name)
        validate_sha256(self.build_fingerprint, "build_fingerprint")
        if any(not isinstance(item, Anomaly) for item in self.anomalies):
            raise ValueError("report anomalies must contain Anomaly objects")

    @property
    def status(self) -> GateStatus:
        if any(item.severity is Severity.FAILURE for item in self.anomalies):
            return GateStatus.FAIL
        if self.anomalies:
            return GateStatus.WARN
        return GateStatus.PASS

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "baseline_id": self.baseline_id,
            "capture_id": self.capture_id,
            "compared_at_utc": self.compared_at_utc,
            "build_fingerprint": self.build_fingerprint,
            "status": self.status.value,
            "anomaly_count": len(self.anomalies),
            "failure_count": sum(item.severity is Severity.FAILURE for item in self.anomalies),
            "warning_count": sum(item.severity is Severity.WARNING for item in self.anomalies),
            "anomalies": [item.as_dict() for item in self.anomalies],
        }


__all__ = [
    "Anomaly",
    "ComparisonReport",
    "CounterPolicy",
    "DeploymentIdentity",
    "DeploymentSlotIdentity",
    "Distribution",
    "GateStatus",
    "MetricDirection",
    "MetricPolicy",
    "RuntimeBaseline",
    "RuntimeCapture",
    "RuntimeConsistencyError",
    "RuntimeObservation",
    "RuntimeScenario",
    "RuntimeSuite",
    "ScenarioResult",
    "ScenarioBaseline",
    "Severity",
    "SlotScope",
    "canonical_sha256",
    "validate_identifier",
    "validate_json",
    "validate_sha256",
]
