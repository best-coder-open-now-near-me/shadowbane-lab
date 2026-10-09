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


def control(ledger, enabled=True, revision=0, **overrides):
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
    assert ledger.inspect_preparation_control(CLIENT_ID, INSTANCE_ID) is None


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
