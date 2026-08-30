"""Strict party-affiliation projection over the canonical native identity adapter."""

from __future__ import annotations

from dataclasses import dataclass

from shadowbane_lab.sim.affiliations import GroupKey, GroupKind, GroupMembership

from .native_group import NativeGroupMemberObservation, NativeGroupObservation
from .native_identity import project_native_group_to_party
from .native_object import NativeEntityIdentityMap


class NativeGroupAffiliationError(ValueError):
    """Raised when a native roster cannot safely become affiliation state."""


@dataclass(frozen=True, slots=True)
class NativeGroupAffiliationProjection:
    """Party memberships plus explicit unresolved native roster records."""

    group_key: GroupKey
    revision: int
    memberships: tuple[GroupMembership, ...]
    unresolved_members: tuple[NativeGroupMemberObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.group_key, GroupKey):
            raise NativeGroupAffiliationError("group_key must be a GroupKey")
        if self.group_key.kind is not GroupKind.PARTY:
            raise NativeGroupAffiliationError(
                "native group roster projections require a PARTY group key"
            )
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise NativeGroupAffiliationError("revision must be an integer")
        if self.revision < 0:
            raise NativeGroupAffiliationError("revision must be non-negative")
        if not isinstance(self.memberships, tuple):
            raise NativeGroupAffiliationError("memberships must be a tuple")
        if any(not isinstance(item, GroupMembership) for item in self.memberships):
            raise NativeGroupAffiliationError("memberships must contain GroupMembership values")
        if any(item.group_key != self.group_key for item in self.memberships):
            raise NativeGroupAffiliationError(
                "projected memberships must use the projection group key"
            )
        if not isinstance(self.unresolved_members, tuple):
            raise NativeGroupAffiliationError("unresolved_members must be a tuple")
        if any(
            not isinstance(item, NativeGroupMemberObservation) for item in self.unresolved_members
        ):
            raise NativeGroupAffiliationError(
                "unresolved_members must contain NativeGroupMemberObservation values"
            )

    @property
    def complete(self) -> bool:
        return not self.unresolved_members

    @property
    def rejection_counts(self) -> tuple[tuple[str, int], ...]:
        if self.complete:
            return ()
        return (("native_identity_unbound", len(self.unresolved_members)),)


def project_native_party_memberships(
    group_key: GroupKey,
    group: NativeGroupObservation,
    identity_map: NativeEntityIdentityMap,
    *,
    revision: int = 1,
    require_complete: bool = True,
) -> NativeGroupAffiliationProjection:
    """Project a verified native party roster through exact object identity only.

    The caller supplies the durable party key. No identity is inferred from names,
    pointers, health, position, or roster order. Strict mode rejects any unbound
    member; observation mode returns resolved memberships and explicit diagnostics.
    """

    if not isinstance(group_key, GroupKey):
        raise NativeGroupAffiliationError("group_key must be a GroupKey")
    if group_key.kind is not GroupKind.PARTY:
        raise NativeGroupAffiliationError(
            "native group roster projections require a PARTY group key"
        )
    if not isinstance(group, NativeGroupObservation):
        raise NativeGroupAffiliationError("group must be a NativeGroupObservation")
    if not isinstance(identity_map, NativeEntityIdentityMap):
        raise NativeGroupAffiliationError("identity_map must be a NativeEntityIdentityMap")
    if not isinstance(require_complete, bool):
        raise NativeGroupAffiliationError("require_complete must be boolean")

    projected = project_native_group_to_party(
        group,
        identity_map,
        party_group_id=group_key.group_id,
        revision=revision,
    )
    result = NativeGroupAffiliationProjection(
        group_key=group_key,
        revision=projected.snapshot.revision,
        memberships=projected.snapshot.memberships,
        unresolved_members=projected.unresolved_members,
    )
    if require_complete and not result.complete:
        reasons = ", ".join(f"{reason}={count}" for reason, count in result.rejection_counts)
        raise NativeGroupAffiliationError(
            f"native party roster identity join is incomplete: {reasons}"
        )
    return result


__all__ = (
    "NativeGroupAffiliationError",
    "NativeGroupAffiliationProjection",
    "project_native_party_memberships",
)
