"""Passive decoded-action evidence; never supplies retaliation authority.

A record precedes native queue publication and carries no verified
hit/miss/hostility meaning. Schema 2 adds a decode-spanning lifecycle observation,
not proof of socket queue age. No actor pointer or selected-target inference is used.
"""

from __future__ import annotations

import argparse
import json
import struct
import time
from pathlib import Path

from .event_reader import WindowsSharedMemorySnapshotReader

HEADER = struct.Struct("<8sIIIIQqqII")
RECORD = struct.Struct("<QQII16I")
CAPACITY = 256
SIZE = HEADER.size + RECORD.size * CAPACITY


def mapping_name(process_id: int, creation_filetime: int, *, schema: int = 1) -> str:
    if type(schema) is not int or schema not in (1, 2):
        raise ValueError("unsupported targeted-action schema")
    for value, maximum in ((process_id, 0xFFFFFFFF), (creation_filetime, 0xFFFFFFFFFFFFFFFF)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
            raise ValueError("exact process ID and creation FILETIME are required")
    return (f"Local\\ShadowbaneLab.Extension.TargetedAction.v{schema}."
            f"{process_id}.{creation_filetime}")


def stable_records(
    first: bytes, second: bytes, process_id: int, creation_filetime: int, *, schema: int = 1
) -> list[dict[str, object]]:
    """Keep only unchanged committed records from two exact-lifetime snapshots."""
    mapping_name(process_id, creation_filetime, schema=schema)
    headers = []
    for data in (first, second):
        if len(data) != SIZE:
            raise ValueError("invalid targeted-action trace size")
        header = HEADER.unpack_from(data)
        if header[:6] != (
            f"WBTACT{schema}\0".encode(), schema, RECORD.size, CAPACITY,
            process_id, creation_filetime,
        ):
            raise ValueError("targeted-action trace identity/layout mismatch")
        if header[6] < 0 or header[7] < 0 or header[8] not in (0, 1) or header[9]:
            raise ValueError("invalid targeted-action trace counters")
        headers.append(header)
    if headers[1][6] < headers[0][6] or headers[1][8] < headers[0][8]:
        raise ValueError("targeted-action trace regressed")
    records = []
    for index in range(CAPACITY):
        offset = HEADER.size + index * RECORD.size
        before = first[offset : offset + RECORD.size]
        after = second[offset : offset + RECORD.size]
        if before != after:
            continue
        sequence, tick, thread, caller, *fields = RECORD.unpack(after)
        if not (max(1, headers[1][6] - CAPACITY + 1) <= sequence <= headers[0][6]):
            continue
        if (sequence - 1) % CAPACITY != index or caller != 0x3625BC or not thread:
            raise ValueError("invalid targeted-action record provenance")
        if (schema == 1 and any(fields[12:])) or (not fields[4] and any(fields[5:8])) or (
            not fields[8] and any(fields[9:12])
        ):
            raise ValueError("nonzero absent/reserved targeted-action fields")
        epoch = fields[12] | (fields[13] << 32) if schema == 2 else 0
        if schema == 2 and (
            (not epoch and any(fields[14:16])) or (epoch and not all(fields[14:16]))
        ):
            raise ValueError("incomplete targeted-action lifecycle context")
        records.append({
            "sequence": sequence,
            "tick_ms": tick,
            "thread_id": thread,
            "actor_key": fields[:2],
            "victim_key": fields[2:4],
            "primary_raw": fields[4:8],
            "secondary_raw": fields[8:12],
            "stage": "decoded_before_queue_publication",
            "combat_authority": False,
            "decode_scene_epoch": epoch or None,
            "decode_local_key": fields[14:16] if epoch else None,
        })
    return sorted(records, key=lambda item: item["sequence"])


class TraceCursor:
    """One exact mapping lifetime; failures and closure permanently revoke it.

    Fresh-only starts after the first validated high-water mark. It does not
    certify network age, scene currency, or combat semantics.
    """

    def __init__(self, process_id: int, creation_filetime: int, *, schema: int = 2,
                 include_history: bool = True) -> None:
        mapping_name(process_id, creation_filetime, schema=schema)
        self.process_id = process_id
        self.creation_filetime = creation_filetime
        self.schema = schema
        self.include_history = include_history
        self._previous: tuple[int, int] | None = None
        self._last = 0
        self.closed = False

    def read(self, first: bytes, second: bytes) -> list[dict[str, object]]:
        if self.closed:
            raise ValueError("targeted-action cursor is closed; initialize a new cursor")
        try:
            records = stable_records(first, second, self.process_id,
                                     self.creation_filetime, schema=self.schema)
            before, after = HEADER.unpack_from(first), HEADER.unpack_from(second)
            if after[7] < before[7] or (self._previous is not None and (
                before[6] < self._previous[0] or before[7] < self._previous[1]
            )):
                raise ValueError("targeted-action stream regressed across reads")
            initial = self._previous is None
            if initial and not self.include_history:
                # Skip even an in-flight slot seen only in the second snapshot.
                self._last = after[6]
            self._previous = after[6], after[7]
            result = []
            for record in records:
                sequence = int(record["sequence"])
                if sequence <= self._last:
                    continue
                result.append({**record, "process_id": self.process_id,
                    "creation_filetime": self.creation_filetime,
                    "missing_before": sequence - self._last - 1,
                    "overwritten": after[7]})
                self._last = sequence
            self.closed = bool(after[8])
            return result
        except Exception:
            self.closed = True
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--creation-filetime", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--schema", type=int, choices=(1, 2), default=2)
    parser.add_argument("--fresh-only", action="store_true",
                        help="Skip all records present at the first validated read")
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error("seconds must be in (0, 3600]")
    name = mapping_name(args.process_id, args.creation_filetime, schema=args.schema)
    memory = WindowsSharedMemorySnapshotReader()
    deadline = time.monotonic() + args.seconds
    cursor = TraceCursor(args.process_id, args.creation_filetime, schema=args.schema,
                         include_history=not args.fresh_only)
    with args.output.open("x", encoding="utf-8") as output:
        while time.monotonic() < deadline:
            first, second = memory.read(name, SIZE), memory.read(name, SIZE)
            for record in cursor.read(first, second):
                output.write(json.dumps(record) + "\n")
            output.flush()
            if cursor.closed:
                break
            time.sleep(0.05)


if __name__ == "__main__":
    main()
