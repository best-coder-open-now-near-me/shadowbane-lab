"""Deterministic diagonal evolution search over utility-policy weights."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import cos, isfinite, log, pi, sqrt
from statistics import fmean

from shadowbane_lab.sim import DeterministicRandom

from .build_model import canonical_digest
from .policy_rollout import UtilityPolicyEvaluation
from .utility_policy import POLICY_WEIGHT_FIELDS, UtilityPolicyWeights


def _positive(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field_name} must be a positive number")
    return float(value)


@dataclass(frozen=True, slots=True)
class DiagonalPolicySearchConfig:
    generations: int = 8
    population_size: int = 12
    elite_count: int = 4
    seed: int = 1
    initial_sigma: float = 0.35
    minimum_sigma: float = 0.025
    maximum_sigma: float = 2.0
    minimum_weight: float = 0.10
    maximum_weight: float = 8.0

    def __post_init__(self) -> None:
        for field_name, minimum in (
            ("generations", 0),
            ("population_size", 2),
            ("elite_count", 1),
            ("seed", 0),
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{field_name} must be an integer of at least {minimum}")
        if self.elite_count > self.population_size:
            raise ValueError("elite_count must not exceed population_size")
        for field_name in (
            "initial_sigma",
            "minimum_sigma",
            "maximum_sigma",
            "minimum_weight",
            "maximum_weight",
        ):
            _positive(getattr(self, field_name), field_name)
        if not self.minimum_sigma <= self.initial_sigma <= self.maximum_sigma:
            raise ValueError("initial_sigma must be inside the sigma bounds")
        if self.minimum_weight >= self.maximum_weight:
            raise ValueError("minimum_weight must be below maximum_weight")

    def as_dict(self) -> dict[str, object]:
        return {
            "generations": self.generations,
            "population_size": self.population_size,
            "elite_count": self.elite_count,
            "seed": self.seed,
            "initial_sigma": self.initial_sigma,
            "minimum_sigma": self.minimum_sigma,
            "maximum_sigma": self.maximum_sigma,
            "minimum_weight": self.minimum_weight,
            "maximum_weight": self.maximum_weight,
        }


@dataclass(frozen=True, slots=True)
class DiagonalPolicySearchGeneration:
    generation: int
    mean: UtilityPolicyWeights
    sigma: tuple[float, ...]
    best: UtilityPolicyEvaluation
    population_evaluations: int

    def as_dict(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "mean": self.mean.as_dict(),
            "sigma": dict(zip(POLICY_WEIGHT_FIELDS, self.sigma, strict=True)),
            "best": self.best.as_dict(),
            "population_evaluations": self.population_evaluations,
        }


@dataclass(frozen=True, slots=True)
class DiagonalPolicySearchResult:
    config: DiagonalPolicySearchConfig
    initial: UtilityPolicyEvaluation
    best: UtilityPolicyEvaluation
    generations: tuple[DiagonalPolicySearchGeneration, ...]
    evaluated_policy_count: int
    result_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "algorithm": "deterministic_diagonal_evolution_strategy_v1",
            "not_cma_es": True,
            "config": self.config.as_dict(),
            "initial": self.initial.as_dict(),
            "best": self.best.as_dict(),
            "generations": [item.as_dict() for item in self.generations],
            "evaluated_policy_count": self.evaluated_policy_count,
            "result_digest": self.result_digest,
        }


PolicyEvaluator = Callable[[UtilityPolicyWeights], UtilityPolicyEvaluation]


def run_diagonal_policy_search(
    evaluate: PolicyEvaluator,
    *,
    initial: UtilityPolicyWeights | None = None,
    config: DiagonalPolicySearchConfig | None = None,
) -> DiagonalPolicySearchResult:
    """Adapt independent Gaussian variances over interpretable policy weights.

    This is deliberately not called CMA-ES: it does not model or adapt a full
    covariance matrix. The current mean is retained in every generation, so the
    returned best can never be worse than the evaluated starting policy.
    """

    if not callable(evaluate):
        raise ValueError("evaluate must be callable")
    initial = initial or UtilityPolicyWeights()
    config = config or DiagonalPolicySearchConfig()
    if not isinstance(initial, UtilityPolicyWeights):
        raise ValueError("initial must be UtilityPolicyWeights")
    if not isinstance(config, DiagonalPolicySearchConfig):
        raise ValueError("config must be DiagonalPolicySearchConfig")

    random = DeterministicRandom(config.seed)
    initial_evaluation = evaluate(initial)
    _validate_evaluation(initial, initial_evaluation)
    best = initial_evaluation
    mean = initial
    sigma = tuple(config.initial_sigma for _ in POLICY_WEIGHT_FIELDS)
    generations: list[DiagonalPolicySearchGeneration] = []
    evaluated = 1

    for generation in range(config.generations):
        candidates = {mean.policy_digest: mean}
        attempts = 0
        while len(candidates) < config.population_size:
            attempts += 1
            if attempts > config.population_size * 1_000:
                raise ValueError("could not generate a unique bounded policy population")
            values = tuple(
                min(
                    config.maximum_weight,
                    max(
                        config.minimum_weight,
                        center + deviation * _standard_normal(random),
                    ),
                )
                for center, deviation in zip(mean.vector, sigma, strict=True)
            )
            candidate = UtilityPolicyWeights.from_vector(
                values,
                heal_threshold=initial.heal_threshold,
            )
            candidates[candidate.policy_digest] = candidate

        evaluations = tuple(evaluate(candidate) for candidate in candidates.values())
        evaluated += len(evaluations)
        for candidate, result in zip(candidates.values(), evaluations, strict=True):
            _validate_evaluation(candidate, result)
        ranked = tuple(
            sorted(
                evaluations,
                key=lambda item: (-item.quality, item.weights.policy_digest),
            )
        )
        elites = ranked[: config.elite_count]
        if _better(ranked[0], best):
            best = ranked[0]
        elite_vectors = tuple(item.weights.vector for item in elites)
        mean_vector = tuple(
            fmean(vector[index] for vector in elite_vectors)
            for index in range(len(POLICY_WEIGHT_FIELDS))
        )
        updated_sigma = []
        for index, previous in enumerate(sigma):
            variance = fmean(
                (vector[index] - mean_vector[index]) ** 2
                for vector in elite_vectors
            )
            adapted = sqrt(0.8 * previous**2 + 0.2 * variance)
            updated_sigma.append(
                min(config.maximum_sigma, max(config.minimum_sigma, adapted))
            )
        mean = UtilityPolicyWeights.from_vector(
            mean_vector,
            heal_threshold=initial.heal_threshold,
        )
        sigma = tuple(updated_sigma)
        generations.append(
            DiagonalPolicySearchGeneration(
                generation=generation,
                mean=mean,
                sigma=sigma,
                best=ranked[0],
                population_evaluations=len(evaluations),
            )
        )

    payload = {
        "algorithm": "deterministic_diagonal_evolution_strategy_v1",
        "config": config.as_dict(),
        "initial": initial_evaluation.as_dict(),
        "best": best.as_dict(),
        "generations": [item.as_dict() for item in generations],
        "evaluated_policy_count": evaluated,
    }
    return DiagonalPolicySearchResult(
        config=config,
        initial=initial_evaluation,
        best=best,
        generations=tuple(generations),
        evaluated_policy_count=evaluated,
        result_digest=canonical_digest(payload),
    )


def _validate_evaluation(
    weights: UtilityPolicyWeights,
    evaluation: UtilityPolicyEvaluation,
) -> None:
    if not isinstance(evaluation, UtilityPolicyEvaluation):
        raise ValueError("evaluator must return UtilityPolicyEvaluation")
    if evaluation.weights.policy_digest != weights.policy_digest:
        raise ValueError("evaluator returned a result for another policy")


def _standard_normal(random: DeterministicRandom) -> float:
    first = max(random.random(), 1.0 / (1 << 32))
    second = random.random()
    return sqrt(-2.0 * log(first)) * cos(2.0 * pi * second)


def _better(
    candidate: UtilityPolicyEvaluation,
    incumbent: UtilityPolicyEvaluation,
) -> bool:
    return (
        candidate.quality > incumbent.quality
        or (
            candidate.quality == incumbent.quality
            and candidate.weights.policy_digest < incumbent.weights.policy_digest
        )
    )


__all__ = [
    "DiagonalPolicySearchConfig",
    "DiagonalPolicySearchGeneration",
    "DiagonalPolicySearchResult",
    "PolicyEvaluator",
    "run_diagonal_policy_search",
]
