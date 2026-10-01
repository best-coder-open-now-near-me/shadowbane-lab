"""Actual Windows command mapping/lease/ledger roundtrip, without game effects."""
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
from shadowbane_lab.client_extension.combat_channel import NativeCombatCommand
from shadowbane_lab.client_extension.combat_fence_v3 import EngagementId, RequestId
from shadowbane_lab.client_extension.combat_fence_windows import create_npc_engagement
from shadowbane_lab.client_extension.combat_wire_v2 import (
    CLEANUP_REQUIRED,
    OUTBOUND_QUEUED,
    Action,
    ClosureProof,
    Command,
    EntryState,
    Outcome,
    Phase,
    Receipt,
    Verb,
    identity_digest,
)
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Owner
from shadowbane_lab.client_observation.native_object import NativeObjectKey


def test_real_power_readiness_mapping_retains_binding_and_cleanup():
    executable = os.environ.get("SHADOWBANE_COMBAT_CHANNEL_TEST_EXE")
    if sys.platform != "win32" or not executable:
        pytest.skip("requires the built Windows combat channel fixture")
    process = subprocess.Popen(
        [executable, "--ipc-readiness"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    transport = ticket = None
    try:
        assert process.stdout is not None
        pid, creation = map(int, process.stdout.readline().split())
        assert pid == process.pid
        transport = WindowsNativeActionCommandTransport(
            NativeClientProcessIdentity(pid, creation)
        )
        assert transport.header.capability_flags & 0x70 == 0x70
        producer = transport.host_process_identity
        host = Host(producer.process_id, transport.host_lease_generation,
                    producer.creation_filetime_utc)
        grant = Grant(11, 7, Owner.AUTOMATION, "ipc-readiness", "same-engagement")
        ticket, binding = create_npc_engagement(
            client_pid=pid, client_creation=creation, host=host, grant=grant,
            local_key=NativeObjectKey(91, 53), target_key=NativeObjectKey(92, 37),
            owner_digest=identity_digest("fixture-owner"), engagement=EngagementId(1),
            actor_address_hint=0x12300000, target_address_hint=0x12400000,
        )
        base = Command(host, 0x10000, grant, binding, RequestId(1), Action.NONE,
                       0, identity_digest("Local"), identity_digest("Server"))
        sequence = 0

        def send(payload, verb):
            nonlocal sequence
            sequence += 1
            result = transport.submit(NativeCombatCommand(sequence, verb, payload),
                                      timeout_ms=1500)
            assert result.command_id == sequence
            assert result.stage is NativeActionResultStage.SUBMITTED_TO_CLIENT
            assert result.error_code == 0
            receipt = Receipt.decode(result.movement_payload[:384])
            receipt.require_command(payload, verb)
            assert receipt.grant == grant
            assert receipt.binding_digest == binding.digest
            assert receipt.engagement == binding.engagement
            return receipt

        bound = send(base, Verb.BIND_ENGAGEMENT)
        assert bound.phase is Phase.BOUND and bound.flags == CLEANUP_REQUIRED
        power = replace(base, request=RequestId(2), action=Action.SELF_POWER,
                        power_id=563795161)
        for verb in (Verb.SUBMIT, Verb.SUBMIT, Verb.ACTION_STATUS):
            blocked = send(power, verb)
            assert blocked.outcome is Outcome.POWER_REUSE_BLOCKED
            assert blocked.entry_state is EntryState.NEVER_ENTERED
            assert blocked.phase is Phase.BOUND
            assert blocked.closure is ClosureProof.NONE
            assert blocked.flags == CLEANUP_REQUIRED
        attack = replace(base, request=RequestId(3), action=Action.ATTACK)
        queued = send(attack, Verb.SUBMIT)
        assert queued.outcome is Outcome.CLIENT_OUTBOUND_QUEUED
        assert queued.entry_state is EntryState.ENTERED
        assert queued.flags == CLEANUP_REQUIRED | OUTBOUND_QUEUED
        # The native worker refreshes capabilities before publishing this reply.
        assert transport.header.capability_flags & 0x70 == 0
        assert send(power, Verb.ACTION_STATUS).outcome is Outcome.POWER_REUSE_BLOCKED
        # A new action is denied by the actual channel while lifecycle remains reachable.
        sequence += 1
        denied = transport.submit(NativeCombatCommand(
            sequence, Verb.SUBMIT, replace(attack, request=RequestId(4))), timeout_ms=1500)
        assert denied.stage is NativeActionResultStage.FAILED
        assert denied.error_code == 50  # ERROR_NOT_SUPPORTED
        stopped = send(replace(base, request=RequestId(5)), Verb.STOP_ENGAGEMENT)
        assert stopped.cleanup_confirmed
        assert stopped.closure is ClosureProof.NATIVE_STOPPED
        history = send(power, Verb.ACTION_STATUS)
        assert history.outcome is Outcome.POWER_REUSE_BLOCKED
        assert history.entry_state is EntryState.NEVER_ENTERED
        assert history.phase is Phase.CLOSED
        assert history.closure is ClosureProof.NATIVE_STOPPED
        assert history.flags == 0
        assert process.stdin is not None
        process.stdin.write("done\n")
        process.stdin.flush()
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors
        # Replay and STATUS did not re-enter the synthetic backend; one binding,
        # one blocked power, one attack, and one exact-owner stop were executed.
        assert output.strip() == "1 1 1 1"
    finally:
        if ticket is not None:
            ticket.close()
        if transport is not None:
            transport.close()
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
