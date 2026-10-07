"""Passive item/power processing evidence. Never request or application authority.

Run with ``python -m shadowbane_lab.client_extension.item_application_trace``.
Only an existing read-only mapping is opened; no producer, lease or native action.
"""

from __future__ import annotations

import argparse
import json
import struct
import time
from pathlib import Path

from .event_reader import SharedMemorySnapshotReader, WindowsSharedMemorySnapshotReader

HEADER = struct.Struct("<8sIIIIQqqiiq")
RECORD = struct.Struct("<QQIIIIQQIIII16s32sIIII12I")
CAPACITY, RECORD_SIZE = 256, 176
SIZE = HEADER.size + CAPACITY * RECORD_SIZE


class ItemApplicationTraceError(RuntimeError):
    """The optional diagnostic stream cannot supply coherent evidence."""


def _identity(pid, creation):
    for value, maximum in ((pid, 0xFFFFFFFF), (creation, 0xFFFFFFFFFFFFFFFF)):
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("exact process lifetime required")


def mapping_name(pid, creation):
    _identity(pid, creation)
    return f"Local\\ShadowbaneLab.Extension.ItemApplication.v1.{pid}.{creation}"


def parse_snapshot(data: bytes, *, process_id: int, creation: int):
    _identity(process_id, creation)
    if len(data) != SIZE:
        raise ItemApplicationTraceError("item trace size mismatch")
    magic, schema, size, capacity, pid, born, sequence, overwritten, stopped, rejected, drops = (
        HEADER.unpack_from(data)
    )
    if (magic, schema, size, capacity, pid, born) != (
        b"WBITEM1\0",
        1,
        RECORD_SIZE,
        CAPACITY,
        process_id,
        creation,
    ):
        raise ItemApplicationTraceError("item trace identity/layout mismatch")
    if (
        sequence < 0
        or overwritten != max(0, sequence - CAPACITY)
        or stopped not in (0, 1)
        or rejected < 0
        or drops < 0
    ):
        raise ItemApplicationTraceError("invalid item trace counters")
    records = []
    for expected in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        values = RECORD.unpack_from(data, HEADER.size + ((expected - 1) % CAPACITY) * RECORD_SIZE)
        (
            seq,
            tick,
            thread,
            stage,
            kind,
            flags,
            decode,
            scene,
            local_id,
            local_type,
            caller,
            returned,
            request,
            command,
            outcome,
            entry,
            settled,
            history,
            *body,
        ) = values
        reserved = body.pop()
        if (
            seq != expected
            or stage not in (1, 2, 3, 4)
            or kind not in (1, 2)
            or not thread
            or flags & ~7
            or reserved
            or bool(flags & 2) != bool(scene)
            or (scene and (not local_id or local_type != 53))
            or (not scene and (local_id or local_type))
            or (stage == 1 and (decode != seq or caller != 0x3625BC))
            or (flags & 4 and (flags & 3 != 3 or stage not in (2, 3) or not 0 < decode < seq))
            or (stage != 1 and not flags & 4 and decode)
            or (stage != 3 and returned)
        ):
            raise ItemApplicationTraceError("invalid item trace record provenance")
        if not flags & 1 and any(body):
            raise ItemApplicationTraceError("unknown payload contains fields")
        if kind == 1 and (any(body[6:]) or (body[0] != 2 and any(body[4:6]))):
            raise ItemApplicationTraceError("absent item fields are nonzero")
        if stage == 4:
            if (
                not flags & 1
                or flags & 4
                or caller
                or not any(request)
                or not any(command)
                or outcome > 14
                or entry > 2
                or settled > 2
                or history & ~12
            ):
                raise ItemApplicationTraceError("invalid owned return")
            if kind == 1 and (body[:2] != [2, 1] or not all(body[2:4]) or any(body[4:])):
                raise ItemApplicationTraceError("invalid owned item return")
            if kind == 2 and (
                not body[0] or body[1] & ~127 or body[2] > 3 or body[5] > 4
                or body[10] & ~0x3FFFF
                or (body[1] & 64 and not body[1] & 32)
                or (body[1] & 32 and not body[1] & 16)
                or (body[1] & 16 and not body[1] & 1)
                or (body[1] & 2 and not body[1] & 1)
                or (body[1] & 8 and not body[1] & 4)
                or (body[1] & 4 and not body[1] & 2)
                or ((body[3] or body[4]) and not body[1] & 8)
                or (not body[10] & 0x10000 and (body[6] or body[10] & 0xFFFF))
                or (not body[10] & 0x20000 and (body[7] or body[8] or body[9]))
            ):
                raise ItemApplicationTraceError("invalid owned power diagnostic")
        elif any(request) or any(command) or outcome or entry or settled or history:
            raise ItemApplicationTraceError(
                "incoming message has invented local request correlation"
            )
        records.append(
            {
                "sequence": seq,
                "tick_ms": tick,
                "thread_id": thread,
                "stage": {1: "decoded", 2: "processing", 3: "returned", 4: "owned_return"}[stage],
                "kind": "item" if kind == 1 else "power",
                "flags": flags,
                "decode_sequence": decode,
                "scene_epoch": scene,
                "local_key": [local_id, local_type],
                "caller_rva": caller,
                "native_return_raw": returned,
                "request": request.hex() if stage == 4 else None,
                "command_digest": command.hex() if stage == 4 else None,
                "outcome": outcome if stage == 4 else None,
                "entry": entry if stage == 4 else None,
                "local_settlement": settled if stage == 4 else None,
                "history": history if stage == 4 else None,
                "payload_words": body,
                "power_diagnostic": {
                    "power_id": body[0],
                    "native_entered": bool(body[1] & 1),
                    "send_observed": bool(body[1] & 2),
                    "append_observed": bool(body[1] & 4),
                    "followup_entered": bool(body[1] & 8),
                    "use_called": bool(body[1] & 16),
                    "use_returned": bool(body[1] & 32),
                    "use_return_value": bool(body[1] & 64) if body[1] & 32 else None,
                    "receipt_result": body[2],
                    "initiation_epoch": body[3] | body[4] << 32,
                    "availability": body[5],
                    "required_mode_raw": body[6] if body[10] & 0x10000 else None,
                    "actor_mode_raw": body[7] if body[10] & 0x20000 else None,
                    "actor_state_1c_raw": body[8] if body[10] & 0x20000 else None,
                    "actor_state_10_raw": body[9] if body[10] & 0x20000 else None,
                    "definition_274_275_raw": body[10] & 0xFFFF if body[10] & 0x10000 else None,
                } if stage == 4 and kind == 2 else None,
            }
        )
    return {
        "sequence": sequence,
        "overwritten": overwritten,
        "stopped": bool(stopped),
        "rejected": rejected,
        "ticket_drops": drops,
        "records": records,
    }


def _publication_in_progress(data, process_id, creation):
    """Recognize only the native publisher's uncommitted ring-slot window.

    PublishLocked clears/replaces the next slot, then increments overwritten,
    and finally publishes the header sequence. Once the ring wraps, that slot
    still belongs to the old header until the final sequence store.
    """
    if len(data) != SIZE:
        return False
    magic, schema, size, capacity, pid, born, sequence, overwritten, *_ = HEADER.unpack_from(data)
    if (magic, schema, size, capacity, pid, born) != (
        b"WBITEM1\0",
        1,
        RECORD_SIZE,
        CAPACITY,
        process_id,
        creation,
    ) or sequence < CAPACITY:
        return False
    next_slot = HEADER.size + (sequence % CAPACITY) * RECORD_SIZE
    slot_sequence = struct.unpack_from("<Q", data, next_slot)[0]
    return overwritten in (sequence - CAPACITY, sequence - CAPACITY + 1) and slot_sequence in (
        0,
        sequence + 1,
    )


class ItemApplicationTraceReader:
    """Drain a bounded ring without replaying records or hiding evidence gaps.

    The first drain returns retained history explicitly labeled as history. A gap,
    rejected native snapshot or lost lineage ticket permanently marks this capture
    incomplete. Closure and counter regression are terminal for this reader.
    No field grants command admission or proves server acceptance.
    """

    def __init__(self, process_id: int, creation: int, memory: SharedMemorySnapshotReader):
        self.name = mapping_name(process_id, creation)
        self.process_id, self.creation, self.memory = process_id, creation, memory
        self._last = None
        self._terminal = None
        self._incomplete = False
        self._read_errors = 0

    def drain(self):
        if self._terminal:
            raise ItemApplicationTraceError(self._terminal)
        try:
            # Retry observation only; no command is submitted and the accepted
            # cursor stays unchanged until a coherent snapshot is validated.
            for _ in range(3):
                data = self.memory.read(self.name, SIZE)
                stable = data == self.memory.read(self.name, SIZE)
                if stable and not _publication_in_progress(data, self.process_id, self.creation):
                    break
            else:
                raise ItemApplicationTraceError("response mapping changed during bounded read")
        except Exception:
            self._incomplete = True
            self._read_errors += 1
            raise
        try:
            snapshot = parse_snapshot(data, process_id=self.process_id, creation=self.creation)
        except ItemApplicationTraceError:
            self._incomplete = True
            self._read_errors += 1
            raise
        last = self._last
        if last and any(
            snapshot[key] < last[key]
            for key in (
                "sequence",
                "overwritten",
                "rejected",
                "ticket_drops",
            )
        ):
            self._terminal = "response counters regressed; capture cannot rebind"
            raise ItemApplicationTraceError(self._terminal)
        previous = last["sequence"] if last else 0
        oldest = max(1, snapshot["sequence"] - CAPACITY + 1)
        missed = max(0, oldest - previous - 1)
        self._incomplete |= bool(
            missed
            or snapshot["rejected"]
            or snapshot["ticket_drops"]
            or any(
                r["flags"] & 3 != 3
                or (r["stage"] in ("processing", "returned") and not r["flags"] & 4)
                for r in snapshot["records"]
            )
        )
        self._last = {
            key: snapshot[key]
            for key in (
                "sequence",
                "overwritten",
                "rejected",
                "ticket_drops",
            )
        }
        if snapshot["stopped"]:
            self._terminal = "response recorder stopped; capture cannot rebind"
        return {
            **snapshot,
            "process_id": self.process_id,
            "process_creation_filetime_utc": self.creation,
            "records": [r for r in snapshot["records"] if r["sequence"] > previous],
            "initial_history": last is None,
            "missed_records": missed,
            "capture_incomplete": self._incomplete,
            "read_errors": self._read_errors,
            "command_admitted": False,
            "server_acceptance_verified": False,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--creation-filetime", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= 3600:
        parser.error("seconds must be in (0, 3600]")
    reader = ItemApplicationTraceReader(
        args.process_id, args.creation_filetime, WindowsSharedMemorySnapshotReader()
    )
    deadline = time.monotonic() + args.seconds
    with args.output.open("x", encoding="utf-8") as output:
        while time.monotonic() < deadline:
            try:
                result = reader.drain()
            except Exception as error:
                output.write(
                    json.dumps(
                        {
                            "diagnostic_state": "unknown",
                            "error": str(error),
                            "command_admitted": False,
                            "server_acceptance_verified": False,
                        }
                    )
                    + "\n"
                )
                return 1
            result["diagnostic_state"] = "stopped" if result["stopped"] else "available"
            result["application_authority"] = False
            output.write(json.dumps(result) + "\n")
            output.flush()
            if result["stopped"]:
                break
            time.sleep(0.05)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
