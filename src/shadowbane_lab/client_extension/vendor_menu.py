"""Durable, non-spending recipe preparation and Inventory menu transitions.

Each invocation owns a new journal. Existing journals, including interrupted
menu requests, are evidence only and are never replayed. An open Inventory is
cached UI evidence, not a claim of complete or newly fetched server inventory.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record

from .action_channel import NativeClientProcessIdentity
from .movement_wire import Host, request_bytes
from .vendor_batch import VendorBatchStopped
from .vendor_menu_wire import (
    IN_FLIGHT,
    RANDOM_SENTINEL,
    READY,
    RESPONSE_WAIT_SECONDS,
    UNRESOLVED,
    Command,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
    uint,
)


class MenuSession(Protocol):
    identity: NativeClientProcessIdentity
    def inspect(self) -> Receipt: ...
    def open_recipe(self, expected: Snapshot, request_key: str) -> Receipt: ...
    def select_recipe(self, expected: Snapshot, template: int, request_key: str) -> Receipt: ...
    def random_mode(self, expected: Snapshot, request_key: str) -> Receipt: ...
    def close_recipe(self, expected: Snapshot, request_key: str) -> Receipt: ...
    def open_inventory(self, expected: Snapshot, request_key: str) -> Receipt: ...
    def close_inventory(self, expected: Snapshot, request_key: str) -> Receipt: ...


def _run(
    session: MenuSession, journal: Path, expected_owner: Snapshot, *,
    operation: str, template: int = 0, table: int | None = None,
    before_action: Callable[[], None], cancelled: Callable[[], bool],
    clock: Callable[[], float], sleeper: Callable[[float], None],
) -> dict:
    expected_owner.encode()
    if expected_owner.empty:
        raise ValueError("an exact observed vendor owner is required")
    journal = Path(journal)
    with exclusive_record_lock(journal.with_suffix(journal.suffix + ".lock")):
        if journal.exists():
            raise VendorBatchStopped("menu journal exists; never replay its requests")
        first = session.inspect()
        record = dict(
            schema_version=1, operation=operation, state="running",
            operation_id=str(uuid.uuid4()), window=first.window,
            process_id=session.identity.process_id,
            process_creation_filetime_utc=session.identity.creation_filetime_utc,
            initial_snapshot=first.snapshot.encode().hex(),
            expected_owner=expected_owner.encode().hex(),
            requested_recipe=(dict(template=dict(object_id=template, object_type=0),
                                   mode=1, table=table, sentinel=3362971591,
                                   prefix=3362971591, suffix=3362971591,
                                   quantity=1, multiple=False) if template else None),
            requests=[],
        )

        def save():
            publish_atomic_record(
                journal, (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8"),
                temporary_label="vendor-menu",
            )

        def current(receipt, *, pending=False):
            state = receipt.snapshot
            state.encode()
            if (receipt.outcome != Outcome.OBSERVED or receipt.window != first.window
                    or state.owner != expected_owner.owner or receipt.flags & UNRESOLVED
                    or (not pending and (not receipt.flags & READY
                                         or receipt.flags & IN_FLIGHT))):
                raise VendorBatchStopped("vendor menu ownership or authority changed")
            return state

        last_observation = first.snapshot

        def perform(verb, done):
            nonlocal last_observation
            before_action()
            if cancelled():
                raise VendorBatchStopped("vendor menu operation cancelled before dispatch")
            observed = current(session.inspect())
            if not _continuous(last_observation, observed):
                raise VendorBatchStopped("vendor menu changed outside this operation")
            last_observation = observed
            if done(observed):
                return observed
            request_key = str(uuid.uuid4())
            request = dict(request_key=request_key, verb=verb.name.lower(), state="prepared",
                           expected_snapshot=observed.encode().hex(),
                           template=template if verb == Verb.SELECT_RECIPE else 0)
            record["requests"].append(request)
            save()
            method = getattr(session, verb.name.lower())
            response = (method(observed, template, request_key) if verb == Verb.SELECT_RECIPE
                        else method(observed, request_key))
            if (response.request_key != request_key or response.window != first.window
                    or response.outcome != Outcome.SUBMITTED or response.flags != IN_FLIGHT
                    or response.snapshot != observed):
                raise VendorBatchStopped("vendor menu submission was not confirmed")
            request["state"] = "submitted"
            save()
            deadline = clock() + RESPONSE_WAIT_SECONDS
            # Reconcile a sent action even if cancellation or focus changed. It
            # must not become a new submission following a lost acknowledgement.
            while True:
                receipt = session.inspect()
                state = current(receipt, pending=True)
                if (verb in (Verb.SELECT_RECIPE, Verb.RANDOM_MODE)
                        and (state.recipe != observed.recipe
                             or state.recipe_list != observed.recipe_list)):
                    raise VendorBatchStopped("recipe window or list changed during menu transition")
                if (receipt.transition_request == request_key and receipt.flags & READY
                        and not receipt.flags & IN_FLIGHT):
                    if not done(state):
                        raise VendorBatchStopped("correlated menu result contradicts the request")
                    request.update(state="observed", observed_snapshot=state.encode().hex(),
                                   transition_request=receipt.transition_request)
                    save()
                    last_observation = state
                    return state
                if clock() >= deadline:
                    raise VendorBatchStopped("menu transition uncertain; never replay")
                sleeper(0.05)

        def recipe_closed(s):
            return not s.recipe and s.front_hud == s.menu

        def inventory_closed(s):
            return not s.inventory and s.front_hud == s.menu

        save()
        try:
            state = current(first)
            if operation in ("prepare_recipe", "open_recipe_catalog"):
                if state.inventory:
                    state = perform(Verb.CLOSE_INVENTORY, inventory_closed)
                if state.recipe and state.multiple:
                    state = perform(Verb.CLOSE_RECIPE, recipe_closed)
                state = perform(Verb.OPEN_RECIPE,
                                lambda s: bool(s.recipe and s.front_hud == s.recipe
                                               and not s.multiple))
                if operation == "prepare_recipe":
                    state = perform(Verb.SELECT_RECIPE, lambda s: s.selected(template))
                    state = perform(Verb.RANDOM_MODE, lambda s: s.random_recipe(template))
                    if not state.random_recipe(template, table):
                        raise VendorBatchStopped(
                            "observed recipe does not match the requested table")
            else:
                if state.recipe:
                    state = perform(Verb.CLOSE_RECIPE, recipe_closed)
                state = perform(Verb.OPEN_INVENTORY,
                                lambda s: bool(s.inventory and s.front_hud == s.inventory))
            record.update(state="complete", final_snapshot=state.encode().hex())
            save()
            return record
        except Exception as exc:
            record.update(state="review", detail=str(exc))
            save()
            raise


def prepare_recipe(
    session: MenuSession, journal: Path, expected_owner: Snapshot, template: int, *,
    table: int | None = None,
    before_action: Callable[[], None] = lambda: None,
    cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Select a typed-zero template and verify random single-item menu state.

    This does not admit Create; spending retains its separate recipe checks.
    The optional table pins a saved expectation instead of adopting a new one.
    """
    if not uint(template, 32, "template"):
        raise ValueError("a nonzero template is required")
    if table is not None and not uint(table, 32, "table"):
        raise ValueError("a nonzero expected table is required")
    return _run(session, journal, expected_owner, operation="prepare_recipe", template=template,
                table=table, before_action=before_action, cancelled=cancelled,
                clock=clock, sleeper=sleeper)


def open_recipe_catalog(
    session: MenuSession, journal: Path, expected_owner: Snapshot, *,
    before_action: Callable[[], None] = lambda: None,
    cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Open the owned single recipe list without selecting or crafting an item."""
    return _run(session, journal, expected_owner, operation="open_recipe_catalog",
                before_action=before_action, cancelled=cancelled, clock=clock, sleeper=sleeper)


def open_inventory(
    session: MenuSession, journal: Path, expected_owner: Snapshot, *,
    before_action: Callable[[], None] = lambda: None,
    cancelled: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Close the recipe if necessary and observe this vendor's Inventory in front."""
    return _run(session, journal, expected_owner, operation="open_inventory",
                before_action=before_action, cancelled=cancelled, clock=clock, sleeper=sleeper)


def _continuous(before: Snapshot, after: Snapshot) -> bool:
    return (before.revision <= after.revision
            and replace(before, revision=0) == replace(after, revision=0))


def validate_completed_menu(raw: bytes) -> tuple[dict, Snapshot, Snapshot]:
    """Validate bounded historical menu evidence without adopting or replaying it."""
    if not isinstance(raw, bytes) or len(raw) > 256 * 1024:
        raise ValueError("vendor menu journal exceeds its bound")
    try:
        record = json.loads(raw)
        if (type(record["schema_version"]) is not int or record["schema_version"] != 1
                or record["operation"] not in (
                    "prepare_recipe", "open_inventory", "open_recipe_catalog")
                or record["state"] != "complete"):
            raise ValueError("invalid completed menu operation")
        request_bytes(record["operation_id"])
        for key, bits in (("process_id", 32), ("process_creation_filetime_utc", 64),
                          ("window", 32)):
            if not uint(record[key], bits, key):
                raise ValueError("missing menu client identity")
        initial = Snapshot.decode(bytes.fromhex(record["initial_snapshot"]))
        expected_owner = Snapshot.decode(bytes.fromhex(record["expected_owner"]))
        final = Snapshot.decode(bytes.fromhex(record["final_snapshot"]))
        if (initial.empty or initial.owner != expected_owner.owner
                or final.owner != initial.owner):
            raise ValueError("menu owner changed")
        preparation = record["operation"] == "prepare_recipe"
        requested = record["requested_recipe"]
        template, table = 0, None
        if preparation:
            template = requested["template"]["object_id"]
            table = requested["table"]
            if not uint(template, 32, "template"):
                raise ValueError("missing recipe template")
            if table is not None and not uint(table, 32, "table"):
                raise ValueError("missing recipe table")
            canonical = dict(template=dict(object_id=template, object_type=0), mode=1,
                             table=table, sentinel=RANDOM_SENTINEL, prefix=RANDOM_SENTINEL,
                             suffix=RANDOM_SENTINEL, quantity=1, multiple=False)
            # JSON boolean/int equality must not admit changed typed expectations.
            if json.dumps(requested, sort_keys=True) != json.dumps(canonical, sort_keys=True):
                raise ValueError("invalid requested recipe identity")
            if not final.random_recipe(template, table):
                raise ValueError("final recipe does not match the saved expectation")
        elif record["operation"] == "open_recipe_catalog":
            if (requested is not None or not final.recipe or final.multiple
                    or final.front_hud != final.recipe):
                raise ValueError("final single recipe catalog was not observed")
        elif requested is not None or not final.inventory or final.front_hud != final.inventory:
            raise ValueError("final Inventory was not observed")
        requests = record["requests"]
        order = ([Verb.CLOSE_INVENTORY, Verb.CLOSE_RECIPE, Verb.OPEN_RECIPE,
                  Verb.SELECT_RECIPE, Verb.RANDOM_MODE] if preparation
                 else [Verb.CLOSE_INVENTORY, Verb.CLOSE_RECIPE, Verb.OPEN_RECIPE]
                 if record["operation"] == "open_recipe_catalog"
                 else [Verb.CLOSE_RECIPE, Verb.OPEN_INVENTORY])
        if not isinstance(requests, list) or len(requests) > len(order):
            raise ValueError("invalid menu request count")
        seen, last = set(), -1
        previous = initial
        for request in requests:
            if request["state"] != "observed":
                raise ValueError("unfinished menu request")
            key = str(uuid.UUID(bytes=request_bytes(request["request_key"])))
            if key in seen or request["transition_request"] != request["request_key"]:
                raise ValueError("unrelated or duplicate menu transition")
            seen.add(key)
            verb = Verb[request["verb"].upper()]
            if verb not in order or order.index(verb) <= last:
                raise ValueError("invalid menu transition order")
            last = order.index(verb)
            before = Snapshot.decode(bytes.fromhex(request["expected_snapshot"]))
            after = Snapshot.decode(bytes.fromhex(request["observed_snapshot"]))
            if (before.owner != initial.owner or after.owner != initial.owner
                    or not _continuous(previous, before) or after.revision < before.revision):
                raise ValueError("menu transition changed owner or lost preceding evidence")
            expected_template = template if verb == Verb.SELECT_RECIPE else 0
            if (type(request["template"]) is not int
                    or request["template"] != expected_template):
                raise ValueError("menu transition changed requested template")
            Command(Host(1, 1, 1), record["window"], key, before,
                    expected_template).encode(verb)
            reached = {
                Verb.CLOSE_INVENTORY: not after.inventory and after.front_hud == after.menu,
                Verb.CLOSE_RECIPE: not after.recipe and after.front_hud == after.menu,
                Verb.OPEN_RECIPE: bool(after.recipe and after.front_hud == after.recipe
                                       and not after.multiple),
                Verb.SELECT_RECIPE: after.selected(template),
                Verb.RANDOM_MODE: after.random_recipe(before.item_template),
                Verb.OPEN_INVENTORY: bool(after.inventory and after.front_hud == after.inventory),
            }
            if (not reached[verb] or (verb in (Verb.SELECT_RECIPE, Verb.RANDOM_MODE)
                    and (after.recipe != before.recipe
                         or after.recipe_list != before.recipe_list))):
                raise ValueError("menu transition did not reach its requested result")
            previous = after
        if not _continuous(previous, final):
            raise ValueError("final menu lacks preceding transition evidence")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("expected a complete, correlated vendor menu journal") from exc
    return record, initial, final
