"""Baseline promotion and robust anomaly comparison for runtime captures."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import median

from .model import (
    Anomaly,
    ComparisonReport,
    Distribution,
    MetricDirection,
    RuntimeBaseline,
    RuntimeCapture,
    RuntimeConsistencyError,
    RuntimeObservation,
    RuntimeScenario,
    RuntimeSuite,
    ScenarioBaseline,
    Severity,
    SlotScope,
    canonical_sha256,
)


def promote_runtime_baseline(
    baseline_id: str,
    suite: RuntimeSuite,
    captures: tuple[RuntimeCapture, ...],
    *,
    promoted_at: datetime | None = None,
) -> RuntimeBaseline:
    """Promote only complete, passing, semantically stable known-good captures."""

    if not captures:
        raise RuntimeConsistencyError("baseline promotion requires at least one capture")
    observations_by_scenario: dict[str, list[RuntimeObservation]] = defaultdict(list)
    for capture in captures:
        _require_capture_context(capture, suite)
        _require_complete_capture(capture, suite)
        if capture.requested_repetitions < suite.minimum_repetitions:
            raise RuntimeConsistencyError(
                f"capture {capture.capture_id} has fewer than "
                f"{suite.minimum_repetitions} repetitions"
            )
        failed = tuple(item for item in capture.observations if not item.passed)
        if failed:
            first = failed[0]
            raise RuntimeConsistencyError(
                f"capture {capture.capture_id} is not promotable: "
                f"{first.scenario_id}/{first.client_id}/{first.repetition} "
                f"reported {first.terminal_reason}"
            )
        for observation in capture.observations:
            observations_by_scenario[observation.scenario_id].append(observation)

    scenario_baselines: list[ScenarioBaseline] = []
    for scenario in suite.scenarios:
        observations = observations_by_scenario[scenario.scenario_id]
        _require_observation_fields(scenario, observations)
        semantic = observations[0].semantic
        assert semantic is not None
        expected_digest = canonical_sha256(semantic)
        if any(
            item.semantic is None or canonical_sha256(item.semantic) != expected_digest
            for item in observations[1:]
        ):
            raise RuntimeConsistencyError(
                f"scenario {scenario.scenario_id} is not semantically stable across known-good runs"
            )

        metrics = _distributions(observations, "metrics")
        counters = _distributions(observations, "counters")
        for name, policy in scenario.counter_policies:
            if policy.maximum_value is not None:
                maximum = dict(counters)[name].maximum
                if maximum > policy.maximum_value:
                    raise RuntimeConsistencyError(
                        f"scenario {scenario.scenario_id} counter {name} exceeds its "
                        f"declared maximum in known-good evidence"
                    )
        scenario_baselines.append(
            ScenarioBaseline(
                scenario_id=scenario.scenario_id,
                semantic=semantic,
                metric_distributions=metrics,
                counter_distributions=counters,
            )
        )

    return RuntimeBaseline(
        baseline_id=baseline_id,
        promoted_at_utc=_timestamp(promoted_at),
        suite=suite,
        source_capture_ids=tuple(capture.capture_id for capture in captures),
        accepted_build_fingerprints=tuple(
            sorted({capture.deployment.build_fingerprint for capture in captures})
        ),
        scenarios=tuple(scenario_baselines),
    )


def compare_runtime_capture(
    baseline: RuntimeBaseline,
    capture: RuntimeCapture,
    *,
    compared_at: datetime | None = None,
) -> ComparisonReport:
    anomalies: list[Anomaly] = []
    suite = baseline.suite
    try:
        _require_capture_context(capture, suite)
    except RuntimeConsistencyError as exc:
        anomalies.append(
            _failure(
                "context",
                None,
                "suite",
                suite.fingerprint,
                capture.suite_fingerprint,
                str(exc),
            )
        )
        return _report(baseline, capture, anomalies, compared_at)

    if capture.requested_repetitions < suite.minimum_repetitions:
        anomalies.append(
            _failure(
                "coverage",
                None,
                "requested_repetitions",
                suite.minimum_repetitions,
                capture.requested_repetitions,
                "capture does not meet the suite repetition floor",
            )
        )

    expected_keys = _expected_observation_keys(capture, suite)
    observed_keys = [
        (item.scenario_id, item.client_id, item.repetition) for item in capture.observations
    ]
    observed_key_set = set(observed_keys)
    for key in sorted(expected_keys - observed_key_set):
        anomalies.append(
            _failure(
                "coverage",
                key[0],
                f"{key[1]}/repetition-{key[2]}",
                "present",
                "missing",
                "required runtime observation is missing",
            )
        )
    for key in sorted(observed_key_set - expected_keys):
        anomalies.append(
            _failure(
                "coverage",
                key[0],
                f"{key[1]}/repetition-{key[2]}",
                "absent",
                "present",
                "unexpected runtime observation was captured",
            )
        )
    if len(observed_keys) != len(observed_key_set):
        anomalies.append(
            _failure(
                "coverage",
                None,
                "observation_coordinates",
                "unique",
                "duplicate",
                "capture contains duplicate scenario/client/repetition coordinates",
            )
        )

    baseline_by_scenario = {item.scenario_id: item for item in baseline.scenarios}
    observations_by_scenario: dict[str, list[RuntimeObservation]] = defaultdict(list)
    for observation in capture.observations:
        if observation.scenario_id in baseline_by_scenario:
            observations_by_scenario[observation.scenario_id].append(observation)
        if not observation.passed:
            anomalies.append(
                _failure(
                    "execution",
                    observation.scenario_id,
                    f"{observation.client_id}/repetition-{observation.repetition}",
                    "passed",
                    observation.terminal_reason,
                    "scenario command did not publish a passing result",
                )
            )

    for scenario in suite.scenarios:
        observations = observations_by_scenario[scenario.scenario_id]
        if not observations:
            continue
        scenario_baseline = baseline_by_scenario[scenario.scenario_id]
        expected_metrics = {name for name, _ in scenario.metric_policies}
        expected_counters = {name for name, _ in scenario.counter_policies}
        usable: list[RuntimeObservation] = []
        expected_semantic_digest = canonical_sha256(scenario_baseline.semantic)
        for observation in observations:
            actual_metrics = {name for name, _ in observation.metrics}
            actual_counters = {name for name, _ in observation.counters}
            if actual_metrics != expected_metrics:
                anomalies.append(
                    _failure(
                        "instrumentation",
                        scenario.scenario_id,
                        "metrics",
                        sorted(expected_metrics),
                        sorted(actual_metrics),
                        "scenario metric names differ from the versioned suite",
                    )
                )
                continue
            if actual_counters != expected_counters:
                anomalies.append(
                    _failure(
                        "instrumentation",
                        scenario.scenario_id,
                        "counters",
                        sorted(expected_counters),
                        sorted(actual_counters),
                        "scenario counter names differ from the versioned suite",
                    )
                )
                continue
            if observation.semantic is None:
                continue
            actual_digest = canonical_sha256(observation.semantic)
            if actual_digest != expected_semantic_digest:
                anomalies.append(
                    _failure(
                        "semantic",
                        scenario.scenario_id,
                        f"{observation.client_id}/repetition-{observation.repetition}",
                        expected_semantic_digest,
                        actual_digest,
                        "canonical semantic runtime evidence changed",
                    )
                )
            usable.append(observation)
        if not usable:
            continue
        _compare_metrics(scenario, scenario_baseline, usable, anomalies)
        _compare_counters(scenario, scenario_baseline, usable, anomalies)

    return _report(baseline, capture, anomalies, compared_at)


def distribution(values: list[float]) -> Distribution:
    if not values:
        raise ValueError("distribution requires values")
    ordered = sorted(float(value) for value in values)
    center = float(median(ordered))
    deviations = [abs(value - center) for value in ordered]
    return Distribution(
        count=len(ordered),
        minimum=ordered[0],
        percentile_05=_percentile(ordered, 0.05),
        median=center,
        percentile_95=_percentile(ordered, 0.95),
        maximum=ordered[-1],
        median_absolute_deviation=float(median(deviations)),
    )


def _compare_metrics(
    scenario: RuntimeScenario,
    baseline: ScenarioBaseline,
    observations: list[RuntimeObservation],
    anomalies: list[Anomaly],
) -> None:
    expected = dict(baseline.metric_distributions)
    actual = dict(_distributions(observations, "metrics"))
    for name, policy in scenario.metric_policies:
        before = expected[name]
        after = actual[name]
        radius = max(
            policy.absolute_tolerance,
            abs(before.median) * policy.relative_tolerance,
            before.median_absolute_deviation * policy.mad_multiplier,
        )
        lower = max(0.0, before.median - radius)
        upper = before.median + radius
        outside = False
        if policy.direction in {MetricDirection.TWO_SIDED, MetricDirection.DECREASE}:
            outside = after.median < lower or after.percentile_05 < max(
                0.0, before.percentile_05 - radius
            )
        if policy.direction in {MetricDirection.TWO_SIDED, MetricDirection.INCREASE}:
            outside = (
                outside
                or after.median > upper
                or after.percentile_95 > (before.percentile_95 + radius)
            )
        if outside:
            anomalies.append(
                Anomaly(
                    severity=policy.severity,
                    category="metric",
                    scenario_id=scenario.scenario_id,
                    field=name,
                    expected={"lower": lower, "upper": upper, "baseline": before.as_dict()},
                    actual=after.as_dict(),
                    detail="candidate runtime metric fell outside its declared robust envelope",
                )
            )
        variability_limit = before.median_absolute_deviation + radius
        if after.median_absolute_deviation > variability_limit:
            anomalies.append(
                Anomaly(
                    severity=policy.severity,
                    category="metric_variability",
                    scenario_id=scenario.scenario_id,
                    field=name,
                    expected={"maximum_mad": variability_limit},
                    actual={"mad": after.median_absolute_deviation},
                    detail="candidate runtime variability exceeded its declared envelope",
                )
            )


def _compare_counters(
    scenario: RuntimeScenario,
    baseline: ScenarioBaseline,
    observations: list[RuntimeObservation],
    anomalies: list[Anomaly],
) -> None:
    expected = dict(baseline.counter_distributions)
    actual = dict(_distributions(observations, "counters"))
    for name, policy in scenario.counter_policies:
        allowed = expected[name].maximum + policy.maximum_increase
        if policy.maximum_value is not None:
            allowed = min(allowed, float(policy.maximum_value))
        if actual[name].maximum > allowed:
            anomalies.append(
                Anomaly(
                    severity=policy.severity,
                    category="counter",
                    scenario_id=scenario.scenario_id,
                    field=name,
                    expected={"maximum": allowed},
                    actual=actual[name].as_dict(),
                    detail="candidate runtime counter exceeded its declared ceiling",
                )
            )


def _require_capture_context(capture: RuntimeCapture, suite: RuntimeSuite) -> None:
    expected = (suite.suite_id, suite.suite_revision, suite.environment_id, suite.fingerprint)
    actual = (
        capture.suite_id,
        capture.suite_revision,
        capture.environment_id,
        capture.suite_fingerprint,
    )
    if actual != expected:
        raise RuntimeConsistencyError("capture suite or environment differs from the baseline")


def _require_complete_capture(capture: RuntimeCapture, suite: RuntimeSuite) -> None:
    expected = _expected_observation_keys(capture, suite)
    actual = [(item.scenario_id, item.client_id, item.repetition) for item in capture.observations]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise RuntimeConsistencyError(
            f"capture {capture.capture_id} does not contain the exact scenario matrix"
        )


def _expected_observation_keys(
    capture: RuntimeCapture,
    suite: RuntimeSuite,
) -> set[tuple[str, str, int]]:
    slots = tuple(item.client_id for item in capture.deployment.slots)
    result: set[tuple[str, str, int]] = set()
    for scenario in suite.scenarios:
        scenario_slots = slots[:1] if scenario.slot_scope is SlotScope.FIRST else slots
        for client_id in scenario_slots:
            for repetition in range(capture.requested_repetitions):
                result.add((scenario.scenario_id, client_id, repetition))
    return result


def _require_observation_fields(
    scenario: RuntimeScenario,
    observations: list[RuntimeObservation],
) -> None:
    expected_metrics = {name for name, _ in scenario.metric_policies}
    expected_counters = {name for name, _ in scenario.counter_policies}
    for observation in observations:
        if {name for name, _ in observation.metrics} != expected_metrics:
            raise RuntimeConsistencyError(
                f"scenario {scenario.scenario_id} metrics differ from the suite"
            )
        if {name for name, _ in observation.counters} != expected_counters:
            raise RuntimeConsistencyError(
                f"scenario {scenario.scenario_id} counters differ from the suite"
            )


def _distributions(
    observations: list[RuntimeObservation],
    field_name: str,
) -> tuple[tuple[str, Distribution], ...]:
    values: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        fields = getattr(observation, field_name)
        for name, value in fields:
            values[name].append(float(value))
    return tuple((name, distribution(items)) for name, items in sorted(values.items()))


def _percentile(ordered: list[float], quantile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _failure(
    category: str,
    scenario_id: str | None,
    field: str,
    expected: object,
    actual: object,
    detail: str,
) -> Anomaly:
    return Anomaly(
        severity=Severity.FAILURE,
        category=category,
        scenario_id=scenario_id,
        field=field,
        expected=expected,
        actual=actual,
        detail=detail,
    )


def _report(
    baseline: RuntimeBaseline,
    capture: RuntimeCapture,
    anomalies: list[Anomaly],
    compared_at: datetime | None,
) -> ComparisonReport:
    return ComparisonReport(
        baseline_id=baseline.baseline_id,
        capture_id=capture.capture_id,
        compared_at_utc=_timestamp(compared_at),
        build_fingerprint=capture.deployment.build_fingerprint,
        anomalies=tuple(anomalies),
    )


def _timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "compare_runtime_capture",
    "distribution",
    "promote_runtime_baseline",
]
