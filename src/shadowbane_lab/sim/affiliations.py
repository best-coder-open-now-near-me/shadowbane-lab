"""Immutable scenario affiliations and source-independent relation facts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations, permutations
from typing import Protocol

from shadowbane_lab.protocol import Relation


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


class AffiliationConfigurationError(ValueError):
    """Raised when an affiliation snapshot cannot be interpreted deterministically."""


class AffiliationConflictError(AffiliationConfigurationError):
    """Raised when equally specific relation overrides disagree."""


class GroupKind(StrEnum):
    """Symmetric set memberships maintained by a scenario."""

    PARTY = "party"
    GUILD = "guild"
    NATION = "nation"
    SCENARIO_SIDE = "scenario_side"


@dataclass(frozen=True, slots=True, order=True)
class GroupKey:
    """Source-qualified identity for one scenario group."""

    kind: GroupKind
    group_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GroupKind):
            raise ValueError("kind must be a GroupKind")
        _identifier(self.group_id, "group_id")


@dataclass(frozen=True, slots=True)
class GroupMembership:
    """One entity's membership in one symmetric group."""

    entity_id: str
    group_key: GroupKey
    role: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "entity_id")
        if not isinstance(self.group_key, GroupKey):
            raise ValueError("group_key must be a GroupKey")
        if self.role is not None:
            _identifier(self.role, "role")


@dataclass(frozen=True, slots=True, order=True)
class OwnershipEdge:
    """Directed owner-to-owned relation for pets, summons, and subordinate objects."""

    owner_id: str
    owned_id: str

    def __post_init__(self) -> None:
        _identifier(self.owner_id, "owner_id")
        _identifier(self.owned_id, "owned_id")
        if self.owner_id == self.owned_id:
            raise ValueError("ownership edges cannot be self-referential")


@dataclass(frozen=True, slots=True)
class RelationSubject:
    """Entity or group endpoint used by a scenario relation override."""

    entity_id: str | None = None
    group_key: GroupKey | None = None

    def __post_init__(self) -> None:
        if (self.entity_id is None) == (self.group_key is None):
            raise ValueError("exactly one of entity_id or group_key is required")
        if self.entity_id is not None:
            _identifier(self.entity_id, "entity_id")
        if self.group_key is not None and not isinstance(self.group_key, GroupKey):
            raise ValueError("group_key must be a GroupKey")

    @classmethod
    def for_entity(cls, entity_id: str) -> RelationSubject:
        return cls(entity_id=entity_id)

    @classmethod
    def for_group(cls, group_key: GroupKey) -> RelationSubject:
        return cls(group_key=group_key)

    @property
    def specificity(self) -> int:
        return 2 if self.entity_id is not None else 1

    @property
    def sort_key(self) -> tuple[str, str, str]:
        if self.entity_id is not None:
            return ("entity", "", self.entity_id)
        assert self.group_key is not None
        return ("group", self.group_key.kind.value, self.group_key.group_id)

    def matches(self, entity_id: str, memberships: frozenset[GroupKey]) -> bool:
        if self.entity_id is not None:
            return self.entity_id == entity_id
        assert self.group_key is not None
        return self.group_key in memberships


@dataclass(frozen=True, slots=True)
class RelationOverride:
    """Explicit relation whose endpoint specificity determines precedence."""

    left: RelationSubject
    right: RelationSubject
    relation: Relation
    symmetric: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.left, RelationSubject):
            raise ValueError("left must be a RelationSubject")
        if not isinstance(self.right, RelationSubject):
            raise ValueError("right must be a RelationSubject")
        if self.left == self.right:
            raise ValueError("relation override endpoints must differ")
        if not isinstance(self.relation, Relation):
            raise ValueError("relation must be a Relation")
        if self.relation is Relation.SELF:
            raise ValueError("SELF cannot be assigned by a relation override")
        if not isinstance(self.symmetric, bool):
            raise ValueError("symmetric must be boolean")

    @property
    def precedence(self) -> int:
        """Entity/entity beats entity/group, which beats group/group."""

        return self.left.specificity + self.right.specificity

    @property
    def identity_key(self) -> tuple[object, ...]:
        endpoints = (self.left.sort_key, self.right.sort_key)
        if self.symmetric:
            endpoints = tuple(sorted(endpoints))
        return (*endpoints, self.symmetric)

    def matches(
        self,
        left_entity_id: str,
        right_entity_id: str,
        left_memberships: frozenset[GroupKey],
        right_memberships: frozenset[GroupKey],
    ) -> bool:
        forward = self.left.matches(left_entity_id, left_memberships) and self.right.matches(
            right_entity_id, right_memberships
        )
        if forward or not self.symmetric:
            return forward
        return self.left.matches(right_entity_id, right_memberships) and self.right.matches(
            left_entity_id, left_memberships
        )

    def is_between_group_kind(self, kind: GroupKind) -> bool:
        return (
            self.left.group_key is not None
            and self.left.group_key.kind is kind
            and self.right.group_key is not None
            and self.right.group_key.kind is kind
        )


@dataclass(frozen=True, slots=True)
class AffiliationSnapshot:
    """Immutable, revisioned scenario-affiliation state."""

    revision: int = 1
    memberships: tuple[GroupMembership, ...] = ()
    ownership_edges: tuple[OwnershipEdge, ...] = ()
    relation_overrides: tuple[RelationOverride, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise ValueError("revision must be an integer")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if any(not isinstance(item, GroupMembership) for item in self.memberships):
            raise ValueError("memberships must contain GroupMembership values")
        if any(not isinstance(item, OwnershipEdge) for item in self.ownership_edges):
            raise ValueError("ownership_edges must contain OwnershipEdge values")
        if any(not isinstance(item, RelationOverride) for item in self.relation_overrides):
            raise ValueError("relation_overrides must contain RelationOverride values")

        membership_keys = tuple((item.entity_id, item.group_key) for item in self.memberships)
        if len(membership_keys) != len(set(membership_keys)):
            raise AffiliationConfigurationError("memberships must not contain duplicates")
        group_kinds_by_entity: dict[str, set[GroupKind]] = defaultdict(set)
        for membership in self.memberships:
            kinds = group_kinds_by_entity[membership.entity_id]
            if membership.group_key.kind in kinds:
                raise AffiliationConfigurationError(
                    "an entity cannot belong to multiple groups of the same kind"
                )
            kinds.add(membership.group_key.kind)

        if len(self.ownership_edges) != len(set(self.ownership_edges)):
            raise AffiliationConfigurationError("ownership_edges must not contain duplicates")
        owner_by_owned: dict[str, str] = {}
        for edge in self.ownership_edges:
            existing = owner_by_owned.get(edge.owned_id)
            if existing is not None and existing != edge.owner_id:
                raise AffiliationConfigurationError(
                    "an owned entity cannot have multiple direct owners"
                )
            owner_by_owned[edge.owned_id] = edge.owner_id
        self._validate_ownership_cycles(owner_by_owned)

        overrides_by_identity: dict[tuple[object, ...], RelationOverride] = {}
        for override in self.relation_overrides:
            existing = overrides_by_identity.get(override.identity_key)
            if existing is not None:
                if existing.relation is not override.relation:
                    raise AffiliationConflictError(
                        "relation overrides with identical endpoints disagree"
                    )
                raise AffiliationConfigurationError(
                    "relation_overrides must not contain duplicates"
                )
            overrides_by_identity[override.identity_key] = override

        self._validate_known_entity_override_conflicts()

    @staticmethod
    def _validate_ownership_cycles(owner_by_owned: Mapping[str, str]) -> None:
        for entity_id in owner_by_owned:
            visited: set[str] = set()
            current = entity_id
            while current in owner_by_owned:
                if current in visited:
                    raise AffiliationConfigurationError("ownership graph contains a cycle")
                visited.add(current)
                current = owner_by_owned[current]

    def _validate_known_entity_override_conflicts(self) -> None:
        entity_ids = self.entity_ids
        if len(entity_ids) < 2 or not self.relation_overrides:
            return
        memberships = self.memberships_by_entity
        for left_entity_id, right_entity_id in permutations(entity_ids, 2):
            _select_override(
                self.relation_overrides,
                left_entity_id,
                right_entity_id,
                memberships.get(left_entity_id, frozenset()),
                memberships.get(right_entity_id, frozenset()),
            )

    @property
    def entity_ids(self) -> tuple[str, ...]:
        values = {membership.entity_id for membership in self.memberships}
        for edge in self.ownership_edges:
            values.add(edge.owner_id)
            values.add(edge.owned_id)
        for override in self.relation_overrides:
            if override.left.entity_id is not None:
                values.add(override.left.entity_id)
            if override.right.entity_id is not None:
                values.add(override.right.entity_id)
        return tuple(sorted(values))

    @property
    def memberships_by_entity(self) -> dict[str, frozenset[GroupKey]]:
        values: dict[str, set[GroupKey]] = defaultdict(set)
        for membership in self.memberships:
            values[membership.entity_id].add(membership.group_key)
        return {entity_id: frozenset(groups) for entity_id, groups in values.items()}


@dataclass(frozen=True, slots=True)
class RelationFacts:
    """Factual relationship channels before a ruleset derives a coarse relation."""

    left_entity_id: str
    right_entity_id: str
    same_entity: bool
    same_party: bool
    same_guild: bool
    same_nation: bool
    same_scenario_side: bool
    opposing_scenario_side: bool
    left_owns_right: bool
    right_owns_left: bool
    same_owner: bool
    same_ownership_family: bool
    explicit_neutrality: bool
    override_relation: Relation | None = None
    override_precedence: int | None = None

    def __post_init__(self) -> None:
        _identifier(self.left_entity_id, "left_entity_id")
        _identifier(self.right_entity_id, "right_entity_id")
        boolean_fields = (
            self.same_entity,
            self.same_party,
            self.same_guild,
            self.same_nation,
            self.same_scenario_side,
            self.opposing_scenario_side,
            self.left_owns_right,
            self.right_owns_left,
            self.same_owner,
            self.same_ownership_family,
            self.explicit_neutrality,
        )
        if any(not isinstance(value, bool) for value in boolean_fields):
            raise ValueError("relation fact flags must be boolean")
        if self.same_entity != (self.left_entity_id == self.right_entity_id):
            raise ValueError("same_entity must match the entity identifiers")
        if self.override_relation is not None:
            if not isinstance(self.override_relation, Relation):
                raise ValueError("override_relation must be a Relation or null")
            if self.override_relation is Relation.SELF:
                raise ValueError("override_relation cannot be SELF")
            if self.override_precedence is None:
                raise ValueError("override_precedence is required with override_relation")
        elif self.override_precedence is not None:
            raise ValueError("override_precedence requires override_relation")
        if self.override_precedence is not None and self.override_precedence <= 0:
            raise ValueError("override_precedence must be positive")
        if self.explicit_neutrality != (self.override_relation is Relation.NEUTRAL):
            raise ValueError("explicit_neutrality must reflect override_relation")


class RelationPolicy(Protocol):
    """Ruleset-owned mapping from exact facts to the compatibility relation."""

    def coarse_relation(self, facts: RelationFacts) -> Relation: ...


@dataclass(frozen=True, slots=True)
class DefaultRelationPolicy:
    """Conservative default that preserves party, side, and owner-family friendliness."""

    same_party_is_ally: bool = True
    same_guild_is_ally: bool = False
    same_nation_is_ally: bool = False
    same_scenario_side_is_ally: bool = True
    same_ownership_family_is_ally: bool = True

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.same_party_is_ally,
                self.same_guild_is_ally,
                self.same_nation_is_ally,
                self.same_scenario_side_is_ally,
                self.same_ownership_family_is_ally,
            )
        ):
            raise ValueError("relation policy flags must be boolean")

    def coarse_relation(self, facts: RelationFacts) -> Relation:
        if not isinstance(facts, RelationFacts):
            raise ValueError("facts must be RelationFacts")
        if facts.same_entity:
            return Relation.SELF
        if facts.override_relation is not None:
            return facts.override_relation
        if self.same_party_is_ally and facts.same_party:
            return Relation.ALLY
        if self.same_guild_is_ally and facts.same_guild:
            return Relation.ALLY
        if self.same_nation_is_ally and facts.same_nation:
            return Relation.ALLY
        if self.same_scenario_side_is_ally and facts.same_scenario_side:
            return Relation.ALLY
        if self.same_ownership_family_is_ally and facts.same_ownership_family:
            return Relation.ALLY
        if facts.opposing_scenario_side:
            return Relation.ENEMY
        return Relation.NEUTRAL


class RelationResolver:
    """Derives exact relation facts from one immutable affiliation snapshot."""

    def __init__(self, snapshot: AffiliationSnapshot) -> None:
        if not isinstance(snapshot, AffiliationSnapshot):
            raise ValueError("snapshot must be an AffiliationSnapshot")
        self._snapshot = snapshot
        self._memberships = snapshot.memberships_by_entity
        self._owner_by_owned = {edge.owned_id: edge.owner_id for edge in snapshot.ownership_edges}

    @property
    def snapshot(self) -> AffiliationSnapshot:
        return self._snapshot

    def facts_between(self, left_entity_id: str, right_entity_id: str) -> RelationFacts:
        _identifier(left_entity_id, "left_entity_id")
        _identifier(right_entity_id, "right_entity_id")
        left_memberships = self._memberships.get(left_entity_id, frozenset())
        right_memberships = self._memberships.get(right_entity_id, frozenset())
        override = _select_override(
            self._snapshot.relation_overrides,
            left_entity_id,
            right_entity_id,
            left_memberships,
            right_memberships,
        )
        left_ancestors = self._ancestor_chain(left_entity_id)
        right_ancestors = self._ancestor_chain(right_entity_id)
        same_owner = (
            left_entity_id != right_entity_id
            and self._owner_by_owned.get(left_entity_id) is not None
            and self._owner_by_owned.get(left_entity_id)
            == self._owner_by_owned.get(right_entity_id)
        )
        same_family = left_entity_id != right_entity_id and self._ownership_root(
            left_entity_id
        ) == self._ownership_root(right_entity_id)
        return RelationFacts(
            left_entity_id=left_entity_id,
            right_entity_id=right_entity_id,
            same_entity=left_entity_id == right_entity_id,
            same_party=self._shares_kind(left_memberships, right_memberships, GroupKind.PARTY),
            same_guild=self._shares_kind(left_memberships, right_memberships, GroupKind.GUILD),
            same_nation=self._shares_kind(left_memberships, right_memberships, GroupKind.NATION),
            same_scenario_side=self._shares_kind(
                left_memberships, right_memberships, GroupKind.SCENARIO_SIDE
            ),
            opposing_scenario_side=(
                override is not None
                and override.relation is Relation.ENEMY
                and override.is_between_group_kind(GroupKind.SCENARIO_SIDE)
            ),
            left_owns_right=left_entity_id in right_ancestors,
            right_owns_left=right_entity_id in left_ancestors,
            same_owner=same_owner,
            same_ownership_family=same_family,
            explicit_neutrality=(override is not None and override.relation is Relation.NEUTRAL),
            override_relation=override.relation if override is not None else None,
            override_precedence=override.precedence if override is not None else None,
        )

    def coarse_relation(
        self,
        left_entity_id: str,
        right_entity_id: str,
        policy: RelationPolicy | None = None,
    ) -> Relation:
        selected_policy = DefaultRelationPolicy() if policy is None else policy
        return selected_policy.coarse_relation(self.facts_between(left_entity_id, right_entity_id))

    def _ancestor_chain(self, entity_id: str) -> tuple[str, ...]:
        values: list[str] = []
        current = entity_id
        while current in self._owner_by_owned:
            current = self._owner_by_owned[current]
            values.append(current)
        return tuple(values)

    def _ownership_root(self, entity_id: str) -> str:
        ancestors = self._ancestor_chain(entity_id)
        return ancestors[-1] if ancestors else entity_id

    @staticmethod
    def _shares_kind(
        left: frozenset[GroupKey],
        right: frozenset[GroupKey],
        kind: GroupKind,
    ) -> bool:
        return bool(
            {group for group in left if group.kind is kind}
            & {group for group in right if group.kind is kind}
        )


def legacy_team_affiliations(
    team_ids: Mapping[str, str | None],
    *,
    revision: int = 1,
    group_prefix: str = "legacy-team",
) -> AffiliationSnapshot:
    """Compile legacy ``team_id`` values into scenario-side memberships and diplomacy."""

    if not isinstance(team_ids, Mapping):
        raise ValueError("team_ids must be a mapping")
    _identifier(group_prefix, "group_prefix")
    memberships: list[GroupMembership] = []
    groups_by_team: dict[str, GroupKey] = {}
    for entity_id in sorted(team_ids):
        _identifier(entity_id, "team_ids key")
        team_id = team_ids[entity_id]
        if team_id is None:
            continue
        _identifier(team_id, "team_id")
        group = groups_by_team.setdefault(
            team_id,
            GroupKey(GroupKind.SCENARIO_SIDE, f"{group_prefix}:{team_id}"),
        )
        memberships.append(GroupMembership(entity_id, group))
    overrides = tuple(
        RelationOverride(
            RelationSubject.for_group(left),
            RelationSubject.for_group(right),
            Relation.ENEMY,
        )
        for left, right in combinations(sorted(groups_by_team.values()), 2)
    )
    return AffiliationSnapshot(
        revision=revision,
        memberships=tuple(memberships),
        relation_overrides=overrides,
    )


def _select_override(
    overrides: tuple[RelationOverride, ...],
    left_entity_id: str,
    right_entity_id: str,
    left_memberships: frozenset[GroupKey],
    right_memberships: frozenset[GroupKey],
) -> RelationOverride | None:
    matches = tuple(
        override
        for override in overrides
        if override.matches(
            left_entity_id,
            right_entity_id,
            left_memberships,
            right_memberships,
        )
    )
    if not matches:
        return None
    precedence = max(override.precedence for override in matches)
    strongest = tuple(override for override in matches if override.precedence == precedence)
    relations = {override.relation for override in strongest}
    if len(relations) > 1:
        raise AffiliationConflictError(
            "equally specific relation overrides disagree for "
            f"{left_entity_id!r} and {right_entity_id!r}"
        )
    return min(
        strongest,
        key=lambda override: (
            override.left.sort_key,
            override.right.sort_key,
            override.symmetric,
        ),
    )
