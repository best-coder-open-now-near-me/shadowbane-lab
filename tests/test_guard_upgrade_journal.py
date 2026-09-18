import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.guard_spending_journal import (
    GuardSpendingJournal,
    GuardSpendingStopped,
)
from shadowbane_lab.client_extension.guard_upgrade_session import NativeGuardUpgradeSession
from shadowbane_lab.client_extension.guard_upgrade_wire import (
    IN_FLIGHT,
    UNRESOLVED,
    Command,
    Outcome,
    Receipt,
    Verb,
)
from tests.test_guard_upgrade_commands import HOST, KEY, STATE, Transport

IDENTITY = NativeClientProcessIdentity(988, 123)
COMMAND = Command(HOST, 1000, KEY, STATE)
SUBMITTED = Receipt(KEY, HOST, 1000, Outcome.SUBMITTED, IN_FLIGHT, STATE, KEY)
FINISHED = Receipt(
    str(uuid.uuid4()),
    HOST,
    1000,
    Outcome.OBSERVED,
    0,
    replace(STATE, funds=50, upgrading=1, control_flags=7),
    KEY,
)


def another():
    return replace(COMMAND, request_key=str(uuid.uuid4()))


def assert_blocked(journal, identity=IDENTITY):
    dispatch = Mock()
    with pytest.raises(GuardSpendingStopped):
        journal.submit(identity, another(), dispatch)
    dispatch.assert_not_called()


def test_intent_is_durable_before_dispatch_and_completion_allows_next_spend(tmp_path):
    journal = GuardSpendingJournal(tmp_path)

    def dispatch():
        pointer = json.loads(journal.active.read_text())
        record = json.loads(journal._path(KEY).read_text())
        assert pointer == {"request_key": KEY}
        assert record["submission"] is None and record["completion"] is None
        assert Command.decode(bytes.fromhex(record["command"]), Verb.UPGRADE) == COMMAND
        return SUBMITTED

    assert journal.submit(IDENTITY, COMMAND, dispatch) == SUBMITTED
    assert_blocked(GuardSpendingJournal(tmp_path))
    journal.observe(IDENTITY, FINISHED)
    record = json.loads(journal._path(KEY).read_text())
    assert Receipt.decode(bytes.fromhex(record["completion"])) == FINISHED
    fresh = another()
    journal.submit(IDENTITY, fresh, lambda: replace(SUBMITTED, request_key=fresh.request_key))
    assert_blocked(journal)


def test_same_uuid_never_repeats_even_after_completion(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    journal.observe(IDENTITY, FINISHED)
    dispatch = Mock()
    with pytest.raises(GuardSpendingStopped, match="already attempted"):
        journal.submit(IDENTITY, COMMAND, dispatch)
    dispatch.assert_not_called()


def test_lost_reply_stays_blocked_across_host_and_client_restart(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    dispatch = Mock(side_effect=TimeoutError("reply lost after submission"))
    with pytest.raises(TimeoutError):
        journal.submit(IDENTITY, COMMAND, dispatch)
    dispatch.assert_called_once()
    resumed = GuardSpendingJournal(tmp_path)
    resumed.observe(IDENTITY, FINISHED)
    assert_blocked(resumed)
    assert_blocked(resumed, NativeClientProcessIdentity(999, 456))
    assert json.loads(journal._path(KEY).read_text())["completion"] is None


@pytest.mark.parametrize(
    "receipt",
    [
        replace(FINISHED, flags=IN_FLIGHT),
        replace(FINISHED, flags=UNRESOLVED),
        replace(FINISHED, transition_request=str(uuid.uuid4())),
        replace(FINISHED, outcome=Outcome.UNCERTAIN),
        replace(FINISHED, snapshot=replace(FINISHED.snapshot, funds=49)),
        replace(FINISHED, snapshot=replace(FINISHED.snapshot, upgrading=0, control_flags=3)),
        replace(FINISHED, snapshot=replace(FINISHED.snapshot, rank=3)),
        replace(FINISHED, snapshot=replace(FINISHED.snapshot, upgrade_control=800)),
        replace(
            FINISHED,
            snapshot=replace(FINISHED.snapshot, navigation=replace(STATE.navigation, scene=2)),
        ),
        replace(
            FINISHED,
            snapshot=replace(
                FINISHED.snapshot, navigation=replace(STATE.navigation, building_id=124)
            ),
        ),
        replace(
            FINISHED,
            snapshot=replace(
                FINISHED.snapshot, navigation=replace(STATE.navigation, vendor_id=778)
            ),
        ),
        replace(FINISHED, host=replace(HOST, lease_generation=2)),
        replace(FINISHED, window=2000),
    ],
)
def test_partial_wrong_owner_and_uncertain_observations_never_clear_spending(tmp_path, receipt):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    journal.observe(IDENTITY, receipt)
    assert_blocked(journal)


def test_rank_increase_plus_exact_debit_completes_without_timer(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    completed = replace(FINISHED, snapshot=replace(STATE, rank=2, funds=50))
    journal.observe(IDENTITY, completed)
    assert json.loads(journal.active.read_text()) == {"request_key": None}


@pytest.mark.parametrize(
    "identity",
    [
        NativeClientProcessIdentity(989, 123),
        NativeClientProcessIdentity(988, 124),
    ],
)
def test_new_game_lifetime_cannot_complete_old_action(tmp_path, identity):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    journal.observe(identity, FINISHED)
    assert_blocked(journal, identity)


@pytest.mark.parametrize(
    "outcome", [Outcome.STALE, Outcome.UNAVAILABLE, Outcome.INVALID, Outcome.EXHAUSTED]
)
def test_proven_non_submission_releases_gate_but_not_request_identity(tmp_path, outcome):
    journal = GuardSpendingJournal(tmp_path)
    rejected = replace(SUBMITTED, outcome=outcome, flags=0)
    journal.submit(IDENTITY, COMMAND, lambda: rejected)
    assert json.loads(journal.active.read_text()) == {"request_key": None}
    fresh = another()
    journal.submit(IDENTITY, fresh, lambda: replace(SUBMITTED, request_key=fresh.request_key))
    assert_blocked(journal)


@pytest.mark.parametrize(
    "outcome", [Outcome.PENDING, Outcome.UNCERTAIN, Outcome.OBSERVED, Outcome.STALE]
)
def test_ambiguous_submission_never_releases_gate(tmp_path, outcome):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: replace(SUBMITTED, outcome=outcome, flags=UNRESOLVED))
    journal.observe(IDENTITY, FINISHED)
    assert_blocked(journal)


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_key", str(uuid.uuid4())),
        ("host", replace(HOST, lease_generation=2)),
        ("window", 2000),
    ],
)
def test_mismatched_submission_retains_pre_dispatch_intent(tmp_path, field, value):
    journal = GuardSpendingJournal(tmp_path)
    with pytest.raises(GuardSpendingStopped):
        journal.submit(IDENTITY, COMMAND, lambda: replace(SUBMITTED, **{field: value}))
    assert_blocked(journal)


@pytest.mark.parametrize("failure_at", [1, 2, 3])
def test_persistence_failure_never_causes_unrecorded_dispatch(tmp_path, failure_at):
    import shadowbane_lab.client_extension.guard_spending_journal as module

    journal = GuardSpendingJournal(tmp_path)
    original = module._write
    calls = 0

    def write(path, record):
        nonlocal calls
        calls += 1
        if calls == failure_at:
            raise OSError("disk write failed")
        original(path, record)

    dispatch = Mock(return_value=SUBMITTED)
    with patch.object(module, "_write", side_effect=write), pytest.raises(OSError):
        journal.submit(IDENTITY, COMMAND, dispatch)
    assert dispatch.call_count == int(failure_at == 3)
    if failure_at > 1:
        assert_blocked(GuardSpendingJournal(tmp_path))


@pytest.mark.parametrize(
    "damage", ["pointer", "missing_pointer", "record", "missing_record", "oversized"]
)
def test_corrupt_or_missing_journal_never_unlocks_spending(tmp_path, damage):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    if damage == "pointer":
        journal.active.write_text('{"wrong":true}')
    elif damage == "missing_pointer":
        journal.active.unlink()
    elif damage == "record":
        journal._path(KEY).write_text("{}")
    elif damage == "missing_record":
        journal._path(KEY).unlink()
    else:
        journal._path(KEY).write_text(" " * 8193)
    dispatch = Mock()
    with pytest.raises((GuardSpendingStopped, FileNotFoundError)):
        GuardSpendingJournal(tmp_path).submit(IDENTITY, another(), dispatch)
    dispatch.assert_not_called()


def test_two_callers_share_one_spending_gate(tmp_path):
    def attempt(_):
        journal = GuardSpendingJournal(tmp_path)
        command = another()
        try:
            return journal.submit(
                IDENTITY, command, lambda: replace(SUBMITTED, request_key=command.request_key)
            )
        except GuardSpendingStopped:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sum(outcome is not None for outcome in outcomes) == 1


def test_session_observation_allowed_but_spending_requires_journal():
    with patch(
        "shadowbane_lab.client_extension.guard_upgrade_session.channel.WindowsNativeActionCommandTransport",
        Transport,
    ):
        session = NativeGuardUpgradeSession(IDENTITY, 1000)
        session.inspect()
        before = len(session._transport.commands)
        with pytest.raises(GuardSpendingStopped, match="require"):
            session.upgrade(STATE, KEY)
        assert len(session._transport.commands) == before
        session.close()


def test_command_and_receipt_persistence_bytes_are_canonical():
    assert Command.decode(COMMAND.encode(Verb.UPGRADE), Verb.UPGRADE) == COMMAND
    assert Receipt.decode(FINISHED.encode()) == FINISHED
    data = bytearray(COMMAND.encode(Verb.UPGRADE))
    data[-1] = 1
    with pytest.raises(ValueError):
        Command.decode(bytes(data), Verb.UPGRADE)
    with pytest.raises(ValueError):
        Command.decode(bytes(data[:-1]), Verb.UPGRADE)


def test_unresolved_observation_is_durable_and_late_success_cannot_clear_it(tmp_path):
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    journal.observe(IDENTITY, replace(FINISHED, flags=UNRESOLVED))
    resumed = GuardSpendingJournal(tmp_path)
    resumed.observe(IDENTITY, FINISHED)
    assert_blocked(resumed)
    record = json.loads(journal._path(KEY).read_text())
    assert record["unresolved"] and record["completion"] is None


def test_session_upgrade_then_inspection_records_completion(tmp_path):
    class CompletingTransport(Transport):
        def submit(self, command, *, timeout_ms):
            result = super().submit(command, timeout_ms=timeout_ms)
            receipt = SUBMITTED if command.kind == Verb.UPGRADE else FINISHED
            receipt = replace(receipt, request_key=command.payload.request_key)
            return replace(result, movement_payload=receipt.encode())

    with patch(
        "shadowbane_lab.client_extension.guard_upgrade_session.channel."
        "WindowsNativeActionCommandTransport",
        CompletingTransport,
    ):
        journal = GuardSpendingJournal(tmp_path)
        session = NativeGuardUpgradeSession(IDENTITY, 1000, journal=journal)
        assert session.upgrade(STATE, KEY) == SUBMITTED
        assert_blocked(journal)
        assert session.inspect().snapshot == FINISHED.snapshot
        assert json.loads(journal.active.read_text()) == {"request_key": None}
        session.close()


@pytest.mark.parametrize("case", ["success", "unmarked", "scene", "building", "guard",
                                 "funds", "progress", "front", "uncertain", "host"])
def test_correlated_native_revisit_allows_only_exact_guard_and_debit(tmp_path, case):
    from shadowbane_lab.client_extension.guard_upgrade_wire import REOPENED

    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
    n = replace(STATE.navigation, building_hud=301, vendor_hud=401,
                selected_entry=501, front_hud=401)
    after = replace(FINISHED.snapshot, navigation=n, upgrade_control=601, progress_control=701)
    flags = REOPENED
    if case == "scene":
        after = replace(after, navigation=replace(n, scene=n.scene + 1))
    if case == "building":
        after = replace(after, navigation=replace(n, building_id=124))
    if case == "guard":
        after = replace(after, navigation=replace(n, vendor_id=778))
    if case == "funds":
        after = replace(after, funds=49)
    if case == "progress":
        after = replace(after, upgrading=0, control_flags=3)
    if case == "front":
        after = replace(after, navigation=replace(n, front_hud=999))
    if case == "unmarked":
        flags = 0
    if case == "uncertain":
        flags |= UNRESOLVED
    receipt = replace(FINISHED, snapshot=after, flags=flags)
    if case == "host":
        receipt = replace(receipt, host=replace(HOST, lease_generation=2))
    assert Receipt.decode(receipt.encode()) == receipt
    journal.observe(IDENTITY, receipt)
    if case == "success":
        GuardSpendingJournal(tmp_path).assert_idle()
    else:
        assert_blocked(GuardSpendingJournal(tmp_path))


def rebuilt_page_transaction():
    before = replace(STATE, navigation=replace(
        STATE.navigation, mode=0, front_hud=STATE.navigation.vendor_hud,
    ))
    after = replace(
        before, funds=before.funds - before.cost, upgrading=1, control_flags=7,
        upgrade_control=before.upgrade_control + 1,
        progress_control=before.progress_control + 1,
        navigation=replace(before.navigation, mode=6,
                           building_hud=before.navigation.building_hud + 1),
    )
    return (replace(COMMAND, expected=before), replace(SUBMITTED, snapshot=before),
            replace(FINISHED, snapshot=after))


@pytest.mark.parametrize("instant", [False, True])
def test_rebuilt_building_with_retained_guard_completes_once_across_restart(tmp_path, instant):
    command, submitted, finished = rebuilt_page_transaction()
    if instant:
        finished = replace(finished, snapshot=replace(
            finished.snapshot, rank=command.expected.rank + 1, upgrading=0, control_flags=3,
        ))
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, command, lambda: submitted)
    GuardSpendingJournal(tmp_path).observe(IDENTITY, finished)
    record = json.loads(journal._path(KEY).read_text())
    assert Receipt.decode(bytes.fromhex(record["submission"])) == submitted
    assert Receipt.decode(bytes.fromhex(record["completion"])) == finished
    GuardSpendingJournal(tmp_path).assert_idle()
    dispatch = Mock()
    with pytest.raises(GuardSpendingStopped, match="already attempted"):
        journal.submit(IDENTITY, command, dispatch)
    dispatch.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("scene", 2), ("root", 101), ("manager", 201), ("building_id", 124),
    ("vendor_id", 778), ("vendor_hud", 401), ("selected_entry", 501),
    ("front_hud", 301), ("mode", 0), ("building_hud", 300),
])
def test_rebuilt_page_wrong_owner_never_completes(tmp_path, field, value):
    command, submitted, finished = rebuilt_page_transaction()
    assert getattr(finished.snapshot.navigation, field) != value
    finished = replace(finished, snapshot=replace(
        finished.snapshot, navigation=replace(finished.snapshot.navigation, **{field: value}),
    ))
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, command, lambda: submitted)
    journal.observe(IDENTITY, finished)
    assert_blocked(GuardSpendingJournal(tmp_path))


@pytest.mark.parametrize("field,value", [
    ("cost", 101), ("funds", 150), ("funds", 49), ("upgrading", 0),
    ("control_flags", 3), ("rank", 3),
])
def test_rebuilt_page_partial_or_contradictory_response_stays_blocked(tmp_path, field, value):
    command, submitted, finished = rebuilt_page_transaction()
    finished = replace(finished, snapshot=replace(finished.snapshot, **{field: value}))
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, command, lambda: submitted)
    journal.observe(IDENTITY, finished)
    assert_blocked(GuardSpendingJournal(tmp_path))


@pytest.mark.parametrize("flags", [IN_FLIGHT, UNRESOLVED, IN_FLIGHT | UNRESOLVED])
def test_rebuilt_page_cannot_clear_native_pending_or_uncertain_receipt(tmp_path, flags):
    command, submitted, finished = rebuilt_page_transaction()
    journal = GuardSpendingJournal(tmp_path)
    journal.submit(IDENTITY, command, lambda: submitted)
    journal.observe(IDENTITY, replace(finished, flags=flags))
    assert_blocked(GuardSpendingJournal(tmp_path))
