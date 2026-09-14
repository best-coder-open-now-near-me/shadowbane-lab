import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.vendor_session import NativeVendorSession
from shadowbane_lab.client_extension.vendor_wire import (
    _RECEIPT,
    READY,
    Command,
    Host,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)
from tests.test_vendor_batch import KEY, snapshot


class Transport:
    host_process_identity = NativeClientProcessIdentity(123, 456)
    host_lease_generation = 7
    mode = "normal"
    closed = False

    def __init__(self, identity):
        self.identity = identity
        self.commands = []

    def submit(self, command, *, timeout_ms):
        self.commands.append(command)
        data = command.encode_slot(sequence=1, created_tick=100, deadline_tick=100 + timeout_ms)
        assert len(data) == 768
        request = KEY if self.mode == "wrong_request" else command.payload.request_key
        window = 2000 if self.mode == "wrong_window" else command.payload.window
        host = Host(124 if self.mode == "wrong_host" else 123, 7, 456)
        raw = _RECEIPT.pack(
            uuid.UUID(request).bytes, host.encode(), window, Outcome.OBSERVED,
            READY, snapshot().encode(), 0x57425631, 0, bytes(16), bytes(24),
        )
        return NativeActionResult(
            1, command.command_id, 1,
            NativeActionResultStage.FAILED if self.mode == "contradiction"
            else NativeActionResultStage.SUBMITTED_TO_CLIENT,
            0, 100, 5760, "native_vendor_receipt_v1", raw,
        )

    def close(self):
        self.closed = True


class VendorSessionTests(unittest.TestCase):
    def test_typed_session_correlates_client_host_request_and_window(self):
        with patch(
            "shadowbane_lab.client_extension.vendor_session.channel.WindowsNativeActionCommandTransport",
            Transport,
        ):
            session = NativeVendorSession(NativeClientProcessIdentity(988, 12345), 1000)
            result = session.inspect()
            self.assertEqual(Outcome.OBSERVED, result.outcome)
            self.assertEqual(Verb.INSPECT, session._transport.commands[0].kind)
            session.close()
            self.assertTrue(session._transport.closed)
            with self.assertRaises(NativeActionChannelError):
                session.inspect()

    def test_mismatched_or_contradictory_receipts_are_rejected(self):
        for mode in ("wrong_request", "wrong_window", "wrong_host", "contradiction"):
            with self.subTest(mode=mode), patch(
                "shadowbane_lab.client_extension.vendor_session.channel."
                "WindowsNativeActionCommandTransport", Transport,
            ):
                session = NativeVendorSession(NativeClientProcessIdentity(988, 12345), 1000)
                session._transport.mode = mode
                try:
                    with self.assertRaises(NativeActionChannelError):
                        session.inspect()
                    self.assertEqual(1, len(session._transport.commands))
                finally:
                    session.close()


class VendorCrossLanguageTests(unittest.TestCase):
    def test_cpp_snapshot_command_and_receipt_match_python(self):
        fixture = Path(__file__).parent / "fixtures" / "native_vendor_wire_v1.hex"
        raw_snapshot, raw_command, raw_receipt = (
            bytes.fromhex(line) for line in fixture.read_text().splitlines()
        )
        state = snapshot()
        self.assertEqual(state, Snapshot.decode(raw_snapshot))
        key = str(uuid.UUID(bytes=bytes(range(1, 17))))
        command = Command(Host(1234, 7, 0x1122334455667788), 0x76543210, key, state)
        self.assertEqual(raw_command, command.encode(Verb.CREATE))
        result = Receipt.decode(raw_receipt)
        self.assertEqual(key, result.request_key)
        self.assertEqual(command.host, result.host)
        self.assertEqual(command.window, result.window)
        self.assertEqual(state, result.snapshot)
        self.assertEqual(Outcome.SUBMITTED, result.outcome)
        self.assertEqual(288, len(raw_snapshot))
        self.assertEqual(576, len(raw_command))
        self.assertEqual(384, len(raw_receipt))
        malformed = bytearray(raw_snapshot)
        malformed[272] = 1
        with self.assertRaises(ValueError):
            Snapshot.decode(bytes(malformed))
        with self.assertRaises(ValueError):
            replace(command, expected=Snapshot()).encode(Verb.CREATE)
