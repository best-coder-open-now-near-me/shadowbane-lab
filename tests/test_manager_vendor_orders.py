import copy
import json
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
from shadowbane_lab.client_extension.vendor_menu_wire import Receipt as MenuReceipt
from shadowbane_lab.client_extension.vendor_order_ledger import OrderLedger
from shadowbane_lab.client_extension.vendor_wire import IN_FLIGHT, Outcome, Slot
from shadowbane_lab.manager.vendor_job import VendorJobStore
from shadowbane_lab.manager.vendor_order_job import require_order_handoff_idle, run_order_job
from tests.test_manager_vendor_recipes import Menus as RecipeMenus
from tests.test_manager_vendor_recipes import Session as RecipeSession
from tests.test_vendor_batch import receipt
from tests.test_vendor_order_batch import SPEC
from tests.test_vendor_order_batch import Recorder as BaseRecorder
from tests.test_vendor_order_batch import Session as QueueSession
from tests.test_vendor_order_progress import CHARACTER


class Recorder(BaseRecorder):
    def __init__(self, parent):
        super().__init__()
        self.parent, self.records = parent, []

    def available(self):
        return {}

    def append(self, item, count):
        first = self.cursor["sequence"] + len(self.records) + 1
        body = dict(action=8, error=0, building=[self.parent.state.building, 8],
                    vendor=[self.parent.state.vendor, 42], item=[item, 40],
                    template=self.parent.state.item_template, remaining_count_raw=count)
        self.records.extend(dict(sequence=first + i, stage=stage, decode_sequence=first,
                                 flags=3 if i == 0 else 7, scene_epoch=1,
                                 local=list(CHARACTER), thread_id=10, payload=copy.deepcopy(body))
                            for i, stage in enumerate(("decoded", "processing", "returned")))

    def drain(self):
        if self.records:
            self.cursor["sequence"] = self.records[-1]["sequence"]
            self.cursor["overwritten"] = max(0, self.cursor["sequence"] - 256)
        records, self.records = self.records, []
        return dict(cursor=dict(self.cursor, capture_incomplete=self.incomplete),
                    records=records, capture_incomplete=self.incomplete)


class Menus(RecipeMenus):
    def order_quantity(self, expected, quantity, key):
        assert quantity == 10
        self.parent.state = replace(self.parent.state, quantity=quantity,
                                    revision=self.parent.state.revision + 1)
        self.transition = key
        return MenuReceipt(key, self.inspect().host, 1000, Outcome.SUBMITTED, IN_FLIGHT, expected)


class Session(QueueSession):
    window = 1000
    tables = {26990: 12, 25860: 16}
    menu_failure = False

    def __init__(self, store, capacity=2):
        super().__init__(store.root / "unused.json", capacity=capacity)
        self.store, self.recorder = store, Recorder(self)
        self.keeps, self.inventory, self.menu_calls = [], set(), []
        self.keep_pending, self.lost_keep, self.time = None, False, 0
        self.focused, self.renewals, self.after_sleep = True, 0, lambda: None
        self.closed_count = 0

    reader = RecipeSession.reader

    def close(self):
        self.closed_count += 1

    def inspect_random(self):
        return self.inspect()

    def menu_session(self):
        return Menus(self)

    def after_menu(self, name):
        pass

    def renew_lease(self):
        self.renewals += 1

    def create_orders(self, expected, key, **kwargs):
        self.path = self.store.directory(self.store.current()["job_id"]) / "create.json"
        return super().create_orders(expected, key, **kwargs)

    def inspect_orders(self):
        pending = self.pending
        observed = super().inspect_orders()
        if pending:
            for slot in self.state.slots:
                if slot.item:
                    self.recorder.append(slot.item, 9)
        return observed if self.focused else replace(observed, flags=0)

    def inspect(self):
        if self.keep_pending:
            item, key = self.keep_pending
            self.keep_pending = None
            self.inventory.add(item)
            index = next(i for i, slot in enumerate(self.state.slots) if slot.item == item)
            count = self.counts[index]
            slots, counts = list(self.state.slots), list(self.counts)
            if count > 1:
                self.next_item += 1
                slots[index] = Slot(slots[index].entry, self.next_item, 1)
                counts[index] -= 1
                self.recorder.append(self.next_item, counts[index] - 1)
            else:
                slots[index], counts[index] = Slot(slots[index].entry), 0
            self.state = replace(self.state, slots=tuple(slots), revision=self.state.revision + 1)
            self.counts, self.last_transition = tuple(counts), (item, key)
        return receipt(self.state, item=self.last_transition[0],
                       transition=self.last_transition[1])

    def keep(self, expected, item, key):
        path = self.store.directory(self.store.current()["job_id"]) / "order-progress.json"
        request = json.loads(path.read_bytes())["requests"][-1]
        assert request["state"] == "prepared" and request["request_key"] == key
        assert expected == self.state and self.focused
        self.keeps.append(item)
        if self.lost_keep:
            raise TimeoutError("lost Keep acknowledgement")
        self.keep_pending = item, key
        return receipt(expected, key, Outcome.SUBMITTED, IN_FLIGHT)

    def sleep(self, seconds):
        self.time += seconds
        slots = tuple(replace(slot, state=2) if slot.item else slot for slot in self.state.slots)
        if slots != self.state.slots:
            self.state = replace(self.state, slots=slots, revision=self.state.revision + 1)
        self.after_sleep()


def setup(tmp_path, capacity=2):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    session = Session(store, capacity)
    budget = VendorBatchBudget.from_snapshot(session.state, {555: 1660})
    selection = dict(recipe_spec=SPEC.recipe.as_dict(), revision="a" * 32,
                     owner=dict(server="Test", character="Treehugger", key=list(CHARACTER)),
                     building=dict(object_id=session.state.building),
                     vendor=dict(object_id=session.state.vendor), display_name="Gilded Scepter",
                     admission_snapshot=session.state.encode().hex(),
                     batch_budget=budget.as_dict(), batch_budget_sha256=budget.canonical_digest,
                     order_spec=SPEC.as_dict(), order_sha256=SPEC.canonical_digest)
    record = store.begin(session, 1000, 0, selection=selection)
    return store, session, record


def run(store, session, record):
    return run_order_job(store, session, record, clock=lambda: session.time,
                         sleeper=session.sleep,
                         reader_factory=lambda *args: session.recorder,
                         inventory_reader=lambda *args: sorted(session.inventory))


def test_full_seventy_item_manager_job_uses_one_batch_create_and_seventy_keeps(tmp_path):
    store, session, record = setup(tmp_path, 7)
    result = run(store, session, record)
    assert result["schema_version"] == 4 and result["state"] == "complete"
    assert (result["queued_orders"], result["planned_items"], result["created"], result["kept"]
            ) == (7, 70, 70, 70)
    assert len(session.calls) == 1 and len(set(session.keeps)) == 70
    assert result["excluded"] == 0 and session.inventory == set(session.keeps)
    require_order_handoff_idle(store, session, result)
    summary = store.summary()
    assert summary["queued_orders"] == 7 and summary["planned_items"] == 70


def test_lost_keep_preserves_prepared_intent_and_never_replays(tmp_path):
    store, session, record = setup(tmp_path, 1)
    session.lost_keep = True
    with pytest.raises(TimeoutError, match="lost Keep"):
        run(store, session, record)
    assert store.current()["state"] == "review" and len(session.keeps) == 1
    path = store.directory(record["job_id"])
    with pytest.raises(VendorBatchStopped, match="uncertain"):
        OrderLedger(path / "order-progress.json", (path / "create.json").read_bytes(),
                    CHARACTER, resume=True)
    assert len(session.keeps) == 1


def test_focus_wait_keeps_recorder_drained_and_sends_no_keep(tmp_path):
    store, session, record = setup(tmp_path, 1)
    count = [0]
    def focus_wait():
        count[0] += 1
        if count[0] == 1:
            session.focused = False
        if count[0] == 4:
            session.focused = True
        if not session.focused:
            assert not session.keeps
            if count[0] > 1:
                assert not session.recorder.records
            session.recorder.append(session.state.slots[0].item, session.counts[0] - 1)
    session.after_sleep = focus_wait
    assert run(store, session, record)["state"] == "complete"


def test_job_summary_crash_after_completed_child_does_not_repeat_actions(tmp_path):
    store, session, record = setup(tmp_path, 1)
    result = run(store, session, record)
    calls, keeps = list(session.calls), list(session.keeps)
    result.update(state="cooking", created=0, kept=0)
    store.save(result)
    resumed = run(store, session, result)
    assert resumed["state"] == "complete" and resumed["kept"] == 10
    assert session.calls == calls and session.keeps == keeps


@pytest.mark.parametrize("corruption", ["hash", "cursor", "missing_keep", "prepared", "flags"])
def test_recovery_requires_exact_complete_inventory_chain(tmp_path, corruption):
    store, session, record = setup(tmp_path, 1)
    run(store, session, record)
    directory = store.directory(record["job_id"])
    path = directory / "order-progress.json"
    evidence = json.loads(path.read_bytes())
    if corruption == "hash":
        evidence["admission_sha256"] = "0" * 64
    elif corruption == "cursor":
        evidence["cursor"]["sequence"] += 1
    elif corruption == "missing_keep":
        evidence["events"] = [e for e in evidence["events"] if e["kind"] != "kept"]
    elif corruption == "prepared":
        evidence["state"] = "running"
        evidence["requests"][0]["state"] = "prepared"
    else:
        next(e for e in evidence["events"] if e["kind"] == "kept")["flags"] = 8
    path.write_text(json.dumps(evidence))
    calls, keeps = list(session.calls), list(session.keeps)
    with pytest.raises((VendorBatchStopped, ValueError)):
        OrderLedger(path, (directory / "create.json").read_bytes(), CHARACTER, resume=True)
    assert session.calls == calls and session.keeps == keeps


def test_paused_job_drains_observation_before_resuming(tmp_path):
    store, session, record = setup(tmp_path, 1)
    count = [0]
    def pause():
        count[0] += 1
        if count[0] == 1:
            store.request(record["job_id"], "pause")
            session.recorder.append(session.state.slots[0].item, session.counts[0] - 1)
        elif count[0] == 2:
            assert not session.recorder.records and not session.keeps
            store.request(record["job_id"], "run")
    session.after_sleep = pause
    assert run(store, session, record)["state"] == "complete"
    assert session.renewals >= 1


def test_stop_after_queue_retains_orders_and_proves_native_idle(tmp_path):
    store, session, record = setup(tmp_path, 1)
    session.after_sleep = lambda: store.request(record["job_id"], "stop")
    result = run(store, session, record)
    assert result["state"] == "stopped" and len(session.calls) == 1 and not session.keeps
    assert session.state.slots[0].item and session.counts == (10,)
    require_order_handoff_idle(store, session, result)


@pytest.mark.parametrize("field,value", [
    ("order_sha256", "0" * 64), ("planned_items", 7), ("order_spec", SPEC.recipe.as_dict()),
])
def test_saved_quantity_job_cannot_change_its_intent(tmp_path, field, value):
    store, session, record = setup(tmp_path)
    record[field] = value
    store.save(record)
    with pytest.raises(ValueError):
        store.current()
    assert not session.calls and not session.keeps
