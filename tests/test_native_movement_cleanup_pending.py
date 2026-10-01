"""Retained cleanup is not owner revocation or admission for new work."""

import uuid
from dataclasses import replace
from unittest.mock import Mock

import pytest
from test_combat_session import owner as owner_fixture
from test_combat_wire_v2 import receipt as combat_receipt
from test_native_movement_dispatcher import setup

from shadowbane_lab.client_extension import movement_wire as movement
from shadowbane_lab.client_extension.combat_wire_v2 import Action
from shadowbane_lab.client_extension.combat_wire_v2 import Verb as CombatVerb
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementCleanupPending,
    NativeMovementError,
)
from shadowbane_lab.travel.model import TravelPhase

PENDING = movement.BINDINGS | movement.CLEANUP_PENDING


@pytest.fixture
def owner(monkeypatch):
    yield from owner_fixture.__wrapped__(monkeypatch)


def observed(grant, flags=PENDING):
    return movement.Snapshot(
        2,
        grant.process_identity.process_id,
        flags,
        grant.process_identity.creation_filetime_utc,
        grant.window,
        grant.ownership,
        movement.Settings(),
        1,
        1,
    )


def test_snapshot_and_receipt_preserve_pending_cleanup_bit(owner):
    _, grant, _, _, _ = owner
    snapshot = observed(grant, PENDING | 4 | 16)
    assert movement.Snapshot.decode(snapshot.encode()).encode() == snapshot.encode()
    receipt = movement.Receipt(
        grant.ownership,
        str(uuid.uuid4()),
        grant.host,
        grant.window,
        1,
        movement.Settings(),
        movement.Outcome.STOP_FAILED,
        PENDING,
    )
    assert movement.Receipt.decode(receipt.encode()).encode() == receipt.encode()


@pytest.mark.parametrize(
    "flags,owner_kind",
    [
        (64, movement.Owner.AUTOMATION),
        (PENDING | 2, movement.Owner.AUTOMATION),
        (PENDING | 8, movement.Owner.AUTOMATION),
        (PENDING, movement.Owner.NONE),
        (PENDING, movement.Owner.MANUAL),
        (PENDING | 128, movement.Owner.AUTOMATION),
    ],
)
def test_pending_flag_cannot_hide_invalid_status(owner, flags, owner_kind):
    _, grant, _, _, _ = owner
    snapshot = observed(grant, flags)
    if owner_kind is not movement.Owner.AUTOMATION:
        snapshot = replace(snapshot, grant=movement.Grant(10, 20, owner_kind))
    with pytest.raises(ValueError):
        snapshot.encode()


def test_exact_pending_owner_renews_without_permanent_revocation(owner, monkeypatch):
    session, grant, _, transport, _ = owner
    state = [observed(grant)]
    monkeypatch.setattr(session, "snapshot", lambda: state[0])
    transport.renew_lease = Mock()
    session.renew(grant)
    assert grant not in session._revoked
    state[0] = observed(grant, 3)
    session.renew(grant)
    assert grant not in session._revoked and transport.renew_lease.call_count == 2
    assert transport.commands == []


@pytest.mark.parametrize(
    "cause", ["ready_missing", "bindings_missing", "terminal", "generation", "scene", "owner"]
)
def test_true_owner_or_readiness_failure_still_permanently_revokes(owner, monkeypatch, cause):
    session, grant, _, transport, _ = owner
    snapshot = observed(grant)
    if cause in ("ready_missing", "bindings_missing", "terminal"):
        snapshot = replace(
            snapshot, flags={"ready_missing": 21, "bindings_missing": 2, "terminal": 8}[cause]
        )
    else:
        changed = {
            "generation": replace(grant.ownership, generation=99),
            "scene": replace(grant.ownership, scene=99),
            "owner": movement.Grant(99, 20, movement.Owner.MANUAL),
        }[cause]
        snapshot = replace(snapshot, grant=changed)
    monkeypatch.setattr(session, "snapshot", lambda: snapshot)
    transport.renew_lease = Mock()
    with pytest.raises(NativeMovementError):
        session.renew(grant)
    assert grant in session._revoked
    monkeypatch.setattr(session, "snapshot", lambda: observed(grant, 3))
    with pytest.raises(NativeMovementError):
        session.renew(grant)
    transport.renew_lease.assert_not_called()


@pytest.mark.parametrize("verb", [CombatVerb.SUBMIT, CombatVerb.BIND_ENGAGEMENT])
def test_pending_blocks_new_combat_before_publication_without_revoking(owner, monkeypatch, verb):
    session, grant, command, transport, _ = owner
    monkeypatch.setattr(session, "snapshot", lambda: observed(grant))
    if verb is CombatVerb.BIND_ENGAGEMENT:
        command = replace(command, action=Action.NONE, power_id=0)
    with pytest.raises(NativeMovementCleanupPending):
        session.combat(grant, verb, command)
    assert not transport.commands and grant not in session._revoked


def test_pending_keeps_correlated_action_status_cancel_and_engagement_cleanup_routable(
    owner, monkeypatch
):
    session, grant, command, transport, _ = owner
    monkeypatch.setattr(session, "snapshot", lambda: observed(grant))
    for verb in (CombatVerb.ACTION_STATUS, CombatVerb.CANCEL_ACTION):
        session.combat(grant, verb, command)
    control = replace(command, action=Action.NONE, power_id=0)
    # Build fully correlated status receipts without claiming cleanup confirmation.
    from shadowbane_lab.client_extension.combat_wire_v2 import EntryState, Outcome

    transport.payload = replace(
        combat_receipt(),
        action=Action.NONE,
        power_id=0,
        entry_state=EntryState.UNKNOWN,
        outcome=Outcome.OBSERVED,
        flags=1,
        verb=CombatVerb.ENGAGEMENT_STATUS,
    ).encode()
    for verb in (CombatVerb.ENGAGEMENT_STATUS, CombatVerb.STOP_ENGAGEMENT):
        session.combat(grant, verb, control)
    assert [wire.kind for wire in transport.commands] == [
        CombatVerb.ACTION_STATUS,
        CombatVerb.CANCEL_ACTION,
        CombatVerb.ENGAGEMENT_STATUS,
        CombatVerb.STOP_ENGAGEMENT,
    ]
    assert grant not in session._revoked


def test_move_during_pending_is_not_submitted_and_can_run_after_ready(owner, monkeypatch):
    session, grant, _, transport, _ = owner
    monkeypatch.setattr(session, "snapshot", lambda: observed(grant))
    with pytest.raises(NativeMovementCleanupPending):
        session.move(grant, (1, 0, -2), str(uuid.uuid4()))
    assert not transport.commands and grant not in session._revoked
    monkeypatch.setattr(session, "snapshot", lambda: observed(grant, 3))
    session.move(grant, (1, 0, -2), str(uuid.uuid4()))
    assert len(transport.commands) == 1


@pytest.mark.parametrize("method", ["move", "pause"])
def test_correlated_stop_failure_during_command_retains_owner_for_cleanup(
    owner, monkeypatch, method
):
    session, grant, _, _, _ = owner
    key = str(uuid.uuid4())
    failed = movement.Receipt(
        grant.ownership,
        key,
        grant.host,
        grant.window,
        1,
        movement.Settings(),
        movement.Outcome.STOP_FAILED,
        PENDING,
    )
    calls = []

    def submit(verb, payload, *, timeout_ms=None):
        assert timeout_ms == (session.timeout_ms if method == "pause" else None)
        calls.append((verb, payload))
        if len(calls) == 1:
            raise NativeMovementError(movement.Outcome.STOP_FAILED, failed)
        return replace(failed, outcome=movement.Outcome.ACCEPTED, flags=3)

    monkeypatch.setattr(session, "_submit", submit)

    def attempt():
        return (
            session.move(grant, (1, 0, -2), key) if method == "move" else session.pause(grant, key)
        )

    with pytest.raises(NativeMovementCleanupPending):
        attempt()
    assert grant not in session._revoked
    assert attempt().outcome is movement.Outcome.ACCEPTED
    assert calls[0] == calls[1]


def test_dispatcher_rejects_new_move_and_failed_pause_without_latching(monkeypatch):
    session, adapter, decision = setup()
    snapshot = observed(adapter.grant)
    monkeypatch.setattr(session, "snapshot", lambda: snapshot)
    assert not adapter.is_set()
    result = adapter.dispatch(decision)
    assert not result.accepted and result.reason == "native_movement_cleanup_pending"
    assert not session.calls and not adapter.is_set()
    terminal = replace(
        decision,
        phase=TravelPhase.STOPPED,
        minimap_direction=None,
        maneuver=None,
        click_destination=None,
        terminal_reason="pause",
    )
    keys = []

    def pause(grant, key):
        keys.append(key)
        if len(keys) == 1:
            raise NativeMovementCleanupPending("pending")

    monkeypatch.setattr(session, "pause", pause)
    result = adapter.stop_movement(terminal)
    assert not result.accepted and not adapter.is_set()
    snapshot = replace(snapshot, flags=3)
    assert adapter.stop_movement(terminal).accepted and keys[0] == keys[1]
    assert adapter.dispatch(decision).accepted and not adapter.is_set()
