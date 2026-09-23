"""Durable batch filling of available and newly unlocked vendor slots."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

from .action_channel import NativeClientProcessIdentity
from .vendor_wire import IN_FLIGHT, READY, UNRESOLVED, Outcome, Receipt, Snapshot


class VendorBatchSession(Protocol):
    identity: NativeClientProcessIdentity
    def inspect(self) -> Receipt: ...
    def create(self, expected: Snapshot, request_key: str) -> Receipt: ...


class VendorBatchStopped(RuntimeError):
    pass


def _owner(s: Snapshot) -> tuple[int, ...]:
    return (s.scene, s.root, s.manager, s.menu, s.hireling, s.building, s.vendor)


def _items(s: Snapshot) -> set[int]:
    return {slot.item for slot in s.slots if slot.item}


def fill_available_slots(
    session: VendorBatchSession,
    journal: Path,
    vendor_id: int,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    before_action: Callable[[], None] = lambda: None,
    expected_owner: Snapshot | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    acceptance_timeout: float = 15.0,
) -> dict:
    """Fill free slots and newly unlocked capacity, persisting before each send.

    Existing journals are never replayed. A timeout is uncertain, not evidence
    that Create failed. A completed batch means queue transitions were observed,
    not that the items finished cooking or passed an affix filter.
    """
    if type(vendor_id) is not int or not 0 < vendor_id < 2**32:
        raise ValueError("an exact vendor ID is required")
    if not 0 < acceptance_timeout <= 60:
        raise ValueError("acceptance timeout must be between zero and 60 seconds")
    journal = Path(journal)
    with exclusive_record_lock(journal.with_suffix(journal.suffix + ".lock")):
        if journal.exists():
            raise VendorBatchStopped("journal exists; inspect it without replaying requests")
        first = session.inspect()
        initial = first.snapshot
        if (
            first.outcome != Outcome.OBSERVED or not first.flags & READY
            or first.flags & (IN_FLIGHT | UNRESOLVED)
            or initial.vendor != vendor_id or not initial.random_scepter
        ):
            raise VendorBatchStopped("the requested vendor's random recipe is not ready")
        if expected_owner is not None and (
            _owner(initial) != _owner(expected_owner)
            or _items(initial) != _items(expected_owner)
        ):
            raise VendorBatchStopped("vendor ownership or production changed before filling")
        baseline = _items(initial)
        record = {
            "schema_version": 2 if initial.multiple else 1, "operation": "fill_available_slots",
            "batch_id": str(uuid.uuid4()), "state": "running",
            "vendor_id": vendor_id, "window": first.window,
            "process_id": session.identity.process_id,
            "process_creation_filetime_utc": session.identity.creation_filetime_utc,
            "initial_snapshot": initial.encode().hex(),
            "planned_rolls": initial.free_slots, "capacity": len(initial.slots),
            "capacity_history": [len(initial.slots)], "requests": [], "items": [],
        }

        def save() -> None:
            publish_atomic_record(
                journal, (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8"),
                temporary_label="vendor-batch",
            )

        def require_current(receipt: Receipt, *, pending: bool = False) -> Snapshot:
            s = receipt.snapshot
            if (
                receipt.outcome != Outcome.OBSERVED or receipt.window != first.window
                or _owner(s) != _owner(initial) or len(s.slots) < record["capacity"]
                or receipt.flags & UNRESOLVED
                or (not pending and (
                    not s.random_scepter or s.multiple != initial.multiple
                    or not receipt.flags & READY or receipt.flags & IN_FLIGHT
                ))
            ):
                raise VendorBatchStopped("vendor, session, recipe, or operation authority changed")
            if len(s.slots) > record["capacity"]:
                record["capacity"] = len(s.slots)
                record["capacity_history"].append(len(s.slots))
                record["planned_rolls"] = len(s.slots) - len(baseline)
                save()
            return s

        save()
        try:
            while True:
                before_action()
                if cancelled():
                    record["state"] = "cancelled"
                    save()
                    return record
                fresh = require_current(session.inspect())
                expected_items = baseline | set(record["items"])
                if (
                    _items(fresh) != expected_items
                    or fresh.free_slots != record["planned_rolls"] - len(record["items"])
                ):
                    raise VendorBatchStopped("production changed outside this batch")
                if not fresh.free_slots:
                    break
                request_key = str(uuid.uuid4())
                request = {
                    "request_key": request_key, "state": "prepared",
                    "expected_snapshot": fresh.encode().hex(),
                }
                expected_count = fresh.free_slots if fresh.multiple else 1
                if initial.multiple:
                    request["expected_item_count"] = expected_count
                record["requests"].append(request)
                save()  # Must reach disk before any path can submit Create.
                result = session.create(fresh, request_key)
                if (
                    result.request_key != request_key or result.window != first.window
                    or result.outcome != Outcome.SUBMITTED or result.snapshot != fresh
                    or not result.flags & IN_FLIGHT or result.flags & UNRESOLVED
                ):
                    request["state"] = (
                        "rejected" if result.outcome in (
                            Outcome.STALE, Outcome.INVALID, Outcome.UNAVAILABLE,
                            Outcome.PENDING, Outcome.EXHAUSTED,
                        ) else "uncertain"
                    )
                    raise VendorBatchStopped(
                        f"native Create outcome: {result.outcome.name.lower()}"
                    )
                request["state"] = "submitted"
                save()
                deadline = clock() + acceptance_timeout
                seen_items = expected_items
                while True:
                    if cancelled():
                        record["state"] = "cancelled_pending"
                        save()
                        return record
                    if clock() >= deadline:
                        request["state"] = "uncertain"
                        raise VendorBatchStopped("Create timed out; outcome is uncertain")
                    receipt = session.inspect()
                    observed = require_current(receipt, pending=True)
                    observed_items = _items(observed)
                    new_items = observed_items - expected_items
                    if not seen_items <= observed_items or len(new_items) > expected_count:
                        raise VendorBatchStopped("ambiguous production transition")
                    seen_items = observed_items
                    if receipt.transition_request == request_key:
                        if (
                            len(new_items) != expected_count
                            or receipt.transition_item not in new_items
                            or observed.free_slots != (
                                record["planned_rolls"] - len(record["items"]) - expected_count
                            )
                            or receipt.flags & (IN_FLIGHT | UNRESOLVED)
                        ):
                            raise VendorBatchStopped("ambiguous production transition")
                        request["state"] = "observed"
                        if initial.multiple:
                            request["item_ids"] = sorted(new_items)
                        else:
                            request["item_id"] = receipt.transition_item
                        record["items"].extend(sorted(new_items))
                        save()
                        break
                    if not receipt.flags & IN_FLIGHT:
                        raise VendorBatchStopped("native request ownership was lost")
                    sleeper(0.1)
                # Multiple Create may close its recipe. A full correlated queue
                # completes this capacity batch without demanding another recipe.
                if initial.multiple and not observed.free_slots:
                    break
            record["state"] = "complete"
            save()
            return record
        except BaseException as exc:
            # A process crash can leave "prepared"; recovery must treat that as
            # potentially sent. Never reset it to an unsent action.
            record["state"] = (
                "uncertain" if record["requests"]
                and record["requests"][-1]["state"] in ("prepared", "submitted", "uncertain")
                else "stopped"
            )
            record["reason"] = str(exc) or type(exc).__name__
            save()
            raise
