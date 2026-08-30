from __future__ import annotations

import unittest

from shadowbane_lab.composition.affiliation_runtime import (
    AffiliationComponent,
    AffiliationMaterializationError,
    materialize_scenario_affiliations,
)
from shadowbane_lab.composition.model import (
    ResolvedScenarioView,
    ScenarioOverlay,
    ScenarioSlotView,
)
from shadowbane_lab.protocol import Relation
from shadowbane_lab.sim.affiliation_io import (
    affiliation_snapshot_digest,
    dump_affiliation_snapshot,
)
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    RelationOverride,
    RelationSubject,
)


def _source_snapshot(*, revision: int = 3, include_ghost: bool = False) -> AffiliationSnapshot:
    left = GroupKey(GroupKind.SCENARIO_SIDE, "left")
    right = GroupKey(GroupKind.SCENARIO_SIDE, "right")
    memberships = [
        GroupMembership("aff:left", left),
        GroupMembership("aff:right", right),
    ]
    if include_ghost:
        memberships.append(GroupMembership("aff:ghost", right))
    return AffiliationSnapshot(
        revision=revision,
        memberships=tuple(memberships),
        relation_overrides=(
            RelationOverride(
                RelationSubject.for_group(left),
                RelationSubject.for_group(right),
                Relation.ENEMY,
            ),
        ),
    )


def _scenario(
    snapshot: AffiliationSnapshot | None,
    *,
    snapshot_id: str = "groups:duel",
    digest: str | None = None,
    revision: int | None = None,
) -> ResolvedScenarioView:
    return ResolvedScenarioView(
        scenario_id="duel",
        ruleset_revision="wonderbane:test",
        environment_profile_id="flat",
        slots=(
            ScenarioSlotView(
                slot_id="left",
                entity_id="runtime-left",
                overlay=ScenarioOverlay("left", position=(0.0, 0.0)),
                legacy_team_id="left",
                affiliation_entity_id="aff:left",
            ),
            ScenarioSlotView(
                slot_id="right",
                entity_id="runtime-right",
                overlay=ScenarioOverlay("right", position=(10.0, 0.0)),
                legacy_team_id="right",
                affiliation_entity_id="aff:right",
            ),
        ),
        affiliation_snapshot_id=snapshot_id if snapshot is not None else None,
        affiliation_snapshot_digest=(
            digest
            if digest is not None
            else affiliation_snapshot_digest(snapshot)
            if snapshot is not None
            else None
        ),
        affiliation_revision=(
            revision
            if revision is not None
            else snapshot.revision
            if snapshot is not None
            else 0
        ),
    )


def _component(snapshot: AffiliationSnapshot, snapshot_id: str = "groups:duel"):
    return AffiliationComponent.from_text(snapshot_id, dump_affiliation_snapshot(snapshot))


class AffiliationRuntimeMaterializationTests(unittest.TestCase):
    def test_verifies_payload_and_remaps_affiliation_ids_to_runtime_entities(self) -> None:
        source = _source_snapshot()
        materialized = materialize_scenario_affiliations(
            _scenario(source),
            _component(source),
        )

        assert materialized is not None
        self.assertEqual("groups:duel", materialized.snapshot_id)
        self.assertEqual(affiliation_snapshot_digest(source), materialized.source_digest)
        self.assertEqual(3, materialized.source_revision)
        self.assertEqual(
            ("runtime-left", "runtime-right"),
            materialized.snapshot.entity_ids,
        )
        self.assertEqual(
            Relation.ENEMY,
            next(iter(materialized.snapshot.relation_overrides)).relation,
        )

    def test_digest_revision_and_component_id_mismatches_fail_closed(self) -> None:
        source = _source_snapshot()
        with self.assertRaisesRegex(AffiliationMaterializationError, "digest"):
            materialize_scenario_affiliations(
                _scenario(source, digest="0" * 64),
                _component(source),
            )
        with self.assertRaisesRegex(AffiliationMaterializationError, "revision"):
            materialize_scenario_affiliations(
                _scenario(source, revision=source.revision + 1),
                _component(source),
            )
        with self.assertRaisesRegex(AffiliationMaterializationError, "component id"):
            materialize_scenario_affiliations(
                _scenario(source),
                _component(source, snapshot_id="groups:other"),
            )

    def test_dangling_affiliation_entity_is_not_dropped_or_inferred(self) -> None:
        source = _source_snapshot(include_ghost=True)
        with self.assertRaisesRegex(AffiliationMaterializationError, "absent from the scenario"):
            materialize_scenario_affiliations(
                _scenario(source),
                _component(source),
            )

    def test_undeclared_component_is_rejected_and_legacy_scenario_stays_explicit(self) -> None:
        source = _source_snapshot()
        scenario = _scenario(None)

        self.assertIsNone(materialize_scenario_affiliations(scenario, None))
        with self.assertRaisesRegex(AffiliationMaterializationError, "does not declare"):
            materialize_scenario_affiliations(scenario, _component(source))

    def test_invalid_utf8_payload_is_rejected_before_semantic_decode(self) -> None:
        source = _source_snapshot()
        with self.assertRaisesRegex(AffiliationMaterializationError, "UTF-8"):
            materialize_scenario_affiliations(
                _scenario(source),
                AffiliationComponent("groups:duel", b"\xff"),
            )


if __name__ == "__main__":
    unittest.main()
