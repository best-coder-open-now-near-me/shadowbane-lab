"""Deterministic nearby-mob simulation bridge for the production PvE controller."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from shadowbane_lab.client_observation import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionPhase,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.protocol import EntityKind, Event, EventKind, Relation, TargetKind, Vector2
from shadowbane_lab.pve import (
    PvEController,
    PvEControllerConfig,
    PvEControllerDecision,
    PvEObservation,
    PvEPhase,
)
from shadowbane_lab.pve.model import (
    PvECombatAcknowledgement,
    PvECombatCleanupResult,
    PvECombatDisposition,
    PvECombatKind,
)
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


def _finite_positive(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{field_name} must be a finite positive number")


@dataclass(frozen=True, slots=True)
class NearbyMobSimulationConfig:
    """One observed nearby-mob profile plus explicit simulator assumptions."""

    profile_id: str
    mob_name: str
    mob_health: float
    experience_reward: float
    attack_damage_minimum: int
    attack_damage_maximum: int
    attack_interval_ms: int
    player_current_health: float
    player_maximum_health: float
    player_current_mana: float
    player_maximum_mana: float
    player_current_stamina: float
    player_maximum_stamina: float
    evidence: tuple[str, ...]
    assumptions: tuple[str, ...]
    seed: int = 1
    max_ticks: int = 100

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.profile_id, "profile_id"),
            (self.mob_name, "mob_name"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for value, field_name in (
            (self.mob_health, "mob_health"),
            (self.experience_reward, "experience_reward"),
            (self.player_maximum_health, "player_maximum_health"),
            (self.player_maximum_mana, "player_maximum_mana"),
            (self.player_maximum_stamina, "player_maximum_stamina"),
        ):
            _finite_positive(value, field_name)
        for current, maximum, field_name in (
            (self.player_current_health, self.player_maximum_health, "player health"),
            (self.player_current_mana, self.player_maximum_mana, "player mana"),
            (self.player_current_stamina, self.player_maximum_stamina, "player stamina"),
        ):
            if (
                isinstance(current, bool)
                or not isinstance(current, (int, float))
                or not isfinite(current)
                or current < 0
                or current > maximum
            ):
                raise ValueError(f"{field_name} is outside valid bounds")
        UniformIntegerAmount(self.attack_damage_minimum, self.attack_damage_maximum)
        for value, field_name in (
            (self.attack_interval_ms, "attack_interval_ms"),
            (self.max_ticks, "max_ticks"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.attack_interval_ms % _TICK_DURATION_MS != 0:
            raise ValueError("attack_interval_ms must align to the simulation tick")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        for values, field_name in (
            (self.evidence, "evidence"),
            (self.assumptions, "assumptions"),
        ):
            if (
                not isinstance(values, tuple)
                or not values
                or any(not isinstance(item, str) or not item.strip() for item in values)
            ):
                raise ValueError(f"{field_name} must contain non-empty strings")


def frost_walker_observed_config(
    *, seed: int = 1, max_ticks: int = 100
) -> NearbyMobSimulationConfig:
    """Return the profile measured from the live WonderBane Frost Walker encounter."""

    return NearbyMobSimulationConfig(
        profile_id="wonderbane.frost-walker.2026-08-25",
        mob_name="the Frost Walker",
        mob_health=10.0,
        experience_reward=744.0,
        attack_damage_minimum=4,
        attack_damage_maximum=5,
        attack_interval_ms=1_000,
        player_current_health=1_075.375,
        player_maximum_health=1_075.375,
        player_current_mana=53.75,
        player_maximum_mana=53.75,
        player_current_stamina=324.0,
        player_maximum_stamina=324.0,
        evidence=(
            "native selected-target health: 10/10",
            "native combat records: player hits of 4 and 5",
            "native combat record: 744 experience",
            "native player vitals: 1075.375 health, 53.75 mana, 324 stamina",
        ),
        assumptions=(
            "observed 4-5 basic-attack values are sampled as an inclusive uniform integer roll",
            "the reviewed 1000 ms basic-attack interval is not yet trace-validated",
            "incoming attacks, misses, regeneration, movement, and loot are not modeled",
        ),
        seed=seed,
        max_ticks=max_ticks,
    )


@dataclass(frozen=True, slots=True)
class NearbyMobSimulationResult:
    profile_id: str
    seed: int
    final_phase: PvEPhase
    terminal_reason: str
    kills: int
    ticks: int
    sim_time_ms: int
    attack_rolls: tuple[float, ...]
    effective_damage: tuple[float, ...]
    target_final_health: float
    player_final_health: float
    experience_observed: float
    rejected_actions: int
    total_simulation_events: int
    controller_trace: tuple[PvEControllerDecision, ...]
    evidence: tuple[str, ...]
    assumptions: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "seed": self.seed,
            "final_phase": self.final_phase.value,
            "terminal_reason": self.terminal_reason,
            "kills": self.kills,
            "ticks": self.ticks,
            "sim_time_ms": self.sim_time_ms,
            "attack_rolls": list(self.attack_rolls),
            "effective_damage": list(self.effective_damage),
            "target_final_health": self.target_final_health,
            "player_final_health": self.player_final_health,
            "experience_observed": self.experience_observed,
            "rejected_actions": self.rejected_actions,
            "total_simulation_events": self.total_simulation_events,
            "controller_trace": [
                {
                    "decision_id": item.decision_id,
                    "now_ms": item.now_ms,
                    "phase": item.phase.value,
                    "kills": item.kills,
                    "intent": item.intent.value if item.intent is not None else None,
                    "combat_proposal": (None if item.combat_proposal is None else
                                        item.combat_proposal.as_dict()),
                    "terminal_reason": item.terminal_reason,
                }
                for item in self.controller_trace
            ],
            "evidence": list(self.evidence),
            "assumptions": list(self.assumptions),
        }


def run_nearby_mob_simulation(
    config: NearbyMobSimulationConfig,
) -> NearbyMobSimulationResult:
    """Run the production PvE controller against a deterministic semantic client bridge."""

    if not isinstance(config, NearbyMobSimulationConfig):
        raise ValueError("config must be a NearbyMobSimulationConfig")
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
    environment = ReferenceEnvironment(
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
    controller = PvEController(
        PvEControllerConfig(
            maximum_kills=1,
            maximum_session_ms=(config.max_ticks + 1) * _TICK_DURATION_MS,
        )
    )
    auto_attack = False
    controller_trace: list[PvEControllerDecision] = []
    simulation_events: list[Event] = []
    attack_rolls: list[float] = []
    effective_damage: list[float] = []
    experience_observed = 0.0
    rejected_actions = 0

    for step_number in range(config.max_ticks):
        mob = environment.entity(_MOB_ID)
        target = NativeTargetHealthObservation(target_present=False)
        player = environment.entity(_PLAYER_ID)
        decision = controller.step(
            PvEObservation(
                now_ms=environment.now_ms,
                target=target,
                player=_player_observation(player, config),
                population=_population_observation(mob, auto_attack),
                player_position=NativePlayerPositionObservation(
                    player.position.x, player.position.y, 0.0),
                target_position=NativeTargetPositionObservation(target_present=False),
                player_action=NativePlayerActionObservation(
                    phase=NativeTargetActionPhase.IDLE, motion_id=0, action_pending=False,
                    impact_frame=None, action_sequence=0, motion_sequence=0,
                    mode=2 if auto_attack else 1, action_state=1,
                    selected_target_token=target.target_token,
                    action_target_token="simulation:mob:1" if auto_attack else None,
                    targeting_selected=auto_attack and target.target_present,
                ),
            )
        )
        controller_trace.append(decision)
        if decision.cleanup_request is not None:
            # The simulator owns its action loop, so stopping that loop is the
            # simulation cleanup boundary. This is not a native-client receipt.
            auto_attack = False
            controller.acknowledge_cleanup(PvECombatCleanupResult(
                request=decision.cleanup_request,
                confirmed=True,
                request_key=f"simulation-cleanup:{decision.cleanup_request.sequence}",
            ))
        if decision.terminal:
            break
        proposal = decision.combat_proposal
        if proposal is not None:
            if (proposal.kind is not PvECombatKind.ATTACK
                    or proposal.target_token != "simulation:mob:1"
                    or proposal.target_key != NativeObjectKey(1, 37)
                    or not mob.alive):
                raise ValueError("simulation received an unsupported native object proposal")
            # The simulator owns this exact entity's repeated action loop. ACK
            # its admission without manufacturing a native-client wire receipt.
            auto_attack = True
            controller.acknowledge_combat(proposal, PvECombatAcknowledgement(
                PvECombatDisposition.QUEUED, True, True,
            ), now_ms=environment.now_ms)

        sim_decisions = ()
        if auto_attack and mob.alive:
            exchange = environment.exchange(_PLAYER_ID)
            matches = tuple(
                item
                for item in exchange.affordances.affordances
                if item.action_key == _BASIC_ATTACK and item.binding.target_entity_id == _MOB_ID
            )
            if len(matches) == 1:
                sim_decisions = (
                    exchange.decision(
                        matches[0].affordance_id,
                        f"nearby-mob:{config.seed}:{step_number}",
                    ),
                )
        batch = environment.step(
            sim_decisions,
            truncated=step_number == config.max_ticks - 1,
        )
        simulation_events.extend(batch.events)
        rejected_actions += sum(event.kind == EventKind.ACTION_REJECTED for event in batch.events)
        new_experience = _collect_combat_metrics(
            batch.events, config, attack_rolls, effective_damage,
        )
        experience_observed += new_experience
        if not environment.entity(_MOB_ID).alive:
            auto_attack = False
    else:
        controller_trace.append(controller.stop("simulation_tick_limit", now_ms=environment.now_ms))

    terminal = controller_trace[-1]
    if terminal.terminal_reason is None:
        raise RuntimeError("nearby-mob simulation did not reach a terminal decision")
    return NearbyMobSimulationResult(
        profile_id=config.profile_id,
        seed=config.seed,
        final_phase=terminal.phase,
        terminal_reason=terminal.terminal_reason,
        kills=terminal.kills,
        ticks=environment.tick,
        sim_time_ms=environment.now_ms,
        attack_rolls=tuple(attack_rolls),
        effective_damage=tuple(effective_damage),
        target_final_health=environment.entity(_MOB_ID).scalars["health"],
        player_final_health=environment.entity(_PLAYER_ID).scalars["health"],
        experience_observed=experience_observed,
        rejected_actions=rejected_actions,
        total_simulation_events=len(simulation_events),
        controller_trace=tuple(controller_trace),
        evidence=config.evidence,
        assumptions=config.assumptions,
    )


def _player_observation(
    player: EntityState, config: NearbyMobSimulationConfig
) -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(
        current_health=player.scalars["health"],
        maximum_health=config.player_maximum_health,
        current_mana=player.scalars["mana"],
        maximum_mana=config.player_maximum_mana,
        current_stamina=player.scalars["stamina"],
        maximum_stamina=config.player_maximum_stamina,
    )


def _population_observation(
    mob: EntityState, auto_attack: bool,
) -> NativeCharacterPopulationObservation:
    # A dead object stays observable long enough to confirm its exact lifetime.
    token = "simulation:mob:1"
    return NativeCharacterPopulationObservation(
        characters=(NativeCharacterObservation(
            token=token, object_key=NativeObjectKey(1, 37),
            character_kind=NativeCharacterKind.NPC,
            current_health=mob.scalars["health"], maximum_health=mob.maximums["health"],
            lt=1.0, lg=0.0, altitude=0.0,
            merchant=False, shopkeeper=False, banker=False, trainer=False, minion=False,
        ),),
        selected_target_token=None,
        player_action_target_token=token if auto_attack else None,
        scan_generation=1, rejected_candidates=0, local_player_object_key=NativeObjectKey(1, 53),
    )


def _collect_combat_metrics(
    events: tuple[Event, ...],
    config: NearbyMobSimulationConfig,
    attack_rolls: list[float],
    effective_damage: list[float],
) -> float:
    """Collect simulator results without manufacturing client text events."""
    experience = 0.0
    for event in events:
        if (
            event.kind == EventKind.DAMAGE_APPLIED
            and event.source_entity_id == _PLAYER_ID
            and event.target_entity_id == _MOB_ID
        ):
            scalars = {item.name: item.value for item in event.scalars}
            attack_rolls.append(scalars["requested"])
            effective_damage.append(scalars["effective"])
        elif event.kind == EventKind.ENTITY_DIED and event.target_entity_id == _MOB_ID:
            experience += config.experience_reward
    return experience
