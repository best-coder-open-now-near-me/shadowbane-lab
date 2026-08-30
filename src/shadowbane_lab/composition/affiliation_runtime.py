"""Strict materialization of opaque scenario affiliation components."""

from __future__ import annotations

from dataclasses import dataclass

from shadowbane_lab.composition.model import ResolvedScenarioView
from shadowbane_lab.sim.affiliation_io import (
    AffiliationSnapshotFormatError,
    affiliation_snapshot_digest,
    load_affiliation_snapshot_text,
)
from shadowbane_lab.sim.affiliations import (
    AffiliationSnapshot,
    GroupMembership,
    OwnershipEdge,
    RelationOverride,
    RelationSubject,
)


class AffiliationMaterializationError(ValueError):
    """Raised when a scenario component cannot be verified and bound exactly."""


@dataclass(frozen=True, slots=True)
class AffiliationComponent:
    """Content-addressed canonical affiliation payload supplied beside a case."""

    snapshot_id: str
    payload: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.payload, bytes) or not self.payload:
            raise ValueError("payload must be non-empty UTF-8 bytes")

    @classmethod
    def from_text(cls, snapshot_id: str, payload: str) -> AffiliationComponent:
        if not isinstance(payload, str):
            raise ValueError("payload must be text")
        return cls(snapshot_id, payload.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class MaterializedAffiliations:
    """Verified source identity plus the runtime-entity-bound immutable snapshot."""

    snapshot_id: str
    source_digest: str
    source_revision: int
    snapshot: AffiliationSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.source_digest, str) or len(self.source_digest) != 64:
            raise ValueError("source_digest must be a SHA-256 hex digest")
        try:
            int(self.source_digest, 16)
        except ValueError as exc:
            raise ValueError("source_digest must be a SHA-256 hex digest") from exc
        if (
            isinstance(self.source_revision, bool)
            or not isinstance(self.source_revision, int)
            or self.source_revision < 0
        ):
            raise ValueError("source_revision must be a non-negative integer")
        if not isinstance(self.snapshot, AffiliationSnapshot):
            raise ValueError("snapshot must be an AffiliationSnapshot")


def materialize_scenario_affiliations(
    scenario: ResolvedScenarioView,
    component: AffiliationComponent | None,
) -> MaterializedAffiliations | None:
    """Verify payload identity and bind affiliation IDs to runtime entity IDs.

    The case layer remains opaque: it carries only the component identifier, digest,
    revision, and bytes. This boundary is the first place group semantics are parsed.
    """

    if not isinstance(scenario, ResolvedScenarioView):
        raise ValueError("scenario must be a ResolvedScenarioView")
    declared = (
        scenario.affiliation_snapshot_id is not None
        or scenario.affiliation_snapshot_digest is not None
    )
    if not declared:
        if component is not None:
            raise AffiliationMaterializationError(
                "scenario does not declare an affiliation component"
            )
        return None
    if scenario.affiliation_snapshot_id is None:
        raise AffiliationMaterializationError(
            "scenario affiliation_snapshot_id is required with a digest"
        )
    if scenario.affiliation_snapshot_digest is None:
        raise AffiliationMaterializationError(
            "scenario affiliation_snapshot_digest is required with an id"
        )
    if component is None:
        raise AffiliationMaterializationError(
            "scenario affiliation component payload is missing"
        )
    if component.snapshot_id != scenario.affiliation_snapshot_id:
        raise AffiliationMaterializationError(
            "affiliation component id does not match the scenario declaration"
        )

    try:
        text = component.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AffiliationMaterializationError(
            "affiliation component must be valid UTF-8"
        ) from exc
    try:
        source = load_affiliation_snapshot_text(text)
    except AffiliationSnapshotFormatError as exc:
        raise AffiliationMaterializationError(
            f"affiliation component is invalid: {exc}"
        ) from exc

    digest = affiliation_snapshot_digest(source)
    if digest != scenario.affiliation_snapshot_digest:
        raise AffiliationMaterializationError(
            "affiliation component digest does not match the scenario declaration"
        )
    if source.revision != scenario.affiliation_revision:
        raise AffiliationMaterializationError(
            "affiliation component revision does not match the scenario declaration"
        )

    runtime_entity_by_affiliation_id: dict[str, str] = {}
    for slot in scenario.slots:
        affiliation_entity_id = slot.affiliation_entity_id or slot.entity_id
        existing = runtime_entity_by_affiliation_id.get(affiliation_entity_id)
        if existing is not None:
            raise AffiliationMaterializationError(
                "scenario slots contain duplicate affiliation entity ids"
            )
        runtime_entity_by_affiliation_id[affiliation_entity_id] = slot.entity_id

    unknown = set(source.entity_ids) - set(runtime_entity_by_affiliation_id)
    if unknown:
        raise AffiliationMaterializationError(
            "affiliation component references entities absent from the scenario: "
            + ", ".join(sorted(unknown))
        )

    snapshot = _remap_snapshot(source, runtime_entity_by_affiliation_id)
    return MaterializedAffiliations(
        snapshot_id=component.snapshot_id,
        source_digest=digest,
        source_revision=source.revision,
        snapshot=snapshot,
    )


def _remap_snapshot(
    snapshot: AffiliationSnapshot,
    runtime_entity_by_affiliation_id: dict[str, str],
) -> AffiliationSnapshot:
    return AffiliationSnapshot(
        revision=snapshot.revision,
        memberships=tuple(
            GroupMembership(
                runtime_entity_by_affiliation_id[membership.entity_id],
                membership.group_key,
                membership.role,
            )
            for membership in snapshot.memberships
        ),
        ownership_edges=tuple(
            OwnershipEdge(
                runtime_entity_by_affiliation_id[edge.owner_id],
                runtime_entity_by_affiliation_id[edge.owned_id],
            )
            for edge in snapshot.ownership_edges
        ),
        relation_overrides=tuple(
            RelationOverride(
                _remap_subject(override.left, runtime_entity_by_affiliation_id),
                _remap_subject(override.right, runtime_entity_by_affiliation_id),
                override.relation,
                override.symmetric,
            )
            for override in snapshot.relation_overrides
        ),
    )


def _remap_subject(
    subject: RelationSubject,
    runtime_entity_by_affiliation_id: dict[str, str],
) -> RelationSubject:
    if subject.entity_id is not None:
        return RelationSubject.for_entity(
            runtime_entity_by_affiliation_id[subject.entity_id]
        )
    assert subject.group_key is not None
    return RelationSubject.for_group(subject.group_key)


__all__ = (
    "AffiliationComponent",
    "AffiliationMaterializationError",
    "MaterializedAffiliations",
    "materialize_scenario_affiliations",
)
