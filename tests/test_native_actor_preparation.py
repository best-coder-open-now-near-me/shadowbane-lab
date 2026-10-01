from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_listed_combat import encounter as listed_fixture
from test_native_actor_coordinator import reply
from test_native_actor_coordinator import setup as actor_fixture

from shadowbane_lab.client_extension import actor_publication as publication
from shadowbane_lab.client_extension.actor_action_wire import (
    APPLICATION_PENDING,
    Application,
    Entry,
    LocalSettlement,
    Outcome,
    Receipt,
    Verb,
)
from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
from shadowbane_lab.pve.preparation import PreparationAction

setup = actor_fixture
listed_encounter = listed_fixture


def configure(owner, session, monkeypatch):
    settings = BuffSettings(
        True,
        (
            BuffGroup(
                "concoction",
                (BuffAction(PreparationAction("potion", item_template=(980066, 0)), 429021400),),
            ),
            BuffGroup(
                "precision",
                (BuffAction(PreparationAction("precision", power_id=429545819), 429545819),),
            ),
        ),
    )
    monkeypatch.setattr(
        "shadowbane_lab.client_extension.actor_selector_manifest.PublishedManifest", Mock()
    )
    owner.publication_reader = Mock()
    owner.configure_preparation(settings)
    ident = publication.Identity(
        owner.parent.client_pid,
        owner.parent.client_creation,
        b"l" * 16,
        owner.manifest.digest,
        owner.parent.actor_key,
        owner.parent.actor_hint,
        owner.parent.scene,
    )
    facts = []
    for selector in owner.manifest.selectors:
        item = selector.kind == 4
        facts.append(
            publication.ActionFacts(
                selector,
                40,
                0,
                2,
                0,
                3,
                publication.Coverage.MISSING,
                publication.Readiness.READY,
                (),
                (5802955, 30) if item else (0, 0),
                (980066, 0) if item else (0, 0),
                0x12500000 if item else 0,
                0x12600000 if item else 0,
                1 if item else 0,
                8 if item else 0,
                10 if item else 0,
            )
        )
    pub = publication.Publication(
        ident, 2, 1, b"s" * 16, 10, 1, 0, True, 1, True, (), tuple(facts), ()
    )
    owner.publication_reader.read.return_value = pub

    def send(g, v, c, **kw):
        if v in (Verb.REGISTER_SELECTORS, Verb.OBSERVE_ACTOR):
            r = Receipt(
                c.request,
                c.host,
                c.window,
                Outcome.OBSERVED,
                0,
                None,
                None,
                None,
                c.digest,
                v,
                c.action,
            )
            r.require_command(c, v)
            return SimpleNamespace(receipt=r, native_detail=None)
        result = reply(c, v)
        if c.action.value == 4:
            result.receipt = replace(
                result.receipt,
                flags=result.receipt.flags | APPLICATION_PENDING,
                application=Application.PENDING,
            )
            result.receipt.require_command(c, v)
        return result

    session.actor_action.side_effect = send
    return pub, send


def test_queued_potion_remote_pending_allows_ready_power_without_stop(setup, monkeypatch):
    owner, s, _, _, _ = setup
    pub, _ = configure(owner, s, monkeypatch)
    first = owner.preparation_step()
    assert first.acknowledgement.local_settled
    assert first.receipt.application is Application.PENDING
    owner.publication_reader.read.return_value = replace(pub, revision=2, snapshot_id=b"t" * 16)
    second = owner.preparation_step()
    assert second.acknowledgement.proposal.group_id == "precision"
    submitted = [c.args[2] for c in s.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert [c.action.value for c in submitted] == [4, 3]
    assert all(c.context_id is None for c in submitted)
    assert all(c.parent_id == owner.parent.owner_id for c in submitted)
    s.pause.assert_not_called()
    assert not any(
        c.args[1] in (Verb.STOP_CONTEXT, Verb.STOP_OWNER) for c in s.actor_action.call_args_list
    )


def test_imported_pending_history_survives_policy_reconstruction(setup, monkeypatch):
    owner, s, _, _, _ = setup
    pub, _ = configure(owner, s, monkeypatch)
    history = publication.Application(
        owner.manifest.group_digest(0), b"c" * 32, 1, 0, 2, 1, True, False
    )
    owner.publication_reader.read.return_value = replace(pub, applications=(history,))
    update = owner.preparation_step()
    assert update.acknowledgement.proposal.group_id == "precision"
    assert update.decision.groups[0].application_pending


def test_partial_potion_coverage_suppresses_whole_reapplication(setup, monkeypatch):
    owner, s, _, _, _ = setup
    pub, _ = configure(owner, s, monkeypatch)
    owner.publication_reader.read.return_value = replace(
        pub,
        actions=(replace(pub.actions[0], coverage=publication.Coverage.PARTIAL), pub.actions[1]),
    )
    assert owner.preparation_step().acknowledgement.proposal.group_id == "precision"


def test_unmatched_pending_history_blocks_without_relabeling(setup, monkeypatch):
    owner, s, _, _, _ = setup
    pub, _ = configure(owner, s, monkeypatch)
    history = publication.Application(b"x" * 32, b"c" * 32, 1, 0, 2, 1, True, False)
    owner.publication_reader.read.return_value = replace(pub, applications=(history,))
    with pytest.raises(publication.PublicationError, match="unmatched"):
        owner.preparation_step()
    assert all(c.args[1] is not Verb.SUBMIT for c in s.actor_action.call_args_list)


def test_one_buff_cannot_starve_same_new_combat_proposal(setup, monkeypatch):
    owner, s, _, o, p = setup
    pub, _ = configure(owner, s, monkeypatch)
    assert owner.preparation_step(p) is not None
    owner.publication_reader.read.return_value = replace(pub, revision=2, snapshot_id=b"t" * 16)
    assert owner.preparation_step(p) is None
    assert owner.advance_combat(p, o).acknowledgement.disposition.value == "queued"


def test_local_unsettled_never_uses_effect_presence_as_completion(setup, monkeypatch):
    owner, s, _, _, _ = setup
    pub, send = configure(owner, s, monkeypatch)

    def pending(g, v, c, **kw):
        result = send(g, v, c, **kw)
        if c.action.value == 4:
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        return result

    s.actor_action.side_effect = pending
    first = owner.preparation_step()
    assert first.receipt.entry is Entry.ENTERED and not first.acknowledgement.local_settled
    original = first.command
    owner.publication_reader.read.return_value = replace(
        pub,
        revision=2,
        snapshot_id=b"t" * 16,
        actions=(replace(pub.actions[0], coverage=publication.Coverage.PRESENT), pub.actions[1]),
    )
    second = owner.preparation_step()
    assert second.command is original and not second.acknowledgement.local_settled
    assert s.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scene", 999),
        ("actor_address", 0x12300100),
        ("actor_key", (7, 53)),
        ("process_creation", 999),
    ],
)
def test_publication_exact_parent_identity_checked(setup, monkeypatch, field, value):
    owner, s, _, _, _ = setup
    pub, _ = configure(owner, s, monkeypatch)
    owner.publication_reader.read.return_value = replace(
        pub, identity=replace(pub.identity, **{field: value})
    )
    with pytest.raises(publication.PublicationError, match="parent"):
        owner.preparation_step()
    assert all(c.args[1] is not Verb.SUBMIT for c in s.actor_action.call_args_list)


def test_public_runner_shared_owner_item_combat_power_death_and_exact_cleanup(setup, monkeypatch):
    from test_pve_native_proposals import character, observe

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.client_observation import NativeGroupObservation
    from shadowbane_lab.pve import PvERunner
    from shadowbane_lab.pve.model import PvEControllerConfig
    from shadowbane_lab.pve.native_combat import NativeCombatCoordinator
    from shadowbane_lab.pve.target_authority import PvEController

    owner, session, _, original, proposal = setup
    pub, send = configure(owner, session, monkeypatch)
    combat = NativeCombatCoordinator(owner=owner)
    stop, clock = EventEmergencyStop(), SimpleNamespace(now=0.0)
    target = replace(character(), object_key=proposal.target_key, token=proposal.target_token)
    state = {"power": False, "revision": 1}

    def publication_now():
        state["revision"] += 1
        return replace(
            pub, revision=state["revision"], snapshot_id=state["revision"].to_bytes(16, "big")
        )

    owner.publication_reader.read.side_effect = publication_now

    def current():
        observed_target = replace(target, current_health=0) if state["power"] else target
        value = observe(round(clock.now * 1000), characters=(observed_target,))
        return replace(
            value,
            population=replace(
                value.population,
                local_player_object_key=original.population.local_player_object_key,
            ),
        )

    def source(field):
        return SimpleNamespace(
            process_id=owner.parent.client_pid, observe=lambda: getattr(current(), field)
        )

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb is Verb.SUBMIT and command.power_id == 429545819:
            state["power"] = True
        return result

    session.actor_action.side_effect = response
    trace = []

    def record(step):
        trace.append(step)
        if step.combat_cleanup is not None and step.combat_cleanup.confirmed:
            stop.trip()

    def sleep(seconds):
        clock.now += seconds
        assert clock.now < 4, "shared owner did not complete bounded cleanup"

    runner = PvERunner(
        controller=PvEController(PvEControllerConfig()),
        health_reader=source("target"),
        player_vitals_reader=source("player"),
        player_position_reader=source("player_position"),
        target_position_reader=source("target_position"),
        population_reader=source("population"),
        player_action_reader=SimpleNamespace(
            process_id=owner.parent.client_pid, observe_player=lambda: current().player_action
        ),
        group_reader=SimpleNamespace(
            process_id=owner.parent.client_pid,
            observe=lambda: NativeGroupObservation(False, False, ()),
        ),
        party_group_id="party",
        dispatcher=combat,
        combat_cleanup=combat,
        actor_preparation=owner,
        stop_signal=stop,
        clock=lambda: clock.now,
        sleeper=sleep,
        trace_sink=record,
        poll_interval_ms=100,
    )
    result = runner.run()
    assert result.kills == 1 and not combat.active
    calls = session.actor_action.call_args_list
    submits = [c.args[2] for c in calls if c.args[1] is Verb.SUBMIT]
    assert [(c.action.value, c.power_id) for c in submits] == [(4, 0), (1, 0), (3, 429545819)]
    assert len({c.parent_id for c in submits}) == 1
    assert submits[0].context_id is None and submits[2].context_id is None
    assert submits[1].context_id is not None
    assert owner._opened and not owner._obligation.released
    assert owner.finish("runner_done")[0] and owner._obligation.released
    session.pause.assert_not_called()
    assert [
        step.as_dict()["preparation"]["group"] for step in trace if step.preparation is not None
    ] == ["concoction", "precision"]


def test_preparation_transport_uncertain_keeps_command_and_original_deadline(setup, monkeypatch):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    now = SimpleNamespace(value=10.0)
    session.cleanup.clock = lambda: now.value

    def uncertain(grant, verb, command, **kwargs):
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
            raise TimeoutError("lost receipt")
        return send(grant, verb, command, **kwargs)

    session.actor_action.side_effect = uncertain
    first = owner.preparation_step()
    command = owner._preparation_command
    assert first.acknowledgement.disposition.value == "uncertain"
    now.value = 14.99
    assert owner.preparation_step().acknowledgement.proposal == first.acknowledgement.proposal
    assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, command)
    now.value = 15.0
    with pytest.raises(RuntimeError, match="deadline"):
        owner.preparation_step()
    assert owner._closed and owner._obligation.released



def test_every_preparation_observation_refreshes_native_capture(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, send = configure(owner, session, monkeypatch)
    seen = []

    def refresh(grant, verb, command, **kwargs):
        if verb is Verb.OBSERVE_ACTOR:
            assert grant is None and command.grant is None and command.parent_id is None
            seen.append(command)
            if len(seen) == 2:
                owner.publication_reader.read.return_value = replace(
                    pub, revision=2, snapshot_id=b"t" * 16,
                    actions=tuple(replace(a, coverage=publication.Coverage.PRESENT,
                                          readiness=publication.Readiness.POWER_REUSE)
                                  for a in pub.actions))
        return send(grant, verb, command, **kwargs)

    session.actor_action.side_effect = refresh
    first, second = owner.observe_preparation(), owner.observe_preparation()
    assert first.publication_epoch == 1 and second.publication_epoch == 2
    assert all(x.state.value == "present" for x in second.coverage)
    assert all(x.state.value == "not_ready" for x in second.readiness)
    assert len(seen) == 2 and seen[0].request != seen[1].request
    assert all(x.manifest_digest == owner.manifest.digest for x in seen)


def test_unavailable_refresh_never_reuses_previous_complete_publication(setup, monkeypatch):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    assert owner.observe_preparation().complete
    owner.publication_reader.read.reset_mock()

    def unavailable(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb is Verb.OBSERVE_ACTOR:
            result.receipt = replace(result.receipt, outcome=Outcome.UNAVAILABLE)
        return result

    session.actor_action.side_effect = unavailable
    assert owner.preparation_step() is None
    owner.publication_reader.read.assert_not_called()
    assert not any(c.args[1] is Verb.SUBMIT for c in session.actor_action.call_args_list)


def test_open_latency_retains_exact_proposal_publication(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, send = configure(owner, session, monkeypatch)

    def slow_open(grant, verb, command, **kwargs):
        if verb is Verb.OPEN_OWNER:
            raise TimeoutError("open receipt delayed")
        return send(grant, verb, command, **kwargs)

    session.actor_action.side_effect = slow_open
    first = owner.preparation_step()
    owner.publication_reader.read.return_value = replace(pub, revision=2, snapshot_id=b"t" * 16)
    second = owner.preparation_step()
    assert second.acknowledgement.proposal == first.acknowledgement.proposal
    assert second.command.publication_revision == 1
    assert second.command.snapshot_id == pub.snapshot_id
    assert second.acknowledgement.local_settled
    assert [c.args[1] for c in session.actor_action.call_args_list].count(Verb.SUBMIT) == 1


def test_context_cleanup_preserves_actor_only_unsettled_action(setup, monkeypatch):
    owner, session, _, observation, proposal = setup
    _, send = configure(owner, session, monkeypatch)
    owner.advance_combat(proposal, observation)

    def pending(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action.value == 4:
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        return result

    session.actor_action.side_effect = pending
    first = owner.preparation_step()
    command = first.command
    assert command.context_id is None and not first.acknowledgement.local_settled
    assert owner.stop_context("target_dead")[0]
    assert owner._local_command is command
    assert not owner._local_ready()
    assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, command)



def test_public_runner_refreshes_buffs_during_listed_combat_after_health_checks(
    listed_encounter, monkeypatch,
):
    from test_listed_combat import frame

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.client_observation import NativeGroupObservation
    from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvERunner

    encounter = listed_encounter
    owner, session = encounter.owner, encounter.session
    session.actor_action = Mock()
    pub, send = configure(owner, session, monkeypatch)
    stop, clock = EventEmergencyStop(), SimpleNamespace(now=0.0)
    state = {"dead": False, "revision": 1}

    def publication_now():
        state["revision"] += 1
        return replace(pub, revision=state["revision"],
                       snapshot_id=state["revision"].to_bytes(16, "big"))

    owner.publication_reader.read.side_effect = publication_now

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb is Verb.SUBMIT and command.power_id == 429545819:
            state["dead"] = True
        return result

    session.actor_action.side_effect = response

    def current():
        return frame(round(clock.now * 1000), dead=state["dead"])

    def source(field):
        return SimpleNamespace(process_id=1234, observe=lambda: getattr(current(), field))

    def record(step):
        if step.listed_combat is not None and step.listed_combat.recovered:
            stop.trip()

    def sleep(seconds):
        clock.now += seconds
        assert clock.now < 3, "listed refresh did not reach normal cleanup"

    runner = PvERunner(
        controller=PvEController(PvEControllerConfig(continuous=True, camp_radius=100)),
        health_reader=source("target"), player_vitals_reader=source("player"),
        player_position_reader=source("player_position"),
        target_position_reader=source("target_position"), population_reader=source("population"),
        group_reader=SimpleNamespace(
            process_id=1234, observe=lambda: NativeGroupObservation(False, False, ())),
        party_group_id="party",
        player_action_reader=SimpleNamespace(
            process_id=1234, observe_player=lambda: current().player_action),
        dispatcher=encounter.combat, combat_cleanup=encounter.combat,
        listed_combat=encounter.coordinator, actor_preparation=owner,
        stop_signal=stop, clock=lambda: clock.now, sleeper=sleep, trace_sink=record,
    )
    result = runner.run()
    submitted = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert [(c.action.value, c.power_id) for c in submitted] == [(1, 0), (4, 0), (3, 429545819)]
    assert len({c.parent_id for c in submitted}) == 1
    assert not encounter.combat.active and owner._opened and not owner._obligation.released
    assert [x.preparation.acknowledgement.proposal.group_id for x in result.trace
            if x.preparation is not None] == ["concoction", "precision"]
    assert any(x.listed_combat is not None and x.listed_combat.recovered for x in result.trace)
    assert owner.finish("test_done")[0]



def test_native_unknown_publication_does_not_stop_combat_or_authorize_preparation(
    setup, monkeypatch,
):
    owner, session, _, observation, proposal = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.return_value = replace(
        pub, complete=False, unknown=1, actions=(), effects=(), applications=())
    assert owner.preparation_step(proposal) is None
    assert owner.advance_combat(proposal, observation).acknowledgement.disposition.value == "queued"
    submitted = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert len(submitted) == 1 and submitted[0].action.value == 1
