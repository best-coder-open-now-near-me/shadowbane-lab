"""General retained-target PvE policy over a sourced proc-Assassin action set."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import StrEnum
from math import ceil, hypot

from shadowbane_lab.progression import (
    StatLine,
    load_wonderbane_irekei_proc_profile,
    spell_damage_range,
)
from shadowbane_lab.protocol import (
    DecisionMessage,
    EntityKind,
    Event,
    EventKind,
    NamedScalar,
    Relation,
    TargetKind,
    Vector2,
)
from shadowbane_lab.pve.calibration import PvECombatCalibration
from shadowbane_lab.rulesets import load_shadowbane_vertical_slice
from shadowbane_lab.sim import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    AgentExchange,
    ChanceGate,
    DamageType,
    DealDamage,
    EntityState,
    PhaseKind,
    RangeBand,
    ReferenceEnvironment,
    SubjectRef,
    TargetingSpec,
    UniformAmount,
    UniformIntegerAmount,
    WeightedAmount,
    close_range_action,
)

_PLAYER_ID = "player"
_PLAYER_TEAM = "player"
_MOB_TEAM = "mob"
_DUAL_FIST = "shadowbane.assassin.dual_fist_successful_hit"
_DUAL_FIST_MAXIMUM_RANGE = 3.0
_SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
_CLOSE_RANGE = "sim.range.close"
_MOB_ATTACK = "shadowbane.mob.basic_attack"
_TICK_DURATION_MS = 200
_MAX_BATCH_EPISODES = 1_000_000


def _positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class CampMobConfig:
    entity_id: str
    health: float
    distance: float
    attack_damage_minimum: int = 5
    attack_damage_maximum: int = 10
    attack_interval_ms: int = 2_000

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("entity_id must be a non-empty string")
        _positive_number(self.health, "health")
        _positive_number(self.distance, "distance")
        _positive_integer(self.attack_damage_minimum, "attack_damage_minimum")
        _positive_integer(self.attack_damage_maximum, "attack_damage_maximum")
        if self.attack_damage_maximum <= self.attack_damage_minimum:
            raise ValueError("attack damage maximum must exceed its minimum")
        _positive_integer(self.attack_interval_ms, "attack_interval_ms")


@dataclass(frozen=True, slots=True)
class SmartCampConfig:
    profile_id: str
    stats: StatLine
    mobs: tuple[CampMobConfig, ...]
    player_health: float = 500.0
    player_mana: float = 220.0
    player_stamina: float = 100.0
    player_move_speed: float = 30.0
    player_attack_interval_ms: int = 1_000
    observed_unattributed_damage: WeightedAmount | None = None
    weapon_key: str = "generic_fast_fist"
    proc_effect_keys: tuple[str, ...] = (
        "tier_three_mental",
        "poison_blade_rank_40",
    )
    shadow_touch_rank: int = 40
    max_ticks: int = 1_000
    seed: int = 1
    evidence: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")
        if not isinstance(self.stats, StatLine):
            raise ValueError("stats must be a StatLine")
        if not self.mobs or any(not isinstance(item, CampMobConfig) for item in self.mobs):
            raise ValueError("mobs must contain at least one CampMobConfig")
        mob_ids = tuple(item.entity_id for item in self.mobs)
        if len(mob_ids) != len(set(mob_ids)) or _PLAYER_ID in mob_ids:
            raise ValueError("mob entity ids must be unique and cannot be player")
        for value, field_name in (
            (self.player_health, "player_health"),
            (self.player_mana, "player_mana"),
            (self.player_stamina, "player_stamina"),
            (self.player_move_speed, "player_move_speed"),
        ):
            _positive_number(value, field_name)
        _positive_integer(self.player_attack_interval_ms, "player_attack_interval_ms")
        if self.observed_unattributed_damage is not None and not isinstance(
            self.observed_unattributed_damage,
            WeightedAmount,
        ):
            raise ValueError(
                "observed_unattributed_damage must be a WeightedAmount or null"
            )
        if not isinstance(self.weapon_key, str) or not self.weapon_key.strip():
            raise ValueError("weapon_key must be a non-empty string")
        if not self.proc_effect_keys or len(self.proc_effect_keys) != len(
            set(self.proc_effect_keys)
        ):
            raise ValueError("proc_effect_keys must be non-empty and unique")
        if (
            isinstance(self.shadow_touch_rank, bool)
            or not isinstance(self.shadow_touch_rank, int)
            or not 0 <= self.shadow_touch_rank <= 40
        ):
            raise ValueError("shadow_touch_rank must be an integer in [0, 40]")
        _positive_integer(self.max_ticks, "max_ticks")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")


class SmartCampTerminationReason(StrEnum):
    CAMP_CLEARED = "camp_cleared"
    PLAYER_DEFEATED = "player_defeated"
    TICK_LIMIT = "tick_limit"


@dataclass(frozen=True, slots=True)
class PolicyChoice:
    at_ms: int
    action_key: str
    target_entity_id: str
    target_changed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "at_ms": self.at_ms,
            "action_key": self.action_key,
            "target_entity_id": self.target_entity_id,
            "target_changed": self.target_changed,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ProcOutcome:
    effect_key: str
    checks: int
    triggers: int
    requested_damage: float
    effective_damage: float

    def as_dict(self) -> dict[str, object]:
        return {
            "effect_key": self.effect_key,
            "checks": self.checks,
            "triggers": self.triggers,
            "requested_damage": self.requested_damage,
            "effective_damage": self.effective_damage,
        }


@dataclass(frozen=True, slots=True)
class SmartCampResult:
    profile_id: str
    seed: int
    reason: SmartCampTerminationReason
    ticks: int
    sim_time_ms: int
    player_alive: bool
    player_final_health: float
    player_final_mana: float
    mobs_killed: int
    mobs_total: int
    target_sequence: tuple[str, ...]
    action_counts: tuple[tuple[str, int], ...]
    physical_damage: float
    observed_unattributed_damage: float
    proc_outcomes: tuple[ProcOutcome, ...]
    rejected_actions: int
    choices: tuple[PolicyChoice, ...]
    evidence: tuple[str, ...]
    assumptions: tuple[str, ...]

    def as_dict(self, *, include_choices: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "profile_id": self.profile_id,
            "seed": self.seed,
            "reason": self.reason.value,
            "ticks": self.ticks,
            "sim_time_ms": self.sim_time_ms,
            "player_alive": self.player_alive,
            "player_final_health": self.player_final_health,
            "player_final_mana": self.player_final_mana,
            "mobs_killed": self.mobs_killed,
            "mobs_total": self.mobs_total,
            "target_sequence": list(self.target_sequence),
            "action_counts": dict(self.action_counts),
            "physical_damage": self.physical_damage,
            "observed_unattributed_damage": self.observed_unattributed_damage,
            "proc_outcomes": [item.as_dict() for item in self.proc_outcomes],
            "rejected_actions": self.rejected_actions,
            "retained_choices": len(self.choices),
            "evidence": list(self.evidence),
            "assumptions": list(self.assumptions),
        }
        if include_choices:
            result["choices"] = [item.as_dict() for item in self.choices]
        return result


@dataclass(frozen=True, slots=True)
class SmartCampBatchProcOutcome:
    effect_key: str
    checks: int
    triggers: int
    trigger_rate: float
    requested_damage: float
    effective_damage: float

    def as_dict(self) -> dict[str, object]:
        return {
            "effect_key": self.effect_key,
            "checks": self.checks,
            "triggers": self.triggers,
            "trigger_rate": self.trigger_rate,
            "requested_damage": self.requested_damage,
            "effective_damage": self.effective_damage,
        }


@dataclass(frozen=True, slots=True)
class SmartCampBatchResult:
    profile_id: str
    seed_start: int
    episodes: int
    camps_cleared: int
    player_defeats: int
    timeouts: int
    clear_rate: float
    mean_clear_time_ms: float | None
    p50_clear_time_ms: int | None
    p90_clear_time_ms: int | None
    p99_clear_time_ms: int | None
    mean_remaining_health: float
    action_counts: tuple[tuple[str, int], ...]
    physical_damage: float
    observed_unattributed_damage: float
    proc_outcomes: tuple[SmartCampBatchProcOutcome, ...]
    rejected_actions: int
    episode_results: tuple[SmartCampResult, ...]
    evidence: tuple[str, ...]
    assumptions: tuple[str, ...]

    def as_dict(self, *, include_episodes: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "profile_id": self.profile_id,
            "seed_start": self.seed_start,
            "episodes": self.episodes,
            "camps_cleared": self.camps_cleared,
            "player_defeats": self.player_defeats,
            "timeouts": self.timeouts,
            "clear_rate": self.clear_rate,
            "mean_clear_time_ms": self.mean_clear_time_ms,
            "p50_clear_time_ms": self.p50_clear_time_ms,
            "p90_clear_time_ms": self.p90_clear_time_ms,
            "p99_clear_time_ms": self.p99_clear_time_ms,
            "mean_remaining_health": self.mean_remaining_health,
            "action_counts": dict(self.action_counts),
            "physical_damage": self.physical_damage,
            "observed_unattributed_damage": self.observed_unattributed_damage,
            "proc_outcomes": [item.as_dict() for item in self.proc_outcomes],
            "rejected_actions": self.rejected_actions,
            "retained_episode_results": len(self.episode_results),
            "evidence": list(self.evidence),
            "assumptions": list(self.assumptions),
        }
        if include_episodes:
            result["episode_results"] = [
                item.as_dict(include_choices=True) for item in self.episode_results
            ]
        return result


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: DecisionMessage | None
    choice: PolicyChoice | None


class SmartCampPolicy:
    """Retain one target, open with useful control, then maintain weapon pressure."""

    def __init__(
        self,
        *,
        weapon_action_key: str = _DUAL_FIST,
        control_action_key: str = _SHADOW_TOUCH,
        control_immunity_tag: str = "immunity.stun",
    ) -> None:
        self._weapon_action_key = weapon_action_key
        self._control_action_key = control_action_key
        self._control_immunity_tag = control_immunity_tag
        self._target_entity_id: str | None = None
        self._control_opened_target_ids: set[str] = set()

    def decide(self, exchange: AgentExchange, correlation_id: str) -> PolicyDecision:
        enemies = tuple(
            item
            for item in exchange.observation.entities
            if item.relation is Relation.ENEMY and item.kind is EntityKind.ACTOR
        )
        if not enemies:
            self._target_entity_id = None
            return PolicyDecision(None, None)
        actor = next(
            item
            for item in exchange.observation.entities
            if item.relation is Relation.SELF
        )
        enemy_ids = {item.entity_id for item in enemies}
        target_changed = self._target_entity_id not in enemy_ids
        if target_changed:
            selected = min(
                enemies,
                key=lambda item: (
                    _distance(actor.position, item.position),
                    _scalar(item.scalars, "health"),
                    item.entity_id,
                ),
            )
            self._target_entity_id = selected.entity_id
        assert self._target_entity_id is not None
        target = next(item for item in enemies if item.entity_id == self._target_entity_id)
        target_affordances = tuple(
            item
            for item in exchange.affordances.affordances
            if item.binding.target_entity_id == self._target_entity_id
        )
        control = next(
            (
                item
                for item in target_affordances
                if item.action_key == self._control_action_key
            ),
            None,
        )
        weapon = next(
            (
                item
                for item in target_affordances
                if item.action_key == self._weapon_action_key
            ),
            None,
        )
        movement = next(
            (
                item
                for item in target_affordances
                if item.action_key == _CLOSE_RANGE
            ),
            None,
        )
        selected_affordance = None
        reason = "waiting_on_action_readiness"
        if (
            self._target_entity_id not in self._control_opened_target_ids
            and control is not None
            and self._control_immunity_tag not in target.tags
        ):
            selected_affordance = control
            self._control_opened_target_ids.add(self._target_entity_id)
            reason = "open_with_control"
        elif weapon is not None:
            selected_affordance = weapon
            reason = "maintain_weapon_pressure"
        elif (
            movement is not None
            and _distance(actor.position, target.position) > _DUAL_FIST_MAXIMUM_RANGE
        ):
            selected_affordance = movement
            reason = "close_to_weapon_range"
        if selected_affordance is None:
            return PolicyDecision(None, None)
        decision = exchange.decision(selected_affordance.affordance_id, correlation_id)
        return PolicyDecision(
            decision,
            PolicyChoice(
                at_ms=exchange.observation.sim_time_ms,
                action_key=decision.action_key,
                target_entity_id=self._target_entity_id,
                target_changed=target_changed,
                reason=reason,
            ),
        )


def irekei_proc_assassin_smart_camp_config(
    *, seed: int = 1, max_ticks: int = 1_000
) -> SmartCampConfig:
    """Return an evidence-bearing level-59 proc-Assassin spawn-camp scenario."""

    return SmartCampConfig(
        profile_id="wonderbane.irekei.proc-assassin.smart-camp.v1",
        stats=StatLine(35, 130, 85, 165, 15),
        mobs=(
            CampMobConfig("camp-mob-1", health=180.0, distance=1.0),
            CampMobConfig("camp-mob-2", health=180.0, distance=1.8),
            CampMobConfig("camp-mob-3", health=180.0, distance=2.6),
        ),
        seed=seed,
        max_ticks=max_ticks,
        evidence=(
            "wonderbane.irekei.rogue_assassin.unarmed_proc.v1",
            "morloch-unarmed-weapons-33179",
            "morloch-proc-33392",
            "morloch-assassin-powers-36339",
        ),
        assumptions=(
            "The observed-trait end-state uses 35/130/85/165/15.",
            "Both speed-20 fists are aggregated into one successful hit opportunity per second.",
            "Each successful hit checks the tier-three mental and rank-40 Poison Blade "
            "procs independently at 5%.",
            "Raw 4-16 weapon damage is used without attack-rating, defense, resistance, "
            "or gear modifiers.",
            "Three generic camp mobs begin in melee range with assumed 180 health and "
            "5-10 damage every two seconds.",
            "The policy retains its current living target, selects the nearest replacement, "
            "opens each target once with rank-40 Shadow Touch when stun immunity is absent, "
            "closes to fist range at the simulator's 30-unit movement rate, and otherwise "
            "attacks.",
        ),
    )


def apply_pve_combat_calibration(
    config: SmartCampConfig,
    calibration: PvECombatCalibration,
) -> SmartCampConfig:
    """Replace supported generic camp assumptions with explicit live observations."""

    if not isinstance(config, SmartCampConfig):
        raise ValueError("config must be SmartCampConfig")
    if not isinstance(calibration, PvECombatCalibration):
        raise ValueError("calibration must be PvECombatCalibration")

    observed_health = calibration.target_maximum_health
    observed_damage = calibration.target_damage
    observed_interval = calibration.target_attack_interval_ms
    observed_distance = calibration.engagement_planar_distance
    observed_output = calibration.native_target_health_decrease
    observed_output_interval = calibration.native_target_health_decrease_interval_ms
    if observed_distance is not None and observed_distance.median <= 0:
        observed_distance = None
    calibrated_damage: tuple[int, int] | None = None
    if observed_damage is not None:
        minimum = observed_damage.minimum
        maximum = observed_damage.maximum
        if (
            minimum >= 1
            and minimum.is_integer()
            and maximum.is_integer()
            and maximum > minimum
        ):
            calibrated_damage = (int(minimum), int(maximum))
    calibrated_interval = None
    if observed_interval is not None:
        calibrated_interval = max(
            _TICK_DURATION_MS,
            round(observed_interval.median / _TICK_DURATION_MS) * _TICK_DURATION_MS,
        )
    player_attack_interval = config.player_attack_interval_ms
    if observed_output_interval is not None:
        player_attack_interval = max(
            _TICK_DURATION_MS,
            round(observed_output_interval.median / _TICK_DURATION_MS)
            * _TICK_DURATION_MS,
        )
    observed_unattributed_damage = config.observed_unattributed_damage
    residual_method: str | None = None
    if observed_output is not None:
        _, mechanistic_expected_damage = _mechanistic_weapon_effects(config)
        residual_mean = observed_output.mean - mechanistic_expected_damage
        if residual_mean > 0:
            if observed_output.minimum > mechanistic_expected_damage:
                observed_unattributed_damage = WeightedAmount(
                    tuple(
                        (value - mechanistic_expected_damage, frequency)
                        for value, frequency in observed_output.histogram
                    )
                )
                residual_method = "histogram"
            else:
                observed_unattributed_damage = WeightedAmount(
                    ((residual_mean, observed_output.count),)
                )
                residual_method = "mean"

    mobs = tuple(
        replace(
            mob,
            health=(mob.health if observed_health is None else observed_health.median),
            distance=(mob.distance if observed_distance is None else observed_distance.median),
            attack_damage_minimum=(
                mob.attack_damage_minimum
                if calibrated_damage is None
                else calibrated_damage[0]
            ),
            attack_damage_maximum=(
                mob.attack_damage_maximum
                if calibrated_damage is None
                else calibrated_damage[1]
            ),
            attack_interval_ms=(
                mob.attack_interval_ms
                if calibrated_interval is None
                else calibrated_interval
            ),
        )
        for mob in config.mobs
    )
    assumptions = list(
        item
        for item in config.assumptions
        if not item.startswith("Three generic camp mobs begin")
        and not (
            observed_output_interval is not None
            and item.startswith("Both speed-20 fists are aggregated")
        )
    )
    assumptions.extend((
        "Every generic simulated camp mob reuses the calibration's aggregate median target "
        "health, engagement distance, and incoming-attack cadence when observed; fields "
        "without sufficient samples retain their declared baseline defaults.",
        "Live event cadence is quantized to the simulator's 200 ms tick, and aggregate "
        "target observations are not treated as named-archetype-specific stats.",
    ))
    if observed_output_interval is not None:
        assumptions.append(
            "The median native target-health decrease interval sets the successful-hit "
            "opportunity cadence; it may aggregate or split client combat events at the "
            "controller poll boundary."
        )
    if residual_method is not None:
        assumptions.append(
            "Sourced physical and proc mechanics remain explicit; the positive difference "
            f"between their expected damage and native aggregate health decreases uses the "
            f"observed {residual_method} as separately tagged unattributed damage. This "
            "normalizes total output without claiming component attribution."
        )
    evidence = config.evidence + (
        calibration.profile_id,
        f"{len(calibration.source_trace_sha256s)} versioned live PvE trace artifact(s)",
    )
    return replace(
        config,
        profile_id=f"{config.profile_id}+{calibration.profile_id}",
        mobs=mobs,
        player_health=(
            config.player_health
            if calibration.starting_player_health is None
            else calibration.starting_player_health.median
        ),
        player_mana=(
            config.player_mana
            if calibration.starting_player_mana is None
            else calibration.starting_player_mana.median
        ),
        player_stamina=(
            config.player_stamina
            if calibration.starting_player_stamina is None
            else calibration.starting_player_stamina.median
        ),
        player_attack_interval_ms=player_attack_interval,
        observed_unattributed_damage=observed_unattributed_damage,
        evidence=evidence,
        assumptions=tuple(assumptions),
    )


def run_smart_camp(config: SmartCampConfig) -> SmartCampResult:
    """Run a multi-mob camp with deliberate player and deterministic mob policies."""

    if not isinstance(config, SmartCampConfig):
        raise ValueError("config must be SmartCampConfig")
    return _run_smart_camp(config, _environment(config))


def run_smart_camp_batch(
    config: SmartCampConfig,
    *,
    episodes: int,
    seed_start: int | None = None,
    retain_episode_results: bool = False,
) -> SmartCampBatchResult:
    """Run contiguous seeds while compiling the sourced action set only once."""

    if not isinstance(config, SmartCampConfig):
        raise ValueError("config must be SmartCampConfig")
    if (
        isinstance(episodes, bool)
        or not isinstance(episodes, int)
        or not 1 <= episodes <= _MAX_BATCH_EPISODES
    ):
        raise ValueError(
            f"episodes must be an integer between 1 and {_MAX_BATCH_EPISODES}"
        )
    first_seed = config.seed if seed_start is None else seed_start
    if isinstance(first_seed, bool) or not isinstance(first_seed, int) or first_seed < 0:
        raise ValueError("seed_start must be a non-negative integer")
    if not isinstance(retain_episode_results, bool):
        raise ValueError("retain_episode_results must be a boolean")

    scenario = _compile_scenario(config)
    retained: list[SmartCampResult] = []
    reason_counts: Counter[SmartCampTerminationReason] = Counter()
    clear_times: Counter[int] = Counter()
    action_counts: Counter[str] = Counter()
    proc_totals = {
        key: {"checks": 0, "triggers": 0, "requested": 0.0, "effective": 0.0}
        for key in config.proc_effect_keys
    }
    total_health = 0.0
    physical_damage = 0.0
    observed_unattributed_damage = 0.0
    rejected_actions = 0
    total_clear_time = 0
    for seed in range(first_seed, first_seed + episodes):
        episode_config = replace(config, seed=seed)
        result = _run_smart_camp(
            episode_config,
            _environment(episode_config, scenario=scenario),
        )
        if retain_episode_results:
            retained.append(result)
        reason_counts[result.reason] += 1
        total_health += result.player_final_health
        physical_damage += result.physical_damage
        observed_unattributed_damage += result.observed_unattributed_damage
        rejected_actions += result.rejected_actions
        action_counts.update(dict(result.action_counts))
        if result.reason is SmartCampTerminationReason.CAMP_CLEARED:
            total_clear_time += result.sim_time_ms
            clear_times[result.sim_time_ms] += 1
        for outcome in result.proc_outcomes:
            totals = proc_totals[outcome.effect_key]
            totals["checks"] += outcome.checks
            totals["triggers"] += outcome.triggers
            totals["requested"] += outcome.requested_damage
            totals["effective"] += outcome.effective_damage

    cleared = reason_counts[SmartCampTerminationReason.CAMP_CLEARED]
    return SmartCampBatchResult(
        profile_id=config.profile_id,
        seed_start=first_seed,
        episodes=episodes,
        camps_cleared=cleared,
        player_defeats=reason_counts[SmartCampTerminationReason.PLAYER_DEFEATED],
        timeouts=reason_counts[SmartCampTerminationReason.TICK_LIMIT],
        clear_rate=cleared / episodes,
        mean_clear_time_ms=total_clear_time / cleared if cleared else None,
        p50_clear_time_ms=_counter_percentile(clear_times, 0.50),
        p90_clear_time_ms=_counter_percentile(clear_times, 0.90),
        p99_clear_time_ms=_counter_percentile(clear_times, 0.99),
        mean_remaining_health=total_health / episodes,
        action_counts=tuple(sorted(action_counts.items())),
        physical_damage=physical_damage,
        observed_unattributed_damage=observed_unattributed_damage,
        proc_outcomes=tuple(
            SmartCampBatchProcOutcome(
                effect_key=key,
                checks=int(proc_totals[key]["checks"]),
                triggers=int(proc_totals[key]["triggers"]),
                trigger_rate=(
                    proc_totals[key]["triggers"] / proc_totals[key]["checks"]
                    if proc_totals[key]["checks"]
                    else 0.0
                ),
                requested_damage=proc_totals[key]["requested"],
                effective_damage=proc_totals[key]["effective"],
            )
            for key in config.proc_effect_keys
        ),
        rejected_actions=rejected_actions,
        episode_results=tuple(retained),
        evidence=config.evidence,
        assumptions=config.assumptions,
    )


def _run_smart_camp(
    config: SmartCampConfig,
    environment: ReferenceEnvironment,
) -> SmartCampResult:
    player_policy = SmartCampPolicy()
    events: list[Event] = []
    choices: list[PolicyChoice] = []
    reason = SmartCampTerminationReason.TICK_LIMIT

    for step_number in range(config.max_ticks):
        player = player_policy.decide(
            environment.exchange(_PLAYER_ID),
            f"smart-camp:{config.seed}:{step_number}:{_PLAYER_ID}",
        )
        decisions = [] if player.decision is None else [player.decision]
        if player.choice is not None:
            choices.append(player.choice)
        for mob in config.mobs:
            state = environment.entity(mob.entity_id)
            if not state.alive:
                continue
            decision = _mob_decision(
                environment.exchange(mob.entity_id),
                f"smart-camp:{config.seed}:{step_number}:{mob.entity_id}",
            )
            if decision is not None:
                decisions.append(decision)
        batch = environment.step(
            tuple(decisions),
            truncated=step_number == config.max_ticks - 1,
        )
        events.extend(batch.events)
        if batch.world_terminated:
            player_alive = environment.entity(_PLAYER_ID).alive
            reason = (
                SmartCampTerminationReason.CAMP_CLEARED
                if player_alive
                else SmartCampTerminationReason.PLAYER_DEFEATED
            )
            break

    return _result(config, environment, events, choices, reason)


@dataclass(frozen=True, slots=True)
class _CompiledSmartCamp:
    catalog: ActionCatalog
    entities: tuple[EntityState, ...]


def _compile_scenario(config: SmartCampConfig) -> _CompiledSmartCamp:
    weapon_effects, expected_damage = _mechanistic_weapon_effects(config)
    if config.observed_unattributed_damage is not None:
        weapon_effects = (
            *weapon_effects,
            DealDamage(
                SubjectRef.TARGET,
                config.observed_unattributed_damage,
                DamageType.UNKNOWN,
                source_key="observed_unattributed",
            ),
        )
        expected_damage += config.observed_unattributed_damage.expected
    dual_fist = ActionSpec(
        action_key=_DUAL_FIST,
        targeting=TargetingSpec(
            kind=TargetKind.ENTITY,
            allowed_relations=(Relation.ENEMY,),
            maximum_range=_DUAL_FIST_MAXIMUM_RANGE,
        ),
        phases=(
            ActionPhase(
                kind=PhaseKind.ACTIVE,
                duration_ms=0,
                effects=weapon_effects,
            ),
        ),
        cooldown_ms=config.player_attack_interval_ms,
        features=(NamedScalar("expected_damage", expected_damage),),
        tags=("combat", "attack", "melee", "physical", "proc"),
    )
    ruleset = load_shadowbane_vertical_slice(
        rank_overrides={_SHADOW_TOUCH: config.shadow_touch_rank}
    )
    shadow_touch = ruleset.record(_SHADOW_TOUCH).action
    if shadow_touch is None:
        raise RuntimeError("ranked Shadow Touch did not compile")
    movement = close_range_action(RangeBand(maximum=_DUAL_FIST_MAXIMUM_RANGE))
    mob_actions = tuple(_mob_action(mob) for mob in config.mobs)
    catalog = ActionCatalog((dual_fist, shadow_touch, movement, *mob_actions))
    entities = [
        EntityState(
            entity_id=_PLAYER_ID,
            life_id="player:1",
            kind=EntityKind.ACTOR,
            team_id=_PLAYER_TEAM,
            position=Vector2(0.0, 0.0),
            scalars={
                "health": config.player_health,
                "mana": config.player_mana,
                "stamina": config.player_stamina,
                "move_speed": config.player_move_speed,
            },
            maximums={
                "health": config.player_health,
                "mana": config.player_mana,
                "stamina": config.player_stamina,
            },
            tags={"profession.assassin", "build.unarmed_proc"},
            action_keys=(_DUAL_FIST, _SHADOW_TOUCH, _CLOSE_RANGE),
        )
    ]
    for mob, mob_action in zip(config.mobs, mob_actions, strict=True):
        entities.append(
            EntityState(
                entity_id=mob.entity_id,
                life_id=f"{mob.entity_id}:1",
                kind=EntityKind.ACTOR,
                team_id=_MOB_TEAM,
                position=Vector2(mob.distance, 0.0),
                scalars={"health": mob.health},
                maximums={"health": mob.health},
                action_keys=(mob_action.action_key,),
            )
        )
    return _CompiledSmartCamp(catalog, tuple(entities))


def _mechanistic_weapon_effects(
    config: SmartCampConfig,
) -> tuple[tuple[DealDamage | ChanceGate, ...], float]:
    progression = load_wonderbane_irekei_proc_profile()
    weapon = progression.weapon(config.weapon_key)
    proc_effects = tuple(
        progression.proc_effect(key) for key in config.proc_effect_keys
    )
    weapon_effects: list[DealDamage | ChanceGate] = [
        DealDamage(
            SubjectRef.TARGET,
            UniformIntegerAmount(
                round(weapon.base_minimum_damage),
                round(weapon.base_maximum_damage),
            ),
            DamageType.CRUSH,
        )
    ]
    expected_damage = (weapon.base_minimum_damage + weapon.base_maximum_damage) / 2.0
    for effect in proc_effects:
        focus = 1.0 if effect.focus_scaling else 0.0
        minimum, maximum = spell_damage_range(
            intelligence=config.stats.intelligence,
            spirit=config.stats.spirit,
            focus=focus,
            base_minimum=effect.base_minimum_damage,
            base_maximum=effect.base_maximum_damage,
        )
        weapon_effects.append(
            ChanceGate(
                effect.key,
                effect.chance_per_successful_hit,
                (
                    DealDamage(
                        SubjectRef.TARGET,
                        UniformAmount(minimum, maximum),
                        effect.damage_type,
                        source_key=effect.key,
                    ),
                ),
            )
        )
        expected_damage += effect.chance_per_successful_hit * (minimum + maximum) / 2.0
    return tuple(weapon_effects), expected_damage


def _environment(
    config: SmartCampConfig,
    *,
    scenario: _CompiledSmartCamp | None = None,
) -> ReferenceEnvironment:
    compiled = _compile_scenario(config) if scenario is None else scenario
    return ReferenceEnvironment(
        compiled.catalog,
        compiled.entities,
        seed=config.seed,
        tick_duration_ms=_TICK_DURATION_MS,
        terminate_on_last_team=True,
    )


def _mob_action(config: CampMobConfig) -> ActionSpec:
    return ActionSpec(
        action_key=f"{_MOB_ATTACK}.{config.entity_id}",
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
        tags=("combat", "attack", "melee", "physical", "mob"),
    )


def _mob_decision(exchange: AgentExchange, correlation_id: str) -> DecisionMessage | None:
    attack = next(
        (
            item
            for item in exchange.affordances.affordances
            if item.binding.target_entity_id == _PLAYER_ID and "mob" in item.tags
        ),
        None,
    )
    return None if attack is None else exchange.decision(attack.affordance_id, correlation_id)


def _result(
    config: SmartCampConfig,
    environment: ReferenceEnvironment,
    events: list[Event],
    choices: list[PolicyChoice],
    reason: SmartCampTerminationReason,
) -> SmartCampResult:
    action_counts: dict[str, int] = {}
    target_sequence: list[str] = []
    physical_damage = 0.0
    observed_unattributed_damage = 0.0
    proc_checks = {key: 0 for key in config.proc_effect_keys}
    proc_triggers = {key: 0 for key in config.proc_effect_keys}
    proc_requested = {key: 0.0 for key in config.proc_effect_keys}
    proc_effective = {key: 0.0 for key in config.proc_effect_keys}
    rejected_actions = 0
    mobs_killed = 0
    for event in events:
        scalars = {item.name: item.value for item in event.scalars}
        if event.kind == EventKind.ACTION_STARTED and event.source_entity_id == _PLAYER_ID:
            if event.action_key is not None:
                action_counts[event.action_key] = action_counts.get(event.action_key, 0) + 1
            if (
                event.target_entity_id is not None
                and (not target_sequence or target_sequence[-1] != event.target_entity_id)
            ):
                target_sequence.append(event.target_entity_id)
        elif event.kind == EventKind.CHANCE_RESOLVED:
            for key in config.proc_effect_keys:
                if f"chance.{key}" in event.tags:
                    proc_checks[key] += 1
                    proc_triggers[key] += round(scalars.get("triggered", 0.0))
        elif event.kind == EventKind.DAMAGE_APPLIED and event.source_entity_id == _PLAYER_ID:
            if "damage.crush" in event.tags:
                physical_damage += scalars.get("effective", 0.0)
            if "damage_source.observed_unattributed" in event.tags:
                observed_unattributed_damage += scalars.get("effective", 0.0)
            for key in config.proc_effect_keys:
                if f"damage.proc.{key}" in event.tags:
                    proc_requested[key] += scalars.get("requested", 0.0)
                    proc_effective[key] += scalars.get("effective", 0.0)
        elif event.kind == EventKind.ACTION_REJECTED:
            rejected_actions += 1
        elif event.kind == EventKind.ENTITY_DIED and event.target_entity_id != _PLAYER_ID:
            mobs_killed += 1
    player = environment.entity(_PLAYER_ID)
    return SmartCampResult(
        profile_id=config.profile_id,
        seed=config.seed,
        reason=reason,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        player_alive=player.alive,
        player_final_health=player.scalars["health"],
        player_final_mana=player.scalars["mana"],
        mobs_killed=mobs_killed,
        mobs_total=len(config.mobs),
        target_sequence=tuple(target_sequence),
        action_counts=tuple(sorted(action_counts.items())),
        physical_damage=physical_damage,
        observed_unattributed_damage=observed_unattributed_damage,
        proc_outcomes=tuple(
            ProcOutcome(
                key,
                proc_checks[key],
                proc_triggers[key],
                proc_requested[key],
                proc_effective[key],
            )
            for key in config.proc_effect_keys
        ),
        rejected_actions=rejected_actions,
        choices=tuple(choices),
        evidence=config.evidence,
        assumptions=config.assumptions,
    )


def _scalar(values: tuple[NamedScalar, ...], name: str) -> float:
    return next((item.value for item in values if item.name == name), 0.0)


def _distance(left: Vector2, right: Vector2) -> float:
    return hypot(left.x - right.x, left.y - right.y)


def _counter_percentile(counts: Counter[int], percentile: float) -> int | None:
    total = sum(counts.values())
    if total == 0:
        return None
    threshold = ceil(percentile * total)
    cumulative = 0
    for value in sorted(counts):
        cumulative += counts[value]
        if cumulative >= threshold:
            return value
    raise RuntimeError("percentile traversal did not reach its threshold")
