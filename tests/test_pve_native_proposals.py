"""Native policy proposals use owned objects and account only correlated results."""
from dataclasses import replace

import pytest

from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionObservation,
    NativeTargetActionPhase,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import NativeCharacterKind
from shadowbane_lab.protocol import Relation
from shadowbane_lab.pve.authority import (
    PvETargetAuthorityEvidence,
    PvETargetCharacterKind,
    StaticPvETargetAuthorityEvaluator,
)
from shadowbane_lab.pve.controller import PvEController
from shadowbane_lab.pve.model import (
    PvECombatAcknowledgement,
    PvECombatCleanupResult,
    PvEControllerConfig,
    PvEIntent,
    PvEObservation,
    PvEPhase,
    PvETrackedTargetAction,
)
from shadowbane_lab.pve.model import (
    PvECombatDisposition as Disposition,
)
from shadowbane_lab.pve.model import (
    PvECombatKind as Kind,
)
from shadowbane_lab.pve.target_authority import PvEController as GuardedController


def character(token="owned", uuid=1, distance=5):
    return NativeCharacterObservation(
        token=token, object_key=NativeObjectKey(37, uuid), character_kind=NativeCharacterKind.NPC,
        current_health=100, maximum_health=100, lt=distance, lg=0, altitude=0,
        merchant=False, shopkeeper=False, banker=False, trainer=False, minion=False,
    )


def observe(now=0, *, characters=None, selected=None, active=None, busy=False, interrupt=None):
    characters = (character(),) if characters is None else characters
    chosen = next((item for item in characters if item.token == selected), None)
    return PvEObservation(
        now_ms=now,
        target=(NativeTargetHealthObservation(False) if chosen is None else
                NativeTargetHealthObservation(True, chosen.current_health,
                                              chosen.maximum_health, chosen.token)),
        player=NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100),
        player_position=NativePlayerPositionObservation(0, 0, 0),
        target_position=(NativeTargetPositionObservation(False) if chosen is None else
                         NativeTargetPositionObservation(True, chosen.lt, chosen.lg,
                                                         chosen.altitude, chosen.token)),
        player_action=NativePlayerActionObservation(
            phase=NativeTargetActionPhase.WINDUP if busy else NativeTargetActionPhase.IDLE,
            targeting_selected=active is not None and active == selected,
            selected_target_token=selected, action_target_token=active,
            motion_id=1, action_pending=busy, impact_frame=None,
            action_sequence=0, motion_sequence=0, mode=2 if busy else 1,
            action_state=6 if busy else 1,
        ),
        population=NativeCharacterPopulationObservation(
            characters=characters, selected_target_token=selected,
            player_action_target_token=active, scan_generation=now + 1, rejected_candidates=0,
            local_player_object_key=NativeObjectKey(53, 99),
        ),
        tracked_target_action=interrupt,
    )


def ack(controller, proposal, disposition=Disposition.QUEUED, now=0, entered=True):
    result = PvECombatAcknowledgement(disposition, entered, True)
    controller.acknowledge_combat(proposal, result, now_ms=now)
    return result


def test_population_acquires_exact_object_without_selection_or_legacy_flag():
    controller = PvEController(PvEControllerConfig())
    near, far = character(), character("selected", 2, 20)
    decision = controller.step(observe(characters=(far, near), selected="selected"))
    assert decision.combat_proposal.kind is Kind.ATTACK
    assert decision.combat_proposal.target_key == near.object_key
    assert decision.combat_proposal.target_token == near.token
    assert controller.pending_combat_proposal == decision.combat_proposal
    assert PvEIntent.ACQUIRE_NEXT_MOB not in controller.required_intents


def test_missing_population_cannot_fall_back_to_selected_input():
    controller = PvEController(PvEControllerConfig())
    decision = controller.step(replace(observe(), population=None))
    assert decision.terminal_reason == "native_population_unavailable"
    assert decision.combat_proposal is None


def test_busy_unknown_action_waits_without_bind_attack_or_cleanup():
    controller = PvEController(PvEControllerConfig())
    waiting = controller.step(observe(busy=True))
    assert waiting.phase is PvEPhase.OBSERVING_ACTION
    assert waiting.combat_proposal is None and waiting.cleanup_request is None
    controller.step(observe(100))
    assert controller.step(observe(101)).combat_proposal.kind is Kind.ATTACK


def test_adoption_binds_existing_object_without_selection_or_attack():
    controller = PvEController(PvEControllerConfig())
    first = controller.step(observe(active="owned", busy=True))
    assert first.combat_proposal.kind is Kind.BIND
    assert first.combat_proposal.adopted_existing_action
    assert first.intent is None and first.cleanup_request is None
    ack(controller, first.combat_proposal, Disposition.BOUND, entered=None)
    again = controller.step(observe(100, active="owned", busy=True))
    assert again.combat_proposal is None and again.cleanup_request is None


def test_proposal_does_not_consume_attack_time_and_pending_blocks_new_action():
    controller = PvEController(PvEControllerConfig())
    first = controller.step(observe())
    # Past the quiet timeout, an unacknowledged proposal has no fictitious attack.
    later = controller.step(observe(3000))
    assert later.combat_proposal is None and later.cleanup_request is None
    assert controller.pending_combat_proposal == first.combat_proposal
    ack(controller, first.combat_proposal, now=3000)
    assert controller.step(observe(3100)).cleanup_request is None
    assert controller.step(observe(4600)).cleanup_request is not None


def test_ack_identity_and_kind_cannot_be_rebound():
    controller = PvEController(PvEControllerConfig())
    proposal = controller.step(observe()).combat_proposal
    with pytest.raises(ValueError):
        ack(controller, replace(proposal, target_key=NativeObjectKey(37, 123)))
    with pytest.raises(ValueError):
        ack(controller, proposal, Disposition.BOUND, entered=None)
    assert controller.pending_combat_proposal == proposal


def test_uncertain_history_stays_pinned_until_exact_status_and_duplicate_ack_is_idempotent():
    controller = PvEController(PvEControllerConfig())
    proposal = controller.step(observe()).combat_proposal
    ack(controller, proposal, Disposition.UNCERTAIN, entered=None)
    assert controller.step(observe(100)).combat_proposal is None
    assert controller.pending_combat_proposal == proposal
    result = ack(controller, proposal, now=100)
    controller.acknowledge_combat(proposal, result, now_ms=100)
    assert controller.pending_combat_proposal is None


@pytest.mark.parametrize("entered", [True, False, None])
def test_rejection_preserves_owned_object_until_cleanup_proof(entered):
    controller = PvEController(PvEControllerConfig())
    proposal = controller.step(observe()).combat_proposal
    ack(controller, proposal, Disposition.REJECTED, entered=entered)
    waiting = controller.step(observe(100))
    assert waiting.phase is PvEPhase.DISENGAGING
    assert waiting.cleanup_request.object_key == proposal.target_key
    assert waiting.combat_proposal is None
    controller.acknowledge_cleanup(
        PvECombatCleanupResult(waiting.cleanup_request, True, "exact-stop-receipt")
    )
    assert controller.pending_combat_proposal is None
    assert controller.step(observe(101)).phase is PvEPhase.SEEKING


def test_deferred_opener_remains_scheduled_without_consuming_delay_or_cooldown():
    controller = PvEController(PvEControllerConfig(opening_intent=PvEIntent.CAST_SHADOW_TOUCH))
    first = controller.step(observe()).combat_proposal
    assert first.kind is Kind.CAST and first.power_id == 428918601
    ack(controller, first, Disposition.DEFERRED, entered=False)
    assert controller.step(observe()).combat_proposal is None
    assert controller.step(observe(500, busy=True)).combat_proposal is None
    second = controller.step(observe(1000)).combat_proposal
    assert second.kind is Kind.CAST and second.proposal_id != first.proposal_id
    ack(controller, second, now=1000)
    assert controller.step(observe(1100)).combat_proposal.kind is Kind.ATTACK


def test_key_reuse_while_pending_requires_cleanup_of_original_object():
    controller = PvEController(PvEControllerConfig())
    original = controller.step(observe()).combat_proposal
    decision = controller.step(observe(100, characters=(character(uuid=2),)))
    assert decision.cleanup_request.object_key == original.target_key
    assert decision.combat_proposal is None


def test_unacknowledged_adoption_retains_cleanup_obligation():
    controller = PvEController(PvEControllerConfig())
    original = controller.step(observe(active="owned", busy=True)).combat_proposal
    ack(controller, original, Disposition.REJECTED, entered=False)
    assert controller.request_final_cleanup().object_key == original.target_key


def test_interrupt_budget_is_charged_only_once_on_correlated_queue():
    controller = PvEController(PvEControllerConfig(
        interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH, maximum_interrupts_per_target=1,
        interrupt_cooldown_ms=2000,
    ))
    first = controller.step(observe()).combat_proposal
    ack(controller, first)
    action = NativeTargetActionObservation(
        target_present=True, phase=NativeTargetActionPhase.WINDUP, target_token="owned",
        targeting_player=True, motion_id=106, action_pending=False, impact_frame=None,
        action_sequence=8,
    )
    bound = PvETrackedTargetAction("owned", character().object_key, action)
    interrupt = controller.step(observe(100, interrupt=bound)).combat_proposal
    assert interrupt.kind is Kind.CAST and interrupt.interrupt_sequence == 8
    ack(controller, interrupt, Disposition.DEFERRED, now=100, entered=False)
    retry = controller.step(observe(200, interrupt=bound)).combat_proposal
    assert retry.kind is Kind.CAST
    ack(controller, retry, now=200)
    later = replace(bound, action=replace(action, action_sequence=9))
    assert controller.step(observe(300, interrupt=later)).combat_proposal is None


def test_guarded_ranking_evaluates_candidate_object_not_selected_snapshot():
    eligible, neutral = character(), character("neutral", 2, 2)
    evidence = tuple(PvETargetAuthorityEvidence(
        target_token=item.token, source_revision=1, target_object_key=item.object_key,
        local_player_object_key=NativeObjectKey(53, 99),
        character_kind=PvETargetCharacterKind.NPC,
        relation=Relation.ENEMY if item is eligible else Relation.NEUTRAL,
        same_party=False, friendly_owned=False, attackable=True, evidence_sources=("native",),
    ) for item in (eligible, neutral))
    controller = GuardedController(
        PvEControllerConfig(),
        target_authority_evaluator=StaticPvETargetAuthorityEvaluator(evidence),
        require_verified_target_authority=True,
    )
    decision = controller.step(observe(characters=(neutral, eligible), selected="neutral"))
    assert decision.combat_proposal.target_token == "owned"
    assert decision.target_authority.target_object_key == eligible.object_key
    assert controller.target_rejections[0].target_token == "neutral"


def test_deferred_bind_preserves_unknown_entry_and_existing_cleanup_obligation():
    controller = PvEController(PvEControllerConfig())
    first = controller.step(observe(active="owned", busy=True)).combat_proposal
    ack(controller, first, Disposition.DEFERRED, entered=None)
    retry = controller.step(observe(100, active="owned", busy=True)).combat_proposal
    assert retry.kind is Kind.BIND and retry.adopted_existing_action
    assert retry.proposal_id != first.proposal_id
    assert controller.request_final_cleanup().object_key == first.target_key


def test_deferred_action_cannot_claim_unknown_native_entry():
    controller = PvEController(PvEControllerConfig())
    first = controller.step(observe()).combat_proposal
    with pytest.raises(ValueError, match="prove no entry"):
        ack(controller, first, Disposition.DEFERRED, entered=None)
    assert controller.pending_combat_proposal == first


def test_historical_queued_action_without_ownership_requires_cleanup_transition():
    controller = PvEController(PvEControllerConfig())
    first = controller.step(observe()).combat_proposal
    controller.acknowledge_combat(first, PvECombatAcknowledgement(
        Disposition.QUEUED, True, False), now_ms=0)
    decision = controller.step(observe(100))
    assert decision.cleanup_request.reason == "native_engagement_closed"
    assert decision.combat_proposal is None


def test_queue_ack_during_stop_cannot_reopen_engagement():
    controller = PvEController(PvEControllerConfig())
    first = controller.step(observe()).combat_proposal
    stopped = controller.stop("operator_stop", now_ms=100)
    ack(controller, first, now=100)
    assert controller.phase is PvEPhase.STOPPED
    assert controller.pending_cleanup == stopped.cleanup_request


def test_deferred_interrupt_rechecks_current_action_opportunity():
    controller = PvEController(PvEControllerConfig(
        interrupt_intent=PvEIntent.CAST_SHADOW_TOUCH, maximum_interrupts_per_target=1,
    ))
    ack(controller, controller.step(observe()).combat_proposal)
    action = NativeTargetActionObservation(
        target_present=True, phase=NativeTargetActionPhase.WINDUP, target_token="owned",
        targeting_player=True, motion_id=106, action_pending=False, impact_frame=None,
        action_sequence=8,
    )
    bound = PvETrackedTargetAction("owned", character().object_key, action)
    interrupted = controller.step(observe(100, interrupt=bound)).combat_proposal
    ack(controller, interrupted, Disposition.DEFERRED, now=100, entered=False)
    assert controller.step(observe(200)).combat_proposal is None
    fresh = replace(bound, action=replace(action, action_sequence=9))
    assert controller.step(observe(300, interrupt=fresh)).combat_proposal.interrupt_sequence == 9


def test_trace_preserves_bind_and_later_pending_receipt_without_synthetic_intent():
    from shadowbane_lab.pve.model import PvERunTraceStep
    from shadowbane_lab.pve.native_combat import NativeCombatUpdate

    controller = PvEController(PvEControllerConfig())
    initial = controller.step(observe(active="owned", busy=True))
    trace = PvERunTraceStep(initial, False, None, None, input_accepted=True)
    assert trace.as_dict()["combat_proposal"]["kind"] == "bind"
    pending = controller.step(observe(100, active="owned", busy=True))
    update = NativeCombatUpdate(PvECombatAcknowledgement(Disposition.UNCERTAIN, None, True))
    trace = PvERunTraceStep(pending, False, None, None, native_combat=update, input_accepted=False)
    assert trace.as_dict()["native_combat"]["native_entered"] is None
    assert trace.as_dict()["combat_proposal"] is None
    with pytest.raises(ValueError, match="outcome requires"):
        PvERunTraceStep(pending, False, None, None, input_accepted=True)
