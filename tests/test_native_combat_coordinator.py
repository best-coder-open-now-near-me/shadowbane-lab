from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_combat_wire_v2 import command as wire_command

from shadowbane_lab.client_extension import combat_fence_windows as fences
from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.cleanup_settlement import CleanupSettlement
from shadowbane_lab.client_extension.combat_fence_v3 import Authority, Ordinals
from shadowbane_lab.client_extension.combat_wire_v2 import (
    CLEANUP_REQUIRED,
    OUTBOUND_QUEUED,
    Action,
    ClosureProof,
    EntryState,
    Outcome,
    Phase,
    Receipt,
    Verb,
)
from shadowbane_lab.client_extension.movement_session import NativeMovementGrant
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve.model import (
    PvECombatDisposition,
    PvECombatKind,
    PvECombatProposal,
)
from shadowbane_lab.pve.native_combat import NativeCombatCoordinator


def answer(c, verb, *, outcome=Outcome.CLIENT_OUTBOUND_QUEUED, phase=Phase.BOUND,
           closure=ClosureProof.NONE, entered=EntryState.ENTERED, queued=True):
    b = c.binding
    control = c.action is Action.NONE
    flags = CLEANUP_REQUIRED if phase in (Phase.BOUND, Phase.STOPPING, Phase.BLOCKED) else 0
    if queued and not control:
        flags |= OUTBOUND_QUEUED
    return Receipt(c.request, c.host, c.window, outcome, flags, c.grant, b.revision,
                   b.local_key, b.target_key, phase, 2, 1, False, b.digest,
                   b.authority, c.action, c.power_id, b.engagement,
                   EntryState.UNKNOWN if control else entered, verb, closure)


@pytest.fixture
def setup(monkeypatch):
    c = wire_command(Authority.NPC)
    session = Mock()
    session.cleanup = CleanupSettlement()
    session.combat_ordinals.return_value = Ordinals()
    grant = NativeMovementGrant(NativeClientProcessIdentity(c.binding.client_pid,
                                c.binding.client_creation), c.window, c.grant, c.host, "owned")
    population = Mock()
    population.resolve_combat_addresses.return_value = (c.binding.actor_address_hint,
                                                        c.binding.target_address_hint)
    actor_key = NativeObjectKey(*c.binding.local_key)
    target_key = NativeObjectKey(*c.binding.target_key)
    character = Mock()
    character.binding = SimpleNamespace(object_key=actor_key,
        identity=SimpleNamespace(character_name="Local", server_name="Server"))
    tickets = []

    def create(**kwargs):
        ticket = Mock()
        tickets.append(ticket)
        return ticket, replace(c.binding, engagement=kwargs["engagement"])

    monkeypatch.setattr(fences, "create_npc_engagement", create)
    session.combat.side_effect = lambda g, v, cmd: SimpleNamespace(
        receipt=answer(cmd, v), native_detail=None)
    coordinator = NativeCombatCoordinator(session=session, grant=grant, population=population,
        character_session=character,
        store=SimpleNamespace(owner=SimpleNamespace(storage_key="aa"*32)))
    observation = SimpleNamespace(
        now_ms=0, population=SimpleNamespace(local_player_object_key=actor_key),
    )
    proposal = PvECombatProposal(1, "opaque-target", target_key, PvECombatKind.CAST, 428918601)
    return coordinator, session, tickets, observation, proposal


def test_two_casts_reuse_engagement_without_pause_or_reacquisition(setup):
    coordinator, session, tickets, observation, proposal = setup
    for index in range(2):
        update = coordinator.advance(replace(proposal, proposal_id=index), observation)
        assert update.acknowledgement.disposition is PvECombatDisposition.QUEUED
    calls = session.combat.call_args_list
    first, second = calls[0].args[2], calls[1].args[2]
    assert first.binding == second.binding
    assert first.request.value < second.request.value
    assert len(tickets) == 1
    session.pause.assert_not_called()


def test_timeout_queries_same_action_and_does_not_submit_again(setup):
    coordinator, session, tickets, observation, proposal = setup
    session.combat.side_effect = TimeoutError()
    assert coordinator.advance(proposal, observation).acknowledgement.disposition is (
        PvECombatDisposition.UNCERTAIN)
    original = session.combat.call_args.args[2]
    session.combat.side_effect = lambda g,v,c: SimpleNamespace(
        receipt=answer(c,v), native_detail=None)
    update = coordinator.advance(proposal, observation)
    assert session.combat.call_args.args[1] is Verb.ACTION_STATUS
    assert session.combat.call_args.args[2] is original
    assert update.acknowledgement.disposition is PvECombatDisposition.QUEUED
    assert len(tickets) == 1


def test_pending_action_rejects_changed_proposal(setup):
    coordinator, session, _, observation, proposal = setup
    session.combat.side_effect = TimeoutError()
    coordinator.advance(proposal, observation)
    with pytest.raises(ValueError, match="unresolved"):
        coordinator.advance(replace(proposal, power_id=1), observation)
    assert session.combat.call_count == 1


def test_cancel_reuses_exact_stop_command_and_retains_uncertain_ticket(setup):
    coordinator, session, tickets, observation, proposal = setup
    coordinator.advance(proposal, observation)
    session.combat.side_effect = TimeoutError()
    assert coordinator.stop("cancel")[0] is False
    first = session.combat.call_args.args[2]
    assert coordinator.active
    tickets[0].close.assert_not_called()
    assert coordinator.stop("cancel")[0] is False
    assert session.combat.call_args.args[2] is first
    assert session.combat.call_args.args[1] is Verb.STOP_ENGAGEMENT
    session.combat.side_effect = lambda g,v,c: SimpleNamespace(receipt=answer(c,v,
        outcome=Outcome.ENGAGEMENT_CLOSED, phase=Phase.CLOSED,
        closure=ClosureProof.NATIVE_STOPPED, queued=False), native_detail=None)
    assert coordinator.stop("cancel")[0] is True
    assert not coordinator.active
    tickets[0].close.assert_called_once()


def test_adopted_action_unknown_stop_requires_same_grant_native_pause(setup):
    coordinator, session, _, observation, proposal = setup
    proposal = replace(proposal, kind=PvECombatKind.BIND, power_id=0, adopted_existing_action=True)
    session.combat.side_effect = TimeoutError()
    coordinator.advance(proposal, observation)
    session.combat.side_effect = lambda g,v,c: SimpleNamespace(receipt=answer(c,v,
        outcome=Outcome.ENGAGEMENT_CLOSED, phase=Phase.CLOSED,
        closure=ClosureProof.NEVER_BOUND, queued=False), native_detail=None)
    session.pause.side_effect = TimeoutError()
    assert coordinator.stop("cancel")[0] is False
    session.pause.assert_called_once()
    assert coordinator.active


def test_deferred_new_engagement_uses_new_ordinal_without_charging_action(setup):
    coordinator, session, tickets, observation, proposal = setup
    session.combat.side_effect = lambda g,v,c: SimpleNamespace(receipt=answer(c,v,
        outcome=Outcome.DEFERRED, phase=Phase.CLOSED, closure=ClosureProof.NEVER_BOUND,
        entered=EntryState.NEVER_ENTERED, queued=False), native_detail=None)
    first = coordinator.advance(proposal, observation)
    assert first.acknowledgement.disposition is PvECombatDisposition.DEFERRED
    assert first.acknowledgement.native_entered is False
    assert not coordinator.active
    second = coordinator.advance(replace(proposal, proposal_id=2), observation)
    assert first.receipt.engagement.value < second.receipt.engagement.value
    assert len(tickets) == 2


def test_unknown_action_is_stopped_after_bounded_resolution_time(setup):
    coordinator, session, _, observation, proposal = setup
    session.combat.side_effect = TimeoutError()
    coordinator.advance(proposal, observation)
    observation.now_ms = 5000
    coordinator.advance(proposal, observation)
    assert session.combat.call_args.args[1] is Verb.STOP_ENGAGEMENT
    stop = session.combat.call_args.args[2]
    observation.now_ms += 100
    coordinator.advance(proposal, observation)
    assert session.combat.call_args.args[2] is stop


def test_adopted_identity_survives_prebinding_failure(setup):
    from shadowbane_lab.pve.model import PvECombatCleanupRequest

    coordinator, _, _, observation, proposal = setup
    adopted = replace(proposal, kind=PvECombatKind.BIND, power_id=0, adopted_existing_action=True)
    coordinator.population.resolve_combat_addresses.side_effect = OSError("missing object")
    with pytest.raises(OSError):
        coordinator.advance(adopted, observation)
    assert coordinator.active
    with pytest.raises(ValueError, match="target differs"):
        coordinator.cleanup(PvECombatCleanupRequest(1, "different", adopted.target_key, "stop"))


def test_shared_session_old_engagement_can_allocate_stop_after_new_coordinator(setup):
    coordinator, session, _, observation, proposal = setup
    coordinator.advance(proposal, observation)
    first = session.combat.call_args.args[2].binding.engagement
    newer = session.combat_ordinals.return_value.next_engagement()
    assert newer.value > first.value
    session.combat.side_effect = TimeoutError()
    coordinator.stop("old-owner stop")
    assert session.combat.call_args.args[1] is Verb.STOP_ENGAGEMENT
    assert session.combat.call_args.args[2].binding.engagement == first


def test_cleanup_waits_for_delayed_exact_closure_using_same_stop_identity(setup):
    from shadowbane_lab.pve.model import PvECombatCleanupRequest
    coordinator, session, tickets, observation, proposal = setup
    clock = SimpleNamespace(now=0.0)
    def sleep(seconds):
        clock.now += seconds
    session.cleanup = CleanupSettlement(clock=lambda: clock.now, sleeper=sleep)
    coordinator.advance(proposal,observation)
    commands=[]
    def reply(grant,verb,command):
        commands.append(command)
        closed=len(commands)==4
        return SimpleNamespace(receipt=answer(command,verb,
            outcome=Outcome.ENGAGEMENT_CLOSED if closed else Outcome.PENDING,
            phase=Phase.CLOSED if closed else Phase.STOPPING,
            closure=ClosureProof.NATIVE_STOPPED if closed else ClosureProof.NONE,queued=False),
            native_detail=None)
    session.combat.side_effect=reply
    request=PvECombatCleanupRequest(1,proposal.target_token,proposal.target_key,'terminal')
    result=coordinator.cleanup(request)
    assert result.confirmed and not coordinator.active
    assert clock.now == pytest.approx(.3)
    assert len(commands)==4 and all(value is commands[0] for value in commands)
    tickets[0].close.assert_called_once()


def test_cleanup_timeout_keeps_correlated_receipt_and_finish_cannot_reset_deadline(setup):
    from shadowbane_lab.pve.model import PvECombatCleanupRequest
    coordinator, session, tickets, observation, proposal = setup
    clock=SimpleNamespace(now=0.0)
    def sleep(seconds):
        clock.now += seconds
    session.cleanup=CleanupSettlement(clock=lambda:clock.now,sleeper=sleep)
    coordinator.advance(proposal,observation)
    session.combat.side_effect=lambda g,v,c: SimpleNamespace(receipt=answer(c,v,
        outcome=Outcome.PENDING,phase=Phase.STOPPING,queued=False),native_detail='native_pending')
    request=PvECombatCleanupRequest(1,proposal.target_token,proposal.target_key,'terminal')
    result=coordinator.cleanup(request)
    assert not result.confirmed and coordinator.active and clock.now == 3
    count=session.combat.call_count
    assert not coordinator.finish('scope_exit')[0]
    assert session.combat.call_count == count
    assert coordinator._last_receipt.phase is Phase.STOPPING
    tickets[0].close.assert_not_called()


@pytest.mark.parametrize("remaining,close_fails", [(0.05, False), (0.0, False), (0.05, True)])
def test_final_ticket_closure_uses_remaining_budget_and_retains_failed_owner(
    setup, remaining, close_fails,
):
    coordinator, session, tickets, observation, proposal = setup
    clock = SimpleNamespace(now=0.0)
    session.cleanup = CleanupSettlement(clock=lambda: clock.now)
    coordinator.advance(proposal, observation)
    obligation = coordinator._cleanup_obligation
    ticket = tickets[0]
    if close_fails:
        ticket.close.side_effect = TimeoutError("fence mutex unavailable")

    def reply(grant, verb, command):
        # The final native STOP response consumes nearly/all of the original budget.
        clock.now = 3.0 - remaining
        return SimpleNamespace(
            receipt=answer(command, verb, outcome=Outcome.ENGAGEMENT_CLOSED,
                           phase=Phase.CLOSED, closure=ClosureProof.NATIVE_STOPPED,
                           queued=False),
            native_detail=None,
        )

    session.combat.side_effect = reply
    confirmed, receipt, detail = coordinator.stop("terminal")
    assert receipt.cleanup_confirmed  # Native evidence remains independently truthful.
    assert obligation.deadline == 3.0
    if remaining:
        ticket.close.assert_called_once()
        assert 49 <= ticket.close.call_args.kwargs["timeout_ms"] <= 50
    else:
        ticket.close.assert_not_called()
    if remaining and not close_fails:
        assert confirmed and detail is None and not coordinator.active
        assert obligation.released and coordinator._cleanup_obligation is None
    else:
        assert not confirmed and "TimeoutError" in detail
        assert coordinator.active and coordinator._ticket is ticket
        assert coordinator._cleanup_obligation is obligation and not obligation.released
        # A later scope exit cannot reset the deadline or discard the retained handles.
        clock.now = 3.0
        before = session.combat.call_count
        assert not coordinator.finish("scope exit")[0]
        assert session.combat.call_count == before
        assert coordinator._ticket is ticket and not obligation.released
