"""Copied native group receive events, scoped to one exact process lifetime.

Returned qualified records attest receive/Process/roster lineage, not a server
session nonce. Consumers must seed history and revalidate before command entry.
"""
from __future__ import annotations

import hashlib
import math
import struct

from .tracking_publication import HEADER, RECORD, _identity

CAPACITY = 32
CONTEXT = struct.Struct("<55I2II")
ROW = struct.Struct("<2I3fI")
LAYOUTS = {
    "messages": (b"WBGRP1\0\0", "GroupMessages", 760),
    "updates": (b"WBGUP1\0\0", "GroupUpdates", 544),
}


class GroupPublicationError(RuntimeError):
    """Incomplete or contradictory native group evidence."""


def _require(ok, detail):
    if not ok:
        raise GroupPublicationError(detail)


def _text(raw, units, maximum):
    _require(0 < units <= maximum and not any(raw[units * 2:]), "noncanonical group text")
    try:
        value = raw[:units * 2].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise GroupPublicationError("invalid group text encoding") from exc
    _require(not any(ord(c) < 32 for c in value), "invalid group text characters")
    return value


def _context(words):
    _require(words[0] == 0x315047 and all(words[1:4]) and 0 < words[4] <= 10,
             "invalid native group context")
    count = words[4]
    _require(not any(words[5 + count * 5:]), "noncanonical native group context")
    rows, keys, nodes, entries = [], set(), set(), set()
    for i in range(count):
        node, entry, first, second, role = words[5 + i * 5:10 + i * 5]
        _require(node >= 0x10000 and entry >= 0x10000 and node % 4 == entry % 4 == 0
                 and first and second and role in (0, 0x15, 0x16), "invalid roster row")
        key = (first, second)
        _require(key not in keys and node not in nodes and entry not in entries,
                 "duplicate native roster identity")
        rows.append((node, entry, first, second, role))
        keys.add(key)
        nodes.add(node)
        entries.add(entry)
    _require(sum(r[-1] == 0x16 for r in rows) <= 1, "duplicate group leaders")
    packed = struct.pack(f"<{5 + count * 5}I", *words[:5 + count * 5])
    return hashlib.sha256(packed).hexdigest(), keys


def parse_snapshot(data, *, process_id, creation, kind):
    _identity(process_id, creation)
    magic, _, size = LAYOUTS[kind]
    _require(len(data) == HEADER.size + CAPACITY * size, "group mapping size mismatch")
    got, schema, record_size, capacity, pid, born, seq, overwritten, stopped, rejected, drops = (
        HEADER.unpack_from(data))
    _require((got, schema, record_size, capacity, pid, born) == (
        magic, 1, size, CAPACITY, process_id, creation), "group mapping identity mismatch")
    _require(seq >= 0 and overwritten == max(0, seq - CAPACITY) and stopped in (0, 1)
             and rejected >= 0 and drops >= 0, "invalid group counters")
    records = []
    for expected in range(max(1, seq - CAPACITY + 1), seq + 1):
        offset = HEADER.size + ((expected - 1) % CAPACITY) * size
        number, tick, thread, stage, decode, generation, epoch, first, second, flags, caller = (
            RECORD.unpack_from(data, offset))
        _require(number == expected and thread and stage in (1, 2, 3) and not flags & ~15
                 and bool(flags & 2) == bool(epoch) and (epoch or not (first or second))
                 and (not flags & 4 or (flags & 3 == 3 and stage != 1 and 0 < decode < number))
                 and (not flags & 8 or flags & 7 == 7)
                 and (stage != 1 or (decode == number and generation == 0))
                 and (stage != 2 or generation == number)
                 and (stage != 3 or 0 < generation < number)
                 and (stage == 1 or flags & 4 or decode == 0), "invalid group record lineage")
        raw = data[offset + RECORD.size:offset + size]
        payload = None
        if flags & 1:
            prefix = CONTEXT.unpack_from(raw)
            words, sender, reserved = prefix[:55], tuple(prefix[55:57]), prefix[57]
            _require(reserved == 0, "nonzero group reserved field")
            digest, keys = None, set()
            if flags & 8:
                digest, keys = _context(words)
            else:
                _require(not any(words) and not any(sender), "unqualified roster leaked")
            if kind == "messages":
                channel, name_units, text_units, extra = struct.unpack_from(
                    "<4I", raw, CONTEXT.size)
                _require(channel == 14 and extra == 0, "non-group channel or reserved payload")
                name_start = CONTEXT.size + 16
                name = _text(raw[name_start:name_start + 192], name_units, 96)
                text = _text(raw[name_start + 192:], text_units, 128)
                _require(not flags & 8 or sender in keys, "sender absent from qualified roster")
                payload = {"sender": name, "sender_key": sender, "text": text}
            else:
                update, count = struct.unpack_from("<2I", raw, CONTEXT.size)
                _require(not any(sender) and update in range(1, 9) and count <= 10
                         and (update in (1, 2, 5) or count == 0), "invalid group update")
                rows, seen = [], set()
                for index in range(count):
                    a, b, x, y, z, extra = ROW.unpack_from(raw, CONTEXT.size + 8 + index * ROW.size)
                    key = (a, b)
                    _require(a and b and key not in seen and extra == 0
                             and all(math.isfinite(v) for v in (x, y, z))
                             and (not flags & 8 or key in keys), "invalid group position row")
                    seen.add(key)
                    rows.append({"key": key, "xyz": (x, y, z)})
                _require(not any(raw[CONTEXT.size + 8 + count * ROW.size:]),
                         "partial group position payload")
                payload = {"kind": update, "positions": rows}
            payload["group_digest"] = digest
        else:
            _require(not any(raw), "partial invalid group payload")
        records.append({"sequence": number, "tick_ms": tick, "stage": stage,
                        "decode_sequence": decode, "processing_generation": generation,
                        "scene_epoch": epoch, "local": (first, second), "flags": flags,
                        "caller_rva": caller, "payload": payload})
    return {"sequence": seq, "overwritten": overwritten, "stopped": bool(stopped),
            "rejected": rejected, "ticket_drops": drops, "records": records}


class GroupPublicationReader:
    """Bounded coherent reads; every startup explicitly seeds retained history."""

    def __init__(self, process_id, creation, memory, *, kind):
        _identity(process_id, creation)
        _, label, self.record_size = LAYOUTS[kind]
        self.kind, self.process_id, self.creation, self.memory = kind, process_id, creation, memory
        self.name = f"Local\\ShadowbaneLab.Extension.{label}.v1.{process_id}.{creation}"
        self.size = HEADER.size + CAPACITY * self.record_size
        self.last = None
        self.terminal = False
        self.failed_read = False

    def drain(self):
        if self.terminal:
            raise GroupPublicationError("group stream ended or regressed")
        try:
            for _ in range(3):
                data = self.memory.read(self.name, self.size)
                if data != self.memory.read(self.name, self.size):
                    continue
                try:
                    result = parse_snapshot(data, process_id=self.process_id,
                                            creation=self.creation, kind=self.kind)
                except GroupPublicationError:
                    continue
                break
            else:
                raise GroupPublicationError("group stream unavailable during bounded read")
        except Exception:
            self.failed_read = True
            raise
        counters = ("sequence", "overwritten", "rejected", "ticket_drops")
        if self.last and any(result[k] < self.last[k] for k in counters):
            self.terminal = True
            raise GroupPublicationError("group publication counters regressed")
        previous = 0 if self.last is None else self.last["sequence"]
        missed = max(0, result["sequence"] - CAPACITY - previous)
        gap = self.failed_read or bool(missed) or any(
            result[k] > (0 if self.last is None else self.last[k])
            for k in ("rejected", "ticket_drops"))
        result.update(initial_history=self.last is None, gap=gap)
        result["records"] = [r for r in result["records"] if r["sequence"] > previous]
        self.last = {k: result[k] for k in counters}
        self.failed_read = False
        self.terminal = result["stopped"]
        return result
