"""Execution of the closed primitive effect set."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
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
    PeriodicPulse,
    RemoveEffect,
    ResistanceAdjustment,
    ResourceImmunity,
    RestoreResource,
    ScalarOperation,
    SubjectRef,
    TagOperation,
    TransferItem,
    TriangularAmount,
    UniformAmount,
    UniformIntegerAmount,
    WeightedAmount,
)
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.random_source import DeterministicRandom
from shadowbane_lab.sim.state import ActiveEffectState, EntityState
from shadowbane_lab.sim.timeline import ScheduledItem, ScheduledKind

EventFactory = Callable[..., Event]
ScheduleCallback = Callable[[ScheduledItem], None]
OrderCallback = Callable[[], int]
InterruptCallback = Callable[[str, str, int, list[Event]], None]


class EffectExecutor:
    """Applies primitive effects to one mutable reference-world state."""

    def __init__(
        self,
        entities: dict[str, EntityState],
        event_factory: EventFactory,
        schedule: ScheduleCallback,
        take_schedule_order: OrderCallback,
        random: DeterministicRandom,
        interrupt_actor: InterruptCallback,
    ) -> None:
        self._entities = entities
        self._event = event_factory
        self._schedule = schedule
        self._take_schedule_order = take_schedule_order
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
            self._resolve_direct(item, effect, due_time, eligible_alive, events)

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
        center = self._area_center(effect, item.binding)
        candidates = [
            entity
            for entity in self._entities.values()
            if entity.entity_id in eligible_alive
            and self._relation(actor, entity) in effect.allowed_relations
            and hypot(entity.position.x - center.x, entity.position.y - center.y)
            <= effect.radius
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
        attack_rating = self._required_scalar(actor, effect.attack_rating_key)
        defense_rating = self._required_scalar(target, effect.defense_rating_key)
        chance = (
            melee_hit_chance_percent(attack_rating, defense_rating)
            if effect.kind is AttackKind.BASIC
            else power_hit_chance_percent(attack_rating, defense_rating)
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
        if "combat.ignore_passive_defense" not in actor.effective_tags:
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
        for nested in effect.effects:
            if isinstance(nested, ChanceGate):
                self._resolve_chance(item, nested, due_time, eligible_alive, events)
            else:
                self._resolve_direct(item, nested, due_time, eligible_alive, events)

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
                self._resolve_direct(item, nested, due_time, eligible_alive, events)

    def _resolve_direct(
        self,
        item: ScheduledItem,
        effect: DirectEffectPrimitive,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list[Event],
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("resolution is missing its action binding")
        subject = self._subject_entity(effect, item.binding)
        if subject is not None and subject.entity_id not in eligible_alive:
            return
        if isinstance(effect, DealDamage):
            self._deal_damage(item, effect, subject, due_time, events)
        elif isinstance(effect, RestoreResource):
            self._restore_resource(item, effect, subject, due_time, events)
        elif isinstance(effect, ModifyScalar):
            self._modify_scalar(item, effect, subject, due_time, events)
        elif isinstance(effect, ModifyTag):
            self._modify_tag(item, effect, subject, due_time, events)
        elif isinstance(effect, ApplyEffect):
            self._apply_effect(item, effect, subject, due_time, events)
        elif isinstance(effect, RemoveEffect):
            self._remove_effect(item, effect, subject, due_time, events)
        elif isinstance(effect, MoveEntity):
            self._move_entity(item, effect, subject, due_time, events)
        elif isinstance(effect, TransferItem):
            self._transfer_item(item, effect, due_time, events)
        elif isinstance(effect, ModifyObjective):
            self._modify_objective(item, effect, subject, due_time, events)
        elif isinstance(effect, ChangeStance):
            self._change_stance(item, effect, subject, due_time, events)
        else:  # pragma: no cover - ChanceGate rejects types outside the closed union.
            raise SimulationConfigurationError(
                f"unsupported direct effect primitive: {type(effect).__name__}"
            )

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
        mitigated = amount
        resistance = 0.0
        armor_piercing = 0.0
        if effect.uses_resistance:
            actor = self._entity(item.actor_id)
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
            protection_applies = (
                f"protection.{effect.damage_type.value}" in subject.effective_tags
            )
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
                if isinstance(modifier, DamageBreakpoint)
                and damage_type in modifier.damage_types
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
            resistance = self._required_scalar(
                subject, f"resist.{effect.resistance_type.value}"
            )
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
                    *(('outcome.blocked_by_resource_immunity',) if restoration_blocked else ()),
                ),
            )
        )

    def _resolve_amount(
        self,
        amount: (
            float
            | UniformAmount
            | TriangularAmount
            | UniformIntegerAmount
            | WeightedAmount
        ),
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
                amount.minimum
                + self._random.randbelow(amount.maximum - amount.minimum + 1)
            )
        if isinstance(amount, WeightedAmount):
            selected = self._random.randbelow(amount.total_weight)
            cumulative = 0
            for value, weight in amount.outcomes:
                cumulative += weight
                if selected < cumulative:
                    return value
            raise SimulationConfigurationError(
                "weighted amount selection did not reach an outcome"
            )
        return amount

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
    ) -> None:
        if subject is None:
            raise SimulationConfigurationError("effect application requires an entity subject")
        if "control.stun" in effect.tags and "immunity.stun" in subject.effective_tags:
            events.append(
                self._event(
                    EventKind.EFFECT_BLOCKED,
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=item.actor_id,
                    target_entity_id=subject.entity_id,
                    action_key=item.action_key,
                    tags=(f"effect.{effect.effect_key}", "reason.immune"),
                )
            )
            return
        storage_key = effect.stacking_key or effect.effect_key
        existing = subject.effects.get(storage_key)
        if existing is not None:
            if not should_overwrite_effect(
                incoming_order=effect.stack_order,
                existing_order=existing.stack_order,
                incoming_trains=effect.trains,
                existing_trains=existing.trains,
                priority=effect.stack_priority,
                same_power=effect.effect_key == existing.effect_key,
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
                        tags=(f"effect.{effect.effect_key}", "reason.stack_priority"),
                    )
                )
                return
            events.append(
                self._effect_removed_event(subject, existing, due_time, item, "reason.replaced")
            )
        instance_id = f"effect-instance:{self._take_schedule_order():012d}"
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
                tags=(f"effect.{effect.effect_key}",),
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
            )
        )
        if "control.stun" in effect.tags:
            self._interrupt_actor(subject.entity_id, "stun", due_time, events)

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
        storage_keys = tuple(
            storage_key
            for storage_key, active in subject.effects.items()
            if (effect.effect_key is not None and active.effect_key == effect.effect_key)
            or (effect.matching_tag is not None and effect.matching_tag in active.tags)
        )
        for storage_key in sorted(storage_keys):
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
