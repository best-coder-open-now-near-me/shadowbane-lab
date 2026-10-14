"""Collect existing completed vendor items without inventing Create provenance."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

from .movement_wire import request_bytes
from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_completion import _read_record
from .vendor_menu import open_inventory, validate_completed_menu
from .vendor_wire import IN_FLIGHT, READY, UNRESOLVED, Outcome, Snapshot, uint

LIMIT = 512 * 1024


def _bytes(record):
    return (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()


def _context(value):
    try:
        identity, owner = value["identity"], value["owner"]
        return (type(value) is dict and set(value) == {"identity", "owner"}
                and type(identity) is list and len(identity) == 3
                and all(isinstance(part, str) and part for part in identity)
                and isinstance(owner["server"], str) and bool(owner["server"])
                and isinstance(owner["character"], str) and bool(owner["character"])
                and type(owner["key"]) is list and len(owner["key"]) == 2
                and type(owner["key"][0]) is int and 0 < owner["key"][0] < 2**32
                and type(owner["key"][1]) is int and owner["key"][1] == 53)
    except (KeyError, TypeError, IndexError):
        return False


def validate_collection(raw):
    """Validate historical inventory receipts; never adopt or replay requests."""
    try:
        if type(raw) is not bytes or len(raw) > LIMIT:
            raise ValueError("collection evidence exceeds its bound")
        r = json.loads(raw)
        initial = Snapshot.decode(bytes.fromhex(r["initial_snapshot"]))
        final = Snapshot.decode(bytes.fromhex(r["final_snapshot"]))
        request_bytes(r["collection_id"])
        if (type(r["schema_version"]) is not int or r["schema_version"] != 1
                or r["operation"] != "collect_existing_completed_items" or r["state"] != "complete"
                or not _context(r["context"])
                or type(r["creates"]) is not int or r["creates"] != 0
                or type(r["funds_moved"]) is not int or r["funds_moved"] != 0
                or type(r["items"]) is not list or type(r["requests"]) is not list
                or any(type(item) is not int for item in r["items"])
                or initial.empty or any(slot.state == 1 for slot in initial.slots)
                or r["items"] != sorted(_items(initial))
                or len(r["requests"]) != len(r["items"])
                or _owner(final) != _owner(initial) or _items(final)
                or len(final.slots) < len(initial.slots)):
            raise ValueError("invalid completed collection")
        for key, bits in (("process_id", 32), ("creation", 64), ("window", 32)):
            if not uint(r[key], bits, key):
                raise ValueError("collection client identity is missing")
        if r["items"]:
            menu, before, after = validate_completed_menu(r["inventory_menu_utf8"].encode())
            if (menu["operation"] != "open_inventory" or before.owner != _owner(initial)
                    or not after.inventory
                    or (menu["process_id"], menu["process_creation_filetime_utc"], menu["window"])
                    != (r["process_id"], r["creation"], r["window"])):
                raise ValueError("collection Inventory evidence changed owner")
        remaining, keys, revision = set(r["items"]), set(), initial.revision
        for item, request in zip(r["items"], r["requests"], strict=True):
            key = request["request_key"]
            request_bytes(key)
            before = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            receipt = request["receipt"]
            after = Snapshot.decode(bytes.fromhex(receipt["snapshot"]))
            if (key in keys or request["state"] != "observed_in_inventory"
                    or type(request["item"]) is not int or request["item"] != item
                    or _owner(before) != _owner(initial) or _owner(after) != _owner(initial)
                    or _items(before) != remaining or _items(after) != remaining - {item}
                    or not before.inventory or not after.inventory
                    or not revision <= before.revision <= after.revision
                    or not any(slot.item == item and slot.state == 2 for slot in before.slots)
                    or receipt["transition_request"] != key or receipt["transition_item"] != item
                    or type(receipt["transition_item"]) is not int
                    or type(receipt["outcome"]) is not int
                    or receipt["outcome"] != int(Outcome.OBSERVED)
                    or type(receipt["flags"]) is not int or receipt["flags"] not in (0, READY)
                    or type(receipt["window"]) is not int or receipt["window"] != r["window"]):
                raise ValueError("collection Keep lacks positive native inventory proof")
            keys.add(key)
            remaining.remove(item)
            revision = after.revision
        if final.revision < revision:
            raise ValueError("collection final observation moved backwards")
        return r
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        raise ValueError("expected a complete, native-confirmed vendor collection") from exc


def collect_completed_items(session, journal: Path, *, context, cancelled=lambda: False,
                            clock=time.monotonic, sleeper=time.sleep):
    """Retain each existing completed item once, then leave its Inventory open.

    The caller owns the worker execution lock and verified character context.
    This journal is independent of historical Create jobs and grants no spending.
    """
    journal = Path(journal)
    with exclusive_record_lock(journal.with_suffix(".lock")):
        if journal.exists():
            raise VendorBatchStopped("collection exists; never replay its Keep requests")
        if not _context(context):
            raise ValueError("collection requires the verified worker and character context")
        first = session.inspect()
        initial = first.snapshot
        initial.encode()
        if (first.outcome != Outcome.OBSERVED or first.window != session.window
                or first.flags & (IN_FLIGHT | UNRESOLVED)
                or initial.empty or any(slot.state == 1 for slot in initial.slots)):
            raise VendorBatchStopped("existing vendor production is not ready for collection")
        record = dict(schema_version=1, operation="collect_existing_completed_items",
                      state="running",
                      collection_id=str(uuid.uuid4()), context=json.loads(json.dumps(context)),
                      process_id=session.identity.process_id,
                      creation=session.identity.creation_filetime_utc, window=first.window,
                      initial_snapshot=initial.encode().hex(), items=sorted(_items(initial)),
                      requests=[], creates=0, funds_moved=0)
        remaining = set(record["items"])

        def save():
            publish_atomic_record(journal, _bytes(record), temporary_label="vendor-collection")

        def current(*, pending=False):
            receipt = session.inspect()
            s = receipt.snapshot
            if (receipt.outcome != Outcome.OBSERVED or receipt.window != first.window
                    or _owner(s) != _owner(initial) or receipt.flags & UNRESOLVED
                    or not pending and receipt.flags & IN_FLIGHT
                    or len(s.slots) < len(initial.slots)
                    or any(slot.state == 1 for slot in s.slots)
                    or not _items(s) <= remaining):
                raise VendorBatchStopped("collection production ownership changed")
            return receipt

        def ready():
            deadline = clock() + 60
            while True:
                if cancelled():
                    raise VendorBatchStopped("collection cancelled before its next action")
                receipt = current()
                if receipt.flags == READY:
                    return receipt
                if clock() >= deadline:
                    raise VendorBatchStopped("collection is waiting for game focus; no retry sent")
                session.renew_lease()
                sleeper(.25)

        save()
        try:
            observed = first
            if remaining:
                menus = session.menu_session()
                try:
                    menu_path = journal.parent / "inventory-menu.json"
                    open_inventory(menus, menu_path, menus.inspect().snapshot,
                                   before_action=ready, cancelled=cancelled, clock=clock,
                                   sleeper=sleeper)
                    record["inventory_menu_utf8"] = _read_record(menu_path, 256 * 1024).decode()
                    save()
                finally:
                    menus.close()
            for item in record["items"]:
                before = ready()
                if (_items(before.snapshot) != remaining or not before.snapshot.inventory
                        or not any(slot.item == item and slot.state == 2
                                   for slot in before.snapshot.slots)):
                    raise VendorBatchStopped("completed collection item changed before Keep")
                key = str(uuid.uuid4())
                request = dict(request_key=key, item=item, state="prepared",
                               expected_snapshot=before.snapshot.encode().hex())
                record["requests"].append(request)
                save()
                submitted = session.keep(before.snapshot, item, key)
                if (submitted.request_key != key or submitted.window != first.window
                        or submitted.outcome != Outcome.SUBMITTED or submitted.flags != IN_FLIGHT
                        or submitted.snapshot != before.snapshot):
                    raise VendorBatchStopped(
                        "collection Keep submission is uncertain; never replay")
                request["state"] = "submitted"
                save()
                deadline = clock() + 15
                while True:
                    observed = current(pending=True)
                    if observed.transition_request == key:
                        receipt = dict(snapshot=observed.snapshot.encode().hex(),
                                       outcome=int(observed.outcome), flags=observed.flags,
                                       window=observed.window, transition_request=key,
                                       transition_item=observed.transition_item)
                        if (observed.flags & (IN_FLIGHT | UNRESOLVED)
                                or observed.transition_item != item
                                or _items(observed.snapshot) != remaining - {item}
                                or not observed.snapshot.inventory):
                            raise VendorBatchStopped(
                                "collection lacks native inventory confirmation")
                        request.update(state="observed_in_inventory", receipt=receipt)
                        remaining.remove(item)
                        save()
                        break
                    if not observed.flags & IN_FLIGHT or clock() >= deadline:
                        raise VendorBatchStopped("collection Keep is unconfirmed; never replay")
                    session.renew_lease()
                    sleeper(.1)
            record.update(state="complete", final_snapshot=observed.snapshot.encode().hex())
            validate_collection(_bytes(record))
            save()
            return record
        except BaseException as exc:
            record.update(state="review", detail=str(exc) or type(exc).__name__)
            save()
            raise
