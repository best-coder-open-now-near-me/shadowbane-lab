"""Compatibility API over the canonical affiliation snapshot interchange.

``affiliation_io`` owns the serialized representation.  This module preserves the
newer byte-oriented helper names without maintaining a second schema or parser.
"""

from __future__ import annotations

from collections.abc import Mapping

from .affiliation_io import (
    AFFILIATION_SNAPSHOT_SCHEMA_VERSION,
    AffiliationSnapshotFormatError,
    affiliation_snapshot_digest as _affiliation_snapshot_digest,
    affiliation_snapshot_from_dict,
    affiliation_snapshot_to_dict,
    dump_affiliation_snapshot,
    load_affiliation_snapshot_text,
)
from .affiliations import AffiliationSnapshot

AFFILIATION_SNAPSHOT_SCHEMA = (
    f"shadowbane-lab.affiliation-snapshot.v{AFFILIATION_SNAPSHOT_SCHEMA_VERSION}"
)
AffiliationCodecError = AffiliationSnapshotFormatError


def affiliation_snapshot_to_data(snapshot: AffiliationSnapshot) -> dict[str, object]:
    """Return the canonical plain-data representation owned by ``affiliation_io``."""

    return affiliation_snapshot_to_dict(snapshot)


def affiliation_snapshot_from_data(payload: object) -> AffiliationSnapshot:
    """Decode strict canonical data through the single affiliation parser."""

    if not isinstance(payload, Mapping):
        raise AffiliationCodecError("affiliation snapshot must be an object")
    return affiliation_snapshot_from_dict(payload)


def encode_affiliation_snapshot(snapshot: AffiliationSnapshot) -> bytes:
    """Encode a snapshot as canonical UTF-8 JSON bytes."""

    return dump_affiliation_snapshot(snapshot).encode("utf-8")


def decode_affiliation_snapshot(
    payload: bytes | bytearray | memoryview | str,
) -> AffiliationSnapshot:
    """Decode strict canonical JSON from text or UTF-8 bytes."""

    if isinstance(payload, str):
        text = payload
    elif isinstance(payload, (bytes, bytearray, memoryview)):
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AffiliationCodecError(
                "affiliation snapshot JSON must be valid UTF-8"
            ) from exc
    else:
        raise TypeError("payload must be UTF-8 bytes or text")
    return load_affiliation_snapshot_text(text)


def affiliation_snapshot_digest(snapshot: AffiliationSnapshot) -> str:
    """Return the canonical SHA-256 snapshot digest."""

    return _affiliation_snapshot_digest(snapshot)


__all__ = (
    "AFFILIATION_SNAPSHOT_SCHEMA",
    "AffiliationCodecError",
    "affiliation_snapshot_digest",
    "affiliation_snapshot_from_data",
    "affiliation_snapshot_to_data",
    "decode_affiliation_snapshot",
    "encode_affiliation_snapshot",
)
