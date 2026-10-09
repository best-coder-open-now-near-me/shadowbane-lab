"""Dashboard status correlates async preparation with a subsequent health read."""

from dataclasses import replace
from types import SimpleNamespace

import test_manager_application as fixtures
from test_pve_status import progress

from shadowbane_lab.manager.operation import WorkerOperationLedger
from shadowbane_lab.manager.preparation_service import PreparationServiceSnapshot
from shadowbane_lab.manager.preparation_status import WorkerPreparationStatus
from shadowbane_lab.manager.worker import (
    WorkerHealthState,
    WorkerHeartbeat,
    WorkerRuntimeState,
    WorkerSlotHealthSnapshot,
)


def setup_status(tmp_path, monkeypatch):
    now = 100.0
    monkeypatch.setattr('shadowbane_lab.manager.preparation_status.time.time', lambda: now)
    client = fixtures._client('client-exact', 101)
    client_id = 'client-01'
    manifest = fixtures._manifest()
    ledger = WorkerOperationLedger(manifest, tmp_path)
    heartbeat = WorkerHeartbeat(
        fixtures.NODE_ID, client_id, client.instance_id, 'worker-' + '1' * 32,
        201, 2001, 2, now, WorkerRuntimeState.RUNNING, True, False,
    )
    preparation = progress().preparation
    preparation = replace(preparation, actor=replace(
        preparation.actor, process_id=client.process_id,
        process_creation=client.process_started_at_100ns,
    ))
    record = WorkerPreparationStatus(heartbeat, PreparationServiceSnapshot(
        'maintaining', 1, preparation,
    ))
    ledger.publish_preparation_status(record)
    session = fixtures._RecordingSession(fixtures.ManagerSessionSnapshot(
        node_id=fixtures.NODE_ID,
        slots=(fixtures._slot(client_id, instance_id=client.instance_id),),
    ))
    application, _ = fixtures._application(session, client, operation_status=ledger)
    return application, ledger, record


def health(heartbeat):
    return WorkerSlotHealthSnapshot(
        client_id=heartbeat.client_id, state=WorkerHealthState.HEALTHY,
        dispatch_allowed=True, active_worker_count=1, heartbeat=heartbeat,
    )


def test_new_preparation_published_during_health_read_does_not_hide_current_buffs(
    tmp_path, monkeypatch,
):
    application, ledger, record = setup_status(tmp_path, monkeypatch)
    next_record = replace(record, heartbeat=replace(record.heartbeat, sequence=3))
    calls = []

    def inspect(*args, **kwargs):
        calls.append(kwargs)
        # Health captured sequence 2; the asynchronous reporter publishes 3
        # before this call returns. Reading preparation afterward creates a
        # false "future record" despite one unchanged healthy worker lifetime.
        ledger.publish_preparation_status(next_record)
        return health(record.heartbeat)

    application._worker_supervisor = SimpleNamespace(inspect=inspect)
    slot = application.status()['slots'][0]
    assert slot['worker']['heartbeat']['sequence'] == 2
    assert ledger.inspect_preparation_status(record.heartbeat.client_id).heartbeat.sequence == 3
    assert slot['automatic_buffs']['state'] == 'maintaining'
    assert slot['automatic_buffs']['current'] is True
    assert slot['automatic_buffs']['preparation']['groups'][0]['coverage'] == 'present'
    assert len(calls) == 1 and calls[0]['renew_permit'] is False


def test_worker_replacement_between_reads_never_inherits_previous_coverage(tmp_path, monkeypatch):
    application, ledger, record = setup_status(tmp_path, monkeypatch)
    replacement = replace(record, heartbeat=replace(
        record.heartbeat, worker_id='worker-' + '2' * 32,
        process_id=202, process_started_at_100ns=2002, sequence=1,
    ))
    calls = []

    def inspect(*args, **kwargs):
        if not calls:
            ledger.publish_preparation_status(replacement)
        calls.append(kwargs)
        return health(replacement.heartbeat)

    application._worker_supervisor = SimpleNamespace(inspect=inspect)
    first = application.status()['slots'][0]
    assert first['worker']['heartbeat']['worker_id'] == replacement.heartbeat.worker_id
    assert first['automatic_buffs'] == dict(
        state='unavailable', current=False, preparation=None, detail=None,
    )
    second = application.status()['slots'][0]
    assert second['automatic_buffs']['state'] == 'maintaining'
    assert second['automatic_buffs']['current'] is True
    assert len(calls) == 2 and all(c['renew_permit'] is False for c in calls)
