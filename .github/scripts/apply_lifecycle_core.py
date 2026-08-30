from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    target.write_text(
        text[:start_index] + replacement + text[end_index:],
        encoding="utf-8",
    )


Path("src/shadowbane_lab/sim/lifecycle.py").write_text(
    dedent(
        '''\
        """Authoritative action execution and scheduled-work lifecycle state."""

        from __future__ import annotations

        from dataclasses import dataclass, field
        from enum import StrEnum

        from shadowbane_lab.protocol import ActionBinding
        from shadowbane_lab.sim.actions import EffectPrimitive, PhaseKind


        def _identifier(value: str, field_name: str) -> None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")


        def _non_negative_integer(value: int, field_name: str) -> None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


        class ActionExecutionStatus(StrEnum):
            STARTED = "started"
            ACTIVE = "active"
            RELEASED = "released"
            RECOVERING = "recovering"
            COMPLETED = "completed"
            INTERRUPTED = "interrupted"


        class PayloadReleaseStatus(StrEnum):
            NOT_APPLICABLE = "not_applicable"
            PENDING = "pending"
            RELEASED = "released"


        class ContinuationPolicy(StrEnum):
            """What owns scheduled work after its source state changes."""

            SOURCE_BOUND = "source_bound"
            DETACH_ON_RELEASE = "detach_on_release"
            EFFECT_INSTANCE_BOUND = "effect_instance_bound"
            TARGET_LIFE_BOUND = "target_life_bound"
            WORLD_BOUND = "world_bound"


        @dataclass(frozen=True, slots=True)
        class ActionExecutionSnapshot:
            correlation_id: str
            actor_entity_id: str
            actor_life_id: str
            target_life_id: str | None
            action_key: str
            binding: ActionBinding
            phase_index: int
            phase_kind: PhaseKind
            phase_started_at_ms: int
            phase_ends_at_ms: int
            status: ActionExecutionStatus
            phase_interruptible: bool
            movement_allowed: bool
            payload_release_status: PayloadReleaseStatus
            released_phase_indexes: tuple[int, ...]
            cancel_token: str
            cancel_on_damage: bool
            cancel_on_stun: bool
            pending_triggered_effects: tuple[EffectPrimitive, ...]
            trigger_payload_scheduled: bool


        @dataclass(slots=True)
        class ActionExecutionState:
            correlation_id: str
            actor_entity_id: str
            actor_life_id: str
            target_life_id: str | None
            action_key: str
            binding: ActionBinding
            phase_index: int
            phase_kind: PhaseKind
            phase_started_at_ms: int
            phase_ends_at_ms: int
            status: ActionExecutionStatus = ActionExecutionStatus.STARTED
            phase_interruptible: bool = False
            movement_allowed: bool = True
            payload_release_status: PayloadReleaseStatus = PayloadReleaseStatus.NOT_APPLICABLE
            released_phase_indexes: set[int] = field(default_factory=set)
            cancel_token: str = ""
            cancel_on_damage: bool = False
            cancel_on_stun: bool = False
            pending_triggered_effects: tuple[EffectPrimitive, ...] = ()
            trigger_payload_scheduled: bool = False

            def __post_init__(self) -> None:
                for value, name in (
                    (self.correlation_id, "correlation_id"),
                    (self.actor_entity_id, "actor_entity_id"),
                    (self.actor_life_id, "actor_life_id"),
                    (self.action_key, "action_key"),
                    (self.cancel_token, "cancel_token"),
                ):
                    _identifier(value, name)
                if self.target_life_id is not None:
                    _identifier(self.target_life_id, "target_life_id")
                if not isinstance(self.binding, ActionBinding):
                    raise ValueError("binding must be an ActionBinding")
                _non_negative_integer(self.phase_index, "phase_index")
                if not isinstance(self.phase_kind, PhaseKind):
                    raise ValueError("phase_kind must be a PhaseKind")
                _non_negative_integer(self.phase_started_at_ms, "phase_started_at_ms")
                _non_negative_integer(self.phase_ends_at_ms, "phase_ends_at_ms")
                if self.phase_ends_at_ms < self.phase_started_at_ms:
                    raise ValueError("phase_ends_at_ms must not precede phase_started_at_ms")
                if not isinstance(self.status, ActionExecutionStatus):
                    raise ValueError("status must be an ActionExecutionStatus")
                if not isinstance(self.payload_release_status, PayloadReleaseStatus):
                    raise ValueError("payload_release_status must be a PayloadReleaseStatus")
                for value, name in (
                    (self.phase_interruptible, "phase_interruptible"),
                    (self.movement_allowed, "movement_allowed"),
                    (self.cancel_on_damage, "cancel_on_damage"),
                    (self.cancel_on_stun, "cancel_on_stun"),
                    (self.trigger_payload_scheduled, "trigger_payload_scheduled"),
                ):
                    if not isinstance(value, bool):
                        raise ValueError(f"{name} must be a boolean")
                self.released_phase_indexes = set(self.released_phase_indexes)
                for phase_index in self.released_phase_indexes:
                    _non_negative_integer(phase_index, "released phase index")
                self.pending_triggered_effects = tuple(self.pending_triggered_effects)

            @property
            def is_terminal(self) -> bool:
                return self.status in {
                    ActionExecutionStatus.COMPLETED,
                    ActionExecutionStatus.INTERRUPTED,
                }

            @property
            def current_phase_released(self) -> bool:
                return self.phase_index in self.released_phase_indexes

            def snapshot(self) -> ActionExecutionSnapshot:
                return ActionExecutionSnapshot(
                    correlation_id=self.correlation_id,
                    actor_entity_id=self.actor_entity_id,
                    actor_life_id=self.actor_life_id,
                    target_life_id=self.target_life_id,
                    action_key=self.action_key,
                    binding=self.binding,
                    phase_index=self.phase_index,
                    phase_kind=self.phase_kind,
                    phase_started_at_ms=self.phase_started_at_ms,
                    phase_ends_at_ms=self.phase_ends_at_ms,
                    status=self.status,
                    phase_interruptible=self.phase_interruptible,
                    movement_allowed=self.movement_allowed,
                    payload_release_status=self.payload_release_status,
                    released_phase_indexes=tuple(sorted(self.released_phase_indexes)),
                    cancel_token=self.cancel_token,
                    cancel_on_damage=self.cancel_on_damage,
                    cancel_on_stun=self.cancel_on_stun,
                    pending_triggered_effects=self.pending_triggered_effects,
                    trigger_payload_scheduled=self.trigger_payload_scheduled,
                )

            @classmethod
            def from_snapshot(cls, snapshot: ActionExecutionSnapshot) -> ActionExecutionState:
                return cls(
                    correlation_id=snapshot.correlation_id,
                    actor_entity_id=snapshot.actor_entity_id,
                    actor_life_id=snapshot.actor_life_id,
                    target_life_id=snapshot.target_life_id,
                    action_key=snapshot.action_key,
                    binding=snapshot.binding,
                    phase_index=snapshot.phase_index,
                    phase_kind=snapshot.phase_kind,
                    phase_started_at_ms=snapshot.phase_started_at_ms,
                    phase_ends_at_ms=snapshot.phase_ends_at_ms,
                    status=snapshot.status,
                    phase_interruptible=snapshot.phase_interruptible,
                    movement_allowed=snapshot.movement_allowed,
                    payload_release_status=snapshot.payload_release_status,
                    released_phase_indexes=set(snapshot.released_phase_indexes),
                    cancel_token=snapshot.cancel_token,
                    cancel_on_damage=snapshot.cancel_on_damage,
                    cancel_on_stun=snapshot.cancel_on_stun,
                    pending_triggered_effects=snapshot.pending_triggered_effects,
                    trigger_payload_scheduled=snapshot.trigger_payload_scheduled,
                )
        '''
    ),
    encoding="utf-8",
)

# timeline.py
replace_once(
    "src/shadowbane_lab/sim/timeline.py",
    "from shadowbane_lab.sim.clock import ClockSnapshot\n",
    "from shadowbane_lab.sim.clock import ClockSnapshot\n"
    "from shadowbane_lab.sim.lifecycle import (\n"
    "    ActionExecutionSnapshot,\n"
    "    ContinuationPolicy,\n"
    ")\n",
)
replace_once(
    "src/shadowbane_lab/sim/timeline.py",
    "class ScheduledKind(StrEnum):\n"
    "    RESOLUTION = \"resolution\"\n"
    "    WEAPON_ATTACK = \"weapon_attack\"\n"
    "    COMPLETION = \"completion\"\n",
    "class ScheduledKind(StrEnum):\n"
    "    PHASE_RELEASE = \"phase_release\"\n"
    "    PHASE_TRANSITION = \"phase_transition\"\n"
    "    RESOLUTION = \"resolution\"\n"
    "    WEAPON_ATTACK = \"weapon_attack\"\n"
    "    COMPLETION = \"completion\"\n",
)
replace_once(
    "src/shadowbane_lab/sim/timeline.py",
    "    cancel_on_stun: bool = False\n",
    "    cancel_on_stun: bool = False\n"
    "    actor_life_id: str | None = None\n"
    "    target_life_id: str | None = None\n"
    "    phase_index: int | None = None\n"
    "    cancel_token: str | None = None\n"
    "    continuation_policy: ContinuationPolicy = ContinuationPolicy.WORLD_BOUND\n"
    "    semantic_priority: int = 0\n",
)
replace_once(
    "src/shadowbane_lab/sim/timeline.py",
    "        for value, name in (\n"
    "            (self.interruptible, \"interruptible\"),\n"
    "            (self.cancel_on_damage, \"cancel_on_damage\"),\n"
    "            (self.cancel_on_stun, \"cancel_on_stun\"),\n"
    "        ):\n"
    "            if not isinstance(value, bool):\n"
    "                raise ValueError(f\"{name} must be a boolean\")\n",
    "        for value, name in (\n"
    "            (self.interruptible, \"interruptible\"),\n"
    "            (self.cancel_on_damage, \"cancel_on_damage\"),\n"
    "            (self.cancel_on_stun, \"cancel_on_stun\"),\n"
    "        ):\n"
    "            if not isinstance(value, bool):\n"
    "                raise ValueError(f\"{name} must be a boolean\")\n"
    "        for value, name in (\n"
    "            (self.actor_life_id, \"actor_life_id\"),\n"
    "            (self.target_life_id, \"target_life_id\"),\n"
    "            (self.cancel_token, \"cancel_token\"),\n"
    "        ):\n"
    "            if value is not None and (not isinstance(value, str) or not value.strip()):\n"
    "                raise ValueError(f\"{name} must be a non-empty string or null\")\n"
    "        if self.phase_index is not None and (\n"
    "            isinstance(self.phase_index, bool)\n"
    "            or not isinstance(self.phase_index, int)\n"
    "            or self.phase_index < 0\n"
    "        ):\n"
    "            raise ValueError(\"phase_index must be a non-negative integer or null\")\n"
    "        if not isinstance(self.continuation_policy, ContinuationPolicy):\n"
    "            raise ValueError(\"continuation_policy must be a ContinuationPolicy\")\n"
    "        if (\n"
    "            isinstance(self.semantic_priority, bool)\n"
    "            or not isinstance(self.semantic_priority, int)\n"
    "        ):\n"
    "            raise ValueError(\"semantic_priority must be an integer\")\n"
    "        if self.kind in {ScheduledKind.PHASE_RELEASE, ScheduledKind.PHASE_TRANSITION}\n"
    "        and self.phase_index is None:\n"
    "            raise ValueError(\"phase lifecycle work requires phase_index\")\n",
)
replace_once(
    "src/shadowbane_lab/sim/timeline.py",
    "class EnvironmentSnapshot:\n"
    "    clock: ClockSnapshot\n"
    "    random: RandomSnapshot\n"
    "    entities: tuple[EntitySnapshot, ...]\n"
    "    scheduled: tuple[ScheduledItem, ...]\n"
    "    next_schedule_order: int\n"
    "    next_event_number: int\n",
    "class EnvironmentSnapshot:\n"
    "    clock: ClockSnapshot\n"
    "    random: RandomSnapshot\n"
    "    entities: tuple[EntitySnapshot, ...]\n"
    "    scheduled: tuple[ScheduledItem, ...]\n"
    "    next_schedule_order: int\n"
    "    next_event_number: int\n"
    "    executions: tuple[ActionExecutionSnapshot, ...] = ()\n"
    "    cancelled_tokens: tuple[str, ...] = ()\n",
)

# environment.py imports and state
replace_once(
    "src/shadowbane_lab/sim/environment.py",
    "from shadowbane_lab.sim.errors import SimulationConfigurationError\n",
    "from shadowbane_lab.sim.errors import SimulationConfigurationError\n"
    "from shadowbane_lab.sim.lifecycle import (\n"
    "    ActionExecutionState,\n"
    "    ActionExecutionStatus,\n"
    "    ContinuationPolicy,\n"
    "    PayloadReleaseStatus,\n"
    ")\n",
)
replace_once(
    "src/shadowbane_lab/sim/environment.py",
    "        self._scheduled: list[ScheduledItem] = []\n"
    "        self._next_schedule_order = 0\n",
    "        self._scheduled: list[ScheduledItem] = []\n"
    "        self._executions: dict[tuple[str, str], ActionExecutionState] = {}\n"
    "        self._cancelled_tokens: set[str] = set()\n"
    "        self._next_schedule_order = 0\n",
)
replace_once(
    "src/shadowbane_lab/sim/environment.py",
    "    def entity(self, entity_id: str) -> EntityState:\n"
    "        return self._entity(entity_id).clone()\n\n",
    "    def entity(self, entity_id: str) -> EntityState:\n"
    "        return self._entity(entity_id).clone()\n\n"
    "    @property\n"
    "    def executions(self) -> tuple[ActionExecutionState, ...]:\n"
    "        return tuple(\n"
    "            ActionExecutionState.from_snapshot(execution.snapshot())\n"
    "            for _, execution in sorted(self._executions.items())\n"
    "        )\n\n"
    "    def execution(\n"
    "        self,\n"
    "        correlation_id: str,\n"
    "        *,\n"
    "        actor_id: str | None = None,\n"
    "    ) -> ActionExecutionState:\n"
    "        matches = [\n"
    "            execution\n"
    "            for execution in self._executions.values()\n"
    "            if execution.correlation_id == correlation_id\n"
    "            and (actor_id is None or execution.actor_entity_id == actor_id)\n"
    "        ]\n"
    "        if len(matches) != 1:\n"
    "            raise KeyError(f\"expected one execution for {correlation_id}, found {len(matches)}\")\n"
    "        return ActionExecutionState.from_snapshot(matches[0].snapshot())\n\n",
)
replace_once(
    "src/shadowbane_lab/sim/environment.py",
    "            next_schedule_order=self._next_schedule_order,\n"
    "            next_event_number=self._next_event_number,\n"
    "        )\n",
    "            next_schedule_order=self._next_schedule_order,\n"
    "            next_event_number=self._next_event_number,\n"
    "            executions=tuple(\n"
    "                execution.snapshot()\n"
    "                for _, execution in sorted(self._executions.items())\n"
    "            ),\n"
    "            cancelled_tokens=tuple(sorted(self._cancelled_tokens)),\n"
    "        )\n",
)
replace_once(
    "src/shadowbane_lab/sim/environment.py",
    "        self._scheduled = list(snapshot.scheduled)\n"
    "        self._next_schedule_order = snapshot.next_schedule_order\n",
    "        self._scheduled = list(snapshot.scheduled)\n"
    "        self._executions = {\n"
    "            (execution.actor_entity_id, execution.correlation_id):\n"
    "            ActionExecutionState.from_snapshot(execution)\n"
    "            for execution in snapshot.executions\n"
    "        }\n"
    "        self._cancelled_tokens = set(snapshot.cancelled_tokens)\n"
    "        self._next_schedule_order = snapshot.next_schedule_order\n",
)

new_action_lifecycle = dedent(
    '''\
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
                action.weapon_attack is not None
                and action.weapon_attack.phase_index == phase_index
            )
            native_payload = bool(phase.effects) or weapon_in_phase
            trigger_payload = bool(execution.pending_triggered_effects) and not (
                execution.trigger_payload_scheduled
            ) and (native_payload or phase_index == len(action.phases) - 1)
            has_payload = native_payload or trigger_payload

            execution.phase_index = phase_index
            execution.phase_kind = phase.kind
            execution.phase_started_at_ms = phase_started_at_ms
            execution.phase_ends_at_ms = phase_end_ms
            execution.phase_interruptible = phase.interruptible
            execution.movement_allowed = phase.movement_allowed
            execution.payload_release_status = (
                PayloadReleaseStatus.PENDING
                if has_payload
                else PayloadReleaseStatus.NOT_APPLICABLE
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

    '''
)
replace_between(
    "src/shadowbane_lab/sim/environment.py",
    "    def _start_action(\n",
    "    def _consume_action_start_triggers(\n",
    new_action_lifecycle,
)

new_process_due = dedent(
    '''\
        def _process_due(
            self,
            until_ms: int,
            events: list[Event],
            life_terminated: set[str],
        ) -> None:
            while True:
                candidates = [
                    item for item in self._scheduled if item.due_time_ms <= until_ms
                ]
                if not candidates:
                    return
                item = min(candidates, key=self._scheduled_key)
                self._scheduled.remove(item)
                if not self._scheduled_item_is_valid(item):
                    continue
                due_time = item.due_time_ms
                alive_before = {
                    entity.entity_id
                    for entity in self._entities.values()
                    if entity.alive
                }
                eligible_alive = frozenset(alive_before)
                if item.kind is ScheduledKind.PHASE_RELEASE:
                    self._release_action_phase(item)
                elif item.kind is ScheduledKind.PHASE_TRANSITION:
                    self._transition_action_phase(item)
                elif item.kind is ScheduledKind.RESOLUTION:
                    self._effect_executor.resolve(item, due_time, eligible_alive, events)
                elif item.kind is ScheduledKind.WEAPON_ATTACK:
                    self._effect_executor.resolve_weapon_attack(
                        item, due_time, eligible_alive, events
                    )
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
                    raise SimulationConfigurationError(
                        f"unsupported scheduled kind: {item.kind}"
                    )
                self._effect_executor.resolve_deaths(
                    due_time,
                    events,
                    life_terminated,
                )
                newly_dead = tuple(
                    sorted(
                        entity_id
                        for entity_id in alive_before
                        if not self._entities[entity_id].alive
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
            return (
                actor is not None
                and actor.alive
                and actor.life_id == item.actor_life_id
            )

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

    '''
)
replace_between(
    "src/shadowbane_lab/sim/environment.py",
    "    def _process_due(\n",
    "    def _delivery_delay(\n",
    new_process_due,
)

new_interrupt = dedent(
    '''\
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

    '''
)
replace_between(
    "src/shadowbane_lab/sim/environment.py",
    "    def _interrupt_actor(\n",
    "    def _schedule(self, item: ScheduledItem) -> None:\n",
    new_interrupt,
)
replace_once(
    "src/shadowbane_lab/sim/environment.py",
    "    @staticmethod\n"
    "    def _scheduled_key(item: ScheduledItem) -> tuple[int, int]:\n"
    "        return item.due_time_ms, item.order\n",
    "    @staticmethod\n"
    "    def _scheduled_key(item: ScheduledItem) -> tuple[int, int, int]:\n"
    "        return item.due_time_ms, item.semantic_priority, item.order\n",
)

# effects.py: lifecycle ownership and immediate liveness consistency.
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "from shadowbane_lab.sim.errors import SimulationConfigurationError\n",
    "from shadowbane_lab.sim.errors import SimulationConfigurationError\n"
    "from shadowbane_lab.sim.lifecycle import ContinuationPolicy\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        if actor is None or target is None:\n"
    "            raise SimulationConfigurationError(\"weapon attack requires actor and entity target\")\n"
    "        if actor.entity_id not in eligible_alive or target.entity_id not in eligible_alive:\n"
    "            return\n",
    "        if actor is None or target is None:\n"
    "            raise SimulationConfigurationError(\"weapon attack requires actor and entity target\")\n"
    "        if actor.entity_id not in eligible_alive or target.entity_id not in eligible_alive:\n"
    "            return\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        if not bypass_passive:\n"
    "            for defense_key in attack.passive_defense_keys:\n",
    "        if not bypass_passive and \"control.stun\" not in target.effective_tags:\n"
    "            for defense_key in attack.passive_defense_keys:\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        actor = self._entity(item.actor_id)\n"
    "        center = self._area_center(effect, item.binding)\n",
    "        actor = self._entity(item.actor_id)\n"
    "        if actor.entity_id not in eligible_alive:\n"
    "            return\n"
    "        center = self._area_center(effect, item.binding)\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        actor = self._entity(item.actor_id)\n"
    "        target = self._entity(item.binding.target_entity_id)\n"
    "        action = self._catalog.get(item.action_key)\n",
    "        actor = self._entity(item.actor_id)\n"
    "        target = self._entity(item.binding.target_entity_id)\n"
    "        if actor.entity_id not in eligible_alive or target.entity_id not in eligible_alive:\n"
    "            return\n"
    "        action = self._catalog.get(item.action_key)\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        if \"combat.ignore_passive_defense\" not in actor.effective_tags and not bypass_passive:\n",
    "        if (\n"
    "            \"combat.ignore_passive_defense\" not in actor.effective_tags\n"
    "            and \"control.stun\" not in target.effective_tags\n"
    "            and not bypass_passive\n"
    "        ):\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        elif isinstance(effect, TransferResource):\n"
    "            self._transfer_resource(item, effect, due_time, events)\n",
    "        elif isinstance(effect, TransferResource):\n"
    "            source = self._entity_for_ref(effect.from_subject, item.binding)\n"
    "            destination = self._entity_for_ref(effect.to_subject, item.binding)\n"
    "            if (\n"
    "                source is None\n"
    "                or destination is None\n"
    "                or source.entity_id not in eligible_alive\n"
    "                or destination.entity_id not in eligible_alive\n"
    "            ):\n"
    "                return\n"
    "            self._transfer_resource(item, effect, due_time, events)\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        elif isinstance(effect, TransferItem):\n"
    "            self._transfer_item(item, effect, due_time, events)\n",
    "        elif isinstance(effect, TransferItem):\n"
    "            source = self._entity_for_ref(effect.from_subject, item.binding)\n"
    "            destination = self._entity_for_ref(effect.to_subject, item.binding)\n"
    "            if (\n"
    "                source is None\n"
    "                or destination is None\n"
    "                or source.entity_id not in eligible_alive\n"
    "                or destination.entity_id not in eligible_alive\n"
    "            ):\n"
    "                return\n"
    "            self._transfer_item(item, effect, due_time, events)\n",
)
# Mark newly-created periodic work as effect-instance-bound. The same snippets occur once
# in _apply_effect after the initial-effects scheduler lives in environment.py.
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "                        periodic_key=modifier.periodic_key,\n"
    "                        pulse_index=pulse_index,\n"
    "                    )\n"
    "                )\n"
    "        self._schedule(\n"
    "            ScheduledItem(\n"
    "                due_time_ms=active.expires_at_ms,\n",
    "                        periodic_key=modifier.periodic_key,\n"
    "                        pulse_index=pulse_index,\n"
    "                        continuation_policy=ContinuationPolicy.EFFECT_INSTANCE_BOUND,\n"
    "                    )\n"
    "                )\n"
    "        self._schedule(\n"
    "            ScheduledItem(\n"
    "                due_time_ms=active.expires_at_ms,\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "                expected_effect_instance_id=instance_id,\n"
    "            )\n"
    "        )\n"
    "        if \"control.stun\" in effect.tags:\n",
    "                expected_effect_instance_id=instance_id,\n"
    "                continuation_policy=ContinuationPolicy.EFFECT_INSTANCE_BOUND,\n"
    "            )\n"
    "        )\n"
    "        if \"control.stun\" in effect.tags:\n",
)

# Public exports.
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "from shadowbane_lab.sim.environment import ReferenceEnvironment\n",
    "from shadowbane_lab.sim.environment import ReferenceEnvironment\n"
    "from shadowbane_lab.sim.lifecycle import (\n"
    "    ActionExecutionSnapshot,\n"
    "    ActionExecutionState,\n"
    "    ActionExecutionStatus,\n"
    "    ContinuationPolicy,\n"
    "    PayloadReleaseStatus,\n"
    ")\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    \"ActionCatalog\",\n",
    "    \"ActionCatalog\",\n"
    "    \"ActionExecutionSnapshot\",\n"
    "    \"ActionExecutionState\",\n"
    "    \"ActionExecutionStatus\",\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    \"CombatStance\",\n",
    "    \"CombatStance\",\n"
    "    \"ContinuationPolicy\",\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    \"PeriodicPulse\",\n",
    "    \"PayloadReleaseStatus\",\n"
    "    \"PeriodicPulse\",\n",
)

# Replace the old accidental simultaneity contract with deterministic microstep behavior.
reference_test = Path("tests/test_reference_environment.py")
reference_text = reference_test.read_text(encoding="utf-8")
start = reference_text.index("    def test_joint_actions_resolve_from_the_same_alive_set")
end = reference_text.index("    def test_projectile_uses_virtual_travel_time", start)
reference_text = (
    reference_text[:start]
    + dedent(
        '''\
            def test_same_timestamp_actions_use_cancellation_aware_microsteps(self) -> None:
                attack = ActionSpec(
                    action_key="attack",
                    targeting=TargetingSpec(
                        kind=TargetKind.ENTITY,
                        allowed_relations=(Relation.ENEMY,),
                        maximum_range=3.0,
                    ),
                    phases=(
                        ActionPhase(
                            kind=PhaseKind.ACTIVE,
                            duration_ms=0,
                            effects=(DealDamage(SubjectRef.TARGET, 10.0, "crush"),),
                        ),
                    ),
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((attack,)),
                    (
                        actor("a", "red", Vector2(0.0, 0.0), ("attack",)),
                        actor("b", "blue", Vector2(1.0, 0.0), ("attack",)),
                    ),
                    seed=1,
                    terminate_on_last_team=True,
                )
                decision_a = action_for(
                    environment, "a", "attack", target_id="b", correlation_id="a-attacks"
                )
                decision_b = action_for(
                    environment, "b", "attack", target_id="a", correlation_id="b-attacks"
                )

                result = environment.step((decision_b, decision_a))

                self.assertTrue(environment.entity("a").alive)
                self.assertFalse(environment.entity("b").alive)
                self.assertEqual(("b:1",), result.life_terminated)
                self.assertTrue(result.world_terminated)
                self.assertEqual(
                    1,
                    sum(event.kind == EventKind.DAMAGE_APPLIED for event in result.events),
                )

        '''
    )
    + reference_text[end:]
)
reference_test.write_text(reference_text, encoding="utf-8")

Path("tests/test_lifecycle_core.py").write_text(
    dedent(
        '''\
        import unittest

        from shadowbane_lab.protocol import EntityKind, EventKind, Relation, TargetKind, Vector2
        from shadowbane_lab.sim import (
            ActionCatalog,
            ActionExecutionStatus,
            ActionPhase,
            ActionSpec,
            DealDamage,
            DeliveryKind,
            DeliverySpec,
            EntityState,
            PayloadReleaseStatus,
            PhaseKind,
            ReferenceEnvironment,
            SubjectRef,
            TargetingSpec,
        )


        def actor(
            entity_id: str,
            team_id: str,
            action_keys: tuple[str, ...],
            *,
            position: Vector2 = Vector2(0.0, 0.0),
            health: float = 100.0,
        ) -> EntityState:
            return EntityState(
                entity_id=entity_id,
                life_id=f"{entity_id}:1",
                kind=EntityKind.ACTOR,
                team_id=team_id,
                position=position,
                scalars={"health": health, "mana": 100.0, "move_speed": 10.0},
                maximums={"health": health, "mana": 100.0},
                action_keys=action_keys,
            )


        def decision(
            environment: ReferenceEnvironment,
            actor_id: str,
            action_key: str,
            correlation_id: str,
            *,
            target_id: str | None = None,
        ):
            exchange = environment.exchange(actor_id)
            matches = [
                item
                for item in exchange.affordances.affordances
                if item.action_key == action_key
                and (target_id is None or item.binding.target_entity_id == target_id)
            ]
            if len(matches) != 1:
                raise AssertionError(f"expected one affordance, found {len(matches)}")
            return exchange.decision(matches[0].affordance_id, correlation_id)


        def hostile_targeting(maximum_range: float = 120.0) -> TargetingSpec:
            return TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=maximum_range,
            )


        class LifecycleCoreTests(unittest.TestCase):
            def test_execution_snapshot_tracks_current_phase_and_replays(self) -> None:
                cast = ActionSpec(
                    action_key="cast",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.WINDUP,
                            400,
                            interruptible=True,
                            movement_allowed=False,
                        ),
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            200,
                            effects=(DealDamage(SubjectRef.TARGET, 5.0, "magic"),),
                            interruptible=True,
                        ),
                        ActionPhase(PhaseKind.RECOVERY, 200),
                    ),
                    cancel_on_damage=True,
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((cast,)),
                    (
                        actor("caster", "red", ("cast",)),
                        actor("target", "blue", (), position=Vector2(1.0, 0.0)),
                    ),
                    seed=1,
                )

                environment.step(
                    (decision(environment, "caster", "cast", "cast-1", target_id="target"),)
                )
                execution = environment.execution("cast-1")
                snapshot = environment.snapshot()

                self.assertEqual(0, execution.phase_index)
                self.assertEqual(PhaseKind.WINDUP, execution.phase_kind)
                self.assertEqual(ActionExecutionStatus.ACTIVE, execution.status)
                self.assertFalse(execution.movement_allowed)
                self.assertEqual(PayloadReleaseStatus.NOT_APPLICABLE, execution.payload_release_status)
                expected = environment.step()
                environment.restore(snapshot)
                self.assertEqual(expected, environment.step())

            def test_later_interruptible_phase_does_not_make_windup_interruptible(self) -> None:
                poke = ActionSpec(
                    action_key="poke",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(DealDamage(SubjectRef.TARGET, 1.0, "crush"),),
                        ),
                    ),
                )
                cast = ActionSpec(
                    action_key="cast",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(PhaseKind.WINDUP, 400, interruptible=False),
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(DealDamage(SubjectRef.TARGET, 7.0, "magic"),),
                            interruptible=True,
                        ),
                    ),
                    cancel_on_damage=True,
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((poke, cast)),
                    (
                        actor("a-poker", "blue", ("poke",), position=Vector2(1.0, 0.0)),
                        actor("b-caster", "red", ("cast",)),
                    ),
                    seed=2,
                )
                result = environment.step(
                    (
                        decision(
                            environment,
                            "a-poker",
                            "poke",
                            "poke-1",
                            target_id="b-caster",
                        ),
                        decision(
                            environment,
                            "b-caster",
                            "cast",
                            "cast-1",
                            target_id="a-poker",
                        ),
                    )
                )
                environment.step()

                self.assertFalse(
                    any(
                        event.kind == EventKind.ACTION_INTERRUPTED
                        and event.correlation_id == "cast-1"
                        for event in result.events
                    )
                )
                self.assertEqual(93.0, environment.entity("a-poker").scalars["health"])
                self.assertEqual(ActionExecutionStatus.COMPLETED, environment.execution("cast-1").status)

            def test_same_timestamp_damage_cancels_unreleased_payload_still_in_queue(self) -> None:
                interrupt = ActionSpec(
                    action_key="interrupt",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            200,
                            effects=(DealDamage(SubjectRef.TARGET, 1.0, "crush"),),
                        ),
                    ),
                )
                cast = ActionSpec(
                    action_key="cast",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            200,
                            effects=(DealDamage(SubjectRef.TARGET, 20.0, "magic"),),
                            interruptible=True,
                        ),
                    ),
                    cancel_on_damage=True,
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((interrupt, cast)),
                    (
                        actor("a-interrupter", "blue", ("interrupt",), position=Vector2(1.0, 0.0)),
                        actor("b-caster", "red", ("cast",)),
                    ),
                    seed=3,
                )

                result = environment.step(
                    (
                        decision(
                            environment,
                            "a-interrupter",
                            "interrupt",
                            "interrupt-1",
                            target_id="b-caster",
                        ),
                        decision(
                            environment,
                            "b-caster",
                            "cast",
                            "cast-1",
                            target_id="a-interrupter",
                        ),
                    )
                )

                self.assertEqual(100.0, environment.entity("a-interrupter").scalars["health"])
                self.assertEqual(ActionExecutionStatus.INTERRUPTED, environment.execution("cast-1").status)
                self.assertTrue(
                    any(
                        event.kind == EventKind.ACTION_INTERRUPTED
                        and event.correlation_id == "cast-1"
                        for event in result.events
                    )
                )

            def test_released_projectile_survives_source_death_without_completed_then_interrupted(self) -> None:
                bolt = ActionSpec(
                    action_key="bolt",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(DealDamage(SubjectRef.TARGET, 9.0, "cold"),),
                            delivery=DeliverySpec(
                                DeliveryKind.PROJECTILE,
                                projectile_speed_units_per_second=60.0,
                            ),
                            interruptible=True,
                        ),
                    ),
                    cancel_on_damage=True,
                )
                kill = ActionSpec(
                    action_key="kill",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(DealDamage(SubjectRef.TARGET, 200.0, "crush"),),
                        ),
                    ),
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((bolt, kill)),
                    (
                        actor("caster", "red", ("bolt",)),
                        actor("killer", "blue", ("kill",), position=Vector2(1.0, 0.0)),
                        actor("target", "blue", (), position=Vector2(60.0, 0.0)),
                    ),
                    seed=4,
                )
                first = environment.step(
                    (decision(environment, "caster", "bolt", "bolt-1", target_id="target"),)
                )
                second = environment.step(
                    (decision(environment, "killer", "kill", "kill-1", target_id="caster"),)
                )
                for _ in range(3):
                    environment.step()
                impact = environment.step()

                self.assertFalse(environment.entity("caster").alive)
                self.assertEqual(91.0, environment.entity("target").scalars["health"])
                self.assertEqual(ActionExecutionStatus.COMPLETED, environment.execution("bolt-1").status)
                all_events = (*first.events, *second.events, *impact.events)
                self.assertFalse(
                    any(
                        event.kind == EventKind.ACTION_INTERRUPTED
                        and event.correlation_id == "bolt-1"
                        for event in all_events
                    )
                )

            def test_death_cancels_source_bound_unreleased_work(self) -> None:
                cast = ActionSpec(
                    action_key="cast",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.WINDUP,
                            600,
                            effects=(DealDamage(SubjectRef.TARGET, 25.0, "magic"),),
                            interruptible=False,
                        ),
                    ),
                )
                kill = ActionSpec(
                    action_key="kill",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(DealDamage(SubjectRef.TARGET, 200.0, "crush"),),
                        ),
                    ),
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((cast, kill)),
                    (
                        actor("caster", "red", ("cast",)),
                        actor("killer", "blue", ("kill",), position=Vector2(1.0, 0.0)),
                    ),
                    seed=5,
                )
                environment.step(
                    (decision(environment, "caster", "cast", "cast-1", target_id="killer"),)
                )
                death = environment.step(
                    (decision(environment, "killer", "kill", "kill-1", target_id="caster"),)
                )
                for _ in range(3):
                    environment.step()

                self.assertEqual(100.0, environment.entity("killer").scalars["health"])
                self.assertEqual(ActionExecutionStatus.INTERRUPTED, environment.execution("cast-1").status)
                self.assertTrue(
                    any(
                        event.kind == EventKind.ACTION_INTERRUPTED
                        and event.correlation_id == "cast-1"
                        and "reason.death" in event.tags
                        for event in death.events
                    )
                )


        if __name__ == "__main__":
            unittest.main()
        '''
    ),
    encoding="utf-8",
)
