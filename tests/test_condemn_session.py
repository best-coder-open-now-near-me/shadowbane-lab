import json
import uuid
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension import condemn_session as module
from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeActionResult,
    NativeActionResultStage,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.condemn_progress import (
    CondemnProgressStopped,
    CondemnProgressStore,
)
from shadowbane_lab.client_extension.condemn_wire import (
    IN_FLIGHT,
    READY,
    Outcome,
    Phase,
    Receipt,
    Verb,
)
from tests.test_condemn_evidence import LIFE, snapshot, triple
from tests.test_condemn_transaction import BEFORE, HOST, LIST, ROW, TARGET


class Stream:
    def __init__(self):
        self.records = []
        self.fail = False

    @property
    def sequence(self):
        return len(self.records)

    def add(self, op):
        self.records.extend(
            triple(self.sequence + 1, operation=op, building=(100, 8) if op == 17 else (0, 0))
        )


class Reader:
    stream = None

    def __init__(self, pid, creation, memory):
        assert (pid, creation) == (LIFE.process_id, LIFE.creation)
        self.last = None

    def drain(self):
        if self.stream.fail:
            raise OSError("reader failed")
        result = snapshot(
            self.stream.records[self.last or 0 :],
            sequence=self.stream.sequence,
            initial_history=self.last is None,
        )
        self.last = self.stream.sequence
        return result


class Transport:
    host_process_identity = NativeClientProcessIdentity(HOST.process_id, HOST.creation_filetime)
    host_lease_generation = HOST.lease_generation
    stream = None
    progress = None

    def __init__(self, identity):
        self.identity, self.commands = identity, []
        self.phase, self.original = None, None
        self.mode, self.closed = "normal", False

    def renew_lease(self):
        pass

    def close(self):
        self.closed = True

    def submit(self, command, timeout_ms):
        self.commands.append(command)
        assert (
            len(
                command.encode_slot(
                    sequence=len(self.commands), created_tick=100, deadline_tick=100 + timeout_ms
                )
            )
            == 768
        )
        c = command.payload
        mutating = command.kind == Verb.ENSURE or c.transition_request is not None
        if mutating:
            a = json.loads(self.progress.path.read_bytes())["attempts"][-1]
            assert a["pending"] == c.encode(command.kind).hex()
        if self.mode == "timeout":
            raise NativeActionChannelTimeout("reply lost")
        if command.kind == Verb.ENSURE:
            self.original = c.request_key
            self.phase = Phase.EXISTING if self.mode == "existing" else Phase.OPENING
        elif c.transition_request:
            assert c.transition_request == self.original
            self.phase = {
                Phase.OPENING: Phase.ADDING,
                Phase.ADDING: Phase.ENABLING,
                Phase.ENABLING: Phase.VERIFIED,
            }[self.phase]
            if self.phase == Phase.ADDING:
                self.stream.add(12)
            if self.phase == Phase.VERIFIED:
                self.stream.add(17)
        p = self.phase or Phase.IDLE
        state = {
            Phase.IDLE: BEFORE,
            Phase.OPENING: BEFORE,
            Phase.ADDING: LIST,
            Phase.ENABLING: ROW,
            Phase.VERIFIED: replace(ROW, enabled=1),
            Phase.EXISTING: replace(ROW, enabled=1),
        }[p]
        flags = READY if p == Phase.IDLE else IN_FLIGHT if p.value in (1, 2, 3) else 0
        tick = (
            0
            if p in (Phase.IDLE, Phase.EXISTING)
            else 995
            if p == Phase.OPENING
            else 1000
            if p == Phase.ADDING
            else 1003
        )
        r = Receipt(
            c.request_key,
            c.host,
            c.window,
            Outcome.SUBMITTED
            if command.kind == Verb.ENSURE and p != Phase.EXISTING
            else Outcome.OBSERVED,
            flags,
            state,
            TARGET,
            TARGET if self.original else None,
            self.original,
            p,
            tick,
            3 if p in (Phase.ENABLING, Phase.VERIFIED) else 0,
            6 if p == Phase.VERIFIED else 0,
        )
        if self.mode == "wrong_request":
            r = replace(r, request_key=str(uuid.uuid4()))
        if self.mode == "wrong_host":
            r = replace(r, host=replace(HOST, lease_generation=9))
        if self.mode == "wrong_window":
            r = replace(r, window=1001)
        if self.mode == "wrong_scope":
            r = replace(
                r,
                target=replace(TARGET, scope=4),
                transition_target=replace(TARGET, scope=4) if self.original else None,
            )
        if self.mode == "reader_failure":
            self.stream.fail = True
        return NativeActionResult(
            1,
            command.command_id,
            len(self.commands),
            NativeActionResultStage.FAILED
            if self.mode == "wrong_stage"
            else NativeActionResultStage.SUBMITTED_TO_CLIENT,
            0,
            1010 + len(self.commands),
            0 if self.mode == "wrong_thread" else 5760,
            "unsupported" if self.mode == "unknown" else "native_condemn_receipt_v1",
            r.encode(),
        )


@pytest.fixture
def session(tmp_path, monkeypatch):
    stream = Stream()
    progress = CondemnProgressStore(tmp_path)
    monkeypatch.setattr(Transport, "stream", stream)
    monkeypatch.setattr(Transport, "progress", progress)
    monkeypatch.setattr(Reader, "stream", stream)
    monkeypatch.setattr(module.channel, "WindowsNativeActionCommandTransport", Transport)
    monkeypatch.setattr(module, "CondemnResponseReader", Reader)
    monkeypatch.setattr(module, "WindowsSharedMemorySnapshotReader", lambda: object())
    s = module.NativeCondemnSession(
        NativeClientProcessIdentity(LIFE.process_id, LIFE.creation), 1000, progress=progress
    )
    yield s
    s.close()


def test_host_session_completes_open_add_enable_with_original_response_window(session):
    assert session.inspect(TARGET).flags & READY
    request = str(uuid.uuid4())
    assert session.ensure(TARGET, BEFORE, request).phase == Phase.OPENING
    assert session.advance().phase == Phase.ADDING
    assert session.advance().phase == Phase.ENABLING
    assert session.advance().phase == Phase.VERIFIED
    session._progress.assert_idle()
    assert session._progress.verified_native_targets(LIFE) == {TARGET}
    commands = session._transport.commands
    assert [c.kind for c in commands] == [
        Verb.INSPECT,
        Verb.ENSURE,
        Verb.INSPECT,
        Verb.INSPECT,
        Verb.INSPECT,
    ]
    assert all(c.payload.transition_request == request for c in commands[2:])
    assert len({c.payload.request_key for c in commands}) == 5


@pytest.mark.parametrize("where", ["inspect", "ensure", "advance"])
def test_timeout_never_retries_or_replays_a_continuation(session, where):
    if where == "advance":
        session.ensure(TARGET, BEFORE, str(uuid.uuid4()))
    previous = len(session._transport.commands)
    session._transport.mode = "timeout"
    with pytest.raises(NativeActionChannelTimeout):
        if where == "inspect":
            session.inspect(TARGET)
        elif where == "ensure":
            session.ensure(TARGET, BEFORE, str(uuid.uuid4()))
        else:
            session.advance()
    assert len(session._transport.commands) == previous + 1
    if where != "inspect":
        with pytest.raises(CondemnProgressStopped):
            session.advance()
        assert len(session._transport.commands) == previous + 1
        assert session._progress.read()["attempts"][-1]["pending"]


@pytest.mark.parametrize(
    "mode",
    [
        "wrong_request",
        "wrong_host",
        "wrong_window",
        "wrong_scope",
        "wrong_stage",
        "wrong_thread",
        "unknown",
        "reader_failure",
    ],
)
def test_bad_or_lost_receipt_retains_intent_and_stops_without_retry(session, mode):
    session._transport.mode = mode
    with pytest.raises((NativeActionChannelError, ValueError, RuntimeError)):
        session.ensure(TARGET, BEFORE, str(uuid.uuid4()))
    assert len(session._transport.commands) == 1
    a = session._progress.read()["attempts"][0]
    assert a["state"] == "intent" and a["pending"]
    with pytest.raises(CondemnProgressStopped):
        session.advance()
    assert len(session._transport.commands) == 1


def test_existing_enabled_state_does_not_send_enable_or_claim_new_response(session):
    session._transport.mode = "existing"
    assert session.ensure(TARGET, BEFORE, str(uuid.uuid4())).phase == Phase.EXISTING
    assert session._progress.read()["attempts"][0]["state"] == "already_enabled"
    assert len(session._transport.commands) == 1


def test_new_host_generation_cannot_advance_and_does_not_send(session):
    session.ensure(TARGET, BEFORE, str(uuid.uuid4()))
    session._transport.host_lease_generation += 1
    with pytest.raises(CondemnProgressStopped):
        session.advance()
    assert len(session._transport.commands) == 1


def test_pending_session_cannot_switch_targets_or_be_replaced(session):
    session.ensure(TARGET, BEFORE, str(uuid.uuid4()))
    with pytest.raises(CondemnProgressStopped):
        session.inspect(replace(TARGET, scope=4))
    new = module.NativeCondemnSession(session.identity, session.window, progress=session._progress)
    try:
        with pytest.raises(CondemnProgressStopped):
            new.ensure(TARGET, BEFORE, str(uuid.uuid4()))
        with pytest.raises(CondemnProgressStopped):
            new.advance()
        assert new._transport.commands == []
    finally:
        new.close()


def test_close_stops_new_actions_and_preserves_pending_journal(session):
    session.ensure(TARGET, BEFORE, str(uuid.uuid4()))
    session.close()
    with pytest.raises(NativeActionChannelError):
        session.advance()
    assert session._progress.read()["active"] is not None
    assert session._transport.closed


def test_ready_inspection_cannot_relabel_another_scope(session):
    session._transport.mode = "wrong_scope"
    with pytest.raises(NativeActionChannelError):
        session.inspect(TARGET)
    assert len(session._transport.commands) == 1
    session._progress.assert_idle()
