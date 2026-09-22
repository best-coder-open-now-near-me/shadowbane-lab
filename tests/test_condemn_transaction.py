import json
import uuid
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.condemn_evidence import ResponseWindow
from shadowbane_lab.client_extension.condemn_progress import (
    CondemnProgressStopped,
    CondemnProgressStore,
)
from shadowbane_lab.client_extension.condemn_transaction import Observation
from shadowbane_lab.client_extension.condemn_wire import (
    IN_FLIGHT,
    UNRESOLVED,
    Command,
    Outcome,
    Phase,
    Receipt,
    Snapshot,
    Target,
    Verb,
)
from shadowbane_lab.client_extension.movement_wire import Host
from tests.test_condemn_evidence import LIFE, snapshot, triple

TARGET = Target((100, 8), (200, 23), 5)
HOST = Host(123, 7, 456)
BEFORE = Snapshot(
    scene=5,
    revision=1,
    local=(20, 53),
    root=0x10000,
    manager=0x30000,
    building_hud=0x15000,
    front=0x15000,
    open_button=0x16000,
    building=(100, 8),
)
LIST = replace(BEFORE, kos=0x20000, list_control=0x21000, front=0x20000, context=(100, 8))
ROW = replace(LIST, entry=0x22000, row=0x23000, entry_key=(200, 23), count=1)


class Flow:
    def __init__(self, path):
        self.store = CondemnProgressStore(path)
        self.window = ResponseWindow(LIFE, snapshot(initial_history=True))
        self.command = Command(HOST, 1000, str(uuid.uuid4()), TARGET, BEFORE)
        self.calls = []
        self.before_dispatch = None
        self.current_command = self.command

    def observation(
        self,
        phase,
        state,
        *,
        tick=1000,
        observed=1004,
        response=None,
        outcome=None,
        floor=0,
        complete=0,
    ):
        c = self.current_command
        receipt = Receipt(
            c.request_key,
            c.host,
            c.window,
            outcome or (Outcome.SUBMITTED if c == self.command else Outcome.OBSERVED),
            0
            if phase in (Phase.VERIFIED, Phase.EXISTING)
            else IN_FLIGHT | (UNRESOLVED if phase == Phase.UNCERTAIN else 0),
            state,
            c.target,
            c.target,
            self.command.request_key,
            phase,
            tick,
            floor,
            complete,
        )
        return Observation(receipt, observed, response)

    def dispatch(self, observation):
        saved = json.loads(self.store.path.read_bytes())
        a = saved["attempts"][-1]
        assert saved["active"] == self.command.request_key and a["pending"] is not None
        verb = Verb.ENSURE if not a["polls"] else Verb.INSPECT
        assert Command.decode(bytes.fromhex(a["pending"]), verb) == self.current_command
        self.calls.append(self.current_command.request_key)
        if self.before_dispatch:
            self.before_dispatch()
        return observation

    def start(self, phase=Phase.OPENING, state=BEFORE, **kwargs):
        observation = self.observation(phase, state, **kwargs)
        return self.store.submit_native(
            self.command, self.window, lambda: self.dispatch(observation)
        )

    def advance(self, phase, state, **kwargs):
        self.current_command = Command(
            HOST, 1000, str(uuid.uuid4()), TARGET, transition_request=self.command.request_key
        )
        observation = self.observation(phase, state, **kwargs)
        return self.store.continue_native(
            self.current_command, self.window, lambda: self.dispatch(observation)
        )

    def enable(self):
        self.start(tick=995)
        self.advance(Phase.ADDING, LIST, tick=996)
        self.advance(Phase.ENABLING, ROW, tick=1000)

    def complete(self):
        (response,) = self.window.consume(snapshot(triple()))
        self.advance(Phase.VERIFIED, replace(ROW, enabled=1), response=response, complete=3)
        return response


def test_complete_composite_retains_boundaries_and_confirmed_progress(tmp_path):
    f = Flow(tmp_path)
    f.enable()
    f.complete()
    recovered = CondemnProgressStore(tmp_path)
    recovered.assert_idle()
    assert recovered.verified_native_targets(LIFE) == {TARGET}
    assert not recovered.verified_native_targets(replace(LIFE, creation=12))
    assert not recovered.verified_targets(LIFE)
    a = recovered.read()["attempts"][0]
    assert a["state"] == "state_verified" and len(a["boundaries"]) == 4 and len(a["polls"]) == 3
    assert len(f.calls) == 4 and len(set(f.calls)) == 4
    assert not f.store._windows


def test_idle_polls_are_bounded_without_repeating_full_boundary_history(tmp_path):
    f = Flow(tmp_path)
    f.start(tick=995)
    for _ in range(10):
        f.advance(Phase.OPENING, BEFORE, tick=995)
    a = f.store.read()["attempts"][0]
    assert len(a["polls"]) == 10 and len(a["boundaries"]) == 1


@pytest.mark.parametrize("at", ["ensure", "continue"])
@pytest.mark.parametrize("failure", ["before_write", "dispatch", "receipt_write"])
def test_write_ahead_failure_or_lost_reply_never_replays(tmp_path, monkeypatch, at, failure):
    f = Flow(tmp_path)
    if at == "continue":
        f.start(tick=995)
    original = f.store._write
    calls = len(f.calls)
    writes = 0

    def write(record):
        nonlocal writes
        writes += 1
        if failure == "before_write" and writes == 1 or failure == "receipt_write" and writes == 2:
            raise OSError("storage failed")
        original(record)

    monkeypatch.setattr(f.store, "_write", write)
    if failure == "dispatch":
        f.before_dispatch = lambda: (_ for _ in ()).throw(TimeoutError("lost reply"))
    with pytest.raises(OSError):
        if at == "ensure":
            f.start()
        else:
            f.advance(Phase.ADDING, LIST, tick=996)
    assert len(f.calls) == calls + (failure != "before_write")
    if failure != "before_write":
        saved = CondemnProgressStore(tmp_path).read()
        assert saved["active"] == f.command.request_key and saved["attempts"][0]["pending"]
        with pytest.raises(CondemnProgressStopped):
            f.advance(Phase.ADDING, LIST, tick=996)
        assert len(f.calls) == calls + 1


def test_restart_and_window_replacement_cannot_take_over_pending_transaction(tmp_path):
    f = Flow(tmp_path)
    f.start(tick=995)
    command = Command(
        HOST, 1000, str(uuid.uuid4()), TARGET, transition_request=f.command.request_key
    )
    for store, window in [
        (CondemnProgressStore(tmp_path), f.window),
        (f.store, ResponseWindow(LIFE, snapshot())),
    ]:
        with pytest.raises(CondemnProgressStopped):
            store.continue_native(command, window, lambda: pytest.fail("replayed"))


@pytest.mark.parametrize("change", ["producer", "window", "scope", "request", "transition"])
def test_continuation_owner_and_fresh_uuid_are_required_before_dispatch(tmp_path, change):
    f = Flow(tmp_path)
    f.start(tick=995)
    c = Command(HOST, 1000, str(uuid.uuid4()), TARGET, transition_request=f.command.request_key)
    if change == "producer":
        c = replace(c, host=replace(HOST, lease_generation=8))
    if change == "window":
        c = replace(c, window=2000)
    if change == "scope":
        c = replace(c, target=replace(TARGET, scope=4))
    if change == "request":
        c = replace(c, request_key=f.command.request_key)
    if change == "transition":
        c = replace(c, transition_request=str(uuid.uuid4()))
    with pytest.raises(CondemnProgressStopped):
        f.store.continue_native(c, f.window, lambda: pytest.fail("invalid dispatch"))
    assert len(f.calls) == 1


@pytest.mark.parametrize(
    "case",
    [
        "wrong_building",
        "old_floor",
        "wrong_entry",
        "unkeyed",
        "disabled_row",
        "changed_root",
        "wrong_sequence",
        "not_drained",
    ],
)
def test_keyed_reply_and_fresh_scoped_row_are_both_required(tmp_path, case):
    f = Flow(tmp_path)
    f.enable()
    from shadowbane_lab.client_extension.condemn_evidence import Response, canonical

    records = triple(
        building=(101, 8)
        if case == "wrong_building"
        else (0, 0)
        if case == "unkeyed"
        else (100, 8),
        entry=(201, 23) if case == "wrong_entry" else (200, 23),
    )
    if case == "old_floor":
        for record in records:
            record["tick_ms"] = 999
    response = Response(LIFE, canonical(records))
    if case != "not_drained":
        (response,) = f.window.consume(snapshot(records))
    row = replace(ROW, enabled=int(case != "disabled_row"))
    if case == "changed_root":
        row = replace(row, root=row.root + 4)
    with pytest.raises((CondemnProgressStopped, ValueError)):
        f.advance(
            Phase.VERIFIED, row, response=response, complete=6 if case == "wrong_sequence" else 3
        )
    assert f.store.read()["active"] == f.command.request_key
    assert f.store.read()["attempts"][0]["pending"]


def test_existing_enabled_row_does_not_require_or_claim_new_response(tmp_path):
    f = Flow(tmp_path)
    f.start(Phase.EXISTING, replace(ROW, enabled=1), tick=0)
    a = f.store.read()["attempts"][0]
    assert a["state"] == "already_enabled" and not a["completion"]
    assert f.store.verified_native_targets(LIFE) == {TARGET}


def test_uncertain_native_result_keeps_barrier(tmp_path):
    f = Flow(tmp_path)
    f.start(Phase.UNCERTAIN, BEFORE, outcome=Outcome.UNCERTAIN)
    assert f.store.read()["attempts"][0]["state"] == "uncertain"
    with pytest.raises(CondemnProgressStopped):
        f.advance(Phase.ADDING, LIST)


def test_known_uninvoked_result_can_close_without_claiming_progress(tmp_path):
    f = Flow(tmp_path)
    receipt = Receipt(f.command.request_key, HOST, 1000, Outcome.UNAVAILABLE, 0, Snapshot())
    f.store.submit_native(f.command, f.window, lambda: Observation(receipt, 1000))
    f.store.assert_idle()
    assert f.store.read()["attempts"][0]["state"] == "not_submitted"
    assert not f.store.verified_native_targets(LIFE)


def test_legacy_and_native_intents_share_one_barrier_and_history(tmp_path):
    from tests.test_condemn_evidence import TARGET as LEGACY_TARGET
    from tests.test_condemn_progress import complete, row, setup

    store, window, request, receipt = setup(tmp_path)
    store.submit(request, LEGACY_TARGET, window, row(False), lambda: receipt)
    f = Flow(tmp_path)
    with pytest.raises(CondemnProgressStopped):
        f.start()
    complete(store, window, request)
    f = Flow(tmp_path)
    f.start()
    with pytest.raises(CondemnProgressStopped):
        store.submit(str(uuid.uuid4()), LEGACY_TARGET, window, row(False), lambda: receipt)
    record = f.store.read()
    assert record["schema_version"] == 2 and len(record["attempts"]) == 2
    assert store.verified_targets(LIFE) == {LEGACY_TARGET}


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda a: a.update(pending=None),
        lambda a: a.update(state="state_verified"),
        lambda a: a["lifetime"].update(scene_epoch=7),
        lambda a: a["polls"].append(a["request"]),
        lambda a: a["boundaries"].append(a["boundaries"][0]),
    ],
)
def test_corrupt_saved_native_state_blocks_without_dispatch(tmp_path, corrupt):
    f = Flow(tmp_path)
    f.start()
    # A real interrupted continuation provides the persisted pending case.
    f.before_dispatch = lambda: (_ for _ in ()).throw(TimeoutError("lost"))
    with pytest.raises(TimeoutError):
        f.advance(Phase.ADDING, LIST)
    record = json.loads(f.store.path.read_bytes())
    corrupt(record["attempts"][0])
    f.store.path.write_text(json.dumps(record))
    with pytest.raises(CondemnProgressStopped):
        CondemnProgressStore(tmp_path).read()


@pytest.mark.parametrize("field", ["sha256", "response", "boundary"])
def test_completed_saved_proof_is_revalidated_on_restart(tmp_path, field):
    f = Flow(tmp_path)
    f.enable()
    (response,) = f.window.consume(snapshot(triple()))
    f.advance(Phase.VERIFIED, replace(ROW, enabled=1), response=response, complete=3)
    record = json.loads(f.store.path.read_bytes())
    a = record["attempts"][0]
    if field == "sha256":
        a["completion"]["sha256"] = "0" * 64
    elif field == "response":
        a["completion"]["response"][0]["tick_ms"] = 999
    else:
        a["boundaries"] = [
            b
            for b in a["boundaries"]
            if Receipt.decode(bytes.fromhex(b["receipt"])).phase != Phase.ENABLING
        ]
    f.store.path.write_text(json.dumps(record))
    with pytest.raises(CondemnProgressStopped):
        CondemnProgressStore(tmp_path).verified_native_targets(LIFE)
