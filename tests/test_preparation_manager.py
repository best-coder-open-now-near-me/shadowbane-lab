import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_manager_application import (
    NODE_ID,
    ClientRegistrySnapshot,
    ManagerSessionSnapshot,
    _client,
    _manifest,
    _RecordingSession,
    _slot,
    _StaticRegistry,
)

from shadowbane_lab.manager.application import ManagerDashboardApplication
from shadowbane_lab.manager.dashboard import DashboardError
from shadowbane_lab.manager.operation import WorkerOperationLedger
from shadowbane_lab.manager.worker import (
    WorkerHealthState,
    WorkerHeartbeat,
    WorkerRuntimeState,
    WorkerSlotHealthSnapshot,
)
from shadowbane_lab.manager.worker_runtime import WorkerActivationSnapshot, WorkerActivationState


def setup(tmp_path):
    manifest = _manifest()
    client = _client("instance-1", 101)
    session = _RecordingSession(ManagerSessionSnapshot(NODE_ID, (
        _slot("client-01", instance_id=client.instance_id), _slot("client-02"))))
    registry = _StaticRegistry(ClientRegistrySnapshot(NODE_ID, (client,)))
    worker = ("worker-" + "1"*32, 1234, 5678)
    heartbeat = WorkerHeartbeat(NODE_ID, "client-01", client.instance_id, *worker,
        4, time.time(), WorkerRuntimeState.RUNNING, True, False)
    health = WorkerSlotHealthSnapshot("client-01", WorkerHealthState.HEALTHY, False, 1, heartbeat)
    supervisor = SimpleNamespace(inspect=Mock(return_value=health), revoke=Mock())
    activation = WorkerActivationSnapshot("client-01", client.instance_id,
        WorkerActivationState.ATTACHED, worker_id=worker[0], worker_process_id=worker[1],
        worker_started_at_100ns=worker[2])
    controller = SimpleNamespace(ensure_started=Mock(), request_stop=Mock(),
        inspect_activation=Mock(return_value=activation), recover_activation=Mock())
    ledger = WorkerOperationLedger(manifest, tmp_path)
    app = ManagerDashboardApplication(manifest, session, registry, supervisor,
        worker_controller=controller, operation_status=ledger)
    return app, ledger, supervisor, controller


def test_explicit_pause_records_instance_latch_without_worker(tmp_path):
    app, ledger, _, controller = setup(tmp_path)
    controller.inspect_activation.side_effect = AssertionError("must not borrow a worker")
    app._execute("pause", client_id="client-01", instance_id="instance-1")
    record = ledger.inspect_preparation_control("client-01", "instance-1")
    assert not record.enabled and record.worker_id is None


def test_resume_requires_current_attached_worker_and_persists_exact_tuple(tmp_path):
    app, ledger, supervisor, _ = setup(tmp_path)
    app._preparation_control("client-01", "instance-1", enabled=False)
    app._preparation_control("client-01", "instance-1", enabled=True)
    record = ledger.inspect_preparation_control("client-01", "instance-1")
    assert record.enabled and record.revision == 2
    assert record.worker_process_id == 1234
    assert supervisor.inspect.call_args.kwargs["renew_permit"] is False


@pytest.mark.parametrize("fault", ["worker", "lifetime", "stale", "instance", "client", "node"])
def test_stale_worker_cannot_resume_instance_control(tmp_path, fault):
    app, ledger, supervisor, _ = setup(tmp_path)
    app._preparation_control("client-01", "instance-1", enabled=False)
    health = supervisor.inspect.return_value
    if fault == "stale":
        health = replace(health, state=WorkerHealthState.STALE)
    else:
        key, value = {"worker": ("worker_id", "worker-"+"2"*32),
                      "lifetime": ("process_started_at_100ns", 9999),
                      "instance": ("instance_id", "other"),
                      "client": ("client_id", "client-02"),
                      "node": ("node_id", "other-node")}[fault]
        health = replace(health, heartbeat=replace(health.heartbeat, **{key: value}))
    supervisor.inspect.return_value = health
    with pytest.raises(DashboardError):
        app._preparation_control("client-01", "instance-1", enabled=True)
    assert not ledger.inspect_preparation_control("client-01", "instance-1").enabled
