"""Initial buff capture unavailability must not become a PvE startup prerequisite."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_native_actor_coordinator import setup as actor_fixture
from test_native_actor_preparation import configure

from shadowbane_lab.client_extension import actor_publication as publication
from shadowbane_lab.client_extension.actor_action_wire import Action, Outcome, Verb

setup = actor_fixture


def test_initial_unavailable_retries_only_same_registration_then_reads_history(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, send = configure(owner, session, monkeypatch)
    unavailable = [True]

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb is Verb.REGISTER_SELECTORS and unavailable[0]:
            result.receipt = replace(result.receipt, outcome=Outcome.UNAVAILABLE)
        return result

    session.actor_action.side_effect = response
    for _ in range(4):
        assert owner.preparation_step() is None
        assert not owner._registered
    owner.publication_reader.read.assert_not_called()
    registrations = list(session.actor_action.call_args_list)
    assert all(call.args == (None, Verb.REGISTER_SELECTORS, owner._register_command)
               for call in registrations)
    assert owner._preparation_policy.pending_proposal is None
    # Native remote application history can outlive an earlier host/Grant. The
    # first successful capture must import it before deciding what to submit.
    owner.publication_reader.read.return_value = replace(pub, applications=(
        publication.Application(owner.manifest.group_digest(0), b'q'*32, 1, 0,
                                      1, 1, True, True),))
    unavailable[0] = False
    update = owner.preparation_step()
    assert update.command.action is Action.SELF_POWER
    assert update.command.power_id == 429545819
    assert owner._registered
    calls = session.actor_action.call_args_list
    assert sum(call.args[1] is Verb.REGISTER_SELECTORS for call in calls) == 5
    assert sum(call.args[1] is Verb.OPEN_OWNER for call in calls) == 1
    assert sum(call.args[1] is Verb.SUBMIT for call in calls) == 1
    assert not any(call.args[2].action is Action.USE_ITEM for call in calls)


@pytest.mark.parametrize('outcome', [Outcome.INVALID, Outcome.DEFERRED])
def test_registration_identity_or_pending_manifest_refusal_is_not_capture_unknown(
    setup, monkeypatch, outcome
):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        result.receipt = replace(result.receipt, outcome=outcome)
        return result

    session.actor_action.side_effect = response
    with pytest.raises(publication.PublicationError, match='registration unconfirmed'):
        owner.preparation_step()
    owner.publication_reader.read.assert_not_called()
    assert not owner._registered


def test_unavailable_registration_still_requires_exact_reply(setup, monkeypatch):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        result.receipt = replace(result.receipt, outcome=Outcome.UNAVAILABLE,
                                 command_digest=b'x'*32)
        return result

    session.actor_action.side_effect = response
    with pytest.raises(ValueError):
        owner.preparation_step()
    owner.publication_reader.read.assert_not_called()
    assert not owner._registered


def test_public_runner_can_finish_npc_while_initial_buff_capture_unavailable(setup, monkeypatch):
    from test_pve_native_proposals import character, observe

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.client_observation import NativeGroupObservation
    from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvERunner
    from shadowbane_lab.pve.native_combat import NativeCombatCoordinator

    owner, session, _, original, proposal = setup
    _, send = configure(owner, session, monkeypatch)
    combat = NativeCombatCoordinator(owner=owner)
    clock, attacked = [0.0], [False]
    target = replace(character(), object_key=proposal.target_key, token=proposal.target_token)

    def current():
        value = observe(round(clock[0]*1000), characters=(
            replace(target, current_health=0) if attacked[0] else target,))
        return replace(value, population=replace(value.population,
            local_player_object_key=original.population.local_player_object_key))

    def source(field):
        return SimpleNamespace(process_id=owner.parent.client_pid,
                               observe=lambda: getattr(current(), field))

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb is Verb.REGISTER_SELECTORS:
            result.receipt = replace(result.receipt, outcome=Outcome.UNAVAILABLE)
        if verb is Verb.SUBMIT and command.action is Action.ATTACK:
            attacked[0] = True
        return result

    session.actor_action.side_effect = response
    def sleep(seconds):
        clock[0] += seconds
        assert clock[0] < 3, 'unavailable buff capture prevented NPC progress'

    runner = PvERunner(controller=PvEController(PvEControllerConfig(maximum_kills=1)),
        health_reader=source('target'), player_vitals_reader=source('player'),
        player_position_reader=source('player_position'),
        target_position_reader=source('target_position'), population_reader=source('population'),
        player_action_reader=SimpleNamespace(process_id=owner.parent.client_pid,
            observe_player=lambda: current().player_action),
        group_reader=SimpleNamespace(process_id=owner.parent.client_pid,
            observe=lambda: NativeGroupObservation(False, False, ())),
        party_group_id='party', dispatcher=combat, combat_cleanup=combat,
        actor_preparation=owner, stop_signal=EventEmergencyStop(),
        clock=lambda: clock[0], sleeper=sleep, poll_interval_ms=100)
    result = runner.run()
    assert result.kills == 1 and not combat.active
    assert result.terminal_reason == 'kill_limit_reached'
    calls = session.actor_action.call_args_list
    submits = [call.args[2] for call in calls if call.args[1] is Verb.SUBMIT]
    assert len(submits) == 1 and submits[0].action is Action.ATTACK
    owner.publication_reader.read.assert_not_called()
    assert not owner._registered and owner._preparation_policy.pending_proposal is None
    assert any(step.combat_cleanup is not None and step.combat_cleanup.confirmed
               for step in result.trace)
    assert owner.finish('test_complete')[0]
