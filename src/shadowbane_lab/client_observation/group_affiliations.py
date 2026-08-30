"""Adapter from native party rosters to simulator affiliation memberships."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

from shadowbane_lab.sim.affiliations import GroupKey, GroupKind, GroupMembership

from .native_identity import (
    NativeEntityIdentityMap,
    NativeIdentityJoin,
    NativeObjectRecord,
    join_native_records,
    native_object_key_from_record,
)


class NativeGroupAffiliationError(ValueError):
    """Raised when a native roster cannot safely become affiliation state."""


@dataclass(frozen=True, slots=True)
class NativeGroupAffiliationProjection:
    """Projected memberships and the complete identity-join audit trail."""

    group_key: GroupKey
    memberships: tuple[GroupMembership, ...]
    identity_join: NativeIdentityJoin

    def __post_init__(self) -> None:
        if not isinstance(self.group_key, GroupKey):
            raise NativeGroupAffiliationError("group_key must be a GroupKey")
        if self.group_key.kind is not GroupKind.PARTY:
            raise NativeGroupAffiliationError(
                "native group roster projections require a PARTY group key"
            )
        if any(not isinstance(item, GroupMembership) for item in self.memberships):
            raise NativeGroupAffiliationError(
                "memberships must contain GroupMembership values"
            )
        if any(item.group_key != self.group_key for item in self.memberships):
            raise NativeGroupAffiliationError(
                "projected memberships must use the projection group key"
            )
        if not isinstance(self.identity_join, NativeIdentityJoin):
            raise NativeGroupAffiliationError(
                "identity_join must be a NativeIdentityJoin"
            )
        if len(self.memberships) != len(self.identity_join.resolved_entity_ids):
            raise NativeGroupAffiliationError(
                "membership count must match resolved native identities"
            )

    @property
    def complete(self) -> bool:
        return not self.identity_join.rejection_counts


_RecordT = TypeVar("_RecordT", bound=NativeObjectRecord)


def project_native_party_memberships(
    group_key: GroupKey,
    records: Iterable[_RecordT],
    identity_map: NativeEntityIdentityMap,
    *,
    role_getter: Callable[[_RecordT], str | None] | None = None,
    require_complete: bool = True,
) -> NativeGroupAffiliationProjection:
    """Project a party roster using only object type/UUID identity.

    ``group_key`` must come from verified protocol/client data or explicit scenario
    configuration. This adapter never derives durable party identity from names,
    roster ordering, pointers, health percentages, or positions.
    """

    if not isinstance(group_key, GroupKey):
        raise NativeGroupAffiliationError("group_key must be a GroupKey")
    if group_key.kind is not GroupKind.PARTY:
        raise NativeGroupAffiliationError(
            "native group roster projections require a PARTY group key"
        )
    if not isinstance(require_complete, bool):
        raise NativeGroupAffiliationError("require_complete must be boolean")
    if role_getter is not None and not callable(role_getter):
        raise NativeGroupAffiliationError("role_getter must be callable or null")

    materialized = tuple(records)
    identity_join = join_native_records(
        materialized,
        identity_map,
        key_getter=native_object_key_from_record,
    )
    if require_complete and identity_join.rejection_counts:
        reasons = ", ".join(
            f"{reason}={count}" for reason, count in identity_join.rejection_counts
        )
        raise NativeGroupAffiliationError(
            f"native party roster identity join is incomplete: {reasons}"
        )

    memberships: list[GroupMembership] = []
    for decision in identity_join.decisions:
        if not decision.accepted:
            continue
        assert decision.entity_id is not None
        role = None
        if role_getter is not None:
            role = role_getter(materialized[decision.record_index])
            if role is not None and (
                not isinstance(role, str) or not role.strip()
            ):
                raise NativeGroupAffiliationError(
                    "role_getter must return a non-empty string or null"
                )
        memberships.append(
            GroupMembership(
                entity_id=decision.entity_id,
                group_key=group_key,
                role=role,
            )
        )

    return NativeGroupAffiliationProjection(
        group_key=group_key,
        memberships=tuple(memberships),
        identity_join=identity_join,
    )
