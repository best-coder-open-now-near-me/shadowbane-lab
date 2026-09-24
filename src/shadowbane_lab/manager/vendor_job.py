"""Durable, bounded vendor jobs owned by the manager's exact client worker.

One job fills currently available capacity once, then finalizes eligible items.
Only native inventory receipts count as kept. Uncertain submissions require
review; a restart never replays a Create or Keep journal.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.vendor_batch import (
    VendorBatchStopped,
    _items,
    _owner,
    fill_available_slots,
)
from shadowbane_lab.client_extension.vendor_completion import (
    _read_record,
    keep_completed_batch,
    validate_completed_batch,
    validate_completed_keep,
)
from shadowbane_lab.client_extension.vendor_menu import (
    open_inventory,
    validate_completed_menu,
)
from shadowbane_lab.client_extension.vendor_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Outcome,
    Snapshot,
)
from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_JOB = re.compile(r"[0-9a-f]{32}\Z")
TERMINAL = {"complete", "stopped", "review"}
MAX_JOB_SECONDS = 3600
_EXTENDED_LOCAL_PREFIX = '\\\\?\\'


def _write(path: Path, value: dict) -> None:
    publish_atomic_record(
        path,
        (json.dumps(value, sort_keys=True, indent=2) + "\n").encode(),
        temporary_label="vendor-job",
    )


class VendorJobStore:
    """Instance-scoped local records; dashboard controls never mutate receipts."""

    def __init__(self, root: Path, node: str, client: str, instance: str):
        if any(
            not isinstance(v, str) or not _IDENTIFIER.fullmatch(v) for v in (node, client, instance)
        ):
            raise ValueError("vendor job requires canonical exact instance identifiers")
        root = Path(root).resolve()
        native_root = str(root)
        if os.name == "nt" and native_root.startswith(_EXTENDED_LOCAL_PREFIX):
            native_root = native_root[4:]
        if native_root.startswith('\\\\') or (
            os.name == "nt" and native_root.upper().startswith('UNC\\')
        ):
            raise ValueError("vendor jobs require local storage")
        if os.name == "nt":
            # Atomic sibling names extend beyond MAX_PATH in installed runtimes.
            # Use Win32 extended local paths without changing durable identities.
            root = Path(_EXTENDED_LOCAL_PREFIX + native_root)
        self.root = root / node / client / "vendor-jobs" / instance
        self.identity = (node, client, instance)

    def current(self) -> dict | None:
        path = self.root / "current.json"
        if not path.exists():
            return None
        pointer = json.loads(_read_record(path, 256))
        job_id = pointer["job_id"]
        return self.read(job_id)

    def directory(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _JOB.fullmatch(job_id):
            raise ValueError("invalid vendor job identifier")
        return self.root / job_id

    def read(self, job_id: str) -> dict:
        record = json.loads(_read_record(self.directory(job_id) / "job.json"))
        if (
            record.get("schema_version") != 1
            or record.get("job_id") != job_id
            or tuple(record.get("identity", ())) != self.identity
            or record.get("phase") not in {"filling", "waiting", "keeping"}
            or record.get("state")
            not in {
                "running",
                "paused",
                "cooking",
                "inventory",
                "attention",
                *TERMINAL,
            }
        ):
            raise ValueError("invalid vendor job record")
        return record

    def save(self, record: dict) -> None:
        _write(self.directory(record["job_id"]) / "job.json", record)

    def begin(self, session, window: int, now: float) -> dict:
        previous = self.current()
        if previous and previous["state"] not in {"complete", "stopped"}:
            raise VendorBatchStopped("resume or review the existing vendor job first")
        first = session.inspect()
        if (
            first.outcome != Outcome.OBSERVED
            or first.window != window
            or first.flags & (IN_FLIGHT | UNRESOLVED)
            or not first.snapshot.random_scepter
        ):
            raise VendorBatchStopped("open the selected vendor's random Gilded Scepter recipe")
        # Verify menu support on this exact native runtime before spending. A
        # newer host must not create a batch and only then discover old commands.
        menus = session.menu_session()
        try:
            supported = menus.inspect()
            if (
                supported.outcome != Outcome.OBSERVED or supported.window != window
                or supported.flags & (IN_FLIGHT | UNRESOLVED)
                or supported.snapshot.owner != _owner(first.snapshot)
            ):
                raise VendorBatchStopped("vendor menu support is not ready on this client")
        finally:
            menus.close()
        record = {
            "schema_version": 1,
            "job_id": uuid.uuid4().hex,
            "identity": self.identity,
            "state": "running",
            "phase": "filling",
            "process_id": session.identity.process_id,
            "process_creation_filetime_utc": session.identity.creation_filetime_utc,
            "window": window,
            "vendor_id": first.snapshot.vendor,
            "initial_snapshot": first.snapshot.encode().hex(),
            "capacity": len(first.snapshot.slots),
            "created": 0,
            "kept": 0,
            "excluded": 0,
            "started_at": now,
            "deadline_at": now + MAX_JOB_SECONDS,
            "detail": "Filling available production slots.",
        }
        self.save(record)
        _write(self.directory(record["job_id"]) / "control.json", {"mode": "run"})
        _write(self.root / "current.json", {"job_id": record["job_id"]})
        return record

    def control(self, job_id: str) -> str:
        record = json.loads(_read_record(self.directory(job_id) / "control.json", 256))
        if set(record) != {"mode"} or record["mode"] not in {"run", "pause", "stop"}:
            raise ValueError("invalid vendor job control")
        return record["mode"]

    def request(self, job_id: str, mode: str) -> None:
        if mode not in {"run", "pause", "stop"}:
            raise ValueError("invalid vendor job control")
        with exclusive_record_lock(self.root / "control.lock"):
            current = self.current()
            if current is None or current["job_id"] != job_id:
                raise VendorBatchStopped("vendor job changed; refresh its controls")
            if current["state"] in TERMINAL:
                raise VendorBatchStopped("this vendor job is finished or needs review")
            if self.control(job_id) == "stop":
                raise VendorBatchStopped("the vendor job has been stopped")
            _write(self.directory(job_id) / "control.json", {"mode": mode})

    def summary(self) -> dict | None:
        record = self.current()
        if record is None:
            return None
        result = {
            key: record[key]
            for key in (
                "job_id",
                "state",
                "detail",
                "capacity",
                "created",
                "kept",
                "excluded",
            )
        }
        result["control"] = self.control(record["job_id"])
        return result


def run_vendor_job(
    store: VendorJobStore,
    session,
    window: int,
    *,
    resume: bool = False,
    cancelled=lambda: False,
    clock=time.time,
    sleeper=time.sleep,
) -> dict:
    """Run one capacity batch, pausing only before new native mutations.

    A local pause lets an already-submitted request finish reconciliation. A
    lost manager permit or Stop interrupts immediately and never retries it.
    Recovery is explicit and permitted only at a fully durable phase boundary.
    """
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        CondemnProgressStore(store.root).assert_idle()
        if cancelled():
            raise VendorBatchStopped("worker dispatch is paused")
        record = store.current() if resume else store.begin(session, window, clock())
        if record is None or record["state"] in TERMINAL:
            raise VendorBatchStopped("no resumable vendor job")
        if (
            record["process_id"] != session.identity.process_id
            or record["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
            or record["window"] != window
        ):
            raise VendorBatchStopped("vendor job belongs to another client lifetime")
        directory = store.directory(record["job_id"])
        initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
        create_path, keep_path = directory / "create.json", directory / "keep.json"
        menu_path = directory / "inventory-menu.json"

        def update(state: str, detail: str):
            if record["state"] != state or record["detail"] != detail:
                record.update(state=state, detail=detail)
                store.save(record)

        def stopped() -> bool:
            return cancelled() or store.control(record["job_id"]) == "stop"

        def before_action():
            while not stopped():
                if clock() >= record["deadline_at"]:
                    raise VendorBatchStopped("one-hour job limit reached; review remaining items")
                if store.control(record["job_id"]) == "pause":
                    update("paused", "Paused. No new crafting actions will be sent.")
                    session.renew_lease()
                    sleeper(0.25)
                    continue
                receipt = session.inspect()
                s = receipt.snapshot
                if (
                    receipt.outcome != Outcome.OBSERVED
                    or receipt.window != window
                    or _owner(s) != _owner(initial)
                    or len(s.slots) < record["capacity"]
                    or receipt.flags & (IN_FLIGHT | UNRESOLVED)
                ):
                    raise VendorBatchStopped(
                        "vendor ownership or operation changed; review required"
                    )
                if receipt.flags & READY:
                    if record["state"] in {"paused", "attention"}:
                        update("running", "Continuing the current production batch.")
                    return receipt
                update(
                    "attention",
                    "Return to the game and leave this vendor window in front. "
                    "Rolling will continue when it is ready.",
                )
                sleeper(0.25)
            return None

        class GuardedSession:
            identity = session.identity
            pending_request = None

            def inspect(self):
                if self.pending_request is not None:
                    # Reconcile an action already sent even while the game is
                    # unfocused. Never wait for focus inside its receipt timeout.
                    receipt = session.inspect()
                    if (
                        receipt.transition_request == self.pending_request
                        and not receipt.flags & (IN_FLIGHT | UNRESOLVED)
                    ):
                        self.pending_request = None
                    return receipt
                receipt = before_action()
                if receipt is None:
                    raise VendorBatchStopped("dispatch revoked before vendor inspection")
                return receipt

            def create(self, expected, key):
                before_action()
                if stopped():
                    raise VendorBatchStopped("dispatch revoked before Create")
                result = session.create(expected, key)
                if result.outcome == Outcome.SUBMITTED and result.flags & IN_FLIGHT:
                    self.pending_request = key
                return result

            def keep(self, expected, item, key):
                before_action()
                if stopped():
                    raise VendorBatchStopped("dispatch revoked before Keep")
                result = session.keep(expected, item, key)
                if result.outcome == Outcome.SUBMITTED and result.flags & IN_FLIGHT:
                    self.pending_request = key
                return result

        guarded = GuardedSession()

        try:
            # An acknowledgement lost across restart remains unresolved even if
            # a window now happens to be visible. Never replay that journal.
            if menu_path.exists():
                menu_record, menu_initial, _ = validate_completed_menu(
                    _read_record(menu_path, 256 * 1024)
                )
                if (
                    menu_record["operation"] != "open_inventory"
                    or any(menu_record[key] != record[key] for key in (
                        "process_id", "process_creation_filetime_utc", "window",
                    ))
                    or menu_initial.owner != _owner(initial)
                ):
                    raise VendorBatchStopped("menu evidence belongs to another vendor or client")
            # Read each bounded journal once. A completed label cannot replace
            # the exact Create -> inventory chain after a job-save interruption.
            batch_raw = _read_record(create_path) if create_path.exists() else None
            batch = None
            if batch_raw is not None:
                try:
                    batch, batch_initial = validate_completed_batch(batch_raw)
                except ValueError as exc:
                    raise VendorBatchStopped(
                        "interrupted or invalid Create evidence; never replay"
                    ) from exc
                if (
                    any(batch[key] != record[key] for key in (
                        "process_id", "process_creation_filetime_utc", "window", "vendor_id",
                    ))
                    or _owner(batch_initial) != _owner(initial)
                    or _items(batch_initial) != _items(initial)
                ):
                    raise VendorBatchStopped("action evidence belongs to another vendor or client")
            if keep_path.exists():
                if batch_raw is None:
                    raise VendorBatchStopped(
                        "Keep evidence has no source Create journal; review required"
                    )
                try:
                    kept = validate_completed_keep(_read_record(keep_path), batch_raw)
                except ValueError as exc:
                    raise VendorBatchStopped(
                        "invalid or unfinished Keep evidence; never replay"
                    ) from exc
                record.update(
                    created=len(batch["items"]), capacity=batch["capacity"], phase="keeping",
                    kept=len(kept["kept"]), excluded=len(kept["excluded"]),
                )
                update("complete", "Batch finished; retained items are confirmed in inventory.")
                return record
            before_action()
            if stopped():
                update(
                    "stopped" if store.control(record["job_id"]) == "stop" else "paused",
                    "Stopped before the next crafting action.",
                )
                return record
            if batch is None:
                if record["phase"] != "filling":
                    raise VendorBatchStopped("missing Create evidence; review this job")
                batch = fill_available_slots(
                    guarded,
                    create_path,
                    record["vendor_id"],
                    cancelled=stopped,
                    before_action=before_action,
                    expected_owner=initial,
                )
                if batch["state"] != "complete":
                    raise VendorBatchStopped("interrupted Create batch requires review")
            record.update(created=len(batch["items"]), capacity=batch["capacity"], phase="waiting")
            store.save(record)
            if not batch["items"]:
                update("complete", "No free production slots. No new items were created.")
                return record
            while True:
                receipt = before_action()
                if stopped():
                    update(
                        "stopped" if store.control(record["job_id"]) == "stop" else "paused",
                        "Production remains saved. No new actions will be sent.",
                    )
                    return record
                s = receipt.snapshot
                if (
                    receipt.outcome != Outcome.OBSERVED
                    or receipt.window != window
                    or _owner(s) != _owner(initial)
                    or not receipt.flags & READY
                    or receipt.flags & (IN_FLIGHT | UNRESOLVED)
                    or len(s.slots) < record["capacity"]
                    or _items(s) != _items(initial) | set(batch["items"])
                ):
                    raise VendorBatchStopped(
                        "vendor ownership or production changed; review required"
                    )
                record["capacity"] = len(s.slots)
                if any(slot.state != 2 for slot in s.slots if slot.item in batch["items"]):
                    update("cooking", "Items are cooking. Waiting for the batch to finish.")
                elif not s.inventory:
                    update("inventory", "Opening this vendor's Inventory for the finished batch.")
                    menus = session.menu_session()
                    try:
                        menu_owner = menus.inspect()
                        if (
                            menu_owner.window != window
                            or menu_owner.snapshot.owner != _owner(initial)
                        ):
                            raise VendorBatchStopped("vendor changed before Inventory opening")
                        open_inventory(
                            menus, menu_path, menu_owner.snapshot,
                            before_action=before_action, cancelled=stopped,
                        )
                    finally:
                        menus.close()
                else:
                    break
                sleeper(0.5)
            record["phase"] = "keeping"
            store.save(record)
            capture = directory / "completion.jsonl"
            kept = keep_completed_batch(
                guarded,
                create_path,
                keep_path,
                capture=capture if capture.exists() else None,
                cancelled=stopped,
                before_action=before_action,
            )
            record.update(kept=len(kept["kept"]), excluded=len(kept["excluded"]))
            if kept["state"] != "complete":
                raise VendorBatchStopped("interrupted Keep batch requires review")
            update("complete", "Batch finished; retained items are confirmed in inventory.")
            return record
        except Exception as exc:
            update("review", str(exc)[:240] or "Vendor job needs review before further actions.")
            raise
