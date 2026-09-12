"""Passive decoded-action evidence; never supplies retaliation authority.

A record precedes the decoder's final stream validation and carries no verified
hit/miss/hostility meaning. No actor pointer or selected-target inference is used.
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


def mapping_name(process_id: int, creation_filetime: int) -> str:
    for value, maximum in ((process_id, 0xFFFFFFFF), (creation_filetime, 0xFFFFFFFFFFFFFFFF)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
            raise ValueError("exact process ID and creation FILETIME are required")
    return f"Local\\ShadowbaneLab.Extension.TargetedAction.v1.{process_id}.{creation_filetime}"


def stable_records(
    first: bytes, second: bytes, process_id: int, creation_filetime: int
) -> list[dict[str, object]]:
    """Keep only unchanged committed records from two exact-lifetime snapshots."""
    mapping_name(process_id, creation_filetime)
    headers = []
    for data in (first, second):
        if len(data) != SIZE:
            raise ValueError("invalid targeted-action trace size")
        header = HEADER.unpack_from(data)
        if header[:6] != (b"WBTACT1\0", 1, RECORD.size, CAPACITY, process_id, creation_filetime):
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
        if any(fields[12:]) or (not fields[4] and any(fields[5:8])) or (
            not fields[8] and any(fields[9:12])
        ):
            raise ValueError("nonzero absent/reserved targeted-action fields")
        records.append({
            "sequence": sequence,
            "tick_ms": tick,
            "thread_id": thread,
            "actor_key": fields[:2],
            "victim_key": fields[2:4],
            "primary_raw": fields[4:8],
            "secondary_raw": fields[8:12],
            "stage": "decoded_before_final_stream_validation",
            "combat_authority": False,
        })
    return sorted(records, key=lambda item: item["sequence"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--creation-filetime", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error("seconds must be in (0, 3600]")
    name = mapping_name(args.process_id, args.creation_filetime)
    memory = WindowsSharedMemorySnapshotReader()
    deadline = time.monotonic() + args.seconds
    last = 0
    with args.output.open("x", encoding="utf-8") as output:
        while time.monotonic() < deadline:
            first, second = memory.read(name, SIZE), memory.read(name, SIZE)
            records = stable_records(first, second, args.process_id, args.creation_filetime)
            header = HEADER.unpack_from(second)
            for record in records:
                sequence = int(record["sequence"])
                if sequence <= last:
                    continue
                output.write(json.dumps({**record, "process_id": args.process_id,
                    "creation_filetime": args.creation_filetime,
                    "missing_before": sequence - last - 1, "overwritten": header[7]}) + "\n")
                last = sequence
            output.flush()
            if header[8]:
                break
            time.sleep(0.05)


if __name__ == "__main__":
    main()
