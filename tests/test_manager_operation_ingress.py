import tempfile
import unittest

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager import parse_manager_manifest
from shadowbane_lab.manager.model import ClientInstanceSnapshot, ClientRegistrySnapshot
from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerTravelDestination,
)
from shadowbane_lab.manager.operation_ingress import (
    ForegroundWorkerOperationIngress,
    WorkerOperationIngressError,
)
from shadowbane_lab.manager.worker import WorkerDispatchPermit, WorkerHealthState

NODE_ID = "gaming-pc-east"
CLIENT_ID = "client-01"
INSTANCE_ID = "instance-101"
GAME_PROCESS_ID = 701
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
                        "executable": r"C:\Games\Shadowbane\sb.exe",
                        "arguments": [],
                        "working_directory": r"C:\Games\Shadowbane",
                    },
                    "expected_process_directory": r"C:\Games\Shadowbane",
                    "expected_executable_names": ["sb.exe"],
                }
            ],
        }
    )


def _client() -> ClientInstanceSnapshot:
    return ClientInstanceSnapshot(
        node_id=NODE_ID,
        instance_id=INSTANCE_ID,
        process_id=GAME_PROCESS_ID,
        process_started_at_100ns=133_700_000_000_000_701,
        window_handle=81,
        executable_name="sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(0, 0, 1920, 955),
        dpi_scale=1.0,
        is_foreground=True,
        is_visible=True,
        executable_path=r"C:\Games\Shadowbane\sb.exe",
    )


def _permit(*, expires_at: float = 102.0) -> WorkerDispatchPermit:
    return WorkerDispatchPermit(
        node_id=NODE_ID,
        client_id=CLIENT_ID,
        instance_id=INSTANCE_ID,
        worker_id=WORKER_ID,
        process_id=9_001,
        process_started_at_100ns=133_700_000_000_009_001,
        heartbeat_sequence=4,
        health_state=WorkerHealthState.HEALTHY,
        allowed=True,
        issued_at=99.0,
        expires_at=expires_at,
        reason="exact worker is healthy",
    )


class _Registry:
    def __init__(self, clients: tuple[ClientInstanceSnapshot, ...]) -> None:
        self.clients = clients

    def inspect(self) -> ClientRegistrySnapshot:
        return ClientRegistrySnapshot(node_id=NODE_ID, clients=self.clients)


class _Permits:
    def __init__(self, permit: WorkerDispatchPermit | None) -> None:
        self.permit = permit

    def inspect_permit(self, client_id: str) -> WorkerDispatchPermit | None:
        if client_id != CLIENT_ID:
            return None
        return self.permit


class ForegroundWorkerOperationIngressTests(unittest.TestCase):
    def test_dispatch_resolves_guarded_foreground_lifetime_to_exact_worker(self) -> None:
        manifest = _manifest()
        destination = WorkerTravelDestination(106_662.0, 52_432.0, 8.0)
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerOperationLedger(manifest, directory)
            ingress = ForegroundWorkerOperationIngress(
                manifest,
                _Registry((_client(),)),
                _Permits(_permit()),
                ledger,
                clock=lambda: 100.0,
                acknowledgement_timeout_seconds=0.01,
            )

            dispatch = ingress.dispatch(
                WorkerOperationKind.TRAVEL,
                "/go 106662 52432",
                destination=destination,
                expected_process_id=GAME_PROCESS_ID,
            )

            snapshots = ledger.inspect_slot(CLIENT_ID)

        self.assertEqual(CLIENT_ID, dispatch.operation.client_id)
        self.assertEqual(INSTANCE_ID, dispatch.operation.instance_id)
        self.assertEqual(WORKER_ID, dispatch.operation.worker_id)
        self.assertEqual(destination, dispatch.operation.destination)
        self.assertIsNone(dispatch.acknowledgement)
        self.assertFalse(dispatch.duplicate)
        self.assertEqual((dispatch.operation,), tuple(item.operation for item in snapshots))

    def test_dispatch_rejects_mismatched_guard_and_expired_permit(self) -> None:
        manifest = _manifest()
        with tempfile.TemporaryDirectory() as directory:
            ledger = WorkerOperationLedger(manifest, directory)
            mismatched = ForegroundWorkerOperationIngress(
                manifest,
                _Registry((_client(),)),
                _Permits(_permit()),
                ledger,
                clock=lambda: 100.0,
                acknowledgement_timeout_seconds=0.01,
            )
            with self.assertRaisesRegex(WorkerOperationIngressError, "guarded process"):
                mismatched.dispatch(
                    WorkerOperationKind.STOP,
                    "/stop",
                    expected_process_id=GAME_PROCESS_ID + 1,
                )

            expired = ForegroundWorkerOperationIngress(
                manifest,
                _Registry((_client(),)),
                _Permits(_permit(expires_at=100.0)),
                ledger,
                clock=lambda: 100.0,
                acknowledgement_timeout_seconds=0.01,
            )
            with self.assertRaisesRegex(WorkerOperationIngressError, "not currently valid"):
                expired.dispatch(
                    WorkerOperationKind.PVE,
                    "/pve",
                    expected_process_id=GAME_PROCESS_ID,
                )


if __name__ == "__main__":
    unittest.main()
