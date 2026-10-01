"""Generic ability openers preserve recipient, identity and native acknowledgement."""

from dataclasses import replace

import pytest
from test_native_combat_coordinator import answer
from test_native_combat_coordinator import setup as coordinator_fixture
from test_pve_native_proposals import ack, character, observe

from shadowbane_lab.client_extension.actor_action_wire import Action, Verb
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
def coordinator():
    return coordinator_fixture.__wrapped__()


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
    followup = controller.step(observe(3, busy=True)).combat_proposal
    assert followup.kind is PvECombatKind.ATTACK
    ack(controller, followup, PvECombatDisposition.DEFERRED, now=3, entered=False)
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

    def uncertain(g, v, c, **kw):
        if v is Verb.SUBMIT:
            raise TimeoutError()
        return SimpleNamespace(receipt=answer(c, v), native_detail=None)

    session.actor_action.side_effect = uncertain
    assert (
        combat.advance(opening, observation).acknowledgement.disposition
        is PvECombatDisposition.UNCERTAIN
    )
    original = session.actor_action.call_args.args[2]
    assert original.action is Action.SELF_POWER and original.power_id == 123
    assert combat.owner.parent.actor_key != combat.owner.context.target_key
    session.actor_action.side_effect = lambda g, v, c, **kw: SimpleNamespace(
        receipt=answer(c, v), native_detail=None
    )
    update = combat.advance(opening, observation)
    assert update.acknowledgement.disposition is PvECombatDisposition.QUEUED
    assert session.actor_action.call_args.args[1] is Verb.ACTION_STATUS
    assert session.actor_action.call_args.args[2] is original
    attack = replace(opening, proposal_id=2, kind=PvECombatKind.ATTACK, power_id=0)
    combat.advance(attack, observation)
    following = session.actor_action.call_args.args[2]
    assert (
        following.parent_id == original.parent_id
        and following.context_id == original.context_id
        and following.request.value > original.request.value
    )
    assert following.action is Action.ATTACK and len(tickets) == 2
    session.require_actor_actions.assert_any_call(combat.owner.grant)
    session.pause.assert_not_called()


def test_missing_actor_capability_rejects_before_new_owner_or_context(coordinator):
    from shadowbane_lab.pve.native_actor import NativeActorCoordinator

    combat, session, tickets, _, _ = coordinator
    session.require_actor_actions.side_effect = RuntimeError("actor actions unavailable")
    count = len(tickets)
    with pytest.raises(RuntimeError, match="unavailable"):
        NativeActorCoordinator(
            session=session,
            grant=combat.owner.grant,
            population=combat.owner.population,
            character_session=combat.owner.character_session,
            store=combat.owner.store,
            ticket_factory=combat.owner._ticket_factory,
        )
    assert len(tickets) == count
    session.actor_action.assert_not_called()


@pytest.mark.parametrize("reuse_blocked", [False, True])
def test_public_runner_opener_then_attack_under_one_engagement(coordinator, reuse_blocked):
    from types import SimpleNamespace

    from shadowbane_lab.client_extension.actor_action_wire import Closure as ClosureProof
    from shadowbane_lab.client_extension.actor_action_wire import Outcome, Phase
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

    def response(grant, verb, command, **kwargs):
        if verb is Verb.STOP_CONTEXT:
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
            if reuse_blocked and command.action is Action.SELF_POWER:
                from test_power_readiness import blocked

                receipt = blocked(command, verb)
            if command.action is Action.ATTACK:
                stop.trip()
        return SimpleNamespace(receipt=receipt, native_detail=None)

    session.actor_action.side_effect = response
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
    calls = [
        c
        for c in session.actor_action.call_args_list
        if c.args[1] not in (Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT)
    ]
    assert [(c.args[1], c.args[2].action) for c in calls] == [
        (Verb.SUBMIT, Action.SELF_POWER),
        (Verb.SUBMIT, Action.ATTACK),
        (Verb.STOP_CONTEXT, Action.NONE),
    ]
    assert len({(c.args[2].parent_id, c.args[2].context_id) for c in calls}) == 1
    assert len(tickets) == 2
    assert result.terminal_reason == "emergency_stop" and not combat.active
    assert [s.decision.now_ms for s in trace if s.native_combat is not None] == [0, 100]
    assert trace[0].decision.intent is None  # generic native ability needs no legacy descriptor
    session.pause.assert_not_called()
    if reuse_blocked:
        assert trace[0].native_combat.acknowledgement.disposition is PvECombatDisposition.NOT_READY
        assert trace[0].as_dict()["native_combat"]["not_ready_reason"] == "power_reuse"
        assert trace[1].as_dict()["opening_skill_skipped"] is True
        assert trace[1].as_dict()["opening_skill_skip_reason"] == "power_reuse"
        assert not runner._controller._last_power_at


@pytest.mark.parametrize("ids", [(123,), (123, 123), (123, 999)])
def test_owned_queued_self_followup_is_only_a_native_admission_proposal(ids):
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    opening = controller.step(observe()).combat_proposal
    ack(controller, opening)
    pending = observe(1, busy=True)
    pending = replace(pending, player_action=replace(pending.player_action, power_protocol_ids=ids))
    followup = controller.step(pending).combat_proposal
    assert followup.kind is PvECombatKind.ATTACK
    assert followup.target_key == opening.target_key
    # Unqualified definitions/protocol mixtures are decided natively, not bypassed.
    ack(controller, followup, PvECombatDisposition.DEFERRED, now=1, entered=False)
    retry = controller.step(replace(pending, now_ms=2)).combat_proposal
    assert retry.kind is PvECombatKind.ATTACK
    ack(controller, retry, PvECombatDisposition.UNCERTAIN, now=2, entered=None)
    assert controller.step(replace(pending, now_ms=3)).combat_proposal is None
    assert controller.pending_combat_proposal is retry


def test_owned_followup_never_reconstructs_missing_initiation_observation():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    ack(controller, controller.step(observe()).combat_proposal)
    unknown = observe(1)
    unknown = replace(
        unknown,
        player_action=replace(
            unknown.player_action, initiation_state=None, power_protocol_ids=None
        ),
    )
    assert controller.step(unknown).combat_proposal is None
    assert controller.pending_cleanup is None


@pytest.mark.parametrize("terminal", [False, True])
def test_followup_provenance_is_revoked_on_cleanup_or_terminal_stop(terminal):
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    ack(controller, controller.step(observe()).combat_proposal)
    assert controller._queued_self_followup is not None
    if terminal:
        controller.stop("owner_revoked", now_ms=1)
    else:
        controller.request_final_cleanup()
    assert controller._queued_self_followup is None


def test_direct_cast_queue_does_not_authorize_busy_followup_attack():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ENGAGEMENT_TARGET))
    )
    ack(controller, controller.step(observe()).combat_proposal)
    assert controller.step(observe(1, busy=True)).combat_proposal is None
    assert controller._queued_self_followup is None


def test_queued_attack_consumes_self_followup_permission():
    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    ack(controller, controller.step(observe()).combat_proposal)
    attack = controller.step(observe(1, busy=True)).combat_proposal
    ack(controller, attack, now=1)
    assert controller._queued_self_followup is None
    assert controller.step(observe(2, busy=True)).combat_proposal is None
