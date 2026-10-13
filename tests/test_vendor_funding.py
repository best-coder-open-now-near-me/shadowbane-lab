import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension import vendor_navigation_wire as nav
from shadowbane_lab.client_extension import vendor_wire as vendor
from shadowbane_lab.client_extension.guard_spending_journal import (
    GuardSpendingJournal,
    GuardSpendingStopped,
)
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_recipe import RandomRecipeSpec
from shadowbane_lab.manager import vendor_funding as module
from shadowbane_lab.manager.vendor_job import VendorJobStore
from tests.test_guard_funding_cycle import IDENTITY, Session, World


class Navigation(Session):
    def open_vendor(self, before, building, target, key):
        def mutate():
            self.world.navigation = replace(
                before,
                vendor_id=target,
                vendor_type=42,
                vendor_hud=400,
                front_hud=400,
                selected_entry=500,
                visible=3,
            )

        return self.action(
            nav.Verb.VENDOR, before, key, "vendor", mutate, building=building, target=target
        )


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(
        game_process_id=988, game_process_started_at_100ns=123, game_window_handle=1000
    )
    operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
    world = World()
    world.gold, world.reserve, world.purse, world.funds = 1000, 100, 20, 10
    world.open_sessions = 2
    journal = GuardSpendingJournal(store.root)
    host = nav.Host(1, 2, 3)
    navigation = Navigation(world, "navigation", journal, host)
    funding = Session(world, "funding", journal, host)
    monkeypatch.setattr(
        module.NativeVendorNavigationSession, "borrow", lambda *args, **kwargs: navigation
    )
    monkeypatch.setattr(module.NativeGuardFundingSession, "borrow", lambda *args, **kwargs: funding)
    monkeypatch.setattr(module, "prepare_recipe", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "close_recipe", lambda *args, **kwargs: None)
    spec = RandomRecipeSpec(26990, 12)
    snapshot = vendor.Snapshot(
        scene=1,
        revision=1,
        root=100,
        manager=200,
        menu=400,
        recipe=700,
        hireling=500,
        building=123,
        vendor=888,
        item_template=26990,
        prefix=3362971591,
        suffix=3362971591,
        mode=1,
        table=12,
        quantity=1,
        slots=(vendor.Slot(1100), vendor.Slot(1200)),
    )
    parent = SimpleNamespace(
        identity=IDENTITY,
        window=1000,
        snapshot=snapshot,
        renew_lease=lambda: None,
        inspect_random=lambda: vendor.Receipt(
            str(uuid.uuid4()), host, 1000, vendor.Outcome.OBSERVED, vendor.READY, parent.snapshot
        ),
        menu_session=lambda: SimpleNamespace(
            inspect=lambda: SimpleNamespace(snapshot=None), close=lambda: None
        ),
    )
    selection = dict(
        building={"object_id": 123},
        vendor={"object_id": 888},
        recipe_spec=spec.as_dict(),
        revision="b" * 32,
    )
    calls = []

    def cost_reader(_):
        calls.append("cost")
        return dict(
            process_id=988,
            process_creation_filetime_utc=123,
            manager_address=200,
            creation_recipe={"window_address": 700},
            building={"object_id": 123},
            vendor={"object_id": 888},
            recipe_resource_costs={"555": {"label": "Gold", "amount": 166}},
            slots=[{"item": {"object_id": 0}, "state": "empty"}] * len(parent.snapshot.slots),
        ), {555: 166}

    tick = [0]

    def clock():
        tick[0] += 0.01
        return tick[0]

    def run(**changes):
        return module.fund_saved_vendor(
            store,
            binding,
            operation,
            parent,
            selection,
            cancelled=changes.get("cancelled", lambda: False),
            cost_reader=changes.get("cost_reader", cost_reader),
            target_reader=changes.get("target_reader", lambda *args: (999, 999)),
            clock=clock,
            sleep=lambda _: None,
        )

    return SimpleNamespace(
        store=store,
        world=world,
        run=run,
        parent=parent,
        calls=calls,
        reader=cost_reader,
        binding=binding,
        path=store.root / "funding" / operation.operation_id / "funding.json",
    )


def test_warehouse_funds_only_shortfall_then_returns_to_exact_vendor(setup):
    result = setup.run()
    assert result["state"] == "funded"
    assert result["required"] == 332 and result["free_slots"] == 2
    assert (result["withdrawn"], result["deposited"]) == (302, 322)
    assert (setup.world.gold, setup.world.purse, setup.world.funds) == (698, 0, 332)
    assert setup.world.navigation.opened(123, 888)
    assert all(row["state"] == "confirmed" for row in result["actions"])
    assert "upgrade" not in setup.world.calls
    GuardSpendingJournal(setup.store.root).assert_idle()
    previous = setup.world.calls[:]
    with pytest.raises(VendorBatchStopped, match="already attempted"):
        setup.run()
    assert setup.world.calls == previous


@pytest.mark.parametrize("size", [1, 2, 7, 16])
def test_one_funding_transaction_covers_entire_available_batch(setup, size):
    setup.world.gold = 10000
    setup.parent.snapshot = replace(
        setup.parent.snapshot, slots=tuple(vendor.Slot(1100 + index * 100) for index in range(size))
    )
    result = setup.run()
    assert result["required"] == 166 * size
    assert result["free_slots"] == size
    assert setup.world.calls.count("withdraw") == 1
    assert setup.world.calls.count("deposit") == 1
    assert result["deposited"] == 166 * size - 10
    assert result["withdrawn"] == 166 * size - 10 - 20
    assert setup.world.funds == 166 * size


@pytest.mark.parametrize("funds,purse,withdrawn,deposited", [(400, 0, 0, 0), (10, 500, 0, 322)])
def test_existing_gold_avoids_unnecessary_money_movements(
    setup, funds, purse, withdrawn, deposited
):
    setup.world.funds, setup.world.purse = funds, purse
    def warehouse_unavailable(*args):
        raise AssertionError("Existing shop/carried gold must not require warehouse access")

    result = setup.run(target_reader=warehouse_unavailable)
    assert (result["withdrawn"], result["deposited"]) == (withdrawn, deposited)
    assert "withdraw" not in setup.world.calls
    assert "warehouse" not in setup.world.calls


def test_reserve_prevents_withdrawal_or_deposit(setup):
    setup.world.reserve = 999
    with pytest.raises(VendorBatchStopped, match="above reserve"):
        setup.run()
    assert not {"withdraw", "deposit"} & set(setup.world.calls)
    assert (setup.world.gold, setup.world.purse, setup.world.funds) == (1000, 20, 10)


@pytest.mark.parametrize(
    "failure", ["building", "vendor", "warehouse", "quote", "withdraw", "deposit"]
)
def test_lost_reply_blocks_later_phases_and_never_replays(setup, failure):
    setup.world.fail = failure
    with pytest.raises(TimeoutError, match="lost"):
        setup.run()
    assert setup.world.calls[-1] == failure
    assert setup.world.calls.count(failure) == 1
    assert json.loads(setup.path.read_text())["state"] == "review"
    with pytest.raises(GuardSpendingStopped):
        GuardSpendingJournal(setup.store.root).assert_idle()


def test_character_change_at_quote_stops_before_transfer(setup):
    setup.world.foreign_actor = True
    with pytest.raises(VendorBatchStopped, match="character"):
        setup.run()
    assert not {"withdraw", "deposit"} & set(setup.world.calls)


def test_cancelled_funding_moves_no_gold(setup):
    with pytest.raises(VendorBatchStopped, match="stopped"):
        setup.run(cancelled=lambda: True)
    assert not setup.world.calls


def test_unqualified_material_is_never_treated_as_gold(setup):
    def cost_reader(_):
        queue = dict(
            process_id=988,
            process_creation_filetime_utc=123,
            manager_address=200,
            creation_recipe={"window_address": 700},
            building={"object_id": 123},
            vendor={"object_id": 888},
            recipe_resource_costs={"555": {"label": "Gold", "amount": 166}},
            slots=[{"item": {"object_id": 0}, "state": "empty"}] * 2,
        )
        return queue, {555: 166, 777: 20}

    with pytest.raises(VendorBatchStopped, match="non-gold"):
        setup.run(cost_reader=cost_reader)
    assert not {"withdraw", "deposit"} & set(setup.world.calls)


def test_unresolved_create_stops_funding_before_menu_or_transfer(setup):
    inspect = setup.parent.inspect_random
    setup.parent.inspect_random = lambda: replace(inspect(), flags=vendor.UNRESOLVED)
    with pytest.raises(VendorBatchStopped, match="not ready"):
        setup.run()
    assert not setup.path.exists() and not setup.world.calls and not setup.calls


def test_dashboard_focus_waits_before_navigation_and_spending(setup):
    inspect = setup.parent.inspect_random
    count = [0]

    def observe():
        count[0] += 1
        return replace(inspect(), flags=0 if count[0] < 4 else vendor.READY)

    setup.parent.inspect_random = observe
    assert setup.run()["state"] == "funded"
    assert count[0] >= 4


def test_existing_review_job_prevents_even_funding(setup, monkeypatch):
    monkeypatch.setattr(setup.store, "current", lambda: {"state": "review"})
    with pytest.raises(VendorBatchStopped, match="existing vendor job"):
        setup.run()
    assert not setup.path.exists() and not setup.world.calls


def test_cost_change_after_transfer_stops_before_crafting(setup):
    def read(_):
        setup.calls.append("cost")
        return dict(
            process_id=988,
            process_creation_filetime_utc=123,
            manager_address=200,
            creation_recipe={"window_address": 700},
            building={"object_id": 123},
            vendor={"object_id": 888},
            recipe_resource_costs={"555": {"label": "Gold", "amount":
                                          166 if len(setup.calls) == 1 else 200}},
            slots=[{"item": {"object_id": 0}, "state": "empty"}] * 2,
        ), {555: 166 if len(setup.calls) == 1 else 200}

    with pytest.raises(VendorBatchStopped, match="changed during funding"):
        setup.run(cost_reader=read)
    assert setup.world.funds == 332
    assert json.loads(setup.path.read_text())["state"] == "review"


def test_changed_gold_label_after_transfer_stops_before_crafting(setup):
    def read(binding):
        queue, costs = setup.reader(binding)
        if len(setup.calls) > 1:
            queue["recipe_resource_costs"]["555"]["label"] = "Iron"
        return queue, costs

    with pytest.raises(VendorBatchStopped, match="changed during funding"):
        setup.run(cost_reader=read)
    assert setup.world.funds == 332
    assert json.loads(setup.path.read_text())["state"] == "review"


def test_non_gold_display_stops_before_any_navigation_or_transfer(setup):
    def read(binding):
        queue, costs = setup.reader(binding)
        queue["recipe_resource_costs"]["555"]["label"] = "Iron"
        return queue, costs

    with pytest.raises(VendorBatchStopped, match="non-gold"):
        setup.run(cost_reader=read)
    assert setup.world.calls == []


@pytest.mark.parametrize(
    "change", ["none", "ambiguous", "scene", "lifetime", "unverified", "valid"]
)
def test_warehouse_selection_uses_exact_current_verified_roster(setup, change):
    row = dict(
        state="verified",
        building={"object_id": 999, "object_type": 8},
        vendors=[
            dict(
                window_verified=True,
                state="verified",
                service_label="Seneschal",
                vendor={"object_id": 999, "object_type": 42},
            )
        ],
    )
    record = dict(
        schema_version=1,
        state="complete",
        identity=list(setup.store.identity),
        game_process_id=988,
        game_creation_filetime=123,
        scene=1,
        root=100,
        roster=[row],
    )
    if change == "none":
        record["roster"] = []
    elif change == "ambiguous":
        record["roster"].append(row)
    elif change == "scene":
        record["scene"] = 2
    elif change == "lifetime":
        record["game_creation_filetime"] = 124
    elif change == "unverified":
        row["vendors"][0]["window_verified"] = False
    module._write(setup.store.root / "navigation" / ("operation-" + "c" * 32 + ".json"), record)
    if change == "valid":
        assert module.warehouse_target(setup.store, setup.binding, 1, 100) == (999, 999)
    else:
        with pytest.raises(VendorBatchStopped):
            module.warehouse_target(setup.store, setup.binding, 1, 100)
