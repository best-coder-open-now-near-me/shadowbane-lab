from __future__ import annotations

import unittest

from shadowbane_lab.client_observation.group_affiliations import (
    NativeGroupAffiliationError,
    project_native_party_memberships,
)
from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_object import (
    NativeEntityBinding,
    NativeEntityIdentityMap,
    NativeObjectKey,
)
from shadowbane_lab.sim.affiliations import GroupKey, GroupKind


def _member(
    name: str,
    object_uuid: int,
    *,
    leader: bool = False,
) -> NativeGroupMemberObservation:
    return NativeGroupMemberObservation(
        first_name=name,
        last_name="",
        object_type=7,
        object_uuid=object_uuid,
        health_percent=100,
        stamina_percent=100,
        mana_percent=100,
        lt=10.0,
        lg=20.0,
        altitude=2.0,
        role_code=0x16 if leader else 0x15,
        follow_enabled=False,
    )


class NativeGroupAffiliationProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.party = GroupKey(GroupKind.PARTY, "runtime:42")
        self.identity_map = NativeEntityIdentityMap(
            (
                NativeEntityBinding(NativeObjectKey(7, 100), "leader"),
                NativeEntityBinding(NativeObjectKey(7, 101), "member"),
            )
        )

    def test_projects_party_memberships_by_native_identity_and_role(self) -> None:
        group = NativeGroupObservation(
            split_gold_enabled=False,
            local_follow_enabled=False,
            members=(
                _member("same-name", 100, leader=True),
                _member("same-name", 101),
            ),
        )

        projection = project_native_party_memberships(
            self.party,
            group,
            self.identity_map,
            revision=9,
        )

        self.assertTrue(projection.complete)
        self.assertEqual(9, projection.revision)
        self.assertEqual(
            ("leader", "member"),
            tuple(item.entity_id for item in projection.memberships),
        )
        self.assertEqual(
            ("leader", "member"),
            tuple(item.role for item in projection.memberships),
        )
        self.assertTrue(all(item.group_key == self.party for item in projection.memberships))
        self.assertEqual((), projection.rejection_counts)

    def test_incomplete_join_fails_closed_by_default(self) -> None:
        group = NativeGroupObservation(
            split_gold_enabled=False,
            local_follow_enabled=False,
            members=(
                _member("leader", 100, leader=True),
                _member("unknown", 999),
            ),
        )

        with self.assertRaisesRegex(NativeGroupAffiliationError, "native_identity_unbound=1"):
            project_native_party_memberships(
                self.party,
                group,
                self.identity_map,
            )

    def test_observation_mode_retains_partial_projection_and_diagnostics(self) -> None:
        unresolved = _member("unknown", 999)
        group = NativeGroupObservation(
            split_gold_enabled=False,
            local_follow_enabled=False,
            members=(
                _member("leader", 100, leader=True),
                unresolved,
            ),
        )

        projection = project_native_party_memberships(
            self.party,
            group,
            self.identity_map,
            require_complete=False,
        )

        self.assertFalse(projection.complete)
        self.assertEqual(("leader",), tuple(item.entity_id for item in projection.memberships))
        self.assertEqual((unresolved,), projection.unresolved_members)
        self.assertEqual(
            (("native_identity_unbound", 1),),
            projection.rejection_counts,
        )

    def test_requires_verified_party_key_and_native_group(self) -> None:
        group = NativeGroupObservation(False, False, (_member("leader", 100),))
        with self.assertRaises(NativeGroupAffiliationError):
            project_native_party_memberships(
                GroupKey(GroupKind.GUILD, "not-a-party"),
                group,
                self.identity_map,
            )
        with self.assertRaises(NativeGroupAffiliationError):
            project_native_party_memberships(
                self.party,
                object(),  # type: ignore[arg-type]
                self.identity_map,
            )


if __name__ == "__main__":
    unittest.main()
