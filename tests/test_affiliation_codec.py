from __future__ import annotations

import json
import unittest

from shadowbane_lab.protocol import Relation
from shadowbane_lab.sim.affiliation_codec import (
    AFFILIATION_SNAPSHOT_SCHEMA,
    AffiliationCodecError,
    affiliation_snapshot_digest,
    affiliation_snapshot_from_data,
    affiliation_snapshot_to_data,
    decode_affiliation_snapshot,
    encode_affiliation_snapshot,
)
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    OwnershipEdge,
    RelationOverride,
    RelationSubject,
)


def _snapshot(*, reverse: bool = False, revision: int = 7) -> AffiliationSnapshot:
    red = GroupKey(GroupKind.SCENARIO_SIDE, "red")
    blue = GroupKey(GroupKind.SCENARIO_SIDE, "blue")
    party = GroupKey(GroupKind.PARTY, "red-one")
    memberships = [
        GroupMembership("healer", party, role="leader"),
        GroupMembership("tank", party, role="member"),
        GroupMembership("enemy", blue),
        GroupMembership("healer", red),
        GroupMembership("tank", red),
    ]
    ownership = [OwnershipEdge("healer", "pet")]
    overrides = [
        RelationOverride(
            RelationSubject.for_group(red),
            RelationSubject.for_group(blue),
            Relation.ENEMY,
        ),
        RelationOverride(
            RelationSubject.for_entity("pet"),
            RelationSubject.for_entity("enemy"),
            Relation.NEUTRAL,
        ),
    ]
    if reverse:
        memberships.reverse()
        ownership.reverse()
        overrides.reverse()
        first = overrides[0]
        overrides[0] = RelationOverride(
            first.right,
            first.left,
            first.relation,
            symmetric=first.symmetric,
        )
    return AffiliationSnapshot(
        revision=revision,
        memberships=tuple(memberships),
        ownership_edges=tuple(ownership),
        relation_overrides=tuple(overrides),
    )


class AffiliationCodecCompatibilityTests(unittest.TestCase):
    def test_round_trip_preserves_canonical_snapshot_semantics(self) -> None:
        snapshot = _snapshot()
        encoded = encode_affiliation_snapshot(snapshot)
        decoded = decode_affiliation_snapshot(encoded)

        self.assertEqual(
            affiliation_snapshot_to_data(snapshot),
            affiliation_snapshot_to_data(decoded),
        )
        self.assertEqual(1, json.loads(encoded)["schema_version"])
        self.assertEqual("shadowbane-lab.affiliation-snapshot.v1", AFFILIATION_SNAPSHOT_SCHEMA)

    def test_semantically_unordered_inputs_encode_and_digest_identically(self) -> None:
        first = _snapshot()
        second = _snapshot(reverse=True)

        self.assertEqual(encode_affiliation_snapshot(first), encode_affiliation_snapshot(second))
        self.assertEqual(affiliation_snapshot_digest(first), affiliation_snapshot_digest(second))

    def test_digest_changes_with_revision_and_payload(self) -> None:
        original = _snapshot()
        revised = _snapshot(revision=8)
        changed_role = affiliation_snapshot_to_data(original)
        changed_role["memberships"][0]["role"] = "member"  # type: ignore[index]

        self.assertNotEqual(
            affiliation_snapshot_digest(original),
            affiliation_snapshot_digest(revised),
        )
        self.assertNotEqual(
            affiliation_snapshot_digest(original),
            affiliation_snapshot_digest(affiliation_snapshot_from_data(changed_role)),
        )

    def test_unknown_missing_and_duplicate_fields_fail_closed(self) -> None:
        data = affiliation_snapshot_to_data(_snapshot())
        data["unknown"] = True
        with self.assertRaises(AffiliationCodecError):
            affiliation_snapshot_from_data(data)

        data = affiliation_snapshot_to_data(_snapshot())
        del data["revision"]
        with self.assertRaises(AffiliationCodecError):
            affiliation_snapshot_from_data(data)

        with self.assertRaises(AffiliationCodecError):
            decode_affiliation_snapshot(
                '{"schema_version":1,"revision":1,"revision":2,'
                '"memberships":[],"ownership_edges":[],"relation_overrides":[]}'
            )

    def test_invalid_utf8_nonstandard_constants_and_unknown_schema_fail_closed(self) -> None:
        with self.assertRaises(AffiliationCodecError):
            decode_affiliation_snapshot(b"\xff")
        with self.assertRaises(AffiliationCodecError):
            decode_affiliation_snapshot(
                '{"schema_version":1,"revision":NaN,"memberships":[],'
                '"ownership_edges":[],"relation_overrides":[]}'
            )

        data = affiliation_snapshot_to_data(_snapshot())
        data["schema_version"] = 2
        with self.assertRaises(AffiliationCodecError):
            affiliation_snapshot_from_data(data)


if __name__ == "__main__":
    unittest.main()
