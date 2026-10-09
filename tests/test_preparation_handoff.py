from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_manager_movement import context

from shadowbane_lab.client_extension import action_channel
from shadowbane_lab.client_extension.movement_session import NativeMovementError
from shadowbane_lab.client_extension.movement_wire import (
    CLEANUP_PENDING,
    Outcome,
    Owner,
    Receipt,
    Settings,
    Snapshot,
)


def retired(movement, **changes):
    grant = movement.dispatcher.grant
    return replace(Snapshot(2, grant.process_identity.process_id, 3,
        grant.process_identity.creation_filetime_utc, grant.window,
        replace(grant.ownership, generation=grant.ownership.generation + 1,
                owner=Owner.MANUAL, worker_id="", operation_id=""),
        Settings(), 1, 1000), **changes)


def stale_stop(*args):
    raise NativeMovementError(Outcome.STALE)


def test_no_acquisition_is_clear_but_ambiguous_acquisition_is_not():
    movement, _, _ = context()
    movement.finish()
    assert movement.cleanup_confirmed
    movement, session, _ = context()
    def uncertain(*args):
        raise RuntimeError("unverified acquisition")
    session.acquire = uncertain
    with pytest.raises(RuntimeError):
        movement.acquire()
    movement.finish()
    assert not movement.cleanup_confirmed


def test_new_manual_owner_proves_old_movement_retired_without_stopping_manual(monkeypatch):
    movement, session, _ = context()
    assert movement.acquire()
    snapshot = retired(movement)
    session.stop = stale_stop
    session.snapshot = lambda: snapshot
    monkeypatch.setattr(action_channel, "_WindowsKernel",
                        lambda: SimpleNamespace(tick_count=lambda: 1100))
    movement.finish()
    assert movement.cleanup_confirmed
    assert snapshot.grant.owner is Owner.MANUAL
    assert len(session.acquire_calls) == 1


@pytest.mark.parametrize("changes", [
    {"process_id": 999}, {"creation_filetime": 999}, {"window": 999},
    {"tick": 0}, {"tick": 1101}, {"flags": CLEANUP_PENDING},
])
def test_stale_reply_needs_fresh_exact_client_retirement(monkeypatch, changes):
    movement, session, _ = context()
    assert movement.acquire()
    snapshot = retired(movement, **changes)
    session.stop = stale_stop
    session.snapshot = lambda: snapshot
    monkeypatch.setattr(action_channel, "_WindowsKernel",
                        lambda: SimpleNamespace(tick_count=lambda: 1100))
    movement.finish()
    assert not movement.cleanup_confirmed


def test_same_generation_is_not_retirement(monkeypatch):
    movement, session, _ = context()
    assert movement.acquire()
    snapshot = retired(movement, grant=movement.dispatcher.grant.ownership)
    session.stop = stale_stop
    session.snapshot = lambda: snapshot
    monkeypatch.setattr(action_channel, "_WindowsKernel",
                        lambda: SimpleNamespace(tick_count=lambda: 1100))
    movement.finish()
    assert not movement.cleanup_confirmed


@pytest.mark.parametrize("pending", [True, False])
def test_correlated_stop_requires_actor_obligation_release(pending):
    movement, session, _ = context()
    assert movement.acquire()
    grant = movement.dispatcher.grant
    obligation = session.cleanup.register(grant)
    # Skip waiting here; deadline expiration is not the release we are testing.
    session.cleanup.wait_for_terminal = lambda _: None
    if not pending:
        session.cleanup.release(obligation)
    def stop(_, key):
        return Receipt(replace(grant.ownership, generation=11, owner=Owner.NONE,
                               worker_id="", operation_id=""),
                       key, grant.host, grant.window, 1, Settings(), Outcome.ACCEPTED, 3)
    session.stop = stop
    movement.finish()
    assert movement.cleanup_confirmed is (not pending)


def test_retirement_cannot_discard_unresolved_actor(monkeypatch):
    movement, session, _ = context()
    assert movement.acquire()
    grant = movement.dispatcher.grant
    session.cleanup.register(grant)
    session.cleanup.wait_for_terminal = lambda _: None
    snapshot = retired(movement)
    session.stop = stale_stop
    session.snapshot = lambda: snapshot
    monkeypatch.setattr(action_channel, "_WindowsKernel",
                        lambda: SimpleNamespace(tick_count=lambda: 1100))
    movement.finish()
    assert not movement.cleanup_confirmed
    assert session.cleanup.has_pending(grant)


@pytest.mark.parametrize("outcome", [Outcome.STALE, Outcome.UNAVAILABLE,
                                     Outcome.INHIBITED, Outcome.INVALID])
def test_correlated_unchanged_grant_refusal_has_no_acquired_obligation(outcome):
    movement, session, _ = context()
    snapshot = session.snapshot()
    snapshot.window = 789
    session.snapshot = lambda: snapshot
    from shadowbane_lab.client_extension.movement_wire import Host
    session._test_host = Host(22, 3, 44)
    def refuse(*args):
        raise NativeMovementError(outcome, Receipt(snapshot.grant, movement.request_key,
            session._test_host, snapshot.window, 1, Settings(), outcome, 3))
    session.acquire = refuse
    with pytest.raises(NativeMovementError):
        movement.acquire()
    movement.finish()
    assert movement.cleanup_confirmed
    assert session.stop_calls == []


@pytest.mark.parametrize("change", ["grant", "request", "window", "cleanup", "stop_failed"])
def test_refusal_without_exact_never_acquired_proof_stays_unresolved(change):
    movement, session, _ = context()
    snapshot = session.snapshot()
    snapshot.window = 789
    session.snapshot = lambda: snapshot
    from shadowbane_lab.client_extension.movement_wire import Host
    session._test_host = Host(22, 3, 44)
    outcome = Outcome.STOP_FAILED if change == "stop_failed" else Outcome.INHIBITED
    receipt = Receipt(snapshot.grant, movement.request_key, session._test_host,
                      snapshot.window, 1, Settings(), outcome, 3)
    if change == "grant":
        receipt = replace(receipt, grant=replace(snapshot.grant,
                          generation=snapshot.grant.generation+1))
    if change == "request":
        receipt = replace(receipt, request_key="foreign")
    if change == "window":
        receipt = replace(receipt, window=snapshot.window+1)
    if change == "cleanup":
        receipt = replace(receipt, flags=CLEANUP_PENDING)
    def refuse(*args):
        raise NativeMovementError(outcome, receipt)
    session.acquire = refuse
    with pytest.raises(NativeMovementError):
        movement.acquire()
    movement.finish()
    assert not movement.cleanup_confirmed


def test_missing_acquire_response_never_claims_no_ownership():
    movement, session, _ = context()
    def timeout(*args):
        raise action_channel.NativeActionChannelTimeout("no reply")
    session.acquire = timeout
    with pytest.raises(action_channel.NativeActionChannelTimeout):
        movement.acquire()
    movement.finish()
    assert not movement.cleanup_confirmed

