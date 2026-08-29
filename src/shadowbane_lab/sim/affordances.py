"""Observation projection and legal semantic affordance generation."""

from __future__ import annotations

from math import hypot

from shadowbane_lab.combat import melee_hit_chance_percent, power_hit_chance_percent
from shadowbane_lab.protocol import (
    ActionBinding,
    Affordance,
    AffordanceSetMessage,
    EntityKind,
    EntityObservation,
    NamedScalar,
    ObservationMessage,
    Relation,
    TargetKind,
    Vector2,
)
from shadowbane_lab.sim.actions import (
    ActionCatalog,
    ActionSpec,
    ApplyEffect,
    AreaEffect,
    AttackGate,
    AttackKind,
    DealDamage,
    ModifyObjective,
    TransferItem,
)
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.state import EntityState
from shadowbane_lab.sim.timeline import AgentExchange

_ACTION_BLOCKING_TAGS = frozenset({"control.stun"})


class AffordanceBuilder:
    """Builds one agent's policy-facing view from authoritative simulation state."""

    def __init__(
        self,
        catalog: ActionCatalog,
        entities: dict[str, EntityState],
        *,
        tick: int,
        now_ms: int,
        direction_candidates: tuple[Vector2, ...],
        position_candidates: tuple[Vector2, ...],
    ) -> None:
        self._catalog = catalog
        self._entities = entities
        self._tick = tick
        self._now_ms = now_ms
        self._direction_candidates = direction_candidates
        self._position_candidates = position_candidates

    def exchange(self, agent_id: str) -> AgentExchange:
        actor = self._entity(agent_id)
        observation_id = f"observation:{self._tick}:{agent_id}"
        entities = tuple(
            self._observe_entity(actor, self._entities[entity_id])
            for entity_id in sorted(self._entities)
            if self._entities[entity_id].alive or entity_id == agent_id
            if self._can_observe(actor, self._entities[entity_id])
        )
        observation = ObservationMessage(
            message_id=f"message:{observation_id}",
            observation_id=observation_id,
            agent_id=agent_id,
            life_id=actor.life_id,
            tick=self._tick,
            sim_time_ms=self._now_ms,
            entities=entities,
            active=actor.alive,
        )
        affordances = self._build_affordances(observation, actor)
        return AgentExchange(observation=observation, affordances=affordances)

    def _build_affordances(
        self,
        observation: ObservationMessage,
        actor: EntityState,
    ) -> AffordanceSetMessage:
        affordances: list[Affordance] = []
        if (
            actor.alive
            and actor.busy_until_ms <= self._now_ms
            and not (_ACTION_BLOCKING_TAGS & actor.effective_tags)
        ):
            for action_key in sorted(actor.action_keys):
                action = self._catalog.get(action_key)
                if not self._actor_can_start(actor, action):
                    continue
                for binding in self._bindings(actor, action):
                    affordances.append(
                        Affordance(
                            affordance_id=(
                                f"affordance:{self._tick}:{actor.entity_id}:{len(affordances):04d}"
                            ),
                            action_key=action.action_key,
                            binding=binding,
                            features=self._affordance_features(actor, action, binding),
                            tags=action.tags,
                        )
                    )
        return AffordanceSetMessage(
            message_id=f"message:affordances:{self._tick}:{actor.entity_id}",
            observation_id=observation.observation_id,
            agent_id=actor.entity_id,
            tick=self._tick,
            affordances=tuple(affordances),
        )

    def _bindings(self, actor: EntityState, action: ActionSpec) -> tuple[ActionBinding, ...]:
        kind = action.targeting.kind
        if kind is TargetKind.NONE:
            return (ActionBinding(actor_id=actor.entity_id),)
        if kind is TargetKind.SELF:
            return (ActionBinding(actor_id=actor.entity_id, target_kind=TargetKind.SELF),)
        if kind is TargetKind.DIRECTION:
            return tuple(
                ActionBinding(
                    actor_id=actor.entity_id,
                    target_kind=TargetKind.DIRECTION,
                    direction=direction,
                )
                for direction in self._direction_candidates
            )
        if kind is TargetKind.POSITION:
            return tuple(
                ActionBinding(
                    actor_id=actor.entity_id,
                    target_kind=TargetKind.POSITION,
                    position=position,
                )
                for position in self._position_candidates
                if self._position_in_range(actor.position, position, action)
            )
        return self._entity_bindings(actor, action)

    def _entity_bindings(
        self,
        actor: EntityState,
        action: ActionSpec,
    ) -> tuple[ActionBinding, ...]:
        bindings: list[ActionBinding] = []
        transfer = self._transfer_effect(action)
        modifies_objective = any(
            isinstance(effect, ModifyObjective)
            for phase in action.phases
            for effect in phase.effects
        )
        for target_id in sorted(self._entities):
            target = self._entities[target_id]
            if not target.alive:
                continue
            if self._relation(actor, target) not in action.targeting.allowed_relations:
                continue
            if not self._can_observe(actor, target):
                continue
            if not self._position_in_range(actor.position, target.position, action):
                continue
            if modifies_objective and target.kind is not EntityKind.OBJECTIVE:
                continue
            if transfer is None:
                bindings.append(
                    ActionBinding(
                        actor_id=actor.entity_id,
                        target_kind=TargetKind.ENTITY,
                        target_entity_id=target.entity_id,
                        objective_id=target.entity_id if modifies_objective else None,
                    )
                )
                continue
            bindings.extend(self._transfer_bindings(actor, target, transfer))
        return tuple(bindings)

    @staticmethod
    def _transfer_bindings(
        actor: EntityState,
        target: EntityState,
        transfer: TransferItem,
    ) -> tuple[ActionBinding, ...]:
        bindings: list[ActionBinding] = []
        item_ids = (
            (transfer.item_id,)
            if transfer.item_id is not None
            else tuple(sorted(item for item, amount in actor.inventory.items() if amount > 0))
        )
        for item_id in item_ids:
            if item_id is None:
                continue
            available = actor.inventory.get(item_id, 0.0)
            quantity = transfer.quantity if transfer.quantity is not None else available
            if quantity <= 0 or quantity > available:
                continue
            bindings.append(
                ActionBinding(
                    actor_id=actor.entity_id,
                    target_kind=TargetKind.ENTITY,
                    target_entity_id=target.entity_id,
                    quantity=quantity,
                    item_id=item_id,
                )
            )
        return tuple(bindings)

    def _actor_can_start(self, actor: EntityState, action: ActionSpec) -> bool:
        if actor.cooldowns.get(action.action_key, 0) > self._now_ms:
            return False
        tags = actor.effective_tags
        if not set(action.required_actor_tags).issubset(tags):
            return False
        if set(action.forbidden_actor_tags) & tags:
            return False
        if "control.silence" in tags and "power" in action.tags:
            return False
        return all(
            actor.scalars.get(cost.resource_key, 0.0) >= cost.amount for cost in action.costs
        )

    def _observe_entity(self, actor: EntityState, entity: EntityState) -> EntityObservation:
        scalars = {name: entity.effective_scalar(name) for name in sorted(entity.scalars)}
        blocking_prefix = "resource.restore.block."
        for effect in entity.effects.values():
            for tag in effect.tags:
                if not tag.startswith(blocking_prefix):
                    continue
                resource_key = tag.removeprefix(blocking_prefix)
                if not resource_key:
                    continue
                scalar_key = f"restore_block_rank.{resource_key}"
                existing = scalars.get(scalar_key)
                if existing is None or effect.magnitude > existing:
                    scalars[scalar_key] = effect.magnitude
        return EntityObservation(
            entity_id=entity.entity_id,
            kind=entity.kind,
            relation=self._relation(actor, entity),
            position=entity.position,
            velocity=entity.velocity,
            scalars=tuple(NamedScalar(name, value) for name, value in sorted(scalars.items())),
            tags=tuple(sorted(entity.effective_tags)),
        )

    def _affordance_features(
        self,
        actor: EntityState,
        action: ActionSpec,
        binding: ActionBinding,
    ) -> tuple[NamedScalar, ...]:
        values = {
            "commitment_ms": float(sum(phase.duration_ms for phase in action.phases)),
            "cooldown_ms": float(action.cooldown_ms),
        }
        for cost in action.costs:
            values[f"cost.{cost.resource_key}"] = cost.amount
        if binding.target_entity_id is not None:
            target = self._entities[binding.target_entity_id]
            values["distance"] = self._distance(actor.position, target.position)
        for feature in action.features:
            values[feature.name] = feature.value
        active_triggers = tuple(
            trigger
            for active in actor.effects.values()
            if (trigger := self._catalog.trigger_for_effect(active.effect_key)) is not None
            and trigger.matches(action.action_key, frozenset(action.tags))
        )
        if action.weapon_attack is not None:
            attack = action.weapon_attack
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
            values["expected_damage"] = (minimum + maximum) / 2.0
            if binding.target_entity_id is not None:
                target = self._entities[binding.target_entity_id]
                attack_rating = self._scalar_or_default(
                    actor,
                    attack.attack_rating_scalar,
                    attack.default_attack_rating,
                )
                defense = self._scalar_or_default(
                    target,
                    attack.defense_scalar,
                    attack.default_defense,
                )
                values["expected_hit_chance"] = attack.hit_chance(attack_rating, defense)
        elif binding.target_entity_id is not None:
            attack_gate = next(self._attack_gates(action), None)
            if attack_gate is not None:
                target = self._entities[binding.target_entity_id]
                modifiers = tuple(
                    trigger.attack_modifier
                    for trigger in active_triggers
                    if trigger.attack_modifier is not None
                )
                attack_rating = self._scalar_or_default(
                    actor,
                    attack_gate.attack_rating_key,
                    0.0,
                ) + sum(modifier.attack_rating_bonus for modifier in modifiers)
                defense = self._scalar_or_default(
                    target,
                    attack_gate.defense_rating_key,
                    0.0,
                )
                bypass = any(modifier.bypass_defense for modifier in modifiers)
                chance_percent = (
                    100
                    if bypass
                    else melee_hit_chance_percent(attack_rating, defense)
                    if attack_gate.kind is AttackKind.BASIC
                    else power_hit_chance_percent(attack_rating, defense)
                )
                values["expected_hit_chance"] = chance_percent / 100.0
        trigger_damage = 0.0
        trigger_control_ms = 0.0
        trigger_count = 0
        for trigger in active_triggers:
            trigger_count += 1
            if trigger.attack_modifier is not None:
                modifier = trigger.attack_modifier
                trigger_damage += (
                    modifier.bonus_damage_minimum + modifier.bonus_damage_maximum
                ) / 2.0
            for effect in trigger.payload:
                if isinstance(effect, DealDamage):
                    trigger_damage += (
                        float(effect.amount)
                        if isinstance(effect.amount, (int, float))
                        else effect.amount.expected
                    )
                elif isinstance(effect, ApplyEffect) and any(
                    tag.startswith("control.") for tag in effect.tags
                ):
                    trigger_control_ms += effect.duration_ms
        if trigger_count:
            values["trigger_count"] = float(trigger_count)
        if trigger_damage:
            values["trigger_expected_damage"] = trigger_damage
        if trigger_control_ms:
            values["trigger_control_duration_ms"] = trigger_control_ms
        return tuple(NamedScalar(name, values[name]) for name in sorted(values))

    @staticmethod
    def _attack_gates(action: ActionSpec):
        for phase in action.phases:
            for effect in phase.effects:
                if isinstance(effect, AttackGate):
                    yield effect
                elif isinstance(effect, AreaEffect):
                    yield from (
                        nested for nested in effect.effects if isinstance(nested, AttackGate)
                    )

    def _position_in_range(
        self,
        actor_position: Vector2,
        target_position: Vector2,
        action: ActionSpec,
    ) -> bool:
        distance = self._distance(actor_position, target_position)
        if distance < action.targeting.minimum_range:
            return False
        maximum = action.targeting.maximum_range
        return maximum is None or distance <= maximum

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
    def _can_observe(actor: EntityState, target: EntityState) -> bool:
        return (
            target.entity_id == actor.entity_id
            or "visibility.invisible" not in target.effective_tags
            or "detection.see_invisible" in actor.effective_tags
        )

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

    @staticmethod
    def _distance(left: Vector2, right: Vector2) -> float:
        return hypot(left.x - right.x, left.y - right.y)

    @staticmethod
    def _transfer_effect(action: ActionSpec) -> TransferItem | None:
        transfers = tuple(
            effect
            for phase in action.phases
            for effect in phase.effects
            if isinstance(effect, TransferItem)
        )
        if len(transfers) > 1:
            raise SimulationConfigurationError("one action cannot contain multiple item transfers")
        return transfers[0] if transfers else None

    def _entity(self, entity_id: str) -> EntityState:
        try:
            return self._entities[entity_id]
        except KeyError as exc:
            raise KeyError(f"unknown entity id: {entity_id}") from exc
