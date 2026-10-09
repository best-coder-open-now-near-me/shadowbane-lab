"""Real Windows actor transport/runtime; game memory and calls are named fixtures.

This does not claim live client execution. Native adapter and exact-image probes
separately qualify the callbacks substituted by the compiled fixture.
"""
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension import actor_action_wire as wire
from shadowbane_lab.client_extension.actor_action_channel import NativeActorCommand
from shadowbane_lab.client_extension.actor_publication import AdmissionBlock
from shadowbane_lab.client_extension.movement_session import NativeMovementSession
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.manager.native_preparation import NativePreparationOwner
from shadowbane_lab.manager.preparation_service import PersistentPreparationService
from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
from shadowbane_lab.pve.native_actor import NativeActorCoordinator
from shadowbane_lab.pve.preparation import PreparationAction


class RawTargetCommand(NativeActorCommand):
    """Deliberately bypass host validation to test the native protocol rejection."""
    def __init__(self, owner, verb):
        object.__setattr__(self, "command_id", 1000000 + int(verb))
        object.__setattr__(self, "kind", verb)
        fields = list(wire._COMMAND.unpack(owner._open_command.encode()))
        fields[5], fields[7] = bytes([1]) * 16, bytes([2]) * 32
        if verb is wire.Verb.SUBMIT:
            fields[8], fields[15] = wire.Action.ATTACK, wire.Recipient.TARGET
        object.__setattr__(self, "payload", wire._COMMAND.pack(*fields))

    def encode_slot(self, *, sequence, created_tick, deadline_tick):
        return channel._COMMAND.pack(
            0, self.command_id, self.kind, channel.CLIENT_ACTION_PAYLOAD_VERSION,
            created_tick, deadline_tick, 0, 0, 0, 0, 0, 0, bytes(96), bytes(32),
        ) + self.payload


def test_real_preparation_service_ipc_keeps_passive_ownership_and_manual_activity():
    executable = os.environ.get("WONDERBANE_PREPARATION_CHANNEL_TEST_EXE")
    if sys.platform != "win32" or not executable:
        pytest.skip("requires the built Windows preparation channel fixture")
    process = subprocess.Popen([executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    session = coordinator = None
    try:
        pid, creation = map(int, process.stdout.readline().split())
        assert pid == process.pid
        identity = channel.NativeClientProcessIdentity(pid, creation)
        session = NativeMovementSession(identity, 0x50000, timeout_ms=1500)
        lease = session.preparation_lease(7)
        assert lease.ownership is None
        assert session._transport.header.capability_flags & channel.ACTOR_PREPARATION_CAPABILITY
        key = NativeObjectKey(91, 53)
        # Only client-memory identity is simulated. Reader still uses real mappings,
        # exact OS process lifetime, immutable manifest and native capture sequence.
        character = SimpleNamespace(binding=SimpleNamespace(
            process_id=pid, process_creation_filetime_utc=creation, object_key=key,
            executable_sha256="e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437",
            identity=SimpleNamespace(character_name="Fixture", server_name="Fixture World")),
            require_current=lambda: None)
        population = SimpleNamespace(observe_actor_identity=lambda: ("fixture-actor", key, None),
            resolve_actor_address=lambda **_: 0x10000)
        coordinator = NativeActorCoordinator(session=session, grant=lease,
            population=population, character_session=character,
            store=SimpleNamespace(owner=SimpleNamespace(storage_key="aa" * 32)))
        settings = BuffSettings(True, (BuffGroup("fixture-power", (
            BuffAction(PreparationAction("fixture-power", power_id=111), 111),)),))
        coordinator.configure_preparation(settings)
        resources = ExitStack()
        resources.callback(session.close)
        owner = NativePreparationOwner(resources, session, lease, coordinator, character, settings)
        owner.settings_changed = lambda: False  # Saved settings file is outside this fixture.
        service = PersistentPreparationService(
            owner_factory=lambda: owner, intent=lambda: (True, 1))
        coordinator._preparation_admission = service.admission_allowed

        def command(text):
            process.stdin.write(text + "\n")
            process.stdin.flush()
            assert process.stdout.readline().strip() == "ack " + text

        command("manual")
        service._cycle()
        # Opening may occur, but manual entry admission must refuse self-action.
        assert not coordinator.local_pending
        observed = coordinator.observe_preparation()
        assert observed is not None and observed.admission_blocks & AdmissionBlock.MANUAL_ACTIVITY
        for verb in (wire.Verb.ATTACH_CONTEXT, wire.Verb.SUBMIT):
            raw = RawTargetCommand(coordinator, verb)
            result = session._transport.submit(raw, timeout_ms=1500)
            assert result.stage is channel.NativeActionResultStage.FAILED
            assert result.error_code != 0

        command("idle")
        for _ in range(8):
            service._cycle()
            if coordinator.local_pending:
                break
            time.sleep(.01)
        assert coordinator.local_pending
        original = coordinator._preparation_command
        assert original.action is wire.Action.SELF_POWER and original.grant is None
        assert not service.request_handoff()
        command("manual")
        service._cycle()  # One bounded passive STOP; simulated owned action still pending.
        assert coordinator.cleanup_expired and not service.request_handoff()
        deadline = coordinator._obligation.deadline
        stop = coordinator._stop_owner_command
        assert stop is not None
        command("settle")
        for _ in range(8):
            service._cycle()
            if service.request_handoff():
                break
            time.sleep(.01)
        assert service.request_handoff()
        assert coordinator._obligation.deadline == deadline
        assert coordinator._stop_owner_command == stop
        confirmed, receipt, _ = coordinator._last_owner_result
        assert confirmed and receipt.closure is wire.Closure.LOCAL_RELEASED
        assert receipt.closure_scope is wire.ClosureScope.OWNER and receipt.flags == 0
        assert coordinator._obligation.released
        process.stdin.write("done\n")
        process.stdin.flush()
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors
        assert output.strip() == "1 0 0 0 1 0"
    finally:
        # The fixture process is not a game. Terminate it first on a failed assertion,
        # then use exact OS retirement disposal instead of inventing a native receipt.
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
        if coordinator is not None:
            coordinator.close_retired_process()
        if session is not None:
            session.close()
