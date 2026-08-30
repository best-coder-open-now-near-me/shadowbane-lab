from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:120]!r}")
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


# ---------------------------------------------------------------------------
# Closed action grammar
# ---------------------------------------------------------------------------
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind\n",
    "from shadowbane_lab.protocol import NamedScalar, Relation, TargetKind\n"
    "from shadowbane_lab.sim.outcomes import EffectOutcomeKind\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    stack_priority: StackPriority = StackPriority.ALWAYS\n",
    "    stack_priority: StackPriority = StackPriority.ALWAYS\n"
    "    immunity_tags: tuple[str, ...] = ()\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "        _unique_strings(self.tags, \"tags\")\n"
    "        if any(not isinstance(modifier, _EFFECT_MODIFIER_TYPES) for modifier in self.modifiers):\n",
    "        _unique_strings(self.tags, \"tags\")\n"
    "        _unique_strings(self.immunity_tags, \"immunity_tags\")\n"
    "        if any(not isinstance(modifier, _EFFECT_MODIFIER_TYPES) for modifier in self.modifiers):\n",
)

conditional_definition = dedent(
    '''\

    @dataclass(frozen=True, slots=True)
    class OutcomeConditional:
        """Resolve follow-up primitives according to one direct effect's outcome.

        Branches are deliberately non-recursive. This is enough to encode
        dependencies such as "ground and grant immunity only when stun applies"
        without introducing arbitrary scripts into the closed action algebra.
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
            if any(not isinstance(outcome, EffectOutcomeKind) for outcome in self.outcomes):
                raise ValueError("outcomes must contain EffectOutcomeKind values")
            if not self.effects and not self.else_effects:
                raise ValueError("at least one conditional branch must contain effects")
            for branch, field_name in (
                (self.effects, "effects"),
                (self.else_effects, "else_effects"),
            ):
                if any(not isinstance(effect, _DIRECT_EFFECT_TYPES) for effect in branch):
                    raise ValueError(
                        f"{field_name} may contain only direct effect primitives"
                    )
    '''
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "_DIRECT_EFFECT_TYPES = (\n"
    "    ModifyScalar,\n"
    "    DealDamage,\n"
    "    RestoreResource,\n"
    "    TransferResource,\n"
    "    ModifyTag,\n"
    "    ApplyEffect,\n"
    "    RemoveEffect,\n"
    "    MoveEntity,\n"
    "    TransferItem,\n"
    "    ModifyObjective,\n"
    "    ChangeStance,\n"
    ")\n\n\n"
    "@dataclass(frozen=True, slots=True)\n"
    "class ChanceGate:\n",
    "_DIRECT_EFFECT_TYPES = (\n"
    "    ModifyScalar,\n"
    "    DealDamage,\n"
    "    RestoreResource,\n"
    "    TransferResource,\n"
    "    ModifyTag,\n"
    "    ApplyEffect,\n"
    "    RemoveEffect,\n"
    "    MoveEntity,\n"
    "    TransferItem,\n"
    "    ModifyObjective,\n"
    "    ChangeStance,\n"
    ")\n"
    + conditional_definition
    + "\n\n@dataclass(frozen=True, slots=True)\n"
    "class ChanceGate:\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    effects: tuple[DirectEffectPrimitive, ...]\n\n"
    "    def __post_init__(self) -> None:\n"
    "        _identifier(self.chance_key, \"chance_key\")\n",
    "    effects: tuple[DirectEffectPrimitive | OutcomeConditional, ...]\n\n"
    "    def __post_init__(self) -> None:\n"
    "        _identifier(self.chance_key, \"chance_key\")\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "        if any(not isinstance(effect, _DIRECT_EFFECT_TYPES) for effect in self.effects):\n"
    "            raise ValueError(\"chance gate effects must contain direct effect primitives\")\n",
    "        if any(\n"
    "            not isinstance(effect, (*_DIRECT_EFFECT_TYPES, OutcomeConditional))\n"
    "            for effect in self.effects\n"
    "        ):\n"
    "            raise ValueError(\n"
    "                \"chance gate effects must contain direct or conditional primitives\"\n"
    "            )\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    effects: tuple[DirectEffectPrimitive | ChanceGate, ...]\n",
    "    effects: tuple[DirectEffectPrimitive | OutcomeConditional | ChanceGate, ...]\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "        if any(\n"
    "            not isinstance(effect, (*_DIRECT_EFFECT_TYPES, ChanceGate)) for effect in self.effects\n"
    "        ):\n"
    "            raise ValueError(\"attack gate effects must contain direct effects or chance gates\")\n",
    "        if any(\n"
    "            not isinstance(\n"
    "                effect,\n"
    "                (*_DIRECT_EFFECT_TYPES, OutcomeConditional, ChanceGate),\n"
    "            )\n"
    "            for effect in self.effects\n"
    "        ):\n"
    "            raise ValueError(\n"
    "                \"attack gate effects must contain direct, conditional, or chance primitives\"\n"
    "            )\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "    effects: tuple[DirectEffectPrimitive | ChanceGate | AttackGate, ...]\n",
    "    effects: tuple[\n"
    "        DirectEffectPrimitive | OutcomeConditional | ChanceGate | AttackGate, ...\n"
    "    ]\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "        if any(\n"
    "            not isinstance(effect, (*_DIRECT_EFFECT_TYPES, ChanceGate, AttackGate))\n"
    "            for effect in self.effects\n"
    "        ):\n"
    "            raise ValueError(\"area effects must contain direct effects or gates\")\n",
    "        if any(\n"
    "            not isinstance(\n"
    "                effect,\n"
    "                (*_DIRECT_EFFECT_TYPES, OutcomeConditional, ChanceGate, AttackGate),\n"
    "            )\n"
    "            for effect in self.effects\n"
    "        ):\n"
    "            raise ValueError(\n"
    "                \"area effects must contain direct, conditional, or gate primitives\"\n"
    "            )\n",
)
replace_once(
    "src/shadowbane_lab/sim/actions.py",
    "EffectPrimitive = DirectEffectPrimitive | ChanceGate | AttackGate | AreaEffect\n\n"
    "_EFFECT_TYPES = (*_DIRECT_EFFECT_TYPES, ChanceGate, AttackGate, AreaEffect)\n",
    "EffectPrimitive = (\n"
    "    DirectEffectPrimitive | OutcomeConditional | ChanceGate | AttackGate | AreaEffect\n"
    ")\n\n"
    "_EFFECT_TYPES = (\n"
    "    *_DIRECT_EFFECT_TYPES,\n"
    "    OutcomeConditional,\n"
    "    ChanceGate,\n"
    "    AttackGate,\n"
    "    AreaEffect,\n"
    ")\n",
)

# ---------------------------------------------------------------------------
# Runtime outcome production and conditional dispatch
# ---------------------------------------------------------------------------
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "    MoveEntity,\n"
    "    MovementMode,\n",
    "    MoveEntity,\n"
    "    MovementMode,\n"
    "    OutcomeConditional,\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "from shadowbane_lab.sim.lifecycle import ContinuationPolicy\n",
    "from shadowbane_lab.sim.lifecycle import ContinuationPolicy\n"
    "from shadowbane_lab.sim.outcomes import EffectOutcome, EffectOutcomeKind\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "            if isinstance(effect, ChanceGate):\n"
    "                self._resolve_chance(\n"
    "                    item,\n"
    "                    effect,\n"
    "                    due_time,\n"
    "                    eligible_alive,\n"
    "                    events,\n"
    "                )\n"
    "                continue\n"
    "            self._resolve_direct(item, effect, due_time, eligible_alive, events)\n",
    "            if isinstance(effect, ChanceGate):\n"
    "                self._resolve_chance(\n"
    "                    item,\n"
    "                    effect,\n"
    "                    due_time,\n"
    "                    eligible_alive,\n"
    "                    events,\n"
    "                )\n"
    "                continue\n"
    "            if isinstance(effect, OutcomeConditional):\n"
    "                self._resolve_outcome_conditional(\n"
    "                    item, effect, due_time, eligible_alive, events\n"
    "                )\n"
    "                continue\n"
    "            self._resolve_direct(item, effect, due_time, eligible_alive, events)\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "                elif isinstance(nested, ChanceGate):\n"
    "                    self._resolve_chance(\n"
    "                        target_item,\n"
    "                        nested,\n"
    "                        due_time,\n"
    "                        eligible_alive,\n"
    "                        events,\n"
    "                    )\n"
    "                else:\n",
    "                elif isinstance(nested, ChanceGate):\n"
    "                    self._resolve_chance(\n"
    "                        target_item,\n"
    "                        nested,\n"
    "                        due_time,\n"
    "                        eligible_alive,\n"
    "                        events,\n"
    "                    )\n"
    "                elif isinstance(nested, OutcomeConditional):\n"
    "                    self._resolve_outcome_conditional(\n"
    "                        target_item, nested, due_time, eligible_alive, events\n"
    "                    )\n"
    "                else:\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "            if isinstance(resolved_nested, ChanceGate):\n"
    "                self._resolve_chance(item, resolved_nested, due_time, eligible_alive, events)\n"
    "            else:\n",
    "            if isinstance(resolved_nested, ChanceGate):\n"
    "                self._resolve_chance(item, resolved_nested, due_time, eligible_alive, events)\n"
    "            elif isinstance(resolved_nested, OutcomeConditional):\n"
    "                self._resolve_outcome_conditional(\n"
    "                    item, resolved_nested, due_time, eligible_alive, events\n"
    "                )\n"
    "            else:\n",
)
replace_once(
    "src/shadowbane_lab/sim/effects.py",
    "        if triggered:\n"
    "            for nested in effect.effects:\n"
    "                self._resolve_direct(item, nested, due_time, eligible_alive, events)\n\n"
    "    def _resolve_direct(\n",
    "        if triggered:\n"
    "            for nested in effect.effects:\n"
    "                if isinstance(nested, OutcomeConditional):\n"
    "                    self._resolve_outcome_conditional(\n"
    "                        item, nested, due_time, eligible_alive, events\n"
    "                    )\n"
    "                else:\n"
    "                    self._resolve_direct(\n"
    "                        item, nested, due_time, eligible_alive, events\n"
    "                    )\n\n"
    "    def _resolve_direct(\n",
)

new_direct_and_conditional = dedent(
    '''\
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
                    EffectOutcomeKind.APPLIED
                    if effective > 0.0
                    else EffectOutcomeKind.RESISTED,
                    primitive_kind,
                    subject_entity_id=subject.entity_id if subject is not None else None,
                    magnitude=effective,
                )
            if isinstance(effect, RestoreResource):
                before = (
                    subject.scalars.get(effect.resource_key, 0.0)
                    if subject is not None
                    else 0.0
                )
                self._restore_resource(item, effect, subject, due_time, events)
                after = (
                    subject.scalars.get(effect.resource_key, 0.0)
                    if subject is not None
                    else before
                )
                effective = max(0.0, after - before)
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED
                    if effective > 0.0
                    else EffectOutcomeKind.NO_CHANGE,
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
                    EffectOutcomeKind.APPLIED
                    if after != before
                    else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=destination.entity_id,
                    magnitude=max(0.0, before[0] - after[0]),
                )
            if isinstance(effect, ModifyScalar):
                before = (
                    subject.scalars.get(effect.scalar_key, 0.0)
                    if subject is not None
                    else 0.0
                )
                self._modify_scalar(item, effect, subject, due_time, events)
                after = (
                    subject.scalars.get(effect.scalar_key, 0.0)
                    if subject is not None
                    else before
                )
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED
                    if after != before
                    else EffectOutcomeKind.NO_CHANGE,
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
                    EffectOutcomeKind.APPLIED
                    if after != before
                    else EffectOutcomeKind.NO_CHANGE,
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
                    EffectOutcomeKind.APPLIED
                    if after < before
                    else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=subject.entity_id if subject is not None else None,
                    effect_key=effect.effect_key or effect.matching_tag,
                    magnitude=float(before - after),
                )
            if isinstance(effect, MoveEntity):
                before = subject.position if subject is not None else None
                self._move_entity(item, effect, subject, due_time, events)
                after = subject.position if subject is not None else before
                moved = before.distance_to(after) if before is not None and after is not None else 0.0
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED
                    if moved > 0.0
                    else EffectOutcomeKind.NO_CHANGE,
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
                    destination.inventory.get(item_id, 0.0)
                    if item_id is not None
                    else 0.0,
                )
                self._transfer_item(item, effect, due_time, events)
                after = (
                    source.inventory.get(item_id, 0.0) if item_id is not None else before[0],
                    destination.inventory.get(item_id, 0.0)
                    if item_id is not None
                    else before[1],
                )
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED
                    if after != before
                    else EffectOutcomeKind.NO_CHANGE,
                    primitive_kind,
                    subject_entity_id=destination.entity_id,
                    effect_key=item_id,
                    magnitude=max(0.0, before[0] - after[0]),
                )
            if isinstance(effect, ModifyObjective):
                before = (
                    subject.scalars.get("objective_progress", 0.0)
                    if subject is not None
                    else 0.0
                )
                self._modify_objective(item, effect, subject, due_time, events)
                after = (
                    subject.scalars.get("objective_progress", 0.0)
                    if subject is not None
                    else before
                )
                return EffectOutcome(
                    EffectOutcomeKind.APPLIED
                    if after != before
                    else EffectOutcomeKind.NO_CHANGE,
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
                    EffectOutcomeKind.APPLIED
                    if after != before
                    else EffectOutcomeKind.NO_CHANGE,
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

    '''
)
replace_between(
    "src/shadowbane_lab/sim/effects.py",
    "    def _resolve_direct(\n",
    "    def expire_effect(\n",
    new_direct_and_conditional,
)

new_apply_effect = dedent(
    '''\
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
                                NamedScalar(
                                    "incoming_stack_order", float(effect.stack_order)
                                ),
                                NamedScalar(
                                    "existing_stack_order", float(existing.stack_order)
                                ),
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
                EffectOutcomeKind.REFRESHED
                if refreshed
                else EffectOutcomeKind.APPLIED,
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

# ---------------------------------------------------------------------------
# Public API and regressions
# ---------------------------------------------------------------------------
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "    MoveEntity,\n"
    "    MovementMode,\n",
    "    MoveEntity,\n"
    "    MovementMode,\n"
    "    OutcomeConditional,\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "from shadowbane_lab.sim.lifecycle import (\n",
    "from shadowbane_lab.sim.lifecycle import (\n",
)
replace_once(
    "src/shadowbane_lab/sim/__init__.py",
    "from shadowbane_lab.sim.random_source import (\n",
    "from shadowbane_lab.sim.outcomes import EffectOutcome, EffectOutcomeKind\n"
    "from shadowbane_lab.sim.random_source import (\n",
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
    "    \"MovementMode\",\n",
    "    \"MovementMode\",\n"
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
            TagOperation,
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
                tags=set(tags),
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
                subject=SubjectRef.TARGET,
                effect_key="effect.stun",
                duration_ms=1_000,
                tags=("control.stun",),
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
                                        TagOperation.REMOVE,
                                    ),
                                    ApplyEffect(
                                        subject=SubjectRef.TARGET,
                                        effect_key="effect.stun-immunity",
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

                result = environment.step(
                    (choose(environment, action.action_key, "cast-1"),)
                )
                target = environment.entity("target")

                self.assertIn("effect.stun", target.effects)
                self.assertIn("effect.stun-immunity", target.effects)
                self.assertNotIn("movement.flight", target.tags)
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

                result = environment.step(
                    (choose(environment, action.action_key, "cast-1"),)
                )
                target = environment.entity("target")

                self.assertNotIn("effect.stun", target.effects)
                self.assertNotIn("effect.stun-immunity", target.effects)
                self.assertIn("movement.flight", target.tags)
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
                                            TagOperation.ADD,
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
                        actor(
                            "caster",
                            "red",
                            (initial.action_key, refresh.action_key),
                        ),
                        actor("target", "blue", ()),
                    ),
                    seed=3,
                )
                environment.step(
                    (choose(environment, initial.action_key, "initial"),)
                )
                result = environment.step(
                    (choose(environment, refresh.action_key, "refresh"),)
                )

                self.assertIn("marker.refreshed", environment.entity("target").tags)
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
                                            TagOperation.ADD,
                                        ),
                                    ),
                                    else_effects=(
                                        ModifyTag(
                                            SubjectRef.TARGET,
                                            "marker.blocked",
                                            TagOperation.ADD,
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

                self.assertIn("marker.blocked", environment.entity("target").tags)
                self.assertNotIn("marker.applied", environment.entity("target").tags)

            def test_generic_immunity_tags_block_non_stun_effects(self) -> None:
                action = ActionSpec(
                    action_key="generic-immunity",
                    targeting=hostile_targeting(),
                    phases=(
                        ActionPhase(
                            PhaseKind.ACTIVE,
                            0,
                            effects=(
                                OutcomeConditional(
                                    conditional_key="root",
                                    condition=ApplyEffect(
                                        subject=SubjectRef.TARGET,
                                        effect_key="effect.root",
                                        duration_ms=1_000,
                                        tags=("control.root",),
                                        immunity_tags=("immunity.root",),
                                    ),
                                    outcomes=(EffectOutcomeKind.BLOCKED_IMMUNITY,),
                                    effects=(
                                        ModifyTag(
                                            SubjectRef.TARGET,
                                            "marker.root-blocked",
                                            TagOperation.ADD,
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
                        actor("target", "blue", (), tags=("immunity.root",)),
                    ),
                    seed=5,
                )

                environment.step((choose(environment, action.action_key, "cast"),))

                target = environment.entity("target")
                self.assertNotIn("effect.root", target.effects)
                self.assertIn("marker.root-blocked", target.tags)

            def test_conditional_grammar_rejects_duplicate_outcomes(self) -> None:
                with self.assertRaisesRegex(ValueError, "duplicates"):
                    OutcomeConditional(
                        conditional_key="bad",
                        condition=stun_condition(),
                        outcomes=(
                            EffectOutcomeKind.APPLIED,
                            EffectOutcomeKind.APPLIED,
                        ),
                        effects=(
                            ModifyTag(
                                SubjectRef.TARGET,
                                "marker",
                                TagOperation.ADD,
                            ),
                        ),
                    )


        if __name__ == "__main__":
            unittest.main()
        '''
    ),
    encoding="utf-8",
)
