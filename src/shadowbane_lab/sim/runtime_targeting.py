"""Runtime bridge from simulator state to one shared affiliation target resolver."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from shadowbane_lab.protocol import Relation, Vector2
from shadowbane_lab.sim.actions import ActionSpec, AreaEffect
from shadowbane_lab.sim.affiliation_io import affiliation_snapshot_digest
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    DefaultRelationPolicy,
    RelationPolicy,
    RelationResolver,
    legacy_team_affiliations,
)
from shadowbane_lab.sim.errors import SimulationConfigurationError
from shadowbane_lab.sim.state import EntityState
from shadowbane_lab.sim.targeting import (
    TargetCandidate,
    TargetOrder,
    TargetResolution,
    TargetResolver,
    TargetSelectorSpec,
    VisibilityRequirement,
)

LineOfSightProvider = Callable[[EntityState, EntityState], bool | None]


@dataclass(frozen=True, slots=True)
class AffiliationTargetConstraints:
    """Exact affiliation predicates layered onto an action's existing target shape."""

    require_same_party: bool = False
    forbid_same_party: bool = False
    require_same_guild: bool = False
    forbid_same_guild: bool = False
    require_same_nation: bool = False
    forbid_same_nation: bool = False
    require_same_scenario_side: bool = False
    forbid_same_scenario_side: bool = False
    require_opposing_scenario_side: bool = False
    forbid_opposing_scenario_side: bool = False
    require_actor_owns_target: bool = False
    require_target_owns_actor: bool = False
    require_same_owner: bool = False
    forbid_same_owner: bool = False
    require_same_ownership_family: bool = False
    forbid_same_ownership_family: bool = False

    def __post_init__(self) -> None:
        # Reuse the authoritative selector validation rather than duplicating its
        # contradiction matrix in this adapter contract.
        self.apply(TargetSelectorSpec())

    def apply(self, selector: TargetSelectorSpec) -> TargetSelectorSpec:
        if not isinstance(selector, TargetSelectorSpec):
            raise ValueError("selector must be a TargetSelectorSpec")
        return replace(
            selector,
            require_same_party=self.require_same_party,
            forbid_same_party=self.forbid_same_party,
            require_same_guild=self.require_same_guild,
            forbid_same_guild=self.forbid_same_guild,
            require_same_nation=self.require_same_nation,
            forbid_same_nation=self.forbid_same_nation,
            require_same_scenario_side=self.require_same_scenario_side,
            forbid_same_scenario_side=self.forbid_same_scenario_side,
            require_opposing_scenario_side=self.require_opposing_scenario_side,
            forbid_opposing_scenario_side=self.forbid_opposing_scenario_side,
            require_actor_owns_target=self.require_actor_owns_target,
            require_target_owns_actor=self.require_target_owns_actor,
            require_same_owner=self.require_same_owner,
            forbid_same_owner=self.forbid_same_owner,
            require_same_ownership_family=self.require_same_ownership_family,
            forbid_same_ownership_family=self.forbid_same_ownership_family,
        )


@dataclass(frozen=True, slots=True)
class RuntimeTargetingProfile:
    """Ruleset-owned exact predicates keyed by compiled action identity."""

    action_constraints: tuple[tuple[str, AffiliationTargetConstraints], ...] = ()
    area_constraints: tuple[tuple[str, AffiliationTargetConstraints], ...] = ()

    def __post_init__(self) -> None:
        for values, field_name in (
            (self.action_constraints, "action_constraints"),
            (self.area_constraints, "area_constraints"),
        ):
            if not isinstance(values, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            keys = tuple(key for key, _ in values)
            if len(keys) != len(set(keys)):
                raise ValueError(f"{field_name} action keys must be unique")
            for key, constraints in values:
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(f"{field_name} action keys must be non-empty strings")
                if not isinstance(constraints, AffiliationTargetConstraints):
                    raise ValueError(f"{field_name} values must be AffiliationTargetConstraints")

    def constraints_for_action(self, action_key: str) -> AffiliationTargetConstraints:
        return dict(self.action_constraints).get(action_key, AffiliationTargetConstraints())

    def constraints_for_area(self, action_key: str) -> AffiliationTargetConstraints:
        return dict(self.area_constraints).get(action_key, AffiliationTargetConstraints())


class RuntimeTargetingContext:
    """Immutable affiliation authority shared by affordances and effect resolution."""

    def __init__(
        self,
        snapshot: AffiliationSnapshot,
        *,
        relation_policy: RelationPolicy | None = None,
        profile: RuntimeTargetingProfile | None = None,
        line_of_sight_provider: LineOfSightProvider | None = None,
    ) -> None:
        if not isinstance(snapshot, AffiliationSnapshot):
            raise ValueError("snapshot must be an AffiliationSnapshot")
        if profile is not None and not isinstance(profile, RuntimeTargetingProfile):
            raise ValueError("profile must be a RuntimeTargetingProfile or null")
        if line_of_sight_provider is not None and not callable(line_of_sight_provider):
            raise ValueError("line_of_sight_provider must be callable or null")
        self._snapshot = snapshot
        self._relation_policy = (
            DefaultRelationPolicy() if relation_policy is None else relation_policy
        )
        self._relations = RelationResolver(snapshot)
        self._resolver = TargetResolver(self._relations, self._relation_policy)
        self._profile = RuntimeTargetingProfile() if profile is None else profile
        self._line_of_sight_provider = line_of_sight_provider
        self._digest = affiliation_snapshot_digest(snapshot)

    @classmethod
    def from_legacy_entities(
        cls,
        entities: Iterable[EntityState],
        *,
        relation_policy: RelationPolicy | None = None,
        profile: RuntimeTargetingProfile | None = None,
        line_of_sight_provider: LineOfSightProvider | None = None,
    ) -> RuntimeTargetingContext:
        materialized = tuple(entities)
        snapshot = legacy_team_affiliations(
            {entity.entity_id: entity.team_id for entity in materialized},
            revision=0,
        )
        return cls(
            snapshot,
            relation_policy=relation_policy,
            profile=profile,
            line_of_sight_provider=line_of_sight_provider,
        )

    @property
    def snapshot(self) -> AffiliationSnapshot:
        return self._snapshot

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def revision(self) -> int:
        return self._snapshot.revision

    @property
    def profile(self) -> RuntimeTargetingProfile:
        return self._profile

    def validate_entities(self, entities: Iterable[EntityState]) -> None:
        entity_ids = {entity.entity_id for entity in entities}
        unknown = set(self._snapshot.entity_ids) - entity_ids
        if unknown:
            raise SimulationConfigurationError(
                "affiliation snapshot references unknown entities: " + ", ".join(sorted(unknown))
            )

    def coarse_relation(self, left_entity_id: str, right_entity_id: str) -> Relation:
        return self._relations.coarse_relation(
            left_entity_id,
            right_entity_id,
            self._relation_policy,
        )

    def selector_for_action(self, action: ActionSpec) -> TargetSelectorSpec:
        base = TargetSelectorSpec(
            allowed_relations=action.targeting.allowed_relations,
            minimum_range=action.targeting.minimum_range,
            maximum_range=action.targeting.maximum_range,
            requires_line_of_sight=action.targeting.requires_line_of_sight,
            order=TargetOrder.ENTITY_ID,
        )
        return self._profile.constraints_for_action(action.action_key).apply(base)

    def selector_for_area(self, action_key: str, effect: AreaEffect) -> TargetSelectorSpec:
        base = TargetSelectorSpec(
            allowed_relations=effect.allowed_relations,
            visibility_requirement=VisibilityRequirement.ANY,
            maximum_range=effect.radius,
            maximum_targets=effect.maximum_targets,
            order=TargetOrder.DISTANCE_THEN_ENTITY_ID,
        )
        return self._profile.constraints_for_area(action_key).apply(base)

    def resolve_action(
        self,
        actor: EntityState,
        entities: Iterable[EntityState],
        action: ActionSpec,
    ) -> TargetResolution:
        selector = self.selector_for_action(action)
        candidates = self._candidates(actor, tuple(entities), selector)
        return self._resolver.resolve(
            self._candidate(actor, actor, selector, position=actor.position),
            candidates,
            selector,
        )

    def resolve_area(
        self,
        actor: EntityState,
        entities: Iterable[EntityState],
        *,
        action_key: str,
        effect: AreaEffect,
        center: Vector2,
        eligible_alive: frozenset[str],
    ) -> TargetResolution:
        selector = self.selector_for_area(action_key, effect)
        materialized = tuple(entities)
        candidates = self._candidates(
            actor,
            materialized,
            selector,
            eligible_alive=eligible_alive,
        )
        origin = self._candidate(actor, actor, selector, position=center)
        return self._resolver.resolve(origin, candidates, selector)

    def _candidates(
        self,
        actor: EntityState,
        entities: tuple[EntityState, ...],
        selector: TargetSelectorSpec,
        *,
        eligible_alive: frozenset[str] | None = None,
    ) -> tuple[TargetCandidate, ...]:
        return tuple(
            self._candidate(
                actor,
                entity,
                selector,
                alive=(
                    entity.alive
                    and (eligible_alive is None or entity.entity_id in eligible_alive)
                ),
            )
            for entity in entities
        )

    def _candidate(
        self,
        actor: EntityState,
        entity: EntityState,
        selector: TargetSelectorSpec,
        *,
        position: Vector2 | None = None,
        alive: bool | None = None,
    ) -> TargetCandidate:
        return TargetCandidate(
            entity_id=entity.entity_id,
            kind=entity.kind,
            position=entity.position if position is None else position,
            alive=entity.alive if alive is None else alive,
            visible_to_actor=self._can_observe(actor, entity),
            line_of_sight=self._line_of_sight(actor, entity, selector),
        )

    def _line_of_sight(
        self,
        actor: EntityState,
        target: EntityState,
        selector: TargetSelectorSpec,
    ) -> bool:
        if not selector.requires_line_of_sight or actor.entity_id == target.entity_id:
            return True
        if self._line_of_sight_provider is None:
            return False
        result = self._line_of_sight_provider(actor, target)
        if result is None:
            return False
        if not isinstance(result, bool):
            raise SimulationConfigurationError("line_of_sight_provider must return boolean or null")
        return result

    @staticmethod
    def _can_observe(actor: EntityState, target: EntityState) -> bool:
        return (
            target.entity_id == actor.entity_id
            or "visibility.invisible" not in target.effective_tags
            or "detection.see_invisible" in actor.effective_tags
        )


__all__ = (
    "AffiliationTargetConstraints",
    "LineOfSightProvider",
    "RuntimeTargetingContext",
    "RuntimeTargetingProfile",
)
