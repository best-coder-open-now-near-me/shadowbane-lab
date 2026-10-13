"""Copied crafting receive history for an exact client lifetime; no commands."""
from __future__ import annotations

import struct

from .event_reader import SharedMemorySnapshotReader
from .vendor_wire import uint

HEADER = struct.Struct("<8sIIIIQqqiiq")
RECORD = struct.Struct("<QQIIQQIIII")
PAYLOAD = struct.Struct("<28I")
CAPACITY, RECORD_SIZE, SIZE = 256, 168, 43072


class VendorProductionError(RuntimeError):
    pass


def mapping_name(process_id: int, creation: int) -> str:
    if not uint(process_id, 32, "process ID") or not uint(creation, 64, "creation"):
        raise ValueError("an exact client lifetime is required")
    return f"Local\\ShadowbaneLab.Extension.VendorProduction.v1.{process_id}.{creation}"


def parse_snapshot(data: bytes, *, process_id: int, creation: int) -> dict:
    mapping_name(process_id, creation)
    if len(data) != SIZE:
        raise VendorProductionError("production mapping size mismatch")
    magic, schema, size, capacity, pid, born, sequence, overwritten, stopped, rejected, drops = (
        HEADER.unpack_from(data))
    if (magic, schema, size, capacity, pid, born) != (
        b"WBPRD1\0\0", 1, RECORD_SIZE, CAPACITY, process_id, creation,
    ):
        raise VendorProductionError("production mapping identity or layout mismatch")
    if (sequence < 0 or overwritten != max(0, sequence - CAPACITY)
            or stopped not in (0, 1) or rejected < 0 or drops < 0):
        raise VendorProductionError("invalid production counters")
    records = []
    for expected in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        offset = HEADER.size + ((expected - 1) % CAPACITY) * RECORD_SIZE
        seq, tick, thread, stage, decode, epoch, local_id, local_type, flags, caller = (
            RECORD.unpack_from(data, offset))
        if (seq != expected or stage not in (1, 2, 3) or not thread or flags & ~7
                or bool(flags & 2) != bool(epoch) or not epoch and (local_id or local_type)
                or flags & 4 and (flags & 3 != 3 or stage == 1 or not 0 < decode < seq)
                or stage == 1 and decode != seq
                or stage != 1 and not flags & 4 and decode):
            raise VendorProductionError("invalid or incomplete production record")
        v = PAYLOAD.unpack_from(data, offset + RECORD.size)
        body = None
        if flags & 1:
            action, error, fields = v[:3]
            if (action > 11 or fields & ~15 or bool(fields & 1) != (action == 8 and not error)
                    or fields & 2 and (action != 10 or error)
                    or bool(fields & 8) != (action == 1)
                    or not fields & 1 and any(v[13:22])
                    or not fields & 2 and any(v[22:26])
                    or not fields & 4 and v[26]
                    or (v[27] > 1 if fields & 8 else v[27] != 0)):
                raise VendorProductionError("invalid or noncanonical production payload")
            if fields & 1 and (not v[13] or v[14] != 40 or not v[15]
                               or v[20] not in (0, 1) or v[21] not in (0, 1)
                               or v[20] == v[21] or v[21] and v[18]):
                raise VendorProductionError("invalid production item")
            if fields & 2 and (not v[22] or v[23] != 40 or not v[24] or v[25]):
                raise VendorProductionError("invalid deposited item")
            body = dict(action=action, error=error, fields=fields, building=v[3:5],
                        vendor=v[5:7], reference=v[7:9], quantity_raw=v[9], marker_raw=v[10],
                        prefix=v[11], suffix=v[12], item=v[13:15], template=v[15],
                        remaining_count_raw=v[16], value=v[17], seconds=v[18], duration=v[19],
                        in_progress=v[20], complete=v[21], deposited_item=v[22:24],
                        deposited_template=v[24:26], strongbox_gold=v[26], multiple_raw=v[27])
        elif any(v):
            raise VendorProductionError("partial production payload published")
        records.append(dict(sequence=seq, tick_ms=tick, thread_id=thread,
                            stage={1: "decoded", 2: "processing", 3: "returned"}[stage],
                            decode_sequence=decode, scene_epoch=epoch,
                            local=(local_id, local_type), flags=flags,
                            caller_rva=caller, payload=body))
    return dict(sequence=sequence, overwritten=overwritten, stopped=bool(stopped),
                rejected=rejected, ticket_drops=drops, records=records)


def _publishing(data: bytes, process_id: int, creation: int) -> bool:
    if len(data) != SIZE:
        return False
    magic, schema, size, capacity, pid, born, sequence, overwritten, *_ = HEADER.unpack_from(data)
    if (magic, schema, size, capacity, pid, born) != (
        b"WBPRD1\0\0", 1, RECORD_SIZE, CAPACITY, process_id, creation,
    ) or sequence < CAPACITY:
        return False
    slot = HEADER.size + sequence % CAPACITY * RECORD_SIZE
    value = struct.unpack_from("<Q", data, slot)[0]
    return (overwritten in (sequence - CAPACITY, sequence - CAPACITY + 1)
            and value in (0, sequence + 1))


class VendorProductionReader:
    """Bookmark before a new Create or resume an exact saved observation cursor.

    Initial retained history may predate this job and is explicitly discarded at
    the bookmark. After that point, any loss is sticky; a reader can never reset
    its baseline to hide a gap. The caller must preserve the cursor with its job.
    Neither a bookmark nor a returned native handler proves item acceptance.
    """

    def __init__(self, process_id: int, creation: int, memory: SharedMemorySnapshotReader,
                 *, resume_cursor: dict | None = None):
        self.name = mapping_name(process_id, creation)
        self.process_id, self.creation, self.memory = process_id, creation, memory
        self._last = None
        self._terminal = None
        self._incomplete, self._read_errors = False, 0
        if resume_cursor is not None:
            required = {"process_id", "creation", "sequence", "overwritten", "rejected",
                        "ticket_drops", "capture_incomplete", "read_errors"}
            if (type(resume_cursor) is not dict or set(resume_cursor) != required
                    or (resume_cursor["process_id"], resume_cursor["creation"])
                    != (process_id, creation)
                    or type(resume_cursor["process_id"]) is not int
                    or type(resume_cursor["creation"]) is not int
                    or type(resume_cursor["capture_incomplete"]) is not bool
                    or any(type(resume_cursor[key]) is not int
                           or not 0 <= resume_cursor[key] < 2**63 for key in
                           ("sequence", "overwritten", "rejected", "ticket_drops", "read_errors"))
                    or resume_cursor["overwritten"] != max(
                        0, resume_cursor["sequence"] - CAPACITY)):
                raise ValueError("invalid production observation cursor")
            self._last = {key: resume_cursor[key] for key in
                          ("sequence", "overwritten", "rejected", "ticket_drops")}
            self._incomplete = resume_cursor["capture_incomplete"]
            self._read_errors = resume_cursor["read_errors"]

    def _read(self):
        if self._terminal:
            raise VendorProductionError(self._terminal)
        try:
            for _ in range(3):
                data = self.memory.read(self.name, SIZE)
                if data == self.memory.read(self.name, SIZE) and not _publishing(
                        data, self.process_id, self.creation):
                    break
            else:
                raise VendorProductionError("production mapping changed during bounded read")
            result = parse_snapshot(data, process_id=self.process_id, creation=self.creation)
            if result["stopped"]:
                self._terminal = "production recorder stopped; cannot rebind"
                raise VendorProductionError(self._terminal)
            return result
        except Exception:
            self._incomplete = True
            self._read_errors += 1
            raise

    @property
    def cursor(self) -> dict:
        if self._last is None:
            raise VendorProductionError("bookmark production before creating an order")
        return dict(process_id=self.process_id, creation=self.creation, **self._last,
                    capture_incomplete=self._incomplete, read_errors=self._read_errors)

    def bookmark(self) -> dict:
        if self._last is not None:
            raise VendorProductionError("an existing observation cursor cannot be reset")
        snapshot = self._read()
        self._last = {key: snapshot[key] for key in
                      ("sequence", "overwritten", "rejected", "ticket_drops")}
        return dict(cursor=self.cursor, history_discarded=len(snapshot["records"]),
                    history_missing=max(0, snapshot["sequence"] - CAPACITY),
                    command_admitted=False)

    def drain(self) -> dict:
        if self._last is None:
            raise VendorProductionError("bookmark production before creating an order")
        snapshot = self._read()
        if any(snapshot[key] < self._last[key] for key in self._last):
            self._terminal = "production counters regressed; cannot rebind"
            self._incomplete = True
            raise VendorProductionError(self._terminal)
        previous = self._last["sequence"]
        missed = max(0, snapshot["sequence"] - CAPACITY - previous)
        self._incomplete |= bool(missed or snapshot["rejected"] > self._last["rejected"]
                                 or snapshot["ticket_drops"] > self._last["ticket_drops"])
        self._last = {key: snapshot[key] for key in self._last}
        return dict(records=[r for r in snapshot["records"] if r["sequence"] > previous],
                    cursor=self.cursor, missed_records=missed,
                    capture_incomplete=self._incomplete, command_admitted=False,
                    server_acceptance_verified=False)
