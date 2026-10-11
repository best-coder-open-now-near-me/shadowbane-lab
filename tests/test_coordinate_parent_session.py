"""Correlated parent succession keeps one coordinate operation, never actor authority."""
import threading
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension import movement_wire as wire
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementCleanupPending,
    NativeMovementError,
    NativeMovementSession,
)
from shadowbane_lab.manager.movement import OperationMovement
from shadowbane_lab.manager.operation import WorkerOperationKind


@pytest.fixture
def native(monkeypatch):
    identity = channel.NativeClientProcessIdentity(101, 1001)
    state = SimpleNamespace(
        grant=wire.Grant(1, 1), flags=3 | wire.COORDINATE_PARENT_CAPABLE,
        opened=[], commands=[], renewals=0, pending=False, lose=False,
        cache={}, wrong=None, now=0.0, closed=False, destination_race=None,
    )

    class Transport:
        def __init__(self, client):
            assert client == identity
            state.opened.append(self)
            self.host_process_identity = channel.NativeClientProcessIdentity(202, 2002)
            self.host_lease_generation = 3

        def submit(self, command, *, timeout_ms):
            assert 0 < timeout_ms <= 750
            state.commands.append(command)
            p, verb = command.payload, command.kind
            encoded = p.encode(verb)
            if p.request_key in state.cache:
                prior, payload = state.cache[p.request_key]
                assert encoded == prior
            else:
                outcome = wire.Outcome.ACCEPTED
                if verb in (wire.Verb.ACQUIRE, wire.Verb.ACQUIRE_COORDINATE):
                    state.grant = wire.Grant(2, 1, wire.Owner.AUTOMATION,
                                            p.worker_id, p.operation_id)
                elif verb in (wire.Verb.CONTINUE_PARENT, wire.Verb.PAUSE):
                    assert state.grant.generation >= p.expected.generation
                    if state.pending:
                        outcome = wire.Outcome.STOP_FAILED
                        state.flags = 65 | wire.COORDINATE_PARENT_CAPABLE
                    else:
                        state.flags = 3 | wire.COORDINATE_PARENT_CAPABLE
                elif verb is wire.Verb.DESTINATION and state.destination_race is not None:
                    state.parent()
                    outcome = state.destination_race
                    state.destination_race = None
                    if outcome is wire.Outcome.STOP_FAILED:
                        state.flags = 65 | wire.COORDINATE_PARENT_CAPABLE
                elif verb is wire.Verb.STOP:
                    state.grant = wire.Grant(state.grant.generation + 1, state.grant.scene)
                payload = wire.Receipt(
                    state.wrong or state.grant, p.request_key, p.host, p.window,
                    1, wire.Settings(), outcome, state.flags & ~wire.COORDINATE_PARENT_CAPABLE,
                ).encode()
                if outcome is wire.Outcome.ACCEPTED:
                    state.cache[p.request_key] = (encoded, payload)
            if state.lose and verb is wire.Verb.CONTINUE_PARENT:
                state.lose = False
                raise channel.NativeActionChannelTimeout("accepted reply lost")
            return channel.NativeActionResult(
                command.command_id, command.command_id, command.command_id,
                channel.NativeActionResultStage.SUBMITTED_TO_CLIENT, 0, 1, 1, "", payload,
            )

        def renew_lease(self):
            state.renewals += 1

        def close(self):
            state.closed = True

    monkeypatch.setattr(channel, "WindowsNativeActionCommandTransport", Transport)
    session = NativeMovementSession(identity, 303)
    session.cleanup.clock = lambda: state.now

    def snapshot():
        return wire.Snapshot(2, 101, state.flags, 1001, 303, state.grant,
                             wire.Settings(), 1, 1)

    monkeypatch.setattr(session, "snapshot", snapshot)
    state.session = session
    state.acquire = lambda: session.acquire(
        snapshot(), "worker", "operation", str(uuid.uuid4()), coordinate_only=True,
    )
    state.parent = lambda: setattr(
        state, "grant", replace(state.grant, generation=state.grant.generation + 1,
                                scene=state.grant.scene + 1),
    )
    yield state
    session.close()


def test_old_native_rejected_before_producer_creation(native):
    native.flags = 3
    with pytest.raises(channel.NativeActionChannelUnavailable, match="continuity"):
        native.acquire()
    assert native.opened == native.commands == []


def test_coordinate_successor_is_receipt_proven_and_used_without_reacquisition(native):
    grant = native.acquire()
    native.parent()
    native.session.renew(grant)
    successor = native.session.current_ownership(grant)
    assert successor == native.grant and successor != grant.ownership
    native.session.move(grant, (10, 0, -20), str(uuid.uuid4()))
    assert [c.kind for c in native.commands] == [
        wire.Verb.ACQUIRE_COORDINATE, wire.Verb.CONTINUE_PARENT, wire.Verb.DESTINATION,
    ]
    assert native.commands[1].payload.expected == grant.ownership
    assert native.commands[1].payload.revision == 1
    assert native.commands[-1].payload.expected == successor
    assert len(native.opened) == native.renewals == 1
    assert native.commands[-1].payload.destination == (10, 0, -20)


@pytest.mark.parametrize("change", ["manual", "token", "scene_only", "generation_only"])
def test_unproven_or_foreign_change_is_permanent_revocation(native, change):
    grant = native.acquire()
    native.parent()
    if change == "manual":
        native.grant = wire.Grant(3, 2, wire.Owner.MANUAL)
    elif change == "token":
        native.grant = replace(native.grant, operation_id="replacement")
    elif change == "scene_only":
        native.grant = replace(native.grant, generation=grant.ownership.generation)
    else:
        native.grant = replace(native.grant, scene=grant.ownership.scene)
    with pytest.raises(NativeMovementError):
        native.session.renew(grant)
    native.grant = grant.ownership
    with pytest.raises(NativeMovementError):
        native.session.move(grant, (1, 0, 2), str(uuid.uuid4()))
    assert native.renewals == 0 and len(native.commands) == 1


@pytest.mark.parametrize("wrong", ["same", "token", "generation", "scene"])
def test_receipt_must_prove_strict_same_operation_successor(native, wrong):
    grant = native.acquire()
    native.parent()
    native.wrong = {
        "same": grant.ownership,
        "token": replace(native.grant, worker_id="other"),
        "generation": replace(native.grant, generation=grant.ownership.generation),
        "scene": replace(native.grant, scene=grant.ownership.scene),
    }[wrong]
    with pytest.raises(channel.NativeActionChannelError):
        native.session.renew(grant)
    assert native.session.current_ownership(grant) == grant.ownership
    assert native.renewals == 0


def test_pending_cleanup_renews_but_never_adopts_or_publishes_destination(native):
    grant = native.acquire()
    native.parent()
    native.pending = True
    native.session.renew(grant)
    assert native.renewals == 1
    assert native.session.current_ownership(grant) == grant.ownership
    with pytest.raises(NativeMovementCleanupPending):
        native.session.move(grant, (1, 0, 2), str(uuid.uuid4()))
    first = native.commands[1].payload
    assert all(c.payload == first for c in native.commands[1:])
    native.pending = False
    native.session.renew(grant)
    assert native.commands[-1].payload == first
    assert native.session.current_ownership(grant) == native.grant
    native.session.move(grant, (2, 0, 3), str(uuid.uuid4()))
    assert native.commands[-1].kind is wire.Verb.DESTINATION


def test_pending_has_original_bounded_cleanup_deadline(native):
    grant = native.acquire()
    native.parent()
    native.pending = True
    native.session.renew(grant)
    native.now = 2.9
    native.session.renew(grant)
    native.now = 3.01
    with pytest.raises(channel.NativeActionChannelError, match="deadline"):
        native.session.renew(grant)
    assert native.renewals == 2


def test_lost_handoff_receipt_retries_identical_request_then_advances_again(native):
    grant = native.acquire()
    native.parent()
    native.lose = True
    native.session.renew(grant)
    first_successor = native.grant
    first = native.commands[-1].payload
    assert native.session.current_ownership(grant) == grant.ownership
    native.parent()
    native.session.renew(grant)
    assert native.commands[-1].payload == first
    assert native.session.current_ownership(grant) == first_successor
    native.session.renew(grant)
    assert native.commands[-1].payload.expected == first_successor
    assert native.commands[-1].payload.request_key != first.request_key
    assert native.session.current_ownership(grant) == native.grant


@pytest.mark.parametrize("lost", [False, True])
def test_cancel_dominates_pending_or_lost_resume_and_stops_original_ack(native, lost):
    grant = native.acquire()
    native.parent()
    native.pending, native.lose = not lost, lost
    native.session.renew(grant)
    before = len(native.commands)
    native.session.cleanup.request_terminal(grant)
    native.session.renew(grant)
    assert len(native.commands) == before  # No retry of an ambiguous resume.
    with pytest.raises(NativeMovementError):
        native.session.move(grant, (1, 0, 2), str(uuid.uuid4()))
    native.pending = False
    native.flags = 3 | wire.COORDINATE_PARENT_CAPABLE
    receipt = native.session.stop(grant, str(uuid.uuid4()))
    assert receipt.grant.owner is wire.Owner.NONE
    assert native.commands[-1].kind is wire.Verb.STOP
    assert native.commands[-1].payload.expected == grant.ownership


def test_coordinate_grant_never_admits_actor_or_combat(native):
    grant = native.acquire()
    for admit in (native.session.require_combat_available, native.session.require_actor_actions):
        with pytest.raises(channel.NativeActionChannelUnavailable, match="coordinate travel"):
            admit(grant)
    assert len(native.commands) == 1


def test_snapshot_successor_alone_does_not_prove_retirement(native, monkeypatch):
    grant = native.acquire()
    native.parent()
    movement = OperationMovement(
        SimpleNamespace(kind=WorkerOperationKind.TRAVEL), native.session, threading.Event(),
    )
    monkeypatch.setattr(channel, "_WindowsKernel", lambda: SimpleNamespace(tick_count=lambda: 1))
    assert not movement._retired_snapshot(grant)
    native.grant = wire.Grant(native.grant.generation + 1, native.grant.scene)
    assert movement._retired_snapshot(grant)


@pytest.mark.parametrize("initial_coordinate", [False, True])
def test_acquisition_retry_cannot_change_coordinate_verb(native, initial_coordinate):
    before = native.session.snapshot()
    request = str(uuid.uuid4())
    native.session.acquire(
        before, "worker", "operation", request, coordinate_only=initial_coordinate,
    )
    with pytest.raises(ValueError, match="acquisition retry"):
        native.session.acquire(
            before, "worker", "operation", request, coordinate_only=not initial_coordinate,
        )
    assert len(native.commands) == 1


def test_mixed_actor_acquisition_never_continues_parent(native):
    grant = native.session.acquire(
        native.session.snapshot(), "worker", "operation", str(uuid.uuid4()),
    )
    native.parent()
    with pytest.raises(NativeMovementError):
        native.session.renew(grant)
    assert [c.kind for c in native.commands] == [wire.Verb.ACQUIRE]


def test_pending_parent_cancel_pause_failure_retains_exact_cleanup_until_stop(native):
    grant = native.acquire()
    native.parent()
    native.pending = True
    native.session.renew(grant)
    native.session.cleanup.request_terminal(grant)
    with pytest.raises(NativeMovementCleanupPending):
        native.session.pause(grant, str(uuid.uuid4()))
    assert grant not in native.session._revoked
    assert native.session.current_ownership(grant) == grant.ownership
    native.pending = False
    native.flags = 3 | wire.COORDINATE_PARENT_CAPABLE
    receipt = native.session.stop(grant, str(uuid.uuid4()))
    assert receipt.grant.owner is wire.Owner.NONE
    assert [c.kind for c in native.commands] == [
        wire.Verb.ACQUIRE_COORDINATE, wire.Verb.CONTINUE_PARENT, wire.Verb.PAUSE, wire.Verb.STOP,
    ]


@pytest.mark.parametrize("kind", [WorkerOperationKind.TRAVEL, WorkerOperationKind.PVE,
                                  WorkerOperationKind.PLAYER_ATTACK])
def test_manager_only_travel_requests_coordinate_authority(native, kind):
    movement = OperationMovement(
        SimpleNamespace(kind=kind, worker_id="worker", operation_id="operation"),
        native.session, threading.Event(),
    )
    assert movement.acquire()
    assert native.commands[0].kind is (
        wire.Verb.ACQUIRE_COORDINATE if kind is WorkerOperationKind.TRAVEL else wire.Verb.ACQUIRE
    )
    assert movement.finish() is None
    assert movement.cleanup_confirmed


def test_actual_coordinate_parent_ipc_preserves_one_operation_and_proves_successor():
    import os
    import subprocess
    import sys
    from pathlib import Path

    configured = os.environ.get("WONDERBANE_MOVEMENT_RUNTIME_TEST")
    if sys.platform != "win32" or not configured:
        pytest.skip("requires the Windows native movement runtime fixture")
    binary = Path(configured)
    assert binary.is_file()
    process = subprocess.Popen(
        [str(binary), "ipc-coordinate"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    session = None
    try:
        pid, creation, window = map(int, process.stdout.readline().split())
        session = NativeMovementSession(channel.NativeClientProcessIdentity(pid, creation), window)
        grant = session.acquire(session.snapshot(), "coordinate-worker", "coordinate-operation",
                                str(uuid.uuid4()), coordinate_only=True)
        assert grant.coordinate_only
        first = session.move(grant, (10, 0, -20), str(uuid.uuid4()))
        assert first.grant == grant.ownership
        process.stdin.write("p\n")
        process.stdin.flush()
        marker, generation, scene = process.stdout.readline().split()
        assert marker == "parent"
        session.renew(grant)
        successor = session.current_ownership(grant)
        assert (successor.generation, successor.scene) == (int(generation), int(scene))
        assert successor.generation > grant.ownership.generation
        assert successor.scene > grant.ownership.scene
        assert successor.worker_id == grant.ownership.worker_id
        assert successor.operation_id == grant.ownership.operation_id
        assert session.move(grant, (20, 0, -30), str(uuid.uuid4())).grant == successor
        session.cleanup.request_terminal(grant)
        stopped = session.stop(grant, str(uuid.uuid4()))
        assert stopped.grant.owner is wire.Owner.NONE
        session.close()
        session = None
        process.stdin.write("q\n")
        process.stdin.flush()
        output, error = process.communicate(timeout=5)
        assert process.returncode == 0, output + error
    finally:
        if session is not None:
            session.close()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


@pytest.mark.parametrize("outcome", [wire.Outcome.STALE, wire.Outcome.STOP_FAILED])
def test_destination_parent_publication_race_defers_without_acceptance_or_revocation(
    native, outcome,
):
    from shadowbane_lab.client_extension.movement_session import NativeMovementParentPending

    grant = native.acquire()
    native.destination_race = outcome
    with pytest.raises(NativeMovementParentPending):
        native.session.move(grant, (1, 0, 2), str(uuid.uuid4()))
    assert grant not in native.session._revoked
    assert native.session.current_ownership(grant) == grant.ownership
    assert [c.kind for c in native.commands] == [
        wire.Verb.ACQUIRE_COORDINATE, wire.Verb.DESTINATION,
    ]
    native.session.renew(grant)
    assert native.commands[-1].kind is wire.Verb.CONTINUE_PARENT
    assert native.session.current_ownership(grant) == native.grant
    native.session.move(grant, (5, 0, 6), str(uuid.uuid4()))
    assert native.commands[-1].payload.destination == (5, 0, 6)  # Fresh proposal, not replay.


def test_foreign_destination_refusal_is_not_deferrable(native):
    grant = native.acquire()
    native.destination_race = wire.Outcome.STALE
    native.wrong = wire.Grant(3, 2, wire.Owner.AUTOMATION, "other", "replacement")
    with pytest.raises(NativeMovementError):
        native.session.move(grant, (1, 0, 2), str(uuid.uuid4()))
    assert grant in native.session._revoked
