"""Build an offline item appearance candidate; never install into a running client."""

from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path

from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.object_navigation import parse_object_navigation_metadata

_HEADER = struct.Struct("<IIII")
_ENTRY = struct.Struct("<IIIII")


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def redirect_item_render(payload: bytes, donor: bytes) -> bytes:
    """Change only the primary render key; leave all gameplay bytes untouched."""
    original = parse_object_navigation_metadata(payload)
    replacement = parse_object_navigation_metadata(donor)
    if original.object_type != 9 or replacement.object_type != 9:
        raise ValueError("appearance redirects require two item objects")
    if original.scale != replacement.scale:
        raise ValueError("item scales differ; explicit alignment qualification is required")
    key = replacement.render_key
    if not key.resource_id:
        raise ValueError("donor has no primary render")
    offset = original.parsed_size - 8
    return (
        payload[:offset] + struct.pack("<II", key.group_id, key.resource_id) + payload[offset + 8 :]
    )


def build_item_appearance_cache(
    source: Path,
    output: Path,
    *,
    source_sha256: str,
    target_key: tuple[int, int],
    donor_key: tuple[int, int],
) -> dict[str, object]:
    """Produce a new, verified CObjects cache; reject stale input and existing output.

    The caller must qualify the donor's render dependencies and attachment first.
    Candidate files are private client assets, never source-controlled exports.
    No backup or live installation is performed here.
    """
    source, output = Path(source), Path(output)
    if _digest(source) != source_sha256.lower():
        raise ValueError("source cache digest mismatch")
    if target_key == donor_key:
        raise ValueError("target and donor must differ")
    with CacheArchive(source) as archive:
        indexed = {(e.group_id, e.resource_id): e for e in archive.entries}
        if len(indexed) != len(archive.entries):
            raise ValueError("duplicate cache keys")
        original = archive.read_resource(indexed[target_key])
        replacement = redirect_item_render(original, archive.read_resource(indexed[donor_key]))
        if original == replacement:
            raise ValueError("target already uses the donor render")
        # Exclusive creation also refuses an alias of the source and pre-existing candidates.
        stream = output.open("xb")
        try:
            with stream, source.open("rb") as raw:
                directory_end = _HEADER.size + len(archive.entries) * _ENTRY.size
                stream.write(bytes(directory_end))
                directory = []
                for entry in archive.entries:
                    key = (entry.group_id, entry.resource_id)
                    if key == target_key:
                        stored, size = replacement, len(replacement)
                    else:
                        raw.seek(entry.data_offset)
                        stored, size = raw.read(entry.stored_size), entry.uncompressed_size
                        if len(stored) != entry.stored_size:
                            raise ValueError("source cache changed during read")
                    directory.append(
                        (entry.group_id, entry.resource_id, stream.tell(), size, len(stored))
                    )
                    stream.write(stored)
                file_size = stream.tell()
                stream.seek(0)
                stream.write(
                    _HEADER.pack(len(directory), directory_end, file_size, archive.header.marker)
                )
                for row in directory:
                    stream.write(_ENTRY.pack(*row))
                stream.flush()
                os.fsync(stream.fileno())
            with CacheArchive(output) as candidate:
                for before, after in zip(archive.entries, candidate.entries, strict=True):
                    key = (before.group_id, before.resource_id)
                    if key != (after.group_id, after.resource_id):
                        raise ValueError("candidate key mismatch")
                    expected = replacement if key == target_key else archive.read_resource(before)
                    if candidate.read_resource(after) != expected:
                        raise ValueError("candidate payload mismatch")
            if _digest(source) != source_sha256.lower():
                raise ValueError("source cache changed during build")
            return {
                "source_sha256": source_sha256.lower(),
                "result_sha256": _digest(output),
                "target_key": target_key,
                "donor_key": donor_key,
                "verified_resources": len(archive.entries),
                "changed_payloads": 1,
                "activation": "client-restart-required",
            }
        except BaseException:
            output.unlink(missing_ok=True)
            raise
