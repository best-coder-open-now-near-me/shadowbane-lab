"""Interpretable weights over the established deterministic utility policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from statistics import fmean
from typing import Protocol

from shadowbane_lab.protocol import DecisionMessage
from shadowbane_lab.rollouts.duel import CombatantConfig, UtilityDuelPolicy
from shadowbane_lab.sim import AgentExchange

from .build_model import canonical_digest

POLICY_WEIGHT_FIELDS = (
    "damage",
    "control",
    "healing",
    "survival",
    "setup",
    "mobility",
    "resource",
)


def _positive(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field_name} must be a positive finite number")
    return float(value)


@dataclass(frozen=True, slots=True)
class UtilityPolicyWeights:
    """Multipliers over action families; the all-ones vector preserves baseline policy."""

    damage: float = 1.0
    control: float = 1.0
    healing: float = 1.0
    survival: float = 1.0
    setup: float = 1.0
    mobility: float = 1.0
    resource: float = 1.0
    heal_threshold: float = 0.65

    def __post_init__(self) -> None:
        for field_name in POLICY_WEIGHT_FIELDS:
            value = _positive(getattr(self, field_name), field_name)
            if not 0.05 <= value <= 20.0:
                raise ValueError(f"{field_name} must be in [0.05, 20]")
        if (
            isinstance(self.heal_threshold, bool)
            or not isinstance(self.heal_threshold, (int, float))
            or not isfinite(self.heal_threshold)
            or not 0.05 <= self.heal_threshold <= 0.95
        ):
            raise ValueError("heal_threshold must be in [0.05, 0.95]")

    @property
    def vector(self) -> tuple[float, ...]:
        return tuple(float(getattr(self, field_name)) for field_name in POLICY_WEIGHT_FIELDS)

    @property
    def policy_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, float]:
        return {
            **{
                field_name: float(getattr(self, field_name))
                for field_name in POLICY_WEIGHT_FIELDS
            },
            "heal_threshold": float(self.heal_threshold),
        }

    @classmethod
    def from_vector(
        cls,
        values: tuple[float, ...],
        *,
        heal_threshold: float = 0.65,
    ) -> UtilityPolicyWeights:
        if len(values) != len(POLICY_WEIGHT_FIELDS):
            raise ValueError(
                f"policy vectors require {len(POLICY_WEIGHT_FIELDS)} weights"
            )
        return cls(
            **dict(zip(POLICY_WEIGHT_FIELDS, values, strict=True)),
            heal_threshold=heal_threshold,
        )


class WeightedUtilityDuelPolicy(UtilityDuelPolicy):
    """Scale utility scores without changing legality, actions, costs, or effects."""

    def __init__(
        self,
        maximum_health: float,
        weights: UtilityPolicyWeights,
        *,
        maximum_resources: dict[str, float] | None = None,
    ) -> None:
        if not isinstance(weights, UtilityPolicyWeights):
            raise ValueError("weights must be UtilityPolicyWeights")
        super().__init__(
            maximum_health,
            heal_threshold=weights.heal_threshold,
            maximum_resources=maximum_resources,
        )
        self._weights = weights

    def _score(self, affordance, health, actor_tags, target_tags, exchange) -> float:
        score = super()._score(
            affordance,
            health,
            actor_tags,
            target_tags,
            exchange,
        )
        if not isfinite(score):
            return score
        features = {feature.name: feature.value for feature in affordance.features}
        tags = frozenset(affordance.tags)
        factors: list[float] = []

        if (
            features.get("expected_damage", 0.0) > 0.0
            or features.get("trigger_expected_damage", 0.0) > 0.0
            or bool({"damage", "weapon", "attack"} & tags)
        ):
            factors.append(self._weights.damage)
        if (
            features.get("control_duration_ms", 0.0) > 0.0
            or features.get("trigger_control_duration_ms", 0.0) > 0.0
            or any(tag.startswith("control.") for tag in tags)
            or "action_denial" in tags
        ):
            factors.append(self._weights.control)
        if "healing" in tags or features.get("expected_healing", 0.0) > 0.0:
            factors.append(self._weights.healing)
        if (
            "damage_absorber" in tags
            or "cleanse" in tags
            or "stance.change.defensive" in tags
        ):
            factors.append(self._weights.survival)
        if (
            "debuff" in tags
            or "armed_trigger" in tags
            or "stealth" in tags
            or "invisibility" in tags
        ):
            factors.append(self._weights.setup)
        if (
            "range.close" in tags
            or "range.open" in tags
            or "movement" in tags
            or "teleport" in tags
        ):
            factors.append(self._weights.mobility)
        if "resource_conversion" in tags or "resource_drain" in tags:
            factors.append(self._weights.resource)

        return score if not factors else score * fmean(factors)


class DuelPolicy(Protocol):
    def decide(
        self,
        exchange: AgentExchange,
        correlation_id: str,
    ) -> DecisionMessage | None: ...


PolicyFactory = Callable[[CombatantConfig], DuelPolicy]


def weighted_policy_factory(weights: UtilityPolicyWeights) -> PolicyFactory:
    if not isinstance(weights, UtilityPolicyWeights):
        raise ValueError("weights must be UtilityPolicyWeights")

    def create(config: CombatantConfig) -> WeightedUtilityDuelPolicy:
        return WeightedUtilityDuelPolicy(
            config.health,
            weights,
            maximum_resources={"mana": config.mana, "stamina": config.stamina},
        )

    return create


def baseline_policy_factory(config: CombatantConfig) -> UtilityDuelPolicy:
    return UtilityDuelPolicy(
        config.health,
        maximum_resources={"mana": config.mana, "stamina": config.stamina},
    )


__all__ = [
    "POLICY_WEIGHT_FIELDS",
    "DuelPolicy",
    "PolicyFactory",
    "UtilityPolicyWeights",
    "WeightedUtilityDuelPolicy",
    "baseline_policy_factory",
    "weighted_policy_factory",
]
