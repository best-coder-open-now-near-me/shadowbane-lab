from __future__ import annotations

from dataclasses import dataclass

from .model import (
    ActionSpec,
    ApplyStatus,
    CombatantState,
    DealDamage,
    Decision,
    ModifyResource,
    Recipient,
    Reposition,
    RepositionMode,
    RestoreHealth,
    StatusKind,
    TargetMode,
    Vec2,
    ZERO_VEC2,
)


@dataclass(slots=True)
class UtilityPolicy:
    """Interpretable baseline policy used before learned policies exist."""

    catalog: dict[str, ActionSpec]

    def decide(self, actor: CombatantState, combatants: list[CombatantState]) -> Decision:
        enemies = [
            other for other in combatants if other.alive and other.team != actor.team
        ]
        if not enemies:
            return Decision(None, None, ZERO_VEC2)

        target = min(enemies, key=lambda enemy: (enemy.position - actor.position).length)
        delta = target.position - actor.position
        distance = delta.length
        direction = delta.normalized()

        preferred = actor.tuning.preferred_range
        if distance > preferred + 0.6:
            movement = direction
        elif distance < max(0.5, preferred - 0.6):
            movement = direction * -1.0
        else:
            # A small deterministic orbit breaks pure one-dimensional stalemates.
            side = -1.0 if actor.index % 2 else 1.0
            movement = Vec2(-direction.y * side, direction.x * side)

        best_action: str | None = None
        best_score = 0.0
        for action_id in actor.stats.action_ids:
            action = self.catalog[action_id]
            candidate_target = actor if action.target_mode is TargetMode.SELF else target
            action_distance = (candidate_target.position - actor.position).length
            if not self._is_locally_legal(actor, action, action_distance):
                continue

            score = self._score_action(actor, target, action, distance)
            if score > best_score or (
                score == best_score and best_action is not None and action.id < best_action
            ):
                best_score = score
                best_action = action.id

        return Decision(target.index, best_action, movement)

    def _is_locally_legal(
        self, actor: CombatantState, action: ActionSpec, distance: float
    ) -> bool:
        if actor.cooldowns.get(action.id, 0.0) > 0.0:
            return False
        if actor.mana + 1e-9 < action.mana_cost:
            return False
        if actor.stamina + 1e-9 < action.stamina_cost:
            return False
        if action.target_mode is TargetMode.ENEMY and distance > action.range:
            return False
        if actor.has_status(StatusKind.SILENCE) and "spell" in action.tags:
            return False
        if actor.has_status(StatusKind.STUN):
            return False
        return True

    def _score_action(
        self,
        actor: CombatantState,
        target: CombatantState,
        action: ActionSpec,
        distance: float,
    ) -> float:
        score = 0.0
        target_missing = 1.0 - target.health_fraction
        self_missing = 1.0 - actor.health_fraction
        has_hostile_damage = False
        has_self_heal = False

        for effect in action.effects:
            recipient = actor if effect.recipient is Recipient.ACTOR else target

            if isinstance(effect, DealDamage):
                damage = effect.amount.evaluate(actor.stats)
                resistance = recipient.stats.resistance(effect.damage_type)
                expected = damage * (1.0 - resistance)
                if recipient is target:
                    has_hostile_damage = True
                    score += actor.tuning.aggression * expected
                    score += actor.tuning.finisher_bias * target_missing * expected * 0.9
                else:
                    score -= expected * 1.5
            elif isinstance(effect, RestoreHealth):
                missing_fraction = 1.0 - recipient.health_fraction
                heal = effect.amount.evaluate(actor.stats)
                effective = min(heal, recipient.stats.max_health - recipient.health)
                if recipient is actor:
                    has_self_heal = True
                    score += (
                        actor.tuning.sustain_bias
                        * effective
                        * (0.4 + 1.8 * missing_fraction)
                    )
                else:
                    score += actor.tuning.sustain_bias * effective
            elif isinstance(effect, ApplyStatus):
                if recipient.has_status(effect.status):
                    score -= 2.0
                    continue

                duration = effect.duration.evaluate(actor.stats)
                if recipient is target and effect.status in {
                    StatusKind.STUN,
                    StatusKind.SILENCE,
                    StatusKind.SNARE,
                }:
                    score += actor.tuning.control_bias * duration * 6.0
                elif recipient is actor and effect.status is StatusKind.WARD:
                    score += (
                        actor.tuning.defense_bias
                        * duration
                        * (0.5 + 2.0 * self_missing)
                    )
                elif recipient is target and effect.status is StatusKind.HEALING_REDUCTION:
                    score += actor.tuning.control_bias * duration * 3.5
                elif (
                    recipient is target
                    and effect.status is StatusKind.BURN
                    and effect.tick_damage is not None
                ):
                    score += (
                        actor.tuning.aggression
                        * duration
                        * effect.tick_damage.evaluate(actor.stats)
                    )
            elif isinstance(effect, ModifyResource):
                amount = effect.amount.evaluate(actor.stats)
                if recipient is target and amount < 0.0 and effect.resource == "mana":
                    score += actor.tuning.control_bias * min(-amount, target.mana) * 0.8
                elif recipient is actor and amount > 0.0:
                    current = getattr(actor, effect.resource)
                    maximum = getattr(actor.stats, f"max_{effect.resource}")
                    score += min(amount, maximum - current) * actor.tuning.sustain_bias
            elif isinstance(effect, Reposition):
                displacement = effect.distance.evaluate(actor.stats)
                if effect.mode is RepositionMode.AWAY_FROM_TARGET:
                    urgency = max(0.0, actor.tuning.preferred_range - distance)
                else:
                    urgency = max(0.0, distance - actor.tuning.preferred_range)
                score += actor.tuning.defense_bias * displacement * urgency * 0.5

        resource_fraction = (
            action.mana_cost / max(actor.stats.max_mana, 1.0)
            + action.stamina_cost / max(actor.stats.max_stamina, 1.0)
        )
        score -= actor.tuning.resource_conservation * resource_fraction * 30.0
        score -= action.cast_time * 1.5

        # Pure heals should not be spammed at full health, but hybrid actions such
        # as Siphon remain valid offensive choices.
        if has_self_heal and not has_hostile_damage and self_missing < 0.08:
            score -= 100.0
        if "defense" in action.tags and self_missing < 0.15 and distance > 5.0:
            score -= 8.0
        return score
