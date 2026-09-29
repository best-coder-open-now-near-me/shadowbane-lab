import unittest
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension import (
    ExtensionPointerButton,
    ExtensionWorldMapDestinationEvent,
)
from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager import parse_manager_manifest
from shadowbane_lab.manager.extension_router import ExactExtensionEventRouter
from shadowbane_lab.manager.model import ClientInstanceSnapshot, ClientRegistrySnapshot
from shadowbane_lab.manager.operation import WorkerOperationKind

NODE_ID = "gaming-pc-east"
PROCESS_ID = 701
WINDOW_HANDLE = 81
NOW = 1_700_000_000.0
FILETIME_UNIX_EPOCH = 116_444_736_000_000_000
PROCESS_CREATION = int((NOW - 3_600.0) * 10_000_000) + FILETIME_UNIX_EPOCH


def _manifest():
    return parse_manager_manifest(
        {
            "schema_version": 1,
            "node_id": NODE_ID,
            "clients": [
                {
                    "client_id": "client-01",
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
        instance_id="instance-101",
        process_id=PROCESS_ID,
        process_started_at_100ns=PROCESS_CREATION,
        window_handle=WINDOW_HANDLE,
        executable_name="sb.exe",
        title="Shadowbane",
        client_bounds=WindowBounds(0, 0, 1920, 955),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
        executable_path=r"C:\Games\Shadowbane\sb.exe",
    )


def _event(*, age_seconds: float = 0.0, window_handle: int = WINDOW_HANDLE):
    captured = int((NOW - age_seconds) * 10_000_000) + FILETIME_UNIX_EPOCH
    return ExtensionWorldMapDestinationEvent(
        sequence=1,
        process_id=PROCESS_ID,
        process_creation_filetime_utc=PROCESS_CREATION,
        captured_at_filetime_utc=captured,
        window_handle=window_handle,
        button=ExtensionPointerButton.RIGHT,
        lt=106_662.0,
        lg=52_432.0,
        snapshot_token="0123456789abcdef",
        desktop_screen_x=400,
        desktop_screen_y=300,
        client_x=380,
        client_y=260,
    )


class Registry:
    def __init__(self, client: ClientInstanceSnapshot) -> None:
        self.client = client

    def inspect(self) -> ClientRegistrySnapshot:
        return ClientRegistrySnapshot(node_id=NODE_ID, clients=(self.client,))


class Consumer:
    process_identity = PROCESS_ID, PROCESS_CREATION

    def __init__(self, event: ExtensionWorldMapDestinationEvent) -> None:
        self.events = (event,)
        self.acknowledged = []
        self.closed = False

    def pending(self):
        return self.events[len(self.acknowledged) :]

    def acknowledge(self, event):
        self.acknowledged.append(event)

    def close(self):
        self.closed = True


class Ingress:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def cancel_if_inflight(self, command, **kwargs):
        self.calls.append((WorkerOperationKind.CANCEL, command, kwargs))
        if self.fail:
            raise RuntimeError("worker unavailable")
        return object()

    def dispatch(self, kind, command, **kwargs):
        self.calls.append((kind, command, kwargs))
        if self.fail:
            raise RuntimeError("worker unavailable")
        return object()


class ExtensionEventRouterTests(unittest.TestCase):
    def test_routes_focus_independent_event_as_cancel_then_exact_travel(self) -> None:
        consumer = Consumer(_event())
        ingress = Ingress()
        prepared = []
        router = ExactExtensionEventRouter(
            _manifest(),
            Registry(_client()),
            ingress,
            consumer_factory=lambda *_: consumer,
            event_preparer=lambda client, event: prepared.append((client, event)),
            clock=lambda: NOW,
        )

        result = router.poll_once()

        self.assertEqual(1, result.dispatched_events)
        self.assertEqual((PROCESS_ID,), result.dispatched_process_ids)
        self.assertEqual([consumer.events[0]], consumer.acknowledged)
        self.assertEqual([(_client(), consumer.events[0])], prepared)
        self.assertEqual(
            [WorkerOperationKind.CANCEL, WorkerOperationKind.TRAVEL],
            [call[0] for call in ingress.calls],
        )
        travel = ingress.calls[1][2]
        self.assertEqual(PROCESS_ID, travel["expected_process_id"])
        self.assertEqual(WINDOW_HANDLE, travel["expected_window_handle"])
        for _, _, options in ingress.calls:
            self.assertEqual(PROCESS_CREATION, options["expected_process_started_at_100ns"])
        self.assertFalse(travel["require_foreground"])
        self.assertEqual(106_662.0, travel["destination"].lt)
        self.assertEqual(52_432.0, travel["destination"].lg)
        self.assertRegex(travel["operation_id"], r"operation-[0-9a-f]{32}\Z")

    def test_rejects_and_acknowledges_stale_or_rebound_event(self) -> None:
        for event in (_event(age_seconds=9.0), _event(window_handle=WINDOW_HANDLE + 1)):
            with self.subTest(event=event):
                consumer = Consumer(event)
                ingress = Ingress()
                router = ExactExtensionEventRouter(
                    _manifest(),
                    Registry(_client()),
                    ingress,
                    consumer_factory=lambda *_, source=consumer: source,
                    clock=lambda: NOW,
                )

                result = router.poll_once()

                self.assertEqual(1, result.rejected_events)
                self.assertEqual([event], consumer.acknowledged)
                self.assertEqual([], ingress.calls)

    def test_transient_dispatch_failure_leaves_event_unacknowledged(self) -> None:
        consumer = Consumer(_event())
        router = ExactExtensionEventRouter(
            _manifest(),
            Registry(replace(_client(), is_foreground=True)),
            Ingress(fail=True),
            consumer_factory=lambda *_: consumer,
            clock=lambda: NOW,
        )

        result = router.poll_once()

        self.assertEqual((), tuple(consumer.acknowledged))
        self.assertEqual(1, result.pending_events)
        self.assertTrue(result.issues)

    def test_transient_event_preparation_failure_leaves_event_unacknowledged(self) -> None:
        consumer = Consumer(_event())
        ingress = Ingress()

        def fail_preparation(_client, _event) -> None:
            raise RuntimeError("world map did not close")

        router = ExactExtensionEventRouter(
            _manifest(),
            Registry(replace(_client(), is_foreground=True)),
            ingress,
            consumer_factory=lambda *_: consumer,
            event_preparer=fail_preparation,
            clock=lambda: NOW,
        )

        result = router.poll_once()

        self.assertEqual((), tuple(consumer.acknowledged))
        self.assertEqual([], ingress.calls)
        self.assertEqual(1, result.pending_events)
        self.assertTrue(result.issues)


if __name__ == "__main__":
    unittest.main()



@pytest.mark.parametrize("switch_at", [2, 3])
def test_process_replacement_cannot_redirect_extension_cancellation_or_travel(tmp_path, switch_at):
    from shadowbane_lab.manager.operation import WorkerOperationLedger, new_worker_operation
    from shadowbane_lab.manager.operation_ingress import ForegroundWorkerOperationIngress
    from shadowbane_lab.manager.registry import derive_client_instance_id
    from shadowbane_lab.manager.worker import WorkerDispatchPermit, WorkerHealthState

    # Registry read 1 captures the event owner, 2 resolves cancellation and
    # 3 resolves travel. Replace between either pair of ownership checks.
    manifest = _manifest()
    original = _client()
    replacement = replace(
        original,
        process_started_at_100ns=PROCESS_CREATION + 1,
        instance_id=derive_client_instance_id(
            NODE_ID, PROCESS_ID, PROCESS_CREATION + 1, WINDOW_HANDLE,
        ),
    )
    ledger = WorkerOperationLedger(manifest, tmp_path / str(switch_at))

    class ReplacingRegistry(Registry):
        reads = 0

        def inspect(self):
            self.reads += 1
            if self.reads == switch_at:
                self.client = replacement
                # New B legitimately owns an active job and a fresh permit.
                # A's old click must neither cancel it nor start travel on B.
                ledger.submit(new_worker_operation(
                    permits.inspect_permit("client-01"), WorkerOperationKind.PVE,
                    "/pve", now=NOW,
                ))
            return super().inspect()

    registry = ReplacingRegistry(original)

    class Permits:
        def inspect_permit(self, client_id):
            return WorkerDispatchPermit(
                node_id=NODE_ID, client_id=client_id,
                instance_id=registry.client.instance_id,
                worker_id="worker-0123456789abcdef0123456789abcdef",
                process_id=9001, process_started_at_100ns=1000, heartbeat_sequence=1,
                health_state=WorkerHealthState.HEALTHY, allowed=True,
                issued_at=NOW - 1, expires_at=NOW + 1, reason="healthy worker",
            )

    permits = Permits()
    ingress = ForegroundWorkerOperationIngress(
        manifest, registry, permits, ledger, clock=lambda: NOW,
        acknowledgement_timeout_seconds=0.001,
    )
    consumer = Consumer(_event())
    router = ExactExtensionEventRouter(
        manifest, registry, ingress, consumer_factory=lambda *_: consumer,
        clock=lambda: NOW,
    )

    result = router.poll_once()

    assert registry.reads == switch_at
    assert result.dispatched_events == 0
    assert result.pending_events == 1
    assert consumer.acknowledged == []
    retained = ledger.inspect_slot("client-01")
    assert len(retained) == 1
    assert retained[0].operation.kind is WorkerOperationKind.PVE
    assert retained[0].operation.instance_id == replacement.instance_id
    assert retained[0].receipt is None
