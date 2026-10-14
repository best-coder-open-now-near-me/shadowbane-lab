import copy
import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_completion import _read_record
from shadowbane_lab.client_extension.vendor_order_ledger import LIMIT
from shadowbane_lab.client_extension.vendor_order_ledger import OrderLedger
from shadowbane_lab.client_extension.vendor_wire import UNRESOLVED
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from shadowbane_lab.manager.vendor_job import run_vendor_job
from shadowbane_lab.manager.vendor_order_job import run_order_job
from shadowbane_lab.manager.vendor_review_recovery import (
    resume_review,
    retain_review_capture,
    review_job_ready,
)
from tests.test_manager_vendor_orders import run, setup


def fail_batch(tmp_path, capacity=7):
    store, session, record = setup(tmp_path, capacity)
    with pytest.raises(NativeVendorDialogCaptureError):
        run_order_job(store, session, record, clock=lambda: session.time, sleeper=session.sleep,
                      reader_factory=lambda *args: session.recorder,
                      inventory_reader=lambda *args: (_ for _ in ()).throw(
                          NativeVendorDialogCaptureError("vendor queue changed during observation"))
                      )
    assert len(session.calls) == 1 and store.current()["state"] == "review"
    directory = store.directory(record["job_id"])
    initial = json.loads((directory / "create.json").read_bytes())["production_records"]
    return store, session, record, initial


def capture(session, records):
    first = dict(kind="started", schema_version=3, process_id=session.identity.process_id,
                 creation=session.identity.creation_filetime_utc, native_commands_sent=0)
    last = dict(kind="records", missed=0, sequence=records[-1]["sequence"], records=records,
                rejected=0, ticket_drops=0, overwritten=max(0, records[-1]["sequence"] - 256))
    return b"".join((json.dumps(r) + "\n").encode() for r in (first, last))


def test_review_continues_same_seventy_item_batch_without_create_or_funding_replay(tmp_path):
    store, session, record, original = fail_batch(tmp_path)
    assert not store.summary()["can_reconcile"]
    # The server keeps producing after the host observation failure. This
    # independent capture retains the same causal replies, never item guesses.
    for _ in range(2):
        session.sleep(.5)
    raw = capture(session, original + session.recorder.records)
    receipt = retain_review_capture(store, record["job_id"], raw)
    assert receipt["creates"] == receipt["keeps"] == receipt["funds_moved"] == 0
    assert store.summary()["can_reconcile"]
    store.request(record["job_id"], "run")
    session.recorder.drain()  # New live reader begins at the retained archive cursor.
    def runner(store, native, current, **kwargs):
        return run(store, native, current)
    with patch("shadowbane_lab.manager.vendor_order_job.run_order_job", side_effect=runner):
        result = run_vendor_job(store, session, 1000, resume=True)
    assert result["state"] == "complete" and result["kept"] == result["created"] == 70
    assert len(session.calls) == 1 and len(session.keeps) == 7
    path, = (store.directory(record["job_id"]) / "review-continuations").glob("*.json")
    retained = json.loads(path.read_bytes())
    assert retained["prior_job"]["state"] == "review"
    assert retained["state"] == "observations_retained" and retained["creates"] == 0


@pytest.mark.parametrize("fault", ["gap", "drop", "lifetime", "counter", "extra_create"])
def test_recovery_rejects_incomplete_or_unrelated_passive_history(tmp_path, fault):
    store, session, record, original = fail_batch(tmp_path)
    session.sleep(.5)
    raw = capture(session, original + session.recorder.records)
    lines = [json.loads(line) for line in raw.splitlines()]
    if fault == "gap":
        lines[1]["records"].pop(0)
    elif fault == "drop":
        lines[1]["ticket_drops"] = 1
    elif fault == "lifetime":
        lines[0]["creation"] += 1
    elif fault == "counter":
        lines[1]["sequence"] += 1
    else:
        extra = copy.deepcopy(original[0])
        extra["sequence"] = lines[1]["sequence"] + 1
        lines[1]["records"].append(extra)
        lines[1]["sequence"] += 1
    raw = b"".join((json.dumps(line) + "\n").encode() for line in lines)
    with pytest.raises((VendorBatchStopped, ValueError)):
        retain_review_capture(store, record["job_id"], raw)
    assert len(session.calls) == 1 and not session.keeps
    assert store.current()["state"] == "review" and not store.summary()["can_reconcile"]


@pytest.mark.parametrize("fault", ["pending_keep", "changed_admission", "unfinished_menu",
                                   "changed_progress", "native_unresolved", "owner_changed"])
def test_recovery_never_erases_uncertain_actions_or_changed_ownership(tmp_path, fault):
    store, session, record, original = fail_batch(tmp_path, 1)
    directory = store.directory(record["job_id"])
    progress = directory / "order-progress.json"
    if fault in {"pending_keep", "changed_admission", "unfinished_menu"}:
        path = (progress if fault == "pending_keep" else directory / "create.json"
                if fault == "changed_admission" else directory / "order-inventory-menu.json")
        data = json.loads(_read_record(path, LIMIT))
        if fault == "pending_keep":
            data["requests"].append(dict(request_key="11111111-2222-4333-8444-555555555555",
                                         state="prepared", item_id=101))
        else:
            data["state"] = "review"
        path.write_text(json.dumps(data))
        with pytest.raises((VendorBatchStopped, ValueError)):
            retain_review_capture(store, record["job_id"], capture(session, original))
    else:
        retain_review_capture(store, record["job_id"], capture(session, original))
        if fault == "changed_progress":
            data = json.loads(_read_record(progress, LIMIT))
            data["events"].append(dict(kind="unknown"))
            progress.write_text(json.dumps(data))
        elif fault == "native_unresolved":
            inspect = session.inspect_orders
            session.inspect_orders = lambda: replace(inspect(), flags=UNRESOLVED)
        else:
            session.state = replace(session.state, building=999)
        with pytest.raises((VendorBatchStopped, ValueError)):
            resume_review(store, session, store.current())
    assert len(session.calls) == 1 and not session.keeps


def test_retained_capture_and_continuation_are_single_use_and_do_not_extend_deadline(tmp_path):
    store, session, record, original = fail_batch(tmp_path, 1)
    deadline = record["deadline_at"]
    raw = capture(session, original) + b'{"partial_live_append":'
    retain_review_capture(store, record["job_id"], raw)
    with pytest.raises(VendorBatchStopped, match="exist"):
        retain_review_capture(store, record["job_id"], raw)
    review_job_ready(store, record)
    resume_review(store, session, record)
    assert store.current()["deadline_at"] == deadline
    assert len(session.calls) == 1 and not session.keeps
    record["state"] = "review"
    store.save(record)
    with pytest.raises(VendorBatchStopped):
        resume_review(store, session, record)


def test_missing_progress_never_creates_a_new_journal_during_summary_or_recovery(tmp_path):
    store, session, record, original = fail_batch(tmp_path, 1)
    path = store.directory(record["job_id"]) / "order-progress.json"
    path.unlink()
    assert not store.summary()["can_reconcile"] and not path.exists()
    with pytest.raises(VendorBatchStopped, match="missing"):
        retain_review_capture(store, record["job_id"], capture(session, original))
    assert not path.exists() and len(session.calls) == 1 and not session.keeps


def legacy_missing_receipt(tmp_path):
    store, session, record, original = fail_batch(tmp_path, 2)
    retain_review_capture(store, record["job_id"], capture(session, original))
    resume_review(store, session, record)
    directory = store.directory(record["job_id"])
    # The installed .118 layout used one fixed filename. Preserve and read it.
    for folder, legacy in (("review-observations", "review-observation.json"),
                           ("review-continuations", "review-continuation.json")):
        source, = (directory / folder).glob("*.json")
        source.rename(directory / legacy)

    def old_failure(ledger, request, observed):
        request["state"] = "observed"
        raise VendorBatchStopped("native quantity Keep did not prove inventory presence")
    with patch.object(OrderLedger, "kept", old_failure):
        with pytest.raises(VendorBatchStopped, match="inventory presence"):
            run(store, session, store.current())
    progress = json.loads((directory / "order-progress.json").read_bytes())
    records = list(original)
    for event in progress["events"]:
        if event["kind"] == "received":
            records.extend(event["records"])
    records.extend(session.recorder.records)
    old_inspect = session.inspect_orders
    session.inspect_orders = lambda: replace(old_inspect(), transition_item=session.last_transition[0],
                                             transition_request=session.last_transition[1])
    return store, session, capture(session, records)


@pytest.mark.parametrize("fault", [None, "transition", "item", "unresolved", "unfinished_prior"])
def test_legacy_observed_keep_requires_exact_native_receipt_and_never_replays(tmp_path, fault):
    store, session, raw = legacy_missing_receipt(tmp_path)
    record = store.current()
    directory = store.directory(record["job_id"])
    before = (directory / "order-progress.json").read_bytes()
    if fault == "unfinished_prior":
        path = directory / "review-continuation.json"
        prior = json.loads(path.read_bytes())
        prior["state"] = "prepared"
        path.write_text(json.dumps(prior))
        with pytest.raises(VendorBatchStopped, match="unfinished"):
            retain_review_capture(store, record["job_id"], raw)
        assert (directory / "order-progress.json").read_bytes() == before
        return
    retained = retain_review_capture(store, record["job_id"], raw)
    assert retained["keeps"] == 0 and store.summary()["can_reconcile"]
    inspect = session.inspect_orders
    if fault == "transition":
        session.inspect_orders = lambda: replace(inspect(), transition_request="11111111-2222-4333-8444-555555555555")
    elif fault == "item":
        session.inspect_orders = lambda: replace(inspect(), transition_item=999)
    elif fault == "unresolved":
        session.inspect_orders = lambda: replace(inspect(), flags=UNRESOLVED)
    if fault:
        with pytest.raises(VendorBatchStopped):
            resume_review(store, session, record)
        assert (directory / "order-progress.json").read_bytes() == before
        assert len(session.keeps) == 1 and len(session.calls) == 1
        return
    deadline = record["deadline_at"]
    resume_review(store, session, record)
    session.recorder.drain()
    result = run(store, session, store.current())
    assert result["state"] == "complete" and result["kept"] == 20
    assert len(session.keeps) == len(set(session.keeps)) == 2 and len(session.calls) == 1
    assert result["deadline_at"] == deadline
    assert (directory / "review-continuation.json").exists()
    assert len(list((directory / "review-continuations").glob("*.json"))) == 1


def test_manager_and_exact_worker_continue_review_without_funder_or_collector(tmp_path):
    import threading

    from shadowbane_lab.client_extension.vendor_budget import VendorBatchBudget
    from shadowbane_lab.manager.operation import WorkerOperationState
    from shadowbane_lab.manager.vendor_control import VendorWorkerExecutor
    from shadowbane_lab.manager.worker_runtime import ExactClientWorkerBinding
    from tests.test_manager_operation import CLIENT_ID, INSTANCE_ID, NODE_ID, WORKER_ID
    from tests.test_manager_vendor_control import VendorControlTests
    from tests.test_manager_vendor_orders import Session
    from tests.test_manager_vendor_recipes import OWNER
    from tests.test_vendor_order_batch import SPEC

    test = VendorControlTests()
    test.setUp()
    try:
        store, session = test.store, Session(test.store, 7)
        budget = VendorBatchBudget.from_snapshot(session.state, {555: 1660})
        selection = dict(recipe_spec=SPEC.recipe.as_dict(), revision="a" * 32, owner=OWNER,
                         building=dict(object_id=session.state.building),
                         vendor=dict(object_id=session.state.vendor), display_name="Gilded Scepter",
                         admission_snapshot=session.state.encode().hex(),
                         batch_budget=budget.as_dict(), batch_budget_sha256=budget.canonical_digest,
                         order_spec=SPEC.as_dict(), order_sha256=SPEC.canonical_digest)
        record = store.begin(session, 1000, 0, selection=selection)
        with pytest.raises(NativeVendorDialogCaptureError):
            run_order_job(store, session, record, clock=lambda: session.time, sleeper=session.sleep,
                          reader_factory=lambda *args: session.recorder,
                          inventory_reader=lambda *args: (_ for _ in ()).throw(
                              NativeVendorDialogCaptureError("observation changed")))
        original = json.loads((store.directory(record["job_id"]) / "create.json").read_bytes())
        raw = capture(session, original["production_records"])
        retain_review_capture(store, record["job_id"], raw)
        test.control.execute("vendor-resume", CLIENT_ID, INSTANCE_ID, job_id=record["job_id"])
        pending = test.operations.inspect_slot(CLIENT_ID)
        assert len(pending) == 1
        assert pending[0].operation.command == "vendor resume " + record["job_id"]
        binding = ExactClientWorkerBinding(CLIENT_ID, INSTANCE_ID, 988, 1234567, 1000, WORKER_ID)
        def forbidden(*args, **kwargs):
            pytest.fail("recovery must not collect or fund")
        worker = VendorWorkerExecutor(test.root, NODE_ID, binding,
                                      session_factory=lambda _: session,
                                      recipe_reader=session.reader, funding_runner=forbidden,
                                      collection_runner=forbidden)
        with patch("shadowbane_lab.manager.vendor_order_job.run_order_job",
                   side_effect=lambda store, native, record, **kwargs: run(store, native, record)):
            result = worker.execute(pending[0].operation, stop_signal=threading.Event())
        assert result.state == WorkerOperationState.SUCCEEDED
        assert len(session.calls) == 1 and len(session.keeps) == 7
    finally:
        test.doCleanups()
