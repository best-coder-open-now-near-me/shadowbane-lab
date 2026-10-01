"""Combat shares movement ownership; ambiguous completion never reacquires it."""

import uuid
from dataclasses import replace

import pytest
from test_combat_wire_v2 import command as fixture
from test_combat_wire_v2 import receipt

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension import movement_wire as movement
from shadowbane_lab.client_extension.combat_channel import NativeCombatCommand
from shadowbane_lab.client_extension.combat_fence_v3 import RequestId
from shadowbane_lab.client_extension.combat_wire_v2 import (
    CLEANUP_REQUIRED,
    Action,
    EntryState,
    Outcome,
    Phase,
    Verb,
)
from shadowbane_lab.client_extension.movement_session import (
    NativeCombatResult,
    NativeMovementError,
    NativeMovementSession,
)


@pytest.fixture
def owner(monkeypatch):
    command = fixture()
    identity = channel.NativeClientProcessIdentity(
        command.binding.client_pid, command.binding.client_creation,
    )
    opened = []

    class Transport:
        def __init__(self, client):
            assert client == identity
            opened.append(self)
            self.host_process_identity = channel.NativeClientProcessIdentity(
                command.host.process_id, command.host.creation_filetime,
            )
            self.host_lease_generation = command.host.lease_generation
            self.header = channel.NativeActionChannelHeader(
                identity, channel.CLIENT_ACTION_TRANSPORT_CAPABILITY
                | channel.OBJECT_COMBAT_CAPABILITY,
            )
            self.commands = []
            self.failure = None
            self.payload = receipt().encode()
            self.stage = channel.NativeActionResultStage.SUBMITTED_TO_CLIENT
            self.error = 0
            self.detail = ""
            self.closed = False

        def submit(self, wire, *, timeout_ms):
            assert timeout_ms == 127
            self.commands.append(wire)
            if self.failure:
                raise self.failure
            payload = self.payload
            if isinstance(wire, NativeCombatCommand) and payload and len(payload) == 384:
                # The real service echoes the requested verb even for action history.
                payload = payload[:376] + int(wire.kind).to_bytes(4, "little") + payload[380:]
            if not isinstance(wire, NativeCombatCommand):
                payload = movement.Receipt(
                    command.grant, wire.payload.request_key, command.host,
                    command.window, 1, movement.Settings(), movement.Outcome.ACCEPTED, 2,
                ).encode()
            return channel.NativeActionResult(
                len(self.commands), wire.command_id, len(self.commands),
                self.stage, self.error, 1, 1, self.detail, payload,
            )

        def close(self):
            self.closed = True

    monkeypatch.setattr(channel, "WindowsNativeActionCommandTransport", Transport)
    session = NativeMovementSession(identity, command.window, timeout_ms=127)
    before = movement.Snapshot(
        2, identity.process_id, 3, identity.creation_filetime_utc, command.window,
        command.grant, movement.Settings(), 1, 1,
    )
    monkeypatch.setattr(session, "snapshot", lambda: before)
    grant = session.acquire(before, "worker", "operation", str(uuid.uuid4()))
    transport = opened[0]
    transport.commands.clear()
    yield session, grant, command, transport, opened
    session.close()


def test_combat_reuses_acquired_producer_and_original_binding_for_every_verb(owner):
    session, grant, command, transport, opened = owner
    for verb in (Verb.SUBMIT, Verb.ACTION_STATUS, Verb.CANCEL_ACTION):
        expected = NativeCombatResult(replace(receipt(), verb=verb))
        assert session.combat(grant, verb, command) == expected
    assert opened == [transport]
    assert [wire.kind for wire in transport.commands] == [
        Verb.SUBMIT, Verb.ACTION_STATUS, Verb.CANCEL_ACTION,
    ]
    assert [wire.command_id for wire in transport.commands] == [2, 3, 4]
    assert all(wire.payload is command for wire in transport.commands)
    assert all(wire.payload.encode() == command.encode() for wire in transport.commands)


def test_combat_preflight_is_readonly_and_requires_current_owner_and_capability(owner):
    session, grant, _, transport, opened = owner
    session.require_combat_available(grant)
    assert not transport.commands and opened == [transport]
    transport.header = replace(transport.header, capability_flags=1)
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.require_combat_available(grant)
    assert not transport.commands and opened == [transport]
    transport.header = replace(transport.header, capability_flags=17)
    session.stop(grant, str(uuid.uuid4()))
    transport.commands.clear()
    with pytest.raises(NativeMovementError) as failure:
        session.require_combat_available(grant)
    assert failure.value.outcome is movement.Outcome.STALE
    assert not transport.commands and opened == [transport]


@pytest.mark.parametrize("field", ["pid", "creation", "window", "grant", "host", "binding"])
def test_mismatched_owner_is_rejected_before_transport_publication(owner, field):
    session, grant, command, transport, opened = owner
    if field in ("pid", "creation"):
        identity = replace(grant.process_identity, **{
            "process_id" if field == "pid" else "creation_filetime_utc": 99,
        })
        grant = replace(grant, process_identity=identity)
    elif field == "window":
        grant = replace(grant, window=99)
    elif field == "grant":
        command = replace(command, grant=replace(command.grant, generation=99))
    elif field == "host":
        command = replace(command, host=replace(command.host, lease_generation=99))
    else:
        command = replace(command, binding=replace(command.binding, client_creation=99))
    for verb in (Verb.SUBMIT, Verb.ACTION_STATUS, Verb.CANCEL_ACTION):
        with pytest.raises(ValueError, match="another owner"):
            session.combat(grant, verb, command)
    assert not transport.commands
    assert opened == [transport]


def test_revoked_owner_can_only_query_or_cancel_its_original_transaction(owner):
    session, grant, command, transport, opened = owner
    session.stop(grant, str(uuid.uuid4()))
    transport.commands.clear()
    with pytest.raises(NativeMovementError) as failure:
        session.combat(grant, Verb.SUBMIT, command)
    assert failure.value.outcome is movement.Outcome.STALE
    for verb in (Verb.ACTION_STATUS, Verb.CANCEL_ACTION):
        session.combat(grant, verb, command)
    assert [wire.kind for wire in transport.commands] == [Verb.ACTION_STATUS, Verb.CANCEL_ACTION]
    assert all(wire.payload is command for wire in transport.commands)
    assert opened == [transport]


def test_ambiguous_movement_stop_excludes_start_but_allows_exact_combat_cleanup(owner):
    session, grant, command, transport, _ = owner
    transport.failure = channel.NativeActionChannelTimeout("ambiguous stop")
    with pytest.raises(channel.NativeActionChannelTimeout):
        session.stop(grant, str(uuid.uuid4()))
    transport.failure = None
    transport.commands.clear()
    with pytest.raises(NativeMovementError) as failure:
        session.combat(grant, Verb.SUBMIT, command)
    assert failure.value.outcome is movement.Outcome.INHIBITED
    session.combat(grant, Verb.CANCEL_ACTION, command)
    assert len(transport.commands) == 1


def test_start_timeout_does_not_retry_or_reacquire_and_status_keeps_original_command(owner):
    session, grant, command, transport, opened = owner
    transport.failure = channel.NativeActionChannelTimeout("ambiguous start")
    with pytest.raises(channel.NativeActionChannelTimeout):
        session.combat(grant, Verb.SUBMIT, command)
    assert len(transport.commands) == 1
    transport.failure = None
    transport.payload = replace(receipt(), outcome=Outcome.UNCERTAIN,
                                phase=Phase.BLOCKED).encode()
    observed = session.combat(grant, Verb.ACTION_STATUS, command)
    assert observed.receipt.outcome is Outcome.UNCERTAIN
    assert not observed.receipt.cleanup_confirmed
    assert [wire.kind for wire in transport.commands] == [Verb.SUBMIT, Verb.ACTION_STATUS]
    assert all(wire.payload is command for wire in transport.commands)
    assert opened == [transport]


@pytest.mark.parametrize("state", ["closed", "changed_lease"])
def test_unavailable_session_never_opens_or_publishes_another_owner(owner, state):
    session, grant, command, transport, opened = owner
    if state == "closed":
        session.close()
    else:
        transport.host_lease_generation += 1
    for verb in (Verb.SUBMIT, Verb.ACTION_STATUS, Verb.CANCEL_ACTION):
        with pytest.raises(channel.NativeActionChannelError):
            session.combat(grant, verb, command)
    assert not transport.commands
    assert opened == [transport]


def test_readiness_loss_blocks_new_start_but_preserves_exact_old_cleanup(owner):
    session, grant, command, transport, opened = owner
    session.combat(grant, Verb.SUBMIT, command)
    transport.header = replace(transport.header, capability_flags=1)
    transport.commands.clear()
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.require_combat_available(grant)
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.combat(grant, Verb.SUBMIT, command)
    for verb in (Verb.ACTION_STATUS, Verb.CANCEL_ACTION):
        session.combat(grant, verb, command)
    assert [wire.kind for wire in transport.commands] == [Verb.ACTION_STATUS, Verb.CANCEL_ACTION]
    assert all(wire.payload is command for wire in transport.commands)
    assert opened == [transport]


@pytest.mark.parametrize("invalid", ["empty", "zero", "malformed", "wrong_request",
                                   "wrong_grant", "wrong_binding", "failed_stage", "error"])
def test_unconfirmed_or_mismatched_receipt_never_reports_success(owner, invalid):
    session, grant, command, transport, _ = owner
    transport.detail = "combat_v1:diagnostic_must_not_escape_bad_binding"
    if invalid == "empty":
        transport.payload = b""
    elif invalid == "zero":
        transport.payload = bytes(384)
    elif invalid == "malformed":
        transport.payload = b"invalid"
    elif invalid == "wrong_request":
        transport.payload = replace(receipt(), request=RequestId(99)).encode()
    elif invalid == "wrong_grant":
        transport.payload = replace(receipt(), grant=replace(command.grant, generation=99)).encode()
    elif invalid == "wrong_binding":
        transport.payload = replace(receipt(), binding_digest=b"x" * 32).encode()
    elif invalid == "failed_stage":
        transport.stage = channel.NativeActionResultStage.FAILED
    else:
        transport.error = 1
    with pytest.raises((ValueError, channel.NativeActionChannelError)) as failure:
        session.combat(grant, Verb.ACTION_STATUS, command)
    assert transport.detail not in str(failure.value)
    assert len(transport.commands) == 1


@pytest.mark.parametrize("detail", ["", "native_combat_receipt_v1",
                                    "combat_v1:dispatch:native_rejected:d1n0q0f0", "x" * 72])
def test_correlated_result_preserves_opaque_bounded_native_diagnostic(owner, detail):
    session, grant, command, transport, _ = owner
    transport.detail = detail
    result = session.combat(grant, Verb.SUBMIT, command)
    assert isinstance(result, NativeCombatResult)
    assert result.native_detail == (detail or None)
    # No diagnostic metadata is appended to or encoded in Receipt384.
    assert result.receipt == receipt()
    assert result.receipt.encode() == transport.payload
    assert len(result.receipt.encode()) == 384


def test_status_diagnostic_is_not_reused_after_ambiguous_transport(owner):
    session, grant, command, transport, _ = owner
    transport.detail = "combat_v1:entry:queued:d1n1q1f1"
    first = session.combat(grant, Verb.SUBMIT, command)
    transport.failure = channel.NativeActionChannelTimeout("ambiguous status")
    with pytest.raises(channel.NativeActionChannelTimeout):
        session.combat(grant, Verb.ACTION_STATUS, command)
    transport.failure = None
    transport.detail = ""
    last = session.combat(grant, Verb.CANCEL_ACTION, command)
    assert first.native_detail == "combat_v1:entry:queued:d1n1q1f1"
    assert last.native_detail is None


@pytest.mark.parametrize("verb", [Verb.BIND_ENGAGEMENT, Verb.ENGAGEMENT_STATUS,
                                  Verb.STOP_ENGAGEMENT])
def test_engagement_controls_keep_exact_binding_and_separate_action_history(owner, verb):
    session, grant, original, transport, opened = owner
    command = replace(original, action=Action.NONE, power_id=0)
    value = replace(receipt(), action=Action.NONE, power_id=0, verb=verb,
                    entry_state=EntryState.UNKNOWN, flags=CLEANUP_REQUIRED,
                    outcome=Outcome.BOUND)
    transport.payload = value.encode()
    result = session.combat(grant, verb, command)
    assert result.receipt == value
    assert len(transport.commands) == 1 and opened == [transport]


def test_old_v1_capability_cannot_authorize_object_actions(owner):
    session, grant, command, transport, _ = owner
    transport.header = replace(transport.header, capability_flags=9)
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.combat(grant, Verb.SUBMIT, command)
    assert not transport.commands


def test_combat_ordinal_allocator_survives_coordinator_recreation(owner):
    session, grant, _, _, _ = owner
    first = session.combat_ordinals(grant)
    engagement = first.next_engagement()
    first.next_request(engagement)
    second = session.combat_ordinals(grant)
    assert second is first
    assert second.next_engagement().value > engagement.value
