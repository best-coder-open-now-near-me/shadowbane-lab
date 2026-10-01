"""Actual actor Windows mapping, fences and ledger; native gameplay is stubbed."""
import hashlib
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from shadowbane_lab.client_extension.action_channel import (
    NativeActionResultStage,
    NativeClientProcessIdentity,
    WindowsNativeActionCommandTransport,
)
from shadowbane_lab.client_extension.actor_action_channel import NativeActorCommand
from shadowbane_lab.client_extension.actor_action_fence import (
    ActorBinding,
    Authority,
    ContextBinding,
    ContextId,
    OwnerId,
    RequestId,
    State,
    Ticket,
)
from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OUTBOUND_QUEUED,
    OWNER_CLEANUP,
    Action,
    Closure,
    ClosureScope,
    Command,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Reason,
    Receipt,
    Recipient,
    Verb,
)
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner


def test_real_actor_readiness_mapping_retains_parent_context_and_cleanup():
    executable = os.environ.get("SHADOWBANE_COMBAT_CHANNEL_TEST_EXE")
    if sys.platform != "win32" or not executable:
        pytest.skip("requires the built Windows actor channel fixture")
    process = subprocess.Popen(
        [executable, "--ipc-readiness"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    transport = parent_ticket = child_ticket = None
    try:
        assert process.stdout is not None
        pid, creation = map(int, process.stdout.readline().split())
        assert pid == process.pid
        transport = WindowsNativeActionCommandTransport(NativeClientProcessIdentity(pid, creation))
        assert transport.header.capability_flags & 0x80
        assert transport.header.capability_flags & 0x78 == 0
        producer = transport.host_process_identity
        host = Host(producer.process_id, transport.host_lease_generation,
                    producer.creation_filetime_utc)
        grant = Grant(11, 7, Owner.AUTOMATION, "ipc-readiness", "same-owner")
        parent = ActorBinding(pid, host.process_id, creation, host.creation_filetime,
            host.lease_generation, grant.generation, grant.scene, OwnerId(1), (91, 53),
            0x12300000, b"n" * 32, b"s" * 32, b"o" * 32,
            hashlib.sha256(grant.encode()[24:]).digest())
        child = ContextBinding(parent.digest, ContextId(1), Authority.NPC, 0x12400000,
            (92, 37), 0, bytes(32), bytes(32), bytes(32))
        parent_ticket = Ticket(parent, create=True)
        child_ticket = Ticket(child, parent=parent, create=True)
        parent_ticket.arm()
        child_ticket.arm()
        base = Command(host, 0x10000, grant, RequestId(1), parent.owner_id, None,
                       parent.digest, bytes(32))
        target = replace(base, context_id=child.context_id, context_digest=child.digest)
        sequence = 0

        def send(payload, verb):
            nonlocal sequence
            sequence += 1
            result = transport.submit(NativeActorCommand(sequence, verb, payload), timeout_ms=1500)
            assert result.command_id == sequence
            assert result.stage is NativeActionResultStage.SUBMITTED_TO_CLIENT
            assert result.error_code == 0
            receipt = Receipt.decode(result.movement_payload[:384])
            receipt.require_command(payload, verb)
            assert receipt.grant == grant
            assert receipt.parent_id == parent.owner_id
            assert receipt.context_id == payload.context_id
            return receipt

        opened = send(base, Verb.OPEN_OWNER)
        assert opened.owner_phase is Phase.BOUND and opened.flags == OWNER_CLEANUP
        assert parent_ticket.state() is State.ENTERED
        bound = send(target, Verb.ATTACH_CONTEXT)
        owned = OWNER_CLEANUP | CONTEXT_CLEANUP
        assert bound.context_phase is Phase.BOUND and bound.flags == owned
        assert child_ticket.state() is State.ENTERED
        power = replace(target, request=RequestId(2), action=Action.SELF_POWER,
                        recipient=Recipient.ACTOR, power_id=563795161)
        for verb in (Verb.SUBMIT, Verb.SUBMIT, Verb.ACTION_STATUS):
            blocked = send(power, verb)
            assert blocked.outcome is Outcome.POWER_REUSE_BLOCKED
            assert blocked.entry is Entry.NEVER_ENTERED
            assert blocked.local_settlement is LocalSettlement.SETTLED
            assert blocked.reason is Reason.POWER_REUSE
            assert blocked.owner_phase is blocked.context_phase is Phase.BOUND
            assert blocked.closure is Closure.NONE and blocked.flags == owned
        attack = replace(target, request=RequestId(3), action=Action.ATTACK,
                         recipient=Recipient.TARGET)
        queued = send(attack, Verb.SUBMIT)
        assert queued.outcome is Outcome.CLIENT_OUTBOUND_QUEUED
        assert queued.entry is Entry.ENTERED
        assert queued.flags == owned | OUTBOUND_QUEUED
        assert transport.header.capability_flags & 0xF8 == 0
        assert send(power, Verb.ACTION_STATUS).outcome is Outcome.POWER_REUSE_BLOCKED
        sequence += 1
        denied = transport.submit(NativeActorCommand(
            sequence, Verb.SUBMIT, replace(attack, request=RequestId(4))), timeout_ms=1500)
        assert denied.stage is NativeActionResultStage.FAILED and denied.error_code == 50
        child_ticket.revoke()
        stopped = send(replace(target, request=RequestId(5)), Verb.STOP_CONTEXT)
        assert stopped.context_phase is Phase.CLOSED and stopped.owner_phase is Phase.BOUND
        assert stopped.closure is Closure.NATIVE_STOPPED
        assert stopped.closure_scope is ClosureScope.CONTEXT and stopped.flags == OWNER_CLEANUP
        assert parent_ticket.state() is State.ENTERED
        history = send(power, Verb.ACTION_STATUS)
        assert history.outcome is Outcome.POWER_REUSE_BLOCKED
        assert history.entry is Entry.NEVER_ENTERED and history.flags == OWNER_CLEANUP
        assert history.context_phase is Phase.CLOSED and history.owner_phase is Phase.BOUND
        assert history.closure_scope is ClosureScope.CONTEXT
        parent_ticket.revoke()
        closed = send(replace(base, request=RequestId(6)), Verb.STOP_OWNER)
        assert closed.owner_phase is Phase.CLOSED and closed.flags == 0
        assert closed.closure is Closure.NATIVE_STOPPED
        assert closed.closure_scope is ClosureScope.OWNER
        history = send(power, Verb.ACTION_STATUS)
        assert history.outcome is Outcome.POWER_REUSE_BLOCKED
        assert history.owner_phase is history.context_phase is Phase.CLOSED
        assert history.flags == 0 and history.closure_scope is ClosureScope.OWNER
        assert process.stdin is not None
        process.stdin.write("done\n")
        process.stdin.flush()
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors
        assert output.strip() == "1 1 1 1 2"
    finally:
        for ticket in (child_ticket, parent_ticket):
            if ticket is not None:
                ticket.close()
        if transport is not None:
            transport.close()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
