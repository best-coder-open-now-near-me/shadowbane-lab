"""Versioned deterministic interchange for immutable affiliation snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from shadowbane_lab.protocol import Relation
from shadowbane_lab.sim.affiliations import (
    AffiliationConfigurationError,
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    OwnershipEdge,
    RelationOverride,
    RelationSubject,
)

AFFILIATION_SNAPSHOT_SCHEMA_VERSION = 1


class AffiliationSnapshotFormatError(AffiliationConfigurationError):
    """Raised when a serialized affiliation snapshot is malformed or unsupported."""


def affiliation_snapshot_to_dict(snapshot: AffiliationSnapshot) -> dict[str, object]:
    """Return a canonical plain-data representation suitable for scenario payloads."""

    if not isinstance(snapshot, AffiliationSnapshot):
        raise AffiliationSnapshotFormatError("snapshot must be an AffiliationSnapshot")
    return {
        "schema_version": AFFILIATION_SNAPSHOT_SCHEMA_VERSION,
        "revision": snapshot.revision,
        "memberships": [
            _membership_payload(membership)
            for membership in sorted(snapshot.memberships, key=_membership_sort_key)
        ],
        "ownership_edges": [
            _ownership_payload(edge)
            for edge in sorted(
                snapshot.ownership_edges,
                key=lambda value: (value.owner_id, value.owned_id),
            )
        ],
        "relation_overrides": [
            _override_payload(override)
            for override in sorted(
                snapshot.relation_overrides,
                key=_override_sort_key,
            )
        ],
    }


def affiliation_snapshot_from_dict(raw: Mapping[str, object]) -> AffiliationSnapshot:
    """Parse one strict schema-version-1 affiliation snapshot payload."""

    if not isinstance(raw, Mapping):
        raise AffiliationSnapshotFormatError("affiliation snapshot must be an object")
    if any(not isinstance(key, str) for key in raw):
        raise AffiliationSnapshotFormatError(
            "affiliation snapshot field names must be strings"
        )
    payload = dict(raw)
    _exact_fields(
        payload,
        {
            "schema_version",
            "revision",
            "memberships",
            "ownership_edges",
            "relation_overrides",
        },
        "affiliation snapshot",
    )
    if payload["schema_version"] != AFFILIATION_SNAPSHOT_SCHEMA_VERSION:
        raise AffiliationSnapshotFormatError(
            "affiliation snapshot must use schema_version 1"
        )
    revision = _non_negative_integer(payload["revision"], "revision")
    memberships_raw = _array(payload["memberships"], "memberships")
    ownership_raw = _array(payload["ownership_edges"], "ownership_edges")
    overrides_raw = _array(payload["relation_overrides"], "relation_overrides")
    try:
        return AffiliationSnapshot(
            revision=revision,
            memberships=tuple(
                _parse_membership(value, index)
                for index, value in enumerate(memberships_raw)
            ),
            ownership_edges=tuple(
                _parse_ownership(value, index)
                for index, value in enumerate(ownership_raw)
            ),
            relation_overrides=tuple(
                _parse_override(value, index)
                for index, value in enumerate(overrides_raw)
            ),
        )
    except AffiliationSnapshotFormatError:
        raise
    except (AffiliationConfigurationError, TypeError, ValueError) as exc:
        raise AffiliationSnapshotFormatError(str(exc)) from exc


def dump_affiliation_snapshot(snapshot: AffiliationSnapshot) -> str:
    """Encode a snapshot as canonical compact JSON."""

    return json.dumps(
        affiliation_snapshot_to_dict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def load_affiliation_snapshot_text(text: str) -> AffiliationSnapshot:
    """Decode canonical or equivalent JSON while rejecting duplicate fields."""

    if not isinstance(text, str):
        raise AffiliationSnapshotFormatError("affiliation snapshot text must be a string")
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonstandard_number,
        )
    except AffiliationSnapshotFormatError:
        raise
    except json.JSONDecodeError as exc:
        raise AffiliationSnapshotFormatError(
            "affiliation snapshot is not valid JSON"
        ) from exc
    if not isinstance(raw, Mapping):
        raise AffiliationSnapshotFormatError("affiliation snapshot must be an object")
    return affiliation_snapshot_from_dict(raw)


def affiliation_snapshot_digest(snapshot: AffiliationSnapshot) -> str:
    """Hash the canonical artifact including schema version and affiliation revision."""

    return hashlib.sha256(dump_affiliation_snapshot(snapshot).encode("utf-8")).hexdigest()


def _membership_payload(membership: GroupMembership) -> dict[str, object]:
    return {
        "entity_id": membership.entity_id,
        "group_key": _group_key_payload(membership.group_key),
        "role": membership.role,
    }


def _membership_sort_key(
    membership: GroupMembership,
) -> tuple[str, str, str, str]:
    return (
        membership.entity_id,
        membership.group_key.kind.value,
        membership.group_key.group_id,
        membership.role or "",
    )


def _ownership_payload(edge: OwnershipEdge) -> dict[str, str]:
    return {
        "owner_id": edge.owner_id,
        "owned_id": edge.owned_id,
    }


def _override_payload(override: RelationOverride) -> dict[str, object]:
    left, right = _canonical_override_subjects(override)
    return {
        "left": _subject_payload(left),
        "right": _subject_payload(right),
        "relation": override.relation.value,
        "symmetric": override.symmetric,
    }


def _override_sort_key(
    override: RelationOverride,
) -> tuple[tuple[str, str, str], tuple[str, str, str], bool, str]:
    left, right = _canonical_override_subjects(override)
    return (
        left.sort_key,
        right.sort_key,
        override.symmetric,
        override.relation.value,
    )


def _canonical_override_subjects(
    override: RelationOverride,
) -> tuple[RelationSubject, RelationSubject]:
    if override.symmetric and override.right.sort_key < override.left.sort_key:
        return override.right, override.left
    return override.left, override.right


def _subject_payload(subject: RelationSubject) -> dict[str, object]:
    return {
        "entity_id": subject.entity_id,
        "group_key": (
            _group_key_payload(subject.group_key)
            if subject.group_key is not None
            else None
        ),
    }


def _group_key_payload(group_key: GroupKey) -> dict[str, str]:
    return {
        "kind": group_key.kind.value,
        "group_id": group_key.group_id,
    }


def _parse_membership(raw: object, index: int) -> GroupMembership:
    path = f"memberships[{index}]"
    value = _object(raw, path)
    _exact_fields(value, {"entity_id", "group_key", "role"}, path)
    role = value["role"]
    if role is not None:
        role = _string(role, f"{path}.role")
    return GroupMembership(
        entity_id=_string(value["entity_id"], f"{path}.entity_id"),
        group_key=_parse_group_key(value["group_key"], f"{path}.group_key"),
        role=role,
    )


def _parse_ownership(raw: object, index: int) -> OwnershipEdge:
    path = f"ownership_edges[{index}]"
    value = _object(raw, path)
    _exact_fields(value, {"owner_id", "owned_id"}, path)
    return OwnershipEdge(
        owner_id=_string(value["owner_id"], f"{path}.owner_id"),
        owned_id=_string(value["owned_id"], f"{path}.owned_id"),
    )


def _parse_override(raw: object, index: int) -> RelationOverride:
    path = f"relation_overrides[{index}]"
    value = _object(raw, path)
    _exact_fields(value, {"left", "right", "relation", "symmetric"}, path)
    relation_raw = _string(value["relation"], f"{path}.relation")
    try:
        relation = Relation(relation_raw)
    except ValueError as exc:
        raise AffiliationSnapshotFormatError(
            f"{path}.relation is unknown: {relation_raw}"
        ) from exc
    symmetric = value["symmetric"]
    if not isinstance(symmetric, bool):
        raise AffiliationSnapshotFormatError(f"{path}.symmetric must be boolean")
    return RelationOverride(
        left=_parse_subject(value["left"], f"{path}.left"),
        right=_parse_subject(value["right"], f"{path}.right"),
        relation=relation,
        symmetric=symmetric,
    )


def _parse_subject(raw: object, path: str) -> RelationSubject:
    value = _object(raw, path)
    _exact_fields(value, {"entity_id", "group_key"}, path)
    entity_id = value["entity_id"]
    group_key = value["group_key"]
    if entity_id is not None:
        entity_id = _string(entity_id, f"{path}.entity_id")
    parsed_group = (
        _parse_group_key(group_key, f"{path}.group_key")
        if group_key is not None
        else None
    )
    return RelationSubject(entity_id=entity_id, group_key=parsed_group)


def _parse_group_key(raw: object, path: str) -> GroupKey:
    value = _object(raw, path)
    _exact_fields(value, {"kind", "group_id"}, path)
    kind_raw = _string(value["kind"], f"{path}.kind")
    try:
        kind = GroupKind(kind_raw)
    except ValueError as exc:
        raise AffiliationSnapshotFormatError(
            f"{path}.kind is unknown: {kind_raw}"
        ) from exc
    return GroupKey(
        kind=kind,
        group_id=_string(value["group_id"], f"{path}.group_id"),
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AffiliationSnapshotFormatError(
                f"affiliation snapshot contains duplicate field {key!r}"
            )
        value[key] = item
    return value


def _reject_nonstandard_number(value: str) -> None:
    raise AffiliationSnapshotFormatError(
        f"affiliation snapshot contains non-standard number {value}"
    )


def _exact_fields(
    raw: Mapping[str, object],
    expected: set[str],
    path: str,
) -> None:
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise AffiliationSnapshotFormatError(
            f"{path} has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise AffiliationSnapshotFormatError(
            f"{path} is missing fields: {', '.join(sorted(missing))}"
        )


def _object(raw: object, path: str) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise AffiliationSnapshotFormatError(f"{path} must be an object")
    if any(not isinstance(key, str) for key in raw):
        raise AffiliationSnapshotFormatError(f"{path} field names must be strings")
    return dict(raw)


def _array(raw: object, path: str) -> list[object]:
    if not isinstance(raw, list):
        raise AffiliationSnapshotFormatError(f"{path} must be an array")
    return raw


def _string(raw: object, path: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise AffiliationSnapshotFormatError(f"{path} must be a non-empty string")
    return raw


def _non_negative_integer(raw: object, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise AffiliationSnapshotFormatError(
            f"{path} must be a non-negative integer"
        )
    return raw
