"""Read-only, lifetime-bound Furniture response evidence; never action authority."""
from __future__ import annotations

import math
import struct

from .event_reader import SharedMemorySnapshotReader

HEADER = struct.Struct("<8sIIIIQqqiiq")
RECORD = struct.Struct("<QQIIQQIIII")
PAYLOAD = struct.Struct("<10I4fi9I")
ROW = struct.Struct("<6I4fi3I")
KEY = struct.Struct("<II")
CAPACITY, MAX_ROWS, RECORD_SIZE, SIZE = 32, 64, 7832, 250688
SECONDARY_OFFSET = PAYLOAD.size + MAX_ROWS * ROW.size
CONSUMED_OFFSET = SECONDARY_OFFSET + MAX_ROWS * ROW.size


class FurnitureResponseError(RuntimeError):
    """The response stream cannot provide coherent evidence."""


def _identity(pid, creation):
    for value, maximum in ((pid, 0xFFFFFFFF), (creation, 0xFFFFFFFFFFFFFFFF)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
            raise ValueError("invalid process lifetime")


def mapping_name(pid, creation):
    _identity(pid, creation)
    return f"Local\\ShadowbaneLab.Extension.Furniture.v1.{pid}.{creation}"


def _rows(raw, offset, count):
    end = offset + MAX_ROWS * ROW.size
    if any(raw[offset + count * ROW.size:end]):
        raise FurnitureResponseError("noncanonical unfilled furniture rows")
    rows = []
    for index in range(count):
        values = ROW.unpack_from(raw, offset + index * ROW.size)
        if (not all(math.isfinite(value) for value in values[6:10])
                or values[12] > 255 or values[13]):
            raise FurnitureResponseError("invalid furniture row fields")
        rows.append({
            "asset": values[:2], "instance": values[2:4], "auxiliary": values[4:6],
            "position_raw": values[6:9], "rotation_raw": values[9],
            "floor_raw": values[10], "word34_raw": values[11], "flag38_raw": values[12],
        })
    return rows


def _payload(raw):
    values = PAYLOAD.unpack_from(raw)
    operation, fields, status, refresh = values[:4]
    reported_scene, scene_count, reported_consumed, consumed_count = values[15:19]
    reported_secondary, secondary_count = values[19:21]
    counts = ((reported_scene, scene_count, 1), (reported_consumed, consumed_count, 2),
              (reported_secondary, secondary_count, 4))
    if (operation not in (2, 3) or fields != (3 if operation == 2 else 5)
            or status & ~7 or refresh > 255 or any(values[21:])
            or any(count != min(reported, MAX_ROWS)
                   or bool(status & bit) != (reported > MAX_ROWS)
                   for reported, count, bit in counts)
            or not all(math.isfinite(value) for value in values[10:14])
            or (operation == 2 and any(raw[32:60]))
            or (operation == 3 and (refresh or reported_consumed or consumed_count))
            or any(raw[CONSUMED_OFFSET + consumed_count * KEY.size:])):
        raise FurnitureResponseError("invalid or noncanonical response payload")
    return {
        "operation": operation, "serialized_fields": fields, "status_raw": status,
        "refresh_raw": refresh, "building": values[4:6], "structure": values[6:8],
        "deed": values[8:10], "position_raw": values[10:13],
        "rotation_raw": values[13], "floor_raw": values[14],
        "reported_scene_count_raw": reported_scene,
        "scene": _rows(raw, PAYLOAD.size, scene_count),
        "reported_secondary_count_raw": reported_secondary,
        "secondary": _rows(raw, SECONDARY_OFFSET, secondary_count),
        "reported_consumed_count_raw": reported_consumed,
        "consumed": [KEY.unpack_from(raw, CONSUMED_OFFSET + index * KEY.size)
                     for index in range(consumed_count)],
    }


def parse_snapshot(data: bytes, *, process_id: int, creation: int):
    """Validate every retained record, including fields absent from native messages."""
    _identity(process_id, creation)
    if len(data) != SIZE:
        raise FurnitureResponseError("response mapping size mismatch")
    (magic, schema, record_size, capacity, pid, born, sequence,
     overwritten, stopped, rejected, drops) = HEADER.unpack_from(data)
    if (magic, schema, record_size, capacity, pid, born) != (
        b"WBFURN1\0", 1, RECORD_SIZE, CAPACITY, process_id, creation,
    ):
        raise FurnitureResponseError("response mapping identity or layout mismatch")
    if (sequence < 0 or overwritten != max(0, sequence - CAPACITY)
            or stopped not in (0, 1) or rejected < 0 or drops < 0):
        raise FurnitureResponseError("invalid response counters")
    records = []
    for expected in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        offset = HEADER.size + ((expected - 1) % CAPACITY) * RECORD_SIZE
        seq, tick, thread, stage, decode, epoch, local_id, local_type, flags, caller = (
            RECORD.unpack_from(data, offset)
        )
        if (seq != expected or stage not in (1, 2, 3, 4) or not thread or flags & ~7
                or bool(flags & 2) != bool(epoch) or (not epoch and (local_id or local_type))
                or (flags & 4 and (flags & 3 != 3 or stage in (1, 4) or not 0 < decode < seq))
                or (stage == 1 and (decode != seq or caller != 0x3625BC))
                or (stage == 4 and caller != 0x362919)
                or (stage != 1 and not flags & 4 and decode)):
            raise FurnitureResponseError("invalid or incomplete response record")
        raw = data[offset + RECORD.size:offset + RECORD_SIZE]
        body = None
        if flags & 1:
            body = _payload(raw)
            if flags & 4 and body["status_raw"]:
                raise FurnitureResponseError("truncated response cannot establish lineage")
        elif any(raw):
            raise FurnitureResponseError("invalid response published partial payload")
        records.append({
            "sequence": seq, "tick_ms": tick, "thread_id": thread,
            "stage": {1: "decoded", 2: "processing", 3: "returned", 4: "serializing"}[stage],
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
        b"WBFURN1\0", 1, RECORD_SIZE, CAPACITY, process_id, creation,
    ) or sequence < CAPACITY:
        return False
    next_slot = HEADER.size + (sequence % CAPACITY) * RECORD_SIZE
    slot_sequence = struct.unpack_from("<Q", data, next_slot)[0]
    return (
        overwritten in (sequence - CAPACITY, sequence - CAPACITY + 1)
        and slot_sequence in (0, sequence + 1)
    )


class FurnitureResponseReader:
    """Drain a bounded ring without replaying records or hiding evidence gaps.

    The first drain returns retained history explicitly labeled as history. A gap,
    rejected/truncated native snapshot or lost lineage ticket marks this capture
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
            raise FurnitureResponseError(self._terminal)
        try:
            # Retry observation only; no command is submitted and the accepted
            # cursor stays unchanged until a coherent snapshot is validated.
            for _ in range(3):
                data = self.memory.read(self.name, SIZE)
                stable = data == self.memory.read(self.name, SIZE)
                if stable and not _publication_in_progress(data, self.process_id, self.creation):
                    break
            else:
                raise FurnitureResponseError("response mapping changed during bounded read")
        except Exception:
            self._incomplete = True
            self._read_errors += 1
            raise
        try:
            snapshot = parse_snapshot(data, process_id=self.process_id, creation=self.creation)
        except FurnitureResponseError:
            self._incomplete = True
            self._read_errors += 1
            raise
        last = self._last
        if last and any(snapshot[key] < last[key] for key in (
            "sequence", "overwritten", "rejected", "ticket_drops",
        )):
            self._terminal = "response counters regressed; capture cannot rebind"
            raise FurnitureResponseError(self._terminal)
        previous = last["sequence"] if last else 0
        oldest = max(1, snapshot["sequence"] - CAPACITY + 1)
        missed = max(0, oldest - previous - 1)
        self._incomplete |= bool(
            missed or snapshot["rejected"] or snapshot["ticket_drops"]
            or any(r["payload"] is None or r["payload"]["status_raw"]
                   for r in snapshot["records"])
        )
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
