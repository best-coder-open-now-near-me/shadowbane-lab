"""Strict JSON persistence for runtime consistency contracts."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path

from .model import (
    Anomaly,
    ComparisonReport,
    CounterPolicy,
    DeploymentIdentity,
    DeploymentSlotIdentity,
    Distribution,
    MetricDirection,
    MetricPolicy,
    RuntimeBaseline,
    RuntimeCapture,
    RuntimeConsistencyError,
    RuntimeObservation,
    RuntimeScenario,
    RuntimeSuite,
    ScenarioBaseline,
    ScenarioResult,
    Severity,
    SlotScope,
    canonical_sha256,
)

_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def load_suite(path: str | Path) -> RuntimeSuite:
    return parse_suite(_load_json(Path(path), "runtime suite"))


def load_scenario_result(path: str | Path) -> ScenarioResult:
    payload = _load_json(Path(path), "runtime scenario result")
    _exact(
        payload,
        {
            "schema_version",
            "scenario_id",
            "passed",
            "terminal_reason",
            "semantic",
            "metrics",
            "counters",
        },
        "runtime scenario result",
    )
    try:
        return ScenarioResult(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            scenario_id=payload["scenario_id"],  # type: ignore[arg-type]
            passed=payload["passed"],  # type: ignore[arg-type]
            terminal_reason=payload["terminal_reason"],  # type: ignore[arg-type]
            semantic=payload["semantic"],
            metrics=_number_items(payload["metrics"], "metrics"),
            counters=_counter_items(payload["counters"], "counters"),
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"invalid runtime scenario result: {exc}") from exc


def load_capture(path: str | Path) -> RuntimeCapture:
    payload = _load_json(Path(path), "runtime capture")
    _exact(
        payload,
        {
            "schema_version",
            "capture_id",
            "captured_at_utc",
            "suite_id",
            "suite_revision",
            "suite_fingerprint",
            "environment_id",
            "requested_repetitions",
            "deployment",
            "build_fingerprint",
            "host",
            "observation_count",
            "observations",
        },
        "runtime capture",
    )
    try:
        observations_payload = _object_list(payload["observations"], "observations")
        observations = tuple(_parse_observation(item) for item in observations_payload)
        if payload["observation_count"] != len(observations):
            raise ValueError("observation_count does not match observations")
        deployment = _parse_deployment(_object(payload["deployment"], "deployment"))
        if payload["build_fingerprint"] != deployment.build_fingerprint:
            raise ValueError("build_fingerprint does not match deployment identity")
        return RuntimeCapture(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            capture_id=payload["capture_id"],  # type: ignore[arg-type]
            captured_at_utc=payload["captured_at_utc"],  # type: ignore[arg-type]
            suite_id=payload["suite_id"],  # type: ignore[arg-type]
            suite_revision=payload["suite_revision"],  # type: ignore[arg-type]
            suite_fingerprint=payload["suite_fingerprint"],  # type: ignore[arg-type]
            environment_id=payload["environment_id"],  # type: ignore[arg-type]
            requested_repetitions=payload["requested_repetitions"],  # type: ignore[arg-type]
            deployment=deployment,
            host=_string_items(payload["host"], "host"),
            observations=observations,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"invalid runtime capture: {exc}") from exc


def load_baseline(path: str | Path) -> RuntimeBaseline:
    payload = _load_json(Path(path), "runtime baseline")
    _exact(
        payload,
        {
            "schema_version",
            "baseline_id",
            "promoted_at_utc",
            "suite",
            "suite_fingerprint",
            "source_capture_ids",
            "accepted_build_fingerprints",
            "scenarios",
        },
        "runtime baseline",
    )
    try:
        suite = parse_suite(_object(payload["suite"], "suite"))
        if payload["suite_fingerprint"] != suite.fingerprint:
            raise ValueError("suite_fingerprint does not match suite")
        return RuntimeBaseline(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            baseline_id=payload["baseline_id"],  # type: ignore[arg-type]
            promoted_at_utc=payload["promoted_at_utc"],  # type: ignore[arg-type]
            suite=suite,
            source_capture_ids=_strings(payload["source_capture_ids"], "source_capture_ids"),
            accepted_build_fingerprints=_strings(
                payload["accepted_build_fingerprints"],
                "accepted_build_fingerprints",
            ),
            scenarios=tuple(
                _parse_scenario_baseline(item)
                for item in _object_list(payload["scenarios"], "scenarios")
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"invalid runtime baseline: {exc}") from exc


def load_report(path: str | Path) -> ComparisonReport:
    payload = _load_json(Path(path), "runtime comparison report")
    _exact(
        payload,
        {
            "schema_version",
            "baseline_id",
            "capture_id",
            "compared_at_utc",
            "build_fingerprint",
            "status",
            "anomaly_count",
            "failure_count",
            "warning_count",
            "anomalies",
        },
        "runtime comparison report",
    )
    try:
        anomalies = tuple(
            _parse_anomaly(item) for item in _object_list(payload["anomalies"], "anomalies")
        )
        report = ComparisonReport(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            baseline_id=payload["baseline_id"],  # type: ignore[arg-type]
            capture_id=payload["capture_id"],  # type: ignore[arg-type]
            compared_at_utc=payload["compared_at_utc"],  # type: ignore[arg-type]
            build_fingerprint=payload["build_fingerprint"],  # type: ignore[arg-type]
            anomalies=anomalies,
        )
        expected = report.as_dict()
        for field_name in ("status", "anomaly_count", "failure_count", "warning_count"):
            if payload[field_name] != expected[field_name]:
                raise ValueError(f"{field_name} does not match report contents")
        return report
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"invalid runtime comparison report: {exc}") from exc


def save_artifact(path: str | Path, value: object) -> None:
    target = Path(path).resolve(strict=False)
    if target.exists():
        raise RuntimeConsistencyError(f"artifact destination already exists: {target}")
    as_dict = getattr(value, "as_dict", None)
    if not callable(as_dict):
        raise ValueError("runtime artifact must provide as_dict()")
    payload = as_dict()
    try:
        encoded = (
            json.dumps(payload, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"runtime artifact is not finite JSON: {exc}") from exc
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        raise RuntimeConsistencyError(f"could not publish runtime artifact: {exc}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def parse_suite(payload: Mapping[str, object]) -> RuntimeSuite:
    _exact(
        payload,
        {
            "schema_version",
            "suite_id",
            "suite_revision",
            "environment_id",
            "minimum_repetitions",
            "scenarios",
        },
        "runtime suite",
    )
    try:
        scenarios = tuple(
            _parse_scenario(item) for item in _object_list(payload["scenarios"], "scenarios")
        )
        return RuntimeSuite(
            schema_version=payload["schema_version"],  # type: ignore[arg-type]
            suite_id=payload["suite_id"],  # type: ignore[arg-type]
            suite_revision=payload["suite_revision"],  # type: ignore[arg-type]
            environment_id=payload["environment_id"],  # type: ignore[arg-type]
            minimum_repetitions=payload["minimum_repetitions"],  # type: ignore[arg-type]
            scenarios=scenarios,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeConsistencyError(f"invalid runtime suite: {exc}") from exc


def _parse_scenario(payload: Mapping[str, object]) -> RuntimeScenario:
    _exact(
        payload,
        {
            "scenario_id",
            "command",
            "timeout_seconds",
            "slot_scope",
            "metric_policies",
            "counter_policies",
        },
        "runtime scenario",
    )
    metric_payload = _object(payload["metric_policies"], "metric_policies")
    counter_payload = _object(payload["counter_policies"], "counter_policies")
    return RuntimeScenario(
        scenario_id=payload["scenario_id"],  # type: ignore[arg-type]
        command=_strings(payload["command"], "command"),
        timeout_seconds=payload["timeout_seconds"],  # type: ignore[arg-type]
        slot_scope=SlotScope(payload["slot_scope"]),  # type: ignore[arg-type]
        metric_policies=tuple(
            sorted(
                (
                    name,
                    _parse_metric_policy(_object(value, f"metric_policies.{name}")),
                )
                for name, value in metric_payload.items()
            )
        ),
        counter_policies=tuple(
            sorted(
                (
                    name,
                    _parse_counter_policy(_object(value, f"counter_policies.{name}")),
                )
                for name, value in counter_payload.items()
            )
        ),
    )


def _parse_metric_policy(payload: Mapping[str, object]) -> MetricPolicy:
    _exact(
        payload,
        {
            "direction",
            "absolute_tolerance",
            "relative_tolerance",
            "mad_multiplier",
            "severity",
        },
        "metric policy",
    )
    return MetricPolicy(
        direction=MetricDirection(payload["direction"]),  # type: ignore[arg-type]
        absolute_tolerance=payload["absolute_tolerance"],  # type: ignore[arg-type]
        relative_tolerance=payload["relative_tolerance"],  # type: ignore[arg-type]
        mad_multiplier=payload["mad_multiplier"],  # type: ignore[arg-type]
        severity=Severity(payload["severity"]),  # type: ignore[arg-type]
    )


def _parse_counter_policy(payload: Mapping[str, object]) -> CounterPolicy:
    _exact(
        payload,
        {"maximum_increase", "maximum_value", "severity"},
        "counter policy",
    )
    return CounterPolicy(
        maximum_increase=payload["maximum_increase"],  # type: ignore[arg-type]
        maximum_value=payload["maximum_value"],  # type: ignore[arg-type]
        severity=Severity(payload["severity"]),  # type: ignore[arg-type]
    )


def _parse_deployment(payload: Mapping[str, object]) -> DeploymentIdentity:
    _exact(
        payload,
        {
            "deployment_id",
            "deployment_kind",
            "baseline_tree_sha256",
            "repository_revision",
            "patch_id",
            "patch_manifest_sha256",
            "resolution",
            "slots",
        },
        "deployment identity",
    )
    slots: list[DeploymentSlotIdentity] = []
    for item in _object_list(payload["slots"], "slots"):
        _exact(
            item,
            {
                "client_id",
                "package_working_tree_sha256",
                "executable_sha256",
                "extension_sha256",
            },
            "deployment slot identity",
        )
        slots.append(
            DeploymentSlotIdentity(
                client_id=item["client_id"],  # type: ignore[arg-type]
                package_working_tree_sha256=item["package_working_tree_sha256"],  # type: ignore[arg-type]
                executable_sha256=item["executable_sha256"],  # type: ignore[arg-type]
                extension_sha256=item["extension_sha256"],  # type: ignore[arg-type]
            )
        )
    return DeploymentIdentity(
        deployment_id=payload["deployment_id"],  # type: ignore[arg-type]
        deployment_kind=payload["deployment_kind"],  # type: ignore[arg-type]
        baseline_tree_sha256=payload["baseline_tree_sha256"],  # type: ignore[arg-type]
        repository_revision=payload["repository_revision"],  # type: ignore[arg-type]
        patch_id=payload["patch_id"],  # type: ignore[arg-type]
        patch_manifest_sha256=payload["patch_manifest_sha256"],  # type: ignore[arg-type]
        resolution=payload["resolution"],  # type: ignore[arg-type]
        slots=tuple(sorted(slots, key=lambda value: value.client_id)),
    )


def _parse_observation(payload: Mapping[str, object]) -> RuntimeObservation:
    _exact(
        payload,
        {
            "scenario_id",
            "client_id",
            "repetition",
            "passed",
            "terminal_reason",
            "command_exit_code",
            "semantic",
            "semantic_sha256",
            "metrics",
            "counters",
        },
        "runtime observation",
    )
    semantic = payload["semantic"]
    expected_digest = None if semantic is None else canonical_sha256(semantic)
    if payload["semantic_sha256"] != expected_digest:
        raise ValueError("runtime observation semantic_sha256 does not match semantic")
    return RuntimeObservation(
        scenario_id=payload["scenario_id"],  # type: ignore[arg-type]
        client_id=payload["client_id"],  # type: ignore[arg-type]
        repetition=payload["repetition"],  # type: ignore[arg-type]
        passed=payload["passed"],  # type: ignore[arg-type]
        terminal_reason=payload["terminal_reason"],  # type: ignore[arg-type]
        command_exit_code=payload["command_exit_code"],  # type: ignore[arg-type]
        semantic=semantic,
        metrics=_number_items(payload["metrics"], "metrics"),
        counters=_counter_items(payload["counters"], "counters"),
    )


def _parse_scenario_baseline(payload: Mapping[str, object]) -> ScenarioBaseline:
    _exact(
        payload,
        {
            "scenario_id",
            "semantic",
            "semantic_sha256",
            "metric_distributions",
            "counter_distributions",
        },
        "scenario baseline",
    )
    if payload["semantic_sha256"] != canonical_sha256(payload["semantic"]):
        raise ValueError("scenario baseline semantic_sha256 does not match semantic")
    return ScenarioBaseline(
        scenario_id=payload["scenario_id"],  # type: ignore[arg-type]
        semantic=payload["semantic"],
        metric_distributions=_distribution_items(
            payload["metric_distributions"], "metric_distributions"
        ),
        counter_distributions=_distribution_items(
            payload["counter_distributions"], "counter_distributions"
        ),
    )


def _distribution_items(value: object, field_name: str) -> tuple[tuple[str, Distribution], ...]:
    payload = _object(value, field_name)
    items: list[tuple[str, Distribution]] = []
    for name, raw in payload.items():
        item = _object(raw, f"{field_name}.{name}")
        _exact(
            item,
            {
                "count",
                "minimum",
                "percentile_05",
                "median",
                "percentile_95",
                "maximum",
                "median_absolute_deviation",
            },
            f"{field_name}.{name}",
        )
        items.append(
            (
                name,
                Distribution(
                    count=item["count"],  # type: ignore[arg-type]
                    minimum=item["minimum"],  # type: ignore[arg-type]
                    percentile_05=item["percentile_05"],  # type: ignore[arg-type]
                    median=item["median"],  # type: ignore[arg-type]
                    percentile_95=item["percentile_95"],  # type: ignore[arg-type]
                    maximum=item["maximum"],  # type: ignore[arg-type]
                    median_absolute_deviation=item["median_absolute_deviation"],  # type: ignore[arg-type]
                ),
            )
        )
    return tuple(sorted(items))


def _parse_anomaly(payload: Mapping[str, object]) -> Anomaly:
    _exact(
        payload,
        {"severity", "category", "scenario_id", "field", "expected", "actual", "detail"},
        "anomaly",
    )
    return Anomaly(
        severity=Severity(payload["severity"]),  # type: ignore[arg-type]
        category=payload["category"],  # type: ignore[arg-type]
        scenario_id=payload["scenario_id"],  # type: ignore[arg-type]
        field=payload["field"],  # type: ignore[arg-type]
        expected=payload["expected"],
        actual=payload["actual"],
        detail=payload["detail"],  # type: ignore[arg-type]
    )


def _load_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        if not path.is_file() or path.is_symlink():
            raise RuntimeConsistencyError(f"{label} must be an existing regular file: {path}")
        data = path.read_bytes()
    except OSError as exc:
        raise RuntimeConsistencyError(f"could not read {label}: {exc}") from exc
    if len(data) > _MAX_ARTIFACT_BYTES:
        raise RuntimeConsistencyError(f"{label} exceeds {_MAX_ARTIFACT_BYTES} bytes")
    try:
        payload = json.loads(data, object_pairs_hook=_reject_duplicate_fields)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeConsistencyError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    return _object(payload, label)


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeConsistencyError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _exact(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise RuntimeConsistencyError(f"{label} fields are not exact: {'; '.join(details)}")


def _object(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeConsistencyError(f"{field_name} must be an object with string keys")
    return value


def _object_list(value: object, field_name: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise RuntimeConsistencyError(f"{field_name} must be an array")
    return tuple(_object(item, f"{field_name} item") for item in value)


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeConsistencyError(f"{field_name} must be an array of strings")
    return tuple(value)


def _string_items(value: object, field_name: str) -> tuple[tuple[str, str], ...]:
    payload = _object(value, field_name)
    if any(not isinstance(item, str) for item in payload.values()):
        raise RuntimeConsistencyError(f"{field_name} values must be strings")
    return tuple(sorted((name, item) for name, item in payload.items()))  # type: ignore[misc]


def _number_items(value: object, field_name: str) -> tuple[tuple[str, float], ...]:
    payload = _object(value, field_name)
    return tuple(sorted((name, item) for name, item in payload.items()))  # type: ignore[misc]


def _counter_items(value: object, field_name: str) -> tuple[tuple[str, int], ...]:
    payload = _object(value, field_name)
    return tuple(sorted((name, item) for name, item in payload.items()))  # type: ignore[misc]


__all__ = [
    "load_baseline",
    "load_capture",
    "load_report",
    "load_scenario_result",
    "load_suite",
    "parse_suite",
    "save_artifact",
]
