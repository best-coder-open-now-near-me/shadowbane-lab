from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    target.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


# actions.py: add one non-recursive conditional primitive over direct effects.
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "from shadowbane_lab.protocol import Relation, TargetKind, Vector2\n",
    "from shadowbane_lab.protocol import Relation, TargetKind, Vector2\n"
    "from shadowbane_lab.sim.outcomes import EffectOutcomeKind\n",
)

conditional_type = dedent(
    '''\

    @dataclass(frozen=True, slots=True)
    class OutcomeConditional:
        """Resolve follow-up primitives only for selected condition outcomes.

        The condition and both branches are intentionally limited to direct
        primitives. This keeps the first conditional algebra finite and
        auditable while still expressing patterns such as "ground only when
        stun applied" and "grant immunity only after a successful control".
        """

        conditional_key: str
        condition: DirectEffectPrimitive
        outcomes: tuple[EffectOutcomeKind, ...]
        effects: tuple[DirectEffectPrimitive, ...]
        else_effects: tuple[DirectEffectPrimitive, ...] = ()

        def __post_init__(self) -> None:
            _identifier(self.conditional_key, "conditional_key")
            if not isinstance(self.condition, _DIRECT_EFFECT_TYPES):
                raise ValueError("condition must be a direct effect primitive")
            if not self.outcomes:
                raise ValueError("outcomes must not be empty")
            if len(self.outcomes) != len(set(self.outcomes)):
                raise ValueError("outcomes must not contain duplicates")
            for outcome in self.outcomes:
                if not isinstance(outcome, EffectOutcomeKind):
                    raise ValueError("outcomes must contain EffectOutcomeKind values")
            if not self.effects and not self.else_effects:
                raise ValueError("at least one conditional branch must contain effects")
            for branch, field_name in (
                (self.effects, "effects"),
                (self.else_effects, "else_effects"),
            ):
                for effect in branch:
                    if not isinstance(effect, _DIRECT_EFFECT_TYPES):
                        raise ValueError(
                            f"{field_name} may contain only direct effect primitives"
                        )
    '''
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "_DIRECT_EFFECT_TYPES = (\n"
    "    DealDamage,\n"
    "    RestoreResource,\n"
    "    ModifyScalar,\n"
    "    ModifyTag,\n"
    "    ApplyEffect,\n"
    "    RemoveEffect,\n"
    "    MoveEntity,\n"
    "    ModifyObjective,\n"
    "    ChangeStance,\n"
    "    TransferResource,\n"
    "    TransferItem,\n"
    ")\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class ChanceGate:\n",
    "_DIRECT_EFFECT_TYPES = (\n"
    "    DealDamage,\n"
    "    RestoreResource,\n"
    "    ModifyScalar,\n"
    "    ModifyTag,\n"
    "    ApplyEffect,\n"
    "    RemoveEffect,\n"
    "    MoveEntity,\n"
    "    ModifyObjective,\n"
    "    ChangeStance,\n"
    "    TransferResource,\n"
    "    TransferItem,\n"
    ")\n"
    + conditional_type
    + "\n\n@dataclass(frozen=True, slots=True)\n"
    "class ChanceGate:\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    effects: tuple[DirectEffectPrimitive, ...]\n",
    "    effects: tuple[DirectEffectPrimitive | OutcomeConditional, ...]\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "        for effect in self.effects:\n"
    "            if not isinstance(effect, _DIRECT_EFFECT_TYPES):\n"
    "                raise ValueError(\"chance-gated effects must contain effect primitives\")\n",
    "        for effect in self.effects:\n"
    "            if not isinstance(effect, (*_DIRECT_EFFECT_TYPES, OutcomeConditional)):\n"
    "                raise ValueError(\n"
    "                    \"chance-gated effects must contain direct or conditional primitives\"\n"
    "                )\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    effects: tuple[DirectEffectPrimitive | ChanceGate, ...]\n",
    "    effects: tuple[DirectEffectPrimitive | OutcomeConditional | ChanceGate, ...]\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "            if not isinstance(effect, (*_DIRECT_EFFECT_TYPES, ChanceGate)):\n"
    "                raise ValueError(\"attack gate effects must contain effect primitives\")\n",
    "            if not isinstance(\n"
    "                effect,\n"
    "                (*_DIRECT_EFFECT_TYPES, OutcomeConditional, ChanceGate),\n"
    "            ):\n"
    "                raise ValueError(\n"
    "                    \"attack gate effects must contain direct, conditional, or chance primitives\"\n"
    "                )\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    effects: tuple[DirectEffectPrimitive | AttackGate | ChanceGate, ...]\n",
    "    effects: tuple[\n"
    "        DirectEffectPrimitive | OutcomeConditional | AttackGate | ChanceGate, ...\n"
    "    ]\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "            if not isinstance(effect, (*_DIRECT_EFFECT_TYPES, AttackGate, ChanceGate)):\n"
    "                raise ValueError(\"area effects must contain effect primitives or gates\")\n",
    "            if not isinstance(\n"
    "                effect,\n"
    "                (*_DIRECT_EFFECT_TYPES, OutcomeConditional, AttackGate, ChanceGate),\n"
    "            ):\n"
    "                raise ValueError(\n"
    "                    \"area effects must contain direct, conditional, or gate primitives\"\n"
    "                )\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "EffectPrimitive: TypeAlias = DirectEffectPrimitive | ChanceGate | AttackGate | AreaEffect\n",
    "EffectPrimitive: TypeAlias = (\n"
    "    DirectEffectPrimitive | OutcomeConditional | ChanceGate | AttackGate | AreaEffect\n"
    ")\n",
)

# effects.py imports and dispatch.
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "    MoveEntity,\n"
    "    PeriodicPulse,\n",
    "    MoveEntity,\n"
    "    OutcomeConditional,\n"
    "    PeriodicPulse,\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "from shadowbane_lab.sim.lifecycle import ContinuationPolicy\n",
    "from shadowbane_lab.sim.lifecycle import ContinuationPolicy\n"
    "from shadowbane_lab.sim.outcomes import EffectOutcome, EffectOutcomeKind\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        if isinstance(effect, AttackGate):\n"
    "            self._resolve_attack(item, effect, binding, due_time, eligible_alive, events)\n"
    "        elif isinstance(effect, ChanceGate):\n",
    "        if isinstance(effect, AttackGate):\n"
    "            self._resolve_attack(item, effect, binding, due_time, eligible_alive, events)\n"
    "        elif isinstance(effect, OutcomeConditional):\n"
    "            self._resolve_outcome_conditional(\n"
    "                item, effect, binding, due_time, eligible_alive, events\n"
    "            )\n"
    "        elif isinstance(effect, ChanceGate):\n",
)

new_direct_and_conditional = dedent(
    '''\
        def _resolve_direct(
            self,
            item: ScheduledItem,
            effect: DirectEffectPrimitive,
            binding: ActionBinding,
            due_time: int,
            eligible_alive: frozenset[str],
            events: list[Event],
        ) -> EffectOutcome:
            subject_ref = _direct_subject(effect)
            subject = self._entity_for_ref(subject_ref, binding) if subject_ref is not None else None
            primitive_kind = type(effect).__name__
            if subject is not None and subject.entity_id not in eligible_alive:
                return EffectOutcome(
                    EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    tags=("reason.subject_not_alive",),
                )
            if isinstance(effect, DealDamage):
                if subject is None:  # pragma: no cover - guaranteed by _direct_subject.
                    raise SimulationConfigurationError("damage effect requires a subject")
                before = subject.scalars.get("health", 0.0)
                self._deal_damage(item, subject, effect, due_time, events)
                amount = max(0.0, before - subject.scalars.get("health", 0.0))
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if amount > 0.0 else EffectOutcomeKind.RESISTED,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    magnitude=amount,
                )
            if isinstance(effect, RestoreResource):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("resource restoration requires a subject")
                before = subject.scalars.get(effect.resource_key, 0.0)
                self._restore_resource(item, subject, effect, due_time, events)
                amount = max(0.0, subject.scalars.get(effect.resource_key, 0.0) - before)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if amount > 0.0 else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    magnitude=amount,
                )
            if isinstance(effect, TransferResource):
                source = self._entity_for_ref(effect.from_subject, binding)
                destination = self._entity_for_ref(effect.to_subject, binding)
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
                amount = max(0.0, before[0] - after[0])
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=destination.entity_id,
                    magnitude=amount,
                )
            if isinstance(effect, ModifyScalar):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("scalar modification requires a subject")
                before = subject.scalars.get(effect.scalar_key, 0.0)
                self._modify_scalar(item, subject, effect, due_time, events)
                after = subject.scalars.get(effect.scalar_key, 0.0)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    magnitude=after - before,
                )
            if isinstance(effect, ModifyTag):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("tag modification requires a subject")
                before = effect.tag in subject.base_tags
                self._modify_tag(item, subject, effect, due_time, events)
                after = effect.tag in subject.base_tags
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    effect_key=effect.tag,
                )
            if isinstance(effect, ApplyEffect):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("active effect requires a subject")
                return self._apply_effect(item, subject, effect, binding, due_time, events)
            if isinstance(effect, RemoveEffect):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("effect removal requires a subject")
                before = tuple(subject.active_effects)
                self._remove_effect(item, subject, effect, due_time, events)
                removed = len(before) - len(subject.active_effects)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if removed > 0 else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    magnitude=float(removed),
                )
            if isinstance(effect, MoveEntity):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("movement requires a subject")
                before = subject.position
                self._move_entity(item, subject, effect, binding, due_time, events)
                moved = subject.position.distance_to(before)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if moved > 0.0 else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    magnitude=moved,
                )
            if isinstance(effect, TransferItem):
                source = self._entity_for_ref(effect.from_subject, binding)
                destination = self._entity_for_ref(effect.to_subject, binding)
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
                    source.inventory.get(effect.item_key, 0),
                    destination.inventory.get(effect.item_key, 0),
                )
                self._transfer_item(item, effect, due_time, events)
                after = (
                    source.inventory.get(effect.item_key, 0),
                    destination.inventory.get(effect.item_key, 0),
                )
                amount = max(0, before[0] - after[0])
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=destination.entity_id,
                    magnitude=float(amount),
                )
            if isinstance(effect, ModifyObjective):
                before = self._objective_scalars.get(effect.objective_key, 0.0)
                self._modify_objective(item, effect, due_time, events)
                after = self._objective_scalars.get(effect.objective_key, 0.0)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if after != before else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    effect_key=effect.objective_key,
                    magnitude=after - before,
                )
            if isinstance(effect, ChangeStance):
                if subject is None:  # pragma: no cover
                    raise SimulationConfigurationError("stance change requires a subject")
                before = subject.stance
                self._change_stance(item, subject, effect, due_time, events)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED if subject.stance != before else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id,
                    effect_key=effect.stance.value,
                )
            raise SimulationConfigurationError(f"unsupported effect primitive: {type(effect)!r}")

        def _resolve_outcome_conditional(
            self,
            item: ScheduledItem,
            conditional: OutcomeConditional,
            binding: ActionBinding,
            due_time: int,
            eligible_alive: frozenset[str],
            events: list[Event],
        ) -> EffectOutcome:
            outcome = self._resolve_direct(
                item,
                conditional.condition,
                binding,
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
                self._resolve_direct(
                    item,
                    effect,
                    binding,
                    due_time,
                    eligible_alive,
                    events,
                )
            return outcome

    '''
)
replace_between(
    "src/shadowbane_lab/sim/effects.py",
    "    def _resolve_direct(\n",
    "    def _resolve_attack(\n",
    new_direct_and_conditional,
)

# Gate and area loops need to dispatch conditional primitives.
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        for nested in gate.effects:\n"
    "            if isinstance(nested, ChanceGate):\n"
    "                self._resolve_chance(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n"
    "            else:\n"
    "                self._resolve_direct(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n",
    "        for nested in gate.effects:\n"
    "            if isinstance(nested, ChanceGate):\n"
    "                self._resolve_chance(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n"
    "            elif isinstance(nested, OutcomeConditional):\n"
    "                self._resolve_outcome_conditional(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n"
    "            else:\n"
    "                self._resolve_direct(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        for nested in gate.effects:\n"
    "            self._resolve_direct(\n"
    "                item, nested, binding, due_time, eligible_alive, events\n"
    "            )\n\n"
    "    def _resolve_area(\n",
    "        for nested in gate.effects:\n"
    "            if isinstance(nested, OutcomeConditional):\n"
    "                self._resolve_outcome_conditional(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n"
    "            else:\n"
    "                self._resolve_direct(\n"
    "                    item, nested, binding, due_time, eligible_alive, events\n"
    "                )\n\n"
    "    def _resolve_area(\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "            for nested in area.effects:\n"
    "                if isinstance(nested, AttackGate):\n"
    "                    self._resolve_attack(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n"
    "                elif isinstance(nested, ChanceGate):\n"
    "                    self._resolve_chance(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n"
    "                else:\n"
    "                    self._resolve_direct(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n",
    "            for nested in area.effects:\n"
    "                if isinstance(nested, AttackGate):\n"
    "                    self._resolve_attack(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n"
    "                elif isinstance(nested, ChanceGate):\n"
    "                    self._resolve_chance(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n"
    "                elif isinstance(nested, OutcomeConditional):\n"
    "                    self._resolve_outcome_conditional(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n"
    "                else:\n"
    "                    self._resolve_direct(\n"
    "                        item, nested, victim_binding, due_time, eligible_alive, events\n"
    "                    )\n",
)

new_apply_effect = dedent(
    '''\
        def _apply_effect(
            self,
            item: ScheduledItem,
            subject: EntityState,
            effect: ApplyEffect,
            binding: ActionBinding,
            due_time: int,
            events: list[Event],
        ) -> EffectOutcome:
            immunity_tags = set(effect.immunity_tags)
            active_tags = set(subject.effective_tags)
            matching_immunity = sorted(immunity_tags & active_tags)
            if matching_immunity:
                events.append(
                    self._event(
                        "effect_immune",
                        due_time,
                        correlation_id=item.correlation_id,
                        source_entity_id=item.actor_id,
                        target_entity_id=subject.entity_id,
                        action_key=item.action_key,
                        tags=tuple(matching_immunity),
                    )
                )
                return EffectOutcome(
                    EffectOutcomeKind.BLOCKED_IMMUNITY,
                    type(effect).__name__,
                    subject_entity_id=subject.entity_id,
                    effect_key=effect.effect_key,
                    tags=tuple(matching_immunity),
                )
            existing_effect = subject.active_effects.get(effect.effect_key)
            replaced_effect: ActiveEffect | None = None
            if existing_effect is not None:
                replaced_effect = existing_effect
            elif effect.stacking_key is not None:
                same_stack = sorted(
                    (
                        candidate
                        for candidate in subject.active_effects.values()
                        if candidate.stacking_key == effect.stacking_key
                    ),
                    key=lambda candidate: (
                        candidate.applied_at_ms,
                        candidate.effect_key,
                    ),
                )
                if same_stack:
                    incumbent = same_stack[-1]
                    incoming_wins = _incoming_effect_wins(
                        effect.stack_order,
                        incoming_rank=effect.rank,
                        incoming_priority=effect.priority,
                        incumbent=incumbent,
                    )
                    if incoming_wins:
                        replaced_effect = incumbent
                    else:
                        events.append(
                            self._event(
                                "effect_blocked",
                                due_time,
                                correlation_id=item.correlation_id,
                                source_entity_id=item.actor_id,
                                target_entity_id=subject.entity_id,
                                action_key=item.action_key,
                                tags=(
                                    f"stacking_key.{effect.stacking_key}",
                                    f"incumbent.{incumbent.effect_key}",
                                ),
                            )
                        )
                        return EffectOutcome(
                            EffectOutcomeKind.BLOCKED_STACK,
                            type(effect).__name__,
                            subject_entity_id=subject.entity_id,
                            effect_key=effect.effect_key,
                            tags=(
                                f"stacking_key.{effect.stacking_key}",
                                f"incumbent.{incumbent.effect_key}",
                            ),
                        )
            refreshed = (
                replaced_effect is not None
                and replaced_effect.effect_key == effect.effect_key
            )
            if replaced_effect is not None:
                subject.active_effects.pop(replaced_effect.effect_key, None)
                events.append(
                    self._event(
                        "effect_removed",
                        due_time,
                        correlation_id=item.correlation_id,
                        source_entity_id=item.actor_id,
                        target_entity_id=subject.entity_id,
                        action_key=item.action_key,
                        tags=(
                            f"reason.replaced_by.{effect.effect_key}",
                            *replaced_effect.tags,
                        ),
                    )
                )
            instance_id = self._next_effect_instance_id(subject, effect.effect_key)
            active = ActiveEffect(
                effect_key=effect.effect_key,
                instance_id=instance_id,
                source_entity_id=item.actor_id,
                applied_at_ms=due_time,
                expires_at_ms=due_time + effect.duration_ms,
                modifiers=effect.modifiers,
                tags=effect.tags,
                stacking_key=effect.stacking_key,
                rank=effect.rank,
                priority=effect.priority,
                stack_order=effect.stack_order,
                dispel_kind=effect.dispel_kind,
            )
            subject.active_effects[effect.effect_key] = active
            events.append(
                self._event(
                    "effect_refreshed" if refreshed else "effect_applied",
                    due_time,
                    correlation_id=item.correlation_id,
                    source_entity_id=item.actor_id,
                    target_entity_id=subject.entity_id,
                    action_key=item.action_key,
                    tags=effect.tags,
                )
            )
            for initial_effect in effect.initial_effects:
                initial_item = ScheduledItem(
                    due_time_ms=due_time,
                    order=self._take_schedule_order(),
                    kind=ScheduledKind.RESOLUTION,
                    actor_id=item.actor_id,
                    correlation_id=item.correlation_id,
                    action_key=item.action_key,
                    binding=binding,
                    effects=(initial_effect,),
                    phase_duration_ms=item.phase_duration_ms,
                    interruptible=False,
                )
                self._resolve_direct(
                    initial_item,
                    initial_effect,
                    binding,
                    due_time,
                    frozenset(
                        entity.entity_id
                        for entity in self._entities.values()
                        if entity.alive
                    ),
                    events,
                )
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
                            binding=binding,
                            interruptible=False,
                            effect_owner_id=subject.entity_id,
                            expected_effect_key=effect.effect_key,
                            expected_effect_instance_id=instance_id,
                            periodic_effects=modifier.effects,
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
                    binding=binding,
                    interruptible=False,
                    effect_owner_id=subject.entity_id,
                    expected_effect_key=effect.effect_key,
                    expected_effect_instance_id=instance_id,
                    continuation_policy=ContinuationPolicy.EFFECT_INSTANCE_BOUND,
                )
            )
            if "control.stun" in effect.tags:
                self._interrupt(subject.entity_id, "stun", due_time, events)
            return EffectOutcome(
                EffectOutcomeKind.REFRESHED if refreshed else EffectOutcomeKind.APPLIED,
                type(effect).__name__,
                subject_entity_id=subject.entity_id,
                effect_key=effect.effect_key,
                magnitude=float(effect.duration_ms),
                tags=effect.tags,
            )

    '''
)
replace_between(
    "src/shadowbane_lab/sim/effects.py",
    "    def _apply_effect(\n",
    "    def _remove_effect(\n",
    new_apply_effect,
)

# Public exports.
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    MoveEntity,\n"
    "    PeriodicPulse,\n",
    "    MoveEntity,\n"
    "    OutcomeConditional,\n"
    "    PeriodicPulse,\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "from shadowbane_lab.sim.lifecycle import (\n",
    "from shadowbane_lab.sim.outcomes import EffectOutcome, EffectOutcomeKind\n"
    "from shadowbane_lab.sim.lifecycle import (\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    \"EntityState\",\n",
    "    \"EffectOutcome\",\n"
    "    \"EffectOutcomeKind\",\n"
    "    \"EntityState\",\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    \"MoveEntity\",\n",
    "    \"MoveEntity\",\n"
    "    \"OutcomeConditional\",\n",
)

Path("tests/test_effect_outcomes.py").write_text(
    dedent(
        '''\
        import unittest

        from shadowbane_lab.protocol import EntityKind, Relation, TargetKind, Vector2
        from shadowbane_lab.sim import (
            ActionCatalog,
            ActionPhase,
            ActionSpec,
            ApplyEffect,
            EffectOutcomeKind,
            EntityState,
            ModifyTag,
            OutcomeConditional,
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
            tags: tuple[str, ...] = (),
        ) -> EntityState:
            return EntityState(
                entity_id=entity_id,
                life_id=f"{entity_id}:1",
                kind=EntityKind.ACTOR,
                team_id=team_id,
                position=Vector2(0.0 if team_id == "red" else 1.0, 0.0),
                scalars={"health": 100.0, "mana": 100.0, "move_speed": 10.0},
                maximums={"health": 100.0, "mana": 100.0},
                base_tags=tags,
                action_keys=action_keys,
            )


        def hostile_targeting() -> TargetingSpec:
            return TargetingSpec(
                kind=TargetKind.ENTITY,
                allowed_relations=(Relation.ENEMY,),
                maximum_range=10.0,
            )


        def choose(environment: ReferenceEnvironment, action_key: str, correlation_id: str):
            exchange = environment.exchange("caster")
            affordance = next(
                value
                for value in exchange.affordances.affordances
                if value.action_key == action_key
                and value.binding.target_entity_id == "target"
            )
            return exchange.decision(affordance.affordance_id, correlation_id)


        def stun_condition() -> ApplyEffect:
            return ApplyEffect(
                effect_key="effect.stun",
                subject=SubjectRef.TARGET,
                duration_ms=1_000,
                tags=("control.stun",),
                immunity_tags=("immunity.stun",),
            )


        def conditional_stun_action() -> ActionSpec:
            return ActionSpec(
                action_key="conditional-stun",
                targeting=hostile_targeting(),
                phases=(
                    ActionPhase(
                        PhaseKind.ACTIVE,
                        0,
                        effects=(
                            OutcomeConditional(
                                conditional_key="stun-followups",
                                condition=stun_condition(),
                                outcomes=(EffectOutcomeKind.APPLIED,),
                                effects=(
                                    ModifyTag(
                                        SubjectRef.TARGET,
                                        "movement.flight",
                                        add=False,
                                    ),
                                    ApplyEffect(
                                        effect_key="effect.stun-immunity",
                                        subject=SubjectRef.TARGET,
                                        duration_ms=3_000,
                                        tags=("immunity.stun",),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            )


        class EffectOutcomeTests(unittest.TestCase):
            def test_applied_condition_runs_followups(self) -> None:
                action = conditional_stun_action()
                environment = ReferenceEnvironment(
                    ActionCatalog((action,)),
                    (
                        actor("caster", "red", (action.action_key,)),
                        actor("target", "blue", (), tags=("movement.flight",)),
                    ),
                    seed=1,
                )

                result = environment.step((choose(environment, action.action_key, "cast-1"),))
                target = environment.entity("target")

                self.assertIn("effect.stun", target.active_effects)
                self.assertIn("effect.stun-immunity", target.active_effects)
                self.assertNotIn("movement.flight", target.base_tags)
                conditional = next(
                    event
                    for event in result.events
                    if event.kind == "effect_outcome_resolved"
                )
                self.assertIn("outcome.applied", conditional.tags)
                self.assertIn("branch.effects", conditional.tags)

            def test_blocked_condition_does_not_run_followups(self) -> None:
                action = conditional_stun_action()
                environment = ReferenceEnvironment(
                    ActionCatalog((action,)),
                    (
                        actor("caster", "red", (action.action_key,)),
                        actor(
                            "target",
                            "blue",
                            (),
                            tags=("movement.flight", "immunity.stun"),
                        ),
                    ),
                    seed=2,
                )

                result = environment.step((choose(environment, action.action_key, "cast-1"),))
                target = environment.entity("target")

                self.assertNotIn("effect.stun", target.active_effects)
                self.assertNotIn("effect.stun-immunity", target.active_effects)
                self.assertIn("movement.flight", target.base_tags)
                conditional = next(
                    event
                    for event in result.events
                    if event.kind == "effect_outcome_resolved"
                )
                self.assertIn("outcome.blocked_immunity", conditional.tags)
                self.assertIn("branch.else_effects", conditional.tags)

            def test_refresh_outcome_can_select_its_own_branch(self) -> None:
                initial = ActionSpec(
                    action_key="initial-stun",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(stun_condition(),),
                        ),
                    ),
                )
                refresh = ActionSpec(
                    action_key="refresh-stun",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(
                                OutcomeConditional(
                                    conditional_key="refresh-only",
                                    condition=stun_condition(),
                                    outcomes=(EffectOutcomeKind.REFRESHED,),
                                    effects=(
                                        ModifyTag(
                                            SubjectRef.TARGET,
                                            "marker.refreshed",
                                            add=True,
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((initial, refresh)),
                    (
                        actor("caster", "red", (initial.action_key, refresh.action_key)),
                        actor("target", "blue", ()),
                    ),
                    seed=3,
                )
                environment.step((choose(environment, initial.action_key, "initial"),))
                result = environment.step((choose(environment, refresh.action_key, "refresh"),))

                self.assertIn("marker.refreshed", environment.entity("target").base_tags)
                conditional = next(
                    event
                    for event in result.events
                    if event.kind == "effect_outcome_resolved"
                )
                self.assertIn("outcome.refreshed", conditional.tags)

            def test_else_branch_is_explicit(self) -> None:
                action = ActionSpec(
                    action_key="else-branch",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(
                                OutcomeConditional(
                                    conditional_key="blocked-marker",
                                    condition=stun_condition(),
                                    outcomes=(EffectOutcomeKind.APPLIED,),
                                    effects=(
                                        ModifyTag(
                                            SubjectRef.TARGET,
                                            "marker.applied",
                                            add=True,
                                        ),
                                    ),
                                    else_effects=(
                                        ModifyTag(
                                            SubjectRef.TARGET,
                                            "marker.blocked",
                                            add=True,
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
                environment = ReferenceEnvironment(
                    ActionCatalog((action,)),
                    (
                        actor("caster", "red", (action.action_key,)),
                        actor("target", "blue", (), tags=("immunity.stun",)),
                    ),
                    seed=4,
                )

                environment.step((choose(environment, action.action_key, "cast"),))

                self.assertIn("marker.blocked", environment.entity("target").base_tags)
                self.assertNotIn("marker.applied", environment.entity("target").base_tags)

            def test_conditional_grammar_rejects_recursive_or_duplicate_outcomes(self) -> None:
                with self.assertRaisesRegex(ValueError, "duplicates"):
                    OutcomeConditional(
                        conditional_key="bad",
                        condition=stun_condition(),
                        outcomes=(EffectOutcomeKind.APPLIED, EffectOutcomeKind.APPLIED),
                        effects=(
                            ModifyTag(
                                SubjectRef.TARGET,
                                "marker",
                                add=True,
                            ),
                        ),
                    )


        if __name__ == "__main__":
            unittest.main()
        '''
    ),
    encoding="utf-8",
)
