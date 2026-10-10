from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from test_player_attack_operation import operation

from shadowbane_lab.cli_commands import client_player_attack as attack
from shadowbane_lab.client_extension.actor_action_wire import Phase
from shadowbane_lab.client_input.stop import StopCause
from shadowbane_lab.client_observation.native_character_config import ActiveCharacterIdentity
from shadowbane_lab.client_observation.native_character_session import NativeCharacterBinding
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
)
from shadowbane_lab.client_observation.native_vitals import NativePlayerVitalsObservation
from shadowbane_lab.manager.operation import WorkerOperationState
from shadowbane_lab.pve.model import PvECombatDisposition


def fixture():
    local, remote = NativeObjectKey(7, 53), NativeObjectKey(42, 53)
    character = NativeCharacterObservation("remote", 100, 100, 1000, 2000, 0,
        False, False, False, False, False, object_key=remote,
        character_kind=NativeCharacterKind.PLAYER)
    binding = NativeCharacterBinding(51, 123, __import__("pathlib").Path("sb.exe"), "a"*64,
                                     ActiveCharacterIdentity(0x10000, "Umbra", "Wonderbane"), local)
    session = NS(binding=binding, require_current=Mock(), reader=object())
    frame = NS(local_player_object_key=local, characters=(character,))
    population = NS(observe=Mock(return_value=frame), observe_player_identity=Mock(
        return_value=NS(object_key=remote, character_name="Other Player",
                        server_name="Wonderbane")))
    group = NS(observe=Mock(return_value=NS(members=())))
    return session, population, group, character


def test_resolver_uses_registered_native_name_not_selection_or_tracking():
    session, population, group, _ = fixture()
    result = attack.resolve_player_attack_target(session, population, group, "oThEr")
    assert result == operation().player_target
    assert population.observe_player_identity.call_count == 2
    session.require_current.assert_called()


@pytest.mark.parametrize("scenario", ["ambiguous", "group", "dead", "protected", "wrong_server",
                                      "changed_name", "missing", "npc"])
def test_resolver_rejects_non_authoritative_target(scenario):
    session, population, group, c = fixture()
    if scenario == "ambiguous":
        population.observe.return_value.characters = (c, replace(c, token="second",
                                                        object_key=NativeObjectKey(43, 53)))
    elif scenario == "group":
        group.observe.return_value.members = (NS(object_type=42, object_uuid=53),)
    elif scenario in ("dead", "protected", "npc"):
        population.observe.return_value.characters = (replace(c, **{
            "dead": {"current_health": 0}, "protected": {"minion": True},
            "npc": {"character_kind": NativeCharacterKind.NPC}}[scenario]),)
    elif scenario == "wrong_server":
        population.observe_player_identity.return_value.server_name = "OtherServer"
    elif scenario == "changed_name":
        old = population.observe_player_identity.return_value
        population.observe_player_identity.side_effect = [old, NS(object_key=c.object_key,
                        character_name="Replacement", server_name="Wonderbane")]
    elif scenario == "missing":
        population.observe.return_value.characters = ()
    with pytest.raises(ValueError):
        attack.resolve_player_attack_target(session, population, group, "Other")


def test_group_change_during_discovery_refuses():
    session, population, group, _ = fixture()
    group.observe.side_effect = [NS(members=()), NS(members=(NS(object_type=42, object_uuid=53),))]
    with pytest.raises(ValueError, match="group membership|group"):
        attack.resolve_player_attack_target(session, population, group, "Other")


def run(monkeypatch, *, dead=False, stop=None, failure=None, cleanup=True, replace_dead=False):
    session, population, group, c = fixture()
    frame = NativeCharacterPopulationObservation((c,), None, None, 1, 0,
                                                  session.binding.object_key, False)
    clock = [0.0]
    calls = [0]
    def sampled(*args, **kwargs):
        calls[0] += 1
        if failure and calls[0] > 1:
            raise ValueError(failure)
        current = c
        if dead and calls[0] > 1:
            current = replace(c, current_health=0,
                              token="replaced" if replace_dead else c.token)
        return frame, current
    monkeypatch.setattr(attack, "_target_frame", sampled)
    owner = NS(finish=Mock(return_value=(cleanup, None, None)),
               preparation_step=Mock(), tracking_step=Mock())
    combat = NS(pending=None, active=False, advance=Mock(), observe=Mock(
        return_value=(NS(context_phase=Phase.BOUND), None)))
    def advance(*args, **kwargs):
        combat.active = True
        return NS(terminal_reason=None,
                  acknowledgement=NS(disposition=PvECombatDisposition.BOUND),
                  as_dict=lambda: {"queued": True})
    combat.advance.side_effect = advance
    signal = stop or NS(is_set=lambda: False)
    def sleep(seconds): clock[0] += seconds
    args = dict(operation=operation(), character_session=session, population=population,
                group=group, vitals=NS(observe=lambda: NativePlayerVitalsObservation(
                    100, 100, 50, 50, 50, 50)),
                owner=owner, combat=combat, intent=NS(entry=NS(entry_id="op")),
                stop_signal=signal, max_seconds=0.5, progress_sink=None,
                clock=lambda: clock[0], sleeper=sleep)
    return args, owner, combat


def test_finite_death_sends_one_attack_and_closes_owner(monkeypatch):
    args, owner, combat = run(monkeypatch, dead=True)
    result = attack._run_finite(**args)
    assert result.state is WorkerOperationState.SUCCEEDED
    assert not result.native_cleanup_confirmed  # Movement closure belongs to outer executor.
    assert combat.advance.call_count == 1
    owner.finish.assert_called_once()


def test_timeout_does_not_republish_attack(monkeypatch):
    args, owner, combat = run(monkeypatch)
    assert attack._run_finite(**args).state is WorkerOperationState.FAILED
    assert combat.advance.call_count == 1
    assert combat.observe.call_count > 0
    owner.finish.assert_called_once()


@pytest.mark.parametrize("reason", ["group joined", "target disappeared", "identity changed"])
def test_changed_target_stops_and_closes_without_retarget(monkeypatch, reason):
    args, owner, combat = run(monkeypatch, failure=reason)
    with pytest.raises(ValueError, match=reason):
        attack._run_finite(**args)
    assert combat.advance.call_count == 1
    owner.finish.assert_called_once()


def test_replaced_zero_health_object_is_not_death_proof(monkeypatch):
    args, owner, _ = run(monkeypatch, dead=True, replace_dead=True)
    with pytest.raises(ValueError, match="instance changed"):
        attack._run_finite(**args)
    owner.finish.assert_called_once()


@pytest.mark.parametrize("kind,state", [("requested", WorkerOperationState.CANCELLED),
                                        ("interrupted", WorkerOperationState.FAILED)])
def test_cancel_and_revocation_keep_distinct_terminal_reason(monkeypatch, kind, state):
    args, owner, combat = run(monkeypatch, stop=NS(is_set=lambda: True,
                                                stop_cause=StopCause("stop", kind)))
    assert attack._run_finite(**args).state is state
    combat.advance.assert_not_called()
    owner.finish.assert_called_once()


def test_uncertain_cleanup_overrides_success(monkeypatch):
    args, _, _ = run(monkeypatch, dead=True, cleanup=False)
    with pytest.raises(RuntimeError, match="cleanup remains unconfirmed"):
        attack._run_finite(**args)


def test_reader_setup_and_exact_target_validation_precede_lease_acquisition(monkeypatch):
    from contextlib import nullcontext
    session, population, group, _ = fixture()
    order = []
    monkeypatch.setattr(attack, "open_native_character_session",
                        lambda **kw: nullcontext(session))
    def opened(name, value):
        def factory(*args, **kwargs):
            order.append(name)
            return nullcontext(value)
        return factory
    monkeypatch.setattr(attack, "open_windows_native_character_population_reader",
                        opened("population", population))
    monkeypatch.setattr(attack, "open_windows_native_group_reader", opened("group", group))
    monkeypatch.setattr(attack, "open_windows_native_player_vitals_reader",
                        opened("vitals", object()))
    monkeypatch.setattr(attack, "_target_frame", lambda *a, **kw: order.append("validated"))
    owner = NS(configure_preparation=Mock(), configure_tracking=Mock())
    monkeypatch.setattr(attack, "NativeActorCoordinator", lambda **kw: owner)
    monkeypatch.setattr(attack, "NativeCombatCoordinator", lambda **kw: object())
    expected = NS(state=WorkerOperationState.SUCCEEDED)
    monkeypatch.setattr(attack, "_run_finite", lambda **kw: expected)
    def acquire():
        order.append("acquire")
        return NS(session=object(), grant=object())
    result = attack.execute_player_attack(binding=NS(game_process_id=51,
                  game_process_started_at_100ns=123), operation=operation(),
                  movement_acquirer=acquire, stop_signal=NS(is_set=lambda: False),
                  settings=NS(buffs=NS(enabled=False), tracking=NS(enabled=False)))
    assert result is expected
    assert order == ["population", "group", "vitals", "validated", "acquire"]


def test_operation_intent_ticket_binds_exact_target_without_saved_list(monkeypatch):
    from shadowbane_lab.client_extension.actor_action_fence import (
        ActorBinding,
        Authority,
        ContextId,
        OwnerId,
        Purpose,
    )
    from shadowbane_lab.client_extension.combat_wire_v2 import identity_digest
    session, _, _, _ = fixture()
    op = operation()
    intent = attack._OperationPlayerIntent(op, session.binding)
    parent = ActorBinding(51, 9001, 123, 456, 1, 2, 3, OwnerId(2),
        (7, 53), 0x10000, identity_digest("Umbra"), identity_digest("Wonderbane"),
        bytes.fromhex(intent.owner.storage_key), b"a" * 32, Purpose.COMBAT)
    ticket = Mock()
    factory = Mock(return_value=ticket)
    monkeypatch.setattr(attack, "Ticket", factory)
    got, context = intent.register_actor_context(intent.entry.entry_id,
        expected_revision=1, parent=parent, context_id=ContextId(3), target_hint=0x20000)
    assert got is ticket and context.authority is Authority.MANUAL_PLAYER
    assert context.target_key == (42, 53) and context.target_name == identity_digest("Other Player")
    assert context.store == context.entry == intent.digest
    ticket.arm.assert_called_once()
    with pytest.raises(ValueError):
        intent.register_actor_context("another operation", expected_revision=1, parent=parent,
                                      context_id=ContextId(4), target_hint=0x20000)


def test_normal_one_target_intent_has_no_arbitrary_fight_timeout(monkeypatch):
    args, owner, combat = run(monkeypatch)
    args["max_seconds"] = None
    elapsed = [0.0]
    args["clock"] = lambda: elapsed[0]
    def sleeper(seconds):
        elapsed[0] += 90
    args["sleeper"] = sleeper
    args["stop_signal"] = NS(is_set=lambda: elapsed[0] >= 270,
                              stop_cause=StopCause("requested_cancel", "requested"))
    result = attack._run_finite(**args)
    assert elapsed[0] == 270 and result.state is WorkerOperationState.CANCELLED
    assert combat.advance.call_count == 1
    owner.finish.assert_called_once()


def test_primary_identity_failure_survives_unconfirmed_cleanup(monkeypatch):
    args, _, _ = run(monkeypatch, failure="exact target changed", cleanup=False)
    with pytest.raises(RuntimeError, match="exact target changed;.*cleanup remains unconfirmed"):
        attack._run_finite(**args)
