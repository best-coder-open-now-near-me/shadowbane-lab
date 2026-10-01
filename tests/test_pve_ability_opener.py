"""Generic ability openers preserve recipient, identity and native acknowledgement."""

from dataclasses import replace

import pytest
from test_native_combat_coordinator import answer
from test_native_combat_coordinator import setup as coordinator_fixture
from test_pve_native_proposals import ack, character, observe

from shadowbane_lab.client_extension.combat_wire_v2 import Action, Verb
from shadowbane_lab.pve.model import (
    PvEAbility,
    PvEAbilityRecipient,
    PvECombatDisposition,
    PvECombatKind,
    PvEControllerConfig,
    PvEIntent,
    PvEPhase,
)
from shadowbane_lab.pve.target_authority import PvEController


@pytest.fixture
def coordinator(monkeypatch):
    return coordinator_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("power_id", [563795161, 12345])
@pytest.mark.parametrize(
    "recipient,kind",
    [
        (PvEAbilityRecipient.ACTOR, PvECombatKind.SELF_POWER),
        (PvEAbilityRecipient.ENGAGEMENT_TARGET, PvECombatKind.CAST),
    ],
)
def test_configured_ability_ack_then_attack_has_no_default_delay(power_id, recipient, kind):
    controller = PvEController(PvEControllerConfig(opening_ability=PvEAbility(power_id, recipient)))
    opening = controller.step(observe()).combat_proposal
    assert opening.kind is kind and opening.power_id == power_id
    assert opening.target_key == character().object_key
    assert not controller._last_power_at
    ack(controller, opening)
    assert controller._last_power_at == {power_id: 0}
    followup = controller.step(observe(1)).combat_proposal
    assert followup.kind is PvECombatKind.ATTACK and followup.power_id == 0
    assert (followup.target_token, followup.target_key) == (
        opening.target_token,
        opening.target_key,
    )


def test_self_power_uncertainty_blocks_attack_and_keeps_exact_pending_proposal():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    opening = controller.step(observe()).combat_proposal
    ack(controller, opening, PvECombatDisposition.UNCERTAIN, entered=None)
    assert controller.step(observe(1000)).combat_proposal is None
    assert controller.pending_combat_proposal is opening
    assert not controller._last_power_at and controller.phase is PvEPhase.OPENING


def test_deferred_self_power_retries_same_recipient_and_id_without_consuming_opener():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    opening = controller.step(observe()).combat_proposal
    ack(controller, opening, PvECombatDisposition.DEFERRED, entered=False)
    assert controller.step(observe()).combat_proposal is None
    assert controller.step(observe(1, busy=True)).combat_proposal is None
    retry = controller.step(observe(2)).combat_proposal
    assert (retry.kind, retry.power_id) == (PvECombatKind.SELF_POWER, 123)
    assert retry.proposal_id != opening.proposal_id
    assert not controller._last_power_at
    ack(controller, retry, now=2)
    assert controller.step(observe(3, busy=True)).combat_proposal is None
    assert controller.step(observe(4)).combat_proposal.kind is PvECombatKind.ATTACK


def test_target_replacement_after_opener_requests_cleanup_not_attack_or_rearm():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    opening = controller.step(observe()).combat_proposal
    ack(controller, opening)
    decision = controller.step(observe(1, characters=(character(uuid=2),)))
    assert decision.combat_proposal is None
    assert decision.cleanup_request is None  # bounded disappearance grace is not death
    decision = controller.step(observe(1000, characters=(character(uuid=2),)))
    assert decision.cleanup_request.object_key == opening.target_key


def test_rejected_opener_retains_original_cleanup_obligation():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    opening = controller.step(observe()).combat_proposal
    ack(controller, opening, PvECombatDisposition.REJECTED, entered=False)
    assert controller.pending_cleanup.object_key == opening.target_key
    assert controller.step(observe(1)).combat_proposal is None


@pytest.mark.parametrize("value", [0, -1, 2**32, True])
def test_invalid_ability_id_rejected(value):
    with pytest.raises(ValueError):
        PvEAbility(value, PvEAbilityRecipient.ACTOR)


def test_legacy_and_generic_config_cannot_silently_override_each_other():
    with pytest.raises(ValueError, match="not both"):
        PvEControllerConfig(
            opening_intent=PvEIntent.CAST_SHADOW_TOUCH,
            opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR),
        )
    with pytest.raises(ValueError, match="recipient"):
        PvEAbility(123, "actor")
    with pytest.raises(ValueError, match="target the engagement"):
        PvEControllerConfig(
            interrupt_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR),
            maximum_interrupts_per_target=1,
        )


def test_self_power_then_attack_reuses_native_engagement_and_immutable_timeout(coordinator):
    from types import SimpleNamespace

    combat, session, tickets, observation, proposal = coordinator
    opening = replace(proposal, kind=PvECombatKind.SELF_POWER, power_id=123)
    session.combat.side_effect = TimeoutError()
    assert (
        combat.advance(opening, observation).acknowledgement.disposition
        is PvECombatDisposition.UNCERTAIN
    )
    original = session.combat.call_args.args[2]
    assert original.action is Action.SELF_POWER and original.power_id == 123
    assert original.binding.local_key != original.binding.target_key
    session.combat.side_effect = lambda g, v, c: SimpleNamespace(
        receipt=answer(c, v), native_detail=None
    )
    update = combat.advance(opening, observation)
    assert update.acknowledgement.disposition is PvECombatDisposition.QUEUED
    assert session.combat.call_args.args[1] is Verb.ACTION_STATUS
    assert session.combat.call_args.args[2] is original
    attack = replace(opening, proposal_id=2, kind=PvECombatKind.ATTACK, power_id=0)
    combat.advance(attack, observation)
    following = session.combat.call_args.args[2]
    assert (
        following.binding == original.binding and following.request.value > original.request.value
    )
    assert following.action is Action.ATTACK and len(tickets) == 1
    session.require_combat_available.assert_any_call(combat.grant, self_power=True)
    session.pause.assert_not_called()


def test_missing_self_capability_rejects_before_new_ticket(coordinator):
    combat, session, tickets, observation, proposal = coordinator
    session.require_combat_available.side_effect = RuntimeError("self power unavailable")
    with pytest.raises(RuntimeError, match="unavailable"):
        combat.advance(replace(proposal, kind=PvECombatKind.SELF_POWER), observation)
    assert not tickets
    session.combat.assert_not_called()


def test_public_runner_enqueues_self_power_then_attack_under_one_engagement(coordinator):
    from types import SimpleNamespace

    from shadowbane_lab.client_extension.combat_wire_v2 import ClosureProof, Outcome, Phase
    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.client_observation import NativeGroupObservation
    from shadowbane_lab.pve import PvERunner

    combat, session, tickets, old_observation, template = coordinator
    stop = EventEmergencyStop()
    clock = SimpleNamespace(now=0.0)
    target = replace(character(), object_key=template.target_key, token=template.target_token)

    def current():
        value = observe(round(clock.now * 1000), characters=(target,))
        return replace(
            value,
            population=replace(
                value.population,
                local_player_object_key=old_observation.population.local_player_object_key,
            ),
        )

    def source(field):
        return SimpleNamespace(process_id=1234, observe=lambda: getattr(current(), field))

    def response(grant, verb, command):
        if verb is Verb.STOP_ENGAGEMENT:
            receipt = answer(
                command,
                verb,
                outcome=Outcome.ENGAGEMENT_CLOSED,
                phase=Phase.CLOSED,
                closure=ClosureProof.NATIVE_STOPPED,
                queued=False,
            )
        else:
            receipt = answer(command, verb)
            if command.action is Action.ATTACK:
                stop.trip()
        return SimpleNamespace(receipt=receipt, native_detail=None)

    session.combat.side_effect = response
    trace = []

    def sleep(seconds):
        clock.now += seconds
        assert clock.now < 2, "opener failed to reach its attack"

    runner = PvERunner(
        controller=PvEController(
            PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
        ),
        health_reader=source("target"),
        player_vitals_reader=source("player"),
        player_position_reader=source("player_position"),
        target_position_reader=source("target_position"),
        population_reader=source("population"),
        group_reader=SimpleNamespace(
            process_id=1234, observe=lambda: NativeGroupObservation(False, False, ())
        ),
        party_group_id="party",
        player_action_reader=SimpleNamespace(
            process_id=1234, observe_player=lambda: current().player_action
        ),
        dispatcher=combat,
        combat_cleanup=combat,
        stop_signal=stop,
        clock=lambda: clock.now,
        sleeper=sleep,
        trace_sink=trace.append,
        poll_interval_ms=100,
    )
    result = runner.run()
    calls = session.combat.call_args_list
    assert [(c.args[1], c.args[2].action) for c in calls] == [
        (Verb.SUBMIT, Action.SELF_POWER),
        (Verb.SUBMIT, Action.ATTACK),
        (Verb.STOP_ENGAGEMENT, Action.NONE),
    ]
    assert len({c.args[2].binding for c in calls}) == len(tickets) == 1
    assert result.terminal_reason == "emergency_stop" and not combat.active
    assert [s.decision.now_ms for s in trace if s.native_combat is not None] == [0, 100]
    assert trace[0].decision.intent is None  # generic native ability needs no legacy descriptor
    session.pause.assert_not_called()
