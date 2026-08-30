from __future__ import annotations

import json
import unittest

from shadowbane_lab.protocol import Relation
from shadowbane_lab.sim.affiliation_io import (
    AffiliationSnapshotFormatError,
    affiliation_snapshot_digest,
    affiliation_snapshot_from_dict,
    affiliation_snapshot_to_dict,
    dump_affiliation_snapshot,
    load_affiliation_snapshot_text,
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


class AffiliationSnapshotSerializationTests(unittest.TestCase):
    def _snapshot(self) -> AffiliationSnapshot:
        party = GroupKey(GroupKind.PARTY, "party-1")
        red = GroupKey(GroupKind.SCENARIO_SIDE, "red")
        blue = GroupKey(GroupKind.SCENARIO_SIDE, "blue")
        return AffiliationSnapshot(
            revision=7,
            memberships=(
                GroupMembership("tank", red),
                GroupMembership("healer", party, role="leader"),
                GroupMembership("tank", party, role="member"),
                GroupMembership("healer", red),
                GroupMembership("enemy", blue),
            ),
            ownership_edges=(
                OwnershipEdge("healer", "pet"),
                OwnershipEdge("pet", "summon"),
            ),
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_group(blue),
                    RelationSubject.for_group(red),
                    Relation.ENEMY,
                ),
                RelationOverride(
                    RelationSubject.for_entity("healer"),
                    RelationSubject.for_entity("enemy"),
                    Relation.NEUTRAL,
                    symmetric=False,
                ),
            ),
        )

    def test_round_trip_preserves_canonical_payload_and_digest(self) -> None:
        snapshot = self._snapshot()
        encoded = dump_affiliation_snapshot(snapshot)
        decoded = load_affiliation_snapshot_text(encoded)

        self.assertEqual(
            affiliation_snapshot_to_dict(snapshot),
            affiliation_snapshot_to_dict(decoded),
        )
        self.assertEqual(
            affiliation_snapshot_digest(snapshot),
            affiliation_snapshot_digest(decoded),
        )
        self.assertEqual(
            encoded,
            json.dumps(
                affiliation_snapshot_to_dict(snapshot),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ),
        )

    def test_input_order_and_symmetric_endpoint_order_do_not_change_digest(self) -> None:
        red = GroupKey(GroupKind.SCENARIO_SIDE, "red")
        blue = GroupKey(GroupKind.SCENARIO_SIDE, "blue")
        first = AffiliationSnapshot(
            memberships=(
                GroupMembership("red-player", red),
                GroupMembership("blue-player", blue),
            ),
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_group(red),
                    RelationSubject.for_group(blue),
                    Relation.ENEMY,
                ),
            ),
        )
        second = AffiliationSnapshot(
            memberships=tuple(reversed(first.memberships)),
            relation_overrides=(
                RelationOverride(
                    RelationSubject.for_group(blue),
                    RelationSubject.for_group(red),
                    Relation.ENEMY,
                ),
            ),
        )

        self.assertEqual(
            affiliation_snapshot_to_dict(first),
            affiliation_snapshot_to_dict(second),
        )
        self.assertEqual(
            affiliation_snapshot_digest(first),
            affiliation_snapshot_digest(second),
        )

    def test_revision_and_party_layout_change_the_digest(self) -> None:
        party = GroupKey(GroupKind.PARTY, "party-1")
        baseline = AffiliationSnapshot(
            revision=1,
            memberships=(GroupMembership("healer", party),),
        )
        new_revision = AffiliationSnapshot(
            revision=2,
            memberships=baseline.memberships,
        )
        new_layout = AffiliationSnapshot(
            revision=1,
            memberships=(
                GroupMembership("healer", party),
                GroupMembership("tank", party),
            ),
        )

        self.assertNotEqual(
            affiliation_snapshot_digest(baseline),
            affiliation_snapshot_digest(new_revision),
        )
        self.assertNotEqual(
            affiliation_snapshot_digest(baseline),
            affiliation_snapshot_digest(new_layout),
        )

    def test_strict_parser_rejects_unknown_missing_and_duplicate_fields(self) -> None:
        payload = affiliation_snapshot_to_dict(self._snapshot())
        with self.assertRaises(AffiliationSnapshotFormatError):
            affiliation_snapshot_from_dict({**payload, "unknown": True})

        missing = dict(payload)
        missing.pop("revision")
        with self.assertRaises(AffiliationSnapshotFormatError):
            affiliation_snapshot_from_dict(missing)

        with self.assertRaises(AffiliationSnapshotFormatError):
            load_affiliation_snapshot_text(
                '{"schema_version":1,"schema_version":1,'
                '"revision":0,"memberships":[],"ownership_edges":[],'
                '"relation_overrides":[]}'
            )

    def test_parser_rejects_unknown_enums_and_nonstandard_numbers(self) -> None:
        payload = affiliation_snapshot_to_dict(self._snapshot())
        payload["memberships"][0]["group_key"]["kind"] = "raid"
        with self.assertRaises(AffiliationSnapshotFormatError):
            affiliation_snapshot_from_dict(payload)

        with self.assertRaises(AffiliationSnapshotFormatError):
            load_affiliation_snapshot_text(
                '{"schema_version":1,"revision":NaN,"memberships":[],'
                '"ownership_edges":[],"relation_overrides":[]}'
            )


if __name__ == "__main__":
    unittest.main()
