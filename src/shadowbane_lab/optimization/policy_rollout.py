"""Policy-injected duel rollouts and common-seed utility-policy leagues."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from statistics import fmean
from typing import Protocol, cast

from shadowbane_lab.protocol import Vector2
from shadowbane_lab.rollouts.duel import (
    DuelResult,
    TerminationReason,
    _cancel_dead_actor_schedule,
    _combatant_result,
    _distance,
    _entity,
    _trace_digest,
)
from shadowbane_lab.rollouts.open_builds import (
    OpenBuildError,
    OpenDuelRun,
    PrimitiveLoadout,
    _combatant,
    resolve_primitive_loadout,
)
from shadowbane_lab.rulesets import CompiledRuleset
from shadowbane_lab.sim import (
    OPEN_RANGE_ACTION_KEY,
    ActionCatalog,
    RangeBand,
    ReferenceEnvironment,
    close_range_action,
    open_range_action,
)

from .build_model import canonical_digest
from .utility_policy import (
    PolicyFactory,
    UtilityPolicyWeights,
    baseline_policy_factory,
    weighted_policy_factory,
)

_MELEE_RANGE = 3.0
_OPEN_RANGE_MINIMUM = 30.0
_OPEN_RANGE_MAXIMUM = 120.0


class DuelScenarioLike(Protocol):
    scenario_id: str
    starting_distance: float
    max_ticks: int
    mirrored: bool

    def as_dict(self) -> dict[str, object]: ...


def _validate_scenario(value: object) -> None:
    for field_name in ("scenario_id", "starting_distance", "max_ticks", "mirrored"):
        if not hasattr(value, field_name):
            raise ValueError("scenarios must implement the duel-scenario contract")
    scenario = cast(DuelScenarioLike, value)
    if not isinstance(scenario.scenario_id, str) or not scenario.scenario_id.strip():
        raise ValueError("scenario_id must be non-empty text")
    _positive(scenario.starting_distance, "scenario starting_distance")
    if (
        isinstance(scenario.max_ticks, bool)
        or not isinstance(scenario.max_ticks, int)
        or scenario.max_ticks < 1
    ):
        raise ValueError("scenario max_ticks must be a positive integer")
    if not isinstance(scenario.mirrored, bool):
        raise ValueError("scenario mirrored must be a boolean")
    if not callable(getattr(value, "as_dict", None)):
        raise ValueError("scenarios must expose as_dict()")


def _positive(value: float, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field_name} must be a positive finite number")
    return float(value)


def _non_negative_integer(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def primitive_loadout_mechanical_payload(loadout: PrimitiveLoadout) -> dict[str, object]:
    """Return rollout mechanics without display or experiment labels."""

    if not isinstance(loadout, PrimitiveLoadout):
        raise ValueError("loadout must be PrimitiveLoadout")
    return {
        "action_keys": sorted(loadout.action_keys),
        "health": float(loadout.health),
        "mana": float(loadout.mana),
        "stamina": float(loadout.stamina),
        "move_speed": float(loadout.move_speed),
        "tags": sorted(loadout.tags),
        "scalars": dict(sorted(loadout.scalars)),
        "persistent_trigger_keys": sorted(loadout.persistent_trigger_keys),
    }


def primitive_loadout_mechanical_digest(loadout: PrimitiveLoadout) -> str:
    return canonical_digest(primitive_loadout_mechanical_payload(loadout))


def run_open_duel_with_policies(
    ruleset: CompiledRuleset,
    left: PrimitiveLoadout,
    right: PrimitiveLoadout,
    *,
    left_policy_factory: PolicyFactory | None = None,
    right_policy_factory: PolicyFactory | None = None,
    starting_distance: float = 15.0,
    max_ticks: int = 1_200,
    seed: int = 1,
    auto_satisfy_action_requirements: bool = True,
) -> OpenDuelRun:
    """Run the ordinary semantic lifecycle with explicitly supplied policies.

    The orchestration mirrors :func:`run_open_duel`; only policy construction is
    injected. Tests require the default weighted policy to produce the exact same
    trace as the production utility baseline.
    """

    if not isinstance(ruleset, CompiledRuleset):
        raise ValueError("ruleset must be CompiledRuleset")
    if left.loadout_id == right.loadout_id:
        raise OpenBuildError("open duel loadout ids must differ")
    if (
        isinstance(max_ticks, bool)
        or not isinstance(max_ticks, int)
        or max_ticks < 1
    ):
        raise ValueError("max_ticks must be a positive integer")
    _non_negative_integer(seed, "seed")
    _positive(starting_distance, "starting_distance")
    if not isinstance(auto_satisfy_action_requirements, bool):
        raise ValueError("auto_satisfy_action_requirements must be a boolean")

    resolved_left = resolve_primitive_loadout(
        left,
        ruleset,
        auto_satisfy_action_requirements=auto_satisfy_action_requirements,
    )
    resolved_right = resolve_primitive_loadout(
        right,
        ruleset,
        auto_satisfy_action_requirements=auto_satisfy_action_requirements,
    )
    left_config = _combatant(resolved_left, left.loadout_id, "left")
    right_config = _combatant(resolved_right, right.loadout_id, "right")
    close = close_range_action(RangeBand(maximum=_MELEE_RANGE))
    open_range = open_range_action(
        RangeBand(minimum=_OPEN_RANGE_MINIMUM, maximum=_OPEN_RANGE_MAXIMUM)
    )
    catalog = ActionCatalog((*ruleset.catalog.actions, close, open_range))
    entities = (
        _entity(left_config, Vector2(0.0, 0.0), ruleset),
        _entity(right_config, Vector2(float(starting_distance), 0.0), ruleset),
    )
    for entity in entities:
        if "behavior.kite" in entity.tags:
            entity.action_keys = (*entity.action_keys, OPEN_RANGE_ACTION_KEY)
    environment = ReferenceEnvironment(
        catalog,
        entities,
        seed=seed,
        terminate_on_last_team=True,
    )
    policies = {
        left_config.entity_id: (left_policy_factory or baseline_policy_factory)(
            left_config
        ),
        right_config.entity_id: (right_policy_factory or baseline_policy_factory)(
            right_config
        ),
    }
    events = []
    reason = TerminationReason.TIME_LIMIT
    cancelled_scheduled_items = 0
    combatants = (left_config, right_config)

    for step_number in range(max_ticks):
        decisions = []
        for item in combatants:
            exchange = environment.exchange(item.entity_id)
            decision = policies[item.entity_id].decide(
                exchange,
                f"duel:{seed}:{step_number}:{item.entity_id}",
            )
            if decision is not None:
                decisions.append(decision)
        batch = environment.step(
            tuple(decisions),
            truncated=step_number == max_ticks - 1,
        )
        events.extend(batch.events)
        cancelled_scheduled_items += _cancel_dead_actor_schedule(environment)
        if batch.world_terminated:
            reason = TerminationReason.LAST_TEAM_STANDING
            break

    states = {item.entity_id: environment.entity(item.entity_id) for item in combatants}
    living = tuple(entity_id for entity_id, state in states.items() if state.alive)
    winner = living[0] if len(living) == 1 else None
    results = tuple(
        _combatant_result(item, states[item.entity_id], events)
        for item in combatants
    )
    final_distance = _distance(
        states[left_config.entity_id].position,
        states[right_config.entity_id].position,
    )
    duel = DuelResult(
        winner_entity_id=winner,
        reason=reason,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        seed=seed,
        starting_distance=float(starting_distance),
        final_distance=final_distance,
        total_events=len(events),
        cancelled_scheduled_items=cancelled_scheduled_items,
        trace_digest=_trace_digest(events),
        combatants=(results[0], results[1]),
    )
    return OpenDuelRun(left=resolved_left, right=resolved_right, duel=duel)


@dataclass(frozen=True, slots=True)
class UtilityPolicyEvaluation:
    weights: UtilityPolicyWeights
    quality: float
    rollout_count: int
    wins: int
    draws: int
    losses: int
    mean_ticks: float
    mean_health_margin: float
    mean_rejected_actions: float
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.weights, UtilityPolicyWeights):
            raise ValueError("weights must be UtilityPolicyWeights")
        if not isfinite(self.quality):
            raise ValueError("quality must be finite")
        for field_name in ("rollout_count", "wins", "draws", "losses"):
            _non_negative_integer(getattr(self, field_name), field_name)
        if self.rollout_count < 1:
            raise ValueError("rollout_count must be positive")
        if self.wins + self.draws + self.losses != self.rollout_count:
            raise ValueError("outcome counts must equal rollout_count")
        for field_name in (
            "mean_ticks",
            "mean_health_margin",
            "mean_rejected_actions",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{field_name} must be finite")
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) != 64:
            raise ValueError("evidence_digest must be a SHA-256 string")

    def as_dict(self) -> dict[str, object]:
        return {
            "weights": self.weights.as_dict(),
            "policy_digest": self.weights.policy_digest,
            "quality": self.quality,
            "rollout_count": self.rollout_count,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "win_rate": self.wins / self.rollout_count,
            "mean_ticks": self.mean_ticks,
            "mean_health_margin": self.mean_health_margin,
            "mean_rejected_actions": self.mean_rejected_actions,
            "evidence_digest": self.evidence_digest,
        }


class UtilityPolicyLeagueEvaluator:
    """Score one policy vector over fixed builds, scenarios, and common seeds."""

    EVALUATOR_VERSION = 1

    def __init__(
        self,
        ruleset: CompiledRuleset,
        controlled: PrimitiveLoadout,
        opponents: tuple[PrimitiveLoadout, ...],
        scenarios: tuple[DuelScenarioLike, ...],
        seeds: tuple[int, ...],
        *,
        opponent_weights: UtilityPolicyWeights | None = None,
    ) -> None:
        if not isinstance(ruleset, CompiledRuleset):
            raise ValueError("ruleset must be CompiledRuleset")
        if not isinstance(controlled, PrimitiveLoadout):
            raise ValueError("controlled must be PrimitiveLoadout")
        if not opponents or any(not isinstance(item, PrimitiveLoadout) for item in opponents):
            raise ValueError("opponents must contain PrimitiveLoadout values")
        if not scenarios:
            raise ValueError("scenarios must not be empty")
        for scenario in scenarios:
            _validate_scenario(scenario)
        if not seeds or len(seeds) != len(set(seeds)):
            raise ValueError("seeds must be non-empty and unique")
        for seed in seeds:
            _non_negative_integer(seed, "seed")
        opponent_weights = opponent_weights or UtilityPolicyWeights()
        if not isinstance(opponent_weights, UtilityPolicyWeights):
            raise ValueError("opponent_weights must be UtilityPolicyWeights")
        controlled_digest = primitive_loadout_mechanical_digest(controlled)
        opponent_digests = tuple(
            primitive_loadout_mechanical_digest(item) for item in opponents
        )
        if controlled_digest in opponent_digests:
            raise ValueError("controlled and opponent mechanics must differ")
        if len(opponent_digests) != len(set(opponent_digests)):
            raise ValueError("opponent mechanics must be distinct")
        self._ruleset = ruleset
        self._controlled = replace(
            controlled,
            loadout_id=f"controlled.{controlled_digest[:20]}",
            display_name="Controlled policy build",
        )
        self._opponents = tuple(
            replace(
                item,
                loadout_id=f"opponent.{index:03d}.{digest[:20]}",
                display_name=f"Policy opponent {index:03d}",
            )
            for index, (item, digest) in enumerate(
                zip(opponents, opponent_digests, strict=True)
            )
        )
        self._scenarios = scenarios
        self._seeds = tuple(sorted(seeds))
        self._opponent_weights = opponent_weights

    def __call__(self, weights: UtilityPolicyWeights) -> UtilityPolicyEvaluation:
        if not isinstance(weights, UtilityPolicyWeights):
            raise ValueError("weights must be UtilityPolicyWeights")
        controlled_factory = weighted_policy_factory(weights)
        opponent_factory = weighted_policy_factory(self._opponent_weights)
        runs: list[dict[str, object]] = []
        scores: list[float] = []
        ticks: list[float] = []
        margins: list[float] = []
        rejected: list[float] = []
        wins = draws = losses = 0

        for opponent in self._opponents:
            opponent_digest = primitive_loadout_mechanical_digest(opponent)
            for scenario in self._scenarios:
                for seed in self._seeds:
                    orientations = (True, False) if scenario.mirrored else (True,)
                    for controlled_left in orientations:
                        left, right = (
                            (self._controlled, opponent)
                            if controlled_left
                            else (opponent, self._controlled)
                        )
                        left_factory, right_factory = (
                            (controlled_factory, opponent_factory)
                            if controlled_left
                            else (opponent_factory, controlled_factory)
                        )
                        outcome = run_open_duel_with_policies(
                            self._ruleset,
                            left,
                            right,
                            left_policy_factory=left_factory,
                            right_policy_factory=right_factory,
                            starting_distance=scenario.starting_distance,
                            max_ticks=scenario.max_ticks,
                            seed=seed,
                        ).duel
                        controlled_result = next(
                            item
                            for item in outcome.combatants
                            if item.entity_id == self._controlled.loadout_id
                        )
                        opponent_result = next(
                            item
                            for item in outcome.combatants
                            if item.entity_id == opponent.loadout_id
                        )
                        controlled_fraction = max(
                            0.0,
                            controlled_result.final_health
                            / max(1.0, self._controlled.health),
                        )
                        opponent_fraction = max(
                            0.0,
                            opponent_result.final_health / max(1.0, opponent.health),
                        )
                        margin = controlled_fraction - opponent_fraction
                        if outcome.winner_entity_id == self._controlled.loadout_id:
                            result_score = 100.0
                            wins += 1
                        elif outcome.winner_entity_id is None:
                            result_score = 0.0
                            draws += 1
                        else:
                            result_score = -100.0
                            losses += 1
                        tempo = 1.0 - min(1.0, outcome.ticks / scenario.max_ticks)
                        result_score += margin * 10.0
                        if outcome.winner_entity_id == self._controlled.loadout_id:
                            result_score += tempo * 5.0
                        elif outcome.winner_entity_id is not None:
                            result_score -= tempo * 5.0
                        result_score -= controlled_result.rejected_actions * 0.25
                        if outcome.reason is TerminationReason.TIME_LIMIT:
                            result_score -= 1.0
                        scores.append(result_score)
                        ticks.append(float(outcome.ticks))
                        margins.append(margin)
                        rejected.append(float(controlled_result.rejected_actions))
                        runs.append(
                            {
                                "opponent_digest": opponent_digest,
                                "scenario": scenario.as_dict(),
                                "seed": seed,
                                "controlled_left": controlled_left,
                                "winner": outcome.winner_entity_id,
                                "termination_reason": outcome.reason.value,
                                "ticks": outcome.ticks,
                                "trace_digest": outcome.trace_digest,
                                "controlled_final_health": controlled_result.final_health,
                                "opponent_final_health": opponent_result.final_health,
                                "controlled_rejected_actions": (
                                    controlled_result.rejected_actions
                                ),
                            }
                        )

        evidence_digest = canonical_digest(
            {
                "evaluator_version": self.EVALUATOR_VERSION,
                "ruleset_id": self._ruleset.ruleset_id,
                "controlled_digest": primitive_loadout_mechanical_digest(
                    self._controlled
                ),
                "opponent_digests": [
                    primitive_loadout_mechanical_digest(item)
                    for item in self._opponents
                ],
                "opponent_policy": self._opponent_weights.as_dict(),
                "candidate_policy": weights.as_dict(),
                "scenarios": [item.as_dict() for item in self._scenarios],
                "seeds": list(self._seeds),
                "runs": runs,
            }
        )
        return UtilityPolicyEvaluation(
            weights=weights,
            quality=fmean(scores),
            rollout_count=len(runs),
            wins=wins,
            draws=draws,
            losses=losses,
            mean_ticks=fmean(ticks),
            mean_health_margin=fmean(margins),
            mean_rejected_actions=fmean(rejected),
            evidence_digest=evidence_digest,
        )


__all__ = [
    "DuelScenarioLike",
    "UtilityPolicyEvaluation",
    "UtilityPolicyLeagueEvaluator",
    "primitive_loadout_mechanical_digest",
    "primitive_loadout_mechanical_payload",
    "run_open_duel_with_policies",
]