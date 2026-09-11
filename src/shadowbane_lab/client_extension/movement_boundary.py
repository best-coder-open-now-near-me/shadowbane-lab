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
INPUT_RECORD = struct.Struct("<7Q12I")
INPUT_CURRENT_OFFSET = 56
INPUT_LOSS_OFFSET = 160
INPUT_EVENTS_OFFSET = 264
V2_HEADER_SIZE = INPUT_EVENTS_OFFSET + CAPACITY * INPUT_RECORD.size
V2_SIZE = V2_HEADER_SIZE + CAPACITY * RECORD.size
LIFETIME_RECORD = struct.Struct("<6Q8I")
LIFETIME_CAPACITY = 64
LIFETIME_CURRENT_OFFSET = V2_SIZE + 16
LIFETIME_FIRST_OFFSET = LIFETIME_CURRENT_OFFSET + LIFETIME_RECORD.size
LIFETIME_EVENTS_OFFSET = LIFETIME_FIRST_OFFSET + LIFETIME_RECORD.size
V3_SIZE = LIFETIME_EVENTS_OFFSET + LIFETIME_CAPACITY * LIFETIME_RECORD.size
LIFETIME_FIELDS = (
    "sequence",
    "tick_ms",
    "previous_epoch",
    "epoch",
    "observed_epoch",
    "watch_generation",
    "cause",
    "outcome",
    "failure_stage",
    "changed_fields",
    "valid_fields",
    "notice_role",
    "finalizer_flags",
    "thread_id",
)
LIFETIME_CAUSES = (
    "invalid",
    "stable",
    "first_watch",
    "tuple_changed",
    "capture_failed",
    "capture_changed",
    "reference_notice",
    "world_notice",
    "binding_lost",
    "arm_rejected",
    "terminal",
    "exhausted",
    "rearmed",
)
LIFETIME_STAGES = (
    "none",
    "window",
    "receiver",
    "mode",
    "actor",
    "world",
    "identity",
    "position",
    "pose",
    "parent",
    "unrecorded_callbacks",
    "overlapping_callback",
    "matching_destruction",
    "reference",
    "binding",
)
INPUT_FIELDS = (
    "sequence",
    "tick_ms",
    "sample_tick_ms",
    "interval_ms",
    "previous_generation",
    "generation",
    "scene",
    "thread_id",
    "window",
    "previous_owner",
    "owner",
    "reason",
    "kind",
    "keys",
    "suppressed_keys",
    "original_keys",
    "gates",
    "policy",
    "key_event",
)
STOP_REASONS = (
    "release",
    "takeover",
    "focus",
    "ui",
    "disabled",
    "device_lost",
    "capture_lost",
    "scene_changed",
    "stalled",
    "shutdown",
    "binding_failure",
)
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


def mapping_name(process_id: int, creation_filetime: int, schema: int = 1) -> str:
    if not 0 < process_id <= 0xFFFFFFFF or not 0 < creation_filetime <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("exact process ID and creation FILETIME are required")
    if schema not in (1, 2, 3):
        raise ValueError("unsupported movement trace schema")
    version = f".v{schema}" if schema >= 2 else ""
    prefix = f"Local\\ShadowbaneLab.Extension.MovementBoundary{version}"
    return f"{prefix}.{process_id}.{creation_filetime}"


def stable_records(
    first: bytes,
    second: bytes,
    process_id: int,
    creation_filetime: int,
) -> list[dict[str, int | float]]:
    """Accept only committed slots unchanged across two independent memory reads."""
    if len(first) != len(second) or len(first) not in (SIZE, V2_SIZE, V3_SIZE):
        raise ValueError("movement boundary mapping size mismatch")
    expected_schema = {SIZE: 1, V2_SIZE: 2, V3_SIZE: 3}[len(first)]
    header_size = HEADER.size if expected_schema == 1 else V2_HEADER_SIZE
    latest = []
    for payload in (first, second):
        magic, schema, size, count, pid, creation, sequence, dropped, enabled = HEADER.unpack_from(
            payload
        )
        if (
            (magic, schema, size, count, pid, creation)
            != (
                f"WBMVTR{expected_schema}\0".encode(),
                expected_schema,
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
        offset = header_size + ((sequence - 1) % CAPACITY) * RECORD.size
        a, b = first[offset : offset + RECORD.size], second[offset : offset + RECORD.size]
        if a != b:
            continue
        values = RECORD.unpack(a)
        if values[0] != sequence or not math.isfinite(values[2]) or values[-1] not in (0, 1):
            continue
        result.append(dict(zip(FIELDS, values, strict=True)))
    return result


def _input_record(
    first: bytes, second: bytes, offset: int, sequence: int | None = None
) -> dict | None:
    a = first[offset : offset + INPUT_RECORD.size]
    if a != second[offset : offset + INPUT_RECORD.size]:
        return None
    record = dict(zip(INPUT_FIELDS, INPUT_RECORD.unpack(a), strict=True))
    kind, reason, event = record["kind"], record["reason"], record["key_event"]
    if (
        not 0 < record["sequence"] <= 0x7FFFFFFFFFFFFFFF
        or (sequence is not None and record["sequence"] != sequence)
        or kind not in (1, 2, 3)
        or record["previous_owner"] > 2
        or record["owner"] > 2
        or (record["keys"] | record["suppressed_keys"] | record["original_keys"]) > 15
        or record["gates"] > 4095
        or record["policy"] > 511
        or (reason >= len(STOP_REASONS) if kind == 2 else reason != 0xFFFFFFFF)
        or (event > 63 or not 1 <= (event & 7) <= 4 if kind == 3 else event != 0)
    ):
        return None
    record["stop_reason"] = STOP_REASONS[reason] if kind == 2 else None
    return record


def stable_input_records(
    first: bytes, second: bytes, process_id: int, creation_filetime: int
) -> dict:
    """Read schema-2 passive diagnostics; command Status and its reserved bytes are untouched."""
    stable_records(first, second, process_id, creation_filetime)
    if len(first) not in (V2_SIZE, V3_SIZE):
        raise ValueError("input diagnostics require movement trace schema 2 or 3")
    start, end = (struct.unpack_from("<Q", payload, HEADER.size)[0] for payload in (first, second))
    if end < start or end > 0x7FFFFFFFFFFFFFFF:
        raise ValueError("input transition sequence regressed or overflowed")
    events = []
    for sequence in range(max(1, end - CAPACITY + 1), start + 1):
        record = _input_record(
            first,
            second,
            INPUT_EVENTS_OFFSET + ((sequence - 1) % CAPACITY) * INPUT_RECORD.size,
            sequence,
        )
        if record is not None:
            events.append(record)
    return {
        "current": _input_record(first, second, INPUT_CURRENT_OFFSET),
        "last_owner_loss": _input_record(first, second, INPUT_LOSS_OFFSET),
        "events": events,
        "write_sequence": end,
    }


def stable_lifetime_records(
    first: bytes, second: bytes, process_id: int, creation_filetime: int
) -> dict:
    """Read cause-only v3 diagnostics; retained origins are not fresh observations."""
    stable_records(first, second, process_id, creation_filetime)
    if len(first) != V3_SIZE:
        raise ValueError("lifetime diagnostics require movement trace schema 3")
    start, end = (struct.unpack_from("<Q", p, V2_SIZE + 8)[0] for p in (first, second))
    if end < start or end > 0x7FFFFFFFFFFFFFFF:
        raise ValueError("lifetime sequence regressed or overflowed")
    published_tick = struct.unpack_from("<Q", second, V2_SIZE)[0]

    def read(offset: int, expected: int | None = None) -> dict | None:
        a = first[offset : offset + LIFETIME_RECORD.size]
        if a != second[offset : offset + LIFETIME_RECORD.size]:
            return None
        r = dict(zip(LIFETIME_FIELDS, LIFETIME_RECORD.unpack(a), strict=True))
        if (
            not 0 < r["sequence"] <= start
            or (expected is not None and r["sequence"] != expected)
            or not 0 < r["cause"] < len(LIFETIME_CAUSES)
            or r["outcome"] > 2
            or r["failure_stage"] >= len(LIFETIME_STAGES)
            or (r["changed_fields"] | r["valid_fields"]) > 63
            or r["notice_role"] > 7
            or r["tick_ms"] > published_tick
            or (r["changed_fields"] and r["valid_fields"] != 63)
        ):
            return None
        r["cause_name"] = LIFETIME_CAUSES[r["cause"]]
        r["failure_stage_name"] = LIFETIME_STAGES[r["failure_stage"]]
        r["retained"] = r["sequence"] < end
        r["age_ms"] = published_tick - r["tick_ms"]
        return r

    events = []
    for seq in range(max(1, end - LIFETIME_CAPACITY + 1), start + 1):
        r = read(
            LIFETIME_EVENTS_OFFSET + ((seq - 1) % LIFETIME_CAPACITY) * LIFETIME_RECORD.size, seq
        )
        if r is not None:
            events.append(r)
    return {
        "current": read(LIFETIME_CURRENT_OFFSET),
        "first_invalidation": read(LIFETIME_FIRST_OFFSET),
        "events": events,
        "write_sequence": end,
        "published_tick_ms": published_tick,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-id", required=True, type=int)
    parser.add_argument("--creation-filetime", required=True, type=int)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument(
        "--schema",
        type=int,
        choices=(1, 2, 3),
        default=3,
        help="3 includes lifetime causes; select 1 or 2 explicitly for older clients",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 300:
        parser.error("seconds must be in (0, 300]")
    name = mapping_name(args.process_id, args.creation_filetime, args.schema)
    size = {1: SIZE, 2: V2_SIZE, 3: V3_SIZE}[args.schema]
    input_last = {"current": 0, "last_owner_loss": 0, "events": 0}
    lifetime_last = {"current": 0, "first_invalidation": 0, "events": 0}
    memory = WindowsSharedMemorySnapshotReader()
    deadline, last = time.monotonic() + args.seconds, 0
    with args.output.open("x", encoding="utf-8") as output:
        output.write(
            json.dumps(
                {
                    "schema": args.schema,
                    "process_id": args.process_id,
                    "creation_filetime": args.creation_filetime,
                    "kind": "passive_update_boundary",
                }
            )
            + "\n"
        )
        while time.monotonic() < deadline:
            first, second = memory.read(name, size), memory.read(name, size)
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
            if args.schema >= 2:
                inputs = stable_input_records(
                    first, second, args.process_id, args.creation_filetime
                )
                for stream in ("current", "last_owner_loss", "events"):
                    entries = inputs[stream] if stream == "events" else [inputs[stream]]
                    for record in entries:
                        if record is not None and record["sequence"] > input_last[stream]:
                            output.write(
                                json.dumps(
                                    {
                                        **record,
                                        "stream": stream,
                                        "producer_dropped": producer_dropped,
                                        "missing_before": record["sequence"]
                                        - input_last[stream]
                                        - 1
                                        if stream == "events"
                                        else None,
                                    }
                                )
                                + "\n"
                            )
                            input_last[stream] = record["sequence"]
            if args.schema == 3:
                lifetime = stable_lifetime_records(
                    first, second, args.process_id, args.creation_filetime
                )
                for stream in ("current", "first_invalidation", "events"):
                    entries = lifetime[stream] if stream == "events" else [lifetime[stream]]
                    for record in entries:
                        if record is not None and record["sequence"] > lifetime_last[stream]:
                            output.write(
                                json.dumps(
                                    {
                                        **record,
                                        "stream": f"lifetime_{stream}",
                                        "published_tick_ms": lifetime["published_tick_ms"],
                                        "producer_dropped": producer_dropped,
                                        "missing_before": record["sequence"]
                                        - lifetime_last[stream]
                                        - 1
                                        if stream == "events"
                                        else None,
                                    }
                                )
                                + "\n"
                            )
                            lifetime_last[stream] = record["sequence"]
            output.flush()
            time.sleep(0.05)


if __name__ == "__main__":
    main()
