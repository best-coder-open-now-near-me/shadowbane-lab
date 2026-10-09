# ruff: noqa: F811
"""Same actor parent tracks without replacing the existing combat action."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_native_actor_coordinator import reply
from test_native_actor_coordinator import setup as actor_setup  # noqa: F401

from shadowbane_lab.client_extension.actor_action_wire import (
    OUTBOUND_QUEUED,
    Action,
    Closure,
    ClosureScope,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Reason,
    Verb,
)


def test_query_uses_same_parent_with_pending_combat_and_no_buff_manifest(actor_setup):
    owner, session, _, observation, proposal = actor_setup
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v, pending=True)
    owner.advance_combat(proposal, observation)
    pending = owner._local_command
    context = owner.context
    combat_proposal = owner._combat_proposal
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    result = owner._tracking_query(429578587)
    assert result.state == "queued"
    call = session.actor_action.call_args
    assert call.args[1] is Verb.SUBMIT
    command = call.args[2]
    assert command.action is Action.TRACK and command.context_id is None
    assert command.parent_id == owner.parent.owner_id and call.kwargs["context"] is None
    assert owner._local_command is pending and owner.context is context
    assert owner._combat_proposal is combat_proposal
    assert [c.args[1] for c in session.actor_action.call_args_list].count(Verb.OPEN_OWNER) == 1
    assert not any(c.args[1] is Verb.CANCEL_ACTION for c in session.actor_action.call_args_list)


def test_ambiguous_query_polls_original_without_replaying_or_overwriting_combat(actor_setup):
    owner, session, _, _, _ = actor_setup
    owner._ensure_open()
    session.actor_action.side_effect = OSError("ack lost")
    assert owner._tracking_query(429578587).state == "unknown"
    original = owner._tracking_command
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    assert owner._tracking_query(429578587, allow_new=False).state == "queued"
    assert session.actor_action.call_args.args[1] is Verb.ACTION_STATUS
    assert session.actor_action.call_args.args[2] is original
    assert owner._tracking_command is None
    count = session.actor_action.call_count
    assert owner._tracking_query(429578587, allow_new=False).state == "not_ready"
    assert session.actor_action.call_count == count


def test_known_native_admission_refusal_has_no_pending_query(actor_setup):
    owner, session, _, _, _ = actor_setup
    owner._ensure_open()
    def refused(g, v, c, **kw):
        receipt = reply(c, v).receipt
        receipt = replace(receipt, outcome=Outcome.DEFERRED,
            flags=receipt.flags & ~OUTBOUND_QUEUED, entry=Entry.NEVER_ENTERED,
            local_settlement=LocalSettlement.SETTLED, reason=Reason.NATIVE_USE)
        return SimpleNamespace(receipt=receipt, native_detail=None)
    session.actor_action.side_effect = refused
    result = owner._tracking_query(429578587)
    assert result.state == "not_ready" and result.detail == "native_use"
    assert owner._tracking_command is None


def test_preflight_failure_does_not_manufacture_pending_submission(actor_setup):
    owner, session, _, _, _ = actor_setup
    owner._ensure_open()
    session.require_actor_tracking.side_effect = RuntimeError("capability missing")
    with pytest.raises(RuntimeError, match="capability"):
        owner._tracking_query(429578587)
    assert owner._tracking_command is None
    assert all(c.args[1] is not Verb.SUBMIT for c in session.actor_action.call_args_list)


@pytest.mark.parametrize("phase,closure", [(Phase.RETIRED, Closure.SCENE_RETIRED),
                                          (Phase.CLOSED, Closure.LOCAL_RELEASED)])
def test_exact_terminal_query_owner_requires_cleanup_without_discarding_command(
        actor_setup, phase, closure):
    from shadowbane_lab.pve.tracking import TrackingActorChanged

    owner, session, _, _, _ = actor_setup
    owner._ensure_open()
    def retired(g, v, c, **kw):
        receipt = replace(reply(c, v).receipt, owner_phase=phase,
            outcome=Outcome.STALE, flags=0, entry=Entry.UNKNOWN,
            closure=closure, closure_scope=ClosureScope.OWNER)
        return SimpleNamespace(receipt=receipt, native_detail=None)
    session.actor_action.side_effect = retired
    with pytest.raises(TrackingActorChanged):
        owner._tracking_query(429578587)
    assert owner._tracking_command is not None
    assert not owner._obligation.released
