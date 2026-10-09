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
    Action,
    Application,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Receipt,
    Verb,
)
from shadowbane_lab.pve.buff_intent import BuffAction, BuffGroup, BuffSettings
from shadowbane_lab.pve.preparation import PreparationAction

setup = actor_fixture
listed_encounter = listed_fixture


def configure(owner, session, monkeypatch, settings=None):
    settings = settings or BuffSettings(
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
        ident,
        2,
        1,
        b"s" * 16,
        10,
        1,
        0,
        True,
        1,
        True,
        (),
        tuple(facts),
        (),
        1,
        publication.AdmissionBlock(0),
    )
    owner.publication_reader.read.return_value = pub
    capture = 0

    def read_capture():
        nonlocal capture
        capture += 2
        return replace(owner.publication_reader.read.return_value, sequence=capture)

    owner.publication_reader.read.side_effect = read_capture

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
            pub,
            sequence=state["revision"] * 2,
            revision=state["revision"],
            snapshot_id=state["revision"].to_bytes(16, "big"),
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


def test_preparation_transport_uncertain_keeps_command_and_response_deadline(setup, monkeypatch):
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
                    pub,
                    revision=2,
                    snapshot_id=b"t" * 16,
                    actions=tuple(
                        replace(
                            a,
                            coverage=publication.Coverage.PRESENT,
                            readiness=publication.Readiness.POWER_REUSE,
                        )
                        for a in pub.actions
                    ),
                )
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


@pytest.mark.parametrize("preexisting_pending_buff", [False, True])
def test_public_runner_refreshes_buffs_during_listed_combat_after_health_checks(
    listed_encounter,
    monkeypatch,
    preexisting_pending_buff,
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
        return replace(
            pub,
            sequence=state["revision"] * 2,
            revision=state["revision"],
            snapshot_id=state["revision"].to_bytes(16, "big"),
        )

    owner.publication_reader.read.side_effect = publication_now

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if preexisting_pending_buff and verb is Verb.SUBMIT and command.action is Action.USE_ITEM:
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        if verb is Verb.SUBMIT and command.power_id == 429545819:
            state["dead"] = True
        return result

    session.actor_action.side_effect = response
    if preexisting_pending_buff:
        first = owner.preparation_step()
        assert first.command.action is Action.USE_ITEM and not first.acknowledgement.local_settled

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
        actor_preparation=owner,
        stop_signal=stop,
        clock=lambda: clock.now,
        sleeper=sleep,
        trace_sink=record,
    )
    result = runner.run()
    submitted = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    expected = (
        [(4, 0), (1, 0), (3, 429545819)]
        if preexisting_pending_buff
        else [(1, 0), (4, 0), (3, 429545819)]
    )
    assert [(c.action.value, c.power_id) for c in submitted] == expected
    assert len({c.parent_id for c in submitted}) == 1
    assert not encounter.combat.active and owner._opened and not owner._obligation.released
    assert [
        x.preparation.acknowledgement.proposal.group_id
        for x in result.trace
        if x.preparation is not None
    ] == (["precision"] if preexisting_pending_buff else ["concoction", "precision"])
    assert owner._preparation_policy.pending_proposal is None
    assert any(x.listed_combat is not None and x.listed_combat.recovered for x in result.trace)
    assert owner.finish("test_done")[0]


def test_native_unknown_publication_does_not_stop_combat_or_authorize_preparation(
    setup,
    monkeypatch,
):
    owner, session, _, observation, proposal = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.return_value = replace(
        pub, complete=False, unknown=1, actions=(), effects=(), applications=()
    )
    assert owner.preparation_step(proposal) is None
    assert owner.advance_combat(proposal, observation).acknowledgement.disposition.value == "queued"
    submitted = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert len(submitted) == 1 and submitted[0].action.value == 1


def test_native_admission_blocks_do_not_open_owner_or_submit(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.return_value = replace(
        pub, admission_blocks=publication.AdmissionBlock.FOREIGN_TARGET
    )
    assert owner.preparation_step() is None
    assert all(
        c.args[1] in (Verb.REGISTER_SELECTORS, Verb.OBSERVE_ACTOR)
        for c in session.actor_action.call_args_list
    )


def test_native_journal_only_changes_cannot_resubmit_refused_buff(setup, monkeypatch):
    from shadowbane_lab.client_extension.actor_action_wire import Reason

    owner, session, _, _, _ = setup
    pub, send = configure(owner, session, monkeypatch)
    pub = replace(
        pub,
        actions=(replace(pub.actions[0], coverage=publication.Coverage.PRESENT), pub.actions[1]),
    )
    owner.publication_reader.read.return_value = pub

    def refuse(g, v, c, **kwargs):
        result = send(g, v, c, **kwargs)
        if v is Verb.SUBMIT:
            result.receipt = replace(
                result.receipt,
                outcome=Outcome.DEFERRED,
                reason=Reason.TARGET_OCCUPIED,
                entry=Entry.NEVER_ENTERED,
                local_settlement=LocalSettlement.SETTLED,
                flags=1,
                application=Application.NONE,
            )
            result.receipt.require_command(c, v)
        return result

    session.actor_action.side_effect = refuse
    first = owner.preparation_step()
    assert first.receipt.reason is Reason.TARGET_OCCUPIED
    assert first.as_dict()["reason"] == "target_occupied"
    for revision in range(2, 40):
        owner.publication_reader.read.return_value = replace(
            pub,
            revision=revision,
            snapshot_id=revision.to_bytes(16, "big"),
            applications=(
                publication.Application(
                    owner.manifest.group_digest(1), first.command.digest, 1, 0, 0, 0, True, False
                ),
            ),
        )
        assert owner.preparation_step() is None
    submits = [c for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert len(submits) == 1
    owner.publication_reader.read.return_value = replace(
        pub,
        revision=40,
        snapshot_id=b"b" * 16,
        admission_revision=2,
        admission_blocks=publication.AdmissionBlock.FOREIGN_TARGET,
    )
    assert owner.preparation_step() is None
    owner.publication_reader.read.return_value = replace(
        pub, revision=41, snapshot_id=b"c" * 16, admission_revision=3
    )
    next_update = owner.preparation_step()
    assert next_update.command.request != first.command.request
    assert next_update.command.parent_id == first.command.parent_id
    assert next_update.command.grant == first.command.grant
    assert len([c for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]) == 2


def test_public_runner_blocked_preparation_trace_does_not_gate_npc_attack(setup, monkeypatch):
    from test_pve_native_proposals import character, observe

    from shadowbane_lab.client_input import EventEmergencyStop
    from shadowbane_lab.client_observation import NativeGroupObservation
    from shadowbane_lab.pve import PvERunner
    from shadowbane_lab.pve.model import PvEControllerConfig
    from shadowbane_lab.pve.native_combat import NativeCombatCoordinator
    from shadowbane_lab.pve.target_authority import PvEController

    owner, session, _, original, proposal = setup
    pub, send = configure(owner, session, monkeypatch)
    pub = replace(pub, admission_blocks=publication.AdmissionBlock.FOREIGN_TARGET)
    combat = NativeCombatCoordinator(owner=owner)
    stop, clock = EventEmergencyStop(), SimpleNamespace(now=0.0)
    target = replace(character(), object_key=proposal.target_key, token=proposal.target_token)
    state = {"power": False, "revision": 1}

    def publication_now():
        state["revision"] += 1
        return replace(
            pub,
            sequence=state["revision"] * 2,
            revision=state["revision"],
            snapshot_id=state["revision"].to_bytes(16, "big"),
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
        if verb is Verb.SUBMIT and command.action is Action.ATTACK:
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
    assert [(c.action.value, c.power_id) for c in submits] == [(1, 0)]
    assert len({c.parent_id for c in submits}) == 1
    assert submits[0].context_id is not None
    assert owner._opened and not owner._obligation.released
    assert owner.finish("runner_done")[0] and owner._obligation.released
    session.pause.assert_not_called()
    statuses = [step.as_dict()["preparation"] for step in trace if step.preparation is not None]
    assert statuses and all(s["action"] is None for s in statuses)
    assert all(s["blockers"] == ["foreign_target"] for s in statuses)
    assert any(step.native_combat is not None and step.preparation is not None for step in trace)


@pytest.mark.parametrize(
    "values",
    [
        (0, 1, 8),
        (1, 0, 8),
        (True, 1, 8),
        (1, True, 8),
        (1, 1, False),
        (1, 1, 0),
        (1, 1, 64),
        (1, 1, -1),
    ],
)
def test_trace_only_status_rejects_missing_or_unknown_authority(values):
    from shadowbane_lab.pve.native_actor import NativePreparationStatus

    with pytest.raises(ValueError):
        NativePreparationStatus(*values)


@pytest.mark.parametrize("uncertain", [False, True])
def test_long_native_pending_uses_status_until_positive_settlement(setup, monkeypatch, uncertain):
    owner, session, _, _, combat = setup
    pub, send = configure(owner, session, monkeypatch)
    # Start with the actor power; an item effect pending remotely is independent.
    owner.publication_reader.read.return_value = replace(
        pub,
        actions=(replace(pub.actions[0], coverage=publication.Coverage.PRESENT), pub.actions[1]),
    )
    now = SimpleNamespace(value=10.0)
    session.cleanup.clock = lambda: now.value
    settled = False

    def native(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
            result.receipt = replace(
                result.receipt,
                local_settlement=LocalSettlement.SETTLED if settled else LocalSettlement.PENDING,
                outcome=Outcome.UNCERTAIN if uncertain else Outcome.CLIENT_OUTBOUND_QUEUED,
            )
        return result

    session.actor_action.side_effect = native
    first = owner.preparation_step(combat)
    command = first.command
    for timestamp in (14.0, 18.0, 28.0):
        now.value = timestamp
        update = owner.preparation_step(combat)
        assert update.command is command
        assert not update.acknowledgement.local_settled
        assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, command)
        assert owner._local_command is command and not owner._obligation.released
    settled = True
    now.value = 29.0
    final = owner.preparation_step(combat)
    assert final.command is command and final.acknowledgement.local_settled
    # The same NPC proposal is allowed immediately; no all-buffs gate or timer.
    assert owner.preparation_step(combat) is None
    assert owner._local_command is None
    assert [c.args[1] for c in session.actor_action.call_args_list].count(Verb.SUBMIT) == 1
    assert all(c.args[1] is not Verb.STOP_OWNER for c in session.actor_action.call_args_list)


@pytest.mark.parametrize(
    "failure", ["missing", "wrong_command", "wrong_verb", "stopping", "unknown"]
)
def test_only_live_correlated_pending_refreshes_response_watchdog(setup, monkeypatch, failure):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    now = SimpleNamespace(value=10.0)
    session.cleanup.clock = lambda: now.value
    failed = False

    def native(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
            if failed:
                if failure == "missing":
                    raise TimeoutError("lost status")
                if failure == "wrong_command":
                    result.receipt = replace(result.receipt, command_digest=b"x" * 32)
                elif failure == "wrong_verb":
                    result.receipt = replace(result.receipt, verb=Verb.SUBMIT)
                elif failure == "stopping":
                    result.receipt = replace(result.receipt, owner_phase=Phase.STOPPING)
                else:
                    result.receipt = replace(
                        result.receipt, local_settlement=LocalSettlement.UNKNOWN
                    )
        return result

    session.actor_action.side_effect = native
    first = owner.preparation_step()
    now.value = 14.0
    assert not owner.preparation_step().acknowledgement.local_settled
    failed = True
    now.value = 18.99
    assert not owner.preparation_step().acknowledgement.local_settled
    now.value = 19.0
    with pytest.raises(RuntimeError, match="status response deadline"):
        owner.preparation_step()
    actions = [
        c
        for c in session.actor_action.call_args_list
        if c.args[1] in (Verb.SUBMIT, Verb.ACTION_STATUS)
    ]
    assert [c.args[1] for c in actions] == [Verb.SUBMIT] + [Verb.ACTION_STATUS] * 3
    assert all(c.args[2] is first.command for c in actions)
    assert owner._closed and owner._obligation.released


def test_explicit_finish_cancels_long_pending_without_claiming_settlement(setup, monkeypatch):
    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    now = SimpleNamespace(value=10.0)
    session.cleanup.clock = lambda: now.value

    def native(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        return result

    session.actor_action.side_effect = native
    first = owner.preparation_step()
    now.value = 30.0
    update = owner.preparation_step()
    assert update.command is first.command and not update.acknowledgement.local_settled
    assert owner.finish("user_cancel")[0]
    assert owner._obligation.released
    assert [c.args[1] for c in session.actor_action.call_args_list].count(Verb.SUBMIT) == 1
    assert [c.args[1] for c in session.actor_action.call_args_list].count(Verb.STOP_OWNER) == 1


def test_unknown_item_resource_allows_independently_ready_power(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, _ = configure(owner, session, monkeypatch)
    item = replace(
        pub.actions[0],
        readiness=publication.Readiness.UNKNOWN,
        item_key=(0, 0),
        template_key=(0, 0),
        item_hint=0,
        template_hint=0,
        quantity=0,
        item_type=0,
        item_flags=0,
    )
    owner.publication_reader.read.return_value = replace(pub, actions=(item, pub.actions[1]))
    update = owner.preparation_step()
    assert update.acknowledgement.proposal.group_id == "precision"
    submits = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert len(submits) == 1 and submits[0].action is Action.SELF_POWER


def test_beorc_settled_at_revision17_continues_rat_and_stance_on_fresh_captures(setup, monkeypatch):
    owner, session, _, _, _ = setup
    settings = BuffSettings(
        True,
        tuple(
            BuffGroup(name, (BuffAction(PreparationAction(name, power_id=power), power),))
            for name, power in (("beorc", 429590426), ("rat", 429513599), ("stance", 676005819))
        ),
    )
    pub, send = configure(owner, session, monkeypatch, settings)
    owner.publication_reader.read.return_value = replace(pub, revision=13, admission_revision=9)
    settled = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.SELF_POWER and command.power_id == 429590426:
            result.receipt = replace(
                result.receipt,
                local_settlement=LocalSettlement.SETTLED if settled else LocalSettlement.PENDING,
            )
            result.receipt.require_command(command, verb)
        return result

    session.actor_action.side_effect = response
    first = owner.preparation_step()
    assert not first.acknowledgement.local_settled
    original = first.command
    owner.publication_reader.read.return_value = replace(
        pub,
        revision=17,
        admission_revision=12,
        snapshot_id=b"u" * 16,
        actions=(replace(pub.actions[0], coverage=publication.Coverage.PRESENT), *pub.actions[1:]),
    )
    assert owner.preparation_step().command is original
    settled = True
    final = owner.preparation_step()
    assert final.command is original and final.acknowledgement.local_settled
    rat, stance = owner.preparation_step(), owner.preparation_step()
    assert [rat.command.power_id, stance.command.power_id] == [429513599, 676005819]
    assert rat.command.publication_revision == stance.command.publication_revision == 17
    assert owner.preparation_step() is None
    submissions = [
        c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT
    ]
    assert [c.power_id for c in submissions] == [429590426, 429513599, 676005819]
    assert all(c.parent_id == owner.parent.owner_id and c.context_id is None for c in submissions)
    assert not any(
        c.args[1] in (Verb.STOP_CONTEXT, Verb.STOP_OWNER)
        for c in session.actor_action.call_args_list
    )


def test_same_native_capture_cannot_release_post_settlement_barrier(setup, monkeypatch):
    owner, session, _, _, _ = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.side_effect = None
    assert owner.preparation_step().acknowledgement.local_settled
    assert owner.preparation_step() is None
    owner.publication_reader.read.return_value = replace(pub, sequence=4)
    assert owner.preparation_step().command.power_id == 429545819
    submitted = [c for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert len(submitted) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"sequence": 2},
        {"sequence": 0},
        {"sequence": 3},
        {"sequence": 2**63},
        {"revision": 2},
        {"lifetime": b"n" * 16},
    ],
)
def test_capture_reset_wrap_or_lifetime_change_permanently_blocks_preparation(
    setup, monkeypatch, change
):
    owner, session, _, _, _ = setup
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.side_effect = None
    pub = replace(pub, sequence=4)
    owner.publication_reader.read.return_value = pub
    owner.observe_preparation()
    changed = (
        replace(pub, identity=replace(pub.identity, actor_lifetime=change["lifetime"]))
        if "lifetime" in change
        else replace(pub, **change)
    )
    owner.publication_reader.read.return_value = changed
    with pytest.raises(publication.PublicationError, match="capture"):
        owner.preparation_step()
    owner.publication_reader.read.return_value = replace(pub, sequence=6)
    with pytest.raises(publication.PublicationError, match="revoked"):
        owner.preparation_step()
    assert all(c.args[1] is not Verb.SUBMIT for c in session.actor_action.call_args_list)


@pytest.mark.parametrize("missing_before_settlement", [False, True])
def test_last_buff_observed_before_settlement_can_renew_on_next_missing_capture(
    setup, monkeypatch, missing_before_settlement
):
    owner, session, _, _, _ = setup
    power = 429590426
    settings = BuffSettings(
        True,
        (BuffGroup("beorc", (BuffAction(PreparationAction("beorc", power_id=power), power),)),),
    )
    pub, send = configure(owner, session, monkeypatch, settings)
    reader = owner.publication_reader.read
    reader.return_value = replace(pub, revision=13, admission_revision=9)
    settled = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.SELF_POWER:
            result.receipt = replace(
                result.receipt,
                local_settlement=LocalSettlement.SETTLED if settled else LocalSettlement.PENDING,
            )
            result.receipt.require_command(command, verb)
        return result

    session.actor_action.side_effect = response
    first = owner.preparation_step()
    original = first.command
    assert not first.acknowledgement.local_settled
    reader.return_value = replace(
        pub,
        revision=17,
        admission_revision=12,
        snapshot_id=b"u" * 16,
        actions=(replace(pub.actions[0], coverage=publication.Coverage.PRESENT),),
    )
    observed = owner.preparation_step()
    assert observed.command is original and not observed.acknowledgement.local_settled
    if missing_before_settlement:
        reader.return_value = replace(
            pub, revision=18, admission_revision=13, snapshot_id=b"v" * 16
        )
        unresolved = owner.preparation_step()
        assert unresolved.command is original and not unresolved.acknowledgement.local_settled
    settled = True
    completed = owner.preparation_step()
    assert completed.command is original and completed.acknowledgement.local_settled
    reader.return_value = replace(pub, revision=19, admission_revision=14, snapshot_id=b"w" * 16)
    renewal = owner.preparation_step()
    assert renewal is not None and renewal.command.power_id == power
    assert renewal.command.request != original.request
    assert renewal.command.parent_id == original.parent_id == owner.parent.owner_id
    assert renewal.command.context_id is original.context_id is None
    assert renewal.command.manifest_digest == original.manifest_digest
    assert renewal.command.publication_revision == 19
    # No observed effect from the first application may release the second one.
    reader.return_value = replace(pub, revision=20, admission_revision=14, snapshot_id=b"x" * 16)
    assert owner.preparation_step() is None
    submits = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert submits == [original, renewal.command]
    polls = [
        c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.ACTION_STATUS
    ]
    assert polls and all(c is original for c in polls)
    assert not any(
        c.args[1] in (Verb.STOP_CONTEXT, Verb.STOP_OWNER)
        for c in session.actor_action.call_args_list
    )


@pytest.mark.parametrize("refusal", [None, "missing", "wrong_command"])
def test_combat_poll_routes_preparation_settlement_to_its_owner(setup, monkeypatch, refusal):
    owner, session, _, observation, combat_proposal = setup
    _, send = configure(owner, session, monkeypatch)
    item_settled = False
    attack_settled = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.USE_ITEM:
            if verb is Verb.ACTION_STATUS and refusal == "missing":
                raise TimeoutError("no correlated status")
            result.receipt = replace(
                result.receipt,
                local_settlement=(
                    LocalSettlement.SETTLED if item_settled else LocalSettlement.PENDING
                ),
            )
            if verb is Verb.ACTION_STATUS and refusal == "wrong_command":
                result.receipt = replace(result.receipt, command_digest=b"x" * 32)
        elif command.action is Action.ATTACK:
            result.receipt = replace(
                result.receipt,
                local_settlement=(
                    LocalSettlement.SETTLED if attack_settled else LocalSettlement.PENDING
                ),
            )
        return result

    session.actor_action.side_effect = response
    first = owner.preparation_step()
    original = first.command
    assert not first.acknowledgement.local_settled
    assert (
        owner.advance_combat(combat_proposal, observation).acknowledgement.disposition.value
        == "uncertain"
    )
    assert owner._local_command is original
    item_settled = True
    update = owner.advance_combat(combat_proposal, observation)
    if refusal is not None:
        assert update.acknowledgement.disposition.value == "uncertain"
        assert owner._local_command is original
        assert owner._preparation_policy.pending_proposal == first.acknowledgement.proposal
        assert [
            c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT
        ] == [original]
        return
    assert update.acknowledgement.disposition.value == "queued"
    attack = update.command
    assert (
        owner._local_command is attack
        and update.receipt.local_settlement is LocalSettlement.PENDING
    )
    assert owner._preparation_policy.pending_proposal is None
    assert owner._preparation_command is owner._preparation_proposal is None
    # The potion remains remotely pending. Its local settlement permits combat,
    # and only the exact newer ATTACK status can release the shared local slot.
    assert owner._preparation_policy._applications.keys() == {"concoction"}
    assert owner.preparation_step() is None
    assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, attack)
    assert owner._local_command is attack
    # Even a retained old result cannot be delivered to a new command owner.
    with pytest.raises(ValueError, match="exact pending command owner"):
        owner._preparation_result(
            send(owner.grant, Verb.ACTION_STATUS, original),
            first.acknowledgement.proposal,
            original,
        )
    assert owner._local_command is attack
    attack_settled = True
    precision = owner.preparation_step()
    assert precision.command.power_id == 429545819
    assert owner.finish("test_complete")[0]


@pytest.mark.parametrize("uncertain", [False, True])
def test_combat_waits_for_live_preparation_status_without_expiring_new_proposal(
    setup, monkeypatch, uncertain
):
    owner, session, _, observation, proposal = setup
    _, send = configure(owner, session, monkeypatch)
    now = SimpleNamespace(value=0.0)
    session.cleanup.clock = lambda: now.value
    settled = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.USE_ITEM:
            result.receipt = replace(
                result.receipt,
                local_settlement=LocalSettlement.SETTLED if settled else LocalSettlement.PENDING,
                outcome=Outcome.UNCERTAIN if uncertain else Outcome.CLIENT_OUTBOUND_QUEUED,
            )
        return result

    session.actor_action.side_effect = response
    first = owner.preparation_step()
    for milliseconds in (1_000, 6_000, 18_000):
        observation.now_ms = milliseconds
        now.value = milliseconds / 1000
        update = owner.advance_combat(proposal, observation)
        assert update.acknowledgement.disposition.value == "uncertain"
        assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, first.command)
        assert owner._local_command is first.command and owner.context is None
        assert owner._preparation_policy.pending_proposal == first.acknowledgement.proposal
    settled = True
    observation.now_ms = 19_000
    now.value = 19.0
    update = owner.advance_combat(proposal, observation)
    assert update.acknowledgement.disposition.value == "queued"
    assert owner._preparation_policy.pending_proposal is None
    assert owner._preparation_policy._applications.keys() == {"concoction"}
    submits = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert [c.action for c in submits] == [Action.USE_ITEM, Action.ATTACK]
    assert not any(
        c.args[1] in (Verb.STOP_OWNER, Verb.STOP_CONTEXT)
        for c in session.actor_action.call_args_list
    )
    assert owner.finish("test_complete")[0]


@pytest.mark.parametrize(
    "failure", ["missing", "wrong_command", "wrong_verb", "stopping", "unknown"]
)
def test_combat_wait_does_not_renew_preparation_deadline_from_invalid_status(
    setup, monkeypatch, failure
):
    owner, session, _, observation, proposal = setup
    _, send = configure(owner, session, monkeypatch)
    now = SimpleNamespace(value=0.0)
    session.cleanup.clock = lambda: now.value
    failed = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.USE_ITEM:
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
            if failed:
                if failure == "missing":
                    raise TimeoutError("missing native reply")
                if failure == "wrong_command":
                    result.receipt = replace(result.receipt, command_digest=b"x" * 32)
                elif failure == "wrong_verb":
                    result.receipt = replace(result.receipt, verb=Verb.SUBMIT)
                elif failure == "stopping":
                    result.receipt = replace(result.receipt, owner_phase=Phase.STOPPING)
                else:
                    result.receipt = replace(
                        result.receipt, local_settlement=LocalSettlement.UNKNOWN
                    )
        return result

    session.actor_action.side_effect = response
    first = owner.preparation_step()
    observation.now_ms = 1_000
    now.value = 1.0
    owner.advance_combat(proposal, observation)
    failed = True
    observation.now_ms = 5_999
    now.value = 5.999
    assert (
        owner.advance_combat(proposal, observation).acknowledgement.disposition.value == "uncertain"
    )
    observation.now_ms = 6_000
    now.value = 6.0
    with pytest.raises(RuntimeError, match="status response deadline expired"):
        owner.advance_combat(proposal, observation)
    submits = [c.args[2] for c in session.actor_action.call_args_list if c.args[1] is Verb.SUBMIT]
    assert submits == [first.command]
    assert any(c.args[1] is Verb.STOP_OWNER for c in session.actor_action.call_args_list)


def test_preparation_waiting_on_pending_combat_does_not_start_a_new_action_deadline(
    setup, monkeypatch
):
    owner, session, _, observation, proposal = setup
    _, send = configure(owner, session, monkeypatch)
    now = SimpleNamespace(value=0.0)
    session.cleanup.clock = lambda: now.value
    settled = False

    def response(grant, verb, command, **kwargs):
        result = send(grant, verb, command, **kwargs)
        if command.action is Action.ATTACK:
            result.receipt = replace(
                result.receipt,
                local_settlement=LocalSettlement.SETTLED if settled else LocalSettlement.PENDING,
            )
        return result

    session.actor_action.side_effect = response
    attack = owner.advance_combat(proposal, observation).command
    for timestamp in (1.0, 6.0, 18.0):
        now.value = timestamp
        assert owner.preparation_step() is None
        assert session.actor_action.call_args.args[1:3] == (Verb.ACTION_STATUS, attack)
        assert owner._local_command is attack
        assert owner._preparation_proposal is owner._preparation_policy.pending_proposal is None
        assert owner._preparation_last_response is None
    settled = True
    now.value = 19.0
    first = owner.preparation_step()
    assert first.command.action is Action.USE_ITEM and first.acknowledgement.local_settled
    assert not any(
        c.args[1] in (Verb.STOP_CONTEXT, Verb.STOP_OWNER)
        for c in session.actor_action.call_args_list
    )
    assert owner.finish("test_complete")[0]


@pytest.mark.parametrize("after_child", [False, True])
def test_registry_churn_is_unavailable_without_cached_coverage(setup, monkeypatch, after_child):
    from shadowbane_lab.client_observation.native_population import (
        NativeCharacterPopulationSnapshotChanged,
    )

    owner, session, _, obs, combat = setup
    configure(owner, session, monkeypatch)
    if after_child:
        owner.advance_combat(combat, obs)
        assert owner.finish_context("native_death")[0]
    before = owner.observe_preparation()
    captured = owner._status_captured_at
    calls = session.actor_action.call_count
    reads = owner.publication_reader.read.call_count
    owner.population.resolve_actor_address.side_effect = NativeCharacterPopulationSnapshotChanged(
        "registry membership changed during read"
    )
    assert owner.observe_preparation() is None
    assert owner.preparation_step() is None
    assert owner._status_observation is None
    assert owner._status_captured_at == captured
    assert session.actor_action.call_count == calls
    assert owner.publication_reader.read.call_count == reads
    owner.population.resolve_actor_address.side_effect = None
    after = owner.observe_preparation()
    assert after.capture_sequence > before.capture_sequence
    assert after.admission_revision == before.admission_revision
    assert owner.preparation_step() is not None


@pytest.mark.parametrize("failure", ["structure", "budget", "session", "token", "address"])
def test_registry_unavailable_does_not_hide_identity_or_fatal_reads(setup, monkeypatch, failure):
    from shadowbane_lab.client_observation.native_population import (
        NativeCharacterPopulationReadError,
        NativeCharacterPopulationSnapshotChanged,
    )

    owner, session, _, _, _ = setup
    configure(owner, session, monkeypatch)
    owner.population.resolve_actor_address.side_effect = NativeCharacterPopulationSnapshotChanged(
        "changed"
    )
    if failure in ("structure", "budget"):
        owner.population.resolve_actor_address.side_effect = NativeCharacterPopulationReadError(
            failure
        )
    elif failure == "address":
        owner.population.resolve_actor_address.side_effect = None
        owner.population.resolve_actor_address.return_value = owner.parent.actor_hint + 4
    elif failure == "session":
        owner.character_session.require_current.side_effect = [None, ValueError("session replaced")]
    else:
        owner.population.observe_actor_identity.side_effect = [
            (owner.actor_token, owner.actor_key, None), ("replacement", owner.actor_key, None)
        ]
    with pytest.raises((NativeCharacterPopulationReadError, ValueError)):
        owner.observe_preparation()
    session.actor_action.assert_not_called()


@pytest.mark.parametrize("uncertain", [False, True])
def test_registry_churn_preserves_original_pending_status_and_cleanup(
    setup, monkeypatch, uncertain
):
    from shadowbane_lab.client_observation.native_population import (
        NativeCharacterPopulationSnapshotChanged,
    )

    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    now = [10.0]
    session.cleanup.clock = lambda: now[0]
    settled = False

    def native(g, v, c, **kw):
        result = send(g, v, c, **kw)
        if v in (Verb.SUBMIT, Verb.ACTION_STATUS):
            result.receipt = replace(
                result.receipt,
                local_settlement=LocalSettlement.SETTLED if settled else LocalSettlement.PENDING,
                outcome=Outcome.UNCERTAIN if uncertain else Outcome.CLIENT_OUTBOUND_QUEUED,
            )
        return result

    session.actor_action.side_effect = native
    first = owner.preparation_step()
    owner.population.resolve_actor_address.side_effect = NativeCharacterPopulationSnapshotChanged(
        "changed"
    )
    for timestamp in (16.0, 24.0):
        now[0] = timestamp
        update = owner.preparation_step()
        assert update.command is first.command
        assert not update.acknowledgement.local_settled
        assert owner._local_command is first.command
    settled = True
    assert owner.preparation_step().acknowledgement.local_settled
    assert owner.preparation_step() is None  # No new action from retained publication.
    calls = [(c.args[1], c.args[2]) for c in session.actor_action.call_args_list]
    action_calls = [(v, c) for v, c in calls if v in (Verb.SUBMIT, Verb.ACTION_STATUS)]
    assert [v for v, c in action_calls] == [Verb.SUBMIT] + [Verb.ACTION_STATUS] * 3
    assert all(c is first.command for v, c in action_calls)
    assert owner.finish("explicit_cancel")[0]
    assert owner._obligation.released


def test_registry_churn_between_proposal_and_open_never_submits_or_marks_refused(
    setup, monkeypatch
):
    from shadowbane_lab.client_observation.native_population import (
        NativeCharacterPopulationSnapshotChanged,
    )

    owner, session, _, _, _ = setup
    configure(owner, session, monkeypatch)
    hint = owner.parent.actor_hint
    owner.population.resolve_actor_address.side_effect = [
        hint, NativeCharacterPopulationSnapshotChanged("changed")
    ]
    update = owner.preparation_step()
    assert not update.acknowledgement.local_settled
    assert owner._preparation_policy.pending_proposal is update.decision.proposal
    assert not owner._preparation_policy._refused_at
    assert not any(
        c.args[1] in (Verb.OPEN_OWNER, Verb.SUBMIT) for c in session.actor_action.call_args_list
    )
    owner.population.resolve_actor_address.side_effect = None
    resumed = owner.preparation_step()
    assert resumed.acknowledgement.local_settled
    assert [c.args[1] for c in session.actor_action.call_args_list].count(Verb.SUBMIT) == 1


@pytest.mark.parametrize("submitted", [False, True])
def test_registry_churn_cannot_renew_missing_response_watchdog(setup, monkeypatch, submitted):
    from shadowbane_lab.client_observation.native_population import (
        NativeCharacterPopulationSnapshotChanged,
    )

    owner, session, _, _, _ = setup
    _, send = configure(owner, session, monkeypatch)
    now = [10.0]
    session.cleanup.clock = lambda: now[0]

    def native(g, v, c, **kw):
        if v is Verb.ACTION_STATUS:
            raise TimeoutError("no status")
        result = send(g, v, c, **kw)
        if v is Verb.SUBMIT:
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        return result

    session.actor_action.side_effect = native
    if not submitted:
        owner.population.resolve_actor_address.side_effect = [
            owner.parent.actor_hint, NativeCharacterPopulationSnapshotChanged("changed")
        ]
    owner.preparation_step()
    owner.population.resolve_actor_address.side_effect = NativeCharacterPopulationSnapshotChanged(
        "changed"
    )
    now[0] = 15.0
    with pytest.raises(RuntimeError, match="status response deadline"):
        owner.preparation_step()
    verbs = [c.args[1] for c in session.actor_action.call_args_list]
    assert verbs.count(Verb.SUBMIT) == int(submitted)
    assert verbs.count(Verb.ACTION_STATUS) == int(submitted)
    assert verbs.count(Verb.STOP_OWNER) == 1
    assert owner._obligation.released
