import copy
import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_recycle_evidence import IMAGE
from shadowbane_lab.client_extension.vendor_recycle_manifest import batch_fingerprint
from shadowbane_lab.client_extension.vendor_wire import (
    IN_FLIGHT,
    READY,
    NativeRecycleCompletion,
    Outcome,
)
from shadowbane_lab.client_observation.native_vendor_queue import NativeVendorObservationChanged
from shadowbane_lab.manager.vendor_recycling import (
    POLICY,
    finish_exclusions,
    require_recycling_idle,
)
from tests.test_vendor_automatic_replies import CHARACTER, reply, send
from tests.test_vendor_batch import receipt, snapshot
from tests.test_vendor_recycle_manifest import item


class Store:
    mode = "run"

    def __init__(self, root):
        self.root = root

    def directory(self, job):
        return self.root / job

    def control(self, job):
        return self.mode


class Reader:
    def __init__(self, session):
        self.session, self.last = session, session.sequence

    def cursor(self):
        return dict(process_id=988, creation=1234567, sequence=self.last,
                    overwritten=max(0, self.last - 256), rejected=0, ticket_drops=0,
                    capture_incomplete=False, read_errors=0)

    def bookmark(self):
        return dict(cursor=self.cursor(), command_admitted=False)

    def drain(self):
        records = [r for r in self.session.history if r["sequence"] > self.last]
        if records:
            self.last = records[-1]["sequence"]
        return dict(records=copy.deepcopy(records), cursor=self.cursor(),
                    capture_incomplete=self.session.incomplete)


class Session:
    identity = SimpleNamespace(process_id=988, creation_filetime_utc=1234567)
    window = 1000
    incomplete = lost_submission = wrong_gold = wrong_native_floor = False
    focused = True

    def __init__(self, store, count):
        self.store = store
        self.state = replace(snapshot(), inventory=900)
        self.rows = [item(i) for i in range(count)]
        self.time, self.gold = 0, 205328
        self.sequence, self.history = 657, []
        self.calls, self.renewals, self.observations = [], 0, 0
        self.pending = self.transition = None
        self.completion = NativeRecycleCompletion(0, 0, 0, 0)
        self.before_observation = lambda: None
        self.after_sleep = lambda: None

    def context(self):
        return SimpleNamespace(initial=self.state, sequence=self.sequence)

    def append(self, records):
        self.history.extend(records)
        self.sequence = records[-1]["sequence"]

    def inspect_recycle(self):
        if self.pending:
            key, batch, floor = self.pending
            for _ in range(2):
                self.append(reply(self.context(), 7, fields=4, strongbox_gold=self.gold))
            self.gold += batch.refund
            self.append(reply(self.context(), 7, fields=4,
                              strongbox_gold=self.gold + int(self.wrong_gold),
                              reference_list_raw=[[i, 40] for i in reversed(batch.items)]))
            self.rows = [row for row in self.rows if row["item"]["object_id"] not in batch.items]
            self.transition = key, len(batch.items)
            self.completion = NativeRecycleCompletion(floor + int(self.wrong_native_floor),
                                                       self.sequence, batch.refund, self.gold)
            self.pending = None
        result = receipt(self.state, str(uuid.uuid4()), flags=READY if self.focused else 0)
        return replace(result, transition_item=self.transition[1] if self.transition else 0,
                       transition_request=self.transition[0] if self.transition else None,
                       recycle_completion=self.completion)

    def recycle(self, expected, key, batch):
        self.calls.append(batch)
        path = self.store.root / ("a" * 32) / "recycling" / f"batch-{len(self.calls)-1:02d}.json"
        intent = json.loads(path.read_text())
        assert intent["state"] == "prepared" and intent["request_key"] == key
        assert expected == self.state and self.focused and not self.pending
        assert batch.gold_before == self.gold
        rows = [row for row in self.rows if row["item"]["object_id"] in batch.items]
        assert batch.fingerprint == batch_fingerprint(rows)
        floor = self.sequence
        self.append(send(self.context(), 3, reference_list_raw=[[i, 40] for i in batch.items]))
        self.pending = key, batch, floor
        if self.lost_submission:
            raise TimeoutError("lost recycle submission result")
        return replace(receipt(expected, key, Outcome.SUBMITTED, IN_FLIGHT),
                       recycle_completion=self.completion)

    def observe(self, native, state):
        assert native is self and state == self.state
        self.observations += 1
        self.before_observation()
        assessment = dict(schema_version=1, record_type="owned_vendor_affix_assessment",
                          process_id=988, process_creation_filetime_utc=1234567,
                          executable_sha256=IMAGE, root=state.root, manager=state.manager,
                          menu=state.menu, building=dict(object_id=state.building, object_type=8),
                          vendor=dict(object_id=state.vendor, object_type=42),
                          scope="displayed_entries", complete_inventory=False,
                          command_admitted=False, strongbox_gold=self.gold,
                          items=copy.deepcopy(self.rows))
        inventory = dict(schema_version=1, record_type="vendor_inventory_snapshot",
                         process_id=988, process_creation_filetime_utc=1234567,
                         executable_sha256=IMAGE, native_window_address=state.root,
                         manager_address=state.manager, menu_address=state.menu,
                         building=assessment["building"], vendor=assessment["vendor"],
                         command_admitted=False,
                         inventory=dict(window_address=state.inventory, scope="displayed_entries",
                                        complete_inventory=False,
                                        items=[copy.deepcopy(row["inventory_row"])
                                               for row in self.rows]))
        return assessment, inventory

    def renew_lease(self):
        self.renewals += 1

    def sleep(self, seconds):
        self.time += seconds
        self.after_sleep()


def setup(tmp_path, count=7):
    store = Store(tmp_path)
    session = Session(store, count)
    eligible = [row["item"]["object_id"] for row in session.rows]
    record = dict(schema_version=5, exclusion_policy=POLICY, job_id="a" * 32,
                  initial_snapshot=session.state.encode().hex(), process_id=988,
                  process_creation_filetime_utc=1234567, window=1000,
                  deadline_at=500, recipe_spec=dict(template=dict(object_id=26990, object_type=0)),
                  recipe_owner=dict(key=list(CHARACTER)), phase="recycling", state="running",
                  kept=count, excluded=0)
    return store, session, record, eligible


def run(store, session, record, eligible, **kwargs):
    return finish_exclusions(store, session, record, eligible,
                             observation_reader=session.observe, reader_factory=Reader,
                             clock=lambda: session.time, sleeper=session.sleep, **kwargs)


def test_one_batch_handles_native_receipt_before_host_drain_without_replaying(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    result = run(store, session, record, eligible)
    assert result["recycled"] == eligible and not result["retained"]
    assert len(session.calls) == 1 and session.gold == 206385 and session.time > 0
    saved = json.loads((store.directory(record["job_id"]) / "recycling/batch-00.json").read_text())
    assert saved["state"] == "observed" and saved["proof"]["server_verified"]
    record.update(state="complete", excluded=7)
    require_recycling_idle(store, session, record)
    assert run(store, session, record, eligible) == result and len(session.calls) == 1


def test_capacity_batch_is_recycled_in_full_bounded_groups_with_fresh_receipts(tmp_path):
    store, session, record, eligible = setup(tmp_path, 70)
    result = run(store, session, record, eligible)
    assert [len(batch.items) for batch in session.calls] == [48, 22]
    assert result["recycled"] == eligible and session.gold == 205328 + 70 * 151


def test_unknown_over_low_tier_and_unrelated_stock_remain_untouched(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    session.rows[0]["assessment"].update(prefix_tier=1, suffix_tier=None,
                                         disposition="keep", reason="unknown_affix_preserved")
    session.rows.append(item(100))  # Old stock is not this job's eligibility set.
    result = run(store, session, record, eligible)
    assert result["retained"] == eligible[:1]
    assert len(session.rows) == 2 and len(session.calls) == 1


def test_all_unknowns_finish_without_a_disposal_or_request_journal(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    for row in session.rows:
        row["assessment"].update(prefix_tier=None, disposition="keep",
                                  reason="unknown_affix_preserved")
    result = run(store, session, record, eligible)
    assert result["retained"] == eligible and session.calls == []
    assert not list((store.directory(record["job_id"]) / "recycling").glob("batch-*.json"))


def test_becoming_unknown_at_final_assessment_protects_the_item(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    def change():
        if session.observations == 2:
            session.rows[0]["assessment"].update(prefix_tier=None, disposition="keep",
                                                 reason="unknown_affix_preserved")
    session.before_observation = change
    result = run(store, session, record, eligible)
    assert result["retained"] == eligible[:1] and len(session.calls[0].items) == 6


@pytest.mark.parametrize("change", ["lost_submission", "wrong_gold", "wrong_native_floor",
                                   "incomplete"])
def test_uncertainty_preserves_the_intent_and_cannot_replay(tmp_path, change):
    store, session, record, eligible = setup(tmp_path)
    setattr(session, change, True)
    with pytest.raises((VendorBatchStopped, TimeoutError)):
        run(store, session, record, eligible)
    assert len(session.calls) == 1
    for flag in ("lost_submission", "wrong_gold", "wrong_native_floor", "incomplete"):
        setattr(session, flag, False)
    with pytest.raises(VendorBatchStopped):
        run(store, session, record, eligible)
    assert len(session.calls) == 1


def test_owner_content_change_is_blocked_before_any_selection_or_disposal(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    def change():
        if session.observations == 2:
            session.rows[0]["inventory_row"]["effects"][0]["token"] += 1
    session.before_observation = change
    with pytest.raises(VendorBatchStopped, match="contents changed"):
        run(store, session, record, eligible)
    assert session.calls == []


def test_focus_pause_deadline_and_stop_do_not_grant_mutation(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    session.focused = False
    session.after_sleep = lambda: setattr(session, "focused", True)
    run(store, session, record, eligible)
    assert session.renewals == 1 and len(session.calls) == 1
    # A separate job stopped before its first gate leaves no action intent.
    store, session, record, eligible = setup(tmp_path / "stopped")
    result = run(store, session, record, eligible, cancelled=lambda: True)
    assert result["state"] == "stopped" and result["retained"] == eligible
    assert session.calls == []
    record["state"] = "stopped"
    require_recycling_idle(store, session, record)
    store, session, record, eligible = setup(tmp_path / "expired")
    record["deadline_at"] = 0
    with pytest.raises(VendorBatchStopped, match="deadline"):
        run(store, session, record, eligible)


def test_atomic_observation_races_retry_without_actions_or_new_requests(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    def race():
        if session.observations <= 2:
            raise NativeVendorObservationChanged("publishing")
    session.before_observation = race
    result = run(store, session, record, eligible)
    assert result["recycled"] == eligible and len(session.calls) == 1


def test_legacy_completed_jobs_cannot_acquire_disposal_authority(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    record["schema_version"] = 4
    with pytest.raises(VendorBatchStopped, match="historical"):
        run(store, session, record, eligible)
    assert session.calls == []


def test_stop_between_batches_reconciles_sent_work_and_releases_without_a_new_send(tmp_path):
    store, session, record, eligible = setup(tmp_path, 70)
    session.after_sleep = lambda: setattr(store, "mode", "stop")
    result = run(store, session, record, eligible)
    assert result["state"] == "stopped" and len(result["recycled"]) == 48
    assert len(result["retained"]) == 22 and len(session.calls) == 1
    record.update(state="stopped", excluded=48)
    require_recycling_idle(store, session, record)
    store.mode = "run"
    with pytest.raises(VendorBatchStopped, match="stopped"):
        run(store, session, record, eligible)
    assert len(session.calls) == 1


def test_changed_completed_plan_and_receipt_are_rejected_without_replay(tmp_path):
    store, session, record, eligible = setup(tmp_path)
    run(store, session, record, eligible)
    path = store.directory(record["job_id"]) / "recycling/batch-00.json"
    value = json.loads(path.read_text())
    value["native_receipt"]["completion"]["refund"] += 1
    path.write_text(json.dumps(value))
    with pytest.raises(VendorBatchStopped):
        run(store, session, record, eligible)
    assert len(session.calls) == 1


def unknown_observation(native, state):
    """Full owned inventory fixture for the existing HTTP/production workflow."""
    observer = object.__new__(Session)
    observer.state, observer.rows = state, []
    observer.observations, observer.gold, observer.before_observation = 0, 205328, lambda: None
    for index, identity in enumerate(sorted(native.inventory)):
        row = item(index)
        row["item"]["object_id"] = identity
        row["template"]["object_id"] = state.item_template
        row["assessment"].update(prefix_tier=None, disposition="keep",
                                  reason="unknown_affix_preserved")
        observer.rows.append(row)
    return observer.observe(observer, state)
