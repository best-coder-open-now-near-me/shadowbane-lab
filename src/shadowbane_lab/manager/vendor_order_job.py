"""Exact-worker quantity jobs: prepare, queue, observe and retain one funded batch."""
from __future__ import annotations

import time
import uuid

from shadowbane_lab.client_extension.event_reader import WindowsSharedMemorySnapshotReader
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, _owner
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_menu import (
    open_inventory,
    prepare_order,
    validate_completed_menu,
)
from shadowbane_lab.client_extension.vendor_order_batch import (
    queue_quantity_orders,
    validate_queued_orders,
)
from shadowbane_lab.client_extension.vendor_order_ledger import LIMIT, OrderLedger
from shadowbane_lab.client_extension.vendor_production_responses import VendorProductionReader
from shadowbane_lab.client_extension.vendor_recipe import (
    RandomOrderSpec,
    validate_recipe_preparation,
)
from shadowbane_lab.client_extension.vendor_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Outcome,
    Snapshot,
)
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_vendor_queue import read_native_vendor_queue


class _OrderJobStopped(VendorBatchStopped):
    pass


def production_reader(session, cursor=None):
    return VendorProductionReader(session.identity.process_id,
                                   session.identity.creation_filetime_utc,
                                   WindowsSharedMemorySnapshotReader(), resume_cursor=cursor)


def inventory_presence(session, state, known, template):
    memory = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", session.identity.process_id)
    try:
        if memory.process_creation_filetime_utc != session.identity.creation_filetime_utc:
            raise VendorBatchStopped("quantity inventory client lifetime changed")
        observed = read_native_vendor_queue(memory)
    finally:
        memory.close()
    inventory = observed["inventory"]
    if (observed["process_id"] != session.identity.process_id
            or observed["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
            or observed["native_window_address"] != state.root
            or observed["manager_address"] != state.manager
            or observed["menu_address"] != state.menu
            or observed["building"] != dict(object_id=state.building, object_type=8)
            or observed["vendor"] != dict(object_id=state.vendor, object_type=42)
            or inventory is None or inventory["window_address"] != state.inventory):
        raise VendorBatchStopped("quantity inventory belongs to another vendor visit")
    items = []
    for row in inventory["items"]:
        item = row["item"]["object_id"]
        if item in known:
            if row["template"] != dict(object_id=template, object_type=0):
                raise VendorBatchStopped("quantity inventory item changed template")
            items.append(item)
    return items


def require_order_handoff_idle(store, session, record):
    initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
    fresh = session.inspect_orders()
    if (fresh.outcome != Outcome.OBSERVED or fresh.window != record["window"]
            or fresh.flags & (IN_FLIGHT | UNRESOLVED)
            or _owner(fresh.snapshot) != _owner(initial)):
        raise VendorBatchStopped("quantity handback remains unresolved")
    directory = store.directory(record["job_id"])
    if record["planned_items"]:
        raw = _read_record(directory / "create.json", LIMIT)
        ledger = OrderLedger(directory / "order-progress.json", raw,
                             tuple(record["recipe_owner"]["key"]), resume=True)
        admission = ledger.progress.admission
        if (any(admission[key] != record[key] for key in (
                "process_id", "process_creation_filetime_utc", "window"))
                or admission["batch_budget_sha256"] != record["batch_budget_sha256"]
                or admission["recipe_sha256"] != record["order_sha256"]
                or _owner(ledger.progress.initial) != _owner(initial)):
            raise VendorBatchStopped("quantity handback evidence changed job")
        ledger.progress.observe(fresh.snapshot, fresh.remaining_counts)
        if (record["state"] not in ("complete", "stopped")
                or record["state"] == "complete" and not ledger.progress.complete
                or record["created"] != len(ledger.progress.items)
                or record["kept"] != len(ledger.progress.inventory_confirmed)):
            raise VendorBatchStopped("quantity batch has unfinished inventory evidence")
    for path in directory.glob("order-*.json"):
        if path.name == "order-progress.json":
            continue
        menu, before, _ = validate_completed_menu(_read_record(path, 256 * 1024))
        if (any(menu[key] != record[key] for key in (
                "process_id", "process_creation_filetime_utc", "window"))
                or before.owner != _owner(initial)):
            raise VendorBatchStopped("quantity menu handback changed owner")


def run_order_job(store, session, record, *, cancelled=lambda: False, clock=time.time,
                  sleeper=time.sleep, reader_factory=production_reader,
                  inventory_reader=inventory_presence):
    """Caller owns execution.lock. Never replay partial Create/menu/Keep evidence."""
    directory = store.directory(record["job_id"])
    create_path, progress_path = directory / "create.json", directory / "order-progress.json"
    initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
    spec = RandomOrderSpec.from_dict(record["order_spec"])
    budget = VendorBatchBudget.from_dict(record["batch_budget"])
    ledger, reader, queue_tick = None, None, None

    def update(state, detail):
        previous = dict(record)
        record.update(state=state, detail=detail)
        if ledger is not None:
            summary = ledger.progress.summary()
            record.update(created=summary["generated"], kept=summary["kept"],
                          capacity=summary["capacity"])
        if record != previous:
            store.save(record)

    def stopped():
        return cancelled() or store.control(record["job_id"]) == "stop"

    def pump():
        if ledger is not None:
            ledger.drain(reader)
        elif queue_tick is not None:
            queue_tick()

    def before_action():
        while True:
            pump()
            if stopped():
                raise _OrderJobStopped("quantity job stopped; production remains journaled")
            if clock() >= record["deadline_at"]:
                raise VendorBatchStopped("quantity job time limit reached; review remaining items")
            if store.control(record["job_id"]) == "pause":
                update("paused", "Paused. Production observation continues.")
                session.renew_lease()
                sleeper(0.25)
                continue
            receipt = session.inspect_orders()
            if (receipt.outcome != Outcome.OBSERVED or receipt.window != record["window"]
                    or _owner(receipt.snapshot) != _owner(initial)
                    or receipt.flags & (IN_FLIGHT | UNRESOLVED)):
                raise VendorBatchStopped("quantity vendor authority changed")
            if receipt.flags & READY:
                return receipt
            update("attention", "Return focus to Shadowbane; production observation continues.")
            sleeper(0.25)

    def prepare(index):
        path = directory / f"order-preparation-{index:02d}.json"
        before_action()
        menus = session.menu_session()
        try:
            if not path.exists():
                prepare_order(menus, path, menus.inspect().snapshot, spec,
                              before_action=before_action, cancelled=stopped)
            raw = _read_record(path, 256 * 1024)
            validate_recipe_preparation(
                raw, spec, session.inspect_orders().snapshot,
                process_id=record["process_id"],
                process_creation_filetime_utc=record["process_creation_filetime_utc"],
                window=record["window"],
            )
            return raw
        finally:
            menus.close()

    def queue_gate(tick):
        nonlocal queue_tick
        queue_tick = tick
        before_action()

    try:
        if not create_path.exists():
            if record["phase"] not in ("preparing", "filling"):
                raise VendorBatchStopped("quantity Create evidence is missing")
            if not budget.free_slots:
                update("complete", "No free production slots. No new orders were created.")
                return record
            reader = reader_factory(session)
            reader.available()
            prep = prepare(0)
            record["phase"] = "filling"
            update("running", f"Queuing {budget.free_slots} orders of {spec.quantity} items.")
            queue_quantity_orders(session, create_path, spec, budget, prep, reader,
                                  character=tuple(record["recipe_owner"]["key"]),
                                  await_authority=queue_gate,
                                  cancelled=stopped)
            queue_tick = None
        admission_raw = _read_record(create_path, LIMIT)
        admission, before = validate_queued_orders(admission_raw)
        if (any(admission[key] != record[key] for key in (
                "process_id", "process_creation_filetime_utc", "window"))
                or _owner(before) != _owner(initial)
                or admission["batch_budget_sha256"] != record["batch_budget_sha256"]
                or admission["recipe_sha256"] != spec.canonical_digest):
            raise VendorBatchStopped("quantity admission belongs to another job")
        ledger = OrderLedger(progress_path, admission_raw, tuple(record["recipe_owner"]["key"]),
                             resume=progress_path.exists())
        if reader is None:
            reader = reader_factory(session, ledger.record["cursor"])
        record.update(phase="waiting", queued_orders=admission["planned_orders"],
                      planned_items=admission["planned_items"])
        update("cooking", "Orders queued. Tracking each item; unknown affixes are retained.")
        opened = False
        while True:
            fresh = before_action()
            pump()  # Catch replies processed between the preceding drain and observation.
            if not fresh.snapshot.inventory:
                if opened:
                    raise VendorBatchStopped("quantity Inventory was closed outside this job")
                menus = session.menu_session()
                try:
                    path = directory / "order-inventory-menu.json"
                    if path.exists():
                        raise VendorBatchStopped("quantity Inventory journal cannot be replayed")
                    open_inventory(menus, path, menus.inspect().snapshot,
                                   before_action=before_action, cancelled=stopped)
                finally:
                    menus.close()
                opened = True
                continue
            opened = True
            p = ledger.progress
            present = inventory_reader(session, fresh.snapshot, set(p.items), spec.template)
            ledger.inventory(fresh.snapshot, present)
            ledger.observe(fresh)
            if p.complete:
                ledger.record["state"] = "complete"
                ledger.save()
                update("complete", "Batch finished; every planned item is confirmed in inventory.")
                return record
            item = p.keep_candidate(fresh.snapshot)
            if item is None:
                update("cooking", f"Generated {len(p.items)}/{budget.total_items}; "
                       f"inventory confirmed {len(p.inventory_confirmed)}. Waiting for production.")
                sleeper(0.5)
                continue
            key = str(uuid.uuid4())
            request = ledger.prepared_keep(fresh.snapshot, key, item)
            # Last-moment permit/focus check after durable intent, before dispatch.
            again = before_action()
            if again.snapshot != fresh.snapshot:
                raise VendorBatchStopped("quantity production changed before Keep")
            result = session.keep(fresh.snapshot, item, key)
            if (result.request_key != key or result.window != record["window"]
                    or result.snapshot != fresh.snapshot or result.outcome != Outcome.SUBMITTED
                    or result.flags != IN_FLIGHT):
                raise VendorBatchStopped("quantity Keep submission is uncertain; never replay")
            request["state"] = "submitted"
            ledger.save()
            deadline = clock() + 15
            while True:
                pump()
                observed = session.inspect()
                if (observed.outcome != Outcome.OBSERVED or observed.window != record["window"]
                        or _owner(observed.snapshot) != _owner(initial)
                        or observed.flags & UNRESOLVED):
                    raise VendorBatchStopped("quantity Keep authority changed")
                if observed.transition_request == key:
                    ledger.kept(request, observed)
                    break
                if not observed.flags & IN_FLIGHT or clock() >= deadline:
                    raise VendorBatchStopped("quantity Keep remains unconfirmed; never replay")
                sleeper(0.1)
            fresh = session.inspect_orders()
            pump()
            ledger.observe(fresh, kept_item=item)
            update("cooking", "Item confirmed in inventory. Continuing the existing orders.")
    except Exception as exc:
        if (isinstance(exc, _OrderJobStopped) and ledger is not None
                and all(r["state"] == "observed" for r in ledger.record["requests"])):
            ledger.record["state"] = "stopped"
            ledger.save()
            update("stopped", "Stopped. Existing orders and item receipts remain saved.")
            return record
        if ledger is not None:
            ledger.record["state"] = "review"
            ledger.save()
        update("review", str(exc)[:240] or "Quantity job needs review; no replay sent.")
        raise
