"""Durable, bounded vendor jobs owned by the manager's exact client worker.

One job fills currently available capacity once, then finalizes eligible items.
Only native inventory receipts count as kept. Uncertain submissions require
review; a restart never replays a Create or Keep journal.
"""

from __future__ import annotations

import hashlib
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
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_completion import (
    _read_record,
    keep_completed_batch,
    validate_completed_batch,
    validate_completed_keep,
)
from shadowbane_lab.client_extension.vendor_menu import (
    open_inventory,
    prepare_recipe,
    validate_completed_menu,
)
from shadowbane_lab.client_extension.vendor_recipe import RandomOrderSpec, RandomRecipeSpec
from shadowbane_lab.client_extension.vendor_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Outcome,
    Receipt,
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
            record.get("schema_version") not in (1, 2, 3, 4, 5)
            or record.get("job_id") != job_id
            or tuple(record.get("identity", ())) != self.identity
            or record.get("phase") not in {
                "preparing", "filling", "waiting", "keeping", "recycling"}
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
        if record["phase"] == "recycling" and record["schema_version"] != 5:
            raise ValueError("historical job cannot adopt recycling")
        if record["schema_version"] in (2, 3, 4, 5):
            spec = RandomRecipeSpec.from_dict(record["recipe_spec"])
            if (record.get("recipe_sha256") != spec.canonical_digest
                    or not _JOB.fullmatch(record.get("recipe_revision", ""))):
                raise ValueError("saved recipe job specification changed")
        if record["schema_version"] in (3, 4, 5) or "batch_budget" in record:
            budget = VendorBatchBudget.from_dict(record["batch_budget"])
            initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
            if (budget.canonical_digest != record.get("batch_budget_sha256")
                    or not budget.matches(initial)):
                raise ValueError("funded vendor batch budget changed")
        if record["schema_version"] in (4, 5):
            order = RandomOrderSpec.from_dict(record["order_spec"])
            if (order.recipe != spec or not order.matches(initial)
                    or record["order_sha256"] != order.canonical_digest
                    or type(record["planned_items"]) is not int
                    or record["planned_items"] != budget.total_items
                    or type(record["queued_orders"]) is not int
                    or not 0 <= record["queued_orders"] <= budget.free_slots
                    or any(type(record[key]) is not int for key in ("created", "kept", "excluded"))
                    or not 0 <= record["kept"] <= record["created"] <= budget.total_items
                    or not 0 <= record["excluded"] <= record["kept"]
                    or record["schema_version"] == 4 and record["excluded"] != 0):
                raise ValueError("quantity job order intent changed")
            if record["schema_version"] == 5:
                from .vendor_recycling import POLICY
                if record.get("exclusion_policy") != POLICY:
                    raise ValueError("quantity job exclusion policy changed")
            if "server_finished" in record or "shortfall" in record:
                finished = record.get("server_finished")
                shortfall = record.get("shortfall")
                if (type(finished) is not bool
                        or finished and (type(shortfall) is not int
                                         or shortfall != budget.total_items - record["created"])
                        or not finished and shortfall is not None):
                    raise ValueError("quantity server outcome changed")
        return record

    def save(self, record: dict) -> None:
        _write(self.directory(record["job_id"]) / "job.json", record)

    def begin(self, session, window: int, now: float, *, selection=None,
              enable_exclusions=False) -> dict:
        previous = self.current()
        if previous and previous["state"] not in {"complete", "stopped"}:
            raise VendorBatchStopped("resume or review the existing vendor job first")
        spec = RandomRecipeSpec.from_dict(selection["recipe_spec"]) if selection else None
        order = (RandomOrderSpec.from_dict(selection["order_spec"])
                 if selection and "order_spec" in selection else None)
        if order and (order.recipe != spec or not order.multiple
                      or selection.get("order_sha256") != order.canonical_digest):
            raise ValueError("quantity job requires exact saved recipe order intent")
        first = (session.inspect_orders() if order else session.inspect_random()
                 if spec else session.inspect())
        budget = None
        if selection and "batch_budget" in selection:
            budget = VendorBatchBudget.from_dict(selection["batch_budget"])
            if (budget.canonical_digest != selection.get("batch_budget_sha256")
                    or not budget.matches(first.snapshot)):
                raise VendorBatchStopped("vendor capacity or recipe changed after funding")
        if (
            first.outcome != Outcome.OBSERVED
            or first.window != window
            or first.flags & (IN_FLIGHT | UNRESOLVED)
            or (not spec and not first.snapshot.random_scepter)
            or (spec and (first.snapshot.building != selection["building"]["object_id"]
                          or first.snapshot.vendor != selection["vendor"]["object_id"]
                          or _owner(first.snapshot) != _owner(Snapshot.decode(
                              bytes.fromhex(selection["admission_snapshot"])))))
        ):
            raise VendorBatchStopped("the saved vendor or random recipe is not ready")
        if order and (budget is None or not order.matches(first.snapshot)
                      or first.remaining_counts is None
                      or any(slot.item and count > 1 for slot, count in
                             zip(first.snapshot.slots, first.remaining_counts, strict=True))):
            raise VendorBatchStopped("funded quantity order support is not ready")
        if order and enable_exclusions:
            supported = session.inspect_recycle()
            if (supported.outcome != Outcome.OBSERVED or supported.window != window
                    or supported.flags & (IN_FLIGHT | UNRESOLVED)
                    or supported.recycle_completion is None
                    or _owner(supported.snapshot) != _owner(first.snapshot)):
                raise VendorBatchStopped("native batch recycling support is not ready")
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
            "schema_version": 5 if order and enable_exclusions else (
                4 if order else 3 if budget else (2 if spec else 1)),
            "job_id": uuid.uuid4().hex,
            "identity": self.identity,
            "state": "running",
            "phase": "preparing" if spec else "filling",
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
            "deadline_at": now + (2 * MAX_JOB_SECONDS if order else MAX_JOB_SECONDS),
            "detail": "Filling available production slots.",
        }
        if spec:
            record.update(recipe_spec=spec.as_dict(), recipe_sha256=spec.canonical_digest,
                          recipe_revision=selection["revision"], recipe_owner=selection["owner"],
                          recipe_label=selection["display_name"])
        if budget:
            record.update(batch_budget=budget.as_dict(),
                          batch_budget_sha256=budget.canonical_digest)
        if order:
            record.update(order_spec=order.as_dict(), order_sha256=order.canonical_digest,
                          planned_items=budget.total_items, queued_orders=0)
            if enable_exclusions:
                from .vendor_recycling import POLICY
                record["exclusion_policy"] = POLICY
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
            if current["state"] == "review" and current["schema_version"] == 4 and mode == "run":
                from .vendor_review_recovery import review_job_ready

                review_job_ready(self, current)
            elif current["state"] in TERMINAL:
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
        if record["schema_version"] in (4, 5):
            result.update(planned_items=record["planned_items"],
                          queued_orders=record["queued_orders"])
            if "server_finished" in record:
                result.update(server_finished=record["server_finished"],
                              shortfall=record["shortfall"])
            if record["schema_version"] == 5:
                result.update(collected=record["kept"], kept=record["kept"] - record["excluded"],
                              exclusion_policy=record["exclusion_policy"])
            if record["state"] == "review":
                from .vendor_review_recovery import review_job_ready

                result["can_reconcile"] = False
                try:
                    review_job_ready(self, record)
                    result["can_reconcile"] = True
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, IndexError):
                    pass
        return result


def require_vendor_handoff_idle(store, session, record):
    """Prove current local receipt and every retained job action before handback."""
    from .vendor_collection import require_collections_idle

    require_collections_idle(store)
    from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        record = store.read(record["job_id"])
        if (record["process_id"] != session.identity.process_id
                or record["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
                or record["window"] != session.window):
            raise VendorBatchStopped("vendor handback belongs to another client")
        initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
        if record["schema_version"] in (4, 5):
            from .vendor_order_job import require_order_handoff_idle

            require_order_handoff_idle(store, session, record)
            if record["schema_version"] == 5:
                from .vendor_recycling import require_recycling_idle
                require_recycling_idle(store, session, record)
            GuardSpendingJournal(store.root).assert_idle()
            CondemnProgressStore(store.root).assert_idle()
            return
        receipt = session.inspect()
        if (not isinstance(receipt, Receipt) or receipt.outcome is not Outcome.OBSERVED
                or receipt.window != record["window"]
                or receipt.flags & (IN_FLIGHT | UNRESOLVED)
                or _owner(receipt.snapshot) != _owner(initial)):
            raise VendorBatchStopped("vendor handback remains unresolved")
        directory = store.directory(record["job_id"])
        batch_path = directory / "create.json"
        batch_raw = _read_record(batch_path) if batch_path.exists() else None
        if batch_raw is not None:
            batch, before = validate_completed_batch(batch_raw)
            if (any(batch[key] != record[key] for key in (
                    "process_id", "process_creation_filetime_utc", "window", "vendor_id"))
                    or _owner(before) != _owner(initial)):
                raise VendorBatchStopped("vendor Create evidence changed owner")
        elif record["created"]:
            raise VendorBatchStopped("vendor Create evidence is missing")
        keep_path = directory / "keep.json"
        if keep_path.exists():
            if batch_raw is None:
                raise VendorBatchStopped("vendor Keep evidence lacks its Create journal")
            validate_completed_keep(_read_record(keep_path), batch_raw)
        elif record["kept"] or record["excluded"]:
            raise VendorBatchStopped("vendor Keep evidence is missing")
        for name in ("inventory-menu.json", "recipe-preparation.json"):
            path = directory / name
            if path.exists():
                menu, before, _ = validate_completed_menu(_read_record(path, 256 * 1024))
                if (any(menu[key] != record[key] for key in (
                        "process_id", "process_creation_filetime_utc", "window"))
                        or before.owner != _owner(initial)):
                    raise VendorBatchStopped("vendor menu evidence changed owner")
        GuardSpendingJournal(store.root).assert_idle()
        CondemnProgressStore(store.root).assert_idle()


def run_vendor_job(
    store: VendorJobStore,
    session,
    window: int,
    *,
    resume: bool = False,
    selection=None,
    enable_exclusions=False,
    exclusion_reader=None,
    cancelled=lambda: False,
    clock=time.time,
    sleeper=time.sleep,
) -> dict:
    """Run one capacity batch, pausing only before new native mutations.

    A local pause lets an already-submitted request finish reconciliation. A
    lost manager permit or Stop interrupts immediately and never retries it.
    Recovery is explicit and permitted only at a fully durable phase boundary.
    """
    from .vendor_collection import require_collections_idle

    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        require_collections_idle(store)
        CondemnProgressStore(store.root).assert_idle()
        if cancelled():
            raise VendorBatchStopped("worker dispatch is paused")
        record = (store.current() if resume
                  else store.begin(session, window, clock(), selection=selection,
                                   enable_exclusions=enable_exclusions))
        if resume and record and record["state"] == "review" and record["schema_version"] == 4:
            from .vendor_review_recovery import resume_review

            resume_review(store, session, record)
        if record is None or record["state"] in TERMINAL:
            raise VendorBatchStopped("no resumable vendor job")
        if (
            record["process_id"] != session.identity.process_id
            or record["process_creation_filetime_utc"] != session.identity.creation_filetime_utc
            or record["window"] != window
        ):
            raise VendorBatchStopped("vendor job belongs to another client lifetime")
        if record["schema_version"] in (4, 5):
            from .vendor_order_job import run_order_job

            return run_order_job(store, session, record, cancelled=cancelled,
                                 clock=clock, sleeper=sleeper,
                                 **({"exclusion_reader": exclusion_reader}
                                    if exclusion_reader is not None else {}))
        directory = store.directory(record["job_id"])
        initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
        create_path, keep_path = directory / "create.json", directory / "keep.json"
        menu_path = directory / "inventory-menu.json"
        preparation_path = directory / "recipe-preparation.json"
        spec = (RandomRecipeSpec.from_dict(record["recipe_spec"])
                if record["schema_version"] in (2, 3) else None)
        preparation_raw = None

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

            def inspect_random(self):
                # begin() proved native feature support before any job mutation.
                return self.inspect()

            def create_random(self, expected, key):
                before_action()
                if stopped():
                    raise VendorBatchStopped("dispatch revoked before random Create")
                result = session.create_random(expected, key)
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
            if spec:
                support = session.inspect_random()
                if (support.outcome != Outcome.OBSERVED or support.window != window
                        or support.flags & (IN_FLIGHT | UNRESOLVED)
                        or _owner(support.snapshot) != _owner(initial)):
                    raise VendorBatchStopped("generalized crafting support or ownership changed")
            if spec and preparation_path.exists():
                preparation_raw = _read_record(preparation_path, 256 * 1024)
                preparation, _, prepared = validate_completed_menu(preparation_raw)
                if (preparation["operation"] != "prepare_recipe"
                        or any(preparation[key] != record[key] for key in (
                            "process_id", "process_creation_filetime_utc", "window"))
                        or prepared.owner != _owner(initial)
                        or not spec.matches(prepared)):
                    raise VendorBatchStopped("saved recipe preparation does not belong to this job")
            elif spec and record["phase"] != "preparing":
                raise VendorBatchStopped("saved recipe preparation evidence is missing")
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
                    or (spec and (batch.get("schema_version") != 3
                                  or batch.get("recipe_spec") != spec.as_dict()
                                  or batch.get("preparation_sha256") != hashlib.sha256(
                                      preparation_raw).hexdigest()))
                    or (not spec and batch.get("schema_version") == 3)
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
            if spec and batch is None and preparation_raw is None:
                fresh = before_action()
                if fresh is None:
                    update("paused", "Stopped before recipe preparation.")
                    return record
                if _items(fresh.snapshot) != _items(initial):
                    raise VendorBatchStopped("production changed before recipe preparation")
                if not fresh.snapshot.free_slots:
                    record["capacity"] = len(fresh.snapshot.slots)
                    update("complete", "No free production slots. No new items were created.")
                    return record
            if spec and preparation_raw is None:
                menus = session.menu_session()
                try:
                    observed = menus.inspect()
                    if observed.snapshot.owner != _owner(initial):
                        raise VendorBatchStopped("vendor changed before recipe preparation")
                    prepare_recipe(menus, preparation_path, observed.snapshot, spec.template,
                                   table=spec.table, before_action=before_action, cancelled=stopped)
                    preparation_raw = _read_record(preparation_path, 256 * 1024)
                finally:
                    menus.close()
            if spec and record["phase"] == "preparing":
                fresh = guarded.inspect_random().snapshot
                if not spec.matches(fresh) or _items(fresh) != _items(initial):
                    raise VendorBatchStopped("recipe or production changed during preparation")
                record["phase"] = "filling"
                store.save(record)
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
                    **({"recipe": spec, "preparation_raw": preparation_raw} if spec else {}),
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
