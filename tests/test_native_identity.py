from __future__ import annotations

import unittest

from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_identity import (
    NativeEntityBinding,
    NativeEntityIdentityMap,
    NativeKeyedCharacterObservation,
    NativeObjectKey,
    join_native_group_population,
    native_group_member_key,
    project_native_group_to_party,
)
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterObservation,
)
from shadowbane_lab.sim.affiliations import GroupKind


def _member(
    name: str,
    object_type: int,
    object_uuid: int,
    *,
    role_code: int = 0x15,
) -> NativeGroupMemberObservation:
    return NativeGroupMemberObservation(
        first_name=name,
        last_name="",
        object_type=object_type,
        object_uuid=object_uuid,
        health_percent=100,
        stamina_percent=100,
        mana_percent=100,
        lt=10.0,
        lg=20.0,
        altitude=2.0,
        role_code=role_code,
        follow_enabled=False,
    )


def _character(token: str) -> NativeCharacterObservation:
    return NativeCharacterObservation(
        token=token,
        current_health=100.0,
        maximum_health=100.0,
        lt=10.0,
        lg=20.0,
        altitude=2.0,
        merchant=False,
        shopkeeper=False,
        banker=False,
        trainer=False,
        minion=False,
    )


class NativeObjectKeyTests(unittest.TestCase):
    def test_key_is_lossless_canonical_and_strict(self) -> None:
        key = NativeObjectKey(3, 42)
        self.assertEqual("00000003:0000002a", key.canonical_token)
        self.assertEqual(key, NativeObjectKey.from_dict(key.as_dict()))
        self.assertFalse(key.is_null)
        self.assertTrue(NativeObjectKey(0, 0).is_null)

        with self.assertRaises(ValueError):
            NativeObjectKey(-1, 42)
        with self.assertRaises(ValueError):
            NativeObjectKey.from_dict(
                {"object_type": 3, "object_uuid": 42, "extra": True}
            )


class NativeEntityIdentityMapTests(unittest.TestCase):
    def test_map_is_one_to_one_and_never_uses_pointer_tokens_as_entity_ids(self) -> None:
        first = NativeObjectKey(3, 101)
        second = NativeObjectKey(3, 102)
        identities = NativeEntityIdentityMap(
            (
                NativeEntityBinding(first, "healer"),
                NativeEntityBinding(second, "tank"),
            )
        )

        self.assertEqual("healer", identities.entity_id_for(first))
        self.assertEqual(second, identities.object_key_for("tank"))
        self.assertIsNone(identities.entity_id_for(NativeObjectKey(3, 999)))
        self.assertEqual("tank", identities.require_entity_id(second))

        with self.assertRaises(KeyError):
            identities.require_entity_id(NativeObjectKey(3, 999))
        with self.assertRaises(ValueError):
            NativeEntityBinding(NativeObjectKey(0, 0), "nobody")
        with self.assertRaises(ValueError):
            NativeEntityIdentityMap(
                (
                    NativeEntityBinding(first, "one"),
                    NativeEntityBinding(first, "two"),
                )
            )
        with self.assertRaises(ValueError):
            NativeEntityIdentityMap(
                (
                    NativeEntityBinding(first, "same"),
                    NativeEntityBinding(second, "same"),
                )
            )


class NativeGroupPopulationJoinTests(unittest.TestCase):
    def test_join_uses_only_exact_object_keys_and_retains_unresolved_records(self) -> None:
        alice = _member("Alice", 3, 101, role_code=0x16)
        bob = _member("Bob", 3, 102)
        group = NativeGroupObservation(
            split_gold_enabled=False,
            local_follow_enabled=False,
            members=(alice, bob),
        )
        keyed_bob = NativeKeyedCharacterObservation(
            NativeObjectKey(3, 102),
            _character("opaque-pointer-token-for-bob"),
        )
        outsider = NativeKeyedCharacterObservation(
            NativeObjectKey(3, 999),
            _character("opaque-pointer-token-for-outsider"),
        )

        joined = join_native_group_population(group, (outsider, keyed_bob))

        self.assertEqual((bob,), tuple(match.member for match in joined.matches))
        self.assertEqual((alice,), joined.unresolved_members)
        self.assertEqual((outsider,), joined.unmatched_characters)
        self.assertEqual(NativeObjectKey(3, 101), native_group_member_key(alice))

    def test_duplicate_population_keys_fail_closed(self) -> None:
        keyed = NativeKeyedCharacterObservation(
            NativeObjectKey(3, 101),
            _character("first"),
        )
        with self.assertRaises(ValueError):
            join_native_group_population(
                NativeGroupObservation(False, False, ()),
                (
                    keyed,
                    NativeKeyedCharacterObservation(
                        keyed.object_key,
                        _character("second"),
                    ),
                ),
            )


class NativePartyProjectionTests(unittest.TestCase):
    def test_projection_maps_only_explicit_bindings_and_preserves_roles(self) -> None:
        leader = _member("Leader", 3, 101, role_code=0x16)
        member = _member("Member", 3, 102)
        unresolved = _member("Unknown", 3, 103)
        group = NativeGroupObservation(
            split_gold_enabled=True,
            local_follow_enabled=False,
            members=(leader, member, unresolved),
        )
        identities = NativeEntityIdentityMap(
            (
                NativeEntityBinding(NativeObjectKey(3, 101), "healer"),
                NativeEntityBinding(NativeObjectKey(3, 102), "tank"),
            )
        )

        projection = project_native_group_to_party(
            group,
            identities,
            party_group_id="wonderbane-group:1842",
            revision=9,
        )

        self.assertEqual(GroupKind.PARTY, projection.group_key.kind)
        self.assertEqual(9, projection.snapshot.revision)
        self.assertEqual(
            (("healer", "leader"), ("tank", "member")),
            tuple(
                (membership.entity_id, membership.role)
                for membership in projection.snapshot.memberships
            ),
        )
        self.assertEqual((unresolved,), projection.unresolved_members)

    def test_projection_requires_caller_supplied_group_identity(self) -> None:
        with self.assertRaises(ValueError):
            project_native_group_to_party(
                NativeGroupObservation(False, False, ()),
                NativeEntityIdentityMap(),
                party_group_id="",
            )


if __name__ == "__main__":
    unittest.main()
