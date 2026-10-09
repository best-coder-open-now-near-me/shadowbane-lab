import json
from dataclasses import replace

import pytest
from test_manager_operation import (
    CLIENT_ID,
    INSTANCE_ID,
    WORKER_ID,
    WORKER_PROCESS_ID,
    WORKER_PROCESS_STARTED,
    _manifest,
    _permit,
)

from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationLedgerError,
    WorkerOperationReceipt,
    WorkerOperationState,
    new_worker_operation,
)
from shadowbane_lab.manager.preparation_control import PreparationControl


@pytest.fixture
def ledger(tmp_path):
    return WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100.)


def control(ledger, enabled=True, revision=None, **overrides):
    if revision is None:
        current = ledger.inspect_preparation_control(CLIENT_ID, INSTANCE_ID)
        revision = 0 if current is None else current.revision
    return ledger.set_preparation_enabled(CLIENT_ID, **{
        "instance_id": INSTANCE_ID, "worker_id": WORKER_ID,
        "worker_process_id": WORKER_PROCESS_ID,
        "worker_process_creation": WORKER_PROCESS_STARTED,
        "enabled": enabled, "expected_revision": revision, **overrides,
    })


def stop(ledger, number=1, **overrides):
    permit = replace(_permit(), **overrides)
    operation = new_worker_operation(permit, WorkerOperationKind.STOP, "/stop",
        now=100., operation_id=f"operation-{number:032x}")
    ledger.submit(operation)
    return operation


def test_resume_supersedes_late_old_stop_and_duplicate(ledger):
    old = stop(ledger)
    resumed = control(ledger)
    assert ledger.latch_preparation_stop(old) == resumed
    assert ledger.submit(old).duplicate
    assert ledger.latch_preparation_stop(old) == resumed
    assert ledger.inspect_preparation_control(CLIENT_ID, INSTANCE_ID).enabled


def test_stop_after_resume_is_latched_and_survives_worker_restart(ledger):
    resumed = control(ledger)
    new = stop(ledger)
    stopped = ledger.latch_preparation_stop(new)
    assert not stopped.enabled
    assert stopped.revision == resumed.revision + 1
    assert ledger.latch_preparation_stop(new) == stopped
    # The record is instance intent, not an expiring permit or process-local latch.
    reopened = WorkerOperationLedger(_manifest(), ledger._root, clock=lambda: 100.)
    assert reopened.inspect_preparation_control(CLIENT_ID, INSTANCE_ID) == stopped


def test_resume_includes_terminal_stop_and_cas_rejects_stale_writer(ledger):
    old = stop(ledger)
    ledger.publish_receipt(WorkerOperationReceipt.for_operation(
        old, WorkerOperationState.SUCCEEDED, observed_at=100.1))
    resumed = control(ledger)
    assert old.operation_id in resumed.superseded_stops
    assert ledger.latch_preparation_stop(old) == resumed
    with pytest.raises(WorkerOperationLedgerError, match="changed"):
        control(ledger, False, revision=0)
    assert ledger.inspect_preparation_control(CLIENT_ID, INSTANCE_ID) == resumed


def test_instance_records_do_not_retarget_new_character_slot(ledger):
    old = stop(ledger, instance_id="old-instance")
    current = control(ledger)
    ledger.latch_preparation_stop(old)
    assert ledger.inspect_preparation_control(CLIENT_ID, INSTANCE_ID) == current
    assert not ledger.inspect_preparation_control(CLIENT_ID, "old-instance").enabled


def test_immutable_stop_required(ledger):
    old = stop(ledger)
    with pytest.raises(WorkerOperationLedgerError, match="own"):
        ledger.latch_preparation_stop(replace(old, command="other"))
    assert not ledger.inspect_preparation_control(CLIENT_ID, INSTANCE_ID).enabled


def test_control_is_not_an_operation_and_strictly_round_trips(ledger):
    item = control(ledger)
    assert ledger.inspect_slot(CLIENT_ID) == ()
    assert PreparationControl.loads(json.dumps(item.to_dict())) == item
    with pytest.raises(ValueError, match="duplicate"):
        PreparationControl.loads(json.dumps(item.to_dict())[:-1] + ', "enabled":true}')


@pytest.mark.parametrize("changes", [
    {"enabled": 1}, {"revision": True}, {"worker_process_id": 0},
    {"schema_version": 2}, {"superseded_stops": ("wrong",)},
])
def test_invalid_control_rejected(ledger, changes):
    item = control(ledger)
    with pytest.raises(ValueError):
        replace(item, **changes)


def test_explicit_disabled_intent_does_not_need_an_old_worker_identity(ledger):
    item = control(ledger, False, worker_id=None, worker_process_id=None,
                   worker_process_creation=None)
    assert not item.enabled
    assert PreparationControl.loads(json.dumps(item.to_dict())) == item
    with pytest.raises(ValueError):
        replace(item, enabled=True)
    with pytest.raises(ValueError):
        replace(item, worker_process_id=10)



def test_submit_stop_survives_worker_loss_before_any_callback(ledger):
    operation = stop(ledger)
    recovered = WorkerOperationLedger(_manifest(), ledger._root, clock=lambda: 100.)
    current = recovered.inspect_preparation_control(CLIENT_ID, INSTANCE_ID)
    assert not current.enabled and current.worker_id == operation.worker_id
    resumed = control(recovered, worker_id="worker-"+"2"*32,
                      worker_process_id=9000, worker_process_creation=9001)
    assert resumed.enabled
    assert recovered.latch_preparation_stop(operation) == resumed
    newer = stop(recovered, 2, worker_id="worker-"+"2"*32,
                 process_id=9000, process_started_at_100ns=9001)
    assert not recovered.inspect_preparation_control(CLIENT_ID, INSTANCE_ID).enabled
    assert recovered.latch_preparation_stop(newer).worker_id == newer.worker_id


def test_crash_between_envelope_and_control_publish_is_recovered_before_resume(
        ledger, monkeypatch):
    original = ledger._publish_preparation_control
    def interrupted(*args):
        raise OSError("process ended after envelope persisted")
    monkeypatch.setattr(ledger, "_publish_preparation_control", interrupted)
    with pytest.raises(WorkerOperationLedgerError, match="process ended after envelope persisted"):
        stop(ledger)
    monkeypatch.setattr(ledger, "_publish_preparation_control", original)
    recovered = WorkerOperationLedger(_manifest(), ledger._root, clock=lambda: 100.)
    assert not recovered.inspect_preparation_control(CLIENT_ID, INSTANCE_ID).enabled
    resumed = control(recovered)
    assert resumed.enabled and len(resumed.superseded_stops) == 1
    assert recovered.inspect_preparation_control(CLIENT_ID, INSTANCE_ID) == resumed


def test_crashed_stop_is_reconciled_before_terminal_envelope_is_pruned(ledger, monkeypatch):
    original = ledger._publish_preparation_control
    monkeypatch.setattr(ledger, "_publish_preparation_control",
                        lambda *args: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(WorkerOperationLedgerError):
        stop(ledger)
    monkeypatch.setattr(ledger, "_publish_preparation_control", original)
    operation = ledger.inspect_slot(CLIENT_ID)[0].operation
    ledger.publish_receipt(WorkerOperationReceipt.for_operation(
        operation, WorkerOperationState.SUCCEEDED, observed_at=100.1))
    recovered = WorkerOperationLedger(_manifest(), ledger._root, clock=lambda: 100.)
    assert recovered.prune_terminal(CLIENT_ID, now=1000000.) == 1
    assert recovered.inspect_slot(CLIENT_ID) == ()
    assert not recovered.inspect_preparation_control(CLIENT_ID, INSTANCE_ID).enabled
    assert control(recovered).enabled
