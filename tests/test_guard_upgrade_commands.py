import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.guard_upgrade_session import NativeGuardUpgradeSession
from shadowbane_lab.client_extension.guard_upgrade_wire import (
    _RECEIPT,
    IN_FLIGHT,
    MAGIC,
    READY,
    UNRESOLVED,
    Command,
    Host,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)
from shadowbane_lab.client_extension.vendor_navigation_wire import Snapshot as Navigation

KEY = "01000000-0000-0000-0000-000000000000"
NAV = Navigation(
    scene=1,
    revision=1,
    root=100,
    manager=200,
    mode=6,
    building_hud=300,
    vendor_hud=400,
    selected_entry=500,
    visible=3,
    building_id=123,
    building_type=8,
    vendor_id=777,
    vendor_type=37,
    initialized=1,
    capacity=1,
    occupied=1,
)
STATE = Snapshot(NAV, 1, 100, 150, 0, 1, 3, 600, 700)
HOST = Host(1, 1, 1)


@pytest.mark.parametrize(
    "state",
    [
        replace(STATE, upgrading=1),
        replace(STATE, can_upgrade=0),
        replace(STATE, control_flags=7),
        replace(STATE, control_flags=1),
        replace(STATE, funds=99),
        replace(STATE, cost=0),
        Snapshot(),
        replace(STATE, navigation=replace(NAV, vendor_type=42)),
        replace(STATE, navigation=replace(NAV, offline=1)),
        replace(STATE, rank=0),
        replace(STATE, cost=True),
        replace(STATE, upgrade_control=700),
        replace(STATE, funds=2**31),
    ],
)
def test_ineligible_upgrade_rejected_before_transport(state):
    with pytest.raises(ValueError):
        Command(HOST, 1000, KEY, state).encode(Verb.UPGRADE)


def raw_receipt(key=KEY, host=HOST, window=1000, flags=READY, state=STATE):
    return _RECEIPT.pack(
        uuid.UUID(key).bytes,
        host.encode(),
        window,
        Outcome.OBSERVED,
        flags,
        state.encode(),
        bytes(16),
        MAGIC,
        bytes(188),
    )


def test_wire_round_trip_and_corrupt_receipts():
    assert Snapshot.decode(STATE.encode()) == STATE
    assert len(Command(HOST, 1000, KEY, STATE).encode(Verb.UPGRADE)) == 576
    assert len(Command(HOST, 1000, KEY).encode(Verb.INSPECT)) == 576
    with pytest.raises(ValueError):
        Command(HOST, 1000, KEY, STATE).encode(Verb.INSPECT)
    assert Receipt.decode(raw_receipt()).snapshot == STATE
    for flags in (READY | IN_FLIGHT, READY | UNRESOLVED, 8):
        with pytest.raises(ValueError):
            Receipt.decode(raw_receipt(flags=flags))
    for offset in (192, 196, 383):
        data = bytearray(raw_receipt())
        data[offset] ^= 1
        with pytest.raises(ValueError):
            Receipt.decode(bytes(data))


def test_native_host_bytes_agree():
    exe = (
        Path(__file__).resolve().parents[1]
        / "artifacts/vendor-native-build/Release"
        / "wonderbane_extension_guard_upgrade_controller_test.exe"
    )
    if not exe.exists():
        pytest.skip("native fixture not built")
    state, command, response = [
        bytes.fromhex(line)
        for line in subprocess.check_output([str(exe), "wire"], text=True).splitlines()
    ]
    assert state == STATE.encode()
    assert command == Command(HOST, 1000, KEY, STATE).encode(Verb.UPGRADE)
    result = Receipt.decode(response)
    assert result == Receipt(KEY, HOST, 1000, Outcome.SUBMITTED, IN_FLIGHT, STATE, KEY)


class Transport:
    host_process_identity = NativeClientProcessIdentity(1, 1)
    host_lease_generation = 1

    def __init__(self, identity):
        self.commands = []
        self.mode = "normal"
        self.closed = False

    def submit(self, command, *, timeout_ms):
        self.commands.append(command)
        assert len(command.encode_slot(sequence=1, created_tick=100, deadline_tick=850)) == 768
        if self.mode == "timeout":
            raise NativeActionChannelTimeout("test")
        payload = raw_receipt(
            key=KEY if self.mode == "request" else command.payload.request_key,
            host=Host(2, 1, 1) if self.mode == "host" else HOST,
            window=2000 if self.mode == "window" else 1000,
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
            "native_guard_upgrade_receipt_v1",
            payload,
        )

    def close(self):
        self.closed = True


def test_session_correlation_and_upgrade_timeout_never_retries():
    with patch(
        "shadowbane_lab.client_extension.guard_upgrade_session.channel."
        "WindowsNativeActionCommandTransport",
        Transport,
    ):
        session = NativeGuardUpgradeSession(NativeClientProcessIdentity(988, 123), 1000)
        assert session.inspect().outcome == Outcome.OBSERVED
        for mode in ("request", "host", "window", "stage"):
            session._transport.mode = mode
            with pytest.raises(NativeActionChannelError):
                session.inspect()
        session._transport.mode = "timeout"
        before = len(session._transport.commands)
        with pytest.raises(NativeActionChannelTimeout):
            session.upgrade(STATE, KEY)
        assert len(session._transport.commands) == before + 1
        assert session._transport.commands[-1].kind == Verb.UPGRADE
        session.close()
        assert session._transport.closed
        with pytest.raises(NativeActionChannelError):
            session.inspect()
