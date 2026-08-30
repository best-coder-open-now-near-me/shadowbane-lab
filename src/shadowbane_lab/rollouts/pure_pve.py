"""Direct semantic PvE rollouts without client-adapter acquisition or safety mechanics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from math import ceil

from shadowbane_lab.protocol import EntityKind, Event, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.rollouts.nearby_mob import NearbyMobSimulationConfig
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    DamageType,
    DealDamage,
    EntityState,
    PhaseKind,
    ReferenceEnvironment,
    SubjectRef,
    TargetingSpec,
    UniformIntegerAmount,
)

_PLAYER_ID = "player"
_MOB_ID = "mob"
_BASIC_ATTACK = "shadowbane.basic_attack"
_TICK_DURATION_MS = 200
_MAX_BATCH_EPISODES = 1_000_000


class PurePvETerminationReason(StrEnum):
    MOB_DEFEATED = "mob_defeated"
    TICK_LIMIT = "tick_limit"


@dataclass(frozen=True, slots=True)
class PurePvEEncounterResult:
    profile_id: str
    seed: int
    reason: PurePvETerminationReason
    killed: bool
    ticks: int
    kill_time_ms: int | None
    attack_rolls: tuple[float, ...]
    effective_damage: tuple[float, ...]
    target_final_health: float
    player_final_health: float
    experience_earned: float
    rejected_actions: int
    total_events: int

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "seed": self.seed,
            "reason": self.reason.value,
            "killed": self.killed,
            "ticks": self.ticks,
            "kill_time_ms": self.kill_time_ms,
            "attack_rolls": list(self.attack_rolls),
            "effective_damage": list(self.effective_damage),
            "target_final_health": self.target_final_health,
            "player_final_health": self.player_final_health,
            "experience_earned": self.experience_earned,
            "rejected_actions": self.rejected_actions,
            "total_events": self.total_events,
        }


@dataclass(frozen=True, slots=True)
class CountBucket:
    value: float
    count: int

    def as_dict(self) -> dict[str, float | int]:
        return {"value": self.value, "count": self.count}


@dataclass(frozen=True, slots=True)
class PurePvEBatchResult:
    profile_id: str
    seed_start: int
    episodes: int
    kills: int
    timeouts: int
    kill_rate: float
    mean_kill_time_ms: float | None
    minimum_kill_time_ms: int | None
    p50_kill_time_ms: int | None
    p90_kill_time_ms: int | None
    p99_kill_time_ms: int | None
    maximum_kill_time_ms: int | None
    mean_attacks_to_kill: float | None
    attacks_to_kill: tuple[CountBucket, ...]
    kill_times_ms: tuple[CountBucket, ...]
    damage_rolls: tuple[CountBucket, ...]
    total_experience: float
    episode_results: tuple[PurePvEEncounterResult, ...]
    evidence: tuple[str, ...]
    assumptions: tuple[str, ...]

    def as_dict(self, *, include_episodes: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "profile_id": self.profile_id,
            "seed_start": self.seed_start,
            "episodes": self.episodes,
            "kills": self.kills,
            "timeouts": self.timeouts,
            "kill_rate": self.kill_rate,
            "mean_kill_time_ms": self.mean_kill_time_ms,
            "minimum_kill_time_ms": self.minimum_kill_time_ms,
            "p50_kill_time_ms": self.p50_kill_time_ms,
            "p90_kill_time_ms": self.p90_kill_time_ms,
            "p99_kill_time_ms": self.p99_kill_time_ms,
            "maximum_kill_time_ms": self.maximum_kill_time_ms,
            "mean_attacks_to_kill": self.mean_attacks_to_kill,
            "attacks_to_kill": [item.as_dict() for item in self.attacks_to_kill],
            "kill_times_ms": [item.as_dict() for item in self.kill_times_ms],
            "damage_rolls": [item.as_dict() for item in self.damage_rolls],
            "total_experience": self.total_experience,
            "retained_episode_results": len(self.episode_results),
            "evidence": list(self.evidence),
            "assumptions": list(self.assumptions),
        }
        if include_episodes:
            result["episode_results"] = [item.as_dict() for item in self.episode_results]
        return result


def run_pure_pve_encounter(
    config: NearbyMobSimulationConfig,
) -> PurePvEEncounterResult:
    """Attack one known hostile semantic entity until death or the virtual tick limit."""

    if not isinstance(config, NearbyMobSimulationConfig):
        raise ValueError("config must be a NearbyMobSimulationConfig")
    environment = _environment(config)
    events: list[Event] = []
    attack_rolls: list[float] = []
    effective_damage: list[float] = []
    rejected_actions = 0
    kill_time_ms: int | None = None
    reason = PurePvETerminationReason.TICK_LIMIT

    for step_number in range(config.max_ticks):
        exchange = environment.exchange(_PLAYER_ID)
        matches = tuple(
            item
            for item in exchange.affordances.affordances
            if item.action_key == _BASIC_ATTACK and item.binding.target_entity_id == _MOB_ID
        )
        decisions = ()
        if len(matches) == 1:
            decisions = (
                exchange.decision(
                    matches[0].affordance_id,
                    f"pure-pve:{config.seed}:{step_number}",
                ),
            )
        batch = environment.step(
            decisions,
            truncated=step_number == config.max_ticks - 1,
        )
        events.extend(batch.events)
        for event in batch.events:
            if (
                event.kind == EventKind.DAMAGE_APPLIED
                and event.source_entity_id == _PLAYER_ID
                and event.target_entity_id == _MOB_ID
            ):
                scalars = {item.name: item.value for item in event.scalars}
                attack_rolls.append(scalars["requested"])
                effective_damage.append(scalars["effective"])
            elif event.kind == EventKind.ACTION_REJECTED:
                rejected_actions += 1
            elif event.kind == EventKind.ENTITY_DIED and event.target_entity_id == _MOB_ID:
                kill_time_ms = event.sim_time_ms
        if batch.world_terminated:
            reason = PurePvETerminationReason.MOB_DEFEATED
            break

    killed = reason is PurePvETerminationReason.MOB_DEFEATED
    return PurePvEEncounterResult(
        profile_id=config.profile_id,
        seed=config.seed,
        reason=reason,
        killed=killed,
        ticks=environment.tick,
        kill_time_ms=kill_time_ms,
        attack_rolls=tuple(attack_rolls),
        effective_damage=tuple(effective_damage),
        target_final_health=environment.entity(_MOB_ID).scalars["health"],
        player_final_health=environment.entity(_PLAYER_ID).scalars["health"],
        experience_earned=config.experience_reward if killed else 0.0,
        rejected_actions=rejected_actions,
        total_events=len(events),
    )


def run_pure_pve_batch(
    config: NearbyMobSimulationConfig,
    *,
    episodes: int,
    seed_start: int = 0,
    retain_episode_results: bool = False,
) -> PurePvEBatchResult:
    """Run a compact contiguous-seed PvE batch with optional exact episode retention."""

    if not isinstance(config, NearbyMobSimulationConfig):
        raise ValueError("config must be a NearbyMobSimulationConfig")
    if (
        isinstance(episodes, bool)
        or not isinstance(episodes, int)
        or not 1 <= episodes <= _MAX_BATCH_EPISODES
    ):
        raise ValueError(f"episodes must be an integer between 1 and {_MAX_BATCH_EPISODES}")
    if isinstance(seed_start, bool) or not isinstance(seed_start, int) or seed_start < 0:
        raise ValueError("seed_start must be a non-negative integer")
    if not isinstance(retain_episode_results, bool):
        raise ValueError("retain_episode_results must be a boolean")

    retained: list[PurePvEEncounterResult] = []
    kill_time_counts: Counter[float] = Counter()
    attack_counts: Counter[float] = Counter()
    roll_counts: Counter[float] = Counter()
    kills = 0
    total_kill_time = 0
    total_attacks = 0
    total_experience = 0.0

    for seed in range(seed_start, seed_start + episodes):
        result = run_pure_pve_encounter(replace(config, seed=seed))
        if retain_episode_results:
            retained.append(result)
        roll_counts.update(result.attack_rolls)
        total_experience += result.experience_earned
        if not result.killed:
            continue
        if result.kill_time_ms is None:
            raise RuntimeError("completed pure PvE encounter is missing its kill time")
        kills += 1
        total_kill_time += result.kill_time_ms
        attacks = len(result.attack_rolls)
        total_attacks += attacks
        kill_time_counts[float(result.kill_time_ms)] += 1
        attack_counts[float(attacks)] += 1

    return PurePvEBatchResult(
        profile_id=config.profile_id,
        seed_start=seed_start,
        episodes=episodes,
        kills=kills,
        timeouts=episodes - kills,
        kill_rate=kills / episodes,
        mean_kill_time_ms=total_kill_time / kills if kills else None,
        minimum_kill_time_ms=(int(min(kill_time_counts)) if kill_time_counts else None),
        p50_kill_time_ms=_counter_percentile(kill_time_counts, 0.50),
        p90_kill_time_ms=_counter_percentile(kill_time_counts, 0.90),
        p99_kill_time_ms=_counter_percentile(kill_time_counts, 0.99),
        maximum_kill_time_ms=(int(max(kill_time_counts)) if kill_time_counts else None),
        mean_attacks_to_kill=total_attacks / kills if kills else None,
        attacks_to_kill=_counter_buckets(attack_counts),
        kill_times_ms=_counter_buckets(kill_time_counts),
        damage_rolls=_counter_buckets(roll_counts),
        total_experience=total_experience,
        episode_results=tuple(retained),
        evidence=config.evidence,
        assumptions=config.assumptions,
    )


def _environment(config: NearbyMobSimulationConfig) -> ReferenceEnvironment:
    action = ActionSpec(
        action_key=_BASIC_ATTACK,
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=3.0,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=(
                    DealDamage(
                        SubjectRef.TARGET,
                        UniformIntegerAmount(
                            config.attack_damage_minimum,
                            config.attack_damage_maximum,
                        ),
                        DamageType.CRUSH,
                    ),
                ),
            ),
        ),
        cooldown_ms=config.attack_interval_ms,
        tags=("combat", "attack", "melee", "physical"),
    )
    return ReferenceEnvironment(
        ActionCatalog((action,)),
        (
            EntityState(
                entity_id=_PLAYER_ID,
                life_id="player:1",
                kind=EntityKind.ACTOR,
                team_id="player",
                position=Vector2(0.0, 0.0),
                scalars={
                    "health": config.player_current_health,
                    "mana": config.player_current_mana,
                    "stamina": config.player_current_stamina,
                },
                maximums={
                    "health": config.player_maximum_health,
                    "mana": config.player_maximum_mana,
                    "stamina": config.player_maximum_stamina,
                },
                action_keys=(_BASIC_ATTACK,),
            ),
            EntityState(
                entity_id=_MOB_ID,
                life_id="mob:1",
                kind=EntityKind.ACTOR,
                team_id="mob",
                position=Vector2(1.0, 0.0),
                scalars={"health": config.mob_health},
                maximums={"health": config.mob_health},
            ),
        ),
        seed=config.seed,
        tick_duration_ms=_TICK_DURATION_MS,
        terminate_on_last_team=True,
    )


def _counter_buckets(counts: Counter[float]) -> tuple[CountBucket, ...]:
    return tuple(CountBucket(value, counts[value]) for value in sorted(counts))


def _counter_percentile(counts: Counter[float], percentile: float) -> int | None:
    total = sum(counts.values())
    if total == 0:
        return None
    threshold = ceil(percentile * total)
    cumulative = 0
    for value in sorted(counts):
        cumulative += counts[value]
        if cumulative >= threshold:
            return int(value)
    raise RuntimeError("percentile counter traversal did not reach its threshold")
