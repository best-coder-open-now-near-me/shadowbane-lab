"""Read-only, exact-lifetime collector for the opt-in native update boundary trace.

This is investigation evidence, not proof of native actuation or a controls capability.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import time
from pathlib import Path

from .event_reader import WindowsSharedMemorySnapshotReader

HEADER = struct.Struct("<8sIIIIQQii")
RECORD = struct.Struct("<QQd12I")
CAPACITY = 256
SIZE = HEADER.size + CAPACITY * RECORD.size
FIELDS = (
    "sequence",
    "tick_ms",
    "native_delta",
    "thread_id",
    "foreground_thread",
    "foreground_pid",
    "receiver",
    "actor",
    "game_mode",
    "ui_candidate",
    "modal_candidate",
    "path_count",
    "movement_state",
    "caller_rva",
    "read_valid",
)


def mapping_name(process_id: int, creation_filetime: int) -> str:
    if not 0 < process_id <= 0xFFFFFFFF or not 0 < creation_filetime <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("exact process ID and creation FILETIME are required")
    return f"Local\\ShadowbaneLab.Extension.MovementBoundary.{process_id}.{creation_filetime}"


def stable_records(
    first: bytes,
    second: bytes,
    process_id: int,
    creation_filetime: int,
) -> list[dict[str, int | float]]:
    """Accept only committed slots unchanged across two independent memory reads."""
    latest = []
    for payload in (first, second):
        if len(payload) != SIZE:
            raise ValueError("movement boundary mapping size mismatch")
        magic, schema, size, count, pid, creation, sequence, dropped, enabled = HEADER.unpack_from(
            payload
        )
        if (
            (magic, schema, size, count, pid, creation)
            != (
                b"WBMVTR1\0",
                1,
                RECORD.size,
                CAPACITY,
                process_id,
                creation_filetime,
            )
            or enabled not in (0, 1)
            or dropped < 0
            or sequence > 0x7FFFFFFFFFFFFFFF
        ):
            raise ValueError("movement boundary identity or schema mismatch")
        latest.append(sequence)
    if latest[1] < latest[0]:
        raise ValueError("movement boundary sequence regressed")
    result = []
    for sequence in range(max(1, latest[1] - CAPACITY + 1), latest[0] + 1):
        offset = HEADER.size + ((sequence - 1) % CAPACITY) * RECORD.size
        a, b = first[offset : offset + RECORD.size], second[offset : offset + RECORD.size]
        if a != b:
            continue
        values = RECORD.unpack(a)
        if values[0] != sequence or not math.isfinite(values[2]) or values[-1] not in (0, 1):
            continue
        result.append(dict(zip(FIELDS, values, strict=True)))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-id", required=True, type=int)
    parser.add_argument("--creation-filetime", required=True, type=int)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 300:
        parser.error("seconds must be in (0, 300]")
    name = mapping_name(args.process_id, args.creation_filetime)
    memory = WindowsSharedMemorySnapshotReader()
    deadline, last = time.monotonic() + args.seconds, 0
    with args.output.open("x", encoding="utf-8") as output:
        output.write(
            json.dumps(
                {
                    "schema": 1,
                    "process_id": args.process_id,
                    "creation_filetime": args.creation_filetime,
                    "kind": "passive_update_boundary",
                }
            )
            + "\n"
        )
        while time.monotonic() < deadline:
            first, second = memory.read(name, SIZE), memory.read(name, SIZE)
            records = stable_records(first, second, args.process_id, args.creation_filetime)
            producer_dropped = HEADER.unpack_from(second)[7]
            for record in records:
                sequence = int(record["sequence"])
                if sequence > last:
                    output.write(
                        json.dumps(
                            {
                                **record,
                                "missing_before": sequence - last - 1,
                                "producer_dropped": producer_dropped,
                            }
                        )
                        + "\n"
                    )
                    last = sequence
            output.flush()
            time.sleep(0.05)


if __name__ == "__main__":
    main()
