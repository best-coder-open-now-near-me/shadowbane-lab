import struct
import subprocess
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.vendor_navigation_session import NativeVendorNavigationSession
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    _RECEIPT,
    IN_FLIGHT,
    MAGIC,
    READY,
    Command,
    Host,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)

KEY = "01000000-0000-0000-0000-000000000000"
STATE = Snapshot(1, 1, 100, 200)
OPENED = replace(
    STATE,
    revision=2,
    building_hud=300,
    active_manager=200,
    mode=6,
    visible=1,
    initialized=1,
    building_id=123,
    building_type=8,
)


def receipt(state=STATE, flags=READY, outcome=Outcome.OBSERVED, key=KEY):
    return Receipt(
        key, Host(1, 1, 1), 1000, outcome, flags, state, KEY if flags & IN_FLIGHT else None
    )


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
            uuid.UUID(key).bytes,
            host.encode(),
            2000 if self.mode == "window" else 1000,
            Outcome.OBSERVED,
            READY,
            STATE.encode(),
            bytes(16),
            MAGIC,
            bytes(220),
        )
        return NativeActionResult(
            1,
            command.command_id,
            1,
            NativeActionResultStage.FAILED
            if self.mode == "stage"
            else NativeActionResultStage.SUBMITTED_TO_CLIENT,
            0,
            100,
            5760,
            "native_vendor_navigation_receipt_v2",
            payload,
        )

    def close(self):
        self.closed = True


class VendorNavigationWireTests(unittest.TestCase):
    def test_snapshot_and_command_boundaries(self):
        self.assertEqual(STATE, Snapshot.decode(STATE.encode()))
        self.assertEqual(96, len(Snapshot().encode()))
        self.assertEqual(
            576, len(Command(Host(1, 1, 1), 1000, KEY, STATE, 123).encode(Verb.BUILDING))
        )
        for state in (
            replace(STATE, offline=2),
            replace(STATE, capacity=129),
            replace(STATE, root=True),
            replace(STATE, visible=1),
            replace(OPENED, mode=0),
            replace(STATE, vendor_id=777, vendor_type=42),
        ):
            with self.subTest(state=state), self.assertRaises(ValueError):
                state.encode()
        for command, verb in (
            (Command(Host(1, 1, 1), 1000, KEY, STATE, 123), Verb.INSPECT),
            (Command(Host(1, 1, 1), 1000, KEY), Verb.BUILDING),
            (Command(Host(1, 1, 1), 1000, KEY, replace(OPENED, offline=1), 123), Verb.BUILDING),
            (Command(Host(1, 1, 1), 0, KEY, STATE), Verb.BUILDING),
        ):
            with self.subTest(command=command), self.assertRaises(ValueError):
                command.encode(verb)

    def test_selected_vacancy_is_a_building_response_but_not_a_vendor(self):
        vacancy = replace(OPENED, selected_entry=400, capacity=3, occupied=2)
        self.assertEqual(vacancy, Snapshot.decode(vacancy.encode()))
        self.assertTrue(vacancy.opened(123))
        self.assertFalse(vacancy.opened(123, 777))
        self.assertEqual(
            576, len(Command(Host(1, 1, 1), 1000, KEY, vacancy, 123, 777).encode(Verb.VENDOR))
        )
        with self.assertRaises(ValueError):
            replace(vacancy, vendor_hud=500, visible=3).encode()
        self.assertTrue(replace(vacancy, active_manager=999).opened(123))

    def test_secondary_action_manager_does_not_replace_visible_hud_ownership(self):
        building = replace(OPENED, active_manager=999)
        vendor = replace(
            building, selected_entry=400, vendor_hud=500, visible=3, vendor_id=777, vendor_type=42
        )
        self.assertTrue(building.opened(123))
        self.assertTrue(vendor.opened(123, 777))
        self.assertFalse(replace(building, visible=0).opened(123))
        self.assertFalse(replace(vendor, visible=1).opened(123, 777))
        self.assertFalse(replace(vendor, offline=1).opened(123, 777))
        self.assertFalse(vendor.opened(456, 777))
        self.assertFalse(vendor.opened(123, 888))

    def test_guard_and_vendor_keys_remain_distinct(self):
        guard = replace(
            OPENED, selected_entry=400, vendor_hud=500, visible=3, vendor_id=777, vendor_type=37
        )
        self.assertEqual(guard, Snapshot.decode(guard.encode()))
        self.assertTrue(guard.opened(123, 777, hireling_type=37))
        self.assertFalse(guard.opened(123, 777))
        self.assertFalse(guard.opened(123, 777, hireling_type=8))
        self.assertFalse(guard.opened(456, 777, hireling_type=37))
        self.assertFalse(replace(guard, visible=1).opened(123, 777, hireling_type=37))
        command = Command(Host(1, 1, 1), 1000, KEY, OPENED, 123, 777)
        self.assertEqual(
            (123, 8, 777, 37), struct.unpack_from("<4I", command.encode(Verb.GUARD), 136)
        )
        self.assertEqual(
            (123, 8, 777, 42), struct.unpack_from("<4I", command.encode(Verb.VENDOR), 136)
        )
        for state, building, target in ((STATE, 123, 777), (OPENED, 456, 777), (OPENED, 123, 0)):
            with (
                self.subTest(state=state, building=building, target=target),
                self.assertRaises(ValueError),
            ):
                Command(Host(1, 1, 1), 1000, KEY, state, building, target).encode(Verb.GUARD)

    def test_warehouse_source_is_separate_from_management_inventory(self):
        state = replace(OPENED, warehouse_hud=800, warehouse_object=900,
                        warehouse_id=777, warehouse_type=42)
        self.assertEqual(state, Snapshot.decode(state.encode()))
        self.assertTrue(state.warehouse_opened(123, 777))
        self.assertFalse(OPENED.warehouse_opened(123, 777))
        for building, source in ((456, 777), (123, 778), (123, 0)):
            self.assertFalse(state.warehouse_opened(building, source))
        for changed in (replace(state, warehouse_type=37), replace(state, warehouse_hud=0),
                        replace(state, warehouse_object=0), replace(state, warehouse_id=0)):
            with self.assertRaises(ValueError):
                changed.encode()
        command = Command(Host(1, 1, 1), 1000, KEY, OPENED, 123, 777)
        self.assertEqual(
            (123, 8, 777, 42), struct.unpack_from("<4I", command.encode(Verb.WAREHOUSE), 136)
        )
        for state, building, source in ((STATE, 123, 777), (OPENED, 456, 777), (OPENED, 123, 0)):
            with self.assertRaises(ValueError):
                Command(Host(1, 1, 1), 1000, KEY, state, building, source).encode(Verb.WAREHOUSE)

    def test_corrupt_receipts_fail_closed(self):
        raw = _RECEIPT.pack(
            uuid.UUID(KEY).bytes,
            Host(1, 1, 1).encode(),
            1000,
            0,
            READY,
            STATE.encode(),
            bytes(16),
            MAGIC,
            bytes(220),
        )
        self.assertEqual(receipt(), Receipt.decode(raw))
        legacy = bytearray(raw)
        struct.pack_into("<I", legacy, 160, 0x57424E31)
        with self.assertRaises(ValueError):
            Receipt.decode(bytes(legacy))
        for offset in (0, 44, 160, 164):
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
        exe = (
            Path(__file__).resolve().parents[1]
            / "artifacts/vendor-native-build/Release"
            / ("wonderbane_extension_vendor_navigation_controller_test.exe")
        )
        if not exe.exists():
            self.skipTest("native fixture executable is not built")
        state, command, raw_receipt = [
            bytes.fromhex(line)
            for line in subprocess.check_output([str(exe), "wire"], text=True).splitlines()
        ]
        self.assertEqual(STATE.encode(), state)
        self.assertEqual(
            Command(Host(1, 1, 1), 1000, KEY, STATE, 123).encode(Verb.BUILDING), command
        )
        self.assertEqual(
            receipt(outcome=Outcome.SUBMITTED, flags=IN_FLIGHT), Receipt.decode(raw_receipt)
        )

    def test_native_warehouse_source_byte_agreement(self):
        exe = (
            Path(__file__).resolve().parents[1] / "artifacts/vendor-native-build/Release"
            / "wonderbane_extension_vendor_navigation_controller_test.exe"
        )
        if not exe.exists():
            self.skipTest("native fixture executable is not built")
        state, command, raw = [bytes.fromhex(line) for line in
                               subprocess.check_output([str(exe), "wire", "warehouse"],
                                                       text=True).splitlines()]
        expected = replace(OPENED, revision=1, active_manager=0, warehouse_hud=600,
                           warehouse_object=700, warehouse_id=777, warehouse_type=42)
        self.assertEqual(expected.encode(), state)
        self.assertEqual(Command(Host(1, 1, 1), 1000, KEY, expected, 123, 777)
                         .encode(Verb.WAREHOUSE), command)
        observed = Receipt.decode(raw)
        self.assertEqual(expected, observed.snapshot)
        self.assertEqual(Outcome.OBSERVED, observed.outcome)
        self.assertEqual(KEY, observed.transition_request)

    def test_session_correlation_close_and_no_open_retry(self):
        with patch(
            "shadowbane_lab.client_extension.vendor_navigation_session.channel.WindowsNativeActionCommandTransport",
            Transport,
        ):
            session = NativeVendorNavigationSession(NativeClientProcessIdentity(988, 123), 1000)
            self.assertEqual(Outcome.OBSERVED, session.inspect().outcome)
            for mode in ("request", "host", "window", "stage"):
                session._transport.mode = mode
                with self.subTest(mode=mode), self.assertRaises(NativeActionChannelError):
                    session.inspect()
            session._transport.mode = "timeout"
            before = len(session._transport.commands)
            with self.assertRaises(NativeActionChannelTimeout):
                session.open_building(STATE, 123, KEY)
            self.assertEqual(before + 1, len(session._transport.commands))
            with self.assertRaises(NativeActionChannelTimeout):
                session.open_vendor(OPENED, 123, 777, KEY)
            self.assertEqual(before + 2, len(session._transport.commands))
            with self.assertRaises(NativeActionChannelTimeout):
                session.open_guard(OPENED, 123, 777, KEY)
            self.assertEqual(before + 3, len(session._transport.commands))
            self.assertEqual(Verb.GUARD, session._transport.commands[-1].kind)
            with self.assertRaises(NativeActionChannelTimeout):
                session.open_warehouse(OPENED, 123, 777, KEY)
            self.assertEqual(before + 4, len(session._transport.commands))
            self.assertEqual(Verb.WAREHOUSE, session._transport.commands[-1].kind)
            session.close()
            self.assertTrue(session._transport.closed)
            with self.assertRaises(NativeActionChannelError):
                session.inspect()
