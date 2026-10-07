"""Unconfirmed admission must finish exact cleanup, not wait for encounter timeout."""
from dataclasses import replace

import pytest
from test_native_actor_coordinator import reply
from test_native_actor_coordinator import setup as actor_fixture

from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OWNER_CLEANUP,
    Closure,
    ClosureScope,
    Outcome,
    Phase,
    Reason,
    Verb,
)
from shadowbane_lab.pve.model import PvECombatDisposition

setup = actor_fixture


def fake_clock(session):
    value = [0.0]
    session.cleanup.clock = lambda: value[0]
    session.cleanup.sleeper = lambda seconds: value.__setitem__(0, value[0] + seconds)
    return value


def pending(result):
    result.receipt = replace(result.receipt, outcome=Outcome.PENDING,
        owner_phase=Phase.BOUND, context_phase=Phase.STOPPING,
        closure=Closure.NONE, closure_scope=ClosureScope.NONE,
        flags=OWNER_CLEANUP | CONTEXT_CLEANUP, reason=Reason.INITIATION)
    return result


def expired(result):
    result.receipt = replace(result.receipt, outcome=Outcome.HISTORY_EXPIRED,
        owner_phase=Phase.UNKNOWN, context_phase=Phase.UNKNOWN,
        closure=Closure.HISTORY_EXPIRED, closure_scope=ClosureScope.NONE, flags=0)
    return result


@pytest.mark.parametrize('preexisting_stop', [False, True])
def test_nonterminal_empty_admission_then_exact_pending_stop_completes(setup, preexisting_stop):
    owner, session, _, observation, proposal = setup
    clock = fake_clock(session)
    stops = []

    def send(g, v, c, **kw):
        result = reply(c, v)
        if v in (Verb.ATTACH_CONTEXT, Verb.CONTEXT_STATUS):
            return pending(result)
        if v is Verb.STOP_CONTEXT:
            stops.append(c)
            if len(stops) == 1:
                return pending(result)
        return result

    session.actor_action.side_effect = send
    initial = owner.advance_combat(proposal, observation)
    assert initial.receipt.verb is Verb.ATTACH_CONTEXT
    assert initial.receipt.reason is Reason.INITIATION
    assert initial.as_dict()['native_reason'] == 'initiation'
    assert initial.command == owner._attach_command
    follow = owner.advance_combat(proposal, observation)
    assert follow.receipt.verb is Verb.CONTEXT_STATUS
    assert follow.command == initial.command
    if preexisting_stop:
        assert not owner.stop_context('external_cleanup')[0]
        clock[0] = 1.0
    observation.now_ms = 5000
    settled = owner.advance_combat(proposal, observation)
    assert settled.acknowledgement.disposition is PvECombatDisposition.REJECTED
    assert settled.terminal_reason is None
    assert settled.receipt.closure is Closure.NATIVE_STOPPED
    assert len(stops) == 2 and stops[0] == stops[1] == settled.command
    assert settled.as_dict()['preceding_replies'][-1]['outcome'] == 'pending'
    assert not owner.active and not owner._obligation.released
    assert owner._obligation.deadline is None and clock[0] < 3.0
    assert not any(c.args[1] is Verb.SUBMIT for c in session.actor_action.call_args_list)
    assert sum(c.args[1] is Verb.ATTACH_CONTEXT for c in session.actor_action.call_args_list) == 1


def test_missing_cleanup_exhausts_original_deadline_without_more_attempts(setup):
    owner, session, _, observation, proposal = setup
    clock = fake_clock(session)

    def send(g, v, c, **kw):
        if v is Verb.STOP_CONTEXT:
            raise TimeoutError('lost reply')
        return pending(reply(c, v)) if v is Verb.ATTACH_CONTEXT else reply(c, v)

    session.actor_action.side_effect = send
    owner.advance_combat(proposal, observation)
    assert not owner.stop_context('first')[0]
    deadline = owner._obligation.deadline
    clock[0] = 2.8
    stopped = owner.advance_combat(proposal, observation)
    assert clock[0] == deadline == 3.0
    assert stopped.terminal_reason == 'combat_cleanup_unconfirmed'
    assert stopped.receipt is None and stopped.command == owner._stop_context_command
    assert stopped.as_dict()['native_reason'] is None
    assert stopped.as_dict()['command_digest'] == stopped.command.digest.hex()
    count = session.actor_action.call_count
    again = owner.advance_combat(proposal, observation)
    assert again.terminal_reason == stopped.terminal_reason
    assert session.actor_action.call_count == count
    assert owner.active and not owner._obligation.released


@pytest.mark.parametrize('lost', [False, True])
def test_untrusted_attach_reply_never_creates_native_evidence(setup, lost):
    owner, session, _, observation, proposal = setup

    def send(g, v, c, **kw):
        result = reply(c, v)
        if v is Verb.ATTACH_CONTEXT:
            if lost:
                raise TimeoutError()
            result.receipt = replace(result.receipt, command_digest=b'x'*32)
        return result

    session.actor_action.side_effect = send
    update = owner.advance_combat(proposal, observation)
    assert update.receipt is None and update.command == owner._attach_command
    assert update.as_dict()['native_reason'] is None
    assert 'actor receipt unavailable:' in update.detail


def test_immediate_never_bound_keeps_admission_and_stop_evidence(setup):
    owner, session, _, observation, proposal = setup
    fake_clock(session)

    def send(g, v, c, **kw):
        result = reply(c, v)
        if v in (Verb.ATTACH_CONTEXT, Verb.STOP_CONTEXT):
            result.receipt = replace(result.receipt, outcome=Outcome.ENGAGEMENT_CLOSED,
                context_phase=Phase.CLOSED, closure=Closure.NEVER_BOUND,
                closure_scope=ClosureScope.CONTEXT, flags=OWNER_CLEANUP, reason=Reason.INITIATION)
        return result

    session.actor_action.side_effect = send
    update = owner.advance_combat(proposal, observation)
    data = update.as_dict()
    assert data['verb'] == 'stop_context' and data['native_reason'] == 'initiation'
    assert data['preceding_replies'][0]['verb'] == 'attach_context'
    assert data['preceding_replies'][0]['closure'] == 'never_bound'
    assert update.terminal_reason is None and not owner.active


@pytest.mark.parametrize('owner_closes', [False, True])
def test_expired_child_history_queries_exact_parent_and_never_reopens(setup, owner_closes):
    owner, session, _, observation, proposal = setup
    clock = fake_clock(session)

    def send(g, v, c, **kw):
        result = reply(c, v)
        if v in (Verb.ATTACH_CONTEXT, Verb.STOP_CONTEXT):
            return expired(result)
        if v is Verb.STOP_OWNER and not owner_closes:
            return expired(result)
        return result

    session.actor_action.side_effect = send
    first = owner.advance_combat(proposal, observation)
    assert first.receipt.outcome is Outcome.HISTORY_EXPIRED
    assert first.receipt.owner_phase is Phase.UNKNOWN
    observation.now_ms = 5000
    update = owner.advance_combat(proposal, observation)
    assert update.receipt.verb is Verb.STOP_OWNER
    assert update.command == owner._stop_owner_command
    assert update.terminal_reason == ('actor_owner_closed' if owner_closes
                                      else 'combat_cleanup_unconfirmed')
    assert owner._obligation.released is owner_closes
    if not owner_closes:
        assert clock[0] == 3.0
    count = session.actor_action.call_count
    owner.advance_combat(replace(proposal, proposal_id=2), observation)
    assert session.actor_action.call_count == count
    assert not any(c.args[1] is Verb.SUBMIT for c in session.actor_action.call_args_list)


def test_prior_child_closure_cannot_settle_new_child_after_deadline(setup):
    owner, session, _, observation, proposal = setup
    clock = fake_clock(session)
    owner.advance_combat(proposal, observation)
    assert owner.finish_context('first_dead')[0]
    prior_receipt = owner._last_context_result[1]
    next_proposal = replace(proposal, proposal_id=2)
    session.actor_action.side_effect = lambda g, v, c, **kw: pending(reply(c, v))
    owner.advance_combat(next_proposal, observation)
    assert owner.context.context_id != prior_receipt.context_id
    assert not owner._last_context_result[0] and owner._cleanup_result_command is None
    session.cleanup.begin(owner._obligation)
    clock[0] = 3.0
    count = session.actor_action.call_count
    observation.now_ms = 5000
    update = owner.advance_combat(next_proposal, observation)
    assert update.terminal_reason == 'combat_cleanup_unconfirmed'
    assert update.receipt is None and update.command is None
    assert session.actor_action.call_count == count

@pytest.mark.parametrize('aggregate_closes', [False, True])
def test_production_runner_finishes_cleanup_before_encounter_timeout(setup, aggregate_closes):
    from types import SimpleNamespace

    from test_pve_controller import (
        AdvancingClock,
        ConstantHealthSource,
        FixturePopulationSource,
        _player,
        _runner,
        _target,
    )

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.pve import PvEController, PvEControllerConfig
    from shadowbane_lab.pve.native_combat import NativeCombatCoordinator

    owner, session, _, _, _ = setup
    clock = AdvancingClock()
    session.cleanup.clock, session.cleanup.sleeper = clock, clock.sleep
    health = ConstantHealthSource(_target('mob'))
    controller = PvEController(PvEControllerConfig(engagement_timeout_ms=120_000))
    population = FixturePopulationSource(health, None, None, controller)
    real_observe = population.observe
    def observe_population():
        frame = real_observe()
        return replace(frame, local_player_object_key=owner.actor_key, characters=tuple(
            replace(character, object_key=setup[4].target_key) for character in frame.characters))
    population.observe = observe_population

    def send(g, v, c, **kw):
        result = reply(c, v)
        if v in (Verb.ATTACH_CONTEXT, Verb.CONTEXT_STATUS):
            return pending(result)
        if v is Verb.STOP_CONTEXT:
            return expired(result) if aggregate_closes else pending(result)
        return result

    session.actor_action.side_effect = send
    runner = _runner(controller=controller, health_reader=health,
        player_vitals_reader=SimpleNamespace(observe=lambda: _player()),
        population_reader=population, dispatcher=NativeCombatCoordinator(owner=owner),
        combat_cleanup=SimpleNamespace(cleanup=owner.cleanup_context),
        stop_signal=EventEmergencyStop(), clock=clock, sleeper=clock.sleep)
    result = runner.run()
    assert result.terminal_reason == ('actor_owner_closed' if aggregate_closes
                                      else 'combat_cleanup_unconfirmed')
    assert clock.value < 9.0
    assert result.kills == 0
    updates = [step.native_combat for step in result.trace if step.native_combat is not None]
    assert updates[0].receipt.verb is Verb.ATTACH_CONTEXT
    assert updates[0].as_dict()['native_reason'] == 'initiation'
    assert updates[-1].terminal_reason == result.terminal_reason
    assert not any(c.args[1] is Verb.SUBMIT for c in session.actor_action.call_args_list)
    assert owner._obligation.released is aggregate_closes
    assert (controller.pending_cleanup is None) is aggregate_closes
