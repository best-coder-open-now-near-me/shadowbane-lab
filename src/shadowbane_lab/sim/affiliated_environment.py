"""Reference environment wired to one affiliation-aware target authority."""

from __future__ import annotations

from dataclasses import dataclass, replace

from shadowbane_lab.protocol import ActionBinding, EntityKind, TargetKind, Vector2
from shadowbane_lab.sim.actions import (
    ActionCatalog,
    ActionSpec,
    AreaEffect,
    AttackGate,
    ChanceGate,
    ModifyObjective,
    OutcomeConditional,
)
from shadowbane_lab.sim.affiliations import AffiliationSnapshot, RelationPolicy
from shadowbane_lab.sim.affordances import AffordanceBuilder
from shadowbane_lab.sim.effects import EffectExecutor
from shadowbane_lab.sim.environment import ReferenceEnvironment
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.random_source import DeterministicRandom
from shadowbane_lab.sim.runtime_targeting import (
    LineOfSightProvider,
    RuntimeTargetingContext,
    RuntimeTargetingProfile,
)
from shadowbane_lab.sim.state import EntityState
from shadowbane_lab.sim.targeting import TargetResolution
from shadowbane_lab.sim.timeline import (
    AgentExchange,
    EnvironmentSnapshot,
    ScheduledItem,
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


class AffiliatedAffordanceBuilder(AffordanceBuilder):
    """Build direct entity bindings through the shared runtime resolver."""

    def __init__(
        self,
        catalog: ActionCatalog,
        entities: dict[str, EntityState],
        targeting: RuntimeTargetingContext,
        *,
        tick: int,
        now_ms: int,
        direction_candidates: tuple[Vector2, ...],
        position_candidates: tuple[Vector2, ...],
    ) -> None:
        super().__init__(
            catalog,
            entities,
            tick=tick,
            now_ms=now_ms,
            direction_candidates=direction_candidates,
            position_candidates=position_candidates,
        )
        self._targeting_context = targeting

    def _bindings(self, actor: EntityState, action: ActionSpec) -> tuple[ActionBinding, ...]:
        if action.targeting.kind is TargetKind.POSITION and action.targeting.requires_line_of_sight:
            # Point LOS has no calibrated provider yet. Do not silently accept it.
            return ()
        return super()._bindings(actor, action)

    def _entity_bindings(
        self,
        actor: EntityState,
        action: ActionSpec,
    ) -> tuple[ActionBinding, ...]:
        resolution = self._targeting_context.resolve_action(
            actor,
            self._entities.values(),
            action,
        )
        bindings: list[ActionBinding] = []
        transfer = self._transfer_effect(action)
        modifies_objective = any(
            isinstance(effect, ModifyObjective)
            for phase in action.phases
            for effect in phase.effects
        )
        for decision in resolution.accepted:
            target = self._entities[decision.entity_id]
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

    def _relation(self, actor: EntityState, target: EntityState):
        return self._targeting_context.coarse_relation(
            actor.entity_id,
            target.entity_id,
        )


class AffiliatedEffectExecutor(EffectExecutor):
    """Resolve area target sets through the same authority as direct affordances."""

    def __init__(
        self,
        entities: dict[str, EntityState],
        event_factory,
        schedule,
        take_schedule_order,
        catalog: ActionCatalog,
        random: DeterministicRandom,
        interrupt_actor,
        targeting: RuntimeTargetingContext,
    ) -> None:
        super().__init__(
            entities,
            event_factory,
            schedule,
            take_schedule_order,
            catalog,
            random,
            interrupt_actor,
        )
        self._targeting_context = targeting

    def _resolve_area(
        self,
        item: ScheduledItem,
        effect: AreaEffect,
        due_time: int,
        eligible_alive: frozenset[str],
        events: list,
    ) -> None:
        if item.binding is None:
            raise SimulationConfigurationError("area resolution requires an action binding")
        actor = self._entity(item.actor_id)
        if actor.entity_id not in eligible_alive:
            return
        center = self._area_center(effect, item.binding)
        resolution = self._targeting_context.resolve_area(
            actor,
            self._entities.values(),
            action_key=item.action_key,
            effect=effect,
            center=center,
            eligible_alive=eligible_alive,
        )
        for decision in resolution.accepted:
            target = self._entities[decision.entity_id]
            target_item = replace(
                item,
                binding=ActionBinding(
                    actor_id=item.binding.actor_id,
                    target_kind=TargetKind.ENTITY,
                    target_entity_id=target.entity_id,
                ),
                target_life_id=target.life_id,
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


@dataclass(frozen=True, slots=True)
class AffiliatedEnvironmentSnapshot:
    """Replay state bound to the immutable affiliation input that produced it."""

    environment: EnvironmentSnapshot
    affiliation_digest: str
    affiliation_revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.environment, EnvironmentSnapshot):
            raise ValueError("environment must be an EnvironmentSnapshot")
        if not isinstance(self.affiliation_digest, str) or len(self.affiliation_digest) != 64:
            raise ValueError("affiliation_digest must be a SHA-256 hex digest")
        try:
            int(self.affiliation_digest, 16)
        except ValueError as exc:
            raise ValueError("affiliation_digest must be a SHA-256 hex digest") from exc
        if (
            isinstance(self.affiliation_revision, bool)
            or not isinstance(self.affiliation_revision, int)
            or self.affiliation_revision < 0
        ):
            raise ValueError("affiliation_revision must be a non-negative integer")


class AffiliatedReferenceEnvironment(ReferenceEnvironment):
    """Lifecycle reference world with frozen affiliation-aware target semantics."""

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
        targeting_context: RuntimeTargetingContext | None = None,
        affiliation_snapshot: AffiliationSnapshot | None = None,
        relation_policy: RelationPolicy | None = None,
        targeting_profile: RuntimeTargetingProfile | None = None,
        line_of_sight_provider: LineOfSightProvider | None = None,
    ) -> None:
        if targeting_context is not None and any(
            value is not None
            for value in (
                affiliation_snapshot,
                relation_policy,
                targeting_profile,
                line_of_sight_provider,
            )
        ):
            raise SimulationConfigurationError(
                "targeting_context cannot be combined with targeting construction inputs"
            )
        if targeting_context is None:
            targeting_context = (
                RuntimeTargetingContext.from_legacy_entities(
                    entities,
                    relation_policy=relation_policy,
                    profile=targeting_profile,
                    line_of_sight_provider=line_of_sight_provider,
                )
                if affiliation_snapshot is None
                else RuntimeTargetingContext(
                    affiliation_snapshot,
                    relation_policy=relation_policy,
                    profile=targeting_profile,
                    line_of_sight_provider=line_of_sight_provider,
                )
            )
        if not isinstance(targeting_context, RuntimeTargetingContext):
            raise SimulationConfigurationError(
                "targeting_context must be a RuntimeTargetingContext"
            )
        targeting_context.validate_entities(entities)
        self._targeting_context = targeting_context
        super().__init__(
            catalog,
            entities,
            seed=seed,
            tick_duration_ms=tick_duration_ms,
            direction_candidates=direction_candidates,
            position_candidates=position_candidates,
            terminate_on_last_team=terminate_on_last_team,
        )

    @property
    def targeting_context(self) -> RuntimeTargetingContext:
        return self._targeting_context

    @property
    def affiliation_snapshot(self) -> AffiliationSnapshot:
        return self._targeting_context.snapshot

    @property
    def affiliation_digest(self) -> str:
        return self._targeting_context.digest

    @property
    def affiliation_revision(self) -> int:
        return self._targeting_context.revision

    def exchange(self, agent_id: str) -> AgentExchange:
        return AffiliatedAffordanceBuilder(
            self._catalog,
            self._entities,
            self._targeting_context,
            tick=self.tick,
            now_ms=self.now_ms,
            direction_candidates=self._direction_candidates,
            position_candidates=self._position_candidates,
        ).exchange(agent_id)

    def resolve_targets(self, agent_id: str, action_key: str) -> TargetResolution:
        actor = self._entity(agent_id)
        action = self._catalog.get(action_key)
        return self._targeting_context.resolve_action(
            actor,
            self._entities.values(),
            action,
        )

    def snapshot(self) -> AffiliatedEnvironmentSnapshot:
        return AffiliatedEnvironmentSnapshot(
            environment=super().snapshot(),
            affiliation_digest=self._targeting_context.digest,
            affiliation_revision=self._targeting_context.revision,
        )

    def restore(self, snapshot: AffiliatedEnvironmentSnapshot) -> None:
        if not isinstance(snapshot, AffiliatedEnvironmentSnapshot):
            raise SimulationConfigurationError(
                "affiliated environment restore requires AffiliatedEnvironmentSnapshot"
            )
        if snapshot.affiliation_digest != self._targeting_context.digest:
            raise SimulationConfigurationError(
                "snapshot affiliation digest does not match this environment"
            )
        if snapshot.affiliation_revision != self._targeting_context.revision:
            raise SimulationConfigurationError(
                "snapshot affiliation revision does not match this environment"
            )
        super().restore(snapshot.environment)

    def _create_effect_executor(self) -> EffectExecutor:
        return AffiliatedEffectExecutor(
            self._entities,
            self._event,
            self._schedule,
            self._take_schedule_order,
            self._catalog,
            self._random,
            self._interrupt_actor,
            self._targeting_context,
        )


__all__ = (
    "AffiliatedAffordanceBuilder",
    "AffiliatedEffectExecutor",
    "AffiliatedEnvironmentSnapshot",
    "AffiliatedReferenceEnvironment",
)
