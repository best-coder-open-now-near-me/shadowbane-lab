"""Read-only, lifetime-bound Condemn response evidence; never action authority."""
from __future__ import annotations

import struct

from .event_reader import SharedMemorySnapshotReader

HEADER = struct.Struct("<8sIIIIQqqiiq")
RECORD = struct.Struct("<QQIIQQIIII")
PAYLOAD = struct.Struct("<18I")
ROW = struct.Struct("<10I")
CAPACITY, MAX_ROWS, RECORD_SIZE, SIZE = 32, 512, 20608, 659520


class CondemnResponseError(RuntimeError):
    """The response stream cannot provide coherent evidence."""


def _identity(pid, creation):
    for value, maximum in ((pid, 0xFFFFFFFF), (creation, 0xFFFFFFFFFFFFFFFF)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
            raise ValueError("invalid process lifetime")


def mapping_name(pid, creation):
    _identity(pid, creation)
    return f"Local\\ShadowbaneLab.Extension.Condemn.v1.{pid}.{creation}"


def parse_snapshot(data: bytes, *, process_id: int, creation: int):
    """Validate every retained record, including fields absent from native messages."""
    _identity(process_id, creation)
    if len(data) != SIZE:
        raise CondemnResponseError("response mapping size mismatch")
    (magic, schema, record_size, capacity, pid, born, sequence,
     overwritten, stopped, rejected, drops) = HEADER.unpack_from(data)
    if (magic, schema, record_size, capacity, pid, born) != (
        b"WBKOS1\0\0", 1, RECORD_SIZE, CAPACITY, process_id, creation,
    ):
        raise CondemnResponseError("response mapping identity or layout mismatch")
    if (sequence < 0 or overwritten != max(0, sequence - CAPACITY)
            or stopped not in (0, 1) or rejected < 0 or drops < 0):
        raise CondemnResponseError("invalid response counters")
    records = []
    for expected in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        offset = HEADER.size + ((expected - 1) % CAPACITY) * RECORD_SIZE
        seq, tick, thread, stage, decode, epoch, local_id, local_type, flags, caller = (
            RECORD.unpack_from(data, offset)
        )
        if (seq != expected or stage not in (1, 2, 3) or not thread or flags & ~7
                or bool(flags & 2) != bool(epoch) or (not epoch and (local_id or local_type))
                or (flags & 4 and (flags & 3 != 3 or stage == 1 or not 0 < decode < seq))
                or (stage == 1 and decode != seq)
                or (stage != 1 and not flags & 4 and decode)):
            raise CondemnResponseError("invalid or incomplete response record")
        raw = data[offset + RECORD.size:offset + RECORD_SIZE]
        body = None
        if flags & 1:
            values = PAYLOAD.unpack_from(raw)
            operation, status, scope, fields = values[:4]
            state, inverted, reported, count = values[14:]
            expected_fields = 3 if operation in (14, 16) else 5 if operation == 15 else 1
            if (not 11 <= operation <= 22 or fields != expected_fields or count > MAX_ROWS
                    or state not in (0, 1) or inverted not in (0, 1)
                    or (fields != 3 and scope) or (fields == 1 and any(values[8:14]))
                    or any(raw[PAYLOAD.size + count * ROW.size:])):
                raise CondemnResponseError("invalid or noncanonical response payload")
            rows = []
            for index in range(count):
                row = ROW.unpack_from(raw, PAYLOAD.size + index * ROW.size)
                if row[9] & 0xFF000000:
                    raise CondemnResponseError("response row contains native padding")
                rows.append({
                    "kind": row[0], "entry": row[1:3], "character": row[3:5],
                    "guild": row[5:7], "nation": row[7:9], "flags_raw": row[9],
                })
            body = {
                "operation": operation, "status_raw": status, "scope_raw": scope,
                "serialized_fields": fields, "building": values[4:6], "entry": values[6:8],
                "character": values[8:10], "guild": values[10:12], "nation": values[12:14],
                "state_raw": state, "inverted_raw": inverted,
                "reported_count_raw": reported, "rows": rows,
            }
        elif any(raw):
            raise CondemnResponseError("invalid response published partial payload")
        records.append({
            "sequence": seq, "tick_ms": tick, "thread_id": thread,
            "stage": {1: "decoded", 2: "processing", 3: "returned"}[stage],
            "decode_sequence": decode, "scene_epoch": epoch, "local": (local_id, local_type),
            "flags": flags, "caller_rva": caller, "payload": body,
        })
    return {
        "sequence": sequence, "overwritten": overwritten, "stopped": bool(stopped),
        "rejected": rejected, "ticket_drops": drops, "records": records,
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
        b"WBKOS1\0\0", 1, RECORD_SIZE, CAPACITY, process_id, creation,
    ) or sequence < CAPACITY:
        return False
    next_slot = HEADER.size + (sequence % CAPACITY) * RECORD_SIZE
    slot_sequence = struct.unpack_from("<Q", data, next_slot)[0]
    return (
        overwritten in (sequence - CAPACITY, sequence - CAPACITY + 1)
        and slot_sequence in (0, sequence + 1)
    )


class CondemnResponseReader:
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
            raise CondemnResponseError(self._terminal)
        try:
            # Retry observation only; no command is submitted and the accepted
            # cursor stays unchanged until a coherent snapshot is validated.
            for _ in range(3):
                data = self.memory.read(self.name, SIZE)
                stable = data == self.memory.read(self.name, SIZE)
                if stable and not _publication_in_progress(data, self.process_id, self.creation):
                    break
            else:
                raise CondemnResponseError("response mapping changed during bounded read")
        except Exception:
            self._incomplete = True
            self._read_errors += 1
            raise
        try:
            snapshot = parse_snapshot(data, process_id=self.process_id, creation=self.creation)
        except CondemnResponseError:
            self._incomplete = True
            self._read_errors += 1
            raise
        last = self._last
        if last and any(snapshot[key] < last[key] for key in (
            "sequence", "overwritten", "rejected", "ticket_drops",
        )):
            self._terminal = "response counters regressed; capture cannot rebind"
            raise CondemnResponseError(self._terminal)
        previous = last["sequence"] if last else 0
        oldest = max(1, snapshot["sequence"] - CAPACITY + 1)
        missed = max(0, oldest - previous - 1)
        self._incomplete |= bool(missed or snapshot["rejected"] or snapshot["ticket_drops"])
        self._last = {key: snapshot[key] for key in (
            "sequence", "overwritten", "rejected", "ticket_drops",
        )}
        if snapshot["stopped"]:
            self._terminal = "response recorder stopped; capture cannot rebind"
        return {
            **snapshot, "process_id": self.process_id,
            "process_creation_filetime_utc": self.creation,
            "records": [r for r in snapshot["records"] if r["sequence"] > previous],
            "initial_history": last is None, "missed_records": missed,
            "capture_incomplete": self._incomplete, "read_errors": self._read_errors,
            "command_admitted": False, "server_acceptance_verified": False,
        }
