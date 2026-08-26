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
    Vector2,
    validate_exchange,
)
from shadowbane_lab.sim.actions import (
    ActionCatalog,
    ActionPhase,
    ActionSpec,
    DeliveryKind,
)
from shadowbane_lab.sim.affordances import AffordanceBuilder
from shadowbane_lab.sim.clock import SimulationClock
from shadowbane_lab.sim.effects import EffectExecutor
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.random_source import DeterministicRandom
from shadowbane_lab.sim.state import EntityState
from shadowbane_lab.sim.timeline import (
    AgentExchange,
    EnvironmentSnapshot,
    ScheduledItem,
    ScheduledKind,
)

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
        actor.cooldowns[action.action_key] = self.now_ms + action.cooldown_ms
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
        self._schedule_action_phases(actor, decision, action)
        self._schedule(
            ScheduledItem(
                due_time_ms=self.now_ms + total_phase_ms,
                order=self._take_schedule_order(),
                kind=ScheduledKind.COMPLETION,
                actor_id=actor.entity_id,
                correlation_id=decision.correlation_id,
                action_key=action.action_key,
            )
        )

    def _schedule_action_phases(
        self,
        actor: EntityState,
        decision: DecisionMessage,
        action: ActionSpec,
    ) -> None:
        phase_end_ms = self.now_ms
        for phase in action.phases:
            phase_end_ms += phase.duration_ms
            if not phase.effects:
                continue
            self._schedule(
                ScheduledItem(
                    due_time_ms=(
                        phase_end_ms + self._delivery_delay(actor, decision.binding, phase)
                    ),
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.RESOLUTION,
                    actor_id=actor.entity_id,
                    correlation_id=decision.correlation_id,
                    action_key=action.action_key,
                    binding=decision.binding,
                    phase_duration_ms=phase.duration_ms,
                    effects=phase.effects,
                )
            )

    def _process_due(
        self,
        until_ms: int,
        events: list[Event],
        life_terminated: set[str],
    ) -> None:
        while True:
            due_times = [
                item.due_time_ms for item in self._scheduled if item.due_time_ms <= until_ms
            ]
            if not due_times:
                return
            due_time = min(due_times)
            group = sorted(
                (item for item in self._scheduled if item.due_time_ms == due_time),
                key=self._scheduled_key,
            )
            self._scheduled = [item for item in self._scheduled if item.due_time_ms != due_time]
            eligible_alive = frozenset(
                entity.entity_id for entity in self._entities.values() if entity.alive
            )
            for item in group:
                if item.kind is ScheduledKind.RESOLUTION:
                    self._effect_executor.resolve(item, due_time, eligible_alive, events)
                elif item.kind is ScheduledKind.COMPLETION:
                    events.append(
                        self._event(
                            EventKind.ACTION_COMPLETED,
                            due_time,
                            correlation_id=item.correlation_id,
                            source_entity_id=item.actor_id,
                            action_key=item.action_key,
                        )
                    )
                else:
                    self._effect_executor.expire_effect(item, due_time, events)
            self._effect_executor.resolve_deaths(due_time, events, life_terminated)

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
            self._random,
        )

    def _schedule(self, item: ScheduledItem) -> None:
        self._scheduled.append(item)

    def _take_schedule_order(self) -> int:
        order = self._next_schedule_order
        self._next_schedule_order += 1
        return order

    @staticmethod
    def _scheduled_key(item: ScheduledItem) -> tuple[int, int]:
        return item.due_time_ms, item.order

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
