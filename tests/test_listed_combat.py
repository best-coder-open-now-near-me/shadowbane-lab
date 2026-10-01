"""Saved-list policy uses the same native engagement owner as ordinary NPC combat."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_actor_action_wire import fixture
from test_combat_fence import LOCAL, OWNER, TARGET, entry, store_at
from test_native_actor_coordinator import reply as actor_reply

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelTimeout,
    NativeActionChannelUnavailable,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.actor_action_fence import Authority, ContextBinding, Ordinals
from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OUTBOUND_QUEUED,
    OWNER_CLEANUP,
    Action,
    Closure,
    ClosureScope,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Verb,
)
from shadowbane_lab.client_extension.cleanup_settlement import CleanupSettlement
from shadowbane_lab.client_extension.combat_wire_v2 import identity_digest
from shadowbane_lab.client_extension.movement_session import NativeMovementGrant
from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvERunner
from shadowbane_lab.pve.authority import PvETargetCharacterKind
from shadowbane_lab.pve.authority_snapshot import build_native_party_authority_snapshot
from shadowbane_lab.pve.listed_combat import (
    ListedCombatCoordinator,
    ListedCombatInterruptionError,
    ListedCombatUpdate,
)
from shadowbane_lab.pve.listed_target import listed_targets
from shadowbane_lab.pve.model import PvECampLease, PvEObservation, PvEPhase
from shadowbane_lab.pve.native_actor import NativeActorCoordinator
from shadowbane_lab.pve.native_combat import NativeCombatCoordinator, context_cleanup_confirmed


def frame(now=0, *, dead=False, absent=False, party=False, lt=5, local=LOCAL):
    character = NativeCharacterObservation(
        "opaque-player-token",
        0 if dead else 100,
        100,
        lt,
        0,
        0,
        False,
        False,
        False,
        False,
        False,
        object_key=TARGET,
        character_kind=NativeCharacterKind.PLAYER,
    )
    population = NativeCharacterPopulationObservation(
        () if absent else (character,),
        None,
        None,
        1,
        0,
        local,
    )
    members = (
        ()
        if not party
        else tuple(
            NativeGroupMemberObservation(
                "untrusted name",
                "",
                key.object_type,
                key.object_uuid,
                100,
                100,
                100,
                0,
                0,
                0,
                0,
                False,
            )
            for key in (local, TARGET)
        )
    )
    authority = build_native_party_authority_snapshot(
        population,
        NativeGroupObservation(False, False, members),
        revision=1,
        party_group_id="party",
    )
    return PvEObservation(
        now,
        NativeTargetHealthObservation(False),
        NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100),
        player_position=NativePlayerPositionObservation(0, 0, 0),
        target_position=NativeTargetPositionObservation(False),
        population=population,
        authority_snapshot=authority,
        player_action=NativePlayerActionObservation(
            targeting_selected=False,
            motion_id=0,
            animation_event_index=0,
            animation_frame=None,
            selected_target_token=None,
            action_target_token=None,
            initiation_state=5,
            power_protocol_ids=(),
            mode=1,
            action_state=1,
        ),
    )


@pytest.fixture
def encounter(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    actor_binding, _, template, _ = fixture()
    grant = NativeMovementGrant(
        NativeClientProcessIdentity(actor_binding.client_pid, actor_binding.client_creation),
        template.window,
        template.grant,
        template.host,
        "acquisition",
    )
    events, calls, commands, tickets, bindings = [], [], [], [], {}
    state = SimpleNamespace(
        failure=None,
        register_failure=None,
        stop_pending=False,
        response=None,
        native_detail=None,
        unavailable=False,
        mode=2,
        action_state=1,
        close_on_status=False,
    )
    current = SimpleNamespace(failure=False)
    clock = SimpleNamespace(now=0.0)

    class Ticket:
        def arm(self, **kwargs):
            pass

        def revoke(self, **kwargs):
            events.append("revoke")

        def close(self, **kwargs):
            events.append("close")

    def register(entry_id, **kwargs):
        if state.register_failure:
            raise state.register_failure
        assert entry_id == entry().entry_id
        assert kwargs["expected_revision"] == store.snapshot().revision
        parent = kwargs["parent"]
        assert parent.actor_key == (LOCAL.object_type, LOCAL.object_uuid)
        ticket = Ticket()
        tickets.append(ticket)
        events.append("register")
        binding = ContextBinding(
            parent.digest,
            kwargs["context_id"],
            Authority.MANUAL_PLAYER,
            kwargs["target_hint"],
            (TARGET.object_type, TARGET.object_uuid),
            store.snapshot().revision,
            b"s" * 32,
            bytes.fromhex(entry_id),
            identity_digest("Enemy"),
        )
        bindings[binding.context_id] = binding
        return ticket, binding

    monkeypatch.setattr(store, "register_actor_context", register)
    parent_ticket = Mock()

    def factory(binding, **kwargs):
        if not isinstance(binding, ContextBinding):
            return parent_ticket
        ticket = Ticket()
        tickets.append(ticket)
        bindings[binding.context_id] = binding
        events.append("register_npc")
        return ticket

    def require_current():
        if current.failure:
            raise RuntimeError("character changed")

    def require_available(owner):
        assert owner is grant
        if state.unavailable:
            raise NativeActionChannelUnavailable("actor action capability absent")

    def reply(command, verb):
        result = actor_reply(command, verb)
        mode = state.response if verb not in (Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT) else None
        if (
            state.close_on_status
            and verb is Verb.CONTEXT_STATUS
            and bindings[command.context_id].authority is Authority.MANUAL_PLAYER
        ):
            mode = "closed"
        control = command.action is Action.NONE
        if mode == "blocked" or (verb is Verb.STOP_CONTEXT and state.stop_pending):
            result.receipt = replace(
                result.receipt,
                outcome=Outcome.UNAVAILABLE,
                owner_phase=Phase.BOUND,
                context_phase=Phase.BLOCKED,
                closure=Closure.NONE,
                closure_scope=ClosureScope.NONE,
                entry=Entry.UNKNOWN,
                local_settlement=(LocalSettlement.UNKNOWN if control else LocalSettlement.PENDING),
                flags=OWNER_CLEANUP | CONTEXT_CLEANUP,
            )
        elif mode in ("closed", "retired"):
            retired = mode == "retired"
            result.receipt = replace(
                result.receipt,
                owner_phase=Phase.RETIRED if retired else Phase.BOUND,
                context_phase=Phase.RETIRED if retired else Phase.CLOSED,
                closure=Closure.SCENE_RETIRED if retired else Closure.NATIVE_STOPPED,
                closure_scope=ClosureScope.OWNER if retired else ClosureScope.CONTEXT,
                outcome=Outcome.ENGAGEMENT_CLOSED if control else Outcome.CLIENT_OUTBOUND_QUEUED,
                flags=(0 if retired else OWNER_CLEANUP) | (0 if control else OUTBOUND_QUEUED),
                mode=1,
                combat_target_present=False,
            )
        result.receipt.require_command(command, verb)
        result.native_detail = state.native_detail
        return result

    def actor_action(owner, verb, command, **kwargs):
        assert owner is grant
        calls.append(verb)
        commands.append(command)
        events.append(verb.name.lower())
        if state.failure and verb not in (Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT):
            raise state.failure
        return reply(command, verb)

    def pause(*args):
        raise AssertionError("listed admission must not pause an otherwise idle actor")

    ids = Ordinals()
    session = SimpleNamespace(
        cleanup=CleanupSettlement(
            clock=lambda: clock.now,
            sleeper=lambda seconds: setattr(clock, "now", clock.now + seconds),
        ),
        actor_action=actor_action,
        pause=pause,
        require_actor_actions=require_available,
        actor_ordinals=lambda owner: ids,
    )
    character_session = SimpleNamespace(
        require_current=require_current,
        binding=SimpleNamespace(
            object_key=LOCAL,
            identity=SimpleNamespace(character_name=OWNER.character, server_name=OWNER.server),
        ),
    )
    population = SimpleNamespace(
        observe_actor_identity=lambda: ("actor-token", LOCAL, None),
        resolve_actor_address=lambda **kwargs: actor_binding.actor_hint,
        resolve_combat_addresses=lambda **kwargs: (actor_binding.actor_hint, 0x12400000),
    )
    owner = NativeActorCoordinator(
        session=session,
        grant=grant,
        population=population,
        character_session=character_session,
        store=store,
        ticket_factory=factory,
    )
    shared = NativeCombatCoordinator(owner=owner)
    coordinator = ListedCombatCoordinator(
        store=store, combat=shared, require_current=require_current
    )
    return SimpleNamespace(
        store=store,
        coordinator=coordinator,
        combat=shared,
        owner=owner,
        session=session,
        state=state,
        current=current,
        calls=calls,
        commands=commands,
        events=events,
        tickets=tickets,
        parent_ticket=parent_ticket,
        bindings=bindings,
        command=template,
    )


def start(encounter):
    assert encounter.coordinator.prepare(frame(), None)
    update = encounter.coordinator.advance(frame())
    assert encounter.coordinator.active
    return update


@pytest.mark.parametrize(
    "case",
    [
        "response",
        "other_server",
        "dead",
        "absent",
        "party",
        "unknown_party",
        "outside_camp",
        "wrong_kind",
        "missing_key",
        "contradictory_kind",
        "nonattackable",
    ],
)
def test_resolver_rejects_unqualified_intent_or_current_identity(encounter, case):
    saved, observation, camp = encounter.store.snapshot(), frame(), None
    if case in ("response", "other_server"):
        selected = saved.entries[0]
        if case == "response":
            selected = replace(selected, source="response")
        else:
            identity = replace(selected.player_identity, server="another server")
            selected = replace(selected, player_identity=identity, entry_id=identity.entry_id)
        saved = replace(saved, entries=(selected,))
    elif case in ("dead", "absent", "party"):
        observation = frame(**{case: True})
    elif case == "unknown_party":
        observation = replace(
            observation,
            authority_snapshot=replace(
                observation.authority_snapshot,
                party_complete=False,
            ),
        )
    elif case == "outside_camp":
        camp = PvECampLease(0, 0, 4, 1)
    elif case in ("contradictory_kind", "nonattackable"):
        authority = observation.authority_snapshot
        changed = replace(
            authority.characters[0],
            **(
                {"character_kind": PvETargetCharacterKind.NPC}
                if case == "contradictory_kind"
                else {"attackable": False}
            ),
        )
        observation = replace(
            observation,
            authority_snapshot=replace(
                authority,
                characters=(changed,),
            ),
        )
    else:
        character = observation.population.characters[0]
        character = replace(
            character,
            **(
                {"character_kind": NativeCharacterKind.NPC}
                if case == "wrong_kind"
                else {"object_key": None}
            ),
        )
        population = replace(observation.population, characters=(character,))
        # Missing exact keys cannot form the coherent authority frame at all.
        if case == "missing_key":
            observation = replace(observation, population=population, authority_snapshot=None)
        else:
            observation = replace(observation, population=population)
    assert not listed_targets(saved, OWNER, observation, camp)


def test_exact_key_candidate_does_not_interpret_opaque_token_or_use_observed_name(encounter):
    (candidate,) = listed_targets(encounter.store.snapshot(), OWNER, frame(), None)
    assert candidate.character.object_key == TARGET
    assert candidate.character.token == "opaque-player-token"
    assert candidate.entry.player_identity.name == "Enemy"


def test_initial_listed_action_is_one_explicit_submit_without_pause(encounter):
    update = start(encounter)
    assert encounter.calls == [Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT, Verb.SUBMIT]
    assert encounter.events == ["open_owner", "register", "attach_context", "submit"]
    assert update.receipt.flags & OUTBOUND_QUEUED
    assert encounter.bindings[encounter.commands[-1].context_id].target_key == (
        TARGET.object_type,
        TARGET.object_uuid,
    )


def test_unknown_submission_polls_exact_action_without_resubmission(encounter):
    encounter.state.failure = NativeActionChannelTimeout("unknown native entry")
    assert not start(encounter).recovered
    original = encounter.commands[-1]
    encounter.state.failure = None
    assert encounter.coordinator.prepare(frame(100), None)
    update = encounter.coordinator.advance(frame(100))
    assert update.receipt.flags & OUTBOUND_QUEUED
    assert encounter.calls == [
        Verb.OPEN_OWNER,
        Verb.ATTACH_CONTEXT,
        Verb.SUBMIT,
        Verb.ACTION_STATUS,
    ]
    assert encounter.commands[-1] is original and len(encounter.tickets) == 1
    assert encounter.coordinator.finish("operator stop").recovered
    assert encounter.calls[-1] is Verb.STOP_CONTEXT
    assert encounter.events[-3:] == ["revoke", "stop_context", "close"]


@pytest.mark.parametrize(
    "invalidation", ["list_edit", "party", "dead", "absent", "camp", "identity", "local", "timeout"]
)
def test_invalidation_revokes_shared_ticket_before_cleanup(encounter, invalidation):
    start(encounter)
    observation, camp = frame(100), None
    if invalidation == "list_edit":
        encounter.store.clear()
    elif invalidation in ("party", "dead", "absent"):
        observation = frame(100, **{invalidation: True})
    elif invalidation == "camp":
        camp = PvECampLease(0, 0, 4, 1)
    elif invalidation == "local":
        observation = frame(100, local=NativeObjectKey(91, 99))
    elif invalidation == "identity":
        encounter.current.failure = True
    else:
        observation = frame(30_000)
    encounter.state.stop_pending = True
    assert encounter.coordinator.prepare(observation, camp)
    update = encounter.coordinator.advance(observation)
    assert not update.recovered and encounter.coordinator.active
    assert "close" not in encounter.events
    assert encounter.events[-2:] == ["revoke", "stop_context"]
    encounter.state.stop_pending = False
    assert encounter.coordinator.finish("stop").recovered
    assert not encounter.combat.active and not encounter.coordinator.active


def test_unknown_status_cannot_release_shared_ticket(encounter):
    start(encounter)
    encounter.state.response = "blocked"
    assert not encounter.coordinator.advance(frame(100)).recovered
    update = encounter.coordinator.finish("stop")
    assert update.terminal_reason == "listed_combat_cleanup_unconfirmed"
    assert encounter.coordinator.active and encounter.combat.active
    assert "close" not in encounter.events


def test_actual_scene_retirement_terminates_instead_of_resuming(encounter):
    start(encounter)
    encounter.state.response = "retired"
    encounter.coordinator.advance(frame(100))
    update = encounter.coordinator.advance(frame(200))
    assert update.terminal_reason == "listed_combat_scene_retired"
    assert not update.recovered and not encounter.combat.active


def test_prepare_failure_discards_unadmitted_candidate(encounter):
    assert encounter.coordinator.prepare(frame(), None)
    encounter.current.failure = True
    with pytest.raises(RuntimeError, match="character changed"):
        encounter.coordinator.prepare(frame(100), None)
    encounter.current.failure = False
    with pytest.raises(RuntimeError, match="prepared"):
        encounter.coordinator.advance(frame(100))
    assert not encounter.commands and not encounter.tickets


def test_admission_failure_preserves_bounded_error_and_requires_shared_cleanup(encounter):
    encounter.state.register_failure = ValueError("race\n" + "x" * 300)
    assert encounter.coordinator.prepare(frame(), None)
    with pytest.raises(ListedCombatInterruptionError) as caught:
        encounter.coordinator.advance(frame())
    assert caught.value.stage == "native_admission"
    assert caught.value.cause_type == "ValueError"
    assert "\n" not in str(caught.value) and len(caught.value.cause_detail) == 160
    assert encounter.calls == [Verb.OPEN_OWNER] and not encounter.tickets
    assert encounter.coordinator.finish("admission failure").recovered


@pytest.mark.parametrize("detail", [None, "combat_v2:rejected", "combat_v2:cleanup_confirmed"])
def test_diagnostic_text_cannot_override_correlated_state(encounter, detail):
    encounter.state.native_detail = detail
    update = start(encounter)
    assert update.native_detail == detail and not update.recovered
    assert update.receipt.context_phase is Phase.BOUND
    encounter.state.response = "blocked"
    stopped = encounter.coordinator.finish("stop")
    assert stopped.terminal_reason == "listed_combat_cleanup_unconfirmed"
    assert not stopped.recovered and encounter.coordinator.active


def test_transport_failure_does_not_replay_old_diagnostic(encounter):
    encounter.state.native_detail = "native queue admitted"
    start(encounter)
    encounter.state.failure = NativeActionChannelTimeout("ambiguous status")
    update = encounter.coordinator.advance(frame(100))
    assert update.receipt is None
    assert update.native_detail != "native queue admitted"
    assert not update.recovered and encounter.coordinator.active


def test_ticket_release_failure_preserves_native_closure_but_not_local_recovery(encounter):
    start(encounter)

    def failed_close(**kwargs):
        raise OSError("ticket close unavailable")

    encounter.tickets[0].close = failed_close
    update = encounter.coordinator.finish("stop")
    assert context_cleanup_confirmed(update.receipt)
    assert not update.recovered and encounter.coordinator.active
    assert update.terminal_reason == "listed_combat_cleanup_unconfirmed"


def test_unavailable_capability_fails_before_authority_registration(encounter):
    encounter.state.unavailable = True
    with pytest.raises(NativeActionChannelUnavailable):
        NativeActorCoordinator(
            session=encounter.session,
            grant=encounter.owner.grant,
            population=encounter.owner.population,
            character_session=encounter.owner.character_session,
            store=encounter.store,
        )
    assert not encounter.tickets and not encounter.commands


def test_rejected_revision_is_quarantined_until_absence_or_new_saved_revision(encounter):
    start(encounter)
    encounter.coordinator.finish("done")
    assert not encounter.coordinator.prepare(frame(100), None)
    assert not encounter.coordinator.prepare(frame(200, absent=True), None)
    assert encounter.coordinator.prepare(frame(300), None)


def test_unknown_trace_fields_remain_unknown():
    update = ListedCombatUpdate("unknown", None).as_dict()
    assert all(
        update[name] is None
        for name in ("flags", "outbound_queued", "mode", "action_state", "combat_target_present")
    )
    assert not update["cleanup_confirmed"]


def test_external_recovery_gates_list_admission_through_resources_and_complete_camp_return():
    controller = PvEController(
        PvEControllerConfig(
            continuous=True,
            camp_radius=100,
            camp_return_radius=10,
            camp_return_trigger_radius=20,
            minimum_recovery_health_fraction=0.9,
            minimum_recovery_mana_fraction=0.9,
            minimum_recovery_stamina_fraction=0.9,
        )
    )
    controller.step(frame(), external_combat=True)
    displaced = replace(frame(100), player_position=NativePlayerPositionObservation(40, 0, 0))
    controller.resume_after_external_combat(displaced)
    low = replace(displaced, now_ms=200, player=replace(displaced.player, current_mana=60))
    decision = controller.step(low)
    assert decision.phase is PvEPhase.RECOVERING and decision.intent is None
    assert not decision.return_to_camp and not controller.can_start_external_combat(low)
    decision = controller.step(replace(displaced, now_ms=300))
    assert decision.return_to_camp and decision.intent is None
    # Crossing the trigger boundary does not finish an already required return.
    close = replace(frame(400), player_position=NativePlayerPositionObservation(15, 0, 0))
    assert controller.step(close).return_to_camp
    assert not controller.can_start_external_combat(close)
    home = frame(500)
    decision = controller.step(home)
    assert decision.phase is PvEPhase.SEEKING and decision.intent is None
    assert controller.can_start_external_combat(frame(600))
    assert controller.kills == 0


def public_runner(encounter, *, observation=frame, after_sleep=None, config=None, journal=None):
    """Exercise public coherent-reader composition and the real native owner."""
    clock = SimpleNamespace(now=0.0)
    stop = EventEmergencyStop()
    controller = PvEController(config or PvEControllerConfig(continuous=True, camp_radius=100))

    def current():
        return observation(round(clock.now * 1000))

    def source(field):
        return SimpleNamespace(process_id=1234, observe=lambda: getattr(current(), field))

    def sleep(seconds):
        clock.now += seconds
        if after_sleep is not None:
            after_sleep(round(clock.now * 1000), stop)
        if clock.now >= 1.0:
            stop.trip()

    runner = PvERunner(
        controller=controller,
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
        dispatcher=encounter.combat,
        combat_cleanup=encounter.combat,
        listed_combat=encounter.coordinator,
        stop_signal=stop,
        clock=lambda: clock.now,
        sleeper=sleep,
        poll_interval_ms=100,
        trace_sink=None if journal is None else journal.append,
    )
    return runner, controller


@pytest.mark.parametrize("cause", ["operator", "low_health"])
def test_public_runner_terminal_cleanup_uses_shared_owner(encounter, cause):
    def observe(now):
        result = frame(now)
        if cause == "low_health" and now >= 100:
            result = replace(result, player=replace(result.player, current_health=1))
        return result

    def sleep(now, stop):
        if cause == "operator" and now >= 100:
            stop.trip()

    runner, _ = public_runner(encounter, observation=observe, after_sleep=sleep)
    result = runner.run()
    assert result.final_phase is PvEPhase.STOPPED
    assert result.kills == 0
    assert encounter.calls == [Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT, Verb.SUBMIT, Verb.STOP_CONTEXT]
    assert encounter.events[-3:] == ["revoke", "stop_context", "close"]
    assert not encounter.combat.active and not encounter.coordinator.active
    assert result.trace[-1].listed_combat.recovered
    assert context_cleanup_confirmed(result.trace[-1].listed_combat.receipt)


def test_public_runner_keyboard_interrupt_cleans_before_outer_session_exit(encounter):
    def interrupt(now, stop):
        raise KeyboardInterrupt

    runner, _ = public_runner(encounter, after_sleep=interrupt)
    with pytest.raises(KeyboardInterrupt):
        try:
            runner.run()
        finally:
            encounter.events.append("outer_session_exit")
    assert encounter.events[-4:] == ["revoke", "stop_context", "close", "outer_session_exit"]
    assert not encounter.combat.active and not encounter.coordinator.active


@pytest.mark.parametrize("resource", ["health", "mana", "stamina"])
def test_public_recovery_waits_for_fresh_resources_before_native_npc_action(encounter, resource):
    encounter.state.close_on_status = True
    npc_key = NativeObjectKey(92, 37)

    def observe(now):
        result = frame(now)
        if now >= 200:
            npc = replace(
                result.population.characters[0],
                token="opaque-npc-token",
                object_key=npc_key,
                character_kind=NativeCharacterKind.NPC,
            )
            result = replace(
                result,
                population=replace(result.population, characters=(npc,)),
                authority_snapshot=None,
            )
            if now < 500:
                result = replace(
                    result, player=replace(result.player, **{f"current_{resource}": 70})
                )
        return result

    journal = []
    runner, controller = public_runner(
        encounter,
        observation=observe,
        journal=journal,
        config=PvEControllerConfig(
            continuous=True,
            camp_radius=100,
            minimum_recovery_health_fraction=0.9,
            minimum_recovery_mana_fraction=0.9,
            minimum_recovery_stamina_fraction=0.9,
        ),
    )
    result = runner.run()
    submits = [
        c for c, v in zip(encounter.commands, encounter.calls, strict=True) if v is Verb.SUBMIT
    ]
    assert len(submits) == 2, result.terminal_reason
    assert encounter.bindings[submits[0].context_id].authority is Authority.MANUAL_PLAYER
    assert encounter.bindings[submits[1].context_id].authority is Authority.NPC
    assert submits[0].context_id < submits[1].context_id
    assert encounter.events.index("close") < encounter.events.index("register_npc")
    ordinary = [step for step in journal if step.native_combat is not None]
    assert ordinary and ordinary[0].decision.now_ms >= 600
    assert ordinary[0].native_combat.receipt.flags & OUTBOUND_QUEUED
    assert not any(step.native_combat for step in journal if step.decision.now_ms < 500)
    assert controller.kills == result.kills == 0
    assert not encounter.combat.active


def test_public_journal_preserves_queued_history_and_confirmed_closure(encounter):
    encounter.state.response = "closed"
    journal = []
    runner, _ = public_runner(encounter, journal=journal)
    runner.run()
    first = next(step.listed_combat for step in journal if step.listed_combat is not None)
    assert first.receipt.context_phase is Phase.CLOSED
    assert first.receipt.flags & OUTBOUND_QUEUED
    assert first.as_dict()["outbound_queued"] is True
    assert any(step.listed_combat and step.listed_combat.recovered for step in journal)
    assert encounter.calls == [Verb.OPEN_OWNER, Verb.ATTACH_CONTEXT, Verb.SUBMIT, Verb.STOP_CONTEXT]
    assert not encounter.combat.active


def test_public_admission_failure_is_terminal_without_ordinary_native_action(encounter):
    encounter.state.register_failure = ValueError("saved authority changed")
    runner, _ = public_runner(encounter)
    result = runner.run()
    assert result.final_phase is PvEPhase.STOPPED
    assert "ListedCombatInterruptionError" in result.terminal_reason
    assert encounter.calls == [Verb.OPEN_OWNER]
    assert not encounter.combat.active and not encounter.coordinator.active
