import subprocess
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.city_window_session import NativeCityWindowSession
from shadowbane_lab.client_extension.city_window_wire import (
    _RECEIPT,
    MAGIC,
    READY,
    Command,
    Host,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.manager.vendor_discovery import discovery_summary, run_discovery
from shadowbane_lab.manager.vendor_job import VendorJobStore

KEY = "01000000-0000-0000-0000-000000000000"
STATE = Snapshot(1, 1, 100, 200)
OPENED = replace(STATE, revision=2, hud=300, active_manager=200,
                 mode=2, visible=1, building_count=1)


def receipt(state=STATE, flags=READY, outcome=Outcome.OBSERVED, key=KEY):
    return Receipt(key, Host(1, 1, 1), 1000, outcome, flags, state)


class Transport:
    host_process_identity = NativeClientProcessIdentity(1, 1)
    host_lease_generation = 1

    def __init__(self, identity):
        self.identity = identity
        self.commands = []
        self.mode = "normal"
        self.closed = False

    def submit(self, command, *, timeout_ms):
        self.commands.append(command)
        assert len(command.encode_slot(sequence=1, created_tick=100, deadline_tick=850)) == 768
        if self.mode == "timeout":
            raise NativeActionChannelTimeout("test")
        key = KEY if self.mode == "request" else command.payload.request_key
        host = Host(2 if self.mode == "host" else 1, 1, 1)
        payload = _RECEIPT.pack(
            uuid.UUID(key).bytes, host.encode(), 2000 if self.mode == "window" else 1000,
            Outcome.OBSERVED, READY, STATE.encode(), MAGIC, bytes(268),
        )
        return NativeActionResult(
            1, command.command_id, 1,
            NativeActionResultStage.FAILED if self.mode == "stage"
            else NativeActionResultStage.SUBMITTED_TO_CLIENT,
            0, 100, 5760, "native_city_window_receipt_v1", payload,
        )

    def close(self):
        self.closed = True


class CityWindowWireTests(unittest.TestCase):
    def test_snapshot_and_command_boundaries(self):
        self.assertEqual(STATE, Snapshot.decode(STATE.encode()))
        self.assertEqual(64, len(Snapshot().encode()))
        self.assertEqual(576, len(Command(Host(1, 1, 1), 1000, KEY, STATE).encode(Verb.OPEN)))
        for state in (replace(STATE, loading=2), replace(STATE, building_count=513),
                      replace(STATE, root=True), replace(STATE, visible=1),
                      replace(OPENED, mode=0), replace(STATE, loading=1)):
            with self.subTest(state=state), self.assertRaises(ValueError):
                state.encode()
        for command, verb in (
            (Command(Host(1, 1, 1), 1000, KEY, STATE), Verb.INSPECT),
            (Command(Host(1, 1, 1), 1000, KEY), Verb.OPEN),
            (Command(Host(1, 1, 1), 1000, KEY, replace(OPENED, loading=1)), Verb.OPEN),
            (Command(Host(1, 1, 1), 0, KEY, STATE), Verb.OPEN),
        ):
            with self.subTest(command=command), self.assertRaises(ValueError):
                command.encode(verb)

    def test_corrupt_receipts_fail_closed(self):
        raw = _RECEIPT.pack(
            uuid.UUID(KEY).bytes, Host(1, 1, 1).encode(), 1000, 0, READY,
            STATE.encode(), MAGIC, bytes(268),
        )
        self.assertEqual(receipt(), Receipt.decode(raw))
        for offset in (0, 44, 112, 116):
            data = bytearray(raw)
            if offset == 0:
                data[:16] = bytes(16)
            else:
                data[offset] ^= 0x80
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                Receipt.decode(bytes(data))
        for size in (0, 383, 385):
            with self.subTest(size=size), self.assertRaises(ValueError):
                Receipt.decode(bytes(size))

    def test_native_host_byte_agreement(self):
        exe = Path(__file__).resolve().parents[1] / "artifacts/vendor-native-build/Release" / (
            "wonderbane_extension_city_window_controller_test.exe"
        )
        if not exe.exists():
            self.skipTest("native fixture executable is not built")
        state, command, raw_receipt = [
            bytes.fromhex(line)
            for line in subprocess.check_output([str(exe), "wire"], text=True).splitlines()
        ]
        self.assertEqual(STATE.encode(), state)
        self.assertEqual(Command(Host(1, 1, 1), 1000, KEY, STATE).encode(Verb.OPEN), command)
        self.assertEqual(receipt(outcome=Outcome.SUBMITTED, flags=0), Receipt.decode(raw_receipt))

    def test_session_correlation_close_and_no_open_retry(self):
        with patch(
            "shadowbane_lab.client_extension.city_window_session.channel.WindowsNativeActionCommandTransport",
            Transport,
        ):
            session = NativeCityWindowSession(NativeClientProcessIdentity(988, 123), 1000)
            self.assertEqual(Outcome.OBSERVED, session.inspect().outcome)
            for mode in ("request", "host", "window", "stage"):
                session._transport.mode = mode
                with self.subTest(mode=mode), self.assertRaises(NativeActionChannelError):
                    session.inspect()
            session._transport.mode = "timeout"
            before = len(session._transport.commands)
            with self.assertRaises(NativeActionChannelTimeout):
                session.open(STATE, KEY)
            self.assertEqual(before + 1, len(session._transport.commands))
            session.close()
            self.assertTrue(session._transport.closed)
            with self.assertRaises(NativeActionChannelError):
                session.inspect()


class NearbyDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = VendorJobStore(Path(self.temp.name), "node", "client", "instance")
        self.binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=123)
        self.operation = SimpleNamespace(operation_id="operation-" + "a" * 32)
        self.session = Mock()
        self.session.inspect.side_effect = [receipt(), receipt(OPENED), receipt(OPENED)]
        self.session.open.return_value = receipt(outcome=Outcome.SUBMITTED, flags=0)
        self.reader = Mock(return_value={
            "process_id": 988, "process_creation_filetime_utc": 123,
            "buildings": [{"vendors": [{"vendor": {"object_id": 401, "object_type": 42}}]}],
            "roster_complete": False, "server_response_verified": False,
        })
        self.tick = 0

    def clock(self):
        self.tick += 1
        return self.tick

    def run_scan(self, **kwargs):
        return run_discovery(
            self.store, self.binding, self.operation, self.session, reader=self.reader,
            clock=self.clock, sleep=lambda _: None,
            cancelled=kwargs.get("cancelled", lambda: False),
        )

    def test_success_separate_from_crafting_and_duplicate_execution_does_not_reopen(self):
        self.store.root.mkdir(parents=True)
        old = self.store.root / "current.json"
        old.write_text('{"job_id":"unchanged-review"}')
        result = self.run_scan()
        self.assertEqual("complete", result["state"])
        self.assertFalse(result["roster_complete"])
        self.assertEqual(1, result["buildings"])
        self.assertEqual(1, result["vendors"])
        self.assertEqual('{"job_id":"unchanged-review"}', old.read_text())
        summary = discovery_summary(self.store)
        self.assertNotIn("roster", summary)
        self.assertEqual("complete", summary["state"])
        with self.assertRaisesRegex(VendorBatchStopped, "already attempted"):
            self.run_scan()
        self.session.open.assert_called_once()

    def test_focus_wait_and_loading_do_not_repeat_open(self):
        loading = replace(OPENED, loading=1)
        self.session.inspect.side_effect = [
            receipt(flags=0), receipt(), receipt(loading, flags=0),
            receipt(OPENED), receipt(OPENED),
        ]
        self.assertEqual("complete", self.run_scan()["state"])
        self.session.open.assert_called_once()

    def test_uncertain_open_is_recorded_without_retry(self):
        self.session.open.return_value = receipt(outcome=Outcome.UNCERTAIN, flags=0)
        with self.assertRaises(VendorBatchStopped):
            self.run_scan()
        self.session.open.assert_called_once()
        self.reader.assert_not_called()
        self.assertEqual("review", discovery_summary(self.store)["state"])

    def test_scene_change_and_foreign_roster_are_rejected(self):
        self.session.inspect.side_effect = [receipt(), receipt(replace(OPENED, scene=2))]
        with self.assertRaisesRegex(VendorBatchStopped, "scene changed"):
            self.run_scan()
        self.reader.assert_not_called()

    def test_cancel_before_open_and_wait_timeout(self):
        with self.assertRaises(VendorBatchStopped):
            self.run_scan(cancelled=lambda: True)
        self.session.open.assert_not_called()
        self.assertEqual("cancelled", discovery_summary(self.store)["state"])

    def test_ready_timeout_does_not_send_open(self):
        self.session.inspect.side_effect = None
        self.session.inspect.return_value = receipt(flags=0)
        with self.assertRaisesRegex(VendorBatchStopped, "did not become ready"):
            self.run_scan()
        self.session.open.assert_not_called()

    def test_roster_identity_and_count_must_match_native_observation(self):
        self.reader.return_value["process_id"] = 989
        with self.assertRaisesRegex(VendorBatchStopped, "changed during verification"):
            self.run_scan()
        self.assertEqual("review", discovery_summary(self.store)["state"])

    def test_snapshot_change_during_external_read_is_rejected(self):
        self.session.inspect.side_effect = [receipt(), receipt(OPENED),
                                           receipt(replace(OPENED, revision=3))]
        with self.assertRaisesRegex(VendorBatchStopped, "changed during verification"):
            self.run_scan()
        self.assertEqual("review", discovery_summary(self.store)["state"])

    def test_cancel_after_ready_does_not_send_open(self):
        cancelled = Mock(side_effect=[False, True, True])
        with self.assertRaisesRegex(VendorBatchStopped, "cancelled"):
            self.run_scan(cancelled=cancelled)
        self.session.inspect.assert_called_once()
        self.session.open.assert_not_called()
        self.assertEqual("cancelled", discovery_summary(self.store)["state"])
