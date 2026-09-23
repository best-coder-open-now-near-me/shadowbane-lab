"""Durable Keep of completed batch items; unknown affixes are preserved."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from shadowbane_lab.client_observation.reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES
from shadowbane_lab.equipment.crafting_assessment import assess_native_crafting_roll
from shadowbane_lab.record_store import (
    exclusive_record_lock,
    publish_atomic_record,
    read_record_bytes,
)

from .action_channel import NativeClientProcessIdentity
from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_wire import IN_FLIGHT, READY, UNRESOLVED, Outcome, Receipt, Snapshot


class CompletionSession(Protocol):
    identity: NativeClientProcessIdentity

    def inspect(self) -> Receipt: ...
    def keep(self, expected: Snapshot, item: int, request_key: str) -> Receipt: ...


def _read_record(path: Path, limit: int = 1024 * 1024) -> bytes:
    data = read_record_bytes(path, limit)
    if len(data) > limit:
        raise ValueError("vendor evidence exceeds its size bound")
    return data


def _observed_requests(batch: dict, initial: Snapshot, items: list) -> bool:
    """Validate one-to-one legacy receipts or the complete multiple-slot chain."""
    requests = batch.get("requests")
    if not isinstance(requests, list) or len(requests) > 16:
        return False
    if any(not isinstance(r, dict) or r.get("state") != "observed" for r in requests):
        return False
    multiple = batch["schema_version"] == 2
    if initial.multiple != int(multiple):
        return False
    seen = _items(initial)
    flattened = []
    keys = set()
    capacity = len(initial.slots)
    try:
        for request in requests:
            key = str(uuid.UUID(request["request_key"]))
            expected = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            additions = request["item_ids"] if multiple else [request["item_id"]]
            count = request["expected_item_count"] if multiple else 1
            if (
                key in keys or not uuid.UUID(key).int
                or not expected.random_scepter or expected.multiple != initial.multiple
                or _owner(expected) != _owner(initial)
                or not capacity <= len(expected.slots) <= batch["capacity"]
                or _items(expected) != seen
                or type(count) is not int or not 0 < count <= expected.free_slots
                or (multiple and count != expected.free_slots)
                or not isinstance(additions, list) or len(additions) != count
                or any(type(item) is not int or not 0 < item < 2**32 for item in additions)
                or len(set(additions)) != count or seen & set(additions)
            ):
                return False
            keys.add(key)
            capacity = len(expected.slots)
            seen.update(additions)
            flattened.extend(additions)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    return flattened == items


def validate_completed_batch(raw: bytes) -> tuple[dict, Snapshot]:
    """Validate the complete observed chain, including historical single-slot jobs.

    A terminal label alone cannot certify completion after a job-save gap. These
    checks never adopt pending requests or grant authority to replay commands.
    """
    try:
        batch = json.loads(raw)
        initial = Snapshot.decode(bytes.fromhex(batch["initial_snapshot"]))
        items, capacity = batch["items"], batch["capacity"]
        history = batch["capacity_history"]
        if (
            type(batch["schema_version"]) is not int or batch["schema_version"] not in (1, 2)
            or batch["operation"] != "fill_available_slots" or batch["state"] != "complete"
            or not uuid.UUID(batch["batch_id"]).int or not initial.random_scepter
            or any(type(batch[key]) is not int or not 0 < batch[key] < 2**bits
                   for key, bits in (("process_id", 32), ("process_creation_filetime_utc", 64),
                                     ("window", 32), ("vendor_id", 32)))
            or batch["vendor_id"] != initial.vendor
            or type(capacity) is not int or not len(initial.slots) <= capacity <= 16
            or not isinstance(history, list) or not 1 <= len(history) <= 16
            or any(type(value) is not int for value in history)
            or history != sorted(set(history))
            or history[0] != len(initial.slots) or history[-1] != capacity
            or type(batch["planned_rolls"]) is not int
            or batch["planned_rolls"] != capacity - len(_items(initial))
            or not isinstance(items, list) or len(items) != batch["planned_rolls"]
            or any(type(item) is not int or not 0 < item < 2**32 for item in items)
            or len(set(items)) != len(items) or set(items) & _items(initial)
            or not _observed_requests(batch, initial, items)
        ):
            raise ValueError("inconsistent completed Create evidence")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("expected a complete, observed vendor Create journal") from exc
    return batch, initial


def validate_completed_keep(raw: bytes, batch_raw: bytes) -> dict:
    """Require the exact source batch and its observed inventory receipt chain.

    At most sixteen receipts are checked once at recovery. This reads historical
    evidence only; it never adopts pending requests or sends native commands.
    """
    batch, initial = validate_completed_batch(batch_raw)
    try:
        kept = json.loads(raw)
        items = batch["items"]
        decisions = kept["decisions"]
        requests = kept["requests"]
        if (
            type(kept["schema_version"]) is not int or kept["schema_version"] != 1
            or kept["operation"] != "keep_completed_batch" or kept["state"] != "complete"
            or not items
            or kept["source_batch_sha256"] != hashlib.sha256(batch_raw).hexdigest()
            or any(type(kept[key]) is not type(batch[key]) or kept[key] != batch[key]
                   for key in ("batch_id", "process_id", "process_creation_filetime_utc",
                               "window", "vendor_id"))
            or not isinstance(decisions, dict) or set(decisions) != {str(item) for item in items}
            or any(not isinstance(value, dict)
                   or value.get("disposition") not in ("keep", "exclude")
                   for value in decisions.values())
            or not isinstance(kept["kept"], list) or not isinstance(kept["excluded"], list)
            or any(type(item) is not int for item in kept["kept"] + kept["excluded"])
            or kept["kept"] != [item for item in items
                                if decisions[str(item)]["disposition"] == "keep"]
            or kept["excluded"] != [item for item in items
                                    if decisions[str(item)]["disposition"] == "exclude"]
            or not isinstance(requests, list) or len(requests) != len(kept["kept"])
        ):
            raise ValueError("inconsistent completed Keep evidence")
        remaining = _items(initial) | set(items)
        capacity = batch["capacity"]
        keys = {str(uuid.UUID(request["request_key"])) for request in batch["requests"]}
        for item, request in zip(kept["kept"], requests, strict=True):
            key = str(uuid.UUID(request["request_key"]))
            expected = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            if (
                key in keys or not uuid.UUID(key).int
                or request["state"] != "observed_in_inventory"
                or type(request["item_id"]) is not int or request["item_id"] != item
                or _owner(expected) != _owner(initial) or not expected.inventory
                or len(expected.slots) < capacity or _items(expected) != remaining
                or any(slot.state != 2 for slot in expected.slots if slot.item in items)
            ):
                raise ValueError("inconsistent inventory receipt chain")
            keys.add(key)
            capacity = len(expected.slots)
            remaining.remove(item)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("expected a complete Keep journal for the exact Create batch") from exc
    return kept


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
            not in REVIEWED_VENDOR_EXECUTABLES
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
    batch, initial = validate_completed_batch(raw)
    items = batch["items"]
    if (
        not items
        or batch["process_id"] != session.identity.process_id
        or batch["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
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
                            or receipt.flags & (IN_FLIGHT | UNRESOLVED)
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
