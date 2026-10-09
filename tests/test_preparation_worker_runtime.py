import time
from types import SimpleNamespace

from test_manager_worker_runtime import (
    CLIENT_ID,
    NODE_ID,
    WORKER_ID,
    WORKER_PROCESS_ID,
    WORKER_PROCESS_STARTED,
    ProcessLifetimeSnapshot,
    _client,
    _manifest,
    _ProcessInspector,
    _StaticRegistry,
)

from shadowbane_lab.manager.operation import (
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationState,
    new_worker_operation,
)
from shadowbane_lab.manager.worker import (
    WorkerDispatchPermit,
    WorkerHealthState,
    WorkerHeartbeatLedger,
    WorkerHeartbeatPublisher,
)
from shadowbane_lab.manager.worker_runtime import ExactClientWorkerBinding, ExactClientWorkerRuntime


class Service:
    ready = False
    def __init__(self):
        self.releases = []
        self.requests = 0
    def request_handoff(self, *, wait_for_preparation=False):
        self.requests += 1
        return self.ready
    def release_handoff(self, *, cleanup_confirmed):
        self.releases.append(cleanup_confirmed)


def setup(tmp_path, proof):
    manifest, client = _manifest(), _client()
    ledger = WorkerOperationLedger(manifest, tmp_path)
    heartbeats = WorkerHeartbeatLedger(manifest, tmp_path)
    process = ProcessLifetimeSnapshot(WORKER_PROCESS_ID, WORKER_PROCESS_STARTED)
    binding = ExactClientWorkerBinding.from_client(CLIENT_ID, client)
    called = []
    def execute(operation, *, stop_signal):
        called.append(operation)
        return WorkerOperationExecution(WorkerOperationState.SUCCEEDED,
                                       native_cleanup_confirmed=proof)
    runtime = ExactClientWorkerRuntime(manifest, binding, heartbeats,
        _StaticRegistry(client), _ProcessInspector(process), process_id=WORKER_PROCESS_ID,
        operation_ledger=ledger, operation_executor=SimpleNamespace(execute=execute))
    publisher = WorkerHeartbeatPublisher(heartbeats, node_id=NODE_ID, client_id=CLIENT_ID,
        instance_id=client.instance_id, process=process, worker_id=WORKER_ID)
    now = time.time()
    permit = WorkerDispatchPermit(NODE_ID, CLIENT_ID, WorkerHealthState.HEALTHY,
        True, now, now+2, "ready", client.instance_id, WORKER_ID,
        WORKER_PROCESS_ID, WORKER_PROCESS_STARTED, 1)
    operation = new_worker_operation(permit, WorkerOperationKind.PVE, "/pve", now=now)
    ledger.submit(operation)
    service = Service()
    runtime._preparation = service
    return runtime, publisher, ledger, operation, service, called


def test_operation_is_unclaimed_until_positive_preparation_parent_close(tmp_path):
    runtime, publisher, ledger, operation, service, called = setup(tmp_path, True)
    assert runtime._start_next_operation(publisher) is None
    assert not called
    assert ledger.inspect_receipt(CLIENT_ID, operation.operation_id) is None
    service.ready = True
    active = runtime._start_next_operation(publisher)
    active.thread.join(2)
    assert not active.thread.is_alive()
    runtime._complete_active_operation(active)
    assert called == [operation]
    assert service.releases == [True]


def test_success_result_without_native_proof_cannot_resume_maintenance(tmp_path):
    runtime, publisher, _, _, service, _ = setup(tmp_path, False)
    service.ready = True
    active = runtime._start_next_operation(publisher)
    active.thread.join(2)
    runtime._complete_active_operation(active)
    assert service.releases == [False]



def test_shutdown_keeps_heartbeats_past_stop_deadline_until_positive_service_exit(tmp_path):
    runtime, _, _, _, _, _ = setup(tmp_path, True)
    from shadowbane_lab.manager.worker_runtime import WorkerRuntimeState
    calls, elapsed = [], [0.0]
    class Closing:
        stopped = False
        requests = 0
        def request_stop(self):
            self.requests += 1
    service = Closing()
    runtime._preparation = service
    def sleep(seconds):
        elapsed[0] += seconds
        if elapsed[0] >= 10:
            service.stopped = True
    runtime._sleep = sleep
    runtime._stop_preparation(SimpleNamespace(publish=lambda state, **kw: calls.append(state)))
    assert elapsed[0] >= 10
    assert service.requests == 1
    assert len(calls) >= 100
    assert set(calls) == {WorkerRuntimeState.STOPPING}
