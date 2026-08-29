"""Progression-aware deterministic duel rollouts over semantic affordances."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from math import hypot
from statistics import fmean

from shadowbane_lab.protocol import (
    Affordance,
    DecisionMessage,
    EntityKind,
    EntityObservation,
    Event,
    EventKind,
    NamedScalar,
    Relation,
    Vector2,
)
from shadowbane_lab.rollouts.ruleset import load_assassin_warlock_duel_ruleset
from shadowbane_lab.rulesets import CharacterBuild, CompiledRuleset
from shadowbane_lab.sim import (
    ActiveEffectState,
    AgentExchange,
    EntityState,
    ReferenceEnvironment,
    ScheduledKind,
)

MOVE = "shadowbane.move"
BASIC_ATTACK = "shadowbane.basic_attack"
SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
FADE = "shadowbane.assassin.fade"
BACKSTAB = "shadowbane.assassin.backstab"
INVISIBILITY = "shadowbane.assassin.invisibility"
SHADOW_MANTLE = "shadowbane.assassin.shadow_mantle"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
MIND_SNARE = "shadowbane.warlock.mind_snare"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
LEVITATION = "shadowbane.warlock.levitation"

_DEFAULT_LEVELS = (10, 15, 18, 19, 22, 26, 28, 42, 75)
_DEFAULT_POWER_RANKS = (0, 10, 20, 40)

_POWER_MAXIMUMS = {
    "assassin": (
        (SHADOW_BOLT, 40),
        (SHADOW_TOUCH, 40),
        (FADE, 20),
        (BACKSTAB, 40),
        (INVISIBILITY, 20),
        (SHADOW_MANTLE, 40),
    ),
    "warlock": (
        (MIND_STRIKE, 40),
        (MIND_SNARE, 40),
        (PSYCHIC_HEALING, 40),
    ),
}


def _positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class CombatantConfig:
    entity_id: str
    team_id: str
    build: CharacterBuild
    health: float = 500.0
    mana: float = 300.0
    stamina: float = 200.0
    move_speed: float = 15.0
    tags: tuple[str, ...] = ()
    extra_scalars: tuple[tuple[str, float], ...] = ()
    initial_trigger_keys: tuple[str, ...] = ()
    action_keys_override: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "entity_id")
        _identifier(self.team_id, "team_id")
        if not isinstance(self.build, CharacterBuild):
            raise ValueError("build must be a CharacterBuild")
        for value, name in (
            (self.health, "health"),
            (self.mana, "mana"),
            (self.stamina, "stamina"),
            (self.move_speed, "move_speed"),
        ):
            _positive_number(value, name)
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")
        for tag in self.tags:
            _identifier(tag, "tag")
        scalar_keys = tuple(key for key, _ in self.extra_scalars)
        if len(scalar_keys) != len(set(scalar_keys)):
            raise ValueError("extra_scalars must not contain duplicate keys")
        reserved = {"health", "mana", "stamina", "move_speed"}
        if set(scalar_keys) & reserved:
            raise ValueError("extra_scalars cannot replace reserved body scalars")
        for key, value in self.extra_scalars:
            _identifier(key, "extra scalar key")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("extra scalar values must be numbers")
        if len(self.initial_trigger_keys) != len(set(self.initial_trigger_keys)):
            raise ValueError("initial_trigger_keys must not contain duplicates")
        for trigger_key in self.initial_trigger_keys:
            _identifier(trigger_key, "initial trigger key")
        if self.action_keys_override is not None:
            if len(self.action_keys_override) != len(set(self.action_keys_override)):
                raise ValueError("action_keys_override must not contain duplicates")
            for action_key in self.action_keys_override:
                _identifier(action_key, "action override key")


@dataclass(frozen=True, slots=True)
class DuelConfig:
    left: CombatantConfig
    right: CombatantConfig
    starting_distance: float = 15.0
    max_ticks: int = 1_200
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
class TriggerCount:
    trigger_key: str
    count: int


@dataclass(frozen=True, slots=True)
class CombatantResult:
    entity_id: str
    profession: str
    level: int
    power_ranks: tuple[tuple[str, int], ...]
    available_actions: tuple[str, ...]
    alive: bool
    final_health: float
    final_mana: float
    final_stamina: float
    damage_dealt: float
    healing_received: float
    mana_spent: float
    stamina_spent: float
    rejected_actions: int
    attacks_attempted: int
    weapon_hits: int
    weapon_misses: int
    passive_defenses: int
    damage_absorbed: float
    actions: tuple[ActionCount, ...]
    triggers: tuple[TriggerCount, ...]


@dataclass(frozen=True, slots=True)
class DuelResult:
    winner_entity_id: str | None
    reason: TerminationReason
    ticks: int
    sim_time_ms: int
    seed: int
    starting_distance: float
    final_distance: float
    total_events: int
    cancelled_scheduled_items: int
    trace_digest: str
    combatants: tuple[CombatantResult, CombatantResult]

    def as_dict(self) -> dict[str, object]:
        return {
            "winner_entity_id": self.winner_entity_id,
            "reason": self.reason.value,
            "ticks": self.ticks,
            "sim_time_ms": self.sim_time_ms,
            "seed": self.seed,
            "starting_distance": self.starting_distance,
            "final_distance": self.final_distance,
            "total_events": self.total_events,
            "cancelled_scheduled_items": self.cancelled_scheduled_items,
            "trace_digest": self.trace_digest,
            "combatants": [
                {
                    "entity_id": item.entity_id,
                    "profession": item.profession,
                    "level": item.level,
                    "power_ranks": dict(item.power_ranks),
                    "available_actions": list(item.available_actions),
                    "alive": item.alive,
                    "final_health": item.final_health,
                    "final_mana": item.final_mana,
                    "final_stamina": item.final_stamina,
                    "damage_dealt": item.damage_dealt,
                    "healing_received": item.healing_received,
                    "mana_spent": item.mana_spent,
                    "stamina_spent": item.stamina_spent,
                    "rejected_actions": item.rejected_actions,
                    "attacks_attempted": item.attacks_attempted,
                    "weapon_hits": item.weapon_hits,
                    "weapon_misses": item.weapon_misses,
                    "passive_defenses": item.passive_defenses,
                    "damage_absorbed": item.damage_absorbed,
                    "actions": {action.action_key: action.count for action in item.actions},
                    "triggers": {trigger.trigger_key: trigger.count for trigger in item.triggers},
                }
                for item in self.combatants
            ],
        }


@dataclass(frozen=True, slots=True)
class ProgressionMatrixCell:
    level: int
    power_rank: int
    starting_distance: float
    matches: int
    assassin_wins: int
    warlock_wins: int
    draws: int
    time_limits: int
    mean_ticks: float
    unique_trace_count: int
    sample: DuelResult

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "power_rank": self.power_rank,
            "starting_distance": self.starting_distance,
            "matches": self.matches,
            "assassin_wins": self.assassin_wins,
            "warlock_wins": self.warlock_wins,
            "draws": self.draws,
            "time_limits": self.time_limits,
            "mean_ticks": self.mean_ticks,
            "unique_trace_count": self.unique_trace_count,
            "sample": self.sample.as_dict(),
        }


class UtilityDuelPolicy:
    """Small deterministic baseline over generic affordance tags and features."""

    def __init__(
        self,
        maximum_health: float,
        *,
        action_keys: tuple[str, ...] = (),
        heal_threshold: float = 0.65,
    ) -> None:
        _positive_number(maximum_health, "maximum_health")
        if not 0.0 < heal_threshold < 1.0:
            raise ValueError("heal_threshold must be between zero and one")
        if len(action_keys) != len(set(action_keys)):
            raise ValueError("action_keys must not contain duplicates")
        self._maximum_health = maximum_health
        self._action_keys = frozenset(action_keys)
        self._heal_threshold = heal_threshold

    def decide(self, exchange: AgentExchange, correlation_id: str) -> DecisionMessage | None:
        affordances = exchange.affordances.affordances
        if not affordances:
            return None
        actor = next(
            entity for entity in exchange.observation.entities if entity.relation is Relation.SELF
        )
        if "control.power_block" in actor.tags:
            return None
        health = _scalar(actor.scalars, "health")
        enemies = {
            entity.entity_id: entity
            for entity in exchange.observation.entities
            if entity.relation is Relation.ENEMY
        }
        scored = tuple(
            (self._score(item, actor, health, enemies, exchange), item) for item in affordances
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
        actor: EntityObservation,
        health: float,
        enemies: dict[str, EntityObservation],
        exchange: AgentExchange,
    ) -> float:
        features = {feature.name: feature.value for feature in affordance.features}
        tags = frozenset(affordance.tags)
        commitment_ms = max(1.0, features.get("commitment_ms", 1.0))

        if "healing" in tags:
            block_rank = _optional_scalar(actor.scalars, "restore_block_rank.health")
            effect_rank = features.get("effect_rank", 0.0)
            if block_rank is not None and block_rank >= effect_rank:
                return -100.0
            health_fraction = health / self._maximum_health
            if health_fraction > self._heal_threshold:
                return -100.0
            missing = max(0.0, self._maximum_health - health)
            effective = min(missing, features.get("expected_healing", 0.0))
            return 12.0 + effective * 1_000.0 / commitment_ms

        if "healing_block" in tags:
            return self._healing_block_score(affordance, enemies, features)
        if "stealth" in tags or "invisibility" in tags:
            return self._stealth_score(affordance, actor, enemies, commitment_ms)
        if "snare" in tags:
            return self._snare_score(affordance, enemies, features)
        if "flight" in tags:
            return -30.0
        if "armed_trigger" in tags:
            trigger_damage = features.get("expected_trigger_damage", 0.0)
            trigger_control_ms = features.get("expected_trigger_control_duration_ms", 0.0)
            followup_ms = max(1.0, features.get("expected_followup_commitment_ms", 1_000.0))
            return (
                8.0
                + trigger_damage * 1_000.0 / (commitment_ms + followup_ms)
                + trigger_control_ms / 300.0
            )

        expected_damage = features.get("expected_damage", 0.0) + features.get(
            "trigger_expected_damage", 0.0
        )
        control_ms = features.get("control_duration_ms", 0.0) + features.get(
            "trigger_control_duration_ms", 0.0
        )
        target_id = affordance.binding.target_entity_id
        target = enemies.get(target_id or "")
        if target is not None and ("immunity.stun" in target.tags or "control.stun" in target.tags):
            control_ms = 0.0
        if expected_damage > 0.0 or control_ms > 0.0:
            score = expected_damage * 1_000.0 / commitment_ms + control_ms / 300.0
            if target is not None and expected_damage >= _scalar(target.scalars, "health"):
                score += 1_000.0
            return score

        if "movement" in tags and affordance.binding.direction is not None:
            return self._movement_score(affordance, exchange)
        return -10.0

    def _stealth_score(
        self,
        affordance: Affordance,
        actor: EntityObservation,
        enemies: dict[str, EntityObservation],
        commitment_ms: float,
    ) -> float:
        if "capability.stealth_required" not in actor.tags or "visibility.invisible" in actor.tags:
            return float("-inf")
        if not enemies:
            return float("-inf")
        distance = min(_distance(actor.position, item.position) for item in enemies.values())
        if distance > 15.0:
            return -25.0
        base = 24.0 if affordance.action_key == INVISIBILITY else 21.0
        return base - commitment_ms / 1_000.0

    @staticmethod
    def _snare_score(
        affordance: Affordance,
        enemies: dict[str, EntityObservation],
        features: dict[str, float],
    ) -> float:
        target = enemies.get(affordance.binding.target_entity_id or "")
        if target is None or "control.snare" in target.tags:
            return -100.0
        if "movement.flight" not in target.tags:
            return -20.0
        return 8.0 + features.get("control_duration_ms", 0.0) / 1_000.0

    @staticmethod
    def _healing_block_score(
        affordance: Affordance,
        enemies: dict[str, EntityObservation],
        features: dict[str, float],
    ) -> float:
        target = enemies.get(affordance.binding.target_entity_id or "")
        if target is None or "healing.block" in target.tags:
            return -100.0
        if "capability.healing" not in target.tags:
            return -20.0
        duration = features.get("control_duration_ms", 0.0)
        block_rank = features.get("healing_block_rank", 0.0)
        return 32.0 + min(duration, 30_000.0) / 30_000.0 + min(block_rank, 40.0) / 40.0

    @staticmethod
    def _movement_score(affordance: Affordance, exchange: AgentExchange) -> float:
        actor = next(
            entity for entity in exchange.observation.entities if entity.relation is Relation.SELF
        )
        enemies = tuple(
            entity for entity in exchange.observation.entities if entity.relation is Relation.ENEMY
        )
        if not enemies or affordance.binding.direction is None:
            return float("-inf")
        target = min(enemies, key=lambda item: _distance(actor.position, item.position))
        delta_x = target.position.x - actor.position.x
        delta_y = target.position.y - actor.position.y
        length = hypot(delta_x, delta_y)
        if length == 0.0:
            return float("-inf")
        direction = affordance.binding.direction
        alignment = (direction.x * delta_x + direction.y * delta_y) / length
        return 1.0 + alignment


def run_duel(config: DuelConfig, *, ruleset: CompiledRuleset | None = None) -> DuelResult:
    """Run one deterministic duel until one team remains or the tick budget expires."""

    rank_overrides = _merge_rank_overrides(config.left.build, config.right.build)
    if ruleset is None:
        ruleset = load_assassin_warlock_duel_ruleset(rank_overrides=rank_overrides)
    else:
        for action_key, rank in rank_overrides.items():
            record = ruleset.record(action_key)
            if record.rank != rank:
                raise ValueError(f"{action_key} was compiled at rank {record.rank}, not {rank}")
    entities = (
        _entity(config.left, Vector2(0.0, 0.0), ruleset),
        _entity(config.right, Vector2(config.starting_distance, 0.0), ruleset),
    )
    environment = ReferenceEnvironment(
        ruleset.catalog,
        entities,
        seed=config.seed,
        terminate_on_last_team=True,
    )
    combatants = (config.left, config.right)
    policies = {
        item.entity_id: UtilityDuelPolicy(
            item.health,
            action_keys=next(
                entity.action_keys for entity in entities if entity.entity_id == item.entity_id
            ),
        )
        for item in combatants
    }
    events: list[Event] = []
    reason = TerminationReason.TIME_LIMIT
    cancelled_scheduled_items = 0

    for step_number in range(config.max_ticks):
        decisions = []
        for item in combatants:
            exchange = environment.exchange(item.entity_id)
            decision = policies[item.entity_id].decide(
                exchange, f"duel:{config.seed}:{step_number}:{item.entity_id}"
            )
            if decision is not None:
                decisions.append(decision)
        batch = environment.step(tuple(decisions), truncated=step_number == config.max_ticks - 1)
        events.extend(batch.events)
        cancelled_scheduled_items += _cancel_dead_actor_schedule(environment)
        if batch.world_terminated:
            reason = TerminationReason.LAST_TEAM_STANDING
            break

    states = {item.entity_id: environment.entity(item.entity_id) for item in combatants}
    living = tuple(entity_id for entity_id, state in states.items() if state.alive)
    winner = living[0] if len(living) == 1 else None
    results = tuple(_combatant_result(item, states[item.entity_id], events) for item in combatants)
    final_distance = _distance(
        states[config.left.entity_id].position, states[config.right.entity_id].position
    )
    return DuelResult(
        winner_entity_id=winner,
        reason=reason,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        seed=config.seed,
        starting_distance=config.starting_distance,
        final_distance=final_distance,
        total_events=len(events),
        cancelled_scheduled_items=cancelled_scheduled_items,
        trace_digest=_trace_digest(events),
        combatants=(results[0], results[1]),
    )


def matched_progression_duels(
    *,
    levels: tuple[int, ...] = _DEFAULT_LEVELS,
    power_ranks: tuple[int, ...] = _DEFAULT_POWER_RANKS,
    starting_distance: float = 15.0,
    max_ticks: int = 1_200,
    seed: int = 1,
) -> tuple[tuple[int, int, DuelResult], ...]:
    """Bracket matched-level outcomes without inventing a rank-allocation curve."""

    _validate_levels(levels)
    _validate_power_ranks(power_ranks)
    _positive_number(starting_distance, "starting_distance")
    results: list[tuple[int, int, DuelResult]] = []
    for rank in power_ranks:
        for level in levels:
            assassin = progression_build("assassin", level, rank)
            warlock = progression_build("warlock", level, rank)
            duel = DuelConfig(
                left=CombatantConfig("assassin", "assassin", assassin),
                right=CombatantConfig("warlock", "warlock", warlock),
                starting_distance=starting_distance,
                max_ticks=max_ticks,
                seed=seed,
            )
            results.append((level, rank, run_duel(duel)))
    return tuple(results)


def progression_duel_matrix(
    *,
    levels: tuple[int, ...] = _DEFAULT_LEVELS,
    power_ranks: tuple[int, ...] = _DEFAULT_POWER_RANKS,
    starting_distances: tuple[float, ...] = (15.0, 60.0, 110.0),
    seeds: tuple[int, ...] = (1,),
    max_ticks: int = 1_200,
) -> tuple[ProgressionMatrixCell, ...]:
    """Aggregate matched progression duels across range and deterministic seed brackets."""

    _validate_levels(levels)
    _validate_power_ranks(power_ranks)
    if not starting_distances:
        raise ValueError("starting_distances must not be empty")
    for distance in starting_distances:
        _positive_number(distance, "starting distance")
    if not seeds:
        raise ValueError("seeds must not be empty")
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seeds must be non-negative integers")

    cells: list[ProgressionMatrixCell] = []
    for level in levels:
        for rank in power_ranks:
            assassin = progression_build("assassin", level, rank)
            warlock = progression_build("warlock", level, rank)
            for distance in starting_distances:
                results = tuple(
                    run_duel(
                        DuelConfig(
                            left=CombatantConfig("assassin", "assassin", assassin),
                            right=CombatantConfig("warlock", "warlock", warlock),
                            starting_distance=distance,
                            max_ticks=max_ticks,
                            seed=seed,
                        )
                    )
                    for seed in seeds
                )
                cells.append(
                    ProgressionMatrixCell(
                        level=level,
                        power_rank=rank,
                        starting_distance=distance,
                        matches=len(results),
                        assassin_wins=sum(
                            result.winner_entity_id == "assassin" for result in results
                        ),
                        warlock_wins=sum(
                            result.winner_entity_id == "warlock" for result in results
                        ),
                        draws=sum(result.winner_entity_id is None for result in results),
                        time_limits=sum(
                            result.reason is TerminationReason.TIME_LIMIT for result in results
                        ),
                        mean_ticks=fmean(result.ticks for result in results),
                        unique_trace_count=len({result.trace_digest for result in results}),
                        sample=results[0],
                    )
                )
    return tuple(cells)


def progression_build(profession: str, level: int, rank: int) -> CharacterBuild:
    """Build an explicit equal-rank bracket, clamping powers with smaller rank caps."""

    try:
        power_limits = _POWER_MAXIMUMS[profession]
    except KeyError as exc:
        raise ValueError(f"unsupported duel profession: {profession}") from exc
    if isinstance(level, bool) or not isinstance(level, int) or level < 1:
        raise ValueError("level must be a positive integer")
    if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank <= 40:
        raise ValueError("rank must be an integer between zero and 40")
    if profession == "assassin":
        skills = (("shadowmastery", 200), ("sorcery", 1), ("stalk", 1))
    else:
        skills = (("warlockry", 200),)
    return CharacterBuild(
        profession=profession,
        level=level,
        skill_ranks=skills,
        power_ranks=tuple(
            (action_key, min(rank, maximum_rank)) for action_key, maximum_rank in power_limits
        ),
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
    tags = set(config.tags)
    if config.build.profession != "open":
        tags.add(f"profession.{config.build.profession}")
    if config.build.profession == "assassin":
        tags.update(("equipment.melee_weapon", "power.stalk"))
    if config.action_keys_override is None:
        action_keys = ruleset.action_keys_for(config.build)
    else:
        compiled_keys = {
            record.action_key for record in ruleset.records if record.action is not None
        }
        unknown = set(config.action_keys_override) - compiled_keys
        if unknown:
            raise ValueError(
                "action override contains unknown or unresolved actions: "
                + ", ".join(sorted(unknown))
            )
        action_keys = tuple(sorted(config.action_keys_override))
    for action_key in action_keys:
        action = ruleset.record(action_key).action
        if action is None:
            raise ValueError(f"action override is unresolved: {action_key}")
        tags.update(f"capability.{tag}" for tag in action.tags)
    scalar_values = {
        "health": config.health,
        "mana": config.mana,
        "stamina": config.stamina,
        "move_speed": config.move_speed,
    }
    scalar_values.update(dict(config.extra_scalars))
    initial_effects: dict[str, ActiveEffectState] = {}
    for trigger_key in config.initial_trigger_keys:
        trigger = ruleset.catalog.trigger_for_effect(trigger_key)
        if trigger is None:
            raise ValueError(f"unknown initial trigger key: {trigger_key}")
        storage_key = f"PersistentTrigger:{trigger_key}"
        initial_effects[storage_key] = ActiveEffectState(
            effect_key=trigger_key,
            source_entity_id=config.entity_id,
            magnitude=1.0,
            expires_at_ms=(1 << 63) - 1,
            stacking_key=storage_key,
            tags={"trigger.passive"},
        )
    return EntityState(
        entity_id=config.entity_id,
        life_id=f"{config.entity_id}:1",
        kind=EntityKind.ACTOR,
        team_id=config.team_id,
        position=position,
        scalars=scalar_values,
        maximums={
            "health": config.health,
            "mana": config.mana,
            "stamina": config.stamina,
        },
        tags=tags,
        action_keys=action_keys,
        effects=initial_effects,
    )


def _combatant_result(
    config: CombatantConfig, state: EntityState, events: list[Event]
) -> CombatantResult:
    action_counts: dict[str, int] = {}
    trigger_counts: dict[str, int] = {}
    damage_dealt = 0.0
    healing_received = 0.0
    mana_spent = 0.0
    stamina_spent = 0.0
    rejected_actions = 0
    attacks_attempted = 0
    weapon_hits = 0
    weapon_misses = 0
    passive_defenses = 0
    damage_absorbed = 0.0
    for event in events:
        scalars = {scalar.name: scalar.value for scalar in event.scalars}
        if event.kind == EventKind.ACTION_STARTED and event.source_entity_id == config.entity_id:
            if event.action_key is not None:
                action_counts[event.action_key] = action_counts.get(event.action_key, 0) + 1
        elif event.kind == EventKind.ATTACK_ROLLED and event.source_entity_id == config.entity_id:
            attacks_attempted += 1
            if "result.hit_roll" in event.tags:
                weapon_hits += 1
            else:
                weapon_misses += 1
        elif (
            event.kind == EventKind.PASSIVE_DEFENSE_TRIGGERED
            and event.target_entity_id == config.entity_id
        ):
            passive_defenses += 1
        elif (
            event.kind == EventKind.ABSORBER_CONSUMED and event.target_entity_id == config.entity_id
        ):
            damage_absorbed += scalars.get("absorbed", 0.0)
        elif event.kind == EventKind.TRIGGER_FIRED and event.source_entity_id == config.entity_id:
            trigger_tag = next((tag for tag in event.tags if tag.startswith("trigger.")), None)
            if trigger_tag is not None:
                trigger_key = trigger_tag.removeprefix("trigger.")
                trigger_counts[trigger_key] = trigger_counts.get(trigger_key, 0) + 1
        elif event.kind == EventKind.DAMAGE_APPLIED and event.source_entity_id == config.entity_id:
            damage_dealt += scalars.get("effective", 0.0)
        elif (
            event.kind == EventKind.RESOURCE_RESTORED
            and event.target_entity_id == config.entity_id
            and "resource.health" in event.tags
        ):
            healing_received += scalars.get("effective", 0.0)
        elif event.kind == "resource_spent" and event.source_entity_id == config.entity_id:
            mana_spent += scalars.get("mana", 0.0)
            stamina_spent += scalars.get("stamina", 0.0)
        elif event.kind == EventKind.ACTION_REJECTED and event.source_entity_id == config.entity_id:
            rejected_actions += 1
    return CombatantResult(
        entity_id=config.entity_id,
        profession=config.build.profession,
        level=config.build.level,
        power_ranks=tuple(sorted(config.build.power_ranks)),
        available_actions=tuple(sorted(state.action_keys)),
        alive=state.alive,
        final_health=state.scalars.get("health", 0.0),
        final_mana=state.scalars.get("mana", 0.0),
        final_stamina=state.scalars.get("stamina", 0.0),
        damage_dealt=damage_dealt,
        healing_received=healing_received,
        mana_spent=mana_spent,
        stamina_spent=stamina_spent,
        rejected_actions=rejected_actions,
        attacks_attempted=attacks_attempted,
        weapon_hits=weapon_hits,
        weapon_misses=weapon_misses,
        passive_defenses=passive_defenses,
        damage_absorbed=damage_absorbed,
        actions=tuple(
            ActionCount(action_key, count) for action_key, count in sorted(action_counts.items())
        ),
        triggers=tuple(
            TriggerCount(trigger_key, count)
            for trigger_key, count in sorted(trigger_counts.items())
        ),
    )


def _cancel_dead_actor_schedule(environment: ReferenceEnvironment) -> int:
    """Prevent future resolutions from actors that died on an earlier simulator time."""

    snapshot = environment.snapshot()
    living = {entity.entity_id for entity in snapshot.entities if entity.alive}
    scheduled = tuple(
        item
        for item in snapshot.scheduled
        if item.kind is ScheduledKind.EFFECT_EXPIRY or item.actor_id in living
    )
    removed = len(snapshot.scheduled) - len(scheduled)
    if removed:
        environment.restore(replace(snapshot, scheduled=scheduled))
    return removed


def _trace_digest(events: list[Event]) -> str:
    semantic_trace = [
        {
            "kind": event.kind,
            "tick": event.tick,
            "sim_time_ms": event.sim_time_ms,
            "source": event.source_entity_id,
            "target": event.target_entity_id,
            "action": event.action_key,
            "scalars": [(item.name, item.value) for item in event.scalars],
            "tags": list(event.tags),
        }
        for event in events
    ]
    encoded = json.dumps(semantic_trace, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _validate_levels(levels: tuple[int, ...]) -> None:
    if not levels:
        raise ValueError("levels must not be empty")
    for level in levels:
        if isinstance(level, bool) or not isinstance(level, int) or level < 1:
            raise ValueError("levels must be positive integers")


def _validate_power_ranks(power_ranks: tuple[int, ...]) -> None:
    if not power_ranks:
        raise ValueError("power_ranks must not be empty")
    for rank in power_ranks:
        if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank <= 40:
            raise ValueError("power ranks must be integers between zero and 40")


def _scalar(values: tuple[NamedScalar, ...], name: str) -> float:
    return next((item.value for item in values if item.name == name), 0.0)


def _optional_scalar(values: tuple[NamedScalar, ...], name: str) -> float | None:
    return next((item.value for item in values if item.name == name), None)


def _distance(left: Vector2, right: Vector2) -> float:
    return hypot(left.x - right.x, left.y - right.y)
