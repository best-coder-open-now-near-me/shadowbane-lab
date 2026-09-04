import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager import (
    ClientInstanceSnapshot,
    ClientRegistrySnapshot,
    ExactClientWorkerBinding,
    ExactClientWorkerRuntime,
    ManagedWorkerController,
    ProcessLifetimeSnapshot,
    SubprocessWorkerLauncher,
    WorkerDispatchPermit,
    WorkerHealthState,
    WorkerHeartbeat,
    WorkerHeartbeatLedger,
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationState,
    WorkerRuntimeState,
    WorkerStopRequest,
    derive_client_instance_id,
    loads_worker_stop_request,
    new_worker_operation,
    parse_manager_manifest,
)
from shadowbane_lab.manager.worker_runtime import _OperationStopSignal

NODE_ID = "gaming-pc-east"
CLIENT_ID = "client-01"
GAME_PROCESS_ID = 101
GAME_PROCESS_STARTED = 133_700_000_000_000_101
GAME_WINDOW_HANDLE = 1001
WORKER_PROCESS_ID = 9001
WORKER_PROCESS_STARTED = 133_700_000_000_009_001
WORKER_ID = "worker-0123456789abcdef0123456789abcdef"


def _manifest():
    return parse_manager_manifest(
        {
            "schema_version": 1,
            "node_id": NODE_ID,
            "clients": [
                {
                    "client_id": CLIENT_ID,
                    "launch": {
                        "executable": r"C:\Games\Shadowbane\launcher.exe",
                        "arguments": ["-windowed"],
                        "working_directory": r"C:\Games\Shadowbane",
                    },
                    "expected_process_directory": r"C:\Games\Shadowbane",
                    "expected_executable_names": ["sb.exe"],
                }
            ],
        }
    )


def _client(
    *,
    process_id: int = GAME_PROCESS_ID,
    process_started_at_100ns: int = GAME_PROCESS_STARTED,
    window_handle: int = GAME_WINDOW_HANDLE,
) -> ClientInstanceSnapshot:
    return ClientInstanceSnapshot(
        node_id=NODE_ID,
        instance_id=derive_client_instance_id(
            NODE_ID,
            process_id,
            process_started_at_100ns,
            window_handle,
        ),
        process_id=process_id,
        process_started_at_100ns=process_started_at_100ns,
        window_handle=window_handle,
        executable_name="sb.exe",
        executable_path=r"C:\Games\Shadowbane\sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(left=0, top=0, width=1280, height=720),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
    )


class _StaticRegistry:
    def __init__(self, *clients: ClientInstanceSnapshot) -> None:
        self.clients = tuple(clients)

    def inspect(self) -> ClientRegistrySnapshot:
        return ClientRegistrySnapshot(node_id=NODE_ID, clients=self.clients)


class _ProcessInspector:
    def __init__(self, *processes: ProcessLifetimeSnapshot) -> None:
        self.processes = {process.process_id: process for process in processes}

    def inspect(self, process_id: int) -> ProcessLifetimeSnapshot | None:
        return self.processes.get(process_id)


class _StopSignal:
    def __init__(self) -> None:
        self.stopped = False

    def is_set(self) -> bool:
        return self.stopped


class _RecordingLauncher:
    def __init__(self) -> None:
        self.bindings: list[ExactClientWorkerBinding] = []

    def launch(self, binding: ExactClientWorkerBinding) -> int:
        self.bindings.append(binding)
        return 7777


class _RecordingOperationExecutor:
    def __init__(self) -> None:
        self.operations = []

    def execute(self, operation, *, stop_signal):
        self.operations.append(operation)
        if operation.kind is WorkerOperationKind.PVE:
            deadline = time.monotonic() + 1.0
            while not stop_signal.is_set() and time.monotonic() < deadline:
                time.sleep(0.005)
            if stop_signal.is_set():
                return WorkerOperationExecution(
                    WorkerOperationState.CANCELLED,
                    "preempted by priority stop",
                )
        return WorkerOperationExecution(
            WorkerOperationState.SUCCEEDED,
            "operation completed",
        )


def _heartbeat(*, instance_id: str, observed_at: float = 100.0) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        node_id=NODE_ID,
        client_id=CLIENT_ID,
        instance_id=instance_id,
        worker_id=WORKER_ID,
        process_id=WORKER_PROCESS_ID,
        process_started_at_100ns=WORKER_PROCESS_STARTED,
        sequence=1,
        observed_at=observed_at,
        runtime_state=WorkerRuntimeState.RUNNING,
        dispatch_ready=True,
        emergency_stop=False,
    )


class ExactClientWorkerRuntimeTests(unittest.TestCase):
    def test_internal_cancel_interrupts_active_engine_operation(self) -> None:
        class PendingCancellationLedger:
            def pending_for(self, **_kwargs):
                return (SimpleNamespace(kind=WorkerOperationKind.CANCEL),)

        signal = _OperationStopSignal(
            _StopSignal(),
            PendingCancellationLedger(),
            ExactClientWorkerBinding.from_client(CLIENT_ID, _client()),
            WORKER_ID,
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )

        self.assertTrue(signal.is_set())

    def test_runtime_publishes_ready_only_while_exact_game_identity_exists(self) -> None:
        manifest = _manifest()
        client = _client()
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        stop = _StopSignal()
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerHeartbeatLedger(manifest, directory)

            runtime = ExactClientWorkerRuntime(
                manifest,
                ExactClientWorkerBinding.from_client(CLIENT_ID, client),
                ledger,
                _StaticRegistry(client),
                _ProcessInspector(worker_process),
                process_id=WORKER_PROCESS_ID,
                sleeper=lambda _seconds: setattr(stop, "stopped", True),
            )

            result = runtime.serve(stop_signal=stop)
            final = ledger.inspect(CLIENT_ID).records[0]

        self.assertEqual(0, result)
        self.assertEqual(WorkerRuntimeState.STOPPED, final.runtime_state)
        self.assertFalse(final.dispatch_ready)
        self.assertFalse(final.emergency_stop)
        self.assertGreaterEqual(final.sequence, 4)

    def test_exact_stop_request_ends_only_its_worker_lifetime_cleanly(self) -> None:
        manifest = _manifest()
        client = _client()
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerHeartbeatLedger(manifest, directory)

            def request_stop(_seconds: float) -> None:
                running = ledger.inspect(CLIENT_ID).records[0]
                ledger.publish_stop_request(
                    WorkerStopRequest(
                        node_id=NODE_ID,
                        client_id=CLIENT_ID,
                        worker_id=running.worker_id,
                        process_id=running.process_id,
                        process_started_at_100ns=running.process_started_at_100ns,
                        requested_at=101.0,
                        reason="operator detached exact client",
                    )
                )

            runtime = ExactClientWorkerRuntime(
                manifest,
                ExactClientWorkerBinding.from_client(CLIENT_ID, client),
                ledger,
                _StaticRegistry(client),
                _ProcessInspector(worker_process),
                process_id=WORKER_PROCESS_ID,
                sleeper=request_stop,
            )

            result = runtime.serve()
            final = ledger.inspect(CLIENT_ID).records[0]

        self.assertEqual(0, result)
        self.assertEqual(WorkerRuntimeState.STOPPED, final.runtime_state)
        self.assertEqual("operator detached exact client", final.detail)

    def test_game_identity_loss_latches_emergency_stop_and_exits(self) -> None:
        manifest = _manifest()
        client = _client()
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerHeartbeatLedger(manifest, directory)
            runtime = ExactClientWorkerRuntime(
                manifest,
                ExactClientWorkerBinding.from_client(CLIENT_ID, client),
                ledger,
                _StaticRegistry(),
                _ProcessInspector(worker_process),
                process_id=WORKER_PROCESS_ID,
                sleeper=lambda _seconds: None,
            )

            result = runtime.serve()
            final = ledger.inspect(CLIENT_ID).records[0]

        self.assertEqual(1, result)
        self.assertEqual(WorkerRuntimeState.STOPPED, final.runtime_state)
        self.assertTrue(final.emergency_stop)
        self.assertIn("no longer uniquely visible", final.detail or "")

    def test_runtime_acknowledges_and_executes_through_exact_worker_gate(self) -> None:
        manifest = _manifest()
        client = _client()
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        stop = _StopSignal()
        executor = _RecordingOperationExecutor()
        sleeps = 0
        operation = None
        with tempfile.TemporaryDirectory() as directory:
            heartbeat_ledger = WorkerHeartbeatLedger(manifest, directory)
            operation_ledger = WorkerOperationLedger(manifest, directory)

            def drive(_seconds: float) -> None:
                nonlocal sleeps, operation
                sleeps += 1
                heartbeat = heartbeat_ledger.inspect(CLIENT_ID).records[0]
                permit = WorkerDispatchPermit(
                    node_id=NODE_ID,
                    client_id=CLIENT_ID,
                    instance_id=client.instance_id,
                    worker_id=heartbeat.worker_id,
                    process_id=heartbeat.process_id,
                    process_started_at_100ns=heartbeat.process_started_at_100ns,
                    heartbeat_sequence=heartbeat.sequence,
                    health_state=WorkerHealthState.HEALTHY,
                    allowed=True,
                    issued_at=time.time(),
                    expires_at=time.time() + 30.0,
                    reason="test manager authorizes exact worker",
                )
                heartbeat_ledger.publish_permit(permit)
                if sleeps == 1:
                    operation = new_worker_operation(
                        permit,
                        WorkerOperationKind.TRAVEL,
                        "/go 120000 60000",
                    )
                    operation_ledger.submit(operation)
                elif sleeps >= 3:
                    stop.stopped = True
                time.sleep(0.01)

            runtime = ExactClientWorkerRuntime(
                manifest,
                ExactClientWorkerBinding.from_client(CLIENT_ID, client),
                heartbeat_ledger,
                _StaticRegistry(client),
                _ProcessInspector(worker_process),
                operation_ledger=operation_ledger,
                operation_executor=executor,
                process_id=WORKER_PROCESS_ID,
                sleeper=drive,
            )

            result = runtime.serve(stop_signal=stop)
            assert operation is not None
            receipt = operation_ledger.inspect_receipt(CLIENT_ID, operation.operation_id)

        self.assertEqual(0, result)
        self.assertEqual([operation], executor.operations)
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(WorkerOperationState.SUCCEEDED, receipt.state)

    def test_priority_stop_preempts_active_operation_then_executes_stop(self) -> None:
        manifest = _manifest()
        client = _client()
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        stop_runtime = _StopSignal()
        executor = _RecordingOperationExecutor()
        sleeps = 0
        pve_operation = None
        stop_operation = None
        with tempfile.TemporaryDirectory() as directory:
            heartbeat_ledger = WorkerHeartbeatLedger(manifest, directory)
            operation_ledger = WorkerOperationLedger(manifest, directory)

            def drive(_seconds: float) -> None:
                nonlocal sleeps, pve_operation, stop_operation
                sleeps += 1
                heartbeat = heartbeat_ledger.inspect(CLIENT_ID).records[0]
                permit = WorkerDispatchPermit(
                    node_id=NODE_ID,
                    client_id=CLIENT_ID,
                    instance_id=client.instance_id,
                    worker_id=heartbeat.worker_id,
                    process_id=heartbeat.process_id,
                    process_started_at_100ns=heartbeat.process_started_at_100ns,
                    heartbeat_sequence=heartbeat.sequence,
                    health_state=WorkerHealthState.HEALTHY,
                    allowed=True,
                    issued_at=time.time(),
                    expires_at=time.time() + 30.0,
                    reason="test manager authorizes exact worker",
                )
                heartbeat_ledger.publish_permit(permit)
                if sleeps == 1:
                    pve_operation = new_worker_operation(
                        permit,
                        WorkerOperationKind.PVE,
                        "/pve",
                    )
                    operation_ledger.submit(pve_operation)
                elif sleeps == 2:
                    stop_operation = new_worker_operation(
                        permit,
                        WorkerOperationKind.STOP,
                        "/stop",
                    )
                    operation_ledger.submit(stop_operation)
                elif sleeps >= 5:
                    stop_runtime.stopped = True
                time.sleep(0.02)

            runtime = ExactClientWorkerRuntime(
                manifest,
                ExactClientWorkerBinding.from_client(CLIENT_ID, client),
                heartbeat_ledger,
                _StaticRegistry(client),
                _ProcessInspector(worker_process),
                operation_ledger=operation_ledger,
                operation_executor=executor,
                process_id=WORKER_PROCESS_ID,
                sleeper=drive,
            )

            result = runtime.serve(stop_signal=stop_runtime)
            assert pve_operation is not None
            assert stop_operation is not None
            pve_receipt = operation_ledger.inspect_receipt(
                CLIENT_ID,
                pve_operation.operation_id,
            )
            stop_receipt = operation_ledger.inspect_receipt(
                CLIENT_ID,
                stop_operation.operation_id,
            )

        self.assertEqual(0, result)
        self.assertEqual(
            [WorkerOperationKind.PVE, WorkerOperationKind.STOP],
            [operation.kind for operation in executor.operations],
        )
        self.assertIsNotNone(pve_receipt)
        self.assertIsNotNone(stop_receipt)
        assert pve_receipt is not None and stop_receipt is not None
        self.assertEqual(WorkerOperationState.CANCELLED, pve_receipt.state)
        self.assertEqual(WorkerOperationState.SUCCEEDED, stop_receipt.state)


class ManagedWorkerControllerTests(unittest.TestCase):
    def test_reuses_exact_live_worker_and_stops_it_by_exact_identity(self) -> None:
        manifest = _manifest()
        client = _client()
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        launcher = _RecordingLauncher()
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerHeartbeatLedger(manifest, directory)
            ledger.publish(_heartbeat(instance_id=client.instance_id))
            controller = ManagedWorkerController(
                manifest,
                ledger,
                _ProcessInspector(worker_process),
                launcher,
                clock=lambda: 101.0,
            )

            self.assertIsNone(controller.ensure_started(CLIENT_ID, client))
            self.assertEqual(1, controller.request_stop(CLIENT_ID, reason="detach requested"))
            request = ledger.inspect_stop_request(CLIENT_ID, WORKER_ID)

        self.assertEqual([], launcher.bindings)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(WORKER_PROCESS_ID, request.process_id)
        self.assertEqual("detach requested", request.reason)

    def test_replaced_instance_is_stopped_before_new_worker_launch(self) -> None:
        manifest = _manifest()
        replacement = _client(
            process_id=202,
            process_started_at_100ns=133_700_000_000_000_202,
            window_handle=2002,
        )
        worker_process = ProcessLifetimeSnapshot(
            WORKER_PROCESS_ID,
            WORKER_PROCESS_STARTED,
        )
        launcher = _RecordingLauncher()
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerHeartbeatLedger(manifest, directory)
            ledger.publish(_heartbeat(instance_id=_client().instance_id))
            controller = ManagedWorkerController(
                manifest,
                ledger,
                _ProcessInspector(worker_process),
                launcher,
                clock=lambda: 101.0,
            )

            process_id = controller.ensure_started(CLIENT_ID, replacement)
            request = ledger.inspect_stop_request(CLIENT_ID, WORKER_ID)

        self.assertEqual(7777, process_id)
        self.assertIsNotNone(request)
        self.assertEqual(1, len(launcher.bindings))
        self.assertEqual(replacement.instance_id, launcher.bindings[0].instance_id)

    def test_stop_request_schema_is_strict_and_round_trips(self) -> None:
        request = WorkerStopRequest(
            node_id=NODE_ID,
            client_id=CLIENT_ID,
            worker_id=WORKER_ID,
            process_id=WORKER_PROCESS_ID,
            process_started_at_100ns=WORKER_PROCESS_STARTED,
            requested_at=100.0,
            reason="graceful stop requested",
        )
        encoded = json.dumps(request.to_dict())

        self.assertEqual(request, loads_worker_stop_request(encoded))
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            loads_worker_stop_request(encoded[:-1] + ', "client_id": "client-01"}')

    def test_subprocess_launcher_uses_separate_tokens_and_never_a_shell(self) -> None:
        client = _client()
        binding = ExactClientWorkerBinding.from_client(CLIENT_ID, client)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = SubprocessWorkerLauncher(
                manifest_path=root / "manager.json",
                worker_state_directory=root / "workers",
                log_directory=root / "logs",
                python_executable=Path(sys.executable),
            )
            with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen") as popen:
                popen.return_value.pid = 7331

                process_id = launcher.launch(binding)

        self.assertEqual(7331, process_id)
        argv = popen.call_args.args[0]
        self.assertIsInstance(argv, tuple)
        self.assertIn("shadowbane_lab.cli", argv)
        self.assertIn(client.instance_id, argv)
        self.assertFalse(popen.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
