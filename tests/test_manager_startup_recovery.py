import unittest

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager.manifest import parse_manager_manifest
from shadowbane_lab.manager.model import ClientInstanceSnapshot, ClientRegistrySnapshot
from shadowbane_lab.manager.startup_recovery import recover_manager_bindings
from shadowbane_lab.manager.worker import (
    WorkerHeartbeat,
    WorkerLedgerSnapshot,
    WorkerRuntimeState,
)

NODE_ID = "gaming-pc-east"


def _manifest():
    return parse_manager_manifest(
        {
            "schema_version": 1,
            "node_id": NODE_ID,
            "clients": [
                {
                    "client_id": client_id,
                    "launch": {
                        "executable": r"C:\Games\Shadowbane\sb.exe",
                        "arguments": [],
                        "working_directory": r"C:\Games\Shadowbane",
                    },
                    "expected_process_directory": r"C:\Games\Shadowbane",
                    "expected_executable_names": ["sb.exe"],
                    "window_tile": {
                        "left": left,
                        "top": 0,
                        "width": 960,
                        "height": 955,
                    },
                }
                for client_id, left in (("client-01", 0), ("client-02", 960))
            ],
        }
    )


def _client(instance_id: str, process_id: int) -> ClientInstanceSnapshot:
    return ClientInstanceSnapshot(
        node_id=NODE_ID,
        instance_id=instance_id,
        process_id=process_id,
        process_started_at_100ns=133_700_000_000_000_000 + process_id,
        window_handle=10_000 + process_id,
        executable_name="sb.exe",
        executable_path=r"C:\Games\Shadowbane\sb.exe",
        title=f"Shadowbane {process_id}",
        client_bounds=WindowBounds(left=0, top=0, width=1920, height=955),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
    )


def _heartbeat(
    client_id: str,
    instance_id: str,
    *,
    worker_number: int,
) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        node_id=NODE_ID,
        client_id=client_id,
        instance_id=instance_id,
        worker_id=f"worker-{worker_number:032x}",
        process_id=1_000 + worker_number,
        process_started_at_100ns=133_800_000_000_000_000 + worker_number,
        sequence=1,
        observed_at=1_000.0,
        runtime_state=WorkerRuntimeState.RUNNING,
        dispatch_ready=True,
        emergency_stop=False,
    )


class _Registry:
    def __init__(self, *clients: ClientInstanceSnapshot) -> None:
        self.snapshot = ClientRegistrySnapshot(node_id=NODE_ID, clients=tuple(clients))

    def inspect(self) -> ClientRegistrySnapshot:
        return self.snapshot


class _Ledger:
    def __init__(self, records: dict[str, tuple[WorkerHeartbeat, ...]]) -> None:
        self.records = records

    def inspect(self, client_id: str) -> WorkerLedgerSnapshot:
        return WorkerLedgerSnapshot(client_id=client_id, records=self.records[client_id])


class _Session:
    def __init__(self) -> None:
        self.attachments: list[tuple[str, str]] = []

    def attach(self, client_id: str, *, instance_id: str) -> object:
        self.attachments.append((client_id, instance_id))
        return object()


class _WorkerController:
    def __init__(self, *, fail_client_id: str | None = None) -> None:
        self.starts: list[tuple[str, str]] = []
        self.fail_client_id = fail_client_id

    def ensure_started(
        self,
        client_id: str,
        client: ClientInstanceSnapshot,
    ) -> int | None:
        self.starts.append((client_id, client.instance_id))
        if client_id == self.fail_client_id:
            raise RuntimeError("worker launch failed")
        return 123


class ManagerStartupRecoveryTests(unittest.TestCase):
    def test_recovers_only_exact_one_to_one_prior_worker_ownership(self) -> None:
        first = _client("instance-a", 101)
        second = _client("instance-b", 202)
        session = _Session()
        controller = _WorkerController()

        result = recover_manager_bindings(
            _manifest(),
            _Registry(first, second),
            _Ledger(
                {
                    "client-01": (_heartbeat("client-01", first.instance_id, worker_number=1),),
                    "client-02": (
                        _heartbeat("client-02", second.instance_id, worker_number=2),
                    ),
                }
            ),
            session,
            controller,
        )

        self.assertEqual(("client-01", "client-02"), result.recovered_client_ids)
        self.assertEqual([], list(result.issues))
        self.assertEqual(
            [("client-01", "instance-a"), ("client-02", "instance-b")],
            session.attachments,
        )
        self.assertEqual(session.attachments, controller.starts)

    def test_refuses_cross_slot_and_within_slot_ambiguity(self) -> None:
        first = _client("instance-a", 101)
        second = _client("instance-b", 202)
        session = _Session()

        result = recover_manager_bindings(
            _manifest(),
            _Registry(first, second),
            _Ledger(
                {
                    "client-01": (
                        _heartbeat("client-01", first.instance_id, worker_number=1),
                        _heartbeat("client-01", second.instance_id, worker_number=2),
                    ),
                    "client-02": (
                        _heartbeat("client-02", first.instance_id, worker_number=3),
                    ),
                }
            ),
            session,
            _WorkerController(),
        )

        self.assertEqual((), result.recovered_client_ids)
        self.assertEqual([], session.attachments)
        self.assertTrue(any("multiple current clients" in issue.detail for issue in result.issues))

    def test_keeps_recovered_binding_when_worker_restart_needs_attention(self) -> None:
        first = _client("instance-a", 101)
        session = _Session()

        result = recover_manager_bindings(
            _manifest(),
            _Registry(first),
            _Ledger(
                {
                    "client-01": (_heartbeat("client-01", first.instance_id, worker_number=1),),
                    "client-02": (),
                }
            ),
            session,
            _WorkerController(fail_client_id="client-01"),
        )

        self.assertEqual(("client-01",), result.recovered_client_ids)
        self.assertEqual([("client-01", "instance-a")], session.attachments)
        self.assertTrue(any("worker launch failed" in issue.detail for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
