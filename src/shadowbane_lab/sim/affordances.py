"""Observation projection and legal semantic affordance generation."""

from __future__ import annotations

from math import hypot

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
from shadowbane_lab.sim.actions import ActionCatalog, ActionSpec, ModifyObjective, TransferItem
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
        return all(
            actor.scalars.get(cost.resource_key, 0.0) >= cost.amount for cost in action.costs
        )

    def _observe_entity(self, actor: EntityState, entity: EntityState) -> EntityObservation:
        return EntityObservation(
            entity_id=entity.entity_id,
            kind=entity.kind,
            relation=self._relation(actor, entity),
            position=entity.position,
            velocity=entity.velocity,
            scalars=tuple(
                NamedScalar(name, entity.effective_scalar(name))
                for name in sorted(entity.scalars)
            ),
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
        return tuple(NamedScalar(name, values[name]) for name in sorted(values))

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
