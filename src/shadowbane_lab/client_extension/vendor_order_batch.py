"""Durable, quota-bounded quantity orders; never replay an existing journal."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

from .movement_wire import request_bytes
from .vendor_automatic_replies import AutomaticReplies
from .vendor_batch import VendorBatchStopped, _items, _owner
from .vendor_budget import VendorBatchBudget
from .vendor_production_responses import VendorProductionReader
from .vendor_recipe import RandomOrderSpec, validate_recipe_preparation
from .vendor_wire import IN_FLIGHT, READY, UNRESOLVED, Command, Host, Outcome, Snapshot, Verb, uint


def _counts(values, state):
    return (type(values) in (list, tuple) and len(values) == len(state.slots)
            and all(type(value) is int and 0 <= value <= 255 for value in values))


def queue_quantity_orders(
    session, journal: Path, specification: RandomOrderSpec, budget: VendorBatchBudget,
    preparation_raw: bytes, production_reader, *, character, before_action=lambda: None,
    await_authority=None,
    cancelled=lambda: False, clock=time.monotonic, sleeper=time.sleep,
    acceptance_timeout: float = 15.0,
) -> dict:
    """Submit one full-capacity quantity request and verify every funded slot.

    The initial item ID represents one order, not all its future generated items.
    This finishes queue admission only; inventory completion is a separate phase.
    Rank growth cannot increase this batch's quota or cause another funding pass.
    """
    if (type(specification) is not RandomOrderSpec or not specification.multiple
            or type(budget) is not VendorBatchBudget or not 0 < acceptance_timeout <= 60):
        raise ValueError("a full-capacity order and immutable batch budget are required")
    if (production_reader.process_id, production_reader.creation) != (
        session.identity.process_id, session.identity.creation_filetime_utc,
    ):
        raise ValueError("production recorder belongs to another client lifetime")
    journal = Path(journal)
    with exclusive_record_lock(journal.with_suffix(journal.suffix + ".lock")):
        if journal.exists():
            raise VendorBatchStopped("quantity journal exists; never replay its requests")
        native_budget = budget.native_budget
        native_budget.encode(specification.quantity)
        first = session.inspect_orders()
        initial = first.snapshot
        if (first.outcome != Outcome.OBSERVED or first.flags != READY
                or not specification.matches(initial) or not budget.matches(initial)
                or not _counts(first.remaining_counts, initial)
                or any(slot.state == 1 for slot in initial.slots)):
            raise VendorBatchStopped("the exact funded quantity recipe is not ready")
        validate_recipe_preparation(
            preparation_raw, specification, initial, process_id=session.identity.process_id,
            process_creation_filetime_utc=session.identity.creation_filetime_utc,
            window=first.window,
        )
        bookmark = production_reader.bookmark()
        proof = AutomaticReplies(initial, specification, character, budget.free_slots,
                                 bookmark["cursor"]["sequence"])
        record = dict(schema_version=6, operation="queue_quantity_orders", state="running",
                      character=list(character),
                      batch_id=str(uuid.uuid4()), process_id=session.identity.process_id,
                      process_creation_filetime_utc=session.identity.creation_filetime_utc,
                      window=first.window, initial_snapshot=initial.encode().hex(),
                      initial_counts=list(first.remaining_counts),
                      recipe_spec=specification.as_dict(),
                      recipe_sha256=specification.canonical_digest,
                      batch_budget=budget.as_dict(), batch_budget_sha256=budget.canonical_digest,
                      preparation_journal_utf8=preparation_raw.decode("utf-8"),
                      preparation_sha256=hashlib.sha256(preparation_raw).hexdigest(),
                      planned_orders=budget.free_slots, planned_items=budget.total_items,
                      capacity=len(initial.slots), capacity_history=[len(initial.slots)],
                      requests=[], initial_items=[], production_cursor=bookmark["cursor"],
                      production_bookmark=bookmark, production_records=[])

        def save():
            publish_atomic_record(journal, (json.dumps(record, sort_keys=True, indent=2)
                                           + "\n").encode(), temporary_label="vendor-orders")

        def drain():
            result = production_reader.drain()
            record["production_cursor"] = result["cursor"]
            record["production_records"].extend(result["records"])
            save()
            if result["capture_incomplete"] or len(record["production_records"]) > 4096:
                raise VendorBatchStopped("production observation is incomplete; no retry sent")
            proof.receive(result["records"])

        def current(receipt, *, pending=False):
            state = receipt.snapshot
            state.encode()
            if (receipt.outcome != Outcome.OBSERVED or receipt.window != first.window
                    or _owner(state) != _owner(initial) or receipt.flags & UNRESOLVED
                    or len(state.slots) < record["capacity"]
                    or receipt.remaining_counts is None
                    or len(receipt.remaining_counts) != len(state.slots)
                    or any(type(count) is not int or not 0 <= count <= 255
                           for count in receipt.remaining_counts)
                    or not pending and (receipt.flags != READY
                                        or not specification.matches(state))):
                raise VendorBatchStopped("quantity order ownership or native authority changed")
            if len(state.slots) > record["capacity"]:
                record["capacity"] = len(state.slots)
                record["capacity_history"].append(len(state.slots))
                save()
            return state

        save()
        try:
            if await_authority is None:
                before_action()
            else:
                # Long focus/pause waits must keep the permanent ring drained
                # into this same journal, never a second observation owner.
                await_authority(drain)
            drain()
            if cancelled():
                record["state"] = "stopped"
                save()
                return record
            order_preparation = preparation_raw
            fresh_receipt = session.inspect_orders()
            fresh = current(fresh_receipt)
            if len(fresh.slots) != budget.capacity:
                raise VendorBatchStopped("capacity changed before batch submission; replan funding")
            validate_recipe_preparation(
                order_preparation, specification, fresh,
                process_id=session.identity.process_id,
                process_creation_filetime_utc=session.identity.creation_filetime_utc,
                window=first.window,
            )
            expected_items = _items(initial) | set(record["initial_items"])
            if _items(fresh) != expected_items:
                raise VendorBatchStopped("production changed during quantity-order filling")
            key = str(uuid.uuid4())
            attempt = dict(request_key=key, state="prepared",
                           expected_snapshot=fresh.encode().hex(),
                           expected_counts=list(fresh_receipt.remaining_counts),
                           preparation_journal_utf8=order_preparation.decode(),
                           preparation_sha256=hashlib.sha256(order_preparation).hexdigest())
            record["requests"].append(attempt)
            save()
            submitted = session.create_orders(fresh, key, batch_key=record["batch_id"],
                                               budget=native_budget)
            if (submitted.request_key != key or submitted.window != first.window
                    or submitted.outcome != Outcome.SUBMITTED or submitted.flags != IN_FLIGHT
                    or submitted.snapshot != fresh
                    or submitted.remaining_counts != fresh_receipt.remaining_counts):
                attempt["state"] = "uncertain"
                raise VendorBatchStopped("quantity Create submission was not confirmed")
            attempt["state"] = "submitted"
            save()
            deadline = clock() + acceptance_timeout
            while True:
                drain()
                observed = session.inspect_orders()
                drain()  # Include callbacks processed by this independent native view.
                record["last_observation"] = dict(
                    outcome=observed.outcome.name, flags=observed.flags,
                    snapshot=observed.snapshot.encode().hex(),
                    counts=(list(observed.remaining_counts)
                            if observed.remaining_counts is not None else None),
                    transition_request=observed.transition_request,
                    transition_item=observed.transition_item,
                )
                save()
                state = current(observed, pending=True)
                additions = _items(state) - expected_items
                if (not expected_items <= _items(state) or len(additions) > budget.free_slots
                        or state.revision < fresh.revision):
                    raise VendorBatchStopped("ambiguous quantity-order arrival")
                if observed.transition_request == key:
                    if (observed.flags & (IN_FLIGHT | UNRESOLVED)
                            or len(additions) != budget.free_slots
                            or observed.transition_item not in additions
                            or not proof.admits(sorted(additions))):
                        raise VendorBatchStopped("native order admission lacks qualified replies")
                    attempt.update(state="observed", item_ids=sorted(additions),
                                   observed_snapshot=state.encode().hex(),
                                   observed_counts=list(observed.remaining_counts),
                                   transition_request=observed.transition_request)
                    record["initial_items"].extend(sorted(additions))
                    save()
                    break
                if not observed.flags & IN_FLIGHT or clock() >= deadline:
                    raise VendorBatchStopped("quantity Create is unconfirmed; never replay")
                sleeper(0.1)
            drain()
            record["state"] = "queued"
            save()
            return record
        except BaseException as exc:
            record.update(state="review", detail=str(exc) or type(exc).__name__)
            save()
            raise


def validate_queued_orders(raw: bytes) -> tuple[dict, Snapshot]:
    """Validate historical admission without submitting or adopting any request."""
    if type(raw) is not bytes or len(raw) > 4 * 1024 * 1024:
        raise ValueError("quantity admission evidence exceeds its bound")
    try:
        record = json.loads(raw)
        spec = RandomOrderSpec.from_dict(record["recipe_spec"])
        budget = VendorBatchBudget.from_dict(record["batch_budget"])
        initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
        prep = record["preparation_journal_utf8"].encode()
        request_bytes(record["batch_id"])
        for name, bits in (("process_id", 32), ("process_creation_filetime_utc", 64),
                           ("window", 32)):
            if not uint(record[name], bits, name):
                raise ValueError("invalid quantity batch client identity")
        for name in ("planned_orders", "planned_items", "capacity"):
            if type(record[name]) is not int:
                raise ValueError("invalid quantity batch bounds")
        if (type(record["capacity_history"]) is not list
                or any(type(v) is not int or not len(initial.slots) <= v <= 16
                       for v in record["capacity_history"])):
            raise ValueError("invalid capacity history")
        bookmark = record["production_bookmark"]
        for cursor in (bookmark["cursor"], record["production_cursor"]):
            VendorProductionReader(record["process_id"],
                                   record["process_creation_filetime_utc"], None,
                                   resume_cursor=cursor)
            if cursor["capture_incomplete"] or cursor["read_errors"]:
                raise ValueError("production observation was incomplete")
        if (bookmark["command_admitted"] is not False
                or record["production_cursor"]["sequence"] < bookmark["cursor"]["sequence"]
                or any(record["production_cursor"][key] != bookmark["cursor"][key]
                       for key in ("rejected", "ticket_drops"))
                or not _counts(record["initial_counts"], initial)
                or any(slot.state == 1 for slot in initial.slots)):
            raise ValueError("invalid initial production observation")
        validate_recipe_preparation(
            prep, spec, initial, process_id=record["process_id"],
            process_creation_filetime_utc=record["process_creation_filetime_utc"],
            window=record["window"],
        )
        if (type(record["schema_version"]) is not int or record["schema_version"] != 6
                or record["operation"] != "queue_quantity_orders" or record["state"] != "queued"
                or not spec.multiple or not spec.matches(initial) or not budget.matches(initial)
                or record["recipe_sha256"] != spec.canonical_digest
                or record["batch_budget_sha256"] != budget.canonical_digest
                or record["preparation_sha256"] != hashlib.sha256(prep).hexdigest()
                or record["planned_orders"] != budget.free_slots
                or record["planned_items"] != budget.total_items
                or len(record["requests"]) != 1
                or len(record["initial_items"]) != budget.free_slots
                or not len(initial.slots) <= record["capacity"] <= 16
                or record["capacity_history"] != sorted(set(record["capacity_history"]))
                or record["capacity_history"][0] != len(initial.slots)
                or record["capacity_history"][-1] != record["capacity"]):
            raise ValueError("inconsistent quantity batch admission")
        seen, keys, previous = _items(initial), set(), initial
        for request in record["requests"]:
            items = request["item_ids"]
            key = request["request_key"]
            request_bytes(key)
            before = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            after = Snapshot.decode(bytes.fromhex(request["observed_snapshot"]))
            counts = request["observed_counts"]
            order_prep = request["preparation_journal_utf8"].encode()
            validate_recipe_preparation(
                order_prep, spec, before, process_id=record["process_id"],
                process_creation_filetime_utc=record["process_creation_filetime_utc"],
                window=record["window"],
            )
            Command(Host(1, 1, 1), record["window"], key, before, batch_key=record["batch_id"],
                    order_budget=budget.native_budget).encode(Verb.CREATE_ORDERS)
            if (key in keys or request["state"] != "observed"
                    or request["transition_request"] != key
                    or type(items) is not list or items != record["initial_items"]
                    or len(set(items)) != budget.free_slots or items != sorted(items)
                    or any(type(item) is not int or not 0 < item < 2**32 for item in items)
                    or _owner(before) != _owner(initial) or _owner(after) != _owner(initial)
                    or not spec.matches(before)
                    or request["preparation_sha256"] != hashlib.sha256(order_prep).hexdigest()
                    or not len(previous.slots) <= len(before.slots) <= len(after.slots)
                    <= record["capacity"]
                    or not previous.revision <= before.revision <= after.revision
                    or len(before.slots) != budget.capacity
                    or _items(before) != seen or _items(after) != seen | set(items)
                    or seen & set(items)
                    or not _counts(request["expected_counts"], before)
                    or not _counts(counts, after)):
                raise ValueError("unconfirmed quantity order transition")
            keys.add(key)
            seen.update(items)
            previous = after
        proof = AutomaticReplies(initial, spec, tuple(record["character"]), budget.free_slots,
                                 bookmark["cursor"]["sequence"])
        proof.receive(record["production_records"])
        if (proof.sequence != record["production_cursor"]["sequence"]
                or not proof.admits(record["initial_items"])):
            raise ValueError("quantity admission lacks complete server arrival evidence")
        return record, initial
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, VendorBatchStopped) as exc:
        raise ValueError("expected a complete observed quantity-order admission journal") from exc
