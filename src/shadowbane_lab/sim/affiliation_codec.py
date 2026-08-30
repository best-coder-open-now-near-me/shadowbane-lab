"""Canonical JSON boundary for immutable scenario affiliation snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import NoReturn

from shadowbane_lab.protocol import Relation

from .affiliations import (
    AffiliationSnapshot,
    GroupKey,
    GroupKind,
    GroupMembership,
    OwnershipEdge,
    RelationOverride,
    RelationSubject,
)

AFFILIATION_SNAPSHOT_SCHEMA = "shadowbane-lab.affiliation-snapshot.v1"


class AffiliationCodecError(ValueError):
    """Raised when affiliation data is not strict, canonicalizable v1 data."""


def affiliation_snapshot_to_data(snapshot: AffiliationSnapshot) -> dict[str, object]:
    """Return a deterministic, plain-data representation of ``snapshot``."""

    if not isinstance(snapshot, AffiliationSnapshot):
        raise TypeError("snapshot must be an AffiliationSnapshot")

    memberships = sorted(
        snapshot.memberships,
        key=lambda item: (
            item.entity_id,
            item.group_key.kind.value,
            item.group_key.group_id,
            "" if item.role is None else item.role,
        ),
    )
    ownership_edges = sorted(
        snapshot.ownership_edges,
        key=lambda item: (item.owner_id, item.owned_id),
    )
    relation_overrides = sorted(
        (_canonical_override(item) for item in snapshot.relation_overrides),
        key=lambda item: (
            item.left.sort_key,
            item.right.sort_key,
            item.relation.value,
            item.symmetric,
        ),
    )

    return {
        "schema": AFFILIATION_SNAPSHOT_SCHEMA,
        "revision": snapshot.revision,
        "memberships": [
            {
                "entity_id": item.entity_id,
                "group": _group_key_to_data(item.group_key),
                "role": item.role,
            }
            for item in memberships
        ],
        "ownership_edges": [
            {"owner_id": item.owner_id, "owned_id": item.owned_id}
            for item in ownership_edges
        ],
        "relation_overrides": [
            {
                "left": _subject_to_data(item.left),
                "right": _subject_to_data(item.right),
                "relation": item.relation.value,
                "symmetric": item.symmetric,
            }
            for item in relation_overrides
        ],
    }


def affiliation_snapshot_from_data(payload: object) -> AffiliationSnapshot:
    """Parse strict v1 plain data into a validated immutable snapshot."""

    root = _object(payload, "snapshot")
    _fields(
        root,
        required={
            "schema",
            "revision",
            "memberships",
            "ownership_edges",
            "relation_overrides",
        },
        location="snapshot",
    )
    if root["schema"] != AFFILIATION_SNAPSHOT_SCHEMA:
        raise AffiliationCodecError(
            f"snapshot.schema must be {AFFILIATION_SNAPSHOT_SCHEMA!r}"
        )

    revision = _integer(root["revision"], "snapshot.revision", minimum=0)
    memberships = tuple(
        _membership_from_data(item, f"snapshot.memberships[{index}]")
        for index, item in enumerate(_array(root["memberships"], "snapshot.memberships"))
    )
    ownership_edges = tuple(
        _ownership_from_data(item, f"snapshot.ownership_edges[{index}]")
        for index, item in enumerate(
            _array(root["ownership_edges"], "snapshot.ownership_edges")
        )
    )
    relation_overrides = tuple(
        _override_from_data(item, f"snapshot.relation_overrides[{index}]")
        for index, item in enumerate(
            _array(root["relation_overrides"], "snapshot.relation_overrides")
        )
    )

    try:
        return AffiliationSnapshot(
            revision=revision,
            memberships=memberships,
            ownership_edges=ownership_edges,
            relation_overrides=relation_overrides,
        )
    except ValueError as exc:
        raise AffiliationCodecError(f"snapshot is invalid: {exc}") from exc


def encode_affiliation_snapshot(snapshot: AffiliationSnapshot) -> bytes:
    """Encode ``snapshot`` as stable UTF-8 JSON suitable for signatures."""

    return json.dumps(
        affiliation_snapshot_to_data(snapshot),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_affiliation_snapshot(
    payload: bytes | bytearray | memoryview | str,
) -> AffiliationSnapshot:
    """Decode strict JSON, rejecting duplicate keys and non-standard constants."""

    if isinstance(payload, str):
        text = payload
    elif isinstance(payload, (bytes, bytearray, memoryview)):
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AffiliationCodecError("snapshot JSON must be valid UTF-8") from exc
    else:
        raise TypeError("payload must be UTF-8 bytes or text")

    try:
        data = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise AffiliationCodecError(f"invalid snapshot JSON: {exc.msg}") from exc
    return affiliation_snapshot_from_data(data)


def affiliation_snapshot_digest(snapshot: AffiliationSnapshot) -> str:
    """Return the SHA-256 digest of the canonical encoded snapshot."""

    return hashlib.sha256(encode_affiliation_snapshot(snapshot)).hexdigest()


def _canonical_override(override: RelationOverride) -> RelationOverride:
    if not override.symmetric or override.left.sort_key <= override.right.sort_key:
        return override
    return RelationOverride(
        left=override.right,
        right=override.left,
        relation=override.relation,
        symmetric=True,
    )


def _group_key_to_data(group_key: GroupKey) -> dict[str, str]:
    return {"kind": group_key.kind.value, "group_id": group_key.group_id}


def _subject_to_data(subject: RelationSubject) -> dict[str, object]:
    if subject.entity_id is not None:
        return {"kind": "entity", "entity_id": subject.entity_id}
    assert subject.group_key is not None
    return {"kind": "group", "group": _group_key_to_data(subject.group_key)}


def _membership_from_data(payload: object, location: str) -> GroupMembership:
    value = _object(payload, location)
    _fields(value, required={"entity_id", "group", "role"}, location=location)
    role = value["role"]
    if role is not None:
        role = _string(role, f"{location}.role")
    return GroupMembership(
        entity_id=_string(value["entity_id"], f"{location}.entity_id"),
        group_key=_group_key_from_data(value["group"], f"{location}.group"),
        role=role,
    )


def _ownership_from_data(payload: object, location: str) -> OwnershipEdge:
    value = _object(payload, location)
    _fields(value, required={"owner_id", "owned_id"}, location=location)
    return OwnershipEdge(
        owner_id=_string(value["owner_id"], f"{location}.owner_id"),
        owned_id=_string(value["owned_id"], f"{location}.owned_id"),
    )


def _override_from_data(payload: object, location: str) -> RelationOverride:
    value = _object(payload, location)
    _fields(
        value,
        required={"left", "right", "relation", "symmetric"},
        location=location,
    )
    relation_value = _string(value["relation"], f"{location}.relation")
    try:
        relation = Relation(relation_value)
    except ValueError as exc:
        raise AffiliationCodecError(
            f"{location}.relation is not a known Relation"
        ) from exc
    return RelationOverride(
        left=_subject_from_data(value["left"], f"{location}.left"),
        right=_subject_from_data(value["right"], f"{location}.right"),
        relation=relation,
        symmetric=_boolean(value["symmetric"], f"{location}.symmetric"),
    )


def _subject_from_data(payload: object, location: str) -> RelationSubject:
    value = _object(payload, location)
    kind = _string(value.get("kind"), f"{location}.kind")
    if kind == "entity":
        _fields(value, required={"kind", "entity_id"}, location=location)
        return RelationSubject.for_entity(
            _string(value["entity_id"], f"{location}.entity_id")
        )
    if kind == "group":
        _fields(value, required={"kind", "group"}, location=location)
        return RelationSubject.for_group(
            _group_key_from_data(value["group"], f"{location}.group")
        )
    raise AffiliationCodecError(f"{location}.kind must be 'entity' or 'group'")


def _group_key_from_data(payload: object, location: str) -> GroupKey:
    value = _object(payload, location)
    _fields(value, required={"kind", "group_id"}, location=location)
    kind_value = _string(value["kind"], f"{location}.kind")
    try:
        kind = GroupKind(kind_value)
    except ValueError as exc:
        raise AffiliationCodecError(f"{location}.kind is not a known GroupKind") from exc
    return GroupKey(
        kind=kind,
        group_id=_string(value["group_id"], f"{location}.group_id"),
    )


def _unique_object(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AffiliationCodecError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise AffiliationCodecError(f"non-standard JSON constant {value!r} is not allowed")


def _object(payload: object, location: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise AffiliationCodecError(f"{location} must be an object")
    if any(not isinstance(key, str) for key in payload):
        raise AffiliationCodecError(f"{location} keys must be strings")
    return payload


def _array(payload: object, location: str) -> Sequence[object]:
    if isinstance(payload, (str, bytes, bytearray)) or not isinstance(
        payload, Sequence
    ):
        raise AffiliationCodecError(f"{location} must be an array")
    return payload


def _fields(
    payload: Mapping[str, object],
    *,
    required: set[str],
    location: str,
) -> None:
    fields = set(payload)
    missing = sorted(required - fields)
    unknown = sorted(fields - required)
    if missing:
        raise AffiliationCodecError(f"{location} is missing fields: {', '.join(missing)}")
    if unknown:
        raise AffiliationCodecError(f"{location} has unknown fields: {', '.join(unknown)}")


def _string(payload: object, location: str) -> str:
    if not isinstance(payload, str) or not payload.strip():
        raise AffiliationCodecError(f"{location} must be a non-empty string")
    return payload


def _integer(payload: object, location: str, *, minimum: int) -> int:
    if isinstance(payload, bool) or not isinstance(payload, int) or payload < minimum:
        raise AffiliationCodecError(f"{location} must be an integer >= {minimum}")
    return payload


def _boolean(payload: object, location: str) -> bool:
    if not isinstance(payload, bool):
        raise AffiliationCodecError(f"{location} must be boolean")
    return payload
