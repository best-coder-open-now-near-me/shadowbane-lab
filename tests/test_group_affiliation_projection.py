from __future__ import annotations

import unittest
from dataclasses import dataclass

from shadowbane_lab.client_observation.group_affiliations import (
    NativeGroupAffiliationError,
    project_native_party_memberships,
)
from shadowbane_lab.client_observation.native_identity import (
    NativeEntityIdentityMap,
    NativeIdentityBinding,
    NativeObjectKey,
)
from shadowbane_lab.sim.affiliations import GroupKey, GroupKind


@dataclass(frozen=True)
class _RosterMember:
    object_type: int
    object_uuid: int
    first_name: str
    leader: bool


class NativeGroupAffiliationProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.party = GroupKey(GroupKind.PARTY, "runtime:42")
        self.identity_map = NativeEntityIdentityMap(
            (
                NativeIdentityBinding(NativeObjectKey(7, 100), "leader"),
                NativeIdentityBinding(NativeObjectKey(7, 101), "member"),
            )
        )

    def test_projects_party_memberships_by_native_identity_and_role(self) -> None:
        records = (
            _RosterMember(7, 100, "same-name", True),
            _RosterMember(7, 101, "same-name", False),
        )

        projection = project_native_party_memberships(
            self.party,
            records,
            self.identity_map,
            role_getter=lambda item: "leader" if item.leader else "member",
        )

        self.assertTrue(projection.complete)
        self.assertEqual(
            ("leader", "member"),
            tuple(item.entity_id for item in projection.memberships),
        )
        self.assertEqual(
            ("leader", "member"),
            tuple(item.role for item in projection.memberships),
        )
        self.assertTrue(
            all(item.group_key == self.party for item in projection.memberships)
        )

    def test_incomplete_join_fails_closed_by_default(self) -> None:
        records = (
            _RosterMember(7, 100, "leader", True),
            _RosterMember(7, 999, "unknown", False),
        )

        with self.assertRaisesRegex(
            NativeGroupAffiliationError, "native_identity_unbound=1"
        ):
            project_native_party_memberships(
                self.party,
                records,
                self.identity_map,
            )

    def test_observation_mode_retains_partial_projection_and_diagnostics(self) -> None:
        records = (
            _RosterMember(7, 100, "leader", True),
            _RosterMember(7, 999, "unknown", False),
        )

        projection = project_native_party_memberships(
            self.party,
            records,
            self.identity_map,
            require_complete=False,
        )

        self.assertFalse(projection.complete)
        self.assertEqual(
            ("leader",), tuple(item.entity_id for item in projection.memberships)
        )
        self.assertEqual(
            (("native_identity_unbound", 1),),
            projection.identity_join.rejection_counts,
        )

    def test_requires_verified_party_key_and_valid_role_values(self) -> None:
        records = (_RosterMember(7, 100, "leader", True),)
        with self.assertRaises(NativeGroupAffiliationError):
            project_native_party_memberships(
                GroupKey(GroupKind.GUILD, "not-a-party"),
                records,
                self.identity_map,
            )
        with self.assertRaises(NativeGroupAffiliationError):
            project_native_party_memberships(
                self.party,
                records,
                self.identity_map,
                role_getter=lambda _item: "",
            )


if __name__ == "__main__":
    unittest.main()
