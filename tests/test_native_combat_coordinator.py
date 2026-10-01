"""The target facade retains the actor owner across exact child cleanup."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_native_actor_coordinator import reply
from test_native_actor_coordinator import setup as actor_setup

from shadowbane_lab.client_extension.actor_action_fence import ContextId
from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OUTBOUND_QUEUED,
    OWNER_CLEANUP,
    Closure,
    ClosureScope,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Verb,
)
from shadowbane_lab.pve.model import (
    PvECombatCleanupRequest,
    PvECombatDisposition,
    PvECombatKind,
)
from shadowbane_lab.pve.native_combat import NativeCombatCoordinator, context_cleanup_confirmed


@pytest.fixture
def setup():
    owner, session, tickets, observation, proposal = actor_setup.__wrapped__()
    clock = SimpleNamespace(now=0.0)
    session.cleanup.clock = lambda: clock.now
    session.cleanup.sleeper = lambda seconds: setattr(clock, "now", clock.now + seconds)
    owner.test_clock = clock
    return (
        NativeCombatCoordinator(owner=owner),
        session,
        tickets,
        observation,
        replace(proposal, kind=PvECombatKind.CAST, power_id=428918601),
    )


def answer(command, verb, *, outcome=None, phase=None, closure=None, queued=None):
    """Typed v3 response fixture; every default control verb has its real scope."""
    value = reply(command, verb).receipt
    changes = {}
    if outcome is not None:
        changes["outcome"] = outcome
    if phase is not None:
        changes["context_phase"] = phase
        if phase in (Phase.CLOSED, Phase.RETIRED):
            changes["closure_scope"] = (
                ClosureScope.OWNER if phase is Phase.RETIRED else ClosureScope.CONTEXT
            )
            changes["owner_phase"] = Phase.RETIRED if phase is Phase.RETIRED else Phase.BOUND
            changes["flags"] = 0 if phase is Phase.RETIRED else OWNER_CLEANUP
            changes["mode"] = 1
    if closure is not None:
        changes["closure"] = closure
    if queued is not None:
        flags = changes.get("flags", value.flags)
        changes["flags"] = flags | OUTBOUND_QUEUED if queued else flags & ~OUTBOUND_QUEUED
    return replace(value, **changes)


def action_calls(session, verb=Verb.SUBMIT):
    return [call.args[2] for call in session.actor_action.call_args_list if call.args[1] is verb]


def pending_reply(command, verb):
    result = reply(command, verb)
    receipt = replace(
        result.receipt,
        outcome=Outcome.PENDING,
        context_phase=Phase.STOPPING,
        closure=Closure.NONE,
        closure_scope=ClosureScope.NONE,
        flags=OWNER_CLEANUP | CONTEXT_CLEANUP,
    )
    receipt.require_command(command, verb)
    return SimpleNamespace(receipt=receipt, native_detail="native_pending")


def test_two_casts_reuse_context_and_parent_without_pause_or_reacquisition(setup):
    coordinator, session, tickets, observation, proposal = setup
    for index in range(2):
        update = coordinator.advance(replace(proposal, proposal_id=index), observation)
        assert update.acknowledgement.disposition is PvECombatDisposition.QUEUED
    first, second = action_calls(session)
    assert first.parent_id == second.parent_id and first.context_id == second.context_id
    assert first.request.value < second.request.value
    assert len(tickets) == 2  # One parent and one child, retained across both actions.
    assert len(action_calls(session, Verb.OPEN_OWNER)) == 1
    assert len(action_calls(session, Verb.ATTACH_CONTEXT)) == 1
    session.pause.assert_not_called()


def test_timeout_queries_same_action_and_does_not_submit_again(setup):
    coordinator, session, tickets, observation, proposal = setup

    def send(g, verb, command, **kwargs):
        if verb is Verb.SUBMIT:
            raise TimeoutError()
        return reply(command, verb)

    session.actor_action.side_effect = send
    assert (
        coordinator.advance(proposal, observation).acknowledgement.disposition
        is PvECombatDisposition.UNCERTAIN
    )
    original = action_calls(session)[0]
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    update = coordinator.advance(proposal, observation)
    assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, original)
    assert update.acknowledgement.disposition is PvECombatDisposition.QUEUED
    assert len(action_calls(session)) == 1 and len(tickets) == 2


def test_pending_action_rejects_changed_proposal(setup):
    coordinator, session, _, observation, proposal = setup

    def send(g, verb, command, **kwargs):
        if verb is Verb.SUBMIT:
            raise TimeoutError()
        return reply(command, verb)

    session.actor_action.side_effect = send
    coordinator.advance(proposal, observation)
    with pytest.raises(ValueError, match="unresolved"):
        coordinator.advance(replace(proposal, power_id=1), observation)
    assert len(action_calls(session)) == 1


def test_cancel_reuses_exact_stop_and_retains_parent_after_child_closure(setup):
    coordinator, session, tickets, observation, proposal = setup
    coordinator.advance(proposal, observation)
    session.actor_action.side_effect = TimeoutError()
    assert coordinator.stop("cancel")[0] is False
    first = session.actor_action.call_args.args[2]
    assert coordinator.active
    tickets[1].close.assert_not_called()
    assert coordinator.stop("cancel")[0] is False
    assert session.actor_action.call_args.args[1:3] == (Verb.STOP_CONTEXT, first)
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    assert coordinator.stop("cancel")[0] is True and not coordinator.active
    tickets[1].close.assert_called_once()
    tickets[0].close.assert_not_called()
    assert not coordinator.owner._obligation.released


def test_adopted_unknown_binding_cannot_be_released_by_never_bound_tombstone(setup):
    coordinator, session, _, observation, proposal = setup
    adopted = replace(proposal, kind=PvECombatKind.BIND, power_id=0, adopted_existing_action=True)

    def send(g, verb, command, **kwargs):
        if verb is Verb.ATTACH_CONTEXT:
            raise TimeoutError()
        result = reply(command, verb)
        if verb in (Verb.STOP_CONTEXT, Verb.STOP_OWNER):
            result.receipt = replace(result.receipt, closure=Closure.NEVER_BOUND)
        return result

    session.actor_action.side_effect = send
    coordinator.advance(adopted, observation)
    assert coordinator.stop("cancel")[0] is False and coordinator.active
    session.pause.assert_not_called()  # Adoption needs positive typed cleanup, not blanket PAUSE.


def test_deferred_action_does_not_charge_entry_and_new_context_needs_exact_closure(setup):
    coordinator, session, tickets, observation, proposal = setup

    def send(g, verb, command, **kwargs):
        result = reply(command, verb)
        if verb is Verb.SUBMIT:
            result.receipt = replace(
                result.receipt,
                outcome=Outcome.DEFERRED,
                entry=Entry.NEVER_ENTERED,
                local_settlement=LocalSettlement.SETTLED,
                flags=OWNER_CLEANUP | CONTEXT_CLEANUP,
            )
        return result

    session.actor_action.side_effect = send
    first = coordinator.advance(proposal, observation)
    assert first.acknowledgement.disposition is PvECombatDisposition.DEFERRED
    assert first.acknowledgement.native_entered is False
    assert coordinator.stop("reconsider")[0]
    second = coordinator.advance(replace(proposal, proposal_id=2), observation)
    assert first.receipt.context_id.value < second.receipt.context_id.value
    assert first.receipt.parent_id == second.receipt.parent_id and len(tickets) == 3


def test_unknown_action_is_stopped_after_bounded_resolution_time(setup):
    coordinator, session, _, observation, proposal = setup

    def send(g, verb, command, **kwargs):
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS, Verb.STOP_CONTEXT):
            raise TimeoutError()
        return reply(command, verb)

    session.actor_action.side_effect = send
    coordinator.advance(proposal, observation)
    observation.now_ms = 5000
    coordinator.advance(proposal, observation)
    assert session.actor_action.call_args.args[1] is Verb.STOP_CONTEXT
    stop = session.actor_action.call_args.args[2]
    observation.now_ms += 100
    coordinator.advance(proposal, observation)
    assert session.actor_action.call_args.args[2] is stop


def test_adopted_identity_survives_prebinding_failure(setup):
    coordinator, _, _, observation, proposal = setup
    adopted = replace(proposal, kind=PvECombatKind.BIND, power_id=0, adopted_existing_action=True)
    coordinator.owner.population.resolve_combat_addresses.side_effect = OSError("missing object")
    with pytest.raises(OSError):
        coordinator.advance(adopted, observation)
    assert coordinator.active
    with pytest.raises(ValueError, match="target"):
        coordinator.cleanup(PvECombatCleanupRequest(1, "different", adopted.target_key, "stop"))


def test_namespace_new_ordinal_cannot_redirect_old_context_stop(setup):
    coordinator, session, _, observation, proposal = setup
    coordinator.advance(proposal, observation)
    first = coordinator.owner.context.context_id
    newer = session.actor_ordinals.return_value.next(ContextId)
    assert newer.value > first.value
    session.actor_action.side_effect = TimeoutError()
    coordinator.stop("old-context stop")
    assert session.actor_action.call_args.args[1] is Verb.STOP_CONTEXT
    assert session.actor_action.call_args.args[2].context_id == first


def test_cleanup_waits_for_delayed_exact_closure_using_same_stop_identity(setup):
    coordinator, session, tickets, observation, proposal = setup
    coordinator.advance(proposal, observation)
    commands = []

    def send(grant, verb, command, **kwargs):
        commands.append(command)
        return reply(command, verb) if len(commands) == 4 else pending_reply(command, verb)

    session.actor_action.side_effect = send
    request = PvECombatCleanupRequest(1, proposal.target_token, proposal.target_key, "terminal")
    result = coordinator.cleanup(request)
    assert result.confirmed and not coordinator.active
    assert coordinator.owner.test_clock.now == pytest.approx(0.3)
    assert len(commands) == 4 and all(value is commands[0] for value in commands)
    tickets[1].close.assert_called_once()
    tickets[0].close.assert_not_called()


def test_cleanup_timeout_keeps_correlated_receipt_and_finish_cannot_reset_deadline(setup):
    coordinator, session, tickets, observation, proposal = setup
    coordinator.advance(proposal, observation)
    session.actor_action.side_effect = lambda g, v, c, **kw: pending_reply(c, v)
    request = PvECombatCleanupRequest(1, proposal.target_token, proposal.target_key, "terminal")
    result = coordinator.cleanup(request)
    assert not result.confirmed and coordinator.active and coordinator.owner.test_clock.now == 3
    count = session.actor_action.call_count
    assert not coordinator.finish("scope_exit")[0] and session.actor_action.call_count == count
    assert coordinator.owner._last_receipt.context_phase is Phase.STOPPING
    tickets[1].close.assert_not_called()


@pytest.mark.parametrize("remaining,close_fails", [(0.05, False), (0.0, False), (0.05, True)])
def test_final_child_ticket_closure_uses_remaining_budget_and_keeps_parent(
    setup, remaining, close_fails
):
    coordinator, session, tickets, observation, proposal = setup
    coordinator.advance(proposal, observation)
    obligation = coordinator.owner._obligation
    ticket = tickets[1]
    if close_fails:
        ticket.close.side_effect = TimeoutError("fence mutex unavailable")

    def send(grant, verb, command, **kwargs):
        coordinator.owner.test_clock.now = 3.0 - remaining
        return reply(command, verb)

    session.actor_action.side_effect = send
    confirmed, receipt, detail = coordinator.stop("terminal")
    assert context_cleanup_confirmed(receipt)
    tickets[0].close.assert_not_called()
    assert not obligation.released  # A child receipt never releases the actor owner.
    if remaining:
        ticket.close.assert_called_once()
        assert 49 <= ticket.close.call_args.kwargs["timeout_ms"] <= 50
    else:
        ticket.close.assert_not_called()
    if remaining and not close_fails:
        assert confirmed and detail is None and not coordinator.active
        assert obligation.deadline is None
    else:
        assert not confirmed and "TimeoutError" in detail and coordinator.active
        assert obligation.deadline == 3.0
        coordinator.owner.test_clock.now = 3.0
        before = session.actor_action.call_count
        assert not coordinator.finish("scope exit")[0]
        assert session.actor_action.call_count == before
