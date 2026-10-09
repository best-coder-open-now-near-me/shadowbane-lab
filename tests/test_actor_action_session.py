"""Actor entry and lifecycle share one original movement producer/Grant."""
import uuid
from dataclasses import replace

import pytest
from test_actor_action_wire import fixture

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension import movement_wire as movement
from shadowbane_lab.client_extension.actor_action_channel import NativeActorCommand
from shadowbane_lab.client_extension.actor_action_wire import (
    Action,
    Closure,
    ClosureScope,
    Command,
    Outcome,
    Phase,
    Receipt,
    RequestId,
    Verb,
)
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementCleanupPending,
    NativeMovementSession,
)


@pytest.fixture
def owned(monkeypatch):
    parent, _, command, receipt = fixture()
    identity = channel.NativeClientProcessIdentity(parent.client_pid, parent.client_creation)
    opened = []

    class Transport:
        def __init__(self, actual):
            assert actual == identity
            opened.append(self)
            self.host_process_identity = channel.NativeClientProcessIdentity(
                command.host.process_id, command.host.creation_filetime)
            self.host_lease_generation = command.host.lease_generation
            self.header = channel.NativeActionChannelHeader(identity,
                channel.CLIENT_ACTION_TRANSPORT_CAPABILITY | channel.ACTOR_ACTION_CAPABILITY
                | channel.ACTOR_ADMISSION_CAPABILITY)
            self.commands = []
            self.failure = None
            self.payload = receipt
            self.stage = channel.NativeActionResultStage.SUBMITTED_TO_CLIENT
            self.error = 0
            self.detail = "opaque:diagnostic"
            self.timeouts = []

        def submit(self, wire, *, timeout_ms):
            self.commands.append(wire)
            self.timeouts.append(timeout_ms)
            if self.failure:
                raise self.failure
            if isinstance(wire, NativeActorCommand):
                payload = (replace(self.payload, verb=wire.kind).encode()
                           if isinstance(self.payload, Receipt) else self.payload)
            else:
                payload = movement.Receipt(command.grant, wire.payload.request_key, command.host,
                    command.window, 1, movement.Settings(), movement.Outcome.ACCEPTED, 2).encode()
            return channel.NativeActionResult(len(self.commands), wire.command_id,
                len(self.commands), self.stage, self.error, 1, 1, self.detail, payload)

        def close(self):
            pass

    monkeypatch.setattr(channel, "WindowsNativeActionCommandTransport", Transport)
    session = NativeMovementSession(identity, command.window, timeout_ms=127)
    snapshot = movement.Snapshot(2, identity.process_id, 3, identity.creation_filetime_utc,
        command.window, command.grant, movement.Settings(), 1, 1)
    monkeypatch.setattr(session, "snapshot", lambda: snapshot)
    grant = session.acquire(snapshot, "worker", "operation", str(uuid.uuid4()))
    transport = opened[0]
    transport.commands.clear()
    transport.timeouts.clear()
    yield session, grant, parent, command, receipt, transport, opened
    session.close()


def test_exact_actor_command_reuses_transport_grant_and_action_for_status(owned):
    session, grant, parent, command, receipt, transport, opened = owned
    session.require_actor_actions(grant)
    assert not transport.commands
    for verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
        result = session.actor_action(grant, verb, command, parent=parent)
        assert result.receipt == replace(receipt, verb=verb)
        assert result.native_detail == "opaque:diagnostic"
    assert opened == [transport]
    assert all(wire.payload is command for wire in transport.commands)
    assert [wire.command_id for wire in transport.commands] == [2, 3]


def test_actor_timeout_has_one_submission_and_no_reacquire(owned):
    session, grant, parent, command, _, transport, opened = owned
    transport.failure = channel.NativeActionChannelTimeout("unknown")
    with pytest.raises(channel.NativeActionChannelTimeout):
        session.actor_action(grant, Verb.SUBMIT, command, parent=parent)
    assert len(transport.commands) == 1 and opened == [transport]
    transport.failure = None
    session.actor_action(grant, Verb.ACTION_STATUS, command, parent=parent)
    assert [wire.kind for wire in transport.commands] == [Verb.SUBMIT, Verb.ACTION_STATUS]


def test_capability_drop_blocks_entry_but_not_original_status(owned):
    session, grant, parent, command, _, transport, _ = owned
    transport.header = replace(transport.header, capability_flags=1)
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.require_actor_actions(grant)
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.actor_action(grant, Verb.SUBMIT, command, parent=parent)
    assert not transport.commands
    session.actor_action(grant, Verb.ACTION_STATUS, command, parent=parent)
    assert len(transport.commands) == 1


def test_pending_cleanup_blocks_new_work_without_revoking_same_owner(owned, monkeypatch):
    session, grant, parent, command, _, transport, _ = owned
    snapshot = replace(session.snapshot(), flags=1 | movement.CLEANUP_PENDING)
    monkeypatch.setattr(session, "snapshot", lambda: snapshot)
    with pytest.raises(NativeMovementCleanupPending):
        session.actor_action(grant, Verb.SUBMIT, command, parent=parent)
    assert grant not in session._revoked and not transport.commands
    session.actor_action(grant, Verb.ACTION_STATUS, command, parent=parent)


@pytest.mark.parametrize("part", ["owner", "scene", "client", "lease", "context"])
def test_mismatched_actor_binding_never_publishes(part, owned):
    session, grant, parent, command, _, transport, _ = owned
    if part == "owner":
        parent = replace(parent, owner=b"x" * 32)
    elif part == "scene":
        command = replace(command, grant=replace(command.grant, scene=88))
    elif part == "client":
        parent = replace(parent, client_creation=88)
        command = replace(command, parent_digest=parent.digest)
    elif part == "lease":
        transport.host_lease_generation += 1
    else:
        command = replace(command, context_id=fixture()[1].context_id,
                          context_digest=fixture()[1].digest)
    with pytest.raises((ValueError, channel.NativeActionChannelError)):
        session.actor_action(grant, Verb.ACTION_STATUS, command, parent=parent)
    assert not transport.commands


def test_readonly_query_borrows_existing_producer_without_grant_or_input(owned):
    session, _, _, old, _, transport, opened = owned
    command = Command(old.host, old.window, None, RequestId(55), None, None,
                      bytes(32), bytes(32))
    transport.payload = Receipt(command.request, old.host, old.window, Outcome.OBSERVED,
        0, None, None, None, command.digest, Verb.OBSERVE_ACTOR, Action.NONE)
    result = session.actor_action(None, Verb.OBSERVE_ACTOR, command)
    assert result.receipt.grant is None and opened == [transport]
    assert [wire.kind for wire in transport.commands] == [Verb.OBSERVE_ACTOR]


@pytest.mark.parametrize("corruption", ["digest", "malformed", "outer_stage", "outer_error"])
def test_no_diagnostic_or_authority_before_receipt_and_outer_result_agree(corruption, owned):
    session, grant, parent, command, receipt, transport, _ = owned
    if corruption == "digest":
        transport.payload = replace(receipt, command_digest=b"x" * 32)
    elif corruption == "malformed":
        transport.payload = bytes(384)
    elif corruption == "outer_stage":
        transport.stage = channel.NativeActionResultStage.REJECTED_BY_CLIENT
    else:
        transport.error = 1
    with pytest.raises((ValueError, channel.NativeActionChannelError)):
        session.actor_action(grant, Verb.SUBMIT, command, parent=parent)


def test_stop_owner_uses_exact_cleanup_remaining_budget(owned, monkeypatch):
    session, grant, parent, old, _, transport, _ = owned
    command = Command(old.host, old.window, old.grant, RequestId(9), old.parent_id, None,
                      old.parent_digest, bytes(32))
    transport.payload = Receipt(command.request, old.host, old.window, Outcome.ENGAGEMENT_CLOSED,
        0, old.grant, old.parent_id, None, command.digest, Verb.STOP_OWNER, Action.NONE,
        owner_phase=Phase.CLOSED, closure=Closure.LOCAL_RELEASED,
        closure_scope=ClosureScope.OWNER)
    monkeypatch.setattr(session.cleanup, "timeout_ms", lambda actual, maximum: 31)
    session.actor_action(grant, Verb.STOP_OWNER, command, parent=parent)
    assert transport.timeouts == [31]


def test_typed_actor_slot_preserves_outer_geometry_and_payload():
    command = fixture()[2]
    wire = NativeActorCommand(7, Verb.SUBMIT, command)
    slot = wire.encode_slot(sequence=2, created_tick=10, deadline_tick=20)
    assert len(slot) == channel.CLIENT_ACTION_COMMAND_SLOT_SIZE
    assert slot[192:] == command.encode()



def test_old_actor_capability_cannot_admit_new_schema_but_can_cleanup(owned):
    session,grant,parent,command,_,transport,_=owned
    transport.header=replace(transport.header,capability_flags=1|channel.ACTOR_ACTION_CAPABILITY)
    with pytest.raises(channel.NativeActionChannelUnavailable,match='admission'):
        session.require_actor_actions(grant)
    with pytest.raises(channel.NativeActionChannelUnavailable,match='admission'):
        session.actor_action(grant,Verb.SUBMIT,command,parent=parent)
    assert not transport.commands
    session.actor_action(grant,Verb.ACTION_STATUS,command,parent=parent)
    stop=Command(command.host,command.window,command.grant,RequestId(99),command.parent_id,None,
                 command.parent_digest,bytes(32))
    transport.payload=Receipt(stop.request,stop.host,stop.window,Outcome.ENGAGEMENT_CLOSED,0,
        stop.grant,stop.parent_id,None,stop.digest,Verb.STOP_OWNER,Action.NONE,
        owner_phase=Phase.CLOSED,closure=Closure.LOCAL_RELEASED,closure_scope=ClosureScope.OWNER)
    session.actor_action(grant,Verb.STOP_OWNER,stop,parent=parent)
    assert [w.kind for w in transport.commands]==[Verb.ACTION_STATUS,Verb.STOP_OWNER]


def test_tracking_capability_gates_new_query_but_not_retained_status(owned):
    from test_actor_action_wire import tracking_fixture
    session, grant, parent, _, _, transport, opened = owned
    _, _, command, receipt = tracking_fixture()
    with pytest.raises(channel.NativeActionChannelUnavailable, match="tracking"):
        session.require_actor_tracking(grant)
    with pytest.raises(channel.NativeActionChannelUnavailable, match="tracking"):
        session.actor_action(grant, Verb.SUBMIT, command, parent=parent)
    assert transport.commands == []
    transport.header = replace(transport.header, capability_flags=(
        transport.header.capability_flags | channel.ACTOR_TRACK_CAPABILITY))
    session.require_actor_tracking(grant)
    assert transport.commands == []
    transport.payload = receipt
    result = session.actor_action(grant, Verb.SUBMIT, command, parent=parent)
    result.receipt.require_command(command, Verb.SUBMIT)
    transport.header = replace(transport.header, capability_flags=(
        transport.header.capability_flags & ~channel.ACTOR_TRACK_CAPABILITY))
    result = session.actor_action(grant, Verb.ACTION_STATUS, command, parent=parent)
    result.receipt.require_command(command, Verb.ACTION_STATUS)
    with pytest.raises(channel.NativeActionChannelUnavailable, match="tracking"):
        session.require_actor_tracking(grant)
    with pytest.raises(channel.NativeActionChannelUnavailable, match="tracking"):
        session.actor_action(grant, Verb.SUBMIT, command, parent=parent)
    assert len(transport.commands) == 2 and opened == [transport]
