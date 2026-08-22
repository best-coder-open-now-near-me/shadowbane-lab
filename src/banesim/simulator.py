from __future__ import annotations

from dataclasses import dataclass
from random import Random

from .model import (
    ActionSpec,
    ActiveStatus,
    ApplyStatus,
    CombatEvent,
    CombatantState,
    DealDamage,
    Decision,
    ModifyResource,
    PendingAction,
    Recipient,
    Reposition,
    RepositionMode,
    RestoreHealth,
    StatusKind,
    TargetMode,
    Vec2,
    ZERO_VEC2,
)
from .policy import UtilityPolicy


@dataclass(frozen=True, slots=True)
class DuelResult:
    winner_team: int | None
    duration: float
    seed: int
    combatants: tuple[CombatantState, CombatantState]
    events: tuple[CombatEvent, ...]

    @property
    def draw(self) -> bool:
        return self.winner_team is None


class CombatSimulator:
    """Small deterministic fixed-tick simulator.

    It intentionally models only the generic mechanics needed to validate the
    action grammar and search loop. Reforged fidelity comes later through data
    imports and differential tests.
    """

    def __init__(
        self,
        catalog: dict[str, ActionSpec],
        *,
        tick_seconds: float = 0.20,
        max_time_seconds: float = 45.0,
        arena_radius: float = 24.0,
        record_events: bool = False,
    ) -> None:
        if tick_seconds <= 0.0:
            raise ValueError("tick_seconds must be positive")
        self.catalog = catalog
        self.tick_seconds = tick_seconds
        self.max_time_seconds = max_time_seconds
        self.arena_radius = arena_radius
        self.record_events = record_events

    def run_duel(
        self,
        left: tuple,
        right: tuple,
        *,
        seed: int,
        starting_distance: float = 12.0,
    ) -> DuelResult:
        left_stats, left_tuning = left
        right_stats, right_tuning = right
        combatants = [
            CombatantState.from_build(
                index=0,
                team=0,
                stats=left_stats,
                tuning=left_tuning,
                position=Vec2(-starting_distance / 2.0, 0.0),
            ),
            CombatantState.from_build(
                index=1,
                team=1,
                stats=right_stats,
                tuning=right_tuning,
                position=Vec2(starting_distance / 2.0, 0.0),
            ),
        ]
        policies = [UtilityPolicy(self.catalog), UtilityPolicy(self.catalog)]
        rng = Random(seed)
        events: list[CombatEvent] = []
        current_time = 0.0

        while current_time < self.max_time_seconds and self._teams_alive(combatants) > 1:
            self._sample_distances(combatants)
            self._advance_resources_and_statuses(combatants, current_time, events)

            decisions: list[Decision] = []
            for actor, policy in zip(combatants, policies, strict=True):
                if not actor.alive or actor.has_status(StatusKind.STUN):
                    decisions.append(Decision(None, None, ZERO_VEC2))
                elif actor.pending_action is not None:
                    decisions.append(Decision(None, None, ZERO_VEC2))
                else:
                    decisions.append(policy.decide(actor, combatants))

            self._start_actions(combatants, decisions, current_time, events)
            self._apply_movement(combatants, decisions)
            self._advance_casts(combatants, rng, current_time, events)
            current_time += self.tick_seconds

        living_teams = {actor.team for actor in combatants if actor.alive}
        winner_team = next(iter(living_teams)) if len(living_teams) == 1 else None
        return DuelResult(
            winner_team=winner_team,
            duration=min(current_time, self.max_time_seconds),
            seed=seed,
            combatants=(combatants[0], combatants[1]),
            events=tuple(events),
        )

    def _teams_alive(self, combatants: list[CombatantState]) -> int:
        return len({actor.team for actor in combatants if actor.alive})

    def _sample_distances(self, combatants: list[CombatantState]) -> None:
        for actor in combatants:
            if not actor.alive:
                continue
            enemies = [other for other in combatants if other.alive and other.team != actor.team]
            if not enemies:
                continue
            distance = min((enemy.position - actor.position).length for enemy in enemies)
            actor.metrics.distance_sum += distance
            actor.metrics.distance_samples += 1

    def _advance_resources_and_statuses(
        self,
        combatants: list[CombatantState],
        current_time: float,
        events: list[CombatEvent],
    ) -> None:
        dt = self.tick_seconds
        for actor in combatants:
            if not actor.alive:
                continue

            actor.health = min(actor.stats.max_health, actor.health + actor.stats.health_regen * dt)
            actor.mana = min(actor.stats.max_mana, actor.mana + actor.stats.mana_regen * dt)
            actor.stamina = min(
                actor.stats.max_stamina, actor.stamina + actor.stats.stamina_regen * dt
            )

            for action_id in tuple(actor.cooldowns):
                remaining = max(0.0, actor.cooldowns[action_id] - dt)
                if remaining == 0.0:
                    del actor.cooldowns[action_id]
                else:
                    actor.cooldowns[action_id] = remaining

            expired: list[StatusKind] = []
            for kind, status in actor.statuses.items():
                status.remaining -= dt
                if status.tick_damage > 0.0:
                    status.time_to_tick -= dt
                    while status.time_to_tick <= 1e-9 and status.remaining > -dt:
                        source = combatants[status.source_index]
                        self._deal_damage(
                            source,
                            actor,
                            status.tick_damage,
                            status.damage_type,
                            current_time,
                            events,
                            detail=f"{kind.value} tick",
                        )
                        status.time_to_tick += status.tick_interval
                        if not actor.alive:
                            break
                if status.remaining <= 1e-9:
                    expired.append(kind)
            for kind in expired:
                del actor.statuses[kind]

    def _apply_movement(
        self, combatants: list[CombatantState], decisions: list[Decision]
    ) -> None:
        dt = self.tick_seconds
        next_positions: list[Vec2] = []
        for actor, decision in zip(combatants, decisions, strict=True):
            if not actor.alive or actor.has_status(StatusKind.STUN):
                next_positions.append(actor.position)
                continue

            movement = decision.movement.normalized()
            speed = actor.stats.move_speed
            snare = actor.statuses.get(StatusKind.SNARE)
            if snare is not None:
                speed *= max(0.10, 1.0 - min(snare.magnitude, 0.90))
            if actor.pending_action is not None:
                speed *= 0.15

            proposed = actor.position + movement * (speed * dt)
            if proposed.length > self.arena_radius:
                proposed = proposed.normalized() * self.arena_radius
            next_positions.append(proposed)

        for actor, position in zip(combatants, next_positions, strict=True):
            actor.position = position

    def _start_actions(
        self,
        combatants: list[CombatantState],
        decisions: list[Decision],
        current_time: float,
        events: list[CombatEvent],
    ) -> None:
        for actor, decision in zip(combatants, decisions, strict=True):
            if not actor.alive or actor.pending_action is not None or decision.action_id is None:
                continue
            action = self.catalog.get(decision.action_id)
            if action is None:
                actor.metrics.invalid_actions += 1
                continue

            target_index = actor.index if action.target_mode is TargetMode.SELF else decision.target_index
            if target_index is None or not 0 <= target_index < len(combatants):
                actor.metrics.invalid_actions += 1
                continue
            target = combatants[target_index]
            if not self._is_action_legal(actor, target, action):
                actor.metrics.invalid_actions += 1
                continue

            actor.mana -= action.mana_cost
            actor.stamina -= action.stamina_cost
            actor.metrics.resource_spent += action.mana_cost + action.stamina_cost
            actor.cooldowns[action.id] = action.cooldown
            actor.pending_action = PendingAction(action.id, target_index, action.cast_time)
            actor.metrics.actions_started += 1
            for tag in action.tags:
                actor.metrics.actions_by_tag[tag] = actor.metrics.actions_by_tag.get(tag, 0) + 1
            self._event(events, current_time, "action_started", actor.index, target_index, detail=action.id)

    def _is_action_legal(
        self, actor: CombatantState, target: CombatantState, action: ActionSpec
    ) -> bool:
        if not actor.alive or not target.alive:
            return False
        if action.id not in actor.stats.action_ids:
            return False
        if actor.cooldowns.get(action.id, 0.0) > 0.0:
            return False
        if actor.mana + 1e-9 < action.mana_cost:
            return False
        if actor.stamina + 1e-9 < action.stamina_cost:
            return False
        if actor.has_status(StatusKind.STUN):
            return False
        if actor.has_status(StatusKind.SILENCE) and "spell" in action.tags:
            return False
        if action.target_mode is TargetMode.ENEMY:
            if target.team == actor.team:
                return False
            if (target.position - actor.position).length > action.range + 1e-9:
                return False
        return True

    def _advance_casts(
        self,
        combatants: list[CombatantState],
        rng: Random,
        current_time: float,
        events: list[CombatEvent],
    ) -> None:
        completed: list[tuple[int, PendingAction]] = []
        for actor in combatants:
            if not actor.alive or actor.pending_action is None:
                continue
            if actor.has_status(StatusKind.STUN):
                self._event(
                    events,
                    current_time,
                    "action_interrupted",
                    actor.index,
                    actor.pending_action.target_index,
                    detail=actor.pending_action.action_id,
                )
                actor.pending_action = None
                continue
            actor.pending_action.remaining -= self.tick_seconds
            if actor.pending_action.remaining <= 1e-9:
                completed.append((actor.index, actor.pending_action))
                actor.pending_action = None

        # Resolve in actor-index order for deterministic tie handling.
        for actor_index, pending in completed:
            actor = combatants[actor_index]
            target = combatants[pending.target_index]
            action = self.catalog[pending.action_id]
            if not actor.alive or not target.alive:
                self._event(
                    events,
                    current_time,
                    "action_fizzled",
                    actor.index,
                    target.index,
                    detail=action.id,
                )
                continue
            if action.target_mode is TargetMode.ENEMY and (
                target.position - actor.position
            ).length > action.range + 1e-9:
                self._event(
                    events,
                    current_time,
                    "action_out_of_range",
                    actor.index,
                    target.index,
                    detail=action.id,
                )
                continue

            if action.requires_hit and not self._roll_hit(actor, target, rng):
                self._event(
                    events,
                    current_time,
                    "action_missed",
                    actor.index,
                    target.index,
                    detail=action.id,
                )
                continue
            self._resolve_action(actor, target, action, current_time, events)

    def _roll_hit(self, actor: CombatantState, target: CombatantState, rng: Random) -> bool:
        chance = 0.72 + (actor.stats.accuracy - target.stats.evasion) / 240.0
        chance = max(0.15, min(0.95, chance))
        return rng.random() < chance

    def _resolve_action(
        self,
        actor: CombatantState,
        target: CombatantState,
        action: ActionSpec,
        current_time: float,
        events: list[CombatEvent],
    ) -> None:
        for effect in action.effects:
            recipient = actor if effect.recipient is Recipient.ACTOR else target
            if recipient is target and not target.alive:
                continue

            if isinstance(effect, DealDamage):
                self._deal_damage(
                    actor,
                    recipient,
                    effect.amount.evaluate(actor.stats),
                    effect.damage_type,
                    current_time,
                    events,
                    detail=action.id,
                )
            elif isinstance(effect, RestoreHealth):
                reduction = recipient.statuses.get(StatusKind.HEALING_REDUCTION)
                multiplier = 1.0 if reduction is None else max(0.0, 1.0 - reduction.magnitude)
                raw = effect.amount.evaluate(actor.stats) * multiplier
                amount = min(raw, recipient.stats.max_health - recipient.health)
                recipient.health += amount
                actor.metrics.healing_done += amount
                self._event(
                    events,
                    current_time,
                    "healed",
                    actor.index,
                    recipient.index,
                    amount,
                    action.id,
                )
            elif isinstance(effect, ModifyResource):
                amount = effect.amount.evaluate(actor.stats)
                current = getattr(recipient, effect.resource)
                maximum = getattr(recipient.stats, f"max_{effect.resource}")
                updated = max(0.0, min(maximum, current + amount))
                setattr(recipient, effect.resource, updated)
                self._event(
                    events,
                    current_time,
                    "resource_modified",
                    actor.index,
                    recipient.index,
                    updated - current,
                    f"{action.id}:{effect.resource}",
                )
            elif isinstance(effect, ApplyStatus):
                duration = max(0.0, effect.duration.evaluate(actor.stats))
                magnitude = max(0.0, effect.magnitude.evaluate(actor.stats))
                tick_damage = (
                    0.0 if effect.tick_damage is None else effect.tick_damage.evaluate(actor.stats)
                )
                existing = recipient.statuses.get(effect.status)
                if existing is None or duration >= existing.remaining or magnitude >= existing.magnitude:
                    recipient.statuses[effect.status] = ActiveStatus(
                        kind=effect.status,
                        source_index=actor.index,
                        remaining=max(duration, existing.remaining if existing else 0.0),
                        magnitude=max(magnitude, existing.magnitude if existing else 0.0),
                        tick_damage=max(tick_damage, existing.tick_damage if existing else 0.0),
                        tick_interval=effect.tick_interval,
                        time_to_tick=effect.tick_interval,
                        damage_type=effect.damage_type,
                    )
                if recipient.team != actor.team and effect.status in {
                    StatusKind.STUN,
                    StatusKind.SILENCE,
                    StatusKind.SNARE,
                }:
                    actor.metrics.control_seconds_applied += duration
                self._event(
                    events,
                    current_time,
                    "status_applied",
                    actor.index,
                    recipient.index,
                    duration,
                    f"{action.id}:{effect.status.value}",
                )
            elif isinstance(effect, Reposition):
                reference = target if recipient is actor else actor
                direction = (reference.position - recipient.position).normalized()
                if effect.mode is RepositionMode.AWAY_FROM_TARGET:
                    direction = direction * -1.0
                distance = max(0.0, effect.distance.evaluate(actor.stats))
                proposed = recipient.position + direction * distance
                if proposed.length > self.arena_radius:
                    proposed = proposed.normalized() * self.arena_radius
                recipient.position = proposed
                self._event(
                    events,
                    current_time,
                    "repositioned",
                    actor.index,
                    recipient.index,
                    distance,
                    action.id,
                )

        self._event(events, current_time, "action_resolved", actor.index, target.index, detail=action.id)

    def _deal_damage(
        self,
        source: CombatantState,
        target: CombatantState,
        raw_amount: float,
        damage_type: str,
        current_time: float,
        events: list[CombatEvent],
        *,
        detail: str,
    ) -> None:
        if not target.alive:
            return
        resistance = max(0.0, min(0.80, target.stats.resistance(damage_type)))
        ward = target.statuses.get(StatusKind.WARD)
        ward_reduction = 0.0 if ward is None else min(0.75, ward.magnitude)
        amount = max(0.0, raw_amount * (1.0 - resistance) * (1.0 - ward_reduction))
        amount = min(amount, target.health)
        target.health -= amount
        source.metrics.damage_dealt += amount
        target.metrics.damage_received += amount
        self._event(events, current_time, "damaged", source.index, target.index, amount, detail)
        if target.health <= 1e-9:
            target.health = 0.0
            target.alive = False
            target.pending_action = None
            target.movement_intent = ZERO_VEC2
            self._event(events, current_time, "died", source.index, target.index, detail=detail)

    def _event(
        self,
        events: list[CombatEvent],
        time: float,
        kind: str,
        actor_index: int | None,
        target_index: int | None,
        amount: float = 0.0,
        detail: str = "",
    ) -> None:
        if self.record_events:
            events.append(CombatEvent(time, kind, actor_index, target_index, amount, detail))
