"""One durable warehouse-to-building funding and guard-upgrade transaction.

The town scheduler owns the target list and repeats completed cycles as ranks
become available. This layer owns exact window/session handoffs and every gold
movement; it never treats submission as acceptance or replays an interrupted cycle.
"""
from __future__ import annotations

import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.guard_funding_session import NativeGuardFundingSession
from shadowbane_lab.client_extension.guard_funding_wire import Direction
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.client_extension.guard_upgrade_session import NativeGuardUpgradeSession
from shadowbane_lab.client_extension.vendor_navigation_session import NativeVendorNavigationSession
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Outcome,
)
from shadowbane_lab.record_store import exclusive_record_lock

from .vendor_discovery import _memory
from .vendor_job import _write


class GuardFundingCycleStopped(RuntimeError):
    """No later phase may run after this failure; journals remain authoritative."""


class _Cancelled(GuardFundingCycleStopped):
    pass


@dataclass(frozen=True, slots=True)
class GuardFundingTarget:
    process_id: int
    creation: int
    scene: int
    root: int
    warehouse_building: int
    warehouse_hireling: int
    building: int
    guard: int

    def __post_init__(self):
        for field, value in asdict(self).items():
            bits = 64 if field in {"scene", "creation"} else 32
            if type(value) is not int or not 0 < value < 2 ** bits:
                raise ValueError("guard funding requires exact scene and object identities")


def open_guard_cycle_session(binding, kind, *, journal):
    _memory(binding).close()
    constructors = {
        "navigation": NativeVendorNavigationSession,
        "funding": NativeGuardFundingSession,
        "guard": NativeGuardUpgradeSession,
    }
    return constructors[kind](
        NativeClientProcessIdentity(binding.game_process_id, binding.game_process_started_at_100ns),
        binding.game_window_handle, journal=journal,
    )


class _Cycle:
    def __init__(self, binding, target, journal, record, save, cancelled, factory, clock, sleep):
        self.binding, self.target, self.journal = binding, target, journal
        self.record, self.save, self.cancelled = record, save, cancelled
        self.factory, self.clock, self.sleep = factory, clock, sleep
        self.character = None

    def check(self):
        if self.cancelled():
            raise _Cancelled("Guard funding cancelled; confirmed gold movements are retained.")

    @contextmanager
    def session(self, kind):
        self.check()
        self.journal.assert_idle()
        session = self.factory(self.binding, kind, journal=self.journal)
        try:
            if session.identity != NativeClientProcessIdentity(
                self.binding.game_process_id, self.binding.game_process_started_at_100ns,
            ) or session.window != self.binding.game_window_handle:
                raise GuardFundingCycleStopped("The guard session belongs to another client.")
            yield session
            # A producer is never handed off while its transition is pending.
            self.journal.assert_idle()
        finally:
            session.close()

    def context(self, state):
        context = getattr(state, "navigation", state)
        if (context.scene, context.root) != (self.target.scene, self.target.root):
            raise GuardFundingCycleStopped("The guard funding scene changed.")
        if hasattr(state, "character_id"):
            character = state.actor, state.character_id, state.character_type
            if self.character is not None and character != self.character:
                raise GuardFundingCycleStopped("The character holding the gold changed.")
            self.character = character

    def observe(self, session, inspect, matches, *, request=None):
        deadline = self.clock() + (15 if request else 60)
        while True:
            self.check()
            session.renew_lease()
            receipt = inspect()
            if receipt.outcome != Outcome.OBSERVED or receipt.flags & UNRESOLVED:
                raise GuardFundingCycleStopped("An unresolved guard action needs review.")
            if request is not None and receipt.transition_request != request:
                raise GuardFundingCycleStopped(
                    "The active guard response belongs to another request."
                )
            if not receipt.snapshot.empty:
                self.context(receipt.snapshot)
                if not receipt.flags & IN_FLIGHT and (request or receipt.flags & READY):
                    if not matches(receipt.snapshot):
                        raise GuardFundingCycleStopped(
                            "The requested guard funding window changed."
                        )
                    if request:
                        self.journal.assert_idle()
                    return receipt.snapshot
            if self.clock() >= deadline:
                raise GuardFundingCycleStopped("The guard funding response was not confirmed.")
            self.sleep(0.1)

    def action(self, session, label, before, dispatch, inspect, matches):
        self.check()
        key = str(uuid.uuid4())
        attempt = {"request_key": key, "operation": label, "state": "prepared",
                   "expected": before.encode().hex()}
        self.record["actions"].append(attempt)
        self.record["phase"] = label
        self.save()
        self.check()
        response = dispatch(key)
        attempt.update(state="submitted", outcome=response.outcome.name)
        self.save()
        if (response.outcome not in (Outcome.SUBMITTED, Outcome.OBSERVED)
                or response.flags & UNRESOLVED or response.transition_request != key):
            raise GuardFundingCycleStopped("Guard action was not accepted; no retry was sent.")
        after = self.observe(session, inspect, matches, request=key)
        attempt.update(state="confirmed", observed=after.encode().hex())
        self.save()
        return after

    def visit(self, building, *, guard=0, warehouse=0):
        with self.session("navigation") as session:
            before = self.observe(session, session.inspect, lambda _: True)
            if warehouse:
                def opened(state):
                    return state.warehouse_opened(building, warehouse)
            elif guard:
                def opened(state):
                    return state.opened(building, guard, hireling_type=37)
            else:
                def opened(state):
                    return state.opened(building)
            if opened(before):
                return  # Inspection is sufficient; no action UUID is consumed.
            if not before.owns_building(building) or not (guard or warehouse):
                before = self.action(
                    session, "open_building", before,
                    lambda key: session.open_building(before, building, key), session.inspect,
                    lambda s: s.opened(building),
                )
            if guard or warehouse:
                method = session.open_warehouse if warehouse else session.open_guard
                self.action(
                    session, "open_warehouse" if warehouse else "open_guard", before,
                    lambda key: method(before, building, warehouse or guard, key),
                    session.inspect, opened,
                )

    def guard_state(self):
        with self.session("guard") as session:
            return self.observe(
                session, session.inspect,
                lambda s: s.navigation.opened(self.target.building, self.target.guard,
                                              hireling_type=37),
            )

    def funding_state(self, session, direction, source):
        state = self.observe(
            session, lambda: session.inspect(direction),
            lambda s: s.direction == direction and s.source_id == source
            and s.source_type == (42 if direction == Direction.WAREHOUSE else 8),
        )
        if state.quote:
            raise GuardFundingCycleStopped("An existing amount window must be reviewed first.")
        return state

    def transfer(self, session, before, amount):
        if not before.can_open or amount <= 0:
            raise GuardFundingCycleStopped("The requested gold movement is unavailable.")
        def inspect():
            return session.inspect(Direction(before.direction))

        def same(state):
            return before.same_owner(state)
        quote = self.action(
            session, "open_quote", before, lambda key: session.open_quote(before, key),
            inspect, same,
        )
        if not quote.eligible(amount):
            raise GuardFundingCycleStopped("The gold quote changed before transfer.")
        after = self.action(
            session, "withdraw" if before.direction == 1 else "deposit", quote,
            lambda key: session.transfer(quote, amount, key), inspect, same,
        )
        field = "withdrawn" if before.direction == 1 else "deposited"
        self.record[field] += amount
        self.save()
        return after

    def run(self):
        t = self.target
        self.visit(t.building, guard=t.guard)
        before = self.guard_state()
        self.record.update(initial_rank=before.rank, quoted_cost=before.cost,
                           initial_building_funds=before.funds)
        self.save()
        if before.upgrading:
            return "waiting", "This guard is already upgrading."
        if before.rank < self.record["minimum_rank"]:
            raise GuardFundingCycleStopped(
                "The previously accepted guard upgrade has not reached its expected rank."
            )
        if not before.can_upgrade or not before.cost or before.control_flags != 3:
            return "unavailable", "No eligible upgrade is offered; maximum rank is unverified."
        if before.funds < before.cost:
            self.visit(t.warehouse_building, warehouse=t.warehouse_hireling)
            with self.session("funding") as session:
                source = self.funding_state(session, Direction.WAREHOUSE, t.warehouse_hireling)
                shortfall = max(0, before.cost - before.funds - source.purse)
                if shortfall > max(0, source.balance - source.reserve):
                    return "insufficient", "Warehouse gold and purse cannot fund this upgrade."
                if shortfall:
                    self.transfer(session, source, shortfall)
            self.visit(t.building)
            with self.session("funding") as session:
                destination = self.funding_state(session, Direction.STRUCTURE, t.building)
                shortfall = max(0, before.cost - destination.balance)
                if shortfall > destination.purse:
                    raise GuardFundingCycleStopped("The guard building or purse balance changed.")
                if shortfall:
                    self.transfer(session, destination, shortfall)
            self.visit(t.building, guard=t.guard)
        with self.session("guard") as session:
            current = self.observe(
                session, session.inspect,
                lambda s: s.navigation.opened(t.building, t.guard, hireling_type=37),
            )
            if current.rank != before.rank or current.cost != before.cost or not current.eligible:
                raise GuardFundingCycleStopped(
                    "The guard rank, price or eligibility changed before spending."
                )
            after = self.action(
                session, "upgrade", current, lambda key: session.upgrade(current, key),
                session.inspect,
                lambda s: s.navigation.opened(t.building, t.guard, hireling_type=37),
            )
        self.record.update(spent=current.cost, observed_rank=after.rank,
                           upgrade_in_progress=bool(after.upgrading))
        return "started", "The guard upgrade and its exact gold debit are confirmed."


def run_guard_funding_cycle(
    store, binding, operation, target: GuardFundingTarget, *, cancelled,
    session_factory=open_guard_cycle_session, clock=time.monotonic, sleep=time.sleep,
    minimum_rank=1,
):
    """Execute one freshly quoted guard upgrade, preserving all intermediate receipts.

    Caller admission supplies the exact process-bound scene and discovered typed
    targets. No cycle is resumed by repeating its operation ID. A new cycle must
    observe new state and is blocked by any unresolved shared journal action.
    """
    if not isinstance(target, GuardFundingTarget):
        raise ValueError("a validated guard funding target is required")
    if type(minimum_rank) is not int or not 0 < minimum_rank < 2**32 - 1:
        raise ValueError("a valid minimum guard rank is required")
    if not re.fullmatch(r"operation-[0-9a-f]{32}", operation.operation_id):
        raise ValueError("a canonical worker operation is required")
    if (target.process_id, target.creation) != (
        binding.game_process_id, binding.game_process_started_at_100ns,
    ):
        raise GuardFundingCycleStopped("The guard target belongs to another client lifetime.")
    path = store.root / "guard-funding-cycles" / (operation.operation_id + ".json")
    journal = GuardSpendingJournal(store.root)
    with exclusive_record_lock(store.root / "execution.lock", timeout_seconds=0.1):
        if path.exists():
            raise GuardFundingCycleStopped(
                "This guard cycle was already attempted; no replay sent."
            )
        journal.assert_idle()
        record = {
            "schema_version": 1, "identity": list(store.identity),
            "operation_id": operation.operation_id, "target": asdict(target),
            "process_id": binding.game_process_id,
            "process_creation_filetime_utc": binding.game_process_started_at_100ns,
            "window": binding.game_window_handle,
            "state": "running", "phase": "navigation", "actions": [],
            "minimum_rank": minimum_rank,
            "withdrawn": 0, "deposited": 0, "spent": 0,
        }
        def save():
            _write(path, record)
        cycle = _Cycle(binding, target, journal, record, save, cancelled,
                       session_factory, clock, sleep)
        save()
        try:
            record["state"], record["detail"] = cycle.run()
            save()
            return record
        except Exception as exc:
            record.update(state="cancelled" if isinstance(exc, _Cancelled) else "review",
                          detail=str(exc) or type(exc).__name__)
            save()
            raise
