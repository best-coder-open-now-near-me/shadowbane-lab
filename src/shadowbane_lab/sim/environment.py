"""Readable deterministic simulator used as the correctness oracle."""

from __future__ import annotations

from math import ceil, hypot

from shadowbane_lab.protocol import (
    ActionBinding,
    DecisionMessage,
    EntityKind,
    Event,
    EventBatchMessage,
    EventKind,
    NamedScalar,
    ProtocolMismatchError,
    TargetKind,
    Vector2,
    validate_exchange,
)
from shadowbane_lab.sim.actions import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    DeliveryKind,
    EffectPrimitive,
    PeriodicPulse,
    TriggerConsumption,
    TriggerMoment,
)
from shadowbane_lab.sim.affordances import AffordanceBuilder
from shadowbane_lab.sim.clock import SimulationClock
from shadowbane_lab.sim.effects import EffectExecutor
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.lifecycle import (
    ActionExecutionState,
    ActionExecutionStatus,
    ContinuationPolicy,
    PayloadReleaseStatus,
)
from shadowbane_lab.sim.random_source import DeterministicRandom
from shadowbane_lab.sim.state import EntityState
from shadowbane_lab.sim.timeline import (
    AgentExchange,
    EnvironmentSnapshot,
    ScheduledItem,
    ScheduledKind,
)
from shadowbane_lab.sim.timing import effective_action_cooldown_ms

_DEFAULT_DIRECTIONS = (
    Vector2(-1.0, -1.0),
    Vector2(-1.0, 0.0),
    Vector2(-1.0, 1.0),
    Vector2(0.0, -1.0),
    Vector2(0.0, 1.0),
    Vector2(1.0, -1.0),
    Vector2(1.0, 0.0),
    Vector2(1.0, 1.0),
)


class ReferenceEnvironment:
    """Single-world scalar implementation with a deterministic event timeline."""

    def __init__(
        self,
        catalog: ActionCatalog,
        entities: tuple[EntityState, ...],
        *,
        seed: int,
        tick_duration_ms: int = 200,
        direction_candidates: tuple[Vector2, ...] = _DEFAULT_DIRECTIONS,
        position_candidates: tuple[Vector2, ...] = (),
        terminate_on_last_team: bool = False,
    ) -> None:
        if not entities:
            raise SimulationConfigurationError("an environment requires at least one entity")
        entity_ids = tuple(entity.entity_id for entity in entities)
        if len(entity_ids) != len(set(entity_ids)):
            raise SimulationConfigurationError("entity ids must be unique")
        self._catalog = catalog
        self._validate_entity_actions(entities)
        self._entities = {entity.entity_id: entity.clone() for entity in entities}
        self._clock = SimulationClock(tick_duration_ms)
        self._random = DeterministicRandom(seed)
        self._scheduled: list[ScheduledItem] = []
        self._executions: dict[tuple[str, str], ActionExecutionState] = {}
        self._cancelled_tokens: set[str] = set()
        self._next_schedule_order = 0
        self._next_event_number = 0
        self._direction_candidates = self._normalize_directions(direction_candidates)
        self._position_candidates = tuple(position_candidates)
        if any(not isinstance(point, Vector2) for point in self._position_candidates):
            raise SimulationConfigurationError("position candidates must be Vector2 values")
        if not isinstance(terminate_on_last_team, bool):
            raise SimulationConfigurationError("terminate_on_last_team must be a boolean")
        self._terminate_on_last_team = terminate_on_last_team
        self._initial_competing_teams = frozenset(
            entity.team_id
            for entity in entities
            if entity.kind is EntityKind.ACTOR and entity.team_id is not None
        )
        self._effect_executor = self._create_effect_executor()
        self._schedule_initial_effects()
        self._initial_snapshot = self.snapshot()

    @property
    def tick(self) -> int:
        return self._clock.tick

    @property
    def now_ms(self) -> int:
        return self._clock.now_ms

    @property
    def entities(self) -> tuple[EntityState, ...]:
        return tuple(self._entities[key].clone() for key in sorted(self._entities))

    def entity(self, entity_id: str) -> EntityState:
        return self._entity(entity_id).clone()

    @property
    def executions(self) -> tuple[ActionExecutionState, ...]:
        return tuple(
            ActionExecutionState.from_snapshot(execution.snapshot())
            for _, execution in sorted(self._executions.items())
        )

    def execution(
        self,
        correlation_id: str,
        *,
        actor_id: str | None = None,
    ) -> ActionExecutionState:
        matches = [
            execution
            for execution in self._executions.values()
            if execution.correlation_id == correlation_id
            and (actor_id is None or execution.actor_entity_id == actor_id)
        ]
        if len(matches) != 1:
            raise KeyError(f"expected one execution for {correlation_id}, found {len(matches)}")
        return ActionExecutionState.from_snapshot(matches[0].snapshot())

    def exchange(self, agent_id: str) -> AgentExchange:
        return AffordanceBuilder(
            self._catalog,
            self._entities,
            tick=self.tick,
            now_ms=self.now_ms,
            direction_candidates=self._direction_candidates,
            position_candidates=self._position_candidates,
        ).exchange(agent_id)

    def step(
        self,
        decisions: tuple[DecisionMessage, ...] = (),
        *,
        truncated: bool = False,
    ) -> EventBatchMessage:
        if not isinstance(truncated, bool):
            raise ValueError("truncated must be a boolean")
        events: list[Event] = []
        life_terminated: set[str] = set()
        accepted: list[tuple[DecisionMessage, ActionSpec]] = []
        seen_agents: set[str] = set()

        for decision in sorted(decisions, key=lambda item: (item.agent_id, item.correlation_id)):
            if decision.agent_id in seen_agents:
                events.append(self._rejection_event(decision, "reason.multiple_decisions_for_tick"))
                continue
            seen_agents.add(decision.agent_id)
            try:
                exchange = self.exchange(decision.agent_id)
                validate_exchange(exchange.observation, exchange.affordances, decision)
                action = self._catalog.get(decision.action_key)
            except (KeyError, ProtocolMismatchError, ValueError) as exc:
                events.append(self._rejection_event(decision, f"reason.{self._reason_tag(exc)}"))
                continue
            accepted.append((decision, action))

        for decision, action in accepted:
            self._start_action(decision, action, events)

        self._process_due(self.now_ms, events, life_terminated)
        self._clock.advance()
        self._process_due(self.now_ms, events, life_terminated)

        return EventBatchMessage(
            message_id=f"message:events:{self.tick}:{self._next_event_number}",
            tick=self.tick,
            sim_time_ms=self.now_ms,
            events=tuple(events),
            life_terminated=tuple(sorted(life_terminated)),
            world_terminated=self._world_terminated(),
            truncated=truncated,
        )

    def snapshot(self) -> EnvironmentSnapshot:
        return EnvironmentSnapshot(
            clock=self._clock.snapshot(),
            random=self._random.snapshot(),
            entities=tuple(
                self._entities[entity_id].snapshot() for entity_id in sorted(self._entities)
            ),
            scheduled=tuple(sorted(self._scheduled, key=self._scheduled_key)),
            next_schedule_order=self._next_schedule_order,
            next_event_number=self._next_event_number,
            executions=tuple(
                execution.snapshot() for _, execution in sorted(self._executions.items())
            ),
            cancelled_tokens=tuple(sorted(self._cancelled_tokens)),
        )

    def restore(self, snapshot: EnvironmentSnapshot) -> None:
        self._clock.restore(snapshot.clock)
        self._random.restore(snapshot.random)
        entities = tuple(EntityState.from_snapshot(entity) for entity in snapshot.entities)
        entity_ids = tuple(entity.entity_id for entity in entities)
        if len(entity_ids) != len(set(entity_ids)):
            raise SimulationConfigurationError("snapshot entity ids must be unique")
        self._validate_entity_actions(entities)
        self._entities = {entity.entity_id: entity for entity in entities}
        self._scheduled = list(snapshot.scheduled)
        self._executions = {
            (
                execution.actor_entity_id,
                execution.correlation_id,
            ): ActionExecutionState.from_snapshot(execution)
            for execution in snapshot.executions
        }
        self._cancelled_tokens = set(snapshot.cancelled_tokens)
        self._next_schedule_order = snapshot.next_schedule_order
        self._next_event_number = snapshot.next_event_number
        self._effect_executor = self._create_effect_executor()

    def reset(self) -> None:
        self.restore(self._initial_snapshot)

    def _start_action(
        self,
        decision: DecisionMessage,
        action: ActionSpec,
        events: list[Event],
    ) -> None:
        actor = self._entities[decision.agent_id]
        execution_key = (actor.entity_id, decision.correlation_id)
        if execution_key in self._executions:
            raise SimulationConfigurationError(
                f"duplicate action correlation for {actor.entity_id}: {decision.correlation_id}"
            )
        for cost in action.costs:
            before = actor.scalars.get(cost.resource_key, 0.0)
            actor.scalars[cost.resource_key] = before - cost.amount
            events.append(
                self._event(
                    "resource_spent",
                    self.now_ms,
                    correlation_id=decision.correlation_id,
                    source_entity_id=actor.entity_id,
                    action_key=action.action_key,
                    scalars=(NamedScalar(cost.resource_key, cost.amount),),
                )
            )
        actor.cooldowns[action.action_key] = self.now_ms + effective_action_cooldown_ms(
            actor, action
        )
        total_phase_ms = sum(phase.duration_ms for phase in action.phases)
        actor.busy_until_ms = max(actor.busy_until_ms, self.now_ms + total_phase_ms)
        events.append(
            self._event(
                EventKind.ACTION_STARTED,
                self.now_ms,
                correlation_id=decision.correlation_id,
                source_entity_id=actor.entity_id,
                target_entity_id=decision.binding.target_entity_id,
                action_key=action.action_key,
            )
        )
        triggered_effects = self._consume_action_start_triggers(
            actor,
            decision,
            action,
            events,
        )
        target_life_id = None
        if decision.binding.target_entity_id is not None:
            target = self._entities.get(decision.binding.target_entity_id)
            if target is not None:
                target_life_id = target.life_id
        first_phase = action.phases[0]
        execution = ActionExecutionState(
            correlation_id=decision.correlation_id,
            actor_entity_id=actor.entity_id,
            actor_life_id=actor.life_id,
            target_life_id=target_life_id,
            action_key=action.action_key,
            binding=decision.binding,
            phase_index=0,
            phase_kind=first_phase.kind,
            phase_started_at_ms=self.now_ms,
            phase_ends_at_ms=self.now_ms,
            cancel_token=f"cancel:{actor.entity_id}:{decision.correlation_id}",
            cancel_on_damage=action.cancel_on_damage,
            cancel_on_stun=action.cancel_on_stun,
            pending_triggered_effects=triggered_effects,
        )
        self._executions[execution_key] = execution
        self._schedule_action_phase(execution, action, 0, self.now_ms)

    def _schedule_action_phase(
        self,
        execution: ActionExecutionState,
        action: ActionSpec,
        phase_index: int,
        phase_started_at_ms: int,
    ) -> None:
        phase = action.phases[phase_index]
        phase_end_ms = phase_started_at_ms + phase.duration_ms
        weapon_in_phase = (
            action.weapon_attack is not None and action.weapon_attack.phase_index == phase_index
        )
        native_payload = bool(phase.effects) or weapon_in_phase
        trigger_payload = (
            bool(execution.pending_triggered_effects)
            and not (execution.trigger_payload_scheduled)
            and (native_payload or phase_index == len(action.phases) - 1)
        )
        has_payload = native_payload or trigger_payload

        execution.phase_index = phase_index
        execution.phase_kind = phase.kind
        execution.phase_started_at_ms = phase_started_at_ms
        execution.phase_ends_at_ms = phase_end_ms
        execution.phase_interruptible = phase.interruptible
        execution.movement_allowed = phase.movement_allowed
        execution.payload_release_status = (
            PayloadReleaseStatus.PENDING if has_payload else PayloadReleaseStatus.NOT_APPLICABLE
        )
        execution.status = (
            ActionExecutionStatus.RECOVERING
            if phase.kind.value == "recovery"
            else ActionExecutionStatus.ACTIVE
        )

        actor = self._entity(execution.actor_entity_id)
        continuation = (
            ContinuationPolicy.DETACH_ON_RELEASE
            if phase.delivery.kind is DeliveryKind.PROJECTILE
            else ContinuationPolicy.SOURCE_BOUND
        )
        common = {
            "actor_id": actor.entity_id,
            "actor_life_id": execution.actor_life_id,
            "target_life_id": execution.target_life_id,
            "correlation_id": execution.correlation_id,
            "action_key": action.action_key,
            "phase_index": phase_index,
            "cancel_token": execution.cancel_token,
        }
        if has_payload:
            self._schedule(
                ScheduledItem(
                    due_time_ms=phase_end_ms,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.PHASE_RELEASE,
                    continuation_policy=ContinuationPolicy.SOURCE_BOUND,
                    **common,
                )
            )
        due_time_ms = phase_end_ms + self._delivery_delay(
            actor,
            execution.binding,
            phase,
        )
        if weapon_in_phase:
            self._schedule(
                ScheduledItem(
                    due_time_ms=due_time_ms,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.WEAPON_ATTACK,
                    binding=execution.binding,
                    phase_duration_ms=phase.duration_ms,
                    weapon_attack=action.weapon_attack,
                    interruptible=phase.interruptible,
                    cancel_on_damage=action.cancel_on_damage,
                    cancel_on_stun=action.cancel_on_stun,
                    continuation_policy=continuation,
                    **common,
                )
            )
        if phase.effects:
            self._schedule(
                ScheduledItem(
                    due_time_ms=due_time_ms,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.RESOLUTION,
                    binding=execution.binding,
                    phase_duration_ms=phase.duration_ms,
                    effects=phase.effects,
                    interruptible=phase.interruptible,
                    cancel_on_damage=action.cancel_on_damage,
                    cancel_on_stun=action.cancel_on_stun,
                    continuation_policy=continuation,
                    **common,
                )
            )
        if trigger_payload:
            self._schedule(
                ScheduledItem(
                    due_time_ms=due_time_ms,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.RESOLUTION,
                    binding=execution.binding,
                    phase_duration_ms=phase.duration_ms,
                    effects=execution.pending_triggered_effects,
                    interruptible=phase.interruptible,
                    cancel_on_damage=action.cancel_on_damage,
                    cancel_on_stun=action.cancel_on_stun,
                    continuation_policy=continuation,
                    **common,
                )
            )
            execution.trigger_payload_scheduled = True

        if phase_index + 1 < len(action.phases):
            self._schedule(
                ScheduledItem(
                    due_time_ms=phase_end_ms,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.PHASE_TRANSITION,
                    continuation_policy=ContinuationPolicy.SOURCE_BOUND,
                    **common,
                )
            )
        else:
            self._schedule(
                ScheduledItem(
                    due_time_ms=phase_end_ms,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.COMPLETION,
                    continuation_policy=ContinuationPolicy.SOURCE_BOUND,
                    **common,
                )
            )

    def _consume_action_start_triggers(
        self,
        actor: EntityState,
        decision: DecisionMessage,
        action: ActionSpec,
        events: list[Event],
    ) -> tuple[EffectPrimitive, ...]:
        action_tags = frozenset(action.tags)
        payload: list[EffectPrimitive] = []
        for storage_key in sorted(tuple(actor.effects)):
            active = actor.effects.get(storage_key)
            if active is None:
                continue
            trigger = self._catalog.trigger_for_effect(active.effect_key)
            if (
                trigger is None
                or trigger.fire_on is not TriggerMoment.ACTION_START
                or not trigger.matches(action.action_key, action_tags)
            ):
                continue
            if trigger.chance >= 1.0:
                roll, fired = 0.0, True
            elif trigger.chance <= 0.0:
                roll, fired = 1.0, False
            else:
                roll = self._random.random()
                fired = roll < trigger.chance
            events.append(
                self._event(
                    EventKind.TRIGGER_CHECKED,
                    self.now_ms,
                    correlation_id=decision.correlation_id,
                    source_entity_id=actor.entity_id,
                    target_entity_id=decision.binding.target_entity_id,
                    action_key=action.action_key,
                    scalars=(
                        NamedScalar("chance", trigger.chance),
                        NamedScalar("roll", roll),
                    ),
                    tags=(
                        f"trigger.{trigger.trigger_key}",
                        "moment.action_start",
                        "result.fired" if fired else "result.not_fired",
                    ),
                )
            )
            if fired:
                events.append(
                    self._event(
                        EventKind.TRIGGER_FIRED,
                        self.now_ms,
                        correlation_id=decision.correlation_id,
                        source_entity_id=actor.entity_id,
                        target_entity_id=decision.binding.target_entity_id,
                        action_key=action.action_key,
                        tags=tuple(
                            dict.fromkeys(
                                (
                                    f"trigger.{trigger.trigger_key}",
                                    "moment.action_start",
                                    *trigger.tags,
                                )
                            )
                        ),
                    )
                )
                payload.extend(trigger.payload)
            if trigger.consume_on is TriggerConsumption.ACTION_START:
                actor.effects.pop(storage_key)
                events.append(
                    self._event(
                        EventKind.EFFECT_REMOVED,
                        self.now_ms,
                        correlation_id=decision.correlation_id,
                        source_entity_id=active.source_entity_id,
                        target_entity_id=actor.entity_id,
                        action_key=action.action_key,
                        tags=(
                            f"effect.{active.effect_key}",
                            "reason.trigger_consumed",
                        ),
                    )
                )
        return tuple(payload)

    def _process_due(
        self,
        until_ms: int,
        events: list[Event],
        life_terminated: set[str],
    ) -> None:
        while True:
            candidates = [item for item in self._scheduled if item.due_time_ms <= until_ms]
            if not candidates:
                return
            item = min(candidates, key=self._scheduled_key)
            self._scheduled.remove(item)
            if not self._scheduled_item_is_valid(item):
                continue
            due_time = item.due_time_ms
            alive_before = {entity.entity_id for entity in self._entities.values() if entity.alive}
            eligible_alive = frozenset(alive_before)
            if item.kind is ScheduledKind.PHASE_RELEASE:
                self._release_action_phase(item)
            elif item.kind is ScheduledKind.PHASE_TRANSITION:
                self._transition_action_phase(item)
            elif item.kind is ScheduledKind.RESOLUTION:
                self._effect_executor.resolve(item, due_time, eligible_alive, events)
            elif item.kind is ScheduledKind.WEAPON_ATTACK:
                self._effect_executor.resolve_weapon_attack(item, due_time, eligible_alive, events)
            elif item.kind is ScheduledKind.COMPLETION:
                self._complete_action(item, events)
            elif item.kind is ScheduledKind.EFFECT_PULSE:
                self._effect_executor.resolve_effect_pulse(
                    item,
                    due_time,
                    eligible_alive,
                    events,
                )
            elif item.kind is ScheduledKind.EFFECT_EXPIRY:
                self._effect_executor.expire_effect(item, due_time, events)
            else:  # pragma: no cover - ScheduledKind is closed.
                raise SimulationConfigurationError(f"unsupported scheduled kind: {item.kind}")
            self._effect_executor.resolve_deaths(
                due_time,
                events,
                life_terminated,
            )
            newly_dead = tuple(
                sorted(
                    entity_id for entity_id in alive_before if not self._entities[entity_id].alive
                )
            )
            for entity_id in newly_dead:
                self._cleanup_dead_actor(entity_id, due_time, events)

    def _scheduled_item_is_valid(self, item: ScheduledItem) -> bool:
        execution = self._executions.get((item.actor_id, item.correlation_id))
        detached = (
            item.continuation_policy is ContinuationPolicy.DETACH_ON_RELEASE
            and execution is not None
            and item.phase_index is not None
            and item.phase_index in execution.released_phase_indexes
        )
        if item.cancel_token in self._cancelled_tokens and not detached:
            return False
        if item.target_life_id is not None and item.binding is not None:
            target_id = item.binding.target_entity_id
            target = self._entities.get(target_id) if target_id is not None else None
            if target is None or target.life_id != item.target_life_id:
                return False
        if item.continuation_policy is ContinuationPolicy.TARGET_LIFE_BOUND:
            if item.binding is None or item.binding.target_entity_id is None:
                return False
            target = self._entities.get(item.binding.target_entity_id)
            if target is None or not target.alive:
                return False
        if item.actor_life_id is None or detached:
            return True
        if item.continuation_policy not in {
            ContinuationPolicy.SOURCE_BOUND,
            ContinuationPolicy.DETACH_ON_RELEASE,
        }:
            return True
        actor = self._entities.get(item.actor_id)
        return actor is not None and actor.alive and actor.life_id == item.actor_life_id

    def _release_action_phase(self, item: ScheduledItem) -> None:
        execution = self._executions.get((item.actor_id, item.correlation_id))
        if execution is None or execution.is_terminal or item.phase_index is None:
            return
        execution.released_phase_indexes.add(item.phase_index)
        if execution.phase_index == item.phase_index:
            execution.payload_release_status = PayloadReleaseStatus.RELEASED
            if execution.status is ActionExecutionStatus.ACTIVE:
                execution.status = ActionExecutionStatus.RELEASED

    def _transition_action_phase(self, item: ScheduledItem) -> None:
        execution = self._executions.get((item.actor_id, item.correlation_id))
        if execution is None or execution.is_terminal or item.phase_index is None:
            return
        if execution.phase_index != item.phase_index:
            return
        action = self._catalog.get(execution.action_key)
        next_phase_index = item.phase_index + 1
        if next_phase_index >= len(action.phases):
            raise SimulationConfigurationError("phase transition exceeds action phases")
        self._schedule_action_phase(
            execution,
            action,
            next_phase_index,
            item.due_time_ms,
        )

    def _complete_action(self, item: ScheduledItem, events: list[Event]) -> None:
        execution = self._executions.get((item.actor_id, item.correlation_id))
        if execution is not None:
            if execution.status is ActionExecutionStatus.INTERRUPTED:
                return
            if execution.status is ActionExecutionStatus.COMPLETED:
                return
            execution.status = ActionExecutionStatus.COMPLETED
            actor = self._entities.get(item.actor_id)
            if actor is not None and actor.life_id == execution.actor_life_id:
                actor.busy_until_ms = min(actor.busy_until_ms, item.due_time_ms)
        events.append(
            self._event(
                EventKind.ACTION_COMPLETED,
                item.due_time_ms,
                correlation_id=item.correlation_id,
                source_entity_id=item.actor_id,
                action_key=item.action_key,
            )
        )

    def _cleanup_dead_actor(
        self,
        actor_id: str,
        due_time: int,
        events: list[Event],
    ) -> None:
        actor = self._entity(actor_id)
        actor.velocity = Vector2(0.0, 0.0)
        actor.busy_until_ms = min(actor.busy_until_ms, due_time)
        for execution in sorted(
            self._executions.values(),
            key=lambda value: (value.actor_entity_id, value.correlation_id),
        ):
            if (
                execution.actor_entity_id != actor_id
                or execution.actor_life_id != actor.life_id
                or execution.is_terminal
            ):
                continue
            execution.status = ActionExecutionStatus.INTERRUPTED
            self._cancelled_tokens.add(execution.cancel_token)
            events.append(
                self._event(
                    EventKind.ACTION_INTERRUPTED,
                    due_time,
                    correlation_id=execution.correlation_id,
                    source_entity_id=actor_id,
                    action_key=execution.action_key,
                    tags=("reason.death",),
                )
            )

    def _delivery_delay(
        self,
        actor: EntityState,
        binding: ActionBinding,
        phase: ActionPhase,
    ) -> int:
        if phase.delivery.kind is DeliveryKind.IMMEDIATE:
            return 0
        if binding.target_entity_id is None:
            raise SimulationConfigurationError("projectile delivery requires an entity target")
        target = self._entity(binding.target_entity_id)
        speed = phase.delivery.projectile_speed_units_per_second
        if speed is None:
            raise SimulationConfigurationError("projectile delivery requires a speed")
        return ceil(self._distance(actor.position, target.position) / speed * 1_000.0)

    def _world_terminated(self) -> bool:
        if not self._terminate_on_last_team or len(self._initial_competing_teams) < 2:
            return False
        living_teams = {
            entity.team_id
            for entity in self._entities.values()
            if entity.kind is EntityKind.ACTOR and entity.alive and entity.team_id is not None
        }
        return len(living_teams) <= 1

    def _validate_entity_actions(self, entities: tuple[EntityState, ...]) -> None:
        for entity in entities:
            for action_key in entity.action_keys:
                try:
                    self._catalog.get(action_key)
                except KeyError as exc:
                    raise SimulationConfigurationError(
                        f"entity {entity.entity_id} references {action_key}"
                    ) from exc

    def _create_effect_executor(self) -> EffectExecutor:
        return EffectExecutor(
            self._entities,
            self._event,
            self._schedule,
            self._take_schedule_order,
            self._catalog,
            self._random,
            self._interrupt_actor,
        )

    def _schedule_initial_effects(self) -> None:
        """Seed expiry and pulse work for effects present at combat start."""

        persistent_expiry = (1 << 63) - 1
        for entity_id in sorted(self._entities):
            entity = self._entities[entity_id]
            for storage_key in sorted(entity.effects):
                active = entity.effects[storage_key]
                if active.instance_id is None:
                    active.instance_id = (
                        f"initial-effect-instance:{entity_id}:{self._take_schedule_order():012d}"
                    )
                correlation_id = f"initial-effect:{entity_id}:{storage_key}"
                action_key = f"initial.{active.effect_key}"
                binding = ActionBinding(
                    actor_id=active.source_entity_id,
                    target_kind=TargetKind.ENTITY,
                    target_entity_id=entity_id,
                )
                for modifier in active.modifiers:
                    if not isinstance(modifier, PeriodicPulse):
                        continue
                    for pulse_index in range(1, modifier.tick_count + 1):
                        due_time_ms = pulse_index * modifier.interval_ms
                        if due_time_ms > active.expires_at_ms:
                            break
                        self._schedule(
                            ScheduledItem(
                                due_time_ms=due_time_ms,
                                order=self._take_schedule_order(),
                                kind=ScheduledKind.EFFECT_PULSE,
                                actor_id=active.source_entity_id,
                                correlation_id=correlation_id,
                                action_key=action_key,
                                binding=binding,
                                effects=modifier.effects,
                                effect_entity_id=entity_id,
                                effect_storage_key=storage_key,
                                expected_effect_key=active.effect_key,
                                expected_effect_instance_id=active.instance_id,
                                periodic_key=modifier.periodic_key,
                                pulse_index=pulse_index,
                            )
                        )
                if active.expires_at_ms == persistent_expiry:
                    continue
                self._schedule(
                    ScheduledItem(
                        due_time_ms=active.expires_at_ms,
                        order=self._take_schedule_order(),
                        kind=ScheduledKind.EFFECT_EXPIRY,
                        actor_id=active.source_entity_id,
                        correlation_id=correlation_id,
                        action_key=action_key,
                        effect_entity_id=entity_id,
                        effect_storage_key=storage_key,
                        expected_effect_key=active.effect_key,
                        expected_effect_instance_id=active.instance_id,
                    )
                )

    def _interrupt_actor(
        self,
        actor_id: str,
        trigger: str,
        due_time: int,
        events: list[Event],
    ) -> None:
        if trigger not in {"damage", "stun"}:
            raise SimulationConfigurationError(f"unsupported interruption trigger: {trigger}")
        actor = self._entity(actor_id)
        for execution in sorted(
            self._executions.values(),
            key=lambda value: (value.actor_entity_id, value.correlation_id),
        ):
            if execution.actor_entity_id != actor_id or execution.is_terminal:
                continue
            if execution.actor_life_id != actor.life_id:
                continue
            if execution.status not in {
                ActionExecutionStatus.STARTED,
                ActionExecutionStatus.ACTIVE,
            }:
                continue
            if not execution.phase_interruptible:
                continue
            if trigger == "damage" and not execution.cancel_on_damage:
                continue
            if trigger == "stun" and not execution.cancel_on_stun:
                continue
            execution.status = ActionExecutionStatus.INTERRUPTED
            self._cancelled_tokens.add(execution.cancel_token)
            actor.busy_until_ms = min(actor.busy_until_ms, due_time)
            events.append(
                self._event(
                    EventKind.ACTION_INTERRUPTED,
                    due_time,
                    correlation_id=execution.correlation_id,
                    source_entity_id=actor_id,
                    action_key=execution.action_key,
                    tags=(f"reason.{trigger}",),
                )
            )

    def _schedule(self, item: ScheduledItem) -> None:
        self._scheduled.append(item)

    def _take_schedule_order(self) -> int:
        order = self._next_schedule_order
        self._next_schedule_order += 1
        return order

    @staticmethod
    def _scheduled_key(item: ScheduledItem) -> tuple[int, int, int]:
        return item.due_time_ms, item.semantic_priority, item.order

    def _event(
        self,
        kind: str,
        sim_time_ms: int,
        *,
        correlation_id: str | None = None,
        source_entity_id: str | None = None,
        target_entity_id: str | None = None,
        action_key: str | None = None,
        scalars: tuple[NamedScalar, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> Event:
        number = self._next_event_number
        self._next_event_number += 1
        return Event(
            event_id=f"event:{number:012d}",
            kind=str(kind),
            tick=sim_time_ms // self._clock.tick_duration_ms,
            sim_time_ms=sim_time_ms,
            correlation_id=correlation_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            action_key=action_key,
            scalars=scalars,
            tags=tags,
        )

    def _rejection_event(self, decision: DecisionMessage, reason: str) -> Event:
        return self._event(
            EventKind.ACTION_REJECTED,
            self.now_ms,
            correlation_id=decision.correlation_id,
            source_entity_id=decision.agent_id,
            action_key=decision.action_key,
            tags=(reason,),
        )

    @staticmethod
    def _normalize_directions(directions: tuple[Vector2, ...]) -> tuple[Vector2, ...]:
        if not directions:
            raise SimulationConfigurationError("at least one direction candidate is required")
        normalized = tuple(ReferenceEnvironment._normalized(direction) for direction in directions)
        if len(normalized) != len(set(normalized)):
            raise SimulationConfigurationError("direction candidates must be unique")
        return normalized

    @staticmethod
    def _normalized(vector: Vector2) -> Vector2:
        if not isinstance(vector, Vector2):
            raise SimulationConfigurationError("direction candidates must be Vector2 values")
        length = hypot(vector.x, vector.y)
        if length == 0:
            raise SimulationConfigurationError("direction vectors must not be zero")
        return Vector2(vector.x / length, vector.y / length)

    @staticmethod
    def _distance(left: Vector2, right: Vector2) -> float:
        return hypot(left.x - right.x, left.y - right.y)

    @staticmethod
    def _reason_tag(error: Exception) -> str:
        text = str(error).lower()
        cleaned = "".join(character if character.isalnum() else "_" for character in text)
        return cleaned.strip("_")[:80] or "invalid_decision"

    def _entity(self, entity_id: str) -> EntityState:
        try:
            return self._entities[entity_id]
        except KeyError as exc:
            raise KeyError(f"unknown entity id: {entity_id}") from exc
