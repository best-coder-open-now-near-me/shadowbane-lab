"""Manual-list selection and transaction ownership across production boundaries."""

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_combat_fence import LOCAL, OWNER, TARGET, entry, store_at
from test_combat_receipt import receipt
from test_combat_wire import fixture

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelTimeout,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.combat_wire import LOCAL_CANCELLED, Outcome, Phase, Verb
from shadowbane_lab.client_extension.movement_session import NativeMovementGrant
from shadowbane_lab.client_input import EventEmergencyStop
from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_group import (
    NativeGroupMemberObservation,
    NativeGroupObservation,
)
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvERunner
from shadowbane_lab.pve.authority import PvETargetCharacterKind
from shadowbane_lab.pve.authority_snapshot import build_native_party_authority_snapshot
from shadowbane_lab.pve.listed_combat import ListedCombatCoordinator
from shadowbane_lab.pve.listed_target import listed_targets
from shadowbane_lab.pve.model import PvECampLease, PvEObservation, PvEPhase


def frame(now=0, *, dead=False, absent=False, party=False, lt=5, local=LOCAL):
    character = NativeCharacterObservation(
        "opaque-player-token", 0 if dead else 100, 100, lt, 0, 0,
        False, False, False, False, False, object_key=TARGET,
        character_kind=NativeCharacterKind.PLAYER,
    )
    population = NativeCharacterPopulationObservation(
        () if absent else (character,), None, None, 1, 0, local,
    )
    members = () if not party else tuple(
        NativeGroupMemberObservation(
            "untrusted name", "", key.object_type, key.object_uuid,
            100, 100, 100, 0, 0, 0, 0, False,
        ) for key in (local, TARGET)
    )
    authority = build_native_party_authority_snapshot(
        population, NativeGroupObservation(False, False, members),
        revision=1, party_group_id="party",
    )
    return PvEObservation(
        now, NativeTargetHealthObservation(False),
        NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100),
        player_position=NativePlayerPositionObservation(0, 0, 0),
        target_position=NativeTargetPositionObservation(False),
        population=population, authority_snapshot=authority,
    )


@pytest.fixture
def encounter(tmp_path, monkeypatch):
    store = store_at(tmp_path)
    command = fixture()
    command = replace(command, binding=replace(command.binding, revision=1))
    grant = NativeMovementGrant(
        NativeClientProcessIdentity(command.binding.client_pid, command.binding.client_creation),
        command.window, command.grant, command.host, "acquisition",
    )
    events, calls, tickets = [], [], []

    class Ticket:
        def revoke(self, **kwargs):
            events.append("revoke")

        def close(self, **kwargs):
            events.append("close")

    def register(entry_id, **kwargs):
        assert entry_id == entry().entry_id
        assert kwargs["expected_revision"] == store.snapshot().revision
        assert kwargs["grant"] is grant.ownership
        assert kwargs["local_key"] == LOCAL
        ticket = Ticket()
        tickets.append(ticket)
        events.append("register")
        return ticket, command

    monkeypatch.setattr(store, "register_combat_admission", register)

    def for_command(value):
        return replace(value, revision=command.binding.revision,
                       binding_digest=hashlib.sha256(command.binding.encode()).digest())

    state = SimpleNamespace(failure=None, reply=for_command(receipt()))

    def combat(owner, verb, payload):
        assert owner is grant and payload is command
        calls.append(verb)
        events.append(verb.name.lower())
        if state.failure:
            raise state.failure
        return state.reply

    current = SimpleNamespace(failure=False)

    def require_current():
        if current.failure:
            raise RuntimeError("character changed")

    coordinator = ListedCombatCoordinator(
        store=store, session=SimpleNamespace(combat=combat), grant=grant,
        require_current=require_current,
    )
    cancelled = for_command(replace(receipt(), outcome=Outcome.LOCAL_CANCELLED,
                                    flags=LOCAL_CANCELLED, phase=Phase.IDLE))
    return SimpleNamespace(store=store, coordinator=coordinator, state=state,
                           current=current, calls=calls, events=events, tickets=tickets,
                           cancelled=cancelled, command=command)


def start(encounter):
    assert encounter.coordinator.prepare(frame(), None)
    update = encounter.coordinator.advance(frame())
    assert encounter.coordinator.active
    return update


@pytest.mark.parametrize("case", ["response", "other_server", "dead", "absent", "party",
                                  "unknown_party", "outside_camp", "wrong_kind", "missing_key",
                                  "contradictory_kind", "nonattackable"])
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
        observation = replace(observation, authority_snapshot=replace(
            observation.authority_snapshot, party_complete=False,
        ))
    elif case == "outside_camp":
        camp = PvECampLease(0, 0, 4, 1)
    elif case in ("contradictory_kind", "nonattackable"):
        authority = observation.authority_snapshot
        changed = replace(authority.characters[0], **(
            {"character_kind": PvETargetCharacterKind.NPC}
            if case == "contradictory_kind" else {"attackable": False}
        ))
        observation = replace(observation, authority_snapshot=replace(
            authority, characters=(changed,),
        ))
    else:
        character = observation.population.characters[0]
        character = replace(character, **({"character_kind": NativeCharacterKind.NPC}
                                          if case == "wrong_kind" else {"object_key": None}))
        population = replace(observation.population, characters=(character,))
        # Missing exact keys cannot form the coherent authority frame at all.
        if case == "missing_key":
            observation = replace(observation, population=population, authority_snapshot=None)
        else:
            observation = replace(observation, population=population)
    assert not listed_targets(saved, OWNER, observation, camp)


def test_exact_key_candidate_does_not_interpret_opaque_token_or_use_observed_name(encounter):
    candidate, = listed_targets(encounter.store.snapshot(), OWNER, frame(), None)
    assert candidate.character.object_key == TARGET
    assert candidate.character.token == "opaque-player-token"
    assert candidate.entry.player_identity.name == "Enemy"


def test_uncertain_start_revokes_then_cancels_same_command_without_retry(encounter):
    encounter.state.failure = NativeActionChannelTimeout("unknown entry")
    update = start(encounter)
    assert not update.recovered
    assert encounter.calls == [Verb.START]
    encounter.state.failure = None
    encounter.state.reply = encounter.cancelled
    assert encounter.coordinator.prepare(frame(100), None)
    update = encounter.coordinator.advance(frame(100))
    assert update.recovered and not encounter.coordinator.active
    assert encounter.events == ["register", "start", "revoke", "cancel", "close"]
    assert len(encounter.tickets) == 1
    assert not encounter.coordinator.prepare(frame(200), None)


@pytest.mark.parametrize("invalidation", ["list_edit", "party", "dead", "absent",
                                          "camp", "identity", "timeout"])
def test_active_invalidation_keeps_ticket_until_native_cleanup(encounter, invalidation):
    start(encounter)
    observation, camp = frame(100), None
    if invalidation == "list_edit":
        encounter.store.clear()
    elif invalidation in ("party", "dead", "absent"):
        observation = frame(100, **{invalidation: True})
    elif invalidation == "camp":
        camp = PvECampLease(0, 0, 4, 1)
    elif invalidation == "identity":
        encounter.current.failure = True
    else:
        observation = frame(30_000)
    encounter.state.reply = replace(encounter.state.reply, outcome=Outcome.PENDING,
                                    phase=Phase.CANCELLING)
    assert encounter.coordinator.prepare(observation, camp)
    update = encounter.coordinator.advance(observation)
    assert not update.recovered and encounter.coordinator.active
    assert "close" not in encounter.events
    assert encounter.calls == [Verb.START, Verb.CANCEL]
    encounter.state.reply = encounter.cancelled
    update = encounter.coordinator.finish("run stopped")
    assert update.recovered and not encounter.coordinator.active


def test_unknown_native_status_cannot_resume_or_release_ticket(encounter):
    start(encounter)
    encounter.state.reply = replace(encounter.state.reply, outcome=Outcome.UNAVAILABLE,
                                    phase=Phase.BLOCKED)
    encounter.coordinator.prepare(frame(100), None)
    assert not encounter.coordinator.advance(frame(100)).recovered
    update = encounter.coordinator.finish("stop")
    assert update.terminal_reason == "listed_combat_cleanup_unconfirmed"
    assert encounter.coordinator.active and "close" not in encounter.events
    assert encounter.calls == [Verb.START, Verb.STATUS, Verb.CANCEL, Verb.CANCEL, Verb.CANCEL]


def test_scene_retirement_releases_old_ticket_but_never_resumes_same_run(encounter):
    start(encounter)
    encounter.state.reply = replace(encounter.state.reply, outcome=Outcome.STALE,
                                    flags=0, phase=Phase.RETIRED)
    encounter.coordinator.prepare(frame(100), None)
    update = encounter.coordinator.advance(frame(100))
    assert update.terminal_reason == "listed_combat_scene_retired"
    assert not update.recovered and not encounter.coordinator.active


def test_inactive_failed_prepare_discards_previous_provisional_candidate(encounter):
    assert encounter.coordinator.prepare(frame(), None)
    encounter.current.failure = True
    with pytest.raises(RuntimeError, match="character changed"):
        encounter.coordinator.prepare(frame(100), None)
    encounter.current.failure = False
    with pytest.raises(RuntimeError, match="prepared intent"):
        encounter.coordinator.advance(frame(100))
    assert not encounter.calls and not encounter.tickets


def run_public(encounter, *, safety_stop=False, recover=False, interrupt=False, depleted=None):
    stop = EventEmergencyStop()
    state = SimpleNamespace(now=0.0, dispatched=[])
    original = encounter.coordinator.session.combat

    def combat(grant, verb, command):
        if verb is Verb.CANCEL or (recover and verb is Verb.STATUS):
            encounter.state.reply = encounter.cancelled
        return original(grant, verb, command)

    encounter.coordinator.session.combat = combat

    def observed():
        observation = frame(round(state.now * 1000))
        if safety_stop and state.now >= 0.1:
            observation = replace(observation, player=replace(observation.player, current_health=1))
        if depleted is not None and 0.1 <= state.now < 0.4:
            observation = replace(observation, player=replace(observation.player, **{depleted: 60}))
        return observation

    class Reader:
        process_id = encounter.command.binding.client_pid

        def __init__(self, field):
            self.field = field

        def observe(self):
            return getattr(observed(), self.field)

    class GroupReader:
        process_id = encounter.command.binding.client_pid

        def observe(self):
            return NativeGroupObservation(False, False, ())

    class Logs:
        def read_new_entries(self):
            return ()

    class Dispatcher:
        def dispatch(self, intent, *, sequence):
            # Recovery is allowed only after the immutable transaction is closed.
            assert not encounter.coordinator.active
            assert "close" in encounter.events
            state.dispatched.append(intent)
            stop.trip()
            return DispatchResult("test", str(sequence), True)

    def sleep(seconds):
        state.now += seconds
        if interrupt:
            raise KeyboardInterrupt()
        if state.now >= 0.3 and not recover:
            stop.trip()
        assert state.now < 1, "runner did not terminate"

    runner = PvERunner(
        controller=PvEController(PvEControllerConfig(
            minimum_recovery_health_fraction=0.9, minimum_recovery_mana_fraction=0.9,
            minimum_recovery_stamina_fraction=0.9,
        )),
        health_reader=Reader("target"), player_vitals_reader=Reader("player"),
        player_position_reader=Reader("player_position"),
        target_position_reader=Reader("target_position"), population_reader=Reader("population"),
        group_reader=GroupReader(), party_group_id="party", combat_log_reader=Logs(),
        dispatcher=Dispatcher(), stop_signal=stop, listed_combat=encounter.coordinator,
        clock=lambda: state.now, sleeper=sleep,
    )
    return runner, state


@pytest.mark.parametrize("safety_stop", [False, True])
def test_public_runner_stop_holds_ordinary_input_and_confirms_cleanup_in_trace(
    encounter, safety_stop,
):
    runner, state = run_public(encounter, safety_stop=safety_stop)
    result = runner.run()
    assert result.terminal_reason == (
        "player_health_safety_threshold" if safety_stop else "emergency_stop"
    )
    assert result.kills == 0 and not state.dispatched
    assert encounter.calls[0] is Verb.START and encounter.calls[-1] is Verb.CANCEL
    assert not encounter.coordinator.active
    assert result.trace[-1].as_dict()["listed_combat"]["cleanup_confirmed"]


def test_public_runner_recovers_on_fresh_frame_after_confirmed_local_cancellation(encounter):
    runner, state = run_public(encounter, recover=True)
    result = runner.run()
    assert result.terminal_reason == "emergency_stop" and result.kills == 0
    assert len(state.dispatched) == 1
    assert encounter.calls == [Verb.START, Verb.STATUS]
    listed = [step for step in result.trace if step.listed_combat is not None]
    assert listed[-1].listed_combat.recovered
    assert listed[-1].decision.now_ms < next(
        step.decision.now_ms for step in result.trace if step.input_accepted
    )


def test_public_runner_unwind_cancels_before_outer_session_can_close(encounter):
    runner, _ = run_public(encounter, interrupt=True)
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert encounter.calls == [Verb.START, Verb.CANCEL]
    assert not encounter.coordinator.active and encounter.events[-1] == "close"


@pytest.mark.parametrize("depleted", ["current_health", "current_mana", "current_stamina"])
def test_public_runner_waits_for_resource_recovery_after_confirmed_cleanup(encounter, depleted):
    runner, state = run_public(encounter, recover=True, depleted=depleted)
    result = runner.run()
    assert result.kills == 0 and len(state.dispatched) == 1
    assert encounter.calls == [Verb.START, Verb.STATUS]
    waiting = [step for step in result.trace if step.decision.phase is PvEPhase.RECOVERING]
    assert waiting and all(step.decision.intent is None for step in waiting)
    assert next(step.decision.now_ms for step in result.trace if step.input_accepted) >= 500


def test_external_recovery_gates_list_admission_through_resources_and_complete_camp_return():
    controller = PvEController(PvEControllerConfig(
        continuous=True, camp_radius=100, camp_return_radius=10, camp_return_trigger_radius=20,
        minimum_recovery_health_fraction=0.9, minimum_recovery_mana_fraction=0.9,
        minimum_recovery_stamina_fraction=0.9,
    ))
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
