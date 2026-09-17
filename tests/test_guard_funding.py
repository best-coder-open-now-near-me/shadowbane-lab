import json
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.guard_funding_session import NativeGuardFundingSession
from shadowbane_lab.client_extension.guard_funding_wire import (
    IN_FLIGHT,
    UNRESOLVED,
    Command,
    Direction,
    Host,
    Outcome,
    Receipt,
    Snapshot,
    Verb,
)
from shadowbane_lab.client_extension.guard_spending_journal import (
    GuardSpendingJournal,
    GuardSpendingStopped,
)
from tests.test_guard_upgrade_journal import COMMAND as UPGRADE
from tests.test_guard_upgrade_journal import SUBMITTED as UPGRADE_REPLY

HOST = Host(1, 1, 1)
KEY = "01000000-0000-0000-0000-000000000000"
IDENTITY = NativeClientProcessIdentity(988, 123)
STATE = Snapshot(
    1,
    1,
    100,
    200,
    300,
    1,
    400,
    500,
    600,
    700,
    42,
    1,
    800,
    1000,
    50,
    500,
    900,
    950,
    950,
    1100,
    1200,
    1300,
)
COMMAND = Command(HOST, 1000, KEY, STATE, 1, 100)
SUBMITTED = Receipt(KEY, HOST, 1000, Outcome.SUBMITTED, IN_FLIGHT, STATE, KEY)
FINISHED = Receipt(
    str(uuid.uuid4()),
    HOST,
    1000,
    Outcome.OBSERVED,
    0,
    replace(
        STATE, balance=900, purse=600, quote=0, limit=0, entered=0, accept=0, cancel=0, helper=0
    ),
    KEY,
)


def test_native_host_funding_bytes_agree():
    exe = (
        Path(__file__).resolve().parents[1]
        / "artifacts/vendor-native-build/Release"
        / "wonderbane_extension_guard_funding_controller_test.exe"
    )
    if not exe.exists():
        pytest.skip("native funding fixture not built")
    state, command, receipt = [
        bytes.fromhex(line)
        for line in subprocess.check_output([str(exe), "wire"], text=True).splitlines()
    ]
    assert state == STATE.encode()
    assert command == COMMAND.encode(Verb.TRANSFER)
    assert Receipt.decode(receipt) == SUBMITTED
    assert Receipt.decode(SUBMITTED.encode()) == SUBMITTED
    assert Command.decode(command, Verb.TRANSFER) == COMMAND


@pytest.mark.parametrize(
    "change",
    [
        {"amount": 0},
        {"amount": 951},
        {"amount": True},
        {"direction": 2},
        {"expected": replace(STATE, reserve=51)},
        {"expected": replace(STATE, source_type=8)},
        {"expected": replace(STATE, purse=2**31 - 1)},
        {"expected": replace(STATE, character_id=0)},
        {"expected": replace(STATE, quote=0)},
        {"expected": replace(STATE, helper=1200)},
        {"expected": replace(STATE, entered=951)},
        {"window": 0},
    ],
)
def test_invalid_funding_is_rejected_before_transport(change):
    with pytest.raises(ValueError):
        replace(COMMAND, **change).encode(Verb.TRANSFER)


def test_structure_receipt_requires_exact_debit_and_credit():
    before = replace(
        STATE,
        source_object=0,
        source_type=8,
        direction=2,
        resource=0,
        reserve=0,
        limit=500,
        entered=500,
    )
    command = replace(COMMAND, expected=before, direction=2)
    after = replace(
        before, balance=1100, purse=400, quote=0, limit=0, entered=0, accept=0, cancel=0, helper=0
    )
    assert command.confirmed(after)
    assert not command.confirmed(replace(after, purse=500))
    assert not command.confirmed(replace(after, balance=1000))
    assert not command.confirmed(replace(after, source_id=701))
    with pytest.raises(ValueError):
        replace(command, expected=replace(before, purse=499)).encode(Verb.TRANSFER)


@pytest.mark.parametrize("offset", [0, 575])
def test_corrupt_commands_rejected(offset):
    raw = bytearray(COMMAND.encode(Verb.TRANSFER))
    raw[offset] = 0 if offset == 0 else 1
    with pytest.raises(ValueError):
        Command.decode(bytes(raw), Verb.TRANSFER)


def assert_blocked(journal, command):
    command = replace(command, request_key=str(uuid.uuid4()))
    dispatch = Mock()
    with pytest.raises(GuardSpendingStopped):
        journal.submit(IDENTITY, command, dispatch)
    dispatch.assert_not_called()


def test_withdrawal_blocks_upgrade_and_upgrade_blocks_deposit_across_restart(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    resumed = GuardSpendingJournal(tmp_path)
    assert_blocked(resumed, UPGRADE)
    assert_blocked(
        resumed,
        replace(
            COMMAND,
            direction=2,
            expected=replace(
                STATE,
                source_object=0,
                source_type=8,
                resource=0,
                reserve=0,
                direction=2,
                limit=500,
                entered=500,
            ),
        ),
    )
    resumed.observe(IDENTITY, FINISHED)
    upgrade = replace(UPGRADE, request_key=str(uuid.uuid4()))
    resumed.submit(
        IDENTITY, upgrade, lambda: replace(UPGRADE_REPLY, request_key=upgrade.request_key)
    )
    assert_blocked(GuardSpendingJournal(tmp_path), COMMAND)


@pytest.mark.parametrize("damage", ["lost_reply", "wrong_kind", "unresolved"])
def test_transfer_uncertainty_survives_restart_and_late_success(tmp_path, damage):
    journal = GuardSpendingJournal(tmp_path)
    if damage == "lost_reply":
        with pytest.raises(TimeoutError):
            journal.submit(IDENTITY, COMMAND, Mock(side_effect=TimeoutError()))
    elif damage == "wrong_kind":
        with pytest.raises(GuardSpendingStopped):
            journal.submit(IDENTITY, COMMAND, lambda: UPGRADE_REPLY)
    else:
        journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
        journal.observe(IDENTITY, replace(FINISHED, flags=UNRESOLVED))
    resumed = GuardSpendingJournal(tmp_path)
    resumed.observe(IDENTITY, FINISHED)
    assert_blocked(resumed, COMMAND)
    assert_blocked(resumed, UPGRADE)


@pytest.mark.parametrize(
    "change",
    [
        {"snapshot": replace(FINISHED.snapshot, balance=901)},
        {"snapshot": replace(FINISHED.snapshot, purse=599)},
        {"snapshot": replace(FINISHED.snapshot, reserve=51)},
        {"snapshot": replace(FINISHED.snapshot, actor=201)},
        {"snapshot": replace(FINISHED.snapshot, source_id=701)},
        {"transition_request": str(uuid.uuid4())},
        {"flags": IN_FLIGHT},
        {"host": replace(HOST, lease_generation=2)},
        {"window": 1001},
    ],
)
def test_unrelated_or_partial_transfer_receipts_never_complete(tmp_path, change):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    journal.observe(IDENTITY, replace(FINISHED, **change))
    assert_blocked(journal, UPGRADE)
    record = json.loads(journal._path(KEY).read_text())
    assert record["operation"] == "transfer" and record["completion"] is None


class Transport:
    host_process_identity = NativeClientProcessIdentity(1, 1)
    host_lease_generation = 1

    def __init__(self, identity):
        self.commands = []
        self.mode = "normal"

    def submit(self, command, *, timeout_ms):
        self.commands.append(command)
        assert len(command.encode_slot(sequence=1, created_tick=100, deadline_tick=850)) == 768
        if self.mode == "timeout":
            raise NativeActionChannelTimeout("reply lost")
        receipt = SUBMITTED if command.kind == Verb.TRANSFER else FINISHED
        receipt = replace(receipt, request_key=command.payload.request_key)
        if self.mode == "host":
            receipt = replace(receipt, host=Host(2, 1, 1))
        return NativeActionResult(
            1,
            command.command_id,
            1,
            NativeActionResultStage.SUBMITTED_TO_CLIENT,
            0,
            100,
            5760,
            "native_guard_funding_receipt_v1",
            receipt.encode(),
        )

    def close(self):
        pass


def session(tmp_path):
    with patch(
        "shadowbane_lab.client_extension.guard_funding_session.channel.WindowsNativeActionCommandTransport",
        Transport,
    ):
        return NativeGuardFundingSession(IDENTITY, 1000, journal=GuardSpendingJournal(tmp_path))


def test_session_keeps_submission_separate_from_observed_transfer(tmp_path):
    client = session(tmp_path)
    assert client.transfer(STATE, 100, KEY) == SUBMITTED
    assert_blocked(client._journal, UPGRADE)
    assert client.inspect(Direction.WAREHOUSE).snapshot == FINISHED.snapshot
    assert json.loads(client._journal.active.read_text()) == {"request_key": None}
    client.close()


def test_timeout_never_retries_or_allows_new_request(tmp_path):
    client = session(tmp_path)
    client._transport.mode = "timeout"
    with pytest.raises(NativeActionChannelTimeout):
        client.transfer(STATE, 100, KEY)
    with pytest.raises(GuardSpendingStopped):
        client.transfer(STATE, 100, str(uuid.uuid4()))
    assert len(client._transport.commands) == 1
    client.close()


def test_inspection_correlation_and_no_journal_cannot_spend(tmp_path):
    client = session(tmp_path)
    client._transport.mode = "host"
    with pytest.raises(NativeActionChannelError):
        client.inspect(Direction.WAREHOUSE)
    client._journal = None
    before = len(client._transport.commands)
    with pytest.raises(GuardSpendingStopped):
        client.transfer(STATE, 100, KEY)
    assert len(client._transport.commands) == before
    client.close()
