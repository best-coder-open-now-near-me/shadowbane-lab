"""Execution of the closed primitive effect set."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import hypot

from shadowbane_lab.combat import (
    DamageType,
    effective_resistance,
    melee_hit_chance_percent,
    power_hit_chance_percent,
    resisted_amount,
    should_overwrite_effect,
    triangular_roll,
)
from shadowbane_lab.protocol import (
    ActionBinding,
    EntityKind,
    Event,
    EventKind,
    NamedScalar,
    Relation,
    TargetKind,
    Vector2,
)
from shadowbane_lab.sim.actions import (
    ActionCatalog,
    ActionTriggerSpec,
    ApplyEffect,
    AreaEffect,
    AreaOrigin,
    AttackGate,
    AttackKind,
    ChanceGate,
    ChangeStance,
    CombatStance,
    DamageBreakpoint,
    DealDamage,
    DirectEffectPrimitive,
    ModifyObjective,
    ModifyScalar,
    ModifyTag,
    MoveEntity,
    MovementMode,
    OutcomeConditional,
    PeriodicPulse,
    RemoveEffect,
    ResistanceAdjustment,
    ResourceImmunity,
    RestoreResource,
    ScalarOperation,
    SubjectRef,
    TagOperation,
    TransferItem,
    TransferResource,
    TriangularAmount,
    TriggerMoment,
    UniformAmount,
    UniformIntegerAmount,
    WeightedAmount,
)
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.lifecycle import ContinuationPolicy
from shadowbane_lab.sim.outcomes import EffectOutcome, EffectOutcomeKind
from shadowbane_lab.sim.random_source import DeterministicRandom
from shadowbane_lab.sim.state import ActiveEffectState, EntityState
from shadowbane_lab.sim.timeline import ScheduledItem, ScheduledKind

EventFactory = Callable[..., Event]
ScheduleCallback = Callable[[ScheduledItem], None]
OrderCallback = Callable[[], int]
InterruptCallback = Callable[[str, str, int, list[Event]], None]


@dataclass(frozen=True, slots=True)
class _TriggerContext:
    storage_key: str
    active: ActiveEffectState
    trigger: ActionTriggerSpec


class EffectExecutor:
    """Applies primitive effects to one mutable reference-world state."""

    def __init__(
        self,
        entities: dict[str, EntityState],
        event_factory: EventFactory,
        schedule: ScheduleCallback,
        take_schedule_order: OrderCallback,
        catalog: ActionCatalog,
        random: DeterministicRandom,
        interrupt_actor: InterruptCallback,
    ) -> None:
        self._entities = entities
        self._event = event_factory
        self._schedule = schedule
        self._take_schedule_order = take_schedule_order
        self._catalog = catalog
        self._random = random
        self._interrupt_actor = interrupt_actor

    def resolve(
        self,
        item: ScheduledItem,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("resolution is missing its action binding")
        for effect in item.effects:
            if isinstance(effect, AreaEffect):
                self._resolve_area(item, effect, due_time, eligible_alive, events)
                continue
            if isinstance(effect, AttackGate):
                self._resolve_attack(
                    item,
                    effect,
                    due_time,
                    eligible_alive,
                    events,
                )
                continue
            if isinstance(effect, ChanceGate):
                self._resolve_chance(
                    item,
                    effect,
                    due_time,
                    eligible_alive,
                    events,
                )
                continue
            if isinstance(effect, OutcomeConditional):
                self._resolve_outcome_conditional(item, effect, due_time, eligible_alive, events)
                continue
            self._resolve_direct(item, effect, due_time, eligible_alive, events)

    def resolve_weapon_attack(
        self,
        item: ScheduledItem,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        """Resolve one generic weapon attempt through triggers, defenses, and damage."""

        if item.binding is None or item.weapon_attack is None:
            raise SimulationConfigurationError("weapon attack is missing its binding or spec")
        actor = self._entities.get(item.actor_id)
        target = (
            self._entities.get(item.binding.target_entity_id)
            if item.binding.target_entity_id is not None
            else None
        )
        if actor is None or target is None:
            raise SimulationConfigurationError("weapon attack requires actor and entity target")
        if actor.entity_id not in eligible_alive or target.entity_id not in eligible_alive:
            return

        action = self._catalog.get(item.action_key)
        action_tags = frozenset(action.tags)
        contexts = self._matching_trigger_contexts(actor, item.action_key, action_tags)
        fired_attempt_contexts = self._resolve_trigger_moment(
            contexts,
            TriggerMoment.ATTEMPT,
            actor,
            item,
            due_time,
            eligible_alive,
            events,
        )
        modifiers = tuple(
            context.trigger.attack_modifier
            for context in fired_attempt_contexts
            if context.trigger.attack_modifier is not None
        )

        attack = item.weapon_attack
        attack_rating = self._scalar_or_default(
            actor,
            attack.attack_rating_scalar,
            attack.default_attack_rating,
        ) + sum(modifier.attack_rating_bonus for modifier in modifiers)
        defense = self._scalar_or_default(
            target,
            attack.defense_scalar,
            attack.default_defense,
        )
        bypass_defense = any(modifier.bypass_defense for modifier in modifiers)
        hit_chance = attack.hit_chance(attack_rating, defense, bypass=bypass_defense)
        roll, hit_roll_succeeded = self._chance_roll(hit_chance)
        events.append(
            self._event(
                EventKind.ATTACK_ROLLED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=actor.entity_id,
                target_entity_id=target.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("attack_rating", attack_rating),
                    NamedScalar("defense", defense),
                    NamedScalar("hit_chance", hit_chance),
                    NamedScalar("roll", roll),
                ),
                tags=(
                    f"weapon.{attack.weapon_slot}",
                    "result.hit_roll" if hit_roll_succeeded else "result.miss",
                    "defense.bypassed" if bypass_defense else "defense.checked",
                ),
            )
        )
        if not hit_roll_succeeded:
            return

        bypass_passive = any(modifier.bypass_passive_defense for modifier in modifiers)
        if not bypass_passive and "control.stun" not in target.effective_tags:
            for defense_key in attack.passive_defense_keys:
                chance = max(
                    0.0,
                    min(
                        1.0,
                        self._scalar_or_default(
                            target,
                            f"passive.{defense_key}.chance",
                            0.0,
                        ),
                    ),
                )
                if chance <= 0.0:
                    continue
                passive_roll, defended = self._chance_roll(chance)
                if not defended:
                    continue
                events.append(
                    self._event(
                        EventKind.PASSIVE_DEFENSE_TRIGGERED,
                        due_time,
                        correlation_id=item.correlation_id,
                        source_entity_id=target.entity_id,
                        target_entity_id=actor.entity_id,
                        action_key=item.action_key,
                        scalars=(
                            NamedScalar("chance", chance),
                            NamedScalar("roll", passive_roll),
                        ),
                        tags=(
                            f"passive_defense.{defense_key}",
                            f"weapon.{attack.weapon_slot}",
                        ),
                    )
                )
                return

        minimum = (
            self._scalar_or_default(
                actor,
                attack.minimum_damage_scalar,
                attack.minimum_damage,
            )
            if attack.minimum_damage_scalar is not None
            else attack.minimum_damage
        )
        maximum = (
            self._scalar_or_default(
                actor,
                attack.maximum_damage_scalar,
                attack.maximum_damage,
            )
            if attack.maximum_damage_scalar is not None
            else attack.maximum_damage
        )
        if minimum < 0.0 or maximum < minimum:
            raise SimulationConfigurationError("resolved weapon damage range is invalid")
        requested = self._random.uniform(minimum, maximum)
        damage_multiplier = 1.0
        bonus_damage = 0.0
        damage_type = attack.damage_type
        modifier_tags: list[str] = []
        for modifier in modifiers:
            damage_multiplier *= modifier.damage_multiplier
            bonus_damage += self._random.uniform(
                modifier.bonus_damage_minimum,
                modifier.bonus_damage_maximum,
            )
            if modifier.damage_type_override is not None:
                damage_type = modifier.damage_type_override
            modifier_tags.extend(modifier.tags)
        requested = (requested + bonus_damage) * damage_multiplier
        effective = self._apply_weapon_damage(
            item,
            target,
            requested,
            damage_type,
            due_time,
            events,
            extra_tags=tuple(
                dict.fromkeys(
                    (
                        "attack.weapon",
                        f"weapon.{attack.weapon_slot}",
                        *modifier_tags,
                    )
                )
            ),
        )
        self._resolve_trigger_moment(
            contexts,
            TriggerMoment.HIT,
            actor,
            item,
            due_time,
            eligible_alive,
            events,
        )
        if effective > 0.0:
            self._resolve_trigger_moment(
                contexts,
                TriggerMoment.DAMAGE,
                actor,
                item,
                due_time,
                eligible_alive,
                events,
            )

    def _resolve_area(
        self,
        item: ScheduledItem,
        effect: AreaEffect,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("area resolution requires an action binding")
        actor = self._entity(item.actor_id)
        if actor.entity_id not in eligible_alive:
            return
        center = self._area_center(effect, item.binding)
        candidates = [
            entity
            for entity in self._entities.values()
            if entity.entity_id in eligible_alive
            and self._relation(actor, entity) in effect.allowed_relations
            and hypot(entity.position.x - center.x, entity.position.y - center.y) <= effect.radius
        ]
        candidates.sort(
            key=lambda entity: (
                hypot(entity.position.x - center.x, entity.position.y - center.y),
                entity.entity_id,
            )
        )
        if effect.maximum_targets is not None:
            candidates = candidates[: effect.maximum_targets]
        for target in candidates:
            target_item = replace(
                item,
                binding=ActionBinding(
                    actor_id=item.binding.actor_id,
                    target_kind=TargetKind.ENTITY,
                    target_entity_id=target.entity_id,
                ),
            )
            for nested in effect.effects:
                if isinstance(nested, AttackGate):
                    self._resolve_attack(
                        target_item,
                        nested,
                        due_time,
                        eligible_alive,
                        events,
                    )
                elif isinstance(nested, ChanceGate):
                    self._resolve_chance(
                        target_item,
                        nested,
                        due_time,
                        eligible_alive,
                        events,
                    )
                elif isinstance(nested, OutcomeConditional):
                    self._resolve_outcome_conditional(
                        target_item, nested, due_time, eligible_alive, events
                    )
                else:
                    self._resolve_direct(
                        target_item,
                        nested,
                        due_time,
                        eligible_alive,
                        events,
                    )

    def _resolve_attack(
        self,
        item: ScheduledItem,
        effect: AttackGate,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        if item.binding is None or item.binding.target_entity_id is None:
            raise SimulationConfigurationError("attack resolution requires an entity target")
        actor = self._entity(item.actor_id)
        target = self._entity(item.binding.target_entity_id)
        if actor.entity_id not in eligible_alive or target.entity_id not in eligible_alive:
            return
        action = self._catalog.get(item.action_key)
        action_tags = frozenset(action.tags)
        contexts = self._matching_trigger_contexts(actor, item.action_key, action_tags)
        fired_attempt_contexts = self._resolve_trigger_moment(
            contexts,
            TriggerMoment.ATTEMPT,
            actor,
            item,
            due_time,
            eligible_alive,
            events,
        )
        modifiers = tuple(
            context.trigger.attack_modifier
            for context in fired_attempt_contexts
            if context.trigger.attack_modifier is not None
        )
        attack_rating = self._required_scalar(actor, effect.attack_rating_key) + sum(
            modifier.attack_rating_bonus for modifier in modifiers
        )
        defense_rating = self._required_scalar(target, effect.defense_rating_key)
        bypass_defense = any(modifier.bypass_defense for modifier in modifiers)
        chance = (
            100
            if bypass_defense
            else (
                melee_hit_chance_percent(attack_rating, defense_rating)
                if effect.kind is AttackKind.BASIC
                else power_hit_chance_percent(attack_rating, defense_rating)
            )
        )
        roll = self._random.randbelow(100)
        hit = roll < chance
        events.append(
            self._event(
                EventKind.ATTACK_RESOLVED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=target.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("attack_rating", attack_rating),
                    NamedScalar("defense_rating", defense_rating),
                    NamedScalar("chance_percent", float(chance)),
                    NamedScalar("roll", float(roll)),
                    NamedScalar("hit", float(hit)),
                ),
                tags=(
                    f"attack.{effect.kind.value}",
                    f"attack.{effect.attack_key}",
                    "outcome.hit" if hit else "outcome.miss",
                ),
            )
        )
        if not hit:
            return
        bypass_passive = any(modifier.bypass_passive_defense for modifier in modifiers)
        if (
            "combat.ignore_passive_defense" not in actor.effective_tags
            and "control.stun" not in target.effective_tags
            and not bypass_passive
        ):
            for passive_key in effect.passive_defense_keys:
                passive_chance = min(75.0, self._required_scalar(target, passive_key))
                if passive_chance < 0.0:
                    raise SimulationConfigurationError(
                        f"entity {target.entity_id} scalar {passive_key} must not be negative"
                    )
                passive_roll = self._random.randbelow(100)
                triggered = passive_roll < passive_chance
                events.append(
                    self._event(
                        EventKind.PASSIVE_DEFENSE_RESOLVED,
                        due_time,
                        correlation_id=item.correlation_id,
                        source_entity_id=target.entity_id,
                        target_entity_id=actor.entity_id,
                        action_key=item.action_key,
                        scalars=(
                            NamedScalar("chance_percent", passive_chance),
                            NamedScalar("roll", float(passive_roll)),
                            NamedScalar("triggered", float(triggered)),
                        ),
                        tags=(
                            f"passive.{passive_key}",
                            "outcome.triggered" if triggered else "outcome.not_triggered",
                        ),
                    )
                )
                if triggered:
                    return
        self._drop_travel_stance(
            item,
            target,
            due_time,
            events,
            reason="hit",
        )
        before_health = target.scalars.get("health", 0.0)
        damage_multiplier = 1.0
        for modifier in modifiers:
            damage_multiplier *= modifier.damage_multiplier
        for nested in effect.effects:
            resolved_nested = (
                replace(
                    nested,
                    amount=self._scaled_amount(nested.amount, damage_multiplier),
                )
                if isinstance(nested, DealDamage) and damage_multiplier != 1.0
                else nested
            )
            if isinstance(resolved_nested, ChanceGate):
                self._resolve_chance(item, resolved_nested, due_time, eligible_alive, events)
            elif isinstance(resolved_nested, OutcomeConditional):
                self._resolve_outcome_conditional(
                    item, resolved_nested, due_time, eligible_alive, events
                )
            else:
                self._resolve_direct(item, resolved_nested, due_time, eligible_alive, events)
        for modifier in modifiers:
            if modifier.bonus_damage_maximum <= 0.0:
                continue
            bonus = self._random.uniform(
                modifier.bonus_damage_minimum,
                modifier.bonus_damage_maximum,
            )
            base_damage = next(
                (nested for nested in effect.effects if isinstance(nested, DealDamage)),
                None,
            )
            if modifier.damage_type_override is not None:
                damage_type = modifier.damage_type_override
            elif base_damage is not None:
                damage_type = base_damage.damage_type.value
            else:
                raise SimulationConfigurationError(
                    "bonus attack damage requires a typed base-damage effect or override"
                )
            self._deal_damage(
                item,
                DealDamage(
                    SubjectRef.TARGET,
                    max(bonus, 1e-12),
                    damage_type,
                    uses_resistance=True,
                    source_key="weapon_power.attack_modifier",
                ),
                target,
                due_time,
                events,
            )
        self._resolve_trigger_moment(
            contexts,
            TriggerMoment.HIT,
            actor,
            item,
            due_time,
            eligible_alive,
            events,
        )
        if target.scalars.get("health", 0.0) < before_health:
            self._resolve_trigger_moment(
                contexts,
                TriggerMoment.DAMAGE,
                actor,
                item,
                due_time,
                eligible_alive,
                events,
            )

    def _resolve_chance(
        self,
        item: ScheduledItem,
        effect: ChanceGate,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("chance resolution is missing its action binding")
        roll = self._random.random()
        triggered = roll < effect.probability
        events.append(
            self._event(
                EventKind.CHANCE_RESOLVED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=item.binding.target_entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("probability", effect.probability),
                    NamedScalar("roll", roll),
                    NamedScalar("triggered", float(triggered)),
                ),
                tags=(
                    f"chance.{effect.chance_key}",
                    "outcome.triggered" if triggered else "outcome.not_triggered",
                ),
            )
        )
        if triggered:
            for nested in effect.effects:
                if isinstance(nested, OutcomeConditional):
                    self._resolve_outcome_conditional(
                        item, nested, due_time, eligible_alive, events
                    )
                else:
                    self._resolve_direct(item, nested, due_time, eligible_alive, events)

    def _resolve_direct(
        self,
        item: ScheduledItem,
        effect: DirectEffectPrimitive,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> EffectOutcome:
        if item.binding is None:
            raise SimulationConfigurationError("resolution is missing its action binding")
        subject = self._subject_entity(effect, item.binding)
        primitive_kind = type(effect).__name__
        if subject is not None and subject.entity_id not in eligible_alive:
            return EffectOutcome(
                EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id,
                tags=("reason.subject_not_alive",),
            )
        if isinstance(effect, DealDamage):
            before = subject.scalars.get("health", 0.0) if subject is not None else 0.0
            self._deal_damage(item, effect, subject, due_time, events)
            after = subject.scalars.get("health", 0.0) if subject is not None else before
            effective = max(0.0, before - after)
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if effective > 0.0 else EffectOutcomeKind.RESISTED,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                magnitude=effective,
            )
        if isinstance(effect, RestoreResource):
            before = subject.scalars.get(effect.resource_key, 0.0) if subject is not None else 0.0
            self._restore_resource(item, effect, subject, due_time, events)
            after = subject.scalars.get(effect.resource_key, 0.0) if subject is not None else before
            effective = max(0.0, after - before)
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if effective > 0.0 else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                magnitude=effective,
            )
        if isinstance(effect, TransferResource):
            source = self._entity_for_ref(effect.from_subject, item.binding)
            destination = self._entity_for_ref(effect.to_subject, item.binding)
            if (
                source is None
                or destination is None
                or source.entity_id not in eligible_alive
                or destination.entity_id not in eligible_alive
            ):
                return EffectOutcome(
                    EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    tags=("reason.transfer_endpoint_not_alive",),
                )
            before = (
                source.scalars.get(effect.resource_key, 0.0),
                destination.scalars.get(effect.resource_key, 0.0),
            )
            self._transfer_resource(item, effect, due_time, events)
            after = (
                source.scalars.get(effect.resource_key, 0.0),
                destination.scalars.get(effect.resource_key, 0.0),
            )
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=destination.entity_id,
                magnitude=max(0.0, before[0] - after[0]),
            )
        if isinstance(effect, ModifyScalar):
            before = subject.scalars.get(effect.scalar_key, 0.0) if subject is not None else 0.0
            self._modify_scalar(item, effect, subject, due_time, events)
            after = subject.scalars.get(effect.scalar_key, 0.0) if subject is not None else before
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                effect_key=effect.scalar_key,
                magnitude=after - before,
            )
        if isinstance(effect, ModifyTag):
            before = effect.tag in subject.tags if subject is not None else False
            self._modify_tag(item, effect, subject, due_time, events)
            after = effect.tag in subject.tags if subject is not None else before
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                effect_key=effect.tag,
            )
        if isinstance(effect, ApplyEffect):
            return self._apply_effect(item, effect, subject, due_time, events)
        if isinstance(effect, RemoveEffect):
            before = len(subject.effects) if subject is not None else 0
            self._remove_effect(item, effect, subject, due_time, events)
            after = len(subject.effects) if subject is not None else before
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after < before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                effect_key=effect.effect_key or effect.matching_tag,
                magnitude=float(before - after),
            )
        if isinstance(effect, MoveEntity):
            before = subject.position if subject is not None else None
            self._move_entity(item, effect, subject, due_time, events)
            after = subject.position if subject is not None else before
            moved = (
                hypot(after.x - before.x, after.y - before.y)
                if before is not None and after is not None
                else 0.0
            )
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if moved > 0.0 else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                magnitude=moved,
            )
        if isinstance(effect, TransferItem):
            source = self._entity_for_ref(effect.from_subject, item.binding)
            destination = self._entity_for_ref(effect.to_subject, item.binding)
            if (
                source is None
                or destination is None
                or source.entity_id not in eligible_alive
                or destination.entity_id not in eligible_alive
            ):
                return EffectOutcome(
                    EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    tags=("reason.transfer_endpoint_not_alive",),
                )
            item_id = effect.item_id or item.binding.item_id
            before = (
                source.inventory.get(item_id, 0.0) if item_id is not None else 0.0,
                destination.inventory.get(item_id, 0.0) if item_id is not None else 0.0,
            )
            self._transfer_item(item, effect, due_time, events)
            after = (
                source.inventory.get(item_id, 0.0) if item_id is not None else before[0],
                destination.inventory.get(item_id, 0.0) if item_id is not None else before[1],
            )
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=destination.entity_id,
                effect_key=item_id,
                magnitude=max(0.0, before[0] - after[0]),
            )
        if isinstance(effect, ModifyObjective):
            before = subject.scalars.get("objective_progress", 0.0) if subject is not None else 0.0
            self._modify_objective(item, effect, subject, due_time, events)
            after = (
                subject.scalars.get("objective_progress", 0.0) if subject is not None else before
            )
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                effect_key="objective_progress",
                magnitude=after - before,
            )
        if isinstance(effect, ChangeStance):
            before = subject.stance if subject is not None else None
            self._change_stance(item, effect, subject, due_time, events)
            after = subject.stance if subject is not None else before
            return EffectOutcome(
                EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                primitive_kind,
                subject_entity_id=subject.entity_id if subject is not None else None,
                effect_key=effect.stance.value,
            )
        raise SimulationConfigurationError(
            f"unsupported direct effect primitive: {type(effect).__name__}"
        )

    def _resolve_outcome_conditional(
        self,
        item: ScheduledItem,
        conditional: OutcomeConditional,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> EffectOutcome:
        outcome = self._resolve_direct(
            item,
            conditional.condition,
            due_time,
            eligible_alive,
            events,
        )
        matched = outcome.kind in conditional.outcomes
        events.append(
            self._event(
                "effect_outcome_resolved",
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=outcome.subject_entity_id,
                action_key=item.action_key,
                scalars=(NamedScalar("outcome_magnitude", outcome.magnitude),),
                tags=(
                    f"conditional.{conditional.conditional_key}",
                    f"outcome.{outcome.kind.value}",
                    "branch.effects" if matched else "branch.else_effects",
                ),
            )
        )
        branch = conditional.effects if matched else conditional.else_effects
        for effect in branch:
            self._resolve_direct(item, effect, due_time, eligible_alive, events)
        return outcome

    def expire_effect(
        self,
        item: ScheduledItem,
        due_time: int,
        events: list[Event],
    ) -> None:
        if item.effect_entity_id is None or item.effect_storage_key is None:
            raise SimulationConfigurationError("effect expiry is missing its entity or storage key")
        subject = self._entities.get(item.effect_entity_id)
        if subject is None:
            return
        active = subject.effects.get(item.effect_storage_key)
        if (
            active is None
            or active.effect_key != item.expected_effect_key
            or active.instance_id != item.expected_effect_instance_id
            or active.expires_at_ms != due_time
        ):
            return
        subject.effects.pop(item.effect_storage_key)
        events.append(self._effect_removed_event(subject, active, due_time, item, "reason.expired"))

    def resolve_effect_pulse(
        self,
        item: ScheduledItem,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        if (
            item.effect_entity_id is None
            or item.effect_storage_key is None
            or item.periodic_key is None
        ):
            raise SimulationConfigurationError("effect pulse is missing effect identity")
        subject = self._entities.get(item.effect_entity_id)
        if subject is None:
            return
        active = subject.effects.get(item.effect_storage_key)
        if (
            active is None
            or active.effect_key != item.expected_effect_key
            or active.instance_id != item.expected_effect_instance_id
        ):
            return
        periodic = next(
            (
                modifier
                for modifier in active.modifiers
                if isinstance(modifier, PeriodicPulse)
                and modifier.periodic_key == item.periodic_key
            ),
            None,
        )
        if (
            periodic is None
            or item.pulse_index > periodic.tick_count
            or item.effects != periodic.effects
        ):
            raise SimulationConfigurationError("effect pulse does not match its active modifier")
        events.append(
            self._event(
                EventKind.EFFECT_PULSED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(NamedScalar("pulse_index", float(item.pulse_index)),),
                tags=(
                    f"effect.{active.effect_key}",
                    f"periodic.{periodic.periodic_key}",
                ),
            )
        )
        for effect in item.effects:
            self._resolve_direct(item, effect, due_time, eligible_alive, events)

    def resolve_deaths(
        self,
        due_time: int,
        events: list[Event],
        life_terminated: set[str],
    ) -> None:
        for entity_id in sorted(self._entities):
            entity = self._entities[entity_id]
            if entity.alive and entity.scalars.get("health", 1.0) <= 0.0:
                entity.alive = False
                life_terminated.add(entity.life_id)
                events.append(
                    self._event(
                        EventKind.ENTITY_DIED,
                        due_time,
                        target_entity_id=entity.entity_id,
                        tags=(f"life.{entity.life_id}",),
                    )
                )

    def _apply_weapon_damage(
        self,
        item: ScheduledItem,
        subject: EntityState,
        amount: float,
        damage_type: str,
        due_time: int,
        events: list[Event],
        *,
        extra_tags: tuple[str, ...] = (),
    ) -> float:
        actor = self._entity(item.actor_id)
        amount *= self._scalar_or_default(actor, "outgoing.damage.factor", 1.0)
        amount *= self._scalar_or_default(
            actor,
            "outgoing.weapon.damage.factor",
            1.0,
        )
        raw_resistance = subject.scalars.get(
            f"resistance.{damage_type}", subject.scalars.get("resistance.all", 0.0)
        )
        resistance_cap = subject.scalars.get(
            f"resistance_cap.{damage_type}", subject.scalars.get("resistance_cap", 0.75)
        )
        resistance_floor = subject.scalars.get(
            f"resistance_floor.{damage_type}",
            subject.scalars.get("resistance_floor", -1.0),
        )
        if resistance_cap < resistance_floor:
            raise SimulationConfigurationError("resistance cap is below resistance floor")
        resistance = max(resistance_floor, min(resistance_cap, raw_resistance))
        after_resistance = max(0.0, amount * (1.0 - resistance))
        after_absorbers, absorbed = self._consume_weapon_absorbers(
            item,
            subject,
            damage_type,
            after_resistance,
            due_time,
            events,
        )
        before = subject.scalars.get("health", 0.0)
        after = max(0.0, before - after_absorbers)
        subject.scalars["health"] = after
        event_tags = [f"damage.{damage_type}", *extra_tags]
        if item.trigger_key is not None:
            event_tags.append(f"trigger.{item.trigger_key}")
        events.append(
            self._event(
                EventKind.DAMAGE_APPLIED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("requested", amount),
                    NamedScalar("resistance", resistance),
                    NamedScalar("resisted", amount - after_resistance),
                    NamedScalar("absorbed", absorbed),
                    NamedScalar("effective", before - after),
                ),
                tags=tuple(dict.fromkeys(event_tags)),
            )
        )
        if before - after > 0.0:
            self._drop_travel_stance(item, subject, due_time, events, reason="damage")
            self._interrupt_actor(subject.entity_id, "damage", due_time, events)
        return before - after

    def _consume_weapon_absorbers(
        self,
        item: ScheduledItem,
        subject: EntityState,
        damage_type: str,
        amount: float,
        due_time: int,
        events: list[Event],
    ) -> tuple[float, float]:
        remaining = amount
        absorbed_total = 0.0
        candidates = sorted(
            (
                (storage_key, active)
                for storage_key, active in subject.effects.items()
                if active.magnitude > 0.0
                and (
                    "damage.absorb.all" in active.tags
                    or f"damage.absorb.{damage_type}" in active.tags
                )
            ),
            key=lambda value: (value[1].expires_at_ms, value[0]),
        )
        for storage_key, active in candidates:
            if remaining <= 0.0:
                break
            absorbed = min(remaining, active.magnitude)
            if absorbed <= 0.0:
                continue
            active.magnitude -= absorbed
            remaining -= absorbed
            absorbed_total += absorbed
            events.append(
                self._event(
                    EventKind.ABSORBER_CONSUMED,
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=active.source_entity_id,
                    target_entity_id=subject.entity_id,
                    action_key=item.action_key,
                    scalars=(
                        NamedScalar("absorbed", absorbed),
                        NamedScalar("remaining", active.magnitude),
                    ),
                    tags=(
                        f"effect.{active.effect_key}",
                        f"damage.{damage_type}",
                    ),
                )
            )
            if active.magnitude <= 0.0 and subject.effects.get(storage_key) is active:
                subject.effects.pop(storage_key)
                events.append(
                    self._effect_removed_event(
                        subject,
                        active,
                        due_time,
                        item,
                        "reason.depleted",
                    )
                )
        return remaining, absorbed_total

    def _matching_trigger_contexts(
        self,
        actor: EntityState,
        action_key: str,
        action_tags: frozenset[str],
    ) -> tuple[_TriggerContext, ...]:
        contexts: list[_TriggerContext] = []
        for storage_key in sorted(actor.effects):
            active = actor.effects[storage_key]
            trigger = self._catalog.trigger_for_effect(active.effect_key)
            if trigger is not None and trigger.matches(action_key, action_tags):
                contexts.append(_TriggerContext(storage_key, active, trigger))
        return tuple(contexts)

    def _resolve_trigger_moment(
        self,
        contexts: tuple[_TriggerContext, ...],
        moment: TriggerMoment,
        actor: EntityState,
        item: ScheduledItem,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> tuple[_TriggerContext, ...]:
        fired_contexts: list[_TriggerContext] = []
        for context in contexts:
            trigger = context.trigger
            if trigger.fire_on is moment:
                roll, fired = self._chance_roll(trigger.chance)
                events.append(
                    self._event(
                        EventKind.TRIGGER_CHECKED,
                        due_time,
                        correlation_id=item.correlation_id,
                        source_entity_id=actor.entity_id,
                        target_entity_id=(
                            item.binding.target_entity_id if item.binding is not None else None
                        ),
                        action_key=item.action_key,
                        scalars=(
                            NamedScalar("chance", trigger.chance),
                            NamedScalar("roll", roll),
                        ),
                        tags=(
                            f"trigger.{trigger.trigger_key}",
                            f"moment.{moment.value}",
                            "result.fired" if fired else "result.not_fired",
                        ),
                    )
                )
                if fired:
                    fired_contexts.append(context)
                    events.append(
                        self._event(
                            EventKind.TRIGGER_FIRED,
                            due_time,
                            correlation_id=item.correlation_id,
                            source_entity_id=actor.entity_id,
                            target_entity_id=(
                                item.binding.target_entity_id if item.binding is not None else None
                            ),
                            action_key=item.action_key,
                            tags=tuple(
                                dict.fromkeys(
                                    (
                                        f"trigger.{trigger.trigger_key}",
                                        f"moment.{moment.value}",
                                        *trigger.tags,
                                    )
                                )
                            ),
                        )
                    )
                    if trigger.payload:
                        if item.binding is None:
                            raise SimulationConfigurationError(
                                "trigger payload requires the qualifying action binding"
                            )
                        payload_item = ScheduledItem(
                            due_time_ms=due_time,
                            order=item.order,
                            kind=ScheduledKind.RESOLUTION,
                            actor_id=item.actor_id,
                            correlation_id=item.correlation_id,
                            action_key=item.action_key,
                            binding=item.binding,
                            phase_duration_ms=item.phase_duration_ms,
                            effects=trigger.payload,
                            trigger_key=trigger.trigger_key,
                        )
                        self.resolve(payload_item, due_time, eligible_alive, events)
            if trigger.consume_on.value == moment.value:
                current = actor.effects.get(context.storage_key)
                if current is context.active:
                    actor.effects.pop(context.storage_key)
                    events.append(
                        self._effect_removed_event(
                            actor,
                            context.active,
                            due_time,
                            item,
                            "reason.trigger_consumed",
                        )
                    )
        return tuple(fired_contexts)

    def _chance_roll(self, chance: float) -> tuple[float, bool]:
        if chance <= 0.0:
            return 1.0, False
        if chance >= 1.0:
            return 0.0, True
        roll = self._random.random()
        return roll, roll < chance

    def _deal_damage(
        self,
        item: ScheduledItem,
        effect: DealDamage,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("damage requires an entity subject")
        amount = self._resolve_amount(effect.amount)
        actor = self._entity(item.actor_id)
        amount *= self._scalar_or_default(actor, "outgoing.damage.factor", 1.0)
        factor_key = (
            "outgoing.proc.damage.factor"
            if effect.source_key is not None and effect.source_key.startswith("proc.")
            else (
                "outgoing.power.damage.factor"
                if self._action_has_tag(item.action_key, "power")
                else "outgoing.weapon.damage.factor"
            )
        )
        amount *= self._scalar_or_default(actor, factor_key, 1.0)
        mitigated = amount
        resistance = 0.0
        armor_piercing = 0.0
        if effect.uses_resistance:
            resistance = self._required_scalar(subject, f"resist.{effect.damage_type.value}")
            resistance += sum(
                modifier.amount
                for storage_key in sorted(subject.effects)
                for active in (subject.effects[storage_key],)
                for modifier in active.modifiers
                if isinstance(modifier, ResistanceAdjustment)
                and modifier.damage_type is effect.damage_type
            )
            armor_piercing = self._required_scalar(actor, "armor_piercing")
            protection_applies = f"protection.{effect.damage_type.value}" in subject.effective_tags
            protection_trains = 0
            if protection_applies:
                raw_trains = self._required_scalar(subject, "protection.trains")
                if raw_trains < 0 or not raw_trains.is_integer():
                    raise SimulationConfigurationError(
                        f"entity {subject.entity_id} protection.trains must be a "
                        "non-negative integer"
                    )
                protection_trains = int(raw_trains)
            resistance = effective_resistance(
                resistance,
                protection_trains=protection_trains,
                incoming_trains=effect.power_trains,
                protection_applies=protection_applies,
            )
            mitigated = resisted_amount(amount, resistance, armor_piercing)
            if f"immunity.damage.{effect.damage_type.value}" in subject.effective_tags:
                mitigated = 0.0
            if "state.sitting" in subject.effective_tags:
                mitigated *= 2.5
        before = subject.scalars.get("health", 0.0)
        after = max(0.0, before - mitigated)
        subject.scalars["health"] = after
        events.append(
            self._event(
                EventKind.DAMAGE_APPLIED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("requested", amount),
                    NamedScalar("mitigated", mitigated),
                    NamedScalar("resistance_percent", resistance),
                    NamedScalar("armor_piercing", armor_piercing),
                    NamedScalar("effective", before - after),
                ),
                tags=(
                    f"damage.{effect.damage_type.value}",
                    *((f"damage_source.{effect.source_key}",) if effect.source_key else ()),
                ),
            )
        )
        if mitigated > 0.0:
            self._accumulate_damage_breakpoints(
                item,
                subject,
                effect.damage_type,
                mitigated,
                due_time,
                events,
            )
        if before - after > 0.0:
            self._drop_travel_stance(
                item,
                subject,
                due_time,
                events,
                reason="damage",
            )
            self._interrupt_actor(subject.entity_id, "damage", due_time, events)

    def _accumulate_damage_breakpoints(
        self,
        item: ScheduledItem,
        subject: EntityState,
        damage_type: DamageType,
        amount: float,
        due_time: int,
        events: list[Event],
    ) -> None:
        for storage_key in sorted(tuple(subject.effects)):
            active = subject.effects.get(storage_key)
            if active is None:
                continue
            matching = tuple(
                modifier
                for modifier in active.modifiers
                if isinstance(modifier, DamageBreakpoint) and damage_type in modifier.damage_types
            )
            should_remove = False
            removal_scalars: tuple[NamedScalar, ...] = ()
            for modifier in matching:
                accumulated = active.modifier_values[modifier.state_key] + amount
                active.modifier_values[modifier.state_key] = accumulated
                if accumulated > modifier.threshold:
                    should_remove = True
                    removal_scalars = (
                        NamedScalar("breakpoint", modifier.threshold),
                        NamedScalar("accumulated_damage", accumulated),
                    )
                    break
            if not should_remove:
                continue
            subject.effects.pop(storage_key)
            events.append(
                self._effect_removed_event(
                    subject,
                    active,
                    due_time,
                    item,
                    "reason.damage_breakpoint",
                    scalars=removal_scalars,
                )
            )

    def _drop_travel_stance(
        self,
        item: ScheduledItem,
        subject: EntityState,
        due_time: int,
        events: list[Event],
        *,
        reason: str,
    ) -> None:
        if subject.stance is not CombatStance.TRAVEL:
            return
        previous = subject.stance
        subject.stance = CombatStance.NORMAL
        events.append(
            self._event(
                EventKind.STANCE_CHANGED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                tags=(
                    f"stance.from.{previous.value}",
                    f"stance.to.{subject.stance.value}",
                    f"reason.{reason}",
                ),
            )
        )

    def _change_stance(
        self,
        item: ScheduledItem,
        effect: ChangeStance,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("stance change requires an entity subject")
        previous = subject.stance
        if previous is effect.stance:
            return
        subject.stance = effect.stance
        events.append(
            self._event(
                EventKind.STANCE_CHANGED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                tags=(
                    f"stance.from.{previous.value}",
                    f"stance.to.{effect.stance.value}",
                    "reason.action",
                ),
            )
        )

    def _restore_resource(
        self,
        item: ScheduledItem,
        effect: RestoreResource,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("resource restoration requires an entity subject")
        amount = self._resolve_amount(effect.amount)
        if effect.resource_key == "health":
            amount *= self._scalar_or_default(
                self._entity(item.actor_id),
                "outgoing.power.healing.factor",
                1.0,
            )
        mitigated = amount
        resistance = 0.0
        armor_piercing = 0.0
        restoration_blocked = any(
            any(
                isinstance(modifier, ResourceImmunity)
                and modifier.resource_key == effect.resource_key
                for modifier in active.modifiers
            )
            and active.trains >= effect.power_trains
            for active in subject.effects.values()
        )

        if effect.uses_resistance:
            actor = self._entity(item.actor_id)
            if effect.resistance_type is None:
                raise SimulationConfigurationError("resisted restoration requires a type")
            resistance = self._required_scalar(subject, f"resist.{effect.resistance_type.value}")
            armor_piercing = self._required_scalar(actor, "armor_piercing")
            resistance = effective_resistance(
                resistance,
                protection_trains=0,
                incoming_trains=effect.power_trains,
                protection_applies=False,
            )
            mitigated = resisted_amount(amount, resistance, armor_piercing)
        if restoration_blocked:
            mitigated = 0.0
        before = subject.scalars.get(effect.resource_key, 0.0)
        maximum = subject.maximums.get(effect.resource_key)
        after = before + mitigated
        if maximum is not None:
            after = min(after, maximum)
        subject.scalars[effect.resource_key] = after
        events.append(
            self._event(
                EventKind.RESOURCE_RESTORED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("requested", amount),
                    NamedScalar("mitigated", mitigated),
                    NamedScalar("resistance_percent", resistance),
                    NamedScalar("armor_piercing", armor_piercing),
                    NamedScalar("effective", after - before),
                ),
                tags=(
                    f"resource.{effect.resource_key}",
                    *(("outcome.blocked_by_resource_immunity",) if restoration_blocked else ()),
                ),
            )
        )

    def _transfer_resource(
        self,
        item: ScheduledItem,
        effect: TransferResource,
        due_time: int,
        events: list[Event],
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("resource transfer is missing its action binding")
        source = self._entity_for_ref(effect.from_subject, item.binding)
        destination = self._entity_for_ref(effect.to_subject, item.binding)
        if source is None or destination is None:
            raise SimulationConfigurationError("resource transfer requires entity subjects")

        requested = self._resolve_amount(effect.amount)
        source_before = max(0.0, source.scalars.get(effect.resource_key, 0.0))
        drained = min(requested, source_before)
        source_after = source_before - drained
        source.scalars[effect.resource_key] = source_after

        destination_before = max(0.0, destination.scalars.get(effect.resource_key, 0.0))
        credited_requested = drained * effect.efficiency
        destination_after = destination_before + credited_requested
        maximum = destination.maximums.get(effect.resource_key)
        if maximum is not None:
            destination_after = min(destination_after, maximum)
        destination.scalars[effect.resource_key] = destination_after
        credited = destination_after - destination_before

        events.append(
            self._event(
                EventKind.RESOURCE_TRANSFERRED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=source.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("requested", requested),
                    NamedScalar("drained", drained),
                    NamedScalar("efficiency", effect.efficiency),
                    NamedScalar("credited", credited),
                    NamedScalar("source_before", source_before),
                    NamedScalar("source_after", source_after),
                    NamedScalar("destination_before", destination_before),
                    NamedScalar("destination_after", destination_after),
                ),
                tags=(f"resource.{effect.resource_key}", "operation.transfer"),
            )
        )

    def _resolve_amount(
        self,
        amount: (float | UniformAmount | TriangularAmount | UniformIntegerAmount | WeightedAmount),
    ) -> float:
        if isinstance(amount, UniformAmount):
            return self._random.uniform(amount.minimum, amount.maximum)
        if isinstance(amount, TriangularAmount):
            return triangular_roll(
                amount.minimum,
                amount.maximum,
                self._random.random(),
                self._random.random(),
            )
        if isinstance(amount, UniformIntegerAmount):
            return float(
                amount.minimum + self._random.randbelow(amount.maximum - amount.minimum + 1)
            )
        if isinstance(amount, WeightedAmount):
            selected = self._random.randbelow(amount.total_weight)
            cumulative = 0
            for value, weight in amount.outcomes:
                cumulative += weight
                if selected < cumulative:
                    return value
            raise SimulationConfigurationError("weighted amount selection did not reach an outcome")
        return amount

    @staticmethod
    def _scaled_amount(
        amount: (float | UniformAmount | TriangularAmount | UniformIntegerAmount | WeightedAmount),
        factor: float,
    ) -> float | UniformAmount | TriangularAmount | WeightedAmount:
        if isinstance(amount, UniformAmount):
            return UniformAmount(amount.minimum * factor, amount.maximum * factor)
        if isinstance(amount, TriangularAmount):
            return TriangularAmount(amount.minimum * factor, amount.maximum * factor)
        if isinstance(amount, UniformIntegerAmount):
            return UniformAmount(amount.minimum * factor, amount.maximum * factor)
        if isinstance(amount, WeightedAmount):
            return WeightedAmount(
                tuple((value * factor, weight) for value, weight in amount.outcomes)
            )
        return amount * factor

    def _modify_scalar(
        self,
        item: ScheduledItem,
        effect: ModifyScalar,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("scalar modification requires an entity subject")
        before = subject.scalars.get(effect.scalar_key, 0.0)
        after = effect.amount if effect.operation is ScalarOperation.SET else before + effect.amount
        maximum = subject.maximums.get(effect.scalar_key)
        if maximum is not None:
            after = max(0.0, min(after, maximum))
        subject.scalars[effect.scalar_key] = after
        events.append(
            self._event(
                "scalar_modified",
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(NamedScalar("before", before), NamedScalar("after", after)),
                tags=(f"scalar.{effect.scalar_key}",),
            )
        )

    def _modify_tag(
        self,
        item: ScheduledItem,
        effect: ModifyTag,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("tag modification requires an entity subject")
        before = effect.tag in subject.tags
        if effect.operation is TagOperation.ADD:
            subject.tags.add(effect.tag)
        else:
            subject.tags.discard(effect.tag)
        after = effect.tag in subject.tags
        if before != after:
            events.append(
                self._event(
                    "tag_modified",
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=item.actor_id,
                    target_entity_id=subject.entity_id,
                    action_key=item.action_key,
                    tags=(effect.tag, "operation.add" if after else "operation.remove"),
                )
            )

    def _apply_effect(
        self,
        item: ScheduledItem,
        effect: ApplyEffect,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> EffectOutcome:
        if subject is None:
            raise SimulationConfigurationError("effect application requires an entity subject")
        immunity_tags = set(effect.immunity_tags)
        if "control.stun" in effect.tags:
            immunity_tags.add("immunity.stun")
        matching_immunity = tuple(sorted(immunity_tags & set(subject.effective_tags)))
        if matching_immunity:
            events.append(
                self._event(
                    EventKind.EFFECT_BLOCKED,
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=item.actor_id,
                    target_entity_id=subject.entity_id,
                    action_key=item.action_key,
                    tags=(
                        f"effect.{effect.effect_key}",
                        "reason.immune",
                        *matching_immunity,
                    ),
                )
            )
            return EffectOutcome(
                EffectOutcomeKind.BLOCKED_IMMUNITY,
                type(effect).__name__,
                subject_entity_id=subject.entity_id,
                effect_key=effect.effect_key,
                tags=matching_immunity,
            )
        storage_key = effect.stacking_key or effect.effect_key
        existing = subject.effects.get(storage_key)
        refreshed = existing is not None and existing.effect_key == effect.effect_key
        if existing is not None:
            if not should_overwrite_effect(
                incoming_order=effect.stack_order,
                existing_order=existing.stack_order,
                incoming_trains=effect.trains,
                existing_trains=existing.trains,
                priority=effect.stack_priority,
                same_power=refreshed,
            ):
                events.append(
                    self._event(
                        EventKind.EFFECT_BLOCKED,
                        due_time,
                        correlation_id=item.correlation_id,
                        source_entity_id=item.actor_id,
                        target_entity_id=subject.entity_id,
                        action_key=item.action_key,
                        scalars=(
                            NamedScalar("incoming_stack_order", float(effect.stack_order)),
                            NamedScalar("existing_stack_order", float(existing.stack_order)),
                            NamedScalar("incoming_trains", float(effect.trains)),
                            NamedScalar("existing_trains", float(existing.trains)),
                        ),
                        tags=(
                            f"effect.{effect.effect_key}",
                            "reason.stack_priority",
                        ),
                    )
                )
                return EffectOutcome(
                    EffectOutcomeKind.BLOCKED_STACK,
                    type(effect).__name__,
                    subject_entity_id=subject.entity_id,
                    effect_key=effect.effect_key,
                    tags=(f"incumbent.{existing.effect_key}",),
                )
            events.append(
                self._effect_removed_event(
                    subject,
                    existing,
                    due_time,
                    item,
                    "reason.replaced",
                )
            )
        application_order = self._take_schedule_order()
        instance_id = f"effect-instance:{application_order:012d}"
        active = ActiveEffectState(
            effect_key=effect.effect_key,
            source_entity_id=item.actor_id,
            instance_id=instance_id,
            magnitude=effect.magnitude,
            expires_at_ms=due_time + effect.duration_ms,
            stacking_key=effect.stacking_key,
            tags=set(effect.tags),
            modifiers=effect.modifiers,
            modifier_values={
                modifier.state_key: 0.0
                for modifier in effect.modifiers
                if isinstance(modifier, DamageBreakpoint)
            },
            application_order=application_order,
            stack_order=effect.stack_order,
            trains=effect.trains,
            stack_priority=effect.stack_priority,
        )
        subject.effects[storage_key] = active
        events.append(
            self._event(
                EventKind.EFFECT_ADDED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("magnitude", effect.magnitude),
                    NamedScalar("duration_ms", float(effect.duration_ms)),
                    NamedScalar("stack_order", float(effect.stack_order)),
                    NamedScalar("trains", float(effect.trains)),
                ),
                tags=(
                    f"effect.{effect.effect_key}",
                    "outcome.refreshed" if refreshed else "outcome.applied",
                ),
            )
        )
        if item.binding is None:
            raise SimulationConfigurationError("effect application requires a binding")
        for modifier in effect.modifiers:
            if not isinstance(modifier, PeriodicPulse):
                continue
            for pulse_index in range(1, modifier.tick_count + 1):
                self._schedule(
                    ScheduledItem(
                        due_time_ms=due_time + pulse_index * modifier.interval_ms,
                        order=self._take_schedule_order(),
                        kind=ScheduledKind.EFFECT_PULSE,
                        actor_id=item.actor_id,
                        correlation_id=item.correlation_id,
                        action_key=item.action_key,
                        binding=item.binding,
                        effects=modifier.effects,
                        effect_entity_id=subject.entity_id,
                        effect_storage_key=storage_key,
                        expected_effect_key=effect.effect_key,
                        expected_effect_instance_id=instance_id,
                        periodic_key=modifier.periodic_key,
                        pulse_index=pulse_index,
                        continuation_policy=ContinuationPolicy.EFFECT_INSTANCE_BOUND,
                    )
                )
        self._schedule(
            ScheduledItem(
                due_time_ms=active.expires_at_ms,
                order=self._take_schedule_order(),
                kind=ScheduledKind.EFFECT_EXPIRY,
                actor_id=item.actor_id,
                correlation_id=item.correlation_id,
                action_key=item.action_key,
                effect_entity_id=subject.entity_id,
                effect_storage_key=storage_key,
                expected_effect_key=effect.effect_key,
                expected_effect_instance_id=instance_id,
                continuation_policy=ContinuationPolicy.EFFECT_INSTANCE_BOUND,
            )
        )
        if "control.stun" in effect.tags:
            self._interrupt_actor(subject.entity_id, "stun", due_time, events)
        return EffectOutcome(
            EffectOutcomeKind.REFRESHED if refreshed else EffectOutcomeKind.APPLIED,
            type(effect).__name__,
            subject_entity_id=subject.entity_id,
            effect_key=effect.effect_key,
            magnitude=float(effect.duration_ms),
            tags=effect.tags,
        )

    def _remove_effect(
        self,
        item: ScheduledItem,
        effect: RemoveEffect,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("effect removal requires an entity subject")
        matching = [
            (storage_key, active)
            for storage_key, active in subject.effects.items()
            if (effect.effect_key is not None and active.effect_key == effect.effect_key)
            or (effect.matching_tag is not None and effect.matching_tag in active.tags)
        ]
        if effect.maximum_count is None:
            storage_keys = sorted(storage_key for storage_key, _ in matching)
        else:
            # Shadowbane dispels peel the newest matching effects first; this is what
            # makes later cover debuffs protect an earlier high-value mantle.
            matching.sort(
                key=lambda item: (item[1].application_order, item[0]),
                reverse=True,
            )
            storage_keys = [storage_key for storage_key, _ in matching[: effect.maximum_count]]
        for storage_key in storage_keys:
            active = subject.effects.pop(storage_key)
            events.append(
                self._effect_removed_event(subject, active, due_time, item, "reason.removed")
            )

    def _move_entity(
        self,
        item: ScheduledItem,
        effect: MoveEntity,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None or item.binding is None:
            raise SimulationConfigurationError("movement requires an entity and binding")
        before = subject.position
        if effect.mode is MovementMode.TELEPORT:
            if item.binding.position is None:
                raise SimulationConfigurationError("teleport movement requires a bound position")
            after = item.binding.position
        else:
            direction = self._movement_direction(item.binding, effect, subject)
            distance = effect.distance
            if distance is None:
                speed = (
                    subject.effective_scalar("move_speed")
                    if "move_speed" in subject.scalars
                    else 0.0
                )
                distance = speed * item.phase_duration_ms / 1_000.0
            after = Vector2(
                subject.position.x + direction.x * distance,
                subject.position.y + direction.y * distance,
            )
        subject.position = after
        events.append(
            self._event(
                EventKind.MOVEMENT_CHANGED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(
                    NamedScalar("from_x", before.x),
                    NamedScalar("from_y", before.y),
                    NamedScalar("to_x", after.x),
                    NamedScalar("to_y", after.y),
                ),
                tags=(f"movement.{effect.mode.value}",),
            )
        )

    def _movement_direction(
        self,
        binding: ActionBinding,
        effect: MoveEntity,
        subject: EntityState,
    ) -> Vector2:
        direction = binding.direction
        if direction is None and binding.target_entity_id is not None:
            actor = self._entity(binding.actor_id)
            target = self._entity(binding.target_entity_id)
            if effect.mode is MovementMode.PUSH:
                direction = Vector2(
                    target.position.x - actor.position.x,
                    target.position.y - actor.position.y,
                )
            elif effect.mode is MovementMode.PULL:
                direction = Vector2(
                    actor.position.x - target.position.x,
                    actor.position.y - target.position.y,
                )
            else:
                direction = Vector2(
                    target.position.x - subject.position.x,
                    target.position.y - subject.position.y,
                )
        if direction is None:
            raise SimulationConfigurationError("movement requires a direction or entity target")
        return self._normalized(direction)

    def _transfer_item(
        self,
        item: ScheduledItem,
        effect: TransferItem,
        due_time: int,
        events: list[Event],
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("item transfer is missing its action binding")
        source = self._entity_for_ref(effect.from_subject, item.binding)
        target = self._entity_for_ref(effect.to_subject, item.binding)
        item_id = effect.item_id or item.binding.item_id
        quantity = effect.quantity or item.binding.quantity
        if source is None or target is None or item_id is None or quantity is None:
            raise SimulationConfigurationError(
                "item transfer requires bound entities, item, and quantity"
            )
        available = source.inventory.get(item_id, 0.0)
        if available < quantity:
            events.append(
                self._event(
                    EventKind.ACTION_REJECTED,
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=item.actor_id,
                    action_key=item.action_key,
                    tags=("reason.insufficient_inventory_at_resolution",),
                )
            )
            return
        source.inventory[item_id] = available - quantity
        target.inventory[item_id] = target.inventory.get(item_id, 0.0) + quantity
        events.append(
            self._event(
                "item_transferred",
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=source.entity_id,
                target_entity_id=target.entity_id,
                action_key=item.action_key,
                scalars=(NamedScalar("quantity", quantity),),
                tags=(f"item.{item_id}",),
            )
        )

    def _modify_objective(
        self,
        item: ScheduledItem,
        effect: ModifyObjective,
        subject: EntityState | None,
        due_time: int,
        events: list[Event],
    ) -> None:
        if subject is None or subject.kind is not EntityKind.OBJECTIVE:
            raise SimulationConfigurationError(
                "objective modification requires an objective entity"
            )
        before = subject.scalars.get("objective_progress", 0.0)
        after = before + effect.progress_delta
        maximum = subject.maximums.get("objective_progress")
        if maximum is not None:
            after = max(-maximum, min(after, maximum))
        subject.scalars["objective_progress"] = after
        events.append(
            self._event(
                EventKind.OBJECTIVE_CHANGED,
                due_time,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                target_entity_id=subject.entity_id,
                action_key=item.action_key,
                scalars=(NamedScalar("before", before), NamedScalar("after", after)),
            )
        )

    def _effect_removed_event(
        self,
        subject: EntityState,
        active: ActiveEffectState,
        due_time: int,
        item: ScheduledItem,
        reason: str,
        *,
        scalars: tuple[NamedScalar, ...] = (),
    ) -> Event:
        return self._event(
            EventKind.EFFECT_REMOVED,
            due_time,
            correlation_id=item.correlation_id,
            source_entity_id=active.source_entity_id,
            target_entity_id=subject.entity_id,
            action_key=item.action_key,
            scalars=scalars,
            tags=(f"effect.{active.effect_key}", reason),
        )

    def _subject_entity(
        self,
        effect: DirectEffectPrimitive,
        binding: ActionBinding,
    ) -> EntityState | None:
        subject_ref = getattr(effect, "subject", None)
        if subject_ref is None:
            return None
        return self._entity_for_ref(subject_ref, binding)

    def _entity_for_ref(
        self,
        subject: SubjectRef,
        binding: ActionBinding,
    ) -> EntityState | None:
        if subject is SubjectRef.ACTOR:
            return self._entities.get(binding.actor_id)
        if subject is SubjectRef.TARGET:
            if binding.target_kind is TargetKind.SELF:
                return self._entities.get(binding.actor_id)
            if binding.target_entity_id is not None:
                return self._entities.get(binding.target_entity_id)
            return None
        if binding.objective_id is not None:
            return self._entities.get(binding.objective_id)
        if binding.target_entity_id is not None:
            return self._entities.get(binding.target_entity_id)
        return None

    def _area_center(self, effect: AreaEffect, binding: ActionBinding) -> Vector2:
        if effect.origin is AreaOrigin.ACTOR:
            return self._entity(binding.actor_id).position
        if binding.position is not None:
            return binding.position
        if binding.target_entity_id is not None:
            return self._entity(binding.target_entity_id).position
        raise SimulationConfigurationError("target-area effect is missing a bound origin")

    @staticmethod
    def _relation(actor: EntityState, target: EntityState) -> Relation:
        if actor.entity_id == target.entity_id:
            return Relation.SELF
        if actor.team_id is None or target.team_id is None:
            return Relation.NEUTRAL
        if actor.team_id == target.team_id:
            return Relation.ALLY
        return Relation.ENEMY

    @staticmethod
    def _normalized(vector: Vector2) -> Vector2:
        length = hypot(vector.x, vector.y)
        if length == 0:
            raise SimulationConfigurationError("movement direction must not be zero")
        return Vector2(vector.x / length, vector.y / length)

    def _entity(self, entity_id: str) -> EntityState:
        try:
            return self._entities[entity_id]
        except KeyError as exc:
            raise SimulationConfigurationError(f"unknown entity id: {entity_id}") from exc

    @staticmethod
    def _required_scalar(entity: EntityState, scalar_key: str) -> float:
        try:
            return entity.effective_scalar(scalar_key)
        except KeyError as exc:
            raise SimulationConfigurationError(
                f"entity {entity.entity_id} is missing required scalar {scalar_key}"
            ) from exc

    @staticmethod
    def _scalar_or_default(
        entity: EntityState,
        scalar_key: str,
        default: float,
    ) -> float:
        try:
            return entity.effective_scalar(scalar_key)
        except KeyError:
            return float(default)

    def _action_has_tag(self, action_key: str, tag: str) -> bool:
        try:
            return tag in self._catalog.get(action_key).tags
        except KeyError:
            return False
