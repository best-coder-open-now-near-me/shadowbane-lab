"""Continue a definitively admitted review batch from complete passive evidence.

Neither importing observations nor resuming grants Create or funding authority.
All previous Keep intents must already have correlated inventory receipts.
"""
from __future__ import annotations

import hashlib
import json

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped, _owner
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_menu import validate_completed_menu
from shadowbane_lab.client_extension.vendor_order_batch import validate_queued_orders
from shadowbane_lab.client_extension.vendor_order_ledger import LIMIT, OrderLedger
from shadowbane_lab.client_extension.vendor_production_responses import CAPACITY
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, UNRESOLVED, Outcome, Snapshot
from shadowbane_lab.record_store import exclusive_record_lock

from .vendor_job import _write


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _review(store, record):
    directory = store.directory(record["job_id"])
    if record["schema_version"] != 4 or record["state"] != "review":
        raise VendorBatchStopped("only a proven quantity review job can be reconciled")
    raw = _read_record(directory / "create.json", LIMIT)
    admission, initial = validate_queued_orders(raw)
    if (any(admission[key] != record[key] for key in (
            "process_id", "process_creation_filetime_utc", "window"))
            or _owner(initial) != _owner(Snapshot.decode(bytes.fromhex(record["initial_snapshot"])))
            or admission["batch_budget_sha256"] != record["batch_budget_sha256"]
            or admission["recipe_sha256"] != record["order_sha256"]):
        raise VendorBatchStopped("review admission belongs to another funded batch")
    path = directory / "order-progress.json"
    if not path.is_file():
        raise VendorBatchStopped("review progress is missing; no reconstruction can invent it")
    ledger = OrderLedger(path, raw, tuple(record["recipe_owner"]["key"]), resume=True, review=True)
    if ledger.record["state"] != "review":
        raise VendorBatchStopped("review job has inconsistent progress state")
    for path in directory.glob("order-*.json"):
        if path.name == "order-progress.json":
            continue
        menu, before, _ = validate_completed_menu(_read_record(path, 256 * 1024))
        if (any(menu[key] != record[key] for key in (
                "process_id", "process_creation_filetime_utc", "window"))
                or before.owner != _owner(initial)):
            raise VendorBatchStopped("review contains an unfinished or unrelated menu")
    return ledger, initial


def _capture(ledger, raw):
    if type(raw) is not bytes or len(raw) > 16 * 1024 * 1024:
        raise ValueError("passive review capture exceeds its bound")
    lines = raw.splitlines(keepends=True)
    if lines and not lines[-1].endswith(b"\n"):
        lines.pop()  # A live append is not evidence until its whole line is present.
    entries = [json.loads(line) for line in lines]
    admission = ledger.progress.admission
    if (not entries or entries[0].get("kind") != "started"
            or type(entries[0].get("schema_version")) is not int
            or entries[0]["schema_version"] != 3
            or entries[0].get("process_id") != admission["process_id"]
            or entries[0].get("creation") != admission["process_creation_filetime_utc"]
            or type(entries[0].get("native_commands_sent")) is not int
            or entries[0]["native_commands_sent"] != 0):
        raise VendorBatchStopped("passive review capture belongs to another lifetime")
    previous, received = 0, []
    base = ledger.record["cursor"]
    for index, entry in enumerate(entries[1:], start=1):
        if entry.get("kind") == "stopped":
            if (index != len(entries) - 1 or type(entry.get("sequence")) is not int
                    or entry["sequence"] != previous
                    or type(entry.get("native_commands_sent")) is not int
                    or entry["native_commands_sent"] != 0):
                raise VendorBatchStopped("passive review stop changed its cursor")
            continue
        if (entry.get("kind") != "records" or type(entry.get("missed")) is not int
                or entry["missed"] != 0 or type(entry.get("records")) is not list
                or not entry["records"] or type(entry.get("sequence")) is not int
                or entry["sequence"] != entry["records"][-1]["sequence"]
                or type(entry.get("overwritten")) is not int
                or entry["overwritten"] != max(0, entry["sequence"] - CAPACITY)
                or any(type(entry.get(k)) is not int or entry[k] != base[k]
                       for k in ("rejected", "ticket_drops"))):
            raise VendorBatchStopped("passive review capture is incomplete")
        for event in entry["records"]:
            if type(event["sequence"]) is not int or event["sequence"] != previous + 1:
                raise VendorBatchStopped("passive review capture has a gap")
            previous += 1
            if previous > base["sequence"]:
                received.append(event)
    if previous < base["sequence"] or len(received) > 4096:
        raise VendorBatchStopped("passive review capture does not cover the saved cursor")
    ledger.progress.receive(received)
    cursor = dict(base, sequence=previous, overwritten=max(0, previous - CAPACITY))
    ledger._validate_cursor(cursor)
    return received, cursor


def retain_review_capture(store, job_id, raw):
    """Retain independently validated passive history, without commands or job edits."""
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=.1):
        record = store.current()
        if not record or record["job_id"] != job_id:
            raise VendorBatchStopped("review job is no longer current")
        ledger, _ = _review(store, record)
        directory = store.directory(job_id)
        path = directory / "review-observation.json"
        if path.exists():
            raise VendorBatchStopped("review observations exist; never silently replace them")
        original = _read_record(ledger.path, LIMIT)
        received, cursor = _capture(ledger, raw)
        result = dict(schema_version=1, operation="retain_review_production", job_id=job_id,
                      identity=list(store.identity),
                      admission_sha256=ledger.record["admission_sha256"],
                      progress_sha256=_digest(original), capture_sha256=_digest(raw),
                      base_cursor=ledger.record["cursor"], cursor=cursor, records=received,
                      creates=0, funds_moved=0, keeps=0)
        _write(path, result)
        return result


def review_job_ready(store, record):
    ledger, initial = _review(store, record)
    directory = store.directory(record["job_id"])
    raw = _read_record(directory / "review-observation.json", LIMIT)
    receipt = json.loads(raw)
    if (type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or receipt["operation"] != "retain_review_production"
            or receipt["job_id"] != record["job_id"] or receipt["identity"] != list(store.identity)
            or receipt["admission_sha256"] != ledger.record["admission_sha256"]
            or receipt["progress_sha256"] != _digest(_read_record(ledger.path, LIMIT))
            or json.dumps(receipt["base_cursor"], sort_keys=True)
            != json.dumps(ledger.record["cursor"], sort_keys=True)
            or any(type(receipt[k]) is not int or receipt[k] != 0
                   for k in ("creates", "funds_moved", "keeps"))):
        raise VendorBatchStopped("review observations changed the original batch")
    ledger.progress.receive(receipt["records"])
    ledger._validate_cursor(receipt["cursor"])
    return ledger, initial, receipt


def resume_review(store, session, record):
    """Caller owns execution.lock. Only received evidence is added before continuation."""
    ledger, initial, receipt = review_job_ready(store, record)
    if (session.identity.process_id != record["process_id"]
            or session.identity.creation_filetime_utc != record["process_creation_filetime_utc"]):
        raise VendorBatchStopped("review client lifetime changed")
    observed = session.inspect_orders()
    if (observed.outcome != Outcome.OBSERVED or observed.window != record["window"]
            or observed.flags & (IN_FLIGHT | UNRESOLVED)
            or _owner(observed.snapshot) != _owner(initial)):
        raise VendorBatchStopped("review native authority changed")
    menus = session.menu_session()
    try:
        menu = menus.inspect()
        if (int(menu.outcome) != int(Outcome.OBSERVED) or menu.window != record["window"]
                or menu.flags & (IN_FLIGHT | UNRESOLVED) or menu.snapshot.owner != _owner(initial)):
            raise VendorBatchStopped("review menu authority changed")
    finally:
        menus.close()
    directory = store.directory(record["job_id"])
    intent = directory / "review-continuation.json"
    if intent.exists():
        raise VendorBatchStopped("review continuation was attempted; inspect without replay")
    recovery = dict(state="prepared", job_id=record["job_id"], identity=list(store.identity),
                    prior_job=json.loads(json.dumps(record)),
                    observation_sha256=_digest(_read_record(
                        directory / "review-observation.json", LIMIT)),
                    original_progress_sha256=receipt["progress_sha256"], creates=0, funds_moved=0)
    _write(intent, recovery)
    # Reconstruct again so adding the receipt event does not double-apply it.
    ledger, _ = _review(store, record)
    ledger.append(dict(kind="received", records=receipt["records"]))
    ledger.record.update(cursor=receipt["cursor"], state="running")
    ledger._validate_cursor(ledger.record["cursor"])
    ledger.save()
    record.update(state="cooking", detail="Continuing the proven server batch; no Create replay.")
    store.save(record)
    recovery["state"] = "observations_retained"
    _write(intent, recovery)
