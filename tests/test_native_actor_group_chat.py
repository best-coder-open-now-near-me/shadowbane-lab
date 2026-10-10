# ruff: noqa: F811
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_native_actor_coordinator import reply
from test_native_actor_coordinator import setup as actor_setup  # noqa: F401
from test_tracking_callouts import response

from shadowbane_lab.client_extension.actor_action_wire import (
    OUTBOUND_QUEUED,
    Action,
    Entry,
    LocalSettlement,
    Outcome,
    Verb,
)
from shadowbane_lab.client_observation.native_group import NativeGroupContext, NativeGroupReadError
from shadowbane_lab.pve.tracking_callouts import TrackingAppearances


@pytest.fixture
def callouts(actor_setup):
    owner, session, _, observation, proposal = actor_setup
    owner._callouts = TrackingAppearances()
    owner._group_reader = Mock()
    owner._group_reader.observe_context.return_value = NativeGroupContext(
        0x10000, 0x20000, 0x30000, ((0x40000, 0x50000, 9, 53, 0x16),))
    owner._group_callout_step(response(1), allow_new=True)
    return owner, session, observation, proposal


def test_group_arrival_uses_same_owner_without_replacing_cast(callouts):
    owner, session, observation, proposal = callouts
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v, pending=True)
    owner.advance_combat(proposal, observation)
    pending, context = owner._local_command, owner.context
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    owner._group_callout_step(response(2, "Alice"), allow_new=True)
    command = session.actor_action.call_args.args[2]
    assert command.action is Action.GROUP_CHAT and command.group_text == "Hunt Foe: Alice"
    assert command.context_id is None and command.parent_id == owner.parent.owner_id
    assert command.group_digest == owner._group_context.digest
    assert owner._local_command is pending and owner.context is context
    count = session.actor_action.call_count
    owner._group_callout_step(response(3, "Alice"), allow_new=True)
    assert session.actor_action.call_count == count
    assert all(call.args[1] is not Verb.CANCEL_ACTION
               for call in session.actor_action.call_args_list)


def test_uncertain_send_only_polls_original_even_if_entry_disabled(callouts):
    owner, session, _, _ = callouts
    assert owner._ensure_open()
    session.actor_action.side_effect = OSError("lost reply")
    owner._group_callout_step(response(2, "Alice"), allow_new=True)
    command = owner._chat_command
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    owner._group_callout_step(response(3, "Alice"), allow_new=False)
    assert session.actor_action.call_args.args[1] is Verb.ACTION_STATUS
    assert session.actor_action.call_args.args[2] is command
    assert owner._chat_command is None and owner._chat_pending is None


@pytest.mark.parametrize("change", ["none", "group", "departed", "stale"])
def test_definite_no_entry_retries_only_fresh_same_group_arrival(callouts, change):
    owner, session, _, _ = callouts
    assert owner._ensure_open()
    def refuse(g, v, c, **kw):
        r = replace(reply(c, v).receipt, outcome=Outcome.DEFERRED,
                    entry=Entry.NEVER_ENTERED, local_settlement=LocalSettlement.SETTLED,
                    flags=reply(c, v).receipt.flags & ~OUTBOUND_QUEUED)
        return SimpleNamespace(receipt=r, native_detail=None)
    session.actor_action.side_effect = refuse
    owner._group_callout_step(response(2, "Alice"), allow_new=True)
    first = session.actor_action.call_args.args[2]
    assert owner._chat_pending and owner._chat_command is None
    session.actor_action.reset_mock()
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    status = response(3, "Alice")
    if change == "group":
        owner._group_reader.observe_context.return_value = replace(
            owner._group_context, manager=0x21000)
    elif change == "departed":
        status = response(3)
    elif change == "stale":
        status = replace(status, state="stale", current=False)
    owner._group_callout_step(status, allow_new=True)
    if change == "none":
        second = session.actor_action.call_args.args[2]
        assert second.request != first.request and second.group_text == first.group_text
    else:
        session.actor_action.assert_not_called()


def test_unavailable_group_does_not_reset_presence_and_context_change_seeds(callouts):
    owner, session, _, _ = callouts
    owner._group_callout_step(response(2, "Alice"), allow_new=True)
    count = session.actor_action.call_count
    original = owner._group_context
    owner._group_reader.observe_context.side_effect = NativeGroupReadError("unavailable")
    owner._group_callout_step(response(3), allow_new=True)
    owner._group_reader.observe_context.side_effect = None
    owner._group_callout_step(response(4, "Alice"), allow_new=True)
    assert session.actor_action.call_count == count
    owner._group_reader.observe_context.return_value = replace(original, manager=0x21000)
    owner._group_callout_step(response(5, "Bob"), allow_new=True)
    assert session.actor_action.call_count == count


def test_busy_arrivals_coalesce_and_departures_are_pruned_before_send(callouts):
    owner, session, _, _ = callouts
    assert owner._ensure_open()
    def refuse(g, v, c, **kw):
        r = replace(reply(c, v).receipt, outcome=Outcome.DEFERRED,
                    entry=Entry.NEVER_ENTERED, flags=reply(c, v).receipt.flags & ~OUTBOUND_QUEUED)
        return SimpleNamespace(receipt=r, native_detail=None)
    session.actor_action.side_effect = refuse
    owner._group_callout_step(response(2, "Alice"), allow_new=True)
    assert owner._chat_state == "withheld"
    owner._group_callout_step(response(3, "Alice", "Bob"), allow_new=True)
    assert session.actor_action.call_args.args[2].group_text == "Hunt Foe: Alice, Bob"
    session.actor_action.side_effect = lambda g, v, c, **kw: reply(c, v)
    owner._group_callout_step(response(4, "Bob", "Carol"), allow_new=True)
    assert session.actor_action.call_args.args[2].group_text == "Hunt Foe: Bob, Carol"
    assert owner._chat_state == "queued" and "delivery unconfirmed" in owner._chat_detail


def test_group_chat_capability_loss_does_not_abort_other_owner_work(callouts):
    from shadowbane_lab.client_extension.action_channel import NativeActionChannelUnavailable
    owner, session, _, _ = callouts
    assert owner._ensure_open()
    session.actor_action.reset_mock()
    session.require_actor_group_chat.side_effect = NativeActionChannelUnavailable("lost capability")
    owner._group_callout_step(response(2, "Alice"), allow_new=True)
    assert owner._chat_state == "withheld" and owner._chat_command is None
    session.actor_action.assert_not_called()
