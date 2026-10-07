"""Child cleanup cannot consume the only budget for its parent's local work."""

from dataclasses import replace

import pytest
from test_native_actor_coordinator import setup as actor_fixture
from test_native_actor_preparation import configure

from shadowbane_lab.client_extension.actor_action_wire import (
    APPLICATION_PENDING,
    OUTBOUND_QUEUED,
    UNCERTAIN_HISTORY,
    Action,
    Application,
    Closure,
    ClosureScope,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Verb,
)
from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
from shadowbane_lab.pve.model import PvECombatCleanupRequest
from shadowbane_lab.pve.preparation import PreparationAction

setup = actor_fixture


def pending_stop(receipt, *, owner=False):
    return replace(
        receipt,
        outcome=Outcome.PENDING,
        owner_phase=Phase.STOPPING if owner else Phase.BOUND,
        context_phase=Phase.UNKNOWN if owner else Phase.STOPPING,
        closure=Closure.NONE,
        closure_scope=ClosureScope.NONE,
        flags=1 if owner else 3,
    )


def encounter(setup, monkeypatch, *, uncertain=True, local_pending=True, child_closes=False):
    owner, session, tickets, observation, attack = setup
    settings = BuffSettings(True, (BuffGroup("beorc", (
        BuffAction(PreparationAction("beorc", power_id=429590426), 429590426),
    )),))
    _, send = configure(owner, session, monkeypatch, settings)
    clock = [0.0]
    session.cleanup.clock = lambda: clock[0]
    session.cleanup.sleeper = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    owner_responses = []

    def native(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.SELF_POWER:
            result.receipt = replace(
                result.receipt,
                outcome=Outcome.UNCERTAIN if uncertain else Outcome.CLIENT_OUTBOUND_QUEUED,
                entry=Entry.ENTERED,
                local_settlement=(LocalSettlement.PENDING if local_pending
                                  else LocalSettlement.SETTLED),
                application=Application.PENDING,
                flags=(result.receipt.flags & ~OUTBOUND_QUEUED
                       | APPLICATION_PENDING | UNCERTAIN_HISTORY)
                if uncertain else result.receipt.flags | APPLICATION_PENDING,
            )
        if verb is Verb.STOP_CONTEXT and not child_closes:
            result.receipt = pending_stop(result.receipt)
        if verb is Verb.STOP_OWNER and owner_responses:
            response = owner_responses.pop(0)
            if response == "pending":
                result.receipt = pending_stop(result.receipt, owner=True)
            elif response == "wrong":
                result.receipt = replace(result.receipt, command_digest=b"x" * 32)
            elif response == "missing":
                raise TimeoutError("missing stop reply")
        return result

    session.actor_action.side_effect = native
    assert owner.advance_combat(attack, observation).acknowledgement.disposition.value == "queued"
    child = owner.context
    buff = owner.preparation_step()
    assert buff.command.power_id == 429590426 and buff.command.context_id is None
    return owner, session, clock, child, buff, owner_responses, attack, observation, tickets


@pytest.mark.parametrize("uncertain", [False, True])
def test_child_blocked_by_parent_action_stops_aggregate_with_original_budget(
    setup, monkeypatch, uncertain
):
    owner, session, clock, child, buff, responses, attack, observation, tickets = encounter(
        setup, monkeypatch, uncertain=uncertain
    )
    responses.extend(["pending", "pending"])
    cleanup = owner.cleanup_context(PvECombatCleanupRequest(
        0, attack.target_token, attack.target_key, "native_death"
    ))
    confirmed, receipt, _ = owner._last_context_result
    assert cleanup.confirmed and cleanup.owner_closed
    assert cleanup.request_key == receipt.request.encode().hex()
    assert cleanup.as_dict()["owner_closed"] is True
    assert confirmed and receipt.verb is Verb.STOP_OWNER
    assert receipt.closure_scope is ClosureScope.OWNER and receipt.context_id is None
    assert receipt.owner_phase is Phase.CLOSED and receipt.closure is Closure.NATIVE_STOPPED
    calls = [(c.args[1], c.args[2]) for c in session.actor_action.call_args_list]
    stops = [(v, c) for v, c in calls if v in (Verb.STOP_CONTEXT, Verb.STOP_OWNER)]
    assert [v for v, c in stops] == [Verb.STOP_CONTEXT] + [Verb.STOP_OWNER] * 3
    assert stops[0][1].context_id == child.context_id
    assert all(c == stops[1][1] for v, c in stops[1:])
    assert all(c.parent_id == owner.parent.owner_id for v, c in stops)
    assert owner._obligation.deadline == 3.0 and clock[0] < 3.0
    assert owner._obligation.released and session.cleanup.blocked(owner.grant)
    assert owner.context is None and owner._closed and owner._terminal
    # Positive local cleanup is not fabricated application success or policy ACK.
    assert owner._preparation_policy.pending_proposal == buff.decision.proposal
    assert owner._last_preparation_receipt.application is Application.PENDING
    assert owner._last_preparation_receipt.local_settlement is LocalSettlement.PENDING
    before = len(calls)
    assert owner.finish_context("again") == (confirmed, receipt, None)
    assert owner.finish("terminal") == (confirmed, receipt, None)
    assert owner.preparation_step() is None
    following = owner.advance_combat(replace(attack, proposal_id=2), observation)
    assert following.acknowledgement.disposition.value == "rejected"
    assert following.terminal_reason == "actor_owner_closed"
    assert session.actor_action.call_count == before
    assert len([c for v, c in calls if v is Verb.SUBMIT]) == 2
    for ticket in tickets:
        ticket.close.assert_called()


@pytest.mark.parametrize("failure", ["pending", "missing", "wrong"])
def test_aggregate_timeout_preserves_obligation_without_new_deadline(setup, monkeypatch, failure):
    owner, session, clock, _, buff, responses, _, _, _ = encounter(setup, monkeypatch)
    responses.extend([failure] * 100)
    confirmed, _, _ = owner.finish_context("native_death")
    assert not confirmed and not owner._obligation.released
    assert clock[0] == 3.0 and owner._obligation.deadline == 3.0
    calls = [(c.args[1], c.args[2]) for c in session.actor_action.call_args_list]
    stops = [c for v, c in calls if v is Verb.STOP_OWNER]
    assert stops and all(c == stops[0] for c in stops)
    assert len([v for v, c in calls if v is Verb.STOP_CONTEXT]) == 1
    assert not owner.finish("finally")[0]
    assert session.actor_action.call_count == len(calls)
    assert owner._local_command is buff.command
    assert owner._preparation_policy.pending_proposal == buff.decision.proposal
    assert owner.preparation_step() is None


def test_positive_child_closure_does_not_cancel_parent_cast(setup, monkeypatch):
    owner, session, _, _, buff, _, _, _, _ = encounter(
        setup, monkeypatch, child_closes=True
    )
    confirmed, receipt, _ = owner.finish_context("no_child_native_work")
    assert confirmed and receipt.closure_scope is ClosureScope.CONTEXT
    assert not owner._terminal and not owner._obligation.released
    assert owner._obligation.deadline is None and owner._local_command is buff.command
    assert not any(c.args[1] is Verb.STOP_OWNER for c in session.actor_action.call_args_list)


def test_remote_application_pending_does_not_trigger_aggregate_stop(setup, monkeypatch):
    owner, session, _, _, _, _, _, _, _ = encounter(
        setup, monkeypatch, uncertain=False, local_pending=False
    )
    assert owner._local_command is None
    assert not owner.stop_context("native_death")[0]
    assert not owner._terminal and not owner._obligation.released
    assert not any(c.args[1] is Verb.STOP_OWNER for c in session.actor_action.call_args_list)


def test_foreign_local_command_never_authorizes_aggregate_stop(setup, monkeypatch):
    owner, session, _, _, buff, _, _, _, _ = encounter(setup, monkeypatch)
    owner._local_command = replace(buff.command, parent_digest=b"x" * 32)
    assert not owner.stop_context("native_death")[0]
    assert not owner._terminal
    assert not any(c.args[1] is Verb.STOP_OWNER for c in session.actor_action.call_args_list)


@pytest.mark.parametrize("failure", ["missing", "wrong_command"])
def test_unmatched_child_reply_does_not_authorize_aggregate_stop(setup, monkeypatch, failure):
    owner, session, _, _, _, _, _, _, _ = encounter(setup, monkeypatch)
    native = session.actor_action.side_effect

    def reply(grant, verb, command, **kwargs):
        result = native(grant, verb, command, **kwargs)
        if verb is Verb.STOP_CONTEXT:
            if failure == "missing":
                raise TimeoutError("missing child response")
            result.receipt = replace(result.receipt, command_digest=b"x" * 32)
        return result

    session.actor_action.side_effect = reply
    assert not owner.stop_context("native_death")[0]
    assert not owner._terminal and not owner._obligation.released
    assert not any(c.args[1] is Verb.STOP_OWNER for c in session.actor_action.call_args_list)


def test_npc_runner_stops_after_aggregate_closure_instead_of_reacquiring():
    from test_pve_controller import (
        AdvancingClock,
        RecordingPvEDispatcher,
        SequenceHealthSource,
        SequencePlayerVitalsSource,
        _absent,
        _player,
        _runner,
        _target,
    )

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvEPhase
    from shadowbane_lab.pve.model import PvECombatCleanupResult

    calls = []

    class Cleanup:
        def cleanup(self, request):
            calls.append(request)
            return PvECombatCleanupResult(request, True, "exact-owner-stop", owner_closed=True)

    clock, dispatcher = AdvancingClock(), RecordingPvEDispatcher()
    health = SequenceHealthSource((
        _absent(), _target("mob"), _target("mob", current=0),
        _target("mob", current=0), _target("next"),
    ))
    result = _runner(
        controller=PvEController(PvEControllerConfig(maximum_kills=2, post_kill_delay_ms=100)),
        health_reader=health,
        player_vitals_reader=SequencePlayerVitalsSource((_player(),) * 5),
        dispatcher=dispatcher, stop_signal=EventEmergencyStop(), clock=clock, sleeper=clock.sleep,
        combat_cleanup=Cleanup(),
    ).run()
    assert result.final_phase is PvEPhase.STOPPED and result.terminal_reason == "actor_owner_closed"
    assert result.kills == 1 and len(calls) == 1
    assert len(dispatcher.intents) == 1 and health.values
    clean = [step.combat_cleanup for step in result.trace if step.combat_cleanup is not None]
    assert len(clean) == 1 and clean[0].confirmed and clean[0].owner_closed


@pytest.mark.parametrize("confirmed,closed", [(False, True), (True, 1)])
def test_cleanup_result_rejects_unproved_or_untyped_owner_closure(confirmed, closed):
    from test_pve_combat_cleanup import request

    from shadowbane_lab.pve.model import PvECombatCleanupResult

    with pytest.raises(ValueError):
        PvECombatCleanupResult(request(), confirmed, "owner-stop", owner_closed=closed)
