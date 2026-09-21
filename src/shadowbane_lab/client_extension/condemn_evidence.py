"""Qualify bounded Condemn response triples without inventing command ownership.

A successful row-state response has a building and entry key, but no request nonce
or scope. List refreshes may omit the building. Keep those limitations explicit:
this module produces evidence, never permission to submit or replay a toggle.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .condemn_responses import CAPACITY, CondemnResponseError


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def integer(value, maximum=2**64 - 1, *, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CondemnResponseError("invalid Condemn evidence integer")
    return value


def key(value, *, kind=None, empty=False):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise CondemnResponseError("invalid Condemn evidence key")
    result = tuple(integer(v, 2**32 - 1) for v in value)
    if result == (0, 0) and empty:
        return result
    if not all(result) or kind is not None and result[1] != kind:
        raise CondemnResponseError("invalid Condemn evidence key type")
    return result


@dataclass(frozen=True, slots=True)
class Lifetime:
    process_id: int
    creation: int
    scene_epoch: int
    local: tuple[int, int]

    def __post_init__(self):
        integer(self.process_id, 2**32 - 1, minimum=1)
        integer(self.creation, minimum=1)
        integer(self.scene_epoch, minimum=1)
        object.__setattr__(self, "local", key(self.local, kind=53))

    def matches(self, record):
        return (record["scene_epoch"] == self.scene_epoch
                and key(record["local"]) == self.local)


@dataclass(frozen=True, slots=True)
class Target:
    building: tuple[int, int]
    scope: str
    identity: tuple[int, int]
    entry: tuple[int, int]

    def __post_init__(self):
        if self.scope not in {"guild", "nation"}:
            raise CondemnResponseError("only explicit guild or nation scope is supported")
        object.__setattr__(self, "building", key(self.building, kind=8))
        object.__setattr__(self, "identity", key(self.identity, kind=23))
        object.__setattr__(self, "entry", key(self.entry, kind=23))


def _record(value):
    # Own our copy. Neither a caller nor a subsequent reader drain can mutate proof.
    record = json.loads(canonical(value))
    if set(record) != {"sequence", "tick_ms", "thread_id", "stage", "decode_sequence",
                       "scene_epoch", "local", "flags", "caller_rva", "payload"}:
        raise CondemnResponseError("invalid Condemn evidence record")
    for field in ("sequence", "thread_id", "scene_epoch", "decode_sequence"):
        integer(record[field], minimum=1)
    integer(record["tick_ms"])
    integer(record["caller_rva"], 2**32 - 1)
    stage = record["stage"]
    if stage not in {"decoded", "processing", "returned"}:
        raise CondemnResponseError("invalid Condemn response stage")
    expected_flags = 3 if stage == "decoded" else 7
    if type(record["flags"]) is not int or record["flags"] != expected_flags:
        raise CondemnResponseError("Condemn response lacks payload, scene or decode lineage")
    if stage == "decoded":
        if (record["decode_sequence"] != record["sequence"]
                or record["caller_rva"] != 0x3625BC):
            raise CondemnResponseError("Condemn decode has an unverified source")
    elif record["decode_sequence"] >= record["sequence"]:
        raise CondemnResponseError("Condemn response has invalid decode ordering")
    key(record["local"], kind=53)
    body = record["payload"]
    if not isinstance(body, dict) or set(body) != {
        "operation", "status_raw", "scope_raw", "serialized_fields", "building", "entry",
        "character", "guild", "nation", "state_raw", "inverted_raw", "reported_count_raw", "rows",
    }:
        raise CondemnResponseError("invalid Condemn evidence payload")
    op = integer(body["operation"], 22, minimum=11)
    fields = 3 if op in (14, 16) else 5 if op == 15 else 1
    if type(body["serialized_fields"]) is not int or body["serialized_fields"] != fields:
        raise CondemnResponseError("invalid serialized Condemn fields")
    for field in ("status_raw", "scope_raw", "reported_count_raw"):
        integer(body[field], 2**32 - 1)
    for field in ("state_raw", "inverted_raw"):
        integer(body[field], 1)
    for field in ("building", "entry", "character", "guild", "nation"):
        key(body[field], empty=True)
    if (fields != 3 and body["scope_raw"]
            or fields == 1 and any(body[k] != [0, 0] for k in ("character", "guild", "nation"))):
        raise CondemnResponseError("absent Condemn fields contain values")
    if not isinstance(body["rows"], list) or len(body["rows"]) > 512:
        raise CondemnResponseError("Condemn response row bound exceeded")
    for row in body["rows"]:
        if not isinstance(row, dict) or set(row) != {
            "kind", "entry", "character", "guild", "nation", "flags_raw",
        }:
            raise CondemnResponseError("invalid Condemn evidence row")
        integer(row["kind"], 2**32 - 1)
        integer(row["flags_raw"], 0xFFFFFF)
        for field in ("entry", "character", "guild", "nation"):
            key(row[field], empty=True)
    return record


@dataclass(frozen=True, slots=True)
class Response:
    """An immutable, complete copied response; not an action acknowledgement."""

    lifetime: Lifetime
    records_json: bytes

    def __post_init__(self):
        records = [_record(r) for r in json.loads(self.records_json)]
        if len(records) != 3 or [r["stage"] for r in records] != [
            "decoded", "processing", "returned",
        ]:
            raise CondemnResponseError("three ordered Condemn stages are required")
        first, processing, returned = records
        if (not all(self.lifetime.matches(r) for r in records)
                or not first["sequence"] < processing["sequence"] < returned["sequence"]
                or not first["tick_ms"] <= processing["tick_ms"] <= returned["tick_ms"]
                or any(r["decode_sequence"] != first["sequence"] for r in records)
                or any(r["payload"] != first["payload"] for r in records)
                or processing["thread_id"] != returned["thread_id"]
                or processing["caller_rva"] != returned["caller_rva"]):
            raise CondemnResponseError("Condemn stages disagree about response ownership")
        object.__setattr__(self, "records_json", canonical(records))

    @property
    def records(self):
        return json.loads(self.records_json)

    @property
    def payload(self):
        return self.records[0]["payload"]

    @property
    def digest(self):
        return hashlib.sha256(self.records_json).hexdigest()

    def enabled_reply(self, target: Target):
        body = self.payload
        return (body["operation"] == 17 and body["status_raw"] == 0
                and tuple(body["building"]) == target.building
                and tuple(body["entry"]) == target.entry
                and body["state_raw"] == 1 and body["inverted_raw"] == 0
                and body["rows"] == [] and body["reported_count_raw"] == 0)


class ResponseWindow:
    """Drain one fresh observation interval; any new evidence loss poisons it.

    History before the baseline (including old rejected messages) is recorded but
    never contributes to completion. This does not erase the reader's sticky
    whole-capture incomplete flag. A new reader/history drain cannot resume an
    interval, and a stopped or interrupted interval is never auto-rearmed.
    """

    def __init__(self, lifetime: Lifetime, baseline: dict):
        self.lifetime = lifetime
        self.failure = None
        self._pending = {}
        self._last_tick = 0
        self._validate_snapshot(baseline)
        if baseline["stopped"]:
            raise CondemnResponseError("Condemn response recorder is stopped")
        self.baseline = {k: baseline[k] for k in ("sequence", "rejected", "ticket_drops")}
        self.sequence = self.baseline["sequence"]

    def _validate_snapshot(self, snapshot):
        integer(snapshot.get("process_id"), 2**32 - 1, minimum=1)
        integer(snapshot.get("process_creation_filetime_utc"), minimum=1)
        if (snapshot.get("process_id"), snapshot.get("process_creation_filetime_utc")) != (
            self.lifetime.process_id, self.lifetime.creation,
        ):
            raise CondemnResponseError("Condemn response belongs to another process lifetime")
        for field in ("sequence", "rejected", "ticket_drops", "overwritten", "missed_records"):
            integer(snapshot[field], 2**63 - 1)
        if (snapshot["overwritten"] != max(0, snapshot["sequence"] - CAPACITY)
                or not isinstance(snapshot["records"], list)
                or len(snapshot["records"]) > CAPACITY
                or any(type(snapshot[k]) is not bool for k in ("stopped", "initial_history"))):
            raise CondemnResponseError("invalid Condemn response window")

    def invalidate(self, reason="Condemn evidence read interrupted"):
        self.failure = self.failure or reason
        self._pending.clear()
        raise CondemnResponseError(self.failure)

    def consume(self, snapshot: dict) -> tuple[Response, ...]:
        if self.failure:
            raise CondemnResponseError(self.failure)
        try:
            self._validate_snapshot(snapshot)
            if (snapshot["initial_history"] or snapshot["stopped"] or snapshot["missed_records"]
                    or snapshot["sequence"] < self.sequence
                    or any(snapshot[k] != self.baseline[k] for k in ("rejected", "ticket_drops"))):
                raise CondemnResponseError(
                    "Condemn response interval was interrupted or lost evidence")
            records = snapshot["records"]
            if (snapshot["sequence"] - self.sequence != len(records)
                    or any(r["sequence"] != self.sequence + i + 1
                           for i, r in enumerate(records))):
                raise CondemnResponseError("Condemn response interval has a sequence gap or replay")
            completed = []
            for raw in records:
                r = _record(raw)
                if not self.lifetime.matches(r) or r["tick_ms"] < self._last_tick:
                    raise CondemnResponseError("Condemn scene or clock changed")
                self._last_tick = r["tick_ms"]
                decode = r["decode_sequence"]
                # A response decoded before the baseline is explicitly old evidence.
                if decode <= self.baseline["sequence"]:
                    continue
                if r["stage"] == "decoded":
                    if decode in self._pending or len(self._pending) >= 64:
                        raise CondemnResponseError("Condemn response lineage capacity exceeded")
                    self._pending[decode] = [r]
                    continue
                pending = self._pending.get(decode)
                expected = 1 if r["stage"] == "processing" else 2
                if pending is None or len(pending) != expected:
                    raise CondemnResponseError("Condemn response lacks its preceding stages")
                pending.append(r)
                if r["stage"] == "returned":
                    completed.append(Response(self.lifetime, canonical(pending)))
                    del self._pending[decode]
            self.sequence = snapshot["sequence"]
            return tuple(completed)
        except (CondemnResponseError, KeyError, TypeError, ValueError) as exc:
            self.invalidate(str(exc))


def enabled_row(target: Target, observation: dict) -> bool:
    """Check loaded row state only. Visibility, freshness and action admission are separate.

    Mixed identities, duplicate matching entries, inversion and other contexts do
    not qualify. Guild/nation equality does not merge their independently scoped
    rows. No display label or pending-drop identity is used as a target key.
    """
    try:
        if observation["root_refresh_pending_raw"] != 0:
            return False
        windows = [w for w in observation["windows"] if w["kind"] == "kos"]
        if len(windows) != 1:
            return False
        window = windows[0]
        raw_key = window["context_key_raw"]
        if (key((raw_key["object_id"], raw_key["object_type"]), kind=8) != target.building
                or window["flags_raw"] != [0, 0]):
            return False
        matches = []
        for row in window["entries"]:
            entry = row["row_key_raw"]
            if key((entry["object_id"], entry["object_type"]), empty=True) == target.entry:
                matches.append(row)
        if len(matches) != 1:
            return False
        row = matches[0]
        for scope in ("character", "guild", "nation"):
            identity = row["identities"][scope]
            if key((identity["object_id"], identity["object_type"]), empty=True) != (
                target.identity if scope == target.scope else (0, 0)
            ):
                return False
        flags = row["flags_raw"]
        return (len(flags) == 3 and all(type(v) is int and v in (0, 1) for v in flags)
                and flags == ([0, 1, 0] if target.scope == "guild" else [0, 0, 1]))
    except (CondemnResponseError, KeyError, TypeError):
        return False
