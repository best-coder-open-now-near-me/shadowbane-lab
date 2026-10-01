"""Native reuse evidence skips only an optional, unentered opener."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_combat_session import owner as session_fixture
from test_combat_wire_v2 import command, receipt
from test_native_combat_coordinator import answer
from test_native_combat_coordinator import setup as coordinator_fixture
from test_pve_native_proposals import observe

from shadowbane_lab.client_extension import action_channel as channel
from shadowbane_lab.client_extension import combat_wire_v2 as legacy
from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OWNER_CLEANUP,
    Action,
    ClosureScope,
    LocalSettlement,
    Outcome,
    Phase,
    Reason,
    Receipt,
    Verb,
)
from shadowbane_lab.client_extension.actor_action_wire import (
    Closure as ClosureProof,
)
from shadowbane_lab.client_extension.actor_action_wire import (
    Entry as EntryState,
)
from shadowbane_lab.pve.model import (
    PvEAbility,
    PvEAbilityRecipient,
    PvECombatAcknowledgement,
    PvECombatDisposition,
    PvECombatKind,
    PvECombatNotReadyReason,
    PvEControllerConfig,
    PvEPhase,
)
from shadowbane_lab.pve.target_authority import PvEController


@pytest.fixture
def owner(monkeypatch):
    yield from session_fixture.__wrapped__(monkeypatch)


@pytest.fixture
def setup():
    return coordinator_fixture.__wrapped__()


def blocked(c, verb=Verb.SUBMIT):
    if c.action is Action.NONE:
        return answer(c, verb)
    return replace(
        answer(c, verb),
        outcome=Outcome.POWER_REUSE_BLOCKED,
        entry=EntryState.NEVER_ENTERED,
        local_settlement=LocalSettlement.SETTLED,
        reason=Reason.POWER_REUSE,
        flags=OWNER_CLEANUP | CONTEXT_CLEANUP,
    )


def legacy_blocked(c=None, verb=legacy.Verb.SUBMIT):
    return replace(
        receipt(c, verb),
        outcome=legacy.Outcome.POWER_REUSE_BLOCKED,
        entry_state=legacy.EntryState.NEVER_ENTERED,
        flags=legacy.CLEANUP_REQUIRED,
    )


def not_ready():
    return PvECombatAcknowledgement(
        PvECombatDisposition.NOT_READY, False, True, PvECombatNotReadyReason.POWER_REUSE
    )


@pytest.mark.parametrize("action", [legacy.Action.CAST, legacy.Action.SELF_POWER])
def test_power_reuse_wire_retains_geometry_and_exact_action_correlation(action):
    c = command(action=action)
    r = legacy_blocked(c)
    assert len(r.encode()) == 384 and len(c.encode()) == 576
    assert legacy.Receipt.decode(r.encode()) == r
    r.require_command(c, legacy.Verb.SUBMIT)
    with pytest.raises(ValueError):
        r.require_command(replace(c, power_id=c.power_id + 1), legacy.Verb.SUBMIT)


@pytest.mark.parametrize(
    "change",
    [
        dict(action=legacy.Action.ATTACK, power_id=0),
        dict(action=legacy.Action.NONE, power_id=0, verb=legacy.Verb.BIND_ENGAGEMENT),
        dict(entry_state=legacy.EntryState.ENTERED),
        dict(entry_state=legacy.EntryState.UNKNOWN),
        dict(flags=3),
        dict(flags=5),
        dict(flags=0),
        dict(verb=legacy.Verb.CANCEL_ACTION),
        dict(phase=legacy.Phase.CLOSED, closure=legacy.ClosureProof.NEVER_BOUND, flags=0),
    ],
)
def test_power_reuse_wire_rejects_ambiguous_or_unowned_claim(change):
    with pytest.raises(ValueError):
        replace(legacy_blocked(), **change).encode()


def test_unknown_wire_outcome_never_becomes_not_ready():
    data = bytearray(legacy_blocked().encode())
    data[40:44] = (999).to_bytes(4, "little")
    with pytest.raises(ValueError):
        legacy.Receipt.decode(bytes(data))


@pytest.mark.parametrize(
    "change",
    [
        dict(native_entered=True),
        dict(native_entered=None),
        dict(cleanup_required=False),
        dict(not_ready_reason=None),
        dict(not_ready_reason="power_reuse"),
        dict(disposition=PvECombatDisposition.DEFERRED),
    ],
)
def test_policy_not_ready_requires_typed_never_entered_evidence(change):
    with pytest.raises(ValueError):
        replace(not_ready(), **change)


@pytest.mark.parametrize("recipient", list(PvEAbilityRecipient))
def test_optional_opener_skip_waits_for_fresh_clear_frame_without_fake_queue(recipient):
    controller = PvEController(PvEControllerConfig(opening_ability=PvEAbility(123, recipient)))
    proposal = controller.step(observe()).combat_proposal
    controller.acknowledge_combat(proposal, not_ready(), now_ms=0)
    assert controller.pending_combat_proposal is None and controller.pending_cleanup is None
    assert controller._opening_skipped and controller._opening_queued_at is None
    assert controller._queued_self_followup is None and controller._last_power_at == {}
    assert controller.step(observe()).combat_proposal is None
    assert controller.step(observe(1, busy=True)).combat_proposal is None
    unknown = observe(2)
    unknown = replace(
        unknown,
        player_action=replace(
            unknown.player_action, initiation_state=None, power_protocol_ids=None
        ),
    )
    assert controller.step(unknown).combat_proposal is None
    decision = controller.step(observe(3))
    assert decision.combat_proposal.kind is PvECombatKind.ATTACK
    assert decision.combat_proposal.target_key == proposal.target_key
    assert (
        decision.opening_skill_skipped
        and decision.opening_skill_skip_reason is PvECombatNotReadyReason.POWER_REUSE
    )


def test_not_ready_nonopener_cannot_automatically_attack():
    controller = PvEController(PvEControllerConfig())
    proposal = controller.step(observe()).combat_proposal
    controller.acknowledge_combat(proposal, not_ready(), now_ms=0)
    assert controller.pending_cleanup.reason == "native_power_not_ready"
    assert not controller._opening_skipped


@pytest.mark.parametrize("bad", ["entry", "key", "reason_only"])
def test_coordinator_invalid_reuse_receipt_remains_uncertain(setup, bad):
    combat, session, tickets, observation, proposal = setup

    def response(g, v, c, **kwargs):
        if c.action is Action.NONE:
            return SimpleNamespace(receipt=answer(c, v), native_detail=None)
        r = blocked(c, v)
        if bad == "entry":
            r = replace(r, entry=EntryState.ENTERED)
        if bad == "key":
            r = replace(r, command_digest=bytes([99]) * 32)
        if bad == "reason_only":
            r = answer(c, v, outcome=Outcome.UNCERTAIN, queued=False)
        return SimpleNamespace(receipt=r, native_detail="power_reuse")

    session.actor_action.side_effect = response
    update = combat.advance(proposal, observation)
    assert update.acknowledgement.disposition is PvECombatDisposition.UNCERTAIN
    assert update.acknowledgement.not_ready_reason is None and combat.pending == proposal


def test_coordinator_reuse_result_resolves_action_only_and_attack_keeps_engagement(setup):
    combat, session, tickets, observation, proposal = setup
    session.actor_action.side_effect = lambda g, v, c, **kw: SimpleNamespace(
        receipt=blocked(c, v), native_detail=None
    )
    update = combat.advance(proposal, observation)
    original = session.actor_action.call_args.args[2]
    assert update.acknowledgement == not_ready() and combat.pending is None and combat.active
    assert (
        update.as_dict()["not_ready_reason"] == "power_reuse"
        and not update.as_dict()["outbound_queued"]
    )
    session.actor_action.side_effect = lambda g, v, c, **kw: SimpleNamespace(
        receipt=answer(c, v), native_detail=None
    )
    combat.advance(
        replace(proposal, proposal_id=2, kind=PvECombatKind.ATTACK, power_id=0), observation
    )
    follow = session.actor_action.call_args.args[2]
    assert (
        follow.parent_id == original.parent_id
        and follow.context_id == original.context_id
        and follow.request != original.request
        and len(tickets) == 2
    )
    tickets[0].close.assert_not_called()
    session.pause.assert_not_called()


def test_readiness_cap_missing_blocks_preflight_and_submit_but_not_old_status(owner):
    session, grant, c, transport, _ = owner
    transport.header = replace(
        transport.header,
        capability_flags=channel.CLIENT_ACTION_TRANSPORT_CAPABILITY
        | channel.OBJECT_COMBAT_CAPABILITY,
    )
    with pytest.raises(channel.NativeActionChannelUnavailable, match="readiness"):
        session.require_combat_available(grant, power_readiness=True)
    with pytest.raises(channel.NativeActionChannelUnavailable, match="readiness"):
        session.combat(grant, legacy.Verb.SUBMIT, c)
    assert not transport.commands
    session.combat(grant, legacy.Verb.ACTION_STATUS, c)
    assert transport.commands[-1].kind is legacy.Verb.ACTION_STATUS


def test_readiness_preflight_has_no_native_side_effect(owner):
    session, grant, _, transport, _ = owner
    session.require_combat_available(grant, power_readiness=True)
    assert not transport.commands


@pytest.mark.parametrize(
    "phase,closure,flags",
    [
        (Phase.STOPPING, ClosureProof.NONE, OWNER_CLEANUP | CONTEXT_CLEANUP),
        (Phase.BLOCKED, ClosureProof.NONE, OWNER_CLEANUP | CONTEXT_CLEANUP),
        (Phase.CLOSED, ClosureProof.NATIVE_STOPPED, OWNER_CLEANUP),
        (Phase.RETIRED, ClosureProof.SCENE_RETIRED, 0),
    ],
)
def test_historical_reuse_receipt_preserved_without_policy_fallback(setup, phase, closure, flags):
    combat, session, tickets, observation, proposal = setup

    def uncertain(g, v, c, **kw):
        if v is Verb.SUBMIT:
            raise TimeoutError()
        return SimpleNamespace(receipt=answer(c, v), native_detail=None)

    session.actor_action.side_effect = uncertain
    combat.advance(proposal, observation)
    original = session.actor_action.call_args.args[2]

    def response(g, v, c, **kwargs):
        r = replace(
            blocked(c, v),
            context_phase=phase,
            closure=closure,
            flags=flags,
            owner_phase=Phase.RETIRED if phase is Phase.RETIRED else Phase.BOUND,
            closure_scope=ClosureScope.OWNER
            if phase is Phase.RETIRED
            else ClosureScope.CONTEXT
            if phase is Phase.CLOSED
            else ClosureScope.NONE,
            mode=1,
        )
        assert Receipt.decode(r.encode()) == r
        return SimpleNamespace(receipt=r, native_detail=None)

    session.actor_action.side_effect = response
    update = combat.advance(proposal, observation)
    assert session.actor_action.call_args.args[1] is Verb.ACTION_STATUS
    assert session.actor_action.call_args.args[2] is original
    assert update.acknowledgement.disposition is PvECombatDisposition.REJECTED
    assert update.acknowledgement.not_ready_reason is None
    assert update.acknowledgement.cleanup_required == (phase in (Phase.STOPPING, Phase.BLOCKED))
    assert combat.active  # Historical action receipt does not close the actor context handle.
    tickets[0].close.assert_not_called()
    tickets[1].close.assert_not_called()


def test_skip_is_per_encounter_and_does_not_disable_next_opener():
    from test_pve_native_proposals import ack, character

    from shadowbane_lab.pve.model import PvECombatCleanupResult

    controller = PvEController(
        PvEControllerConfig(
            maximum_kills=2, opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR)
        )
    )
    first = controller.step(observe()).combat_proposal
    controller.acknowledge_combat(first, not_ready(), now_ms=0)
    attack = controller.step(observe(1)).combat_proposal
    ack(controller, attack, now=1)
    dead = replace(character(), current_health=0)
    assert controller.step(observe(2, characters=(dead,))).phase is PvEPhase.POST_KILL
    cleanup = controller.step(observe(1002, characters=(dead,))).cleanup_request
    assert cleanup is not None
    controller.acknowledge_cleanup(PvECombatCleanupResult(cleanup, True, "exact-owned-stop"))
    next_target = character(token="second", uuid=2)
    assert controller.step(observe(1003, characters=(next_target,))).phase is PvEPhase.SEEKING
    second = controller.step(observe(1004, characters=(next_target,)))
    assert second.combat_proposal.kind is PvECombatKind.SELF_POWER
    assert second.combat_proposal.target_key != first.target_key
    assert not second.opening_skill_skipped and not controller._last_power_at


def test_target_replacement_after_not_ready_requires_cleanup_not_fallback():
    from test_pve_native_proposals import character

    controller = PvEController(
        PvEControllerConfig(opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR))
    )
    opening = controller.step(observe()).combat_proposal
    controller.acknowledge_combat(opening, not_ready(), now_ms=0)
    changed = (character(token="replacement", uuid=2),)
    assert controller.step(observe(1, characters=changed)).combat_proposal is None
    stopped = controller.step(observe(1000, characters=changed))
    assert (
        stopped.combat_proposal is None and stopped.cleanup_request.object_key == opening.target_key
    )


def test_public_runner_recovery_skips_reuse_blocked_second_opener(setup, monkeypatch):
    from test_pve_native_proposals import character

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.client_observation import NativeGroupObservation
    from shadowbane_lab.client_observation.native_object import NativeObjectKey
    from shadowbane_lab.pve import PvERunner

    combat, session, tickets, old_observation, template = setup
    clock = SimpleNamespace(now=0.0)
    stop = EventEmergencyStop()
    first = replace(character(), object_key=template.target_key, token=template.target_token)
    second = replace(character(token="second", distance=10), object_key=NativeObjectKey(9876, 37))
    first_attack_queued = False

    def current():
        victim = replace(first, current_health=0) if first_attack_queued else first
        value = observe(round(clock.now * 1000), characters=(victim, second))
        return replace(
            value,
            population=replace(
                value.population,
                local_player_object_key=old_observation.population.local_player_object_key,
            ),
        )

    def source(field):
        return SimpleNamespace(process_id=1234, observe=lambda: getattr(current(), field))

    # The real actor coordinator builds each exact child binding directly.
    def response(grant, verb, c, **kwargs):
        nonlocal first_attack_queued
        if verb is Verb.STOP_CONTEXT:
            value = answer(
                c,
                verb,
                outcome=Outcome.ENGAGEMENT_CLOSED,
                phase=Phase.CLOSED,
                closure=ClosureProof.NATIVE_STOPPED,
                queued=False,
            )
        elif c.action is Action.SELF_POWER and combat.owner.context.target_key == (9876, 37):
            value = blocked(c, verb)
        else:
            value = answer(c, verb)
            if c.action is Action.ATTACK:
                if combat.owner.context.target_key == (9876, 37):
                    stop.trip()
                else:
                    first_attack_queued = True
        return SimpleNamespace(receipt=value, native_detail=None)

    session.actor_action.side_effect = response
    trace = []

    def sleep(seconds):
        clock.now += seconds
        assert clock.now < 5, "two-encounter recovery did not complete"

    runner = PvERunner(
        controller=PvEController(
            PvEControllerConfig(
                maximum_kills=2, opening_ability=PvEAbility(123, PvEAbilityRecipient.ACTOR)
            )
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
    )
    result = runner.run()
    calls = [
        x
        for x in session.actor_action.call_args_list
        if x.args[1] not in (Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT)
    ]
    assert [(x.args[1], x.args[2].action) for x in calls] == [
        (Verb.SUBMIT, Action.SELF_POWER),
        (Verb.SUBMIT, Action.ATTACK),
        (Verb.STOP_CONTEXT, Action.NONE),
        (Verb.SUBMIT, Action.SELF_POWER),
        (Verb.SUBMIT, Action.ATTACK),
        (Verb.STOP_CONTEXT, Action.NONE),
    ]
    commands = [x.args[2] for x in calls]
    assert commands[0].context_id == commands[1].context_id == commands[2].context_id
    assert commands[3].context_id == commands[4].context_id == commands[5].context_id
    assert commands[0].context_id != commands[3].context_id
    assert first.object_key != second.object_key
    assert all(x.args[0] == combat.owner.grant for x in calls) and len(tickets) == 3
    death = next(i for i, s in enumerate(trace) if s.decision.kill_confirmation is not None)
    cleanup = next(
        i
        for i, s in enumerate(trace)
        if s.combat_cleanup is not None and s.combat_cleanup.confirmed
    )
    seeking = next(
        i for i, s in enumerate(trace) if i > cleanup and s.decision.phase is PvEPhase.SEEKING
    )
    refused = next(
        i
        for i, s in enumerate(trace)
        if s.native_combat is not None
        and s.native_combat.acknowledgement.disposition is PvECombatDisposition.NOT_READY
    )
    assert death < cleanup < seeking < refused
    assert trace[refused].native_combat.receipt.entry is EntryState.NEVER_ENTERED
    assert trace[refused + 1].decision.opening_skill_skipped
    assert trace[refused + 1].decision.now_ms > trace[refused].decision.now_ms
    assert trace[refused + 1].native_combat.receipt.action is Action.ATTACK
    assert result.terminal_reason == "emergency_stop" and not combat.active
    assert runner._controller._last_power_at == {123: 0}
    session.pause.assert_not_called()
