"""Worker-owned warehouse funding before a new saved-recipe capacity batch.

Only exact two-sided transfer receipts advance the cycle. Interrupted intents
stay in the shared spending journal; neither funding nor crafting is replayed.
"""

from __future__ import annotations

import json
import re
import time
import uuid

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.guard_funding_session import NativeGuardFundingSession
from shadowbane_lab.client_extension.guard_funding_wire import Direction
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_menu import close_recipe, prepare_recipe
from shadowbane_lab.client_extension.vendor_navigation_session import NativeVendorNavigationSession
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Outcome,
)
from shadowbane_lab.client_extension.vendor_recipe import RandomRecipeSpec
from shadowbane_lab.client_observation.native_vendor_cost import read_native_vendor_cost
from shadowbane_lab.record_store import exclusive_record_lock

from .vendor_discovery import _memory
from .vendor_job import _write


def read_cost(binding):
    memory = _memory(binding)
    try:
        return read_native_vendor_cost(memory)
    finally:
        memory.close()


def warehouse_target(store, binding, scene, root):
    """Choose only one freshly navigable Seneschal from verified local discovery."""
    paths = sorted(
        (store.root / "navigation").glob("operation-*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not paths:
        raise VendorBatchStopped("Discover nearby vendors before warehouse funding.")
    record = json.loads(_read_record(paths[0], 2 * 1024 * 1024))
    if (
        record.get("schema_version") != 1
        or record.get("state") != "complete"
        or record.get("identity") != list(store.identity)
        or (record.get("game_process_id"), record.get("game_creation_filetime"))
        != (binding.game_process_id, binding.game_process_started_at_100ns)
        or (record.get("scene"), record.get("root")) != (scene, root)
    ):
        raise VendorBatchStopped("Warehouse discovery belongs to another scene or client.")
    candidates = []
    for building in record["roster"]:
        if building["state"] != "verified" or building["building"]["object_type"] != 8:
            continue
        for vendor in building["vendors"]:
            if (
                vendor.get("window_verified") is True
                and vendor.get("state") == "verified"
                and vendor.get("service_label") == "Seneschal"
                and vendor["vendor"]["object_type"] == 42
            ):
                candidates.append(
                    (building["building"]["object_id"], vendor["vendor"]["object_id"])
                )
    if len(candidates) != 1 or any(
        type(key) is not int or not 0 < key < 2**32 for key in candidates[0]
    ):
        raise VendorBatchStopped("Funding requires one verified nearby warehouse Seneschal.")
    return candidates[0]


class _Funding:
    def __init__(self, binding, parent, record, save, journal, cancelled, clock, sleep):
        self.binding, self.parent, self.record, self.save = binding, parent, record, save
        self.journal, self.cancelled, self.clock, self.sleep = journal, cancelled, clock, sleep
        self.character = None

    def check(self):
        if self.cancelled():
            raise VendorBatchStopped("Vendor funding stopped; confirmed transfers are retained.")
        self.parent.renew_lease()

    def observe(self, session, inspect, matches, *, request=None):
        deadline = self.clock() + (60 if request is None else 16)
        while True:
            self.check()
            receipt = inspect()
            if (
                receipt.outcome != Outcome.OBSERVED
                or receipt.flags & UNRESOLVED
                or receipt.window != self.parent.window
                or request is not None
                and receipt.transition_request != request
            ):
                raise VendorBatchStopped("Vendor funding has an unconfirmed native response.")
            state = receipt.snapshot
            if not state.empty:
                if (state.scene, state.root) != (self.record["scene"], self.record["root"]):
                    raise VendorBatchStopped("The vendor funding scene changed.")
                if hasattr(state, "actor"):
                    character = state.actor, state.character_id, state.character_type
                    if self.character is not None and self.character != character:
                        raise VendorBatchStopped("The character holding the gold changed.")
                    self.character = character
                if not receipt.flags & IN_FLIGHT and (request or receipt.flags & READY):
                    if not matches(state):
                        raise VendorBatchStopped("The vendor funding owner or window changed.")
                    self.journal.assert_idle()
                    return state
            if self.clock() >= deadline:
                raise VendorBatchStopped("Vendor funding timed out; no retry was sent.")
            self.sleep(0.1)

    def action(self, session, label, before, dispatch, inspect, matches):
        self.check()
        key = str(uuid.uuid4())
        attempt = dict(
            request_key=key, operation=label, state="prepared", expected=before.encode().hex()
        )
        self.record["actions"].append(attempt)
        self.save()
        response = dispatch(key)
        attempt.update(state="submitted", outcome=response.outcome.name)
        self.save()
        if (
            response.outcome != Outcome.SUBMITTED
            or response.flags != IN_FLIGHT
            or response.request_key != key
            or response.transition_request != key
            or response.window != self.parent.window
            or response.snapshot != before
        ):
            raise VendorBatchStopped("Vendor funding submission was not confirmed; no retry sent.")
        after = self.observe(session, inspect, matches, request=key)
        attempt.update(state="confirmed", observed=after.encode().hex())
        self.save()
        return after

    def visit(self, session, building, vendor=0, *, warehouse=False):
        before = self.observe(session, session.inspect, lambda _: True)
        if not before.opened(building):
            before = self.action(
                session,
                "building",
                before,
                lambda key: session.open_building(before, building, key),
                session.inspect,
                lambda state: state.opened(building),
            )
        if vendor:
            before = self.action(
                session,
                "vendor",
                before,
                lambda key: session.open_vendor(before, building, vendor, key),
                session.inspect,
                lambda state: state.opened(building, vendor),
            )
        if warehouse:
            self.action(
                session,
                "warehouse",
                before,
                lambda key: session.open_warehouse(before, building, vendor, key),
                session.inspect,
                lambda state: state.warehouse_opened(building, vendor),
            )

    def funds(self, session, direction, source):
        state = self.observe(
            session,
            lambda: session.inspect(direction),
            lambda state: (
                state.direction == direction
                and state.source_id == source
                and state.source_type == (42 if direction == Direction.WAREHOUSE else 8)
            ),
        )
        if state.quote:
            raise VendorBatchStopped("Review the existing gold amount window before funding.")
        return state

    def transfer(self, session, before, amount):
        if not before.can_open or type(amount) is not int or amount <= 0:
            raise VendorBatchStopped("The vendor gold movement is unavailable.")

        def inspect():
            return session.inspect(Direction(before.direction))

        quote = self.action(
            session,
            "quote",
            before,
            lambda key: session.open_quote(before, key),
            inspect,
            before.same_owner,
        )
        if not quote.eligible(amount):
            raise VendorBatchStopped("The gold balance or reserve changed before transfer.")
        after = self.action(
            session,
            "withdraw" if before.direction == 1 else "deposit",
            quote,
            lambda key: session.transfer(quote, amount, key),
            inspect,
            before.same_owner,
        )
        field = "withdrawn" if before.direction == 1 else "deposited"
        self.record[field] += amount
        self.save()
        return after


def fund_saved_vendor(
    store,
    binding,
    operation,
    parent,
    selection,
    *,
    cancelled,
    cost_reader=read_cost,
    target_reader=warehouse_target,
    clock=time.monotonic,
    sleep=time.sleep,
):
    """Fund one current-capacity batch and return to its saved recipe; never craft."""
    if not re.fullmatch(r"operation-[0-9a-f]{32}", operation.operation_id):
        raise ValueError("a canonical vendor operation is required")
    if (parent.identity.process_id, parent.identity.creation_filetime_utc, parent.window) != (
        binding.game_process_id,
        binding.game_process_started_at_100ns,
        binding.game_window_handle,
    ):
        raise VendorBatchStopped("Vendor funding belongs to another client lifetime.")
    directory = store.root / "funding" / operation.operation_id
    path = directory / "funding.json"
    journal = GuardSpendingJournal(store.root)
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        current = store.current()
        if current and current["state"] not in {"complete", "stopped"}:
            raise VendorBatchStopped("Review the existing vendor job before moving gold.")
        CondemnProgressStore(store.root).assert_idle()
        journal.assert_idle()
        if path.exists():
            raise VendorBatchStopped("This vendor funding was already attempted; no replay sent.")
        first = parent.inspect_random()
        if (
            first.outcome != Outcome.OBSERVED
            or first.flags & (IN_FLIGHT | UNRESOLVED)
            or first.snapshot.building != selection["building"]["object_id"]
            or first.snapshot.vendor != selection["vendor"]["object_id"]
        ):
            raise VendorBatchStopped("The saved vendor is not ready for funding.")
        spec = RandomRecipeSpec.from_dict(selection["recipe_spec"])
        record = dict(
            schema_version=1,
            identity=list(store.identity),
            operation_id=operation.operation_id,
            process_id=binding.game_process_id,
            creation=binding.game_process_started_at_100ns,
            window=parent.window,
            scene=first.snapshot.scene,
            root=first.snapshot.root,
            building=first.snapshot.building,
            vendor=first.snapshot.vendor,
            recipe_revision=selection["revision"],
            recipe_sha256=spec.canonical_digest,
            state="running",
            actions=[],
            withdrawn=0,
            deposited=0,
        )

        def save():
            _write(path, record)

        cycle = _Funding(binding, parent, record, save, journal, cancelled, clock, sleep)
        save()
        navigation = NativeVendorNavigationSession.borrow(parent, journal=journal)
        funding = NativeGuardFundingSession.borrow(parent, journal=journal)
        menus = parent.menu_session()
        try:
            cycle.observe(
                parent,
                parent.inspect_random,
                lambda state: (
                    (state.building, state.vendor) == (record["building"], record["vendor"])
                ),
            )
            prepare_recipe(
                menus,
                directory / "prepare.json",
                menus.inspect().snapshot,
                spec.template,
                table=spec.table,
                cancelled=cancelled,
            )
            queue, costs = cost_reader(binding)
            fresh = parent.inspect_random()
            if (
                fresh.flags & (IN_FLIGHT | UNRESOLVED)
                or fresh.outcome != Outcome.OBSERVED
                or not spec.matches(fresh.snapshot)
                or (
                    fresh.snapshot.scene,
                    fresh.snapshot.root,
                    fresh.snapshot.building,
                    fresh.snapshot.vendor,
                )
                != (record["scene"], record["root"], record["building"], record["vendor"])
                or (
                    queue["process_id"],
                    queue["process_creation_filetime_utc"],
                    queue["manager_address"],
                    queue["creation_recipe"]["window_address"],
                    queue["building"]["object_id"],
                    queue["vendor"]["object_id"],
                )
                != (
                    binding.game_process_id,
                    binding.game_process_started_at_100ns,
                    fresh.snapshot.manager,
                    fresh.snapshot.recipe,
                    record["building"],
                    record["vendor"],
                )
                or [(row["item"]["object_id"], row["state"]) for row in queue["slots"]]
                != [
                    (slot.item, ("empty", "cooking", "complete")[slot.state])
                    for slot in fresh.snapshot.slots
                ]
            ):
                raise VendorBatchStopped("Recipe cost or production ownership changed.")
            free = fresh.snapshot.free_slots
            budget = VendorBatchBudget.from_snapshot(fresh.snapshot, costs)
            record.update(
                capacity=len(fresh.snapshot.slots),
                free_slots=free,
                costs={str(key): value for key, value in costs.items()},
                batch_budget=budget.as_dict(), batch_budget_sha256=budget.canonical_digest,
            )
            save()
            if free:
                displayed = queue.get("recipe_resource_costs")
                if (not isinstance(displayed, dict) or len(displayed) != 1
                        or set(displayed) != {str(key) for key in costs}
                        or any(row != {"label": "Gold", "amount": costs[int(key)]}
                               for key, row in displayed.items())):
                    raise VendorBatchStopped("This recipe needs unqualified non-gold resources.")
                resource = next(iter(costs))
                required = budget.total_costs[resource]
                if not 0 < required <= 2**31 - 1:
                    raise VendorBatchStopped("The vendor batch gold requirement exceeds bounds.")
                record.update(required=required, resource=resource)
                save()
                close_recipe(
                    menus, directory / "close.json", menus.inspect().snapshot, cancelled=cancelled
                )
                cycle.visit(navigation, record["building"])
                destination = cycle.funds(funding, Direction.STRUCTURE, record["building"])
                shortfall = max(0, required - destination.balance)
                missing = max(0, shortfall - destination.purse)
                if missing:
                    warehouse, source = target_reader(
                        store, binding, record["scene"], record["root"])
                    record.update(warehouse=warehouse, source=source)
                    save()
                    cycle.visit(navigation, warehouse, source, warehouse=True)
                    source_state = cycle.funds(funding, Direction.WAREHOUSE, source)
                    record["reserve"] = source_state.reserve
                    save()
                    missing = max(0, shortfall - source_state.purse)
                    if (
                        source_state.resource != resource
                        or missing > max(0, source_state.balance - source_state.reserve)
                        or missing > 2**31 - 1 - source_state.purse
                    ):
                        raise VendorBatchStopped(
                            "Warehouse gold above reserve cannot fund this batch."
                        )
                    if missing:
                        cycle.transfer(funding, source_state, missing)
                    cycle.visit(navigation, record["building"])
                    destination = cycle.funds(funding, Direction.STRUCTURE, record["building"])
                    shortfall = max(0, required - destination.balance)
                if shortfall > destination.purse:
                    raise VendorBatchStopped(
                        "Building funds changed; transferred gold remains carried."
                    )
                if shortfall:
                    destination = cycle.transfer(funding, destination, shortfall)
                record["confirmed_building_balance"] = destination.balance
                cycle.visit(navigation, record["building"], record["vendor"])
                prepare_recipe(
                    menus,
                    directory / "return.json",
                    menus.inspect().snapshot,
                    spec.template,
                    table=spec.table,
                    cancelled=cancelled,
                )
                after_queue, after_costs = cost_reader(binding)
                after = parent.inspect_random()
                if (
                    after.outcome != Outcome.OBSERVED
                    or after.flags & (IN_FLIGHT | UNRESOLVED)
                    or not spec.matches(after.snapshot)
                    or (
                        after.snapshot.scene,
                        after.snapshot.root,
                        after.snapshot.building,
                        after.snapshot.vendor,
                    )
                    != (record["scene"], record["root"], record["building"], record["vendor"])
                    or after_costs != costs
                    or after_queue.get("recipe_resource_costs") != queue["recipe_resource_costs"]
                    or (
                        after_queue["process_id"],
                        after_queue["process_creation_filetime_utc"],
                        after_queue["manager_address"],
                        after_queue["creation_recipe"]["window_address"],
                        after_queue["building"]["object_id"],
                        after_queue["vendor"]["object_id"],
                    )
                    != (
                        binding.game_process_id,
                        binding.game_process_started_at_100ns,
                        after.snapshot.manager,
                        after.snapshot.recipe,
                        record["building"],
                        record["vendor"],
                    )
                    or [row["item"]["object_id"] for row in after_queue["slots"]]
                    != [row["item"]["object_id"] for row in queue["slots"]]
                    or [slot.item for slot in after.snapshot.slots]
                    != [row["item"]["object_id"] for row in after_queue["slots"]]
                    or after.snapshot.free_slots != free
                    or not budget.matches(after.snapshot)
                ):
                    raise VendorBatchStopped(
                        "Vendor recipe, capacity or production changed during funding."
                    )
            journal.assert_idle()
            record["state"] = "funded"
            save()
            return record
        except Exception as exc:
            record.update(state="review", detail=str(exc)[:240])
            save()
            raise
        finally:
            menus.close()
            funding.close()
            navigation.close()
