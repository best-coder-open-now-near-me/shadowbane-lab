"""Finite statistical result contracts for non-deterministic mechanics."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean, stdev

from shadowbane_lab.integrity import canonical_json_sha256, validate_identifier

STATISTICAL_RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class StatisticalResult:
    metric_id: str
    samples: tuple[float, ...]
    baseline_samples: tuple[float, ...]
    estimator: str
    estimate: float
    confidence_level: float
    confidence_interval: tuple[float, float]
    test_name: str
    effect_size: float | None
    stopping_rule: str
    stop_reached: bool
    result_id: str | None = None
    schema_version: int = STATISTICAL_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != STATISTICAL_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported statistical result schema version")
        validate_identifier(self.metric_id, "metric_id")
        if not self.samples or len(self.samples) > 1_000_000:
            raise ValueError("statistical result requires 1-1000000 samples")
        if len(self.baseline_samples) > 1_000_000:
            raise ValueError("statistical baseline cannot exceed 1000000 samples")
        if not 0 < self.confidence_level < 1:
            raise ValueError("confidence_level must be in (0, 1)")
        if self.confidence_interval[0] > self.confidence_interval[1]:
            raise ValueError("confidence interval bounds are reversed")
        expected = f"sha256:{canonical_json_sha256(self.content_dict())}"
        if self.result_id is None:
            object.__setattr__(self, "result_id", expected)
        elif self.result_id != expected:
            raise ValueError("result_id does not match statistical result content")

    def content_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_id": self.metric_id,
            "samples": list(self.samples),
            "baseline_samples": list(self.baseline_samples),
            "sample_count": len(self.samples),
            "baseline_sample_count": len(self.baseline_samples),
            "estimator": self.estimator,
            "estimate": self.estimate,
            "confidence_level": self.confidence_level,
            "confidence_interval": list(self.confidence_interval),
            "test_name": self.test_name,
            "effect_size": self.effect_size,
            "stopping_rule": self.stopping_rule,
            "stop_reached": self.stop_reached,
        }

    def as_dict(self) -> dict[str, object]:
        return {"result_id": self.result_id, **self.content_dict()}


def summarize_samples(
    metric_id: str,
    samples: tuple[float, ...],
    *,
    baseline_samples: tuple[float, ...] = (),
    confidence_level: float = 0.95,
    minimum_samples: int = 30,
    target_half_width: float | None = None,
) -> StatisticalResult:
    if not samples:
        raise ValueError("samples cannot be empty")
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be positive")
    if target_half_width is not None and target_half_width <= 0:
        raise ValueError("target_half_width must be positive")
    values = tuple(float(item) for item in samples)
    baseline = tuple(float(item) for item in baseline_samples)
    estimate = fmean(values)
    standard_error = stdev(values) / sqrt(len(values)) if len(values) > 1 else 0.0
    from statistics import NormalDist

    critical = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    half_width = critical * standard_error
    interval = (estimate - half_width, estimate + half_width)
    effect_size = None
    test_name = "mean-normal-approximation"
    if baseline:
        test_name = "descriptive-standardized-mean-difference"
        baseline_mean = fmean(baseline)
        if len(values) > 1 and len(baseline) > 1:
            pooled_variance = (
                (len(values) - 1) * stdev(values) ** 2
                + (len(baseline) - 1) * stdev(baseline) ** 2
            ) / (len(values) + len(baseline) - 2)
            effect_size = (estimate - baseline_mean) / sqrt(pooled_variance) if pooled_variance else 0.0
        else:
            effect_size = 0.0 if estimate == baseline_mean else None
    stopping_rule = f"n>={minimum_samples}"
    stop_reached = len(values) >= minimum_samples
    if target_half_width is not None:
        stopping_rule += f" and ci_half_width<={target_half_width}"
        stop_reached = stop_reached and half_width <= target_half_width
    return StatisticalResult(
        metric_id=metric_id,
        samples=values,
        baseline_samples=baseline,
        estimator="arithmetic_mean",
        estimate=estimate,
        confidence_level=confidence_level,
        confidence_interval=interval,
        test_name=test_name,
        effect_size=effect_size,
        stopping_rule=stopping_rule,
        stop_reached=stop_reached,
    )


__all__ = ["StatisticalResult", "summarize_samples"]
