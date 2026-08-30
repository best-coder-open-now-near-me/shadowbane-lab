"""Standalone target selection over exact affiliation facts and spatial candidates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from math import hypot, isfinite

from shadowbane_lab.protocol import EntityKind, Relation, Vector2
from shadowbane_lab.sim.affiliations import (
    DefaultRelationPolicy,
    RelationFacts,
    RelationPolicy,
    RelationResolver,
)


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


class AliveRequirement(StrEnum):
    ANY = "any"
    ALIVE = "alive"
    DEAD = "dead"


class VisibilityRequirement(StrEnum):
    ANY = "any"
    VISIBLE = "visible"


class TargetOrder(StrEnum):
    ENTITY_ID = "entity_id"
    DISTANCE_THEN_ENTITY_ID = "distance_then_entity_id"


@dataclass(frozen=True, slots=True)
class TargetSelectorSpec:
    """Source-independent target constraints owned by a compiled ability recipe."""

    entity_kinds: tuple[EntityKind, ...] = ()
    alive_requirement: AliveRequirement = AliveRequirement.ALIVE
    allowed_relations: tuple[Relation, ...] = ()
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
    visibility_requirement: VisibilityRequirement = VisibilityRequirement.VISIBLE
    minimum_range: float = 0.0
    maximum_range: float | None = None
    requires_line_of_sight: bool = False
    maximum_targets: int | None = None
    order: TargetOrder = TargetOrder.ENTITY_ID

    def __post_init__(self) -> None:
        if len(self.entity_kinds) != len(set(self.entity_kinds)):
            raise ValueError("entity_kinds must not contain duplicates")
        if any(not isinstance(kind, EntityKind) for kind in self.entity_kinds):
            raise ValueError("entity_kinds must contain EntityKind values")
        if not isinstance(self.alive_requirement, AliveRequirement):
            raise ValueError("alive_requirement must be an AliveRequirement")
        if len(self.allowed_relations) != len(set(self.allowed_relations)):
            raise ValueError("allowed_relations must not contain duplicates")
        if any(not isinstance(relation, Relation) for relation in self.allowed_relations):
            raise ValueError("allowed_relations must contain Relation values")
        if not isinstance(self.visibility_requirement, VisibilityRequirement):
            raise ValueError("visibility_requirement must be a VisibilityRequirement")
        if not isinstance(self.order, TargetOrder):
            raise ValueError("order must be a TargetOrder")
        if not isinstance(self.requires_line_of_sight, bool):
            raise ValueError("requires_line_of_sight must be boolean")

        paired_flags = (
            (self.require_same_party, self.forbid_same_party, "same_party"),
            (self.require_same_guild, self.forbid_same_guild, "same_guild"),
            (self.require_same_nation, self.forbid_same_nation, "same_nation"),
            (
                self.require_same_scenario_side,
                self.forbid_same_scenario_side,
                "same_scenario_side",
            ),
            (
                self.require_opposing_scenario_side,
                self.forbid_opposing_scenario_side,
                "opposing_scenario_side",
            ),
            (self.require_same_owner, self.forbid_same_owner, "same_owner"),
            (
                self.require_same_ownership_family,
                self.forbid_same_ownership_family,
                "same_ownership_family",
            ),
        )
        boolean_values = (
            *(value for required, forbidden, _ in paired_flags for value in (required, forbidden)),
            self.require_actor_owns_target,
            self.require_target_owns_actor,
        )
        if any(not isinstance(value, bool) for value in boolean_values):
            raise ValueError("target affiliation constraints must be boolean")
        for required, forbidden, name in paired_flags:
            if required and forbidden:
                raise ValueError(f"{name} cannot be both required and forbidden")
        if self.require_same_scenario_side and self.require_opposing_scenario_side:
            raise ValueError("a target cannot require both the same and an opposing scenario side")
        if self.require_actor_owns_target and self.require_target_owns_actor:
            raise ValueError("mutual ownership cannot be required")

        _finite(self.minimum_range, "minimum_range")
        if self.minimum_range < 0:
            raise ValueError("minimum_range must not be negative")
        if self.maximum_range is not None:
            _finite(self.maximum_range, "maximum_range")
            if self.maximum_range < self.minimum_range:
                raise ValueError("maximum_range must be at least minimum_range")
        if self.maximum_targets is not None and (
            isinstance(self.maximum_targets, bool)
            or not isinstance(self.maximum_targets, int)
            or self.maximum_targets < 1
        ):
            raise ValueError("maximum_targets must be a positive integer or null")


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    """One authoritative candidate projected for source-independent filtering."""

    entity_id: str
    kind: EntityKind
    position: Vector2
    alive: bool = True
    visible_to_actor: bool = True
    line_of_sight: bool = True

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "entity_id")
        if not isinstance(self.kind, EntityKind):
            raise ValueError("kind must be an EntityKind")
        if not isinstance(self.position, Vector2):
            raise ValueError("position must be a Vector2")
        if any(
            not isinstance(value, bool)
            for value in (self.alive, self.visible_to_actor, self.line_of_sight)
        ):
            raise ValueError("candidate state flags must be boolean")


@dataclass(frozen=True, slots=True)
class TargetDecision:
    """Accepted or rejected result for one considered candidate."""

    candidate: TargetCandidate
    accepted: bool
    relation_facts: RelationFacts
    coarse_relation: Relation
    distance: float
    exclusion_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, TargetCandidate):
            raise ValueError("candidate must be a TargetCandidate")
        if not isinstance(self.accepted, bool):
            raise ValueError("accepted must be boolean")
        if not isinstance(self.relation_facts, RelationFacts):
            raise ValueError("relation_facts must be RelationFacts")
        if not isinstance(self.coarse_relation, Relation):
            raise ValueError("coarse_relation must be a Relation")
        _finite(self.distance, "distance")
        if self.distance < 0:
            raise ValueError("distance must not be negative")
        if len(self.exclusion_reasons) != len(set(self.exclusion_reasons)):
            raise ValueError("exclusion_reasons must not contain duplicates")
        for reason in self.exclusion_reasons:
            _identifier(reason, "exclusion reason")
        if self.accepted == bool(self.exclusion_reasons):
            raise ValueError("accepted candidates must have no exclusion reasons")

    @property
    def entity_id(self) -> str:
        return self.candidate.entity_id


@dataclass(frozen=True, slots=True)
class TargetResolution:
    """Deterministic decision trace for every candidate considered by one selector."""

    actor_id: str
    affiliation_revision: int
    decisions: tuple[TargetDecision, ...]

    def __post_init__(self) -> None:
        _identifier(self.actor_id, "actor_id")
        if (
            isinstance(self.affiliation_revision, bool)
            or not isinstance(self.affiliation_revision, int)
            or self.affiliation_revision < 0
        ):
            raise ValueError("affiliation_revision must be a non-negative integer")
        if any(not isinstance(decision, TargetDecision) for decision in self.decisions):
            raise ValueError("decisions must contain TargetDecision values")
        entity_ids = tuple(decision.entity_id for decision in self.decisions)
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("decisions must contain unique candidate entity ids")

    @property
    def accepted(self) -> tuple[TargetDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.accepted)

    @property
    def accepted_entity_ids(self) -> tuple[str, ...]:
        return tuple(decision.entity_id for decision in self.accepted)

    @property
    def rejection_counts(self) -> tuple[tuple[str, int], ...]:
        counts = Counter(
            reason for decision in self.decisions for reason in decision.exclusion_reasons
        )
        return tuple(sorted(counts.items()))


class TargetResolver:
    """Filters, orders, and caps candidates through one shared relation resolver."""

    def __init__(
        self,
        relation_resolver: RelationResolver,
        relation_policy: RelationPolicy | None = None,
    ) -> None:
        if not isinstance(relation_resolver, RelationResolver):
            raise ValueError("relation_resolver must be a RelationResolver")
        self._relations = relation_resolver
        self._policy = DefaultRelationPolicy() if relation_policy is None else relation_policy

    def resolve(
        self,
        actor: TargetCandidate,
        candidates: tuple[TargetCandidate, ...],
        selector: TargetSelectorSpec,
    ) -> TargetResolution:
        if not isinstance(actor, TargetCandidate):
            raise ValueError("actor must be a TargetCandidate")
        if any(not isinstance(candidate, TargetCandidate) for candidate in candidates):
            raise ValueError("candidates must contain TargetCandidate values")
        if not isinstance(selector, TargetSelectorSpec):
            raise ValueError("selector must be a TargetSelectorSpec")
        candidate_ids = tuple(candidate.entity_id for candidate in candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate entity ids must be unique")

        ordered = tuple(
            sorted(
                candidates,
                key=lambda candidate: self._order_key(actor, candidate, selector.order),
            )
        )
        decisions: list[TargetDecision] = []
        accepted_count = 0
        for candidate in ordered:
            distance = self._distance(actor.position, candidate.position)
            facts = self._relations.facts_between(actor.entity_id, candidate.entity_id)
            coarse_relation = self._policy.coarse_relation(facts)
            reasons = list(
                self._exclusion_reasons(
                    candidate,
                    selector,
                    facts,
                    coarse_relation,
                    distance,
                )
            )
            if not reasons:
                if (
                    selector.maximum_targets is not None
                    and accepted_count >= selector.maximum_targets
                ):
                    reasons.append("target_cap_exceeded")
                else:
                    accepted_count += 1
            decisions.append(
                TargetDecision(
                    candidate=candidate,
                    accepted=not reasons,
                    relation_facts=facts,
                    coarse_relation=coarse_relation,
                    distance=distance,
                    exclusion_reasons=tuple(reasons),
                )
            )
        return TargetResolution(
            actor_id=actor.entity_id,
            affiliation_revision=self._relations.snapshot.revision,
            decisions=tuple(decisions),
        )

    @staticmethod
    def _exclusion_reasons(
        candidate: TargetCandidate,
        selector: TargetSelectorSpec,
        facts: RelationFacts,
        coarse_relation: Relation,
        distance: float,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if selector.entity_kinds and candidate.kind not in selector.entity_kinds:
            reasons.append("entity_kind_not_allowed")
        if selector.alive_requirement is AliveRequirement.ALIVE and not candidate.alive:
            reasons.append("target_not_alive")
        elif selector.alive_requirement is AliveRequirement.DEAD and candidate.alive:
            reasons.append("target_not_dead")

        TargetResolver._append_fact_constraint(
            reasons,
            facts.same_party,
            selector.require_same_party,
            selector.forbid_same_party,
            "not_same_party",
            "same_party_forbidden",
        )
        TargetResolver._append_fact_constraint(
            reasons,
            facts.same_guild,
            selector.require_same_guild,
            selector.forbid_same_guild,
            "not_same_guild",
            "same_guild_forbidden",
        )
        TargetResolver._append_fact_constraint(
            reasons,
            facts.same_nation,
            selector.require_same_nation,
            selector.forbid_same_nation,
            "not_same_nation",
            "same_nation_forbidden",
        )
        TargetResolver._append_fact_constraint(
            reasons,
            facts.same_scenario_side,
            selector.require_same_scenario_side,
            selector.forbid_same_scenario_side,
            "not_same_scenario_side",
            "same_scenario_side_forbidden",
        )
        TargetResolver._append_fact_constraint(
            reasons,
            facts.opposing_scenario_side,
            selector.require_opposing_scenario_side,
            selector.forbid_opposing_scenario_side,
            "not_opposing_scenario_side",
            "opposing_scenario_side_forbidden",
        )
        TargetResolver._append_fact_constraint(
            reasons,
            facts.same_owner,
            selector.require_same_owner,
            selector.forbid_same_owner,
            "not_same_owner",
            "same_owner_forbidden",
        )
        TargetResolver._append_fact_constraint(
            reasons,
            facts.same_ownership_family,
            selector.require_same_ownership_family,
            selector.forbid_same_ownership_family,
            "not_same_ownership_family",
            "same_ownership_family_forbidden",
        )
        if selector.require_actor_owns_target and not facts.left_owns_right:
            reasons.append("actor_does_not_own_target")
        if selector.require_target_owns_actor and not facts.right_owns_left:
            reasons.append("target_does_not_own_actor")

        if selector.allowed_relations and coarse_relation not in selector.allowed_relations:
            reasons.append("relation_not_allowed")
        if (
            selector.visibility_requirement is VisibilityRequirement.VISIBLE
            and not candidate.visible_to_actor
        ):
            reasons.append("not_visible")
        if distance < selector.minimum_range:
            reasons.append("below_minimum_range")
        if selector.maximum_range is not None and distance > selector.maximum_range:
            reasons.append("outside_maximum_range")
        if selector.requires_line_of_sight and not candidate.line_of_sight:
            reasons.append("line_of_sight_blocked")
        return tuple(reasons)

    @staticmethod
    def _append_fact_constraint(
        reasons: list[str],
        fact: bool,
        required: bool,
        forbidden: bool,
        missing_reason: str,
        forbidden_reason: str,
    ) -> None:
        if required and not fact:
            reasons.append(missing_reason)
        if forbidden and fact:
            reasons.append(forbidden_reason)

    @staticmethod
    def _order_key(
        actor: TargetCandidate,
        candidate: TargetCandidate,
        order: TargetOrder,
    ) -> tuple[object, ...]:
        if order is TargetOrder.DISTANCE_THEN_ENTITY_ID:
            return (
                TargetResolver._distance(actor.position, candidate.position),
                candidate.entity_id,
            )
        return (candidate.entity_id,)

    @staticmethod
    def _distance(left: Vector2, right: Vector2) -> float:
        return hypot(left.x - right.x, left.y - right.y)
