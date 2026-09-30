"""Native object tracking and exact-owner cleanup through production boundaries."""
from dataclasses import replace

import pytest
from test_combat_session import owner as owner
from test_pve_controller import (
    AdvancingClock,
    ConfirmedCleanup,
    RecordingPvEDispatcher,
    SequenceHealthSource,
    SequencePlayerVitalsSource,
    _absent,
    _character,
    _event,
    _observation,
    _player,
    _player_action,
    _population,
    _runner,
    _target,
)

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension.movement_session import NativeMovementError
from shadowbane_lab.client_extension.movement_wire import Outcome, Verb
from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import NativeCombatEventKind, NativeTargetActionPhase
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvEIntent, PvEPhase
from shadowbane_lab.pve.combat_cleanup import NativePvECombatCleanup
from shadowbane_lab.pve.model import PvECombatCleanupRequest, PvECombatCleanupResult


def request(sequence=0):
    return PvECombatCleanupRequest(sequence, "mob", NativeObjectKey(200, 53), "test_cleanup")


def engage(**config):
    controller = PvEController(PvEControllerConfig(**config))
    controller.step(_observation(0, _absent()))
    decision = controller.step(_observation(100, _target("mob")))
    assert decision.intent is not None
    return controller


@pytest.mark.parametrize("selected", [None, "other"])
def test_retained_object_progress_and_death_ignore_ui_selection(selected):
    controller = engage(maximum_kills=1, stalled_progress_ms=100)
    selected_health = _absent() if selected is None else _target(selected)
    others = () if selected is None else (_character(selected, lt=140),)
    tracked = _character("mob", lt=103, health=7)
    frame = _observation(200, selected_health,
        population=_population(selected, tracked, *others))
    progress = controller.step(frame)
    assert progress.phase is PvEPhase.ENGAGED and progress.intent is None
    assert progress.tracked_target.character.current_health == 7
    assert progress.cleanup_request is None
    dead = replace(tracked, current_health=0)
    killed = controller.step(replace(frame, now_ms=300,
        population=_population(selected, dead, *others)))
    assert killed.kills == 1 and killed.phase is PvEPhase.COMPLETE
    assert killed.cleanup_request.target_token == "mob"


def test_same_pointer_replacement_key_and_zero_health_are_not_a_kill():
    controller = engage(selection_loss_grace_ms=10)
    replacement = replace(_character("mob", lt=103, health=0),
                          object_key=NativeObjectKey(999, 53))
    frame = _observation(200, _target("mob", current=0),
                         population=_population("mob", replacement))
    assert controller.step(frame).kills == 0
    decision = controller.step(replace(frame, now_ms=210))
    assert decision.phase is PvEPhase.DISENGAGING
    assert decision.kills == 0 and decision.intent is None
    assert not decision.tracked_target.available
    assert decision.cleanup_request.object_key != replacement.object_key


def test_delayed_text_kills_hits_and_player_death_never_control_engagement():
    controller = engage(stalled_progress_ms=100, maximum_reengage_attempts=0,
                        maximum_stalled_retargets=1)
    decision = controller.step(_observation(200, _target("mob"),
        _event(NativeCombatEventKind.TARGET_KILLED, 0),
        _event(NativeCombatEventKind.PLAYER_HIT_TARGET, 1),
        _event(NativeCombatEventKind.PLAYER_KILLED, 2)))
    assert decision.kills == 0
    assert decision.phase is PvEPhase.DISENGAGING
    assert decision.cleanup_request.reason == "engagement_stalled"


def test_actual_action_identity_remains_correlated_after_deselection():
    controller = engage()
    action = replace(_player_action(phase=NativeTargetActionPhase.WINDUP),
                     selected_target_token=None, action_target_token="mob",
                     targeting_selected=False)
    frame = _observation(200, _absent(), player_action=action,
        population=_population(None, _character("mob", lt=103), action_target="mob"))
    decision = controller.step(frame)
    assert decision.phase is PvEPhase.ENGAGED
    assert controller._player_attack_animation_observed
    assert decision.intent is None


def test_busy_action_without_target_is_not_attributed_or_cleanup_proof():
    controller = engage()
    action = replace(_player_action(phase=NativeTargetActionPhase.QUEUED),
                     action_target_token=None, targeting_selected=False)
    frame = _observation(200, _target("mob"), player_action=action)
    decision = controller.step(frame)
    assert not controller._player_attack_animation_observed
    assert decision.phase is PvEPhase.ENGAGED
    stop = controller.stop("operator_stop", now_ms=300)
    assert stop.cleanup_request is not None


def test_mixed_actual_action_frame_is_rejected():
    frame = _observation(0, _target("mob"), player_action=_player_action())
    action = replace(frame.player_action, action_target_token="other", targeting_selected=False)
    with pytest.raises(ValueError, match="resolved different|disagree"):
        replace(frame, player_action=action)


def test_selection_diagnostic_does_not_invalidate_actual_action_frame():
    frame = _observation(0, _target("mob"), player_action=_player_action())
    action = replace(frame.player_action, selected_target_token="other", targeting_selected=False)
    updated = replace(frame, player_action=action)
    assert updated.player_action.action_target_token == frame.player_action.action_target_token
    assert updated.population == frame.population


def test_opener_followup_never_targets_new_selection():
    controller = engage(opening_intent=PvEIntent.CAST_SHADOW_TOUCH, opening_followup_delay_ms=100)
    frame = _observation(200, _target("other"),
        population=_population("other", _character("mob", lt=103), _character("other", lt=104)))
    decision = controller.step(frame)
    assert decision.phase is PvEPhase.ENGAGED and decision.intent is None
    assert decision.tracked_target.token == "mob"


def test_cleanup_qualification_preserves_existing_action_and_later_readiness_drop(owner):
    session, grant, _, transport, _ = owner
    cleanup = NativePvECombatCleanup(session, grant)
    assert transport.commands == []  # Startup does not interrupt a user's existing cast.
    transport.header = replace(transport.header,
        capability_flags=channel.CLIENT_ACTION_TRANSPORT_CAPABILITY)
    result = cleanup.cleanup(request())
    assert result.confirmed
    assert len(transport.commands) == 1
    assert cleanup.cleanup(request()) == result and len(transport.commands) == 1
    assert transport.commands[0].kind.value == Verb.PAUSE.value
    assert transport.commands[0].payload.expected == grant.ownership


def test_missing_capability_prevents_baseline_pause(owner):
    session, grant, _, transport, _ = owner
    transport.header = replace(transport.header,
        capability_flags=channel.CLIENT_ACTION_TRANSPORT_CAPABILITY)
    with pytest.raises(channel.NativeActionChannelUnavailable):
        NativePvECombatCleanup(session, grant)
    assert transport.commands == []




@pytest.mark.parametrize("kind", ["timeout", "stop_failed", "mismatch"])
def test_cleanup_retains_exact_request_and_first_uncertain_result(owner, kind):
    session, grant, _, transport, _ = owner
    cleanup = NativePvECombatCleanup(session, grant)
    if kind == "timeout":
        transport.failure = channel.NativeActionChannelTimeout("unconfirmed\n" + "x"*500)
    elif kind == "stop_failed":
        transport.failure = NativeMovementError(Outcome.STOP_FAILED)
    else:
        original = session.pause
        session.pause = lambda g, key: replace(original(g, key), window=g.window + 1)
    result = cleanup.cleanup(request())
    assert not result.confirmed and result.error
    assert len(result.error) < 230 and "\n" not in result.error
    transport.failure = None
    assert cleanup.cleanup(request()) is result
    assert len(transport.commands) == 1
    with pytest.raises(RuntimeError, match="previous cleanup"):
        cleanup.cleanup(request(1))
    assert len(transport.commands) == 1


def test_cleanup_storage_is_bounded_and_retired_requests_cannot_rebind(owner):
    session, grant, _, transport, _ = owner
    cleanup = NativePvECombatCleanup(session, grant)
    for index in range(100):
        assert cleanup.cleanup(request(index)).confirmed
    count = len(transport.commands)
    with pytest.raises(ValueError, match="retired"):
        cleanup.cleanup(request(0))
    with pytest.raises(ValueError, match="retired"):
        cleanup.cleanup(replace(request(99), target_token="other"))
    assert len(transport.commands) == count
    assert cleanup._result.request == request(99)


@pytest.mark.parametrize("behavior", ["negative", "exception", "missing", "mismatch"])
def test_runner_cleanup_failure_never_retries_or_rearms(behavior):
    calls = []
    class Cleanup:
        def cleanup(self, pending):
            calls.append(pending)
            if behavior == "exception":
                raise TimeoutError("native PAUSE uncertain")
            if behavior == "mismatch":
                return ConfirmedCleanup().cleanup(replace(pending, sequence=999))
            return PvECombatCleanupResult(pending, False, error="busy cast")
    clock, dispatcher = AdvancingClock(), RecordingPvEDispatcher()
    controller = PvEController(PvEControllerConfig(stalled_progress_ms=100,
                                                  maximum_reengage_attempts=0))
    runner = _runner(controller=controller,
        health_reader=SequenceHealthSource((_absent(), _target("mob"), _target("mob"))),
        player_vitals_reader=SequencePlayerVitalsSource((_player(),)*3),
        dispatcher=dispatcher, stop_signal=EventEmergencyStop(), clock=clock, sleeper=clock.sleep,
        combat_cleanup=None if behavior == "missing" else Cleanup())
    result = runner.run()
    assert result.final_phase is PvEPhase.STOPPED
    assert result.terminal_reason == "combat_cleanup_unconfirmed"
    assert len(calls) == (0 if behavior == "missing" else 1)
    assert controller.pending_cleanup is not None
    assert dispatcher.intents == [PvEIntent.ACQUIRE_NEXT_MOB, PvEIntent.ATTACK_SELECTED_TARGET]
    assert any(step.combat_cleanup is not None and not step.combat_cleanup.confirmed
               for step in result.trace)


def test_runner_unwind_cleans_plain_combat_without_any_movement():
    calls = []
    class Cleanup:
        def cleanup(self, pending):
            calls.append(pending)
            return ConfirmedCleanup().cleanup(pending)
    clock = AdvancingClock()
    def sleeper(seconds):
        clock.sleep(seconds)
        if clock.value >= .2:
            raise KeyboardInterrupt
    runner = _runner(controller=PvEController(PvEControllerConfig()),
        health_reader=SequenceHealthSource((_absent(), _target("mob"))),
        player_vitals_reader=SequencePlayerVitalsSource((_player(),)*2),
        dispatcher=RecordingPvEDispatcher(), stop_signal=EventEmergencyStop(),
        clock=clock, sleeper=sleeper, combat_cleanup=Cleanup())
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert len(calls) == 1 and calls[0].target_token == "mob"

@pytest.mark.parametrize("selected", [None, "other", "mob"])
def test_startup_adopts_exact_current_npc_without_redundant_selection_or_attack(selected):
    controller = PvEController(PvEControllerConfig(opening_intent=PvEIntent.CAST_SHADOW_TOUCH))
    action = replace(_player_action(token=selected, mode=2, action_state=4),
                     targeting_selected=selected == "mob", action_target_token="mob")
    selected_health = _absent() if selected is None else _target(selected)
    others = (_character("other", lt=140),) if selected == "other" else ()
    frame = _observation(0, selected_health, player_action=action,
        population=_population(selected, _character("mob", lt=103), *others, action_target="mob"))
    adopted = controller.step(frame)
    assert adopted.phase is PvEPhase.ENGAGED
    assert adopted.tracked_target.token == "mob"
    assert adopted.intent is None and adopted.cleanup_request is None
    assert adopted.native_action_pending
    still_casting = controller.step(replace(frame, now_ms=3000))
    assert still_casting.intent is None and still_casting.cleanup_request is None


@pytest.mark.parametrize("mode,state,pending", [(1, 4, False), (2, 1, True), (None, None, False)])
def test_unknown_target_action_waits_for_actual_completion_not_animation_or_impact(
    mode, state, pending,
):
    controller = PvEController(PvEControllerConfig())
    action = replace(_player_action(token="other", mode=mode, action_state=state),
                     action_pending=pending)
    frame = _observation(0, _target("other"), player_action=action)
    waiting = controller.step(frame)
    assert waiting.phase is PvEPhase.OBSERVING_ACTION
    assert waiting.tracked_target is None and waiting.intent is None
    assert waiting.cleanup_request is None
    # Actual action completion allows new work without waiting for projectile impact.
    finished = replace(action, mode=2, action_state=1, action_pending=False)
    after = controller.step(replace(frame, now_ms=100, player_action=finished))
    assert after.phase is PvEPhase.SEEKING and after.intent is None
    acquire = controller.step(_observation(200, _absent()))
    attack = controller.step(_observation(300, _target("new")))
    assert acquire.intent is PvEIntent.ACQUIRE_NEXT_MOB
    assert attack.intent is PvEIntent.ATTACK_SELECTED_TARGET
    old_projectile = controller.step(_observation(400, _target("new"),
        _event(NativeCombatEventKind.TARGET_KILLED)))
    assert old_projectile.kills == 0


def test_missing_action_observation_is_unknown_and_stop_has_no_fabricated_target():
    controller = PvEController(PvEControllerConfig())
    frame = replace(_observation(0, _target("mob")), player_action=None)
    waiting = controller.step(frame)
    assert waiting.phase is PvEPhase.OBSERVING_ACTION
    assert waiting.intent is None and waiting.cleanup_request is None
    assert controller.stop("operator_stop", now_ms=100).cleanup_request is None


@pytest.mark.parametrize("kind", ["player", "pet", "unknown"])
def test_ordinary_pve_never_adopts_or_attacks_non_npc(kind):
    from shadowbane_lab.client_observation.native_population import NativeCharacterKind
    character = replace(_character("other", lt=104), character_kind=NativeCharacterKind(kind))
    population = _population("other", character)
    controller = PvEController(PvEControllerConfig())
    controller.step(_observation(0, _absent()))
    selected = controller.step(_observation(100, _target("other"), population=population))
    assert selected.intent is not PvEIntent.ATTACK_SELECTED_TARGET
    action = _player_action(token="other", targeting_selected=True, mode=2, action_state=1)
    active = controller.step(_observation(200, _target("other"), player_action=action,
        population=replace(population, player_action_target_token="other")))
    assert active.phase is PvEPhase.OBSERVING_ACTION
    assert active.tracked_target is None and active.intent is None


def test_runner_existing_unknown_cast_performs_no_input_or_cleanup_until_stop():
    from test_pve_controller import SequencePlayerActionSource
    calls = []
    class Cleanup:
        def cleanup(self, pending):
            calls.append(pending)
            return ConfirmedCleanup().cleanup(pending)
    action = _player_action(token="mob", mode=1, action_state=4)
    clock, dispatcher = AdvancingClock(), RecordingPvEDispatcher()
    result = _runner(controller=PvEController(PvEControllerConfig(maximum_session_ms=200)),
        health_reader=SequenceHealthSource((_target("mob"),)*3),
        player_vitals_reader=SequencePlayerVitalsSource((_player(),)*3),
        player_action_reader=SequencePlayerActionSource((action,)*3),
        dispatcher=dispatcher, stop_signal=EventEmergencyStop(), clock=clock, sleeper=clock.sleep,
        combat_cleanup=Cleanup()).run()
    assert result.terminal_reason == "maximum_session_elapsed"
    assert dispatcher.intents == [] and calls == []
    assert all(step.decision.tracked_target is None for step in result.trace)


def test_listed_admission_waits_for_unknown_cast_completion_without_pausing():
    from test_pve_controller import SequencePlayerActionSource
    prepared = []
    class Listed:
        active = False
        def prepare(self, observation, camp):
            prepared.append(observation.now_ms)
            return False
    busy = _player_action(token="mob", mode=1, action_state=4)
    idle = replace(busy, mode=2, action_state=1)
    clock, dispatcher = AdvancingClock(), RecordingPvEDispatcher()
    result = _runner(controller=PvEController(PvEControllerConfig(maximum_session_ms=300)),
        health_reader=SequenceHealthSource((_target("mob"),)*4),
        player_vitals_reader=SequencePlayerVitalsSource((_player(),)*4),
        player_action_reader=SequencePlayerActionSource((busy, busy, idle, idle)),
        dispatcher=dispatcher, stop_signal=EventEmergencyStop(), clock=clock, sleeper=clock.sleep,
        listed_combat=Listed()).run()
    assert result.terminal_reason == "maximum_session_elapsed"
    assert prepared == [200, 300]
    assert dispatcher.intents == []
    assert not any(step.combat_cleanup is not None for step in result.trace)


def test_owned_ordinary_engagement_keeps_explicit_list_interruption_policy():
    controller = engage()
    action = _player_action(token="mob", mode=1, action_state=4)
    assert controller.can_start_external_combat(_observation(200, _target("mob"),
                                                              player_action=action))
