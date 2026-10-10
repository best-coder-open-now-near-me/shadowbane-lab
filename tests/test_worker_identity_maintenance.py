"""Real worker-loop checks of discovery isolation and immutable identity loss."""
import threading
import time

import pytest
from test_manager_worker_runtime import (
    CLIENT_ID,
    NODE_ID,
    WORKER_PROCESS_ID,
    WORKER_PROCESS_STARTED,
    _client,
    _manifest,
    _ProcessInspector,
    _StaticRegistry,
    _StopSignal,
)

from shadowbane_lab.manager import (
    ExactClientWorkerBinding,
    ExactClientWorkerRuntime,
    ProcessLifetimeSnapshot,
    WorkerDispatchPermit,
    WorkerHealthState,
    WorkerHeartbeatLedger,
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationState,
    new_worker_operation,
)


@pytest.mark.parametrize('failure', [None, 'window', 'process', 'unknown'])
def test_maintenance_never_reenters_discovery_and_identity_loss_stops_it(tmp_path, failure):
    client, manifest = _client(), _manifest()
    binding = ExactClientWorkerBinding.from_client(CLIENT_ID, client)
    process = ProcessLifetimeSnapshot(WORKER_PROCESS_ID, WORKER_PROCESS_STARTED)
    heartbeats = WorkerHeartbeatLedger(manifest, tmp_path)
    ledger = WorkerOperationLedger(manifest, tmp_path)
    stop = _StopSignal()
    entered = threading.Event()
    now = 0.0
    operation = None
    maintained = []

    class Registry(_StaticRegistry):
        calls = 0
        def inspect(self):
            self.calls += 1
            assert self.calls == 1, 'Slow desktop discovery entered the lease path'
            return super().inspect()

    class Guard:
        closed = False
        checks = 0
        def require_current(self):
            self.checks += 1
            assert not self.closed
            if failure and now >= .5:
                if failure == 'unknown':
                    raise OSError('exact game inspection unavailable')
                raise RuntimeError('exact ' + failure + ' changed')
        def close(self):
            assert not self.closed
            self.closed = True

    registry, guard = Registry(client), Guard()

    class Executor:
        def execute(self, current, *, stop_signal):
            entered.set()
            deadline = time.monotonic() + 5
            while not stop_signal.is_set() and time.monotonic() < deadline:
                time.sleep(.002)
            assert stop_signal.is_set(), 'Worker failed to stop the test operation'
            return WorkerOperationExecution(WorkerOperationState.CANCELLED)

    def drive(delay):
        nonlocal now, operation
        now += delay
        heartbeat = heartbeats.inspect(CLIENT_ID).records[0]
        stamp = time.time()
        permit = WorkerDispatchPermit(
            node_id=NODE_ID, client_id=CLIENT_ID, instance_id=client.instance_id,
            worker_id=heartbeat.worker_id, process_id=heartbeat.process_id,
            process_started_at_100ns=heartbeat.process_started_at_100ns,
            heartbeat_sequence=heartbeat.sequence, health_state=WorkerHealthState.HEALTHY,
            allowed=True, issued_at=stamp, expires_at=stamp + 30, reason='test grant',
        )
        heartbeats.publish_permit(permit)
        if operation is None:
            operation = new_worker_operation(permit, WorkerOperationKind.TRAVEL, '/go 1 2')
            ledger.submit(operation)
        if now >= 1.25:
            stop.stopped = True

    def maintain(current, signal):
        assert entered.wait(5)
        assert current == operation and not signal.is_set()
        maintained.append(now)

    def factory(current):
        assert current == binding and registry.calls == 1
        return guard

    runtime = ExactClientWorkerRuntime(
        manifest, binding, heartbeats, registry, _ProcessInspector(process),
        game_identity_guard_factory=factory, operation_ledger=ledger,
        operation_executor=Executor(), operation_maintenance=maintain,
        process_id=WORKER_PROCESS_ID, heartbeat_interval_seconds=1,
        monotonic_clock=lambda: now, sleeper=drive,
    )
    result = runtime.serve(stop_signal=stop)
    assert result == (1 if failure else 0)
    assert maintained == ([.25] if failure else [.25, .5, .75, 1.0])
    assert registry.calls == 1 and guard.closed
    final = heartbeats.inspect(CLIENT_ID).records[0]
    assert final.emergency_stop is bool(failure)
    if failure:
        assert ('unavailable' if failure == 'unknown' else 'changed') in final.detail


def test_bootstrap_rejection_never_opens_guard_or_starts_owner(tmp_path):
    from unittest.mock import Mock
    client, manifest = _client(), _manifest()
    factory, initialize, prepare = Mock(), Mock(), Mock()
    runtime = ExactClientWorkerRuntime(
        manifest, ExactClientWorkerBinding.from_client(CLIENT_ID, client),
        WorkerHeartbeatLedger(manifest, tmp_path), _StaticRegistry(),
        _ProcessInspector(ProcessLifetimeSnapshot(WORKER_PROCESS_ID, WORKER_PROCESS_STARTED)),
        game_identity_guard_factory=factory, operation_initializer=initialize,
        preparation_factory=prepare, process_id=WORKER_PROCESS_ID,
    )
    assert runtime.serve() == 1
    factory.assert_not_called()
    initialize.assert_not_called()
    prepare.assert_not_called()


def test_invalid_initial_guard_closes_before_native_initialization(tmp_path):
    from unittest.mock import Mock
    client, manifest = _client(), _manifest()
    guard = Mock()
    guard.require_current.side_effect = OSError("game identity unavailable")
    initialize, prepare = Mock(), Mock()
    runtime = ExactClientWorkerRuntime(
        manifest, ExactClientWorkerBinding.from_client(CLIENT_ID, client),
        WorkerHeartbeatLedger(manifest, tmp_path), _StaticRegistry(client),
        _ProcessInspector(ProcessLifetimeSnapshot(WORKER_PROCESS_ID, WORKER_PROCESS_STARTED)),
        game_identity_guard_factory=lambda binding: guard, operation_initializer=initialize,
        preparation_factory=prepare, process_id=WORKER_PROCESS_ID,
    )
    assert runtime.serve() == 1
    guard.require_current.assert_called_once_with()
    guard.close.assert_called_once_with()
    initialize.assert_not_called()
    prepare.assert_not_called()
