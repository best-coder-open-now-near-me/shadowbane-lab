import unittest
from dataclasses import replace

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

    def dispatch(self, kind, command, **kwargs):
        self.calls.append((kind, command, kwargs))
        if self.fail:
            raise RuntimeError("worker unavailable")
        return object()


class ExtensionEventRouterTests(unittest.TestCase):
    def test_routes_focus_independent_event_as_stop_then_exact_travel(self) -> None:
        consumer = Consumer(_event())
        ingress = Ingress()
        router = ExactExtensionEventRouter(
            _manifest(),
            Registry(_client()),
            ingress,
            consumer_factory=lambda *_: consumer,
            clock=lambda: NOW,
        )

        result = router.poll_once()

        self.assertEqual(1, result.dispatched_events)
        self.assertEqual((PROCESS_ID,), result.dispatched_process_ids)
        self.assertEqual([consumer.events[0]], consumer.acknowledged)
        self.assertEqual(
            [WorkerOperationKind.STOP, WorkerOperationKind.TRAVEL],
            [call[0] for call in ingress.calls],
        )
        travel = ingress.calls[1][2]
        self.assertEqual(PROCESS_ID, travel["expected_process_id"])
        self.assertEqual(WINDOW_HANDLE, travel["expected_window_handle"])
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


if __name__ == "__main__":
    unittest.main()
