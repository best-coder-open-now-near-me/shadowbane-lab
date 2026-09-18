import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension import guard_funding_wire as funding
from shadowbane_lab.client_extension import guard_upgrade_wire as upgrade
from shadowbane_lab.client_extension import vendor_navigation_wire as nav
from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.guard_spending_journal import (
    GuardSpendingJournal,
    GuardSpendingStopped,
)
from shadowbane_lab.manager.guard_funding_cycle import (
    GuardFundingCycleStopped,
    GuardFundingTarget,
    run_guard_funding_cycle,
)
from shadowbane_lab.manager.vendor_job import VendorJobStore

TARGET = GuardFundingTarget(988, 123, 1, 100, 123, 777)
IDENTITY = NativeClientProcessIdentity(988, 123)


class World:
    def __init__(self):
        self.navigation = nav.Snapshot(scene=1, revision=1, root=100, manager=200)
        self.gold, self.reserve, self.purse, self.funds, self.cost = 1000, 100, 80, 20, 100
        self.rank, self.upgrading, self.offer = 1, False, True
        self.quote = {1: False, 2: False}
        self.calls, self.sessions, self.open_sessions = [], 0, 0
        self.fail = None
        self.change_price = self.wrong_source = self.foreign_actor = False
        self.pending = None
        self.transitions = {}
        self.revisit = False

    def state(self, kind, direction=1):
        n = self.navigation
        if kind == "navigation":
            return n
        if kind == "guard":
            return upgrade.Snapshot(n, self.rank, self.cost, self.funds, int(self.upgrading),
                                    int(self.offer), 7 if self.upgrading else 3, 1100, 1200)
        warehouse = direction == 1
        quote = self.quote[direction]
        limit = max(0, self.gold - self.reserve) if warehouse else self.purse
        return funding.Snapshot(
            scene=n.scene, revision=1, root=n.root, actor=9000 if self.foreign_actor
            and quote else 8000, character_id=11, character_type=2,
            manager=600 if warehouse else 200, hud=600 if warehouse else 300,
            source_object=700 if warehouse else 0,
            source_id=9999 if self.wrong_source else 999 if warehouse else n.building_id,
            source_type=42 if warehouse else 8, direction=int(direction),
            resource=555 if warehouse else 0, balance=self.gold if warehouse else self.funds,
            reserve=self.reserve if warehouse else 0, purse=self.purse,
            quote=1300 if quote else 0, limit=limit if quote else 0, entered=0,
            accept=1400 if quote else 0, cancel=1500 if quote else 0, helper=1600 if quote else 0,
        )

    def factory(self, binding, kind, *, journal):
        assert not self.open_sessions and self.pending is None
        self.sessions += 1
        self.open_sessions += 1
        return Session(self, kind, journal, nav.Host(1, self.sessions, 1))


class Session:
    def __init__(self, world, kind, journal, host):
        self.world, self.kind, self.journal, self.host = world, kind, journal, host
        self.closed = False
        self.identity, self.window = IDENTITY, 1000

    def renew_lease(self):
        assert not self.closed

    def inspect(self, direction=1):
        w = self.world
        codec = {"navigation": nav, "guard": upgrade, "funding": funding}[self.kind]
        state, flags = w.state(self.kind, direction), nav.READY
        if w.pending:
            kind, prior, pending_direction = w.pending
            assert kind == self.kind and pending_direction == direction
            state, flags = prior, nav.IN_FLIGHT
            w.pending = None
        if self.kind == "guard" and w.revisit and w.upgrading:
            flags |= upgrade.REOPENED
        result = codec.Receipt(str(uuid.uuid4()), self.host, 1000, nav.Outcome.OBSERVED,
                               flags, state, w.transitions.get(self.kind))
        self.journal.observe(IDENTITY, result)
        return result

    def action(self, verb, before, key, label, mutate, *, building=0, target=0, amount=0):
        w = self.world
        if self.kind == "navigation":
            command = nav.Command(self.host, 1000, key, before, building, target)
            codec = nav
        elif self.kind == "guard":
            command = upgrade.Command(self.host, 1000, key, before)
            codec = upgrade
        else:
            command = funding.Command(self.host, 1000, key, before, before.direction, amount)
            codec = funding
        assert before == w.state(self.kind, getattr(before, "direction", 1))

        def dispatch():
            # Both the cycle intent and exact shared journal precede native entry.
            saved = json.loads(self.journal._path(key).read_text())
            assert saved["submission"] is None
            w.calls.append(label)
            mutate()
            w.transitions[self.kind] = key
            w.pending = self.kind, before, getattr(before, "direction", 1)
            if w.fail == label:
                raise TimeoutError("lost " + label + " reply")
            return codec.Receipt(key, self.host, 1000, nav.Outcome.SUBMITTED,
                                 nav.IN_FLIGHT, before, key)

        kwargs = {"navigation_verb": verb} if self.kind == "navigation" else {}
        return self.journal.submit(IDENTITY, command, dispatch, **kwargs)

    def open_building(self, before, building, key):
        def mutate():
            self.world.navigation = replace(before, building_id=building, building_type=8,
                building_hud=300, vendor_hud=0, front_hud=300, visible=1, mode=6,
                vendor_id=0, vendor_type=0, selected_entry=0, initialized=1, capacity=1, occupied=1)
        return self.action(nav.Verb.BUILDING, before, key, "building", mutate, building=building)

    def open_guard(self, before, building, target, key):
        def mutate():
            self.world.navigation = replace(before, vendor_id=target, vendor_type=37,
                vendor_hud=400, front_hud=400, selected_entry=500, visible=3)
            if self.world.change_price and "deposit" in self.world.calls:
                self.world.cost += 1
        return self.action(nav.Verb.GUARD, before, key, "guard", mutate,
                           building=building, target=target)

    def open_warehouse(self, before, building, target, key):
        def mutate():
            self.world.navigation = replace(before, warehouse_hud=600, warehouse_object=700,
                warehouse_id=target, warehouse_type=42, front_hud=600)
        return self.action(nav.Verb.WAREHOUSE, before, key, "warehouse", mutate,
                           building=building, target=target)

    def open_quote(self, before, key):
        return self.action(funding.Verb.OPEN_QUOTE, before, key, "quote",
                           lambda: self.world.quote.update({before.direction: True}))

    def transfer(self, before, amount, key):
        w = self.world
        def mutate():
            if before.direction == 1:
                w.gold -= amount
                w.purse += amount
            else:
                w.purse -= amount
                w.funds += amount
                if w.revisit:
                    w.navigation = replace(w.navigation, mode=0)
            w.quote[before.direction] = False
        return self.action(funding.Verb.TRANSFER, before, key,
                           "withdraw" if before.direction == 1 else "deposit", mutate,
                           amount=amount)

    def upgrade(self, before, key):
        def mutate():
            self.world.funds -= before.cost
            self.world.upgrading = True
            if self.world.revisit:
                self.world.navigation = replace(self.world.navigation, mode=0, building_hud=301,
                    vendor_hud=401, selected_entry=501, front_hud=401)
        return self.action(upgrade.Verb.UPGRADE, before, key, "upgrade", mutate)

    def close(self):
        assert not self.closed
        self.closed = True
        self.world.open_sessions -= 1


@pytest.fixture
def setup(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=123,
                              game_window_handle=1000)
    operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
    world = World()
    tick = [0]
    def clock():
        tick[0] += 0.05
        return tick[0]
    def run(**changes):
        return run_guard_funding_cycle(store, binding, operation, TARGET,
            cancelled=changes.get("cancelled", lambda: False), session_factory=world.factory,
            clock=clock, sleep=lambda _: None)
    return SimpleNamespace(store=store, world=world, run=run, binding=binding, operation=operation,
        path=store.root / "guard-funding-cycles" / (operation.operation_id + ".json"))


def test_funds_only_shortfall_and_confirms_exact_guard_debit(setup):
    result = setup.run()
    assert result["state"] == "started"
    assert (result["withdrawn"], result["deposited"], result["spent"]) == (0, 80, 100)
    w = setup.world
    assert (w.gold, w.purse, w.funds) == (1000, 0, 0)
    assert w.upgrading and not w.open_sessions
    assert all(a["state"] == "confirmed" for a in result["actions"])
    GuardSpendingJournal(setup.store.root).assert_idle()
    calls = w.calls[:]
    with pytest.raises(GuardFundingCycleStopped, match="already attempted"):
        setup.run()
    assert w.calls == calls


@pytest.mark.parametrize("funds,purse,withdrawn,deposited", [(150, 30, 0, 0), (20, 100, 0, 80)])
def test_existing_building_funds_or_purse_avoid_unneeded_transfers(
    setup, funds, purse, withdrawn, deposited,
):
    setup.world.funds, setup.world.purse = funds, purse
    result = setup.run()
    assert result["state"] == "started"
    assert result["withdrawn"] == withdrawn and result["deposited"] == deposited
    assert "withdraw" not in setup.world.calls
    assert "warehouse" not in setup.world.calls
    if not deposited:
        assert "deposit" not in setup.world.calls


@pytest.mark.parametrize("case,state", [("purse", "insufficient"), ("upgrading", "waiting"),
                                         ("no_offer", "unavailable")])
def test_no_gold_moves_for_insufficient_or_unavailable_upgrade(setup, case, state):
    if case == "purse":
        setup.world.purse = 79
    elif case == "upgrading":
        setup.world.upgrading = True
    else:
        setup.world.offer = False
    result = setup.run()
    assert result["state"] == state and result["spent"] == 0
    assert not set(setup.world.calls) & {"withdraw", "deposit", "upgrade"}
    assert (setup.world.gold, setup.world.purse, setup.world.funds) == (
        1000, 79 if case == "purse" else 80, 20)


@pytest.mark.parametrize("failure", ["building", "guard", "quote", "deposit", "upgrade"])
def test_lost_reply_stops_sequence_and_blocks_new_spending_after_restart(setup, failure):
    w = setup.world
    w.fail = failure
    with pytest.raises(TimeoutError, match="lost"):
        setup.run()
    assert w.calls[-1] == failure and w.calls.count(failure) == 1
    assert not w.open_sessions
    result = json.loads(setup.path.read_text())
    assert result["state"] == "review"
    with pytest.raises(GuardSpendingStopped):
        GuardSpendingJournal(setup.store.root).assert_idle()
    with pytest.raises(GuardFundingCycleStopped, match="already attempted"):
        setup.run()


@pytest.mark.parametrize("change", ["wrong_source", "foreign_actor", "change_price"])
def test_changed_ownership_or_price_blocks_later_gold_actions(setup, change):
    setattr(setup.world, change, True)
    with pytest.raises(GuardFundingCycleStopped, match="changed"):
        setup.run()
    assert "upgrade" not in setup.world.calls and not setup.world.open_sessions
    result = json.loads(setup.path.read_text())
    assert result["state"] == "review"
    if change == "wrong_source":
        assert "withdraw" not in setup.world.calls
    elif change == "foreign_actor":
        assert result["withdrawn"] == 0 and "deposit" not in setup.world.calls
    else:
        assert result["deposited"] == 80 and setup.world.funds == 100


def test_cancellation_after_confirmed_deposit_retains_gold_and_does_not_upgrade(setup):
    def cancelled():
        return setup.path.exists() and json.loads(setup.path.read_text())["deposited"] > 0
    with pytest.raises(GuardFundingCycleStopped, match="cancelled"):
        setup.run(cancelled=cancelled)
    result = json.loads(setup.path.read_text())
    assert result["state"] == "cancelled" and result["withdrawn"] == 0
    assert result["deposited"] == 80 and setup.world.purse == 0
    assert setup.world.funds == 100 and "upgrade" not in setup.world.calls
    GuardSpendingJournal(setup.store.root).assert_idle()


def test_existing_amount_quote_is_not_adopted(setup):
    setup.world.quote[2] = True
    with pytest.raises(GuardFundingCycleStopped, match="existing amount"):
        setup.run()
    assert "withdraw" not in setup.world.calls


def test_input_validation_precedes_any_session(setup):
    for value in (0, True, -1, 2**32):
        with pytest.raises(ValueError):
            replace(TARGET, guard=value)
    setup.operation.operation_id = "../elsewhere"
    with pytest.raises(ValueError):
        setup.run()
    assert not setup.world.sessions


def test_stale_discovery_process_cannot_open_any_session(setup):
    setup.binding.game_process_started_at_100ns += 1
    with pytest.raises(GuardFundingCycleStopped, match="another client lifetime"):
        setup.run()
    assert not setup.world.sessions and not setup.path.exists()


def test_factory_session_identity_is_rechecked_and_closed(setup):
    original = setup.world.factory
    def foreign(*args, **kwargs):
        session = original(*args, **kwargs)
        session.window += 1
        return session
    setup.world.factory = foreign
    with pytest.raises(GuardFundingCycleStopped, match="another client"):
        setup.run()
    assert not setup.world.calls and not setup.world.open_sessions


def test_scene_change_stops_before_gold_actions(setup):
    setup.world.navigation = replace(setup.world.navigation, scene=2)
    with pytest.raises(GuardFundingCycleStopped, match="scene changed"):
        setup.run()
    assert not setup.world.calls and not setup.world.open_sessions


def test_already_selected_upgrading_guard_requires_no_new_window_action(setup):
    setup.world.navigation = nav.Snapshot(
        scene=1, revision=1, root=100, manager=200, mode=6, initialized=1,
        building_id=123, building_type=8, building_hud=300,
        vendor_id=777, vendor_type=37, vendor_hud=400, selected_entry=500,
        visible=3, front_hud=400, capacity=1, occupied=1,
    )
    setup.world.upgrading = True
    assert setup.run()["state"] == "waiting"
    assert not setup.world.calls


def test_new_cycle_id_cannot_bypass_an_unresolved_spend(setup):
    setup.world.fail = "deposit"
    with pytest.raises(TimeoutError):
        setup.run()
    before_sessions = setup.world.sessions
    setup.operation.operation_id = "operation-" + "b" * 32
    with pytest.raises(GuardSpendingStopped):
        setup.run()
    assert setup.world.sessions == before_sessions


@pytest.mark.parametrize("delayed_kind,delay", [("navigation", 45), ("funding", 20)])
def test_slow_menu_response_keeps_one_request_without_extending_spending_timeout(
    setup, monkeypatch, delayed_kind, delay,
):
    tick = [0.0]
    releases = {}
    original = Session.inspect

    def inspect(self, direction=1):
        pending = self.world.pending
        if pending and self.kind == delayed_kind:
            key = self.world.transitions[self.kind]
            release = releases.setdefault(key, tick[0] + delay)
            if tick[0] < release:
                codec = nav if self.kind == "navigation" else funding
                receipt = codec.Receipt(str(uuid.uuid4()), self.host, 1000,
                    nav.Outcome.OBSERVED, nav.IN_FLIGHT, pending[1], key)
                self.journal.observe(IDENTITY, receipt)
                return receipt
        return original(self, direction)

    monkeypatch.setattr(Session, "inspect", inspect)

    def run():
        return run_guard_funding_cycle(setup.store, setup.binding, setup.operation, TARGET,
            cancelled=lambda: False, session_factory=setup.world.factory,
            clock=lambda: tick[0], sleep=lambda _: tick.__setitem__(0, tick[0] + 1))

    if delayed_kind == "navigation":
        result = run()
        assert result["state"] == "started"
        assert (result["withdrawn"], result["deposited"], result["spent"]) == (0, 80, 100)
        assert all(a["state"] == "confirmed" for a in result["actions"])
        assert len(result["actions"]) == len(set(a["request_key"] for a in result["actions"]))
        assert setup.world.calls.count("warehouse") == 0
        assert setup.world.calls.count("upgrade") == 1
        GuardSpendingJournal(setup.store.root).assert_idle()
    else:
        with pytest.raises(GuardFundingCycleStopped, match="not confirmed"):
            run()
        assert setup.world.calls[-1] == "quote"
        assert not set(setup.world.calls) & {"withdraw", "deposit", "upgrade"}
        with pytest.raises(GuardSpendingStopped):
            GuardSpendingJournal(setup.store.root).assert_idle()
    assert not setup.world.open_sessions


def test_full_funding_cycle_accepts_idle_deposit_and_correlated_native_guard_revisit(setup):
    setup.world.revisit = True
    result = setup.run()
    assert result["state"] == "started"
    assert result["spent"] == 100 and result["upgrade_in_progress"]
    assert setup.world.calls.count("upgrade") == 1
    assert setup.world.navigation.mode == 0
    GuardSpendingJournal(setup.store.root).assert_idle()


@pytest.mark.parametrize("purse", [0, 79, 80, 40000000])
def test_carried_only_never_accesses_warehouse_even_when_purse_is_empty(setup, monkeypatch, purse):
    setup.world.purse = purse
    def forbidden(*args, **kwargs):
        pytest.fail("Carried-only funding must not open the warehouse")
    monkeypatch.setattr(Session, "open_warehouse", forbidden)
    original = Session.inspect
    def inspect(self, direction=1):
        if self.kind == "funding":
            assert direction == funding.Direction.STRUCTURE
        return original(self, direction)
    monkeypatch.setattr(Session, "inspect", inspect)
    result = setup.run()
    assert result["state"] == ("started" if purse >= 80 else "insufficient")
    assert result["withdrawn"] == 0 and setup.world.gold == 1000
    assert setup.world.purse == purse - (80 if purse >= 80 else 0)
    assert result["deposited"] == (80 if purse >= 80 else 0)
    GuardSpendingJournal(setup.store.root).assert_idle()
