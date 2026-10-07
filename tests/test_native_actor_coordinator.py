"""Exact parent ownership survives child turnover and local/remote action separation."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_actor_action_wire import fixture

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.actor_action_fence import Ordinals
from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OUTBOUND_QUEUED,
    OWNER_CLEANUP,
    Action,
    Closure,
    ClosureScope,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Receipt,
    Verb,
)
from shadowbane_lab.client_extension.cleanup_settlement import CleanupSettlement
from shadowbane_lab.client_extension.movement_session import NativeMovementGrant
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve.model import PvECombatDisposition, PvECombatKind, PvECombatProposal
from shadowbane_lab.pve.native_actor import NativeActorCoordinator


def reply(c, v, *, pending=False):
    owner = Phase.BOUND
    context = Phase.BOUND if c.context_id else Phase.UNKNOWN
    closure, scope = Closure.NONE, ClosureScope.NONE
    outcome = Outcome.BOUND
    entry, local = Entry.UNKNOWN, LocalSettlement.UNKNOWN
    flags = OWNER_CLEANUP | (CONTEXT_CLEANUP if c.context_id else 0)
    if c.action is not Action.NONE:
        outcome, entry = Outcome.CLIENT_OUTBOUND_QUEUED, Entry.ENTERED
        local = LocalSettlement.PENDING if pending else LocalSettlement.SETTLED
        flags |= OUTBOUND_QUEUED
    if v is Verb.STOP_CONTEXT:
        context, closure, scope = Phase.CLOSED, Closure.NATIVE_STOPPED, ClosureScope.CONTEXT
        flags, outcome = OWNER_CLEANUP, Outcome.ENGAGEMENT_CLOSED
    if v is Verb.STOP_OWNER:
        owner, closure, scope = Phase.CLOSED, Closure.NATIVE_STOPPED, ClosureScope.OWNER
        context = Phase.CLOSED if c.context_id else Phase.UNKNOWN
        flags, outcome = 0, Outcome.ENGAGEMENT_CLOSED
    r = Receipt(
        c.request,
        c.host,
        c.window,
        outcome,
        flags,
        c.grant,
        c.parent_id,
        c.context_id,
        c.digest,
        v,
        c.action,
        entry,
        local,
        owner,
        context,
        closure,
        mode=1 if closure is not Closure.NONE else 2,
        closure_scope=scope,
    )
    r.require_command(c, v)
    return SimpleNamespace(receipt=r, native_detail=None)


@pytest.fixture
def setup():
    parent, _, c, _ = fixture()
    grant = NativeMovementGrant(
        NativeClientProcessIdentity(parent.client_pid, parent.client_creation),
        c.window,
        c.grant,
        c.host,
        "owner",
    )
    session = Mock()
    session.cleanup = CleanupSettlement()
    session.actor_ordinals.return_value = Ordinals()
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    key, target = NativeObjectKey(*parent.actor_key), NativeObjectKey(23885, 37)
    population = Mock()
    population.observe_actor_identity.return_value = ("actor-token", key, None)
    population.resolve_actor_address.return_value = parent.actor_hint
    population.resolve_combat_addresses.return_value = (parent.actor_hint, 0x12400000)
    character = Mock()
    character.binding = SimpleNamespace(
        object_key=key, identity=SimpleNamespace(character_name="Umbra", server_name="Wonderbane")
    )
    tickets = []

    def factory(*args, **kwargs):
        ticket = Mock()
        tickets.append(ticket)
        return ticket

    owner = NativeActorCoordinator(
        session=session,
        grant=grant,
        population=population,
        character_session=character,
        store=SimpleNamespace(owner=SimpleNamespace(storage_key="aa" * 32)),
        ticket_factory=factory,
    )
    obs = SimpleNamespace(now_ms=0, population=SimpleNamespace(local_player_object_key=key))
    proposal = PvECombatProposal(1, "npc", target, PvECombatKind.ATTACK)
    return owner, session, tickets, obs, proposal


def test_context_cleanup_retains_parent_and_obligation_for_next_target(setup):
    owner, s, tickets, o, p = setup
    obligation = owner._obligation
    assert owner.advance_combat(p, o).acknowledgement.disposition is PvECombatDisposition.QUEUED
    first = owner.context
    assert owner.finish_context("dead")[0]
    assert owner._obligation is obligation and not obligation.released
    assert obligation.deadline is None
    tickets[0].close.assert_not_called()
    second = replace(p, proposal_id=2, target_token="second", target_key=NativeObjectKey(23886, 37))
    owner.population.resolve_combat_addresses.return_value = (owner.parent.actor_hint, 0x12400100)
    assert (
        owner.advance_combat(second, o).acknowledgement.disposition is PvECombatDisposition.QUEUED
    )
    assert owner.context.context_id != first.context_id
    assert owner.context.parent_digest == first.parent_digest
    assert [x.args[1] for x in s.actor_action.call_args_list].count(Verb.OPEN_OWNER) == 1
    s.pause.assert_not_called()
    assert owner.finish("shutdown")[0]
    assert obligation.released


def test_positive_queue_local_pending_polls_before_next_action(setup):
    owner, s, _, o, p = setup
    s.actor_action.side_effect = lambda g, v, c, **kw: reply(
        c, v, pending=c.action is not Action.NONE
    )
    assert owner.advance_combat(p, o).acknowledgement.disposition is PvECombatDisposition.QUEUED
    first = owner._local_command
    nextp = replace(p, proposal_id=2)
    assert (
        owner.advance_combat(nextp, o).acknowledgement.disposition is PvECombatDisposition.UNCERTAIN
    )
    assert s.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, first)
    s.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    assert owner.advance_combat(nextp, o).acknowledgement.disposition is PvECombatDisposition.QUEUED
    submits = [x.args[2] for x in s.actor_action.call_args_list if x.args[1] is Verb.SUBMIT]
    assert len(submits) == 2 and submits[0].request != submits[1].request


def test_transport_uncertain_never_resubmits_or_changes_proposal(setup):
    owner, s, _, o, p = setup

    def send(g, v, c, **kw):
        if v is Verb.SUBMIT:
            raise TimeoutError()
        return reply(c, v)

    s.actor_action.side_effect = send
    assert owner.advance_combat(p, o).acknowledgement.disposition is PvECombatDisposition.UNCERTAIN
    old = owner._combat_command
    with pytest.raises(ValueError, match="immutable"):
        owner.advance_combat(replace(p, proposal_id=2), o)
    assert owner.advance_combat(p, o).acknowledgement.disposition is PvECombatDisposition.QUEUED
    assert s.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, old)


def test_context_stop_retries_identical_command_and_keeps_parent(setup):
    owner, s, _, o, p = setup
    owner.advance_combat(p, o)
    s.actor_action.side_effect = TimeoutError()
    assert not owner.stop_context("stop")[0]
    command = owner._stop_context_command
    deadline = owner._obligation.deadline
    assert not owner.stop_context("again")[0]
    assert s.actor_action.call_args.args[1:3] == (Verb.STOP_CONTEXT, command)
    assert owner._obligation.deadline == deadline
    s.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    assert owner.stop_context("again")[0]
    assert owner._opened and not owner._obligation.released


def test_final_owner_requires_owner_scoped_proof(setup):
    owner, s, _, o, p = setup
    owner.advance_combat(p, o)

    def wrong(g, v, c, **kw):
        r = reply(c, v).receipt
        if v is Verb.STOP_OWNER:
            r = replace(
                r, owner_phase=Phase.BOUND, flags=OWNER_CLEANUP, closure_scope=ClosureScope.CONTEXT
            )
        return SimpleNamespace(receipt=r, native_detail=None)

    s.actor_action.side_effect = wrong
    assert not owner._stop_owner_once("stop")[0]
    assert not owner._obligation.released and not owner._closed


@pytest.mark.parametrize("change", ["token", "key", "address", "session"])
def test_parent_identity_changes_never_publish_input(setup, change):
    owner, s, _, o, p = setup
    if change == "token":
        owner.population.observe_actor_identity.return_value = ("new", owner.actor_key, None)
    elif change == "key":
        owner.population.observe_actor_identity.return_value = (
            owner.actor_token,
            NativeObjectKey(7, 53),
            None,
        )
    elif change == "address":
        owner.population.resolve_actor_address.return_value = 0x12300100
    else:
        owner.character_session.require_current.side_effect = RuntimeError("revoked")
    with pytest.raises((ValueError, RuntimeError)):
        owner.advance_combat(p, o)
    s.actor_action.assert_not_called()


def test_uncertain_positive_queue_history_never_acknowledges_new_input(setup):
    owner, session, _, observation, proposal = setup

    def uncertain(grant, verb, command, **kwargs):
        result = reply(command, verb)
        if command.action is not Action.NONE:
            result.receipt = replace(result.receipt, outcome=Outcome.UNCERTAIN)
        return result

    session.actor_action.side_effect = uncertain
    update = owner.advance_combat(proposal, observation)
    assert update.acknowledgement.disposition is PvECombatDisposition.UNCERTAIN
    assert owner.pending is proposal
    assert update.receipt.flags & OUTBOUND_QUEUED


def test_adopted_failed_prebinding_retains_target_for_cleanup_correlation(setup):
    from shadowbane_lab.pve.model import PvECombatCleanupRequest

    owner, session, _, observation, proposal = setup
    adopted = replace(proposal, kind=PvECombatKind.BIND, adopted_existing_action=True)
    owner.population.resolve_combat_addresses.side_effect = RuntimeError("registry unavailable")
    with pytest.raises(RuntimeError):
        owner.advance_combat(adopted, observation)
    assert owner.active and owner.context is None
    with pytest.raises(ValueError, match="retained"):
        owner.cleanup_context(PvECombatCleanupRequest(1, "other", proposal.target_key, "stop"))


def test_scene_retirement_context_reply_closes_aggregate_owner_never_rearms(setup):
    owner, session, _, observation, proposal = setup
    owner.advance_combat(proposal, observation)

    def retired(grant, verb, command, **kwargs):
        result = reply(command, verb)
        if verb is Verb.STOP_CONTEXT:
            result.receipt = replace(
                result.receipt,
                owner_phase=Phase.RETIRED,
                context_phase=Phase.RETIRED,
                closure=Closure.SCENE_RETIRED,
                closure_scope=ClosureScope.OWNER,
                flags=0,
            )
        return result

    session.actor_action.side_effect = retired
    assert owner.stop_context("retired")[0]
    assert owner._closed and owner._obligation.released
    assert owner.finish("again")[0]
    assert (
        owner.advance_combat(
            replace(proposal, proposal_id=2), observation
        ).acknowledgement.disposition
        is PvECombatDisposition.UNCERTAIN
    )


def test_parent_cancel_child_ack_keeps_terminal_deadline_until_owner_stop(setup):
    owner, _, _, observation, proposal = setup
    owner.advance_combat(proposal, observation)
    owner.session.cleanup.request_terminal(owner.grant)
    assert owner.stop_context("parent_cancel")[0]
    assert owner._obligation.deadline is not None and not owner._obligation.released
    assert owner.finish("parent_cancel")[0] and owner._obligation.released


def test_unattached_adopted_action_cannot_close_via_local_release(setup):
    owner, session, _, observation, proposal = setup
    adopted = replace(proposal, kind=PvECombatKind.BIND, adopted_existing_action=True)

    def respond(grant, verb, command, **kwargs):
        if verb is Verb.ATTACH_CONTEXT:
            raise TimeoutError("adoption not proven")
        result = reply(command, verb)
        if verb is Verb.STOP_OWNER:
            result.receipt = replace(result.receipt, closure=Closure.LOCAL_RELEASED)
        return result

    session.actor_action.side_effect = respond
    owner.advance_combat(adopted, observation)
    assert owner._adopted
    confirmed, receipt, _ = owner._stop_owner_once("cancel_adoption")
    assert receipt.closure is Closure.LOCAL_RELEASED and not confirmed
    assert owner.active and not owner._closed and not owner._obligation.released
    session.pause.assert_not_called()


@pytest.mark.parametrize("missing", [False, True])
def test_next_combat_wait_has_only_correlated_prior_action_progress(setup, missing):
    owner, session, _, observation, first = setup
    settled = False
    failed = False

    def response(grant, verb, command, **kwargs):
        if failed and verb is Verb.ACTION_STATUS:
            raise TimeoutError("unavailable original action")
        return reply(command, verb, pending=command.action is not Action.NONE and not settled)

    session.actor_action.side_effect = response
    assert (
        owner.advance_combat(first, observation).acknowledgement.disposition
        is PvECombatDisposition.QUEUED
    )
    original = owner._local_command
    next_proposal = replace(first, proposal_id=first.proposal_id + 1)
    for milliseconds in (1_000, 6_000, 18_000):
        observation.now_ms = milliseconds
        assert (
            owner.advance_combat(next_proposal, observation).acknowledgement.disposition
            is PvECombatDisposition.UNCERTAIN
        )
        assert owner._local_command is original
    failed = missing
    settled = not missing
    observation.now_ms = 23_000
    result = owner.advance_combat(next_proposal, observation)
    submits = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    if missing:
        assert result.acknowledgement.disposition is PvECombatDisposition.REJECTED
        assert len(submits) == 1 and owner.context is None
        assert session.actor_action.call_args.args[1] is Verb.STOP_CONTEXT
    else:
        assert result.acknowledgement.disposition is PvECombatDisposition.QUEUED
        assert len(submits) == 2 and submits[0].request != submits[1].request
    assert owner.finish("test_complete")[0]
