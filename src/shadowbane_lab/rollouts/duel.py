"""Progression-aware deterministic duel rollouts over semantic affordances."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.combat import CombatSheet
from shadowbane_lab.combat.compiler import (
    MAGICBANE_COMBAT_FORMULA_REVISION,
    CombatCompilePolicy,
    CompiledCombatant,
    compile_combatant,
)
from shadowbane_lab.protocol import (
    Affordance,
    DecisionMessage,
    EntityKind,
    Event,
    EventKind,
    NamedScalar,
    Relation,
    Vector2,
)
from shadowbane_lab.rulesets import CharacterBuild, CompiledRuleset, load_shadowbane_vertical_slice
from shadowbane_lab.sim import (
    RANGE_MAXIMUM_FEATURE,
    ActionCatalog,
    AgentExchange,
    EntityState,
    RangeBand,
    ReferenceEnvironment,
    close_range_action,
)

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
STEAL_BREATH = "shadowbane.assassin.steal_breath"
PSYCHIC_SHIELD = "shadowbane.warlock.psychic_shield"
_DIRECTIONAL_MOVE = "shadowbane.move"
_CLOSE_RANGE = "sim.range.close"
_MELEE_RANGE = 3.0


def _positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")


@dataclass(frozen=True, slots=True)
class CombatantConfig:
    entity_id: str
    team_id: str
    build: CharacterBuild
    health: float = 100.0
    mana: float = 200.0
    stamina: float = 100.0
    move_speed: float = 30.0

    def __post_init__(self) -> None:
        for value, name in ((self.entity_id, "entity_id"), (self.team_id, "team_id")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.build, CharacterBuild):
            raise ValueError("build must be a CharacterBuild")
        for value, name in (
            (self.health, "health"),
            (self.mana, "mana"),
            (self.stamina, "stamina"),
            (self.move_speed, "move_speed"),
        ):
            _positive_number(value, name)


@dataclass(frozen=True, slots=True)
class DuelConfig:
    left: CombatantConfig
    right: CombatantConfig
    starting_distance: float = 10.0
    max_ticks: int = 1_000
    seed: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.left, CombatantConfig) or not isinstance(
            self.right, CombatantConfig
        ):
            raise ValueError("left and right must be CombatantConfig values")
        if self.left.entity_id == self.right.entity_id:
            raise ValueError("duel combatants require different entity ids")
        if self.left.team_id == self.right.team_id:
            raise ValueError("duel combatants require different team ids")
        _positive_number(self.starting_distance, "starting_distance")
        if isinstance(self.max_ticks, bool) or not isinstance(self.max_ticks, int):
            raise ValueError("max_ticks must be an integer")
        if self.max_ticks < 1:
            raise ValueError("max_ticks must be positive")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")


class TerminationReason(StrEnum):
    LAST_TEAM_STANDING = "last_team_standing"
    TIME_LIMIT = "time_limit"


@dataclass(frozen=True, slots=True)
class ActionCount:
    action_key: str
    count: int


@dataclass(frozen=True, slots=True)
class CombatantResult:
    entity_id: str
    profession: str
    level: int
    alive: bool
    final_health: float
    final_mana: float
    damage_dealt: float
    healing_received: float
    mana_spent: float
    rejected_actions: int
    actions: tuple[ActionCount, ...]


@dataclass(frozen=True, slots=True)
class DuelResult:
    winner_entity_id: str | None
    reason: TerminationReason
    ticks: int
    sim_time_ms: int
    seed: int
    total_events: int
    combatants: tuple[CombatantResult, CombatantResult]

    def as_dict(self) -> dict[str, object]:
        return {
            "winner_entity_id": self.winner_entity_id,
            "reason": self.reason.value,
            "ticks": self.ticks,
            "sim_time_ms": self.sim_time_ms,
            "seed": self.seed,
            "total_events": self.total_events,
            "combatants": [
                {
                    "entity_id": item.entity_id,
                    "profession": item.profession,
                    "level": item.level,
                    "alive": item.alive,
                    "final_health": item.final_health,
                    "final_mana": item.final_mana,
                    "damage_dealt": item.damage_dealt,
                    "healing_received": item.healing_received,
                    "mana_spent": item.mana_spent,
                    "rejected_actions": item.rejected_actions,
                    "actions": {
                        action.action_key: action.count for action in item.actions
                    },
                }
                for item in self.combatants
            ],
        }


@dataclass(frozen=True, slots=True)
class VerifiedCombatantConfig:
    entity_id: str
    team_id: str
    sheet: CombatSheet
    build: CharacterBuild

    def __post_init__(self) -> None:
        for value, name in ((self.entity_id, "entity_id"), (self.team_id, "team_id")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.sheet, CombatSheet):
            raise ValueError("sheet must be a CombatSheet")
        if not isinstance(self.build, CharacterBuild):
            raise ValueError("build must be a CharacterBuild")


@dataclass(frozen=True, slots=True)
class VerifiedDuelConfig:
    left: VerifiedCombatantConfig
    right: VerifiedCombatantConfig
    compile_policy: CombatCompilePolicy = CombatCompilePolicy()
    starting_distance: float = 10.0
    max_ticks: int = 1_000
    seed: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.left, VerifiedCombatantConfig) or not isinstance(
            self.right, VerifiedCombatantConfig
        ):
            raise ValueError("left and right must be VerifiedCombatantConfig values")
        if self.left.entity_id == self.right.entity_id:
            raise ValueError("duel combatants require different entity ids")
        if self.left.team_id == self.right.team_id:
            raise ValueError("duel combatants require different team ids")
        if self.left.sheet.sheet_id == self.right.sheet.sheet_id:
            raise ValueError("verified duel sheets require distinct sheet ids")
        if not isinstance(self.compile_policy, CombatCompilePolicy):
            raise ValueError("compile_policy must be a CombatCompilePolicy")
        _positive_number(self.starting_distance, "starting_distance")
        if isinstance(self.max_ticks, bool) or not isinstance(self.max_ticks, int):
            raise ValueError("max_ticks must be an integer")
        if self.max_ticks < 1:
            raise ValueError("max_ticks must be positive")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class VerifiedDuelResult:
    duel: DuelResult
    formula_revision: str
    sheet_acceptance: tuple[tuple[str, str, str], ...]
    ruleset_overrides_accepted: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": "complete_combat_sheet",
            "formula_revision": self.formula_revision,
            "ruleset_overrides_accepted": self.ruleset_overrides_accepted,
            "sheet_acceptance": [
                {
                    "sheet_id": sheet_id,
                    "source_revision": source_revision,
                    "compatibility": compatibility,
                }
                for sheet_id, source_revision, compatibility in self.sheet_acceptance
            ],
            **self.duel.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class VerifiedDuelBatchCombatant:
    entity_id: str
    wins: int
    mean_final_health: float
    mean_final_mana: float
    mean_damage_dealt: float
    mean_healing_received: float
    mean_mana_spent: float
    total_rejected_actions: int

    def as_dict(self) -> dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "wins": self.wins,
            "mean_final_health": self.mean_final_health,
            "mean_final_mana": self.mean_final_mana,
            "mean_damage_dealt": self.mean_damage_dealt,
            "mean_healing_received": self.mean_healing_received,
            "mean_mana_spent": self.mean_mana_spent,
            "total_rejected_actions": self.total_rejected_actions,
        }


@dataclass(frozen=True, slots=True)
class VerifiedDuelBatchResult:
    episodes: int
    seed_start: int
    formula_revision: str
    sheet_acceptance: tuple[tuple[str, str, str], ...]
    ruleset_overrides_accepted: bool
    draws: int
    mean_ticks: float
    termination_counts: tuple[tuple[TerminationReason, int], ...]
    combatants: tuple[VerifiedDuelBatchCombatant, VerifiedDuelBatchCombatant]

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": "complete_combat_sheet_batch",
            "episodes": self.episodes,
            "seed_start": self.seed_start,
            "formula_revision": self.formula_revision,
            "ruleset_overrides_accepted": self.ruleset_overrides_accepted,
            "sheet_acceptance": [
                {
                    "sheet_id": sheet_id,
                    "source_revision": source_revision,
                    "compatibility": compatibility,
                }
                for sheet_id, source_revision, compatibility in self.sheet_acceptance
            ],
            "draws": self.draws,
            "mean_ticks": self.mean_ticks,
            "termination_counts": {
                reason.value: count for reason, count in self.termination_counts
            },
            "combatants": [item.as_dict() for item in self.combatants],
        }


@dataclass(frozen=True, slots=True)
class _PreparedVerifiedDuel:
    left: CompiledCombatant
    right: CompiledCombatant
    formula_revision: str
    sheet_acceptance: tuple[tuple[str, str, str], ...]
    ruleset_overrides_accepted: bool


class UtilityDuelPolicy:
    """Small deterministic baseline over generic affordance tags and features."""

    def __init__(self, maximum_health: float, *, heal_threshold: float = 0.65) -> None:
        _positive_number(maximum_health, "maximum_health")
        if not 0.0 < heal_threshold < 1.0:
            raise ValueError("heal_threshold must be between zero and one")
        self._maximum_health = maximum_health
        self._heal_threshold = heal_threshold

    def decide(
        self, exchange: AgentExchange, correlation_id: str
    ) -> DecisionMessage | None:
        affordances = exchange.affordances.affordances
        if not affordances:
            return None
        actor = next(
            entity for entity in exchange.observation.entities if entity.relation is Relation.SELF
        )
        health = _scalar(actor.scalars, "health")
        actor_tags = frozenset(actor.tags)
        target_tags = {
            entity.entity_id: frozenset(entity.tags)
            for entity in exchange.observation.entities
            if entity.relation is Relation.ENEMY
        }
        scored = tuple(
            (self._score(item, health, actor_tags, target_tags, exchange), item)
            for item in affordances
        )
        score, selected = max(
            scored,
            key=lambda item: (item[0], item[1].action_key, item[1].affordance_id),
        )
        if score == float("-inf"):
            return None
        return exchange.decision(selected.affordance_id, correlation_id)

    def _score(
        self,
        affordance: Affordance,
        health: float,
        actor_tags: frozenset[str],
        target_tags: dict[str, frozenset[str]],
        exchange: AgentExchange,
    ) -> float:
        features = {feature.name: feature.value for feature in affordance.features}
        tags = frozenset(affordance.tags)
        commitment_ms = max(1.0, features.get("commitment_ms", 1.0))

        if "damage_absorber" in tags:
            if any(tag.startswith("breakpoint.damage.") for tag in actor_tags):
                return float("-inf")
            return (
                1_000.0
                + features.get("damage_breakpoint", 0.0) / 10.0
                + features.get("effect_duration_ms", 0.0) / 1_000.0
            )

        if "healing" in tags:
            if "immunity.resource.health" in actor_tags:
                return float("-inf")
            health_fraction = health / self._maximum_health
            if health_fraction > self._heal_threshold:
                return -100.0
            missing = max(0.0, self._maximum_health - health)
            effective = min(missing, features.get("expected_healing", 0.0))
            return 8.0 + effective * 1_000.0 / commitment_ms

        expected_damage = features.get("expected_damage", 0.0)
        control_ms = features.get("control_duration_ms", 0.0)
        healing_denial_ms = features.get("healing_denial_ms", 0.0)
        target_id = affordance.binding.target_entity_id
        selected_target_tags = target_tags.get(target_id, ()) if target_id is not None else ()
        if target_id is not None and "immunity.stun" in target_tags.get(target_id, ()):
            control_ms = 0.0
        if healing_denial_ms > 0.0:
            if "immunity.resource.health" in selected_target_tags:
                return float("-inf")
            return 12.0 + healing_denial_ms / 300.0
        if expected_damage > 0.0 or control_ms > 0.0:
            return expected_damage * 1_000.0 / commitment_ms + control_ms / 300.0

        if "range.close" in tags:
            distance = features.get("distance")
            maximum = features.get(RANGE_MAXIMUM_FEATURE)
            if distance is None or maximum is None or distance <= maximum:
                return float("-inf")
            return 1.0
        return -10.0


def run_duel(config: DuelConfig) -> DuelResult:
    """Run one deterministic duel until one team remains or the tick budget expires."""

    rank_overrides = _merge_rank_overrides(config.left.build, config.right.build)
    ruleset = load_shadowbane_vertical_slice(rank_overrides=rank_overrides)
    catalog = ActionCatalog(
        (*ruleset.catalog.actions, close_range_action(RangeBand(maximum=_MELEE_RANGE)))
    )
    entities = (
        _entity(config.left, Vector2(0.0, 0.0), ruleset),
        _entity(config.right, Vector2(config.starting_distance, 0.0), ruleset),
    )
    environment = ReferenceEnvironment(
        catalog,
        entities,
        seed=config.seed,
        terminate_on_last_team=True,
    )
    combatants = (config.left, config.right)
    policies = {
        item.entity_id: UtilityDuelPolicy(item.health) for item in combatants
    }
    events: list[Event] = []
    reason = TerminationReason.TIME_LIMIT

    for step_number in range(config.max_ticks):
        decisions = []
        for item in combatants:
            exchange = environment.exchange(item.entity_id)
            decision = policies[item.entity_id].decide(
                exchange, f"duel:{config.seed}:{step_number}:{item.entity_id}"
            )
            if decision is not None:
                decisions.append(decision)
        batch = environment.step(
            tuple(decisions), truncated=step_number == config.max_ticks - 1
        )
        events.extend(batch.events)
        if batch.world_terminated:
            reason = TerminationReason.LAST_TEAM_STANDING
            break

    states = {item.entity_id: environment.entity(item.entity_id) for item in combatants}
    living = tuple(entity_id for entity_id, state in states.items() if state.alive)
    winner = living[0] if len(living) == 1 else None
    results = tuple(
        _combatant_result(item, states[item.entity_id], events) for item in combatants
    )
    return DuelResult(
        winner_entity_id=winner,
        reason=reason,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        seed=config.seed,
        total_events=len(events),
        combatants=(results[0], results[1]),
    )


def run_verified_duel(config: VerifiedDuelConfig) -> VerifiedDuelResult:
    """Run a duel only after both complete sheets pass the explicit readiness policy."""

    prepared = _prepare_verified_duel(config)
    return _run_prepared_verified_duel(config, prepared, seed=config.seed)


def run_verified_duel_batch(
    config: VerifiedDuelConfig,
    *,
    episodes: int,
    seed_start: int | None = None,
) -> VerifiedDuelBatchResult:
    """Compile once and stream a contiguous deterministic seed batch into aggregates."""

    if isinstance(episodes, bool) or not isinstance(episodes, int) or episodes < 1:
        raise ValueError("episodes must be a positive integer")
    if seed_start is None:
        seed_start = config.seed
    if isinstance(seed_start, bool) or not isinstance(seed_start, int) or seed_start < 0:
        raise ValueError("seed_start must be a non-negative integer")

    prepared = _prepare_verified_duel(config)
    termination_counts: Counter[TerminationReason] = Counter()
    winner_counts: Counter[str] = Counter()
    draws = 0
    total_ticks = 0
    aggregate_values = [
        {
            "final_health": 0.0,
            "final_mana": 0.0,
            "damage_dealt": 0.0,
            "healing_received": 0.0,
            "mana_spent": 0.0,
            "rejected_actions": 0.0,
        }
        for _ in range(2)
    ]
    for offset in range(episodes):
        outcome = _run_prepared_verified_duel(
            config,
            prepared,
            seed=seed_start + offset,
        ).duel
        termination_counts[outcome.reason] += 1
        total_ticks += outcome.ticks
        if outcome.winner_entity_id is None:
            draws += 1
        else:
            winner_counts[outcome.winner_entity_id] += 1
        for index, combatant in enumerate(outcome.combatants):
            totals = aggregate_values[index]
            totals["final_health"] += combatant.final_health
            totals["final_mana"] += combatant.final_mana
            totals["damage_dealt"] += combatant.damage_dealt
            totals["healing_received"] += combatant.healing_received
            totals["mana_spent"] += combatant.mana_spent
            totals["rejected_actions"] += combatant.rejected_actions

    combatants = tuple(
        _aggregate_verified_combatant(
            entity_id,
            aggregate_values[index],
            winner_counts[entity_id],
            episodes,
        )
        for index, entity_id in enumerate(
            (config.left.entity_id, config.right.entity_id)
        )
    )
    return VerifiedDuelBatchResult(
        episodes=episodes,
        seed_start=seed_start,
        formula_revision=prepared.formula_revision,
        sheet_acceptance=prepared.sheet_acceptance,
        ruleset_overrides_accepted=prepared.ruleset_overrides_accepted,
        draws=draws,
        mean_ticks=total_ticks / episodes,
        termination_counts=tuple(sorted(termination_counts.items(), key=lambda item: item[0])),
        combatants=(combatants[0], combatants[1]),
    )


def _prepare_verified_duel(config: VerifiedDuelConfig) -> _PreparedVerifiedDuel:
    rank_overrides = _merge_rank_overrides(config.left.build, config.right.build)
    ruleset = load_shadowbane_vertical_slice(rank_overrides=rank_overrides)
    left = compile_combatant(
        config.left.sheet,
        config.left.build,
        ruleset,
        policy=config.compile_policy,
    )
    right = compile_combatant(
        config.right.sheet,
        config.right.build,
        ruleset,
        policy=config.compile_policy,
    )
    return _PreparedVerifiedDuel(
        left=left,
        right=right,
        formula_revision=MAGICBANE_COMBAT_FORMULA_REVISION,
        sheet_acceptance=tuple(
            (
                item.sheet.sheet_id,
                item.sheet.source_revision,
                item.sheet.compatibility.value,
            )
            for item in (config.left, config.right)
        ),
        ruleset_overrides_accepted=config.compile_policy.allow_ruleset_overrides,
    )


def _run_prepared_verified_duel(
    config: VerifiedDuelConfig,
    prepared: _PreparedVerifiedDuel,
    *,
    seed: int,
) -> VerifiedDuelResult:
    left = prepared.left
    right = prepared.right
    close = close_range_action(RangeBand(maximum=_MELEE_RANGE))
    catalog = ActionCatalog((*left.catalog.actions, *right.catalog.actions, close))
    left_entity = left.entity(config.left.entity_id, config.left.team_id, Vector2(0.0, 0.0))
    right_entity = right.entity(
        config.right.entity_id,
        config.right.team_id,
        Vector2(config.starting_distance, 0.0),
    )
    left_entity.action_keys = (*left_entity.action_keys, _CLOSE_RANGE)
    right_entity.action_keys = (*right_entity.action_keys, _CLOSE_RANGE)
    environment = ReferenceEnvironment(
        catalog,
        (left_entity, right_entity),
        seed=seed,
        terminate_on_last_team=True,
    )
    combatants = (config.left, config.right)
    policies = {
        config.left.entity_id: UtilityDuelPolicy(config.left.sheet.maximum_health),
        config.right.entity_id: UtilityDuelPolicy(config.right.sheet.maximum_health),
    }
    events: list[Event] = []
    reason = TerminationReason.TIME_LIMIT
    for step_number in range(config.max_ticks):
        decisions = []
        for item in combatants:
            exchange = environment.exchange(item.entity_id)
            decision = policies[item.entity_id].decide(
                exchange,
                f"verified-duel:{seed}:{step_number}:{item.entity_id}",
            )
            if decision is not None:
                decisions.append(decision)
        batch = environment.step(
            tuple(decisions),
            truncated=step_number == config.max_ticks - 1,
        )
        events.extend(batch.events)
        if batch.world_terminated:
            reason = TerminationReason.LAST_TEAM_STANDING
            break

    states = {item.entity_id: environment.entity(item.entity_id) for item in combatants}
    living = tuple(entity_id for entity_id, state in states.items() if state.alive)
    winner = living[0] if len(living) == 1 else None
    legacy_configs = (
        CombatantConfig(
            config.left.entity_id,
            config.left.team_id,
            config.left.build,
            health=config.left.sheet.maximum_health,
            mana=config.left.sheet.maximum_mana,
            stamina=config.left.sheet.maximum_stamina,
            move_speed=config.left.sheet.move_speed,
        ),
        CombatantConfig(
            config.right.entity_id,
            config.right.team_id,
            config.right.build,
            health=config.right.sheet.maximum_health,
            mana=config.right.sheet.maximum_mana,
            stamina=config.right.sheet.maximum_stamina,
            move_speed=config.right.sheet.move_speed,
        ),
    )
    results = tuple(
        _combatant_result(item, states[item.entity_id], events) for item in legacy_configs
    )
    duel = DuelResult(
        winner_entity_id=winner,
        reason=reason,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        seed=seed,
        total_events=len(events),
        combatants=(results[0], results[1]),
    )
    return VerifiedDuelResult(
        duel=duel,
        formula_revision=prepared.formula_revision,
        sheet_acceptance=prepared.sheet_acceptance,
        ruleset_overrides_accepted=prepared.ruleset_overrides_accepted,
    )


def _aggregate_verified_combatant(
    entity_id: str,
    totals: dict[str, float],
    wins: int,
    episodes: int,
) -> VerifiedDuelBatchCombatant:
    return VerifiedDuelBatchCombatant(
        entity_id=entity_id,
        wins=wins,
        mean_final_health=totals["final_health"] / episodes,
        mean_final_mana=totals["final_mana"] / episodes,
        mean_damage_dealt=totals["damage_dealt"] / episodes,
        mean_healing_received=totals["healing_received"] / episodes,
        mean_mana_spent=totals["mana_spent"] / episodes,
        total_rejected_actions=int(totals["rejected_actions"]),
    )


def matched_progression_duels(
    *,
    levels: tuple[int, ...] = (10, 15, 18, 22, 26, 40),
    power_ranks: tuple[int, ...] = (0, 20, 40),
    max_ticks: int = 1_000,
    seed: int = 1,
) -> tuple[tuple[int, int, DuelResult], ...]:
    """Bracket matched-level outcomes without inventing a rank-allocation curve."""

    results: list[tuple[int, int, DuelResult]] = []
    for rank in power_ranks:
        if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank <= 40:
            raise ValueError("power ranks must be integers between zero and 40")
        for level in levels:
            if isinstance(level, bool) or not isinstance(level, int) or level < 1:
                raise ValueError("levels must be positive integers")
            assassin = _progression_build("assassin", level, rank)
            warlock = _progression_build("warlock", level, rank)
            duel = DuelConfig(
                left=CombatantConfig("assassin", "assassin", assassin),
                right=CombatantConfig("warlock", "warlock", warlock),
                max_ticks=max_ticks,
                seed=seed,
            )
            results.append((level, rank, run_duel(duel)))
    return tuple(results)


def _progression_build(profession: str, level: int, rank: int) -> CharacterBuild:
    power_keys = (
        (SHADOW_BOLT, SHADOW_TOUCH, STEAL_BREATH)
        if profession == "assassin"
        else (MIND_STRIKE, PSYCHIC_HEALING, PSYCHIC_SHIELD)
    )
    skill_key = "shadowmastery" if profession == "assassin" else "warlockry"
    return CharacterBuild(
        profession=profession,
        level=level,
        skill_ranks=((skill_key, 200),),
        power_ranks=tuple((key, rank) for key in power_keys),
    )


def _merge_rank_overrides(*builds: CharacterBuild) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for build in builds:
        for action_key, rank in build.power_ranks:
            existing = overrides.get(action_key)
            if existing is not None and existing != rank:
                raise ValueError(
                    f"one ruleset cannot compile {action_key} at both rank {existing} and {rank}"
                )
            overrides[action_key] = rank
    return overrides


def _entity(config: CombatantConfig, position: Vector2, ruleset: CompiledRuleset) -> EntityState:
    return EntityState(
        entity_id=config.entity_id,
        life_id=f"{config.entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=config.team_id,
        position=position,
        scalars={
            "health": config.health,
            "mana": config.mana,
            "stamina": config.stamina,
            "move_speed": config.move_speed,
        },
        maximums={
            "health": config.health,
            "mana": config.mana,
            "stamina": config.stamina,
        },
        tags={f"profession.{config.build.profession}"},
        action_keys=tuple(
            _CLOSE_RANGE if key == _DIRECTIONAL_MOVE else key
            for key in ruleset.action_keys_for(config.build)
        ),
    )


def _combatant_result(
    config: CombatantConfig, state: EntityState, events: list[Event]
) -> CombatantResult:
    action_counts: dict[str, int] = {}
    damage_dealt = 0.0
    healing_received = 0.0
    mana_spent = 0.0
    rejected_actions = 0
    for event in events:
        scalars = {scalar.name: scalar.value for scalar in event.scalars}
        if event.kind == EventKind.ACTION_STARTED and event.source_entity_id == config.entity_id:
            if event.action_key is not None:
                action_counts[event.action_key] = action_counts.get(event.action_key, 0) + 1
        elif event.kind == EventKind.DAMAGE_APPLIED and event.source_entity_id == config.entity_id:
            damage_dealt += scalars.get("effective", 0.0)
        elif (
            event.kind == EventKind.RESOURCE_RESTORED
            and event.target_entity_id == config.entity_id
        ):
            if "resource.health" in event.tags:
                healing_received += scalars.get("effective", 0.0)
        elif event.kind == "resource_spent" and event.source_entity_id == config.entity_id:
            mana_spent += scalars.get("mana", 0.0)
        elif event.kind == EventKind.ACTION_REJECTED and event.source_entity_id == config.entity_id:
            rejected_actions += 1
    return CombatantResult(
        entity_id=config.entity_id,
        profession=config.build.profession,
        level=config.build.level,
        alive=state.alive,
        final_health=state.scalars.get("health", 0.0),
        final_mana=state.scalars.get("mana", 0.0),
        damage_dealt=damage_dealt,
        healing_received=healing_received,
        mana_spent=mana_spent,
        rejected_actions=rejected_actions,
        actions=tuple(
            ActionCount(action_key, count) for action_key, count in sorted(action_counts.items())
        ),
    )


def _scalar(values: tuple[NamedScalar, ...], name: str) -> float:
    return next((item.value for item in values if item.name == name), 0.0)
