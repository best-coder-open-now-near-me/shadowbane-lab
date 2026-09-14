"""Durable Keep of completed batch items; unknown affixes are preserved."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from shadowbane_lab.equipment.crafting_assessment import assess_native_crafting_roll
from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

from .action_channel import NativeClientProcessIdentity
from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_wire import IN_FLIGHT, READY, UNRESOLVED, Outcome, Receipt, Snapshot


class CompletionSession(Protocol):
    identity: NativeClientProcessIdentity

    def inspect(self) -> Receipt: ...
    def keep(self, expected: Snapshot, item: int, request_key: str) -> Receipt: ...


def _read_record(path: Path, limit: int = 1024 * 1024) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("vendor evidence exceeds its size bound")
    return data


def _decisions(batch: dict, capture: Path | None) -> dict[int, dict]:
    decisions = {
        item: {"disposition": "keep", "reason": "unknown_affix_preserved"}
        for item in batch["items"]
    }
    if capture is None:
        return decisions
    for line in _read_record(capture, 8 * 1024 * 1024).splitlines():
        record = json.loads(line)
        if record.get("record_type") != "crafting_message":
            continue
        message = record.get("message", {})
        if record.get("direction") != "server_to_client" or message.get("action_id") != 8:
            continue
        item = message.get("roll", {}).get("item", {}).get("object_id")
        if item not in decisions:
            continue
        if (
            record.get("process_id") != batch["process_id"]
            or record.get("process_creation_filetime_utc") != batch["process_creation_filetime_utc"]
            or message.get("vendor") != {"object_id": batch["vendor_id"], "object_type": 42}
            or message.get("roll", {}).get("template_id") != 26990
            or message.get("roll", {}).get("item", {}).get("object_type") != 40
            or record.get("executable_sha256")
            != "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"
        ):
            raise ValueError("completion evidence does not belong to this batch")
        assessment = assess_native_crafting_roll(record).to_dict()
        if assessment["disposition"] == "wait":
            continue
        previous = decisions[item]
        if "prefix" in previous and previous != assessment:
            raise ValueError("conflicting completion affix evidence")
        decisions[item] = assessment
    return decisions


def keep_completed_batch(
    session: CompletionSession,
    batch_journal: Path,
    journal: Path,
    *,
    capture: Path | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    before_action: Callable[[], None] = lambda: None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    acceptance_timeout: float = 15.0,
) -> dict:
    """Finalize eligible completed items once and require native inventory presence.

    Confirmed exclusions stay in production; this operation never discards or
    starts replacement rolls. Missing affix evidence is unknown, not absent.
    Existing Keep journals are never replayed, including after lost responses.
    """
    if not 0 < acceptance_timeout <= 60:
        raise ValueError("invalid completion timeout")
    raw = _read_record(Path(batch_journal))
    batch = json.loads(raw)
    initial = Snapshot.decode(bytes.fromhex(batch["initial_snapshot"]))
    items = batch["items"]
    if (
        batch.get("schema_version") != 1
        or batch.get("operation") != "fill_available_slots"
        or batch.get("state") != "complete"
        or not initial.random_scepter
        or batch["process_id"] != session.identity.process_id
        or batch["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
        or batch["vendor_id"] != initial.vendor
        or not isinstance(items, list)
        or not 1 <= len(items) <= 16
        or any(type(item) is not int or not 0 < item < 2**32 for item in items)
        or len(set(items)) != len(items)
        or set(items) & _items(initial)
        or len(batch["requests"]) != len(items)
        or [r.get("item_id") for r in batch["requests"]] != items
        or any(r.get("state") != "observed" for r in batch["requests"])
    ):
        raise ValueError("expected an observed batch belonging to this live client")
    decisions = _decisions(batch, capture)
    journal = Path(journal)
    with exclusive_record_lock(journal.with_suffix(journal.suffix + ".lock")):
        if journal.exists():
            raise VendorBatchStopped("Keep journal exists; never replay its requests")
        record = {
            "schema_version": 1,
            "operation": "keep_completed_batch",
            "state": "running",
            "batch_id": batch["batch_id"],
            "source_batch_sha256": hashlib.sha256(raw).hexdigest(),
            "process_id": batch["process_id"],
            "process_creation_filetime_utc": batch["process_creation_filetime_utc"],
            "vendor_id": batch["vendor_id"],
            "window": batch["window"],
            "decisions": decisions,
            "requests": [],
            "kept": [],
            "excluded": [item for item in items if decisions[item]["disposition"] == "exclude"],
        }
        capacity = len(initial.slots)

        def save():
            publish_atomic_record(
                journal,
                (json.dumps(record, sort_keys=True, indent=2) + "\n").encode(),
                temporary_label="vendor-keep",
            )

        def current(receipt: Receipt, pending: bool = False) -> Snapshot:
            nonlocal capacity
            s = receipt.snapshot
            if (
                receipt.outcome != Outcome.OBSERVED
                or receipt.window != batch["window"]
                or _owner(s) != _owner(initial)
                or len(s.slots) < capacity
                or not s.inventory
                or receipt.flags & UNRESOLVED
                or (not pending and (not receipt.flags & READY or receipt.flags & IN_FLIGHT))
            ):
                raise VendorBatchStopped("vendor/session/inventory authority is unavailable")
            capacity = len(s.slots)
            return s

        first = current(session.inspect())
        remaining = _items(initial) | set(items)
        if _items(first) != remaining or any(
            slot.state != 2 for slot in first.slots if slot.item in items
        ):
            raise VendorBatchStopped("batch items are missing, changed, or still cooking")
        save()
        try:
            for item in items:
                if item in record["excluded"]:
                    continue
                before_action()
                if cancelled():
                    record["state"] = "cancelled"
                    save()
                    return record
                fresh = current(session.inspect())
                if _items(fresh) != remaining or not any(
                    slot.item == item and slot.state == 2 for slot in fresh.slots
                ):
                    raise VendorBatchStopped("production changed outside this Keep batch")
                key = str(uuid.uuid4())
                request = {
                    "request_key": key,
                    "item_id": item,
                    "state": "prepared",
                    "expected_snapshot": fresh.encode().hex(),
                }
                record["requests"].append(request)
                save()
                result = session.keep(fresh, item, key)
                if (
                    result.request_key != key
                    or result.window != batch["window"]
                    or result.snapshot != fresh
                    or result.outcome != Outcome.SUBMITTED
                    or not result.flags & IN_FLIGHT
                    or result.flags & UNRESOLVED
                ):
                    if (
                        result.request_key == key
                        and result.window == batch["window"]
                        and result.outcome
                        in (
                            Outcome.STALE,
                            Outcome.INVALID,
                            Outcome.UNAVAILABLE,
                            Outcome.PENDING,
                            Outcome.EXHAUSTED,
                        )
                    ):
                        request["state"] = "rejected"
                    raise VendorBatchStopped("native Keep was rejected or its outcome is uncertain")
                request["state"] = "submitted"
                save()
                deadline = clock() + acceptance_timeout
                while True:
                    if cancelled():
                        record["state"] = "cancelled_pending"
                        save()
                        return record
                    if clock() >= deadline:
                        raise VendorBatchStopped(
                            "Keep timed out; never retry without reconciliation"
                        )
                    receipt = session.inspect()
                    observed = current(receipt, pending=True)
                    if receipt.transition_request == key:
                        if (
                            receipt.transition_item != item
                            or not receipt.flags & READY
                            or _items(observed) != remaining - {item}
                        ):
                            raise VendorBatchStopped("ambiguous inventory transition")
                        request["state"] = "observed_in_inventory"
                        record["kept"].append(item)
                        remaining.remove(item)
                        save()
                        break
                    if not receipt.flags & IN_FLIGHT:
                        raise VendorBatchStopped("native Keep ownership lost")
                    sleeper(0.1)
            record["state"] = "complete"
            save()
            return record
        except BaseException as exc:
            record["state"] = (
                "uncertain"
                if record["requests"]
                and record["requests"][-1]["state"] in ("prepared", "submitted")
                else "stopped"
            )
            record["reason"] = str(exc) or type(exc).__name__
            save()
            raise
