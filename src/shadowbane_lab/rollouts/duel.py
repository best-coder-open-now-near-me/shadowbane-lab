"""Progression-aware deterministic duel rollouts over semantic affordances."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from math import hypot
from statistics import fmean

from shadowbane_lab.combat import CombatSheet, StackPriority
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
from shadowbane_lab.rollouts.ruleset import load_assassin_warlock_duel_ruleset
from shadowbane_lab.rulesets import CharacterBuild, CompiledRuleset, load_shadowbane_vertical_slice
from shadowbane_lab.sim import (
    RANGE_MAXIMUM_FEATURE,
    ActionCatalog,
    ActiveEffectState,
    CombatStance,
    DamageBreakpoint,
    AgentExchange,
    EntityState,
    RangeBand,
    ReferenceEnvironment,
    ScheduledKind,
    close_range_action,
)
from shadowbane_lab.sim.actions import EffectModifier, PeriodicPulse

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"
SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
FADE = "shadowbane.assassin.fade"
BACKSTAB = "shadowbane.assassin.backstab"
INVISIBILITY = "shadowbane.assassin.invisibility"
SHADOW_MANTLE = "shadowbane.assassin.shadow_mantle"
PASSWALL = "shadowbane.assassin.passwall"
MIND_STRIKE = "shadowbane.warlock.mind_strike"
MIND_SNARE = "shadowbane.warlock.mind_snare"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"
LEVITATION = "shadowbane.warlock.levitation"
STEAL_BREATH = "shadowbane.assassin.steal_breath"
PSYCHIC_SHIELD = "shadowbane.warlock.psychic_shield"
MOVE = "shadowbane.move"
BASIC_ATTACK = "shadowbane.basic_attack"
_DIRECTIONAL_MOVE = "shadowbane.move"
_CLOSE_RANGE = "sim.range.close"
_MELEE_RANGE = 3.0
_DEFAULT_LEVELS = (10, 15, 18, 19, 22, 26, 28, 42, 75)
_DEFAULT_POWER_RANKS = (0, 10, 20, 40)
_POWER_MAXIMUMS = {
    "assassin": (
        (SHADOW_BOLT, 40),
        (SHADOW_TOUCH, 40),
        (STEAL_BREATH, 40),
        (FADE, 20),
        (BACKSTAB, 40),
        (INVISIBILITY, 20),
        (SHADOW_MANTLE, 40),
    ),
    "warlock": (
        (MIND_STRIKE, 40),
        (MIND_SNARE, 40),
        (PSYCHIC_HEALING, 40),
        (PSYCHIC_SHIELD, 40),
    ),
}


def _positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")


@dataclass(frozen=True, slots=True)
class InitialEffectConfig:
    """Immutable combat-start effect state with simulator-native modifiers."""

    effect_key: str
    duration_ms: int | None = None
    magnitude: float = 1.0
    stacking_key: str | None = None
    tags: tuple[str, ...] = ()
    modifiers: tuple[EffectModifier, ...] = ()
    stack_order: int = 0
    trains: int = 0
    stack_priority: StackPriority = StackPriority.ALWAYS

    def __post_init__(self) -> None:
        if not isinstance(self.effect_key, str) or not self.effect_key.strip():
            raise ValueError("effect_key must be a non-empty string")
        if self.duration_ms is not None and (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or self.duration_ms < 1
        ):
            raise ValueError("duration_ms must be a positive integer or null")
        if isinstance(self.magnitude, bool) or not isinstance(
            self.magnitude, (int, float)
        ):
            raise ValueError("magnitude must be a number")
        if self.stacking_key is not None and (
            not isinstance(self.stacking_key, str) or not self.stacking_key.strip()
        ):
            raise ValueError("stacking_key must be a non-empty string or null")
        if len(self.tags) != len(set(self.tags)) or any(
            not isinstance(tag, str) or not tag.strip() for tag in self.tags
        ):
            raise ValueError("initial effect tags must be unique non-empty strings")
        for value, field_name in (
            (self.stack_order, "stack_order"),
            (self.trains, "trains"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.stack_priority, StackPriority):
            raise ValueError("stack_priority must be a StackPriority")
        # ActiveEffectState owns validation of the closed modifier union and its state keys.
        ActiveEffectState(
            effect_key=self.effect_key,
            source_entity_id="initial-effect-validator",
            magnitude=float(self.magnitude),
            expires_at_ms=self.duration_ms or (1 << 63) - 1,
            stacking_key=self.stacking_key,
            tags=set(self.tags),
            modifiers=self.modifiers,
            modifier_values={
                modifier.state_key: 0.0
                for modifier in self.modifiers
                if isinstance(modifier, DamageBreakpoint)
            },
            stack_order=self.stack_order,
            trains=self.trains,
            stack_priority=self.stack_priority,
        )
        if self.duration_ms is not None and any(
            isinstance(modifier, PeriodicPulse)
            and modifier.duration_ms > self.duration_ms
            for modifier in self.modifiers
        ):
            raise ValueError("periodic pulses must complete within the initial effect duration")


@dataclass(frozen=True, slots=True)
class CombatantConfig:
    entity_id: str
    team_id: str
    build: CharacterBuild
    health: float = 100.0
    mana: float = 200.0
    stamina: float = 100.0
    move_speed: float = 30.0
    tags: tuple[str, ...] = ()
    extra_scalars: tuple[tuple[str, float], ...] = ()
    initial_trigger_keys: tuple[str, ...] = ()
    initial_effects: tuple[InitialEffectConfig, ...] = ()
    initial_stance: CombatStance = CombatStance.NORMAL
    action_keys_override: tuple[str, ...] | None = None

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
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("tags must not contain duplicates")
        for tag in self.tags:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError("tags must contain non-empty strings")
        scalar_keys = tuple(key for key, _ in self.extra_scalars)
        if len(scalar_keys) != len(set(scalar_keys)):
            raise ValueError("extra_scalars must not contain duplicate keys")
        reserved = {"health", "mana", "stamina", "move_speed"}
        if set(scalar_keys) & reserved:
            raise ValueError("extra_scalars cannot replace reserved body scalars")
        for key, value in self.extra_scalars:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("extra scalar keys must be non-empty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("extra scalar values must be numbers")
        if len(self.initial_trigger_keys) != len(set(self.initial_trigger_keys)):
            raise ValueError("initial_trigger_keys must not contain duplicates")
        for trigger_key in self.initial_trigger_keys:
            if not isinstance(trigger_key, str) or not trigger_key.strip():
                raise ValueError("initial trigger keys must be non-empty strings")
        if any(not isinstance(effect, InitialEffectConfig) for effect in self.initial_effects):
            raise ValueError("initial_effects must contain InitialEffectConfig values")
        storage_keys = tuple(
            effect.stacking_key or effect.effect_key for effect in self.initial_effects
        )
        if len(storage_keys) != len(set(storage_keys)):
            raise ValueError("initial_effects must not share storage keys")
        if not isinstance(self.initial_stance, CombatStance):
            raise ValueError("initial_stance must be a CombatStance")
        if self.action_keys_override is not None:
            if len(self.action_keys_override) != len(set(self.action_keys_override)):
                raise ValueError("action_keys_override must not contain duplicates")
            if any(
                not isinstance(action_key, str) or not action_key.strip()
                for action_key in self.action_keys_override
            ):
                raise ValueError("action overrides must contain non-empty strings")


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
                    "actions": {
                        action.action_key: action.count for action in item.actions
                    },
                    "triggers": {
                        trigger.trigger_key: trigger.count for trigger in item.triggers
                    },
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


@dataclass(frozen=True, slots=True)
class VerifiedCombatantConfig:
    entity_id: str
    team_id: str
    sheet: CombatSheet
    build: CharacterBuild
    initial_effects: tuple[InitialEffectConfig, ...] = ()
    initial_stance: CombatStance = CombatStance.NORMAL

    def __post_init__(self) -> None:
        for value, name in ((self.entity_id, "entity_id"), (self.team_id, "team_id")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.sheet, CombatSheet):
            raise ValueError("sheet must be a CombatSheet")
        if not isinstance(self.build, CharacterBuild):
            raise ValueError("build must be a CharacterBuild")
        if any(not isinstance(effect, InitialEffectConfig) for effect in self.initial_effects):
            raise ValueError("initial_effects must contain InitialEffectConfig values")
        storage_keys = tuple(
            effect.stacking_key or effect.effect_key for effect in self.initial_effects
        )
        if len(storage_keys) != len(set(storage_keys)):
            raise ValueError("initial_effects must not share storage keys")
        if not isinstance(self.initial_stance, CombatStance):
            raise ValueError("initial_stance must be a CombatStance")


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
        if "control.power_block" in actor.tags:
            return None
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

        if "stealth" in tags or "invisibility" in tags:
            if (
                "capability.stealth_required" not in actor_tags
                or "visibility.invisible" in actor_tags
            ):
                return float("-inf")
            enemies = tuple(
                entity
                for entity in exchange.observation.entities
                if entity.relation is Relation.ENEMY
            )
            if not enemies:
                return float("-inf")
            actor = next(
                entity
                for entity in exchange.observation.entities
                if entity.relation is Relation.SELF
            )
            distance = min(_distance(actor.position, enemy.position) for enemy in enemies)
            if distance > 15.0:
                return -25.0
            base = 24.0 if affordance.action_key == INVISIBILITY else 21.0
            return base - commitment_ms / 1_000.0

        if "armed_trigger" in tags:
            trigger_damage = features.get("expected_trigger_damage", 0.0)
            trigger_control_ms = features.get(
                "expected_trigger_control_duration_ms", 0.0
            )
            followup_ms = max(
                1.0, features.get("expected_followup_commitment_ms", 1_000.0)
            )
            return (
                8.0
                + trigger_damage * 1_000.0 / (commitment_ms + followup_ms)
                + trigger_control_ms / 300.0
            )

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


def run_duel(
    config: DuelConfig, *, ruleset: CompiledRuleset | None = None
) -> DuelResult:
    """Run one deterministic duel until one team remains or the tick budget expires."""

    rank_overrides = _merge_rank_overrides(config.left.build, config.right.build)
    if ruleset is None:
        ruleset = load_assassin_warlock_duel_ruleset(rank_overrides=rank_overrides)
    else:
        for action_key, rank in rank_overrides.items():
            record = ruleset.record(action_key)
            if record.rank != rank:
                raise ValueError(f"{action_key} was compiled at rank {record.rank}, not {rank}")
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
        batch = environment.step(
            tuple(decisions), truncated=step_number == config.max_ticks - 1
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
        _combatant_result(item, states[item.entity_id], events) for item in combatants
    )
    final_distance = _distance(
        states[config.left.entity_id].position,
        states[config.right.entity_id].position,
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
    ruleset = load_assassin_warlock_duel_ruleset(rank_overrides=rank_overrides)
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
    _apply_initial_state(
        left_entity,
        config.left.initial_effects,
        config.left.initial_stance,
    )
    _apply_initial_state(
        right_entity,
        config.right.initial_effects,
        config.right.initial_stance,
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
    final_distance = _distance(
        states[config.left.entity_id].position,
        states[config.right.entity_id].position,
    )
    duel = DuelResult(
        winner_entity_id=winner,
        reason=reason,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        seed=seed,
        starting_distance=config.starting_distance,
        final_distance=final_distance,
        total_events=len(events),
        cancelled_scheduled_items=0,
        trace_digest=_trace_digest(events),
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
    """Aggregate matched progression duels across range and deterministic seeds."""

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
                            result.reason is TerminationReason.TIME_LIMIT
                            for result in results
                        ),
                        mean_ticks=fmean(result.ticks for result in results),
                        unique_trace_count=len(
                            {result.trace_digest for result in results}
                        ),
                        sample=results[0],
                    )
                )
    return tuple(cells)


def progression_build(profession: str, level: int, rank: int) -> CharacterBuild:
    """Build an explicit equal-rank bracket, respecting individual power caps."""

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
            (action_key, min(rank, maximum_rank))
            for action_key, maximum_rank in power_limits
        ),
    )


def _progression_build(profession: str, level: int, rank: int) -> CharacterBuild:
    """Backward-compatible private alias for older rollout callers."""

    return progression_build(profession, level, rank)


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
    action_keys = tuple(
        _CLOSE_RANGE if key == _DIRECTIONAL_MOVE else key for key in action_keys
    )
    for action_key in action_keys:
        if action_key == _CLOSE_RANGE:
            tags.add("capability.range.close")
            continue
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
    entity = EntityState(
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
        stance=config.initial_stance,
    )
    _apply_initial_state(entity, config.initial_effects, config.initial_stance)
    return entity


def _apply_initial_state(
    entity: EntityState,
    effects: tuple[InitialEffectConfig, ...],
    stance: CombatStance,
) -> None:
    entity.stance = stance
    for index, effect in enumerate(effects):
        storage_key = effect.stacking_key or effect.effect_key
        if storage_key in entity.effects:
            raise ValueError(f"duplicate initial effect storage key: {storage_key}")
        entity.effects[storage_key] = ActiveEffectState(
            effect_key=effect.effect_key,
            source_entity_id=entity.entity_id,
            instance_id=f"initial-effect:{entity.entity_id}:{index:04d}",
            magnitude=effect.magnitude,
            expires_at_ms=effect.duration_ms or (1 << 63) - 1,
            stacking_key=effect.stacking_key,
            tags=set(effect.tags),
            modifiers=effect.modifiers,
            modifier_values={
                modifier.state_key: 0.0
                for modifier in effect.modifiers
                if isinstance(modifier, DamageBreakpoint)
            },
            stack_order=effect.stack_order,
            trains=effect.trains,
            stack_priority=effect.stack_priority,
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
            event.kind == EventKind.ABSORBER_CONSUMED
            and event.target_entity_id == config.entity_id
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
    """Prevent dead actors from resolving future actions while preserving world effects."""

    snapshot = environment.snapshot()
    living = {entity.entity_id for entity in snapshot.entities if entity.alive}
    persistent_kinds = {ScheduledKind.EFFECT_EXPIRY, ScheduledKind.EFFECT_PULSE}
    scheduled = tuple(
        item
        for item in snapshot.scheduled
        if item.kind in persistent_kinds or item.actor_id in living
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
