"""Preparation has exact actor authority without movement/target authority."""

import hashlib
from dataclasses import replace

import pytest
from test_actor_action_wire import fixture

from shadowbane_lab.client_extension.actor_action_fence import ActorBinding, Purpose
from shadowbane_lab.client_extension.actor_action_wire import Action, Command, Receipt, Verb


def preparation():
    parent, child, command, receipt = fixture()
    parent = replace(
        parent,
        purpose=Purpose.PREPARATION,
        movement_generation=0,
        operation=hashlib.sha256(parent.owner_id.encode()).digest(),
    )
    command = replace(command, grant=None, parent_digest=parent.digest)
    receipt = replace(receipt, grant=None, command_digest=command.digest)
    return parent, child, command, receipt


def test_preparation_has_explicit_fence_and_no_movement_authority():
    parent, _, command, receipt = preparation()
    assert ActorBinding.decode(parent.encode())[0] == parent
    assert Command.decode(command.encode()) == command
    assert Receipt.decode(receipt.encode()) == receipt
    command.require_bindings(parent)
    receipt.require_command(command, Verb.SUBMIT)
    assert parent.purpose is Purpose.PREPARATION and parent.movement_generation == 0


def test_preparation_cannot_upgrade_to_combat_or_attach_a_context():
    parent, child, command, _ = preparation()
    old, _, old_command, _ = fixture()
    with pytest.raises(ValueError):
        command.require_bindings(old)
    with pytest.raises(ValueError):
        replace(old_command, parent_digest=parent.digest).require_bindings(parent)
    with pytest.raises(ValueError):
        replace(child, parent_digest=parent.digest).require_parent(parent)
    with pytest.raises(ValueError):
        replace(command, context_id=child.context_id, context_digest=child.digest).encode()
    with pytest.raises(ValueError):
        replace(command, action=Action.ATTACK).encode()


@pytest.mark.parametrize("field,value", [("purpose", 1), ("movement_generation", 1)])
def test_purpose_is_typed_and_cannot_smuggle_movement(field, value):
    parent, _, _, _ = preparation()
    with pytest.raises(ValueError):
        replace(parent, **{field: value})


def test_purpose_and_immutable_operation_are_both_correlated():
    parent, _, command, _ = preparation()
    parent = replace(parent, operation=b"x" * 32)
    with pytest.raises(ValueError):
        replace(command, parent_digest=parent.digest).require_bindings(parent)


from types import SimpleNamespace  # noqa: E402
from unittest.mock import Mock  # noqa: E402

from test_actor_action_session import owned as owned_fixture  # noqa: E402
from test_native_actor_coordinator import setup as coordinator_fixture  # noqa: E402
from test_native_actor_preparation import configure  # noqa: E402

from shadowbane_lab.client_extension import action_channel as channel  # noqa: E402
from shadowbane_lab.client_extension.actor_action_wire import (  # noqa: E402
    Closure,
    ClosureScope,
    Outcome,
    Phase,
)
from shadowbane_lab.client_extension.movement_session import (  # noqa: E402
    NativeMovementSession,
    NativePreparationLease,
)
from shadowbane_lab.pve.native_actor import NativeActorCoordinator  # noqa: E402

owned = owned_fixture
actor_setup = coordinator_fixture


def test_fresh_preparation_transport_never_acquires_movement(owned, monkeypatch):
    old, _, _, _, _, transport, opened = owned
    factory = type(transport)

    def create(identity):
        result = factory(identity)
        result.header = replace(
            result.header,
            capability_flags=(
                result.header.capability_flags | channel.ACTOR_PREPARATION_CAPABILITY
            ),
        )
        result.renew_lease = Mock()
        return result

    monkeypatch.setattr(channel, "WindowsNativeActionCommandTransport", create)
    session = NativeMovementSession(old.identity, old.window)
    lease = session.preparation_lease(7)
    fresh = opened[-1]
    assert isinstance(lease, NativePreparationLease) and lease.ownership is None
    assert fresh.commands == []
    session.maintain_preparation(lease)
    fresh.renew_lease.assert_called_once()
    with pytest.raises((ValueError, AttributeError)):
        session.stop(lease, "00000000-0000-0000-0000-000000000001")
    assert fresh.commands == []
    fresh.host_lease_generation += 1
    with pytest.raises(channel.NativeActionChannelUnavailable):
        session.maintain_preparation(lease)
    assert len(opened) == 2
    session.close()


def maintenance(actor_setup):
    old, session, tickets, _, _ = actor_setup
    old.close_unopened()
    grant = NativePreparationLease(
        old.grant.process_identity, old.grant.window, old.grant.host, old.parent.scene
    )
    return (
        NativeActorCoordinator(
            session=session,
            grant=grant,
            population=old.population,
            character_session=old.character_session,
            store=old.store,
            ticket_factory=old._ticket_factory,
        ),
        session,
        tickets,
    )


def test_unopened_disposal_releases_views_without_native_commands(actor_setup, monkeypatch):
    owner, session, tickets = maintenance(actor_setup)
    configure(owner, session, monkeypatch)
    session.actor_action.reset_mock()
    owner.close_unopened()
    assert owner._obligation.released and not owner.local_pending
    tickets[-1].close.assert_called_once_with(revoke=False)
    owner._manifest_mapping.close.assert_called_once()
    session.actor_action.assert_not_called()


def test_worker_revocation_after_open_prevents_submit_but_not_cleanup(actor_setup, monkeypatch):
    owner, session, _ = maintenance(actor_setup)
    configure(owner, session, monkeypatch)
    allowed = [True]
    owner._preparation_admission = lambda: allowed[0]
    original = session.actor_action.side_effect

    def send(g, v, c, **kw):
        result = original(g, v, c, **kw)
        if v is Verb.OPEN_OWNER:
            allowed[0] = False
        return result

    session.actor_action.side_effect = send
    owner.preparation_step()
    verbs = [call.args[1] for call in session.actor_action.call_args_list]
    assert Verb.OPEN_OWNER in verbs and Verb.SUBMIT not in verbs
    with pytest.raises(RuntimeError, match="correlated cleanup"):
        owner.close_unopened()
    owner.finish("worker paused")
    assert session.actor_action.call_args_list[-1].args[1] is Verb.STOP_OWNER


def test_late_owner_query_keeps_original_command_and_expired_deadline(actor_setup):
    owner, session, tickets = maintenance(actor_setup)
    now = [0.0]
    session.cleanup.clock = lambda: now[0]
    session.cleanup.sleeper = lambda seconds: now.__setitem__(0, now[0] + seconds)
    seen = []
    closed = [False]

    def send(g, verb, command, **kwargs):
        seen.append((verb, command))
        receipt = Receipt(
            command.request,
            command.host,
            command.window,
            Outcome.ENGAGEMENT_CLOSED if closed[0] else Outcome.PENDING,
            0 if closed[0] else 1,
            None,
            command.parent_id,
            None,
            command.digest,
            verb,
            Action.NONE,
            owner_phase=Phase.CLOSED if closed[0] else Phase.STOPPING,
            closure=Closure.LOCAL_RELEASED if closed[0] else Closure.NONE,
            closure_scope=ClosureScope.OWNER if closed[0] else ClosureScope.NONE,
        )
        return SimpleNamespace(receipt=receipt, native_detail=None)

    session.actor_action.side_effect = send
    assert not owner.finish("handoff")[0]
    stop = seen[0][1]
    deadline = owner._obligation.deadline
    assert now[0] >= deadline and all(c == stop for _, c in seen)
    assert not owner.inspect_owner_closure()[0]
    closed[0] = True
    assert owner.inspect_owner_closure()[0]
    assert seen[-2:] == [(Verb.OWNER_STATUS, stop), (Verb.OWNER_STATUS, stop)]
    assert owner._obligation.deadline == deadline and owner._obligation.released
    assert tickets[-1].close.call_args.kwargs == {"revoke": False}
    assert not owner.local_pending


@pytest.mark.parametrize("blocks", [32, 33, 63])
def test_manual_admission_status_is_typed_not_cleanup_failure(blocks):
    from shadowbane_lab.pve.native_actor import NativePreparationStatus

    status = NativePreparationStatus(1, 1, blocks).as_dict()
    assert status["reason"] == "native_admission_blocked"
    assert "manual_activity" in status["blockers"]


def test_passive_refresh_never_creates_policy_proposal(actor_setup, monkeypatch):
    from shadowbane_lab.client_extension.actor_publication import AdmissionBlock

    owner, session, _ = maintenance(actor_setup)
    pub, _ = configure(owner, session, monkeypatch)
    owner.publication_reader.read.return_value = replace(
        pub, admission_blocks=AdmissionBlock.MANUAL_ACTIVITY
    )
    assert owner.preparation_step(allow_new=False) is None
    assert owner._preparation_policy.pending_proposal is None
    assert owner.latest_preparation_status.as_dict()["reason"] == "native_admission_blocked"
    assert all(
        c.args[1] in (Verb.REGISTER_SELECTORS, Verb.OBSERVE_ACTOR)
        for c in session.actor_action.call_args_list
    )


def test_passive_step_does_not_publish_an_existing_unsent_proposal(actor_setup, monkeypatch):
    owner, session, _ = maintenance(actor_setup)
    configure(owner, session, monkeypatch)
    allowed = [False]
    owner._preparation_admission = lambda: allowed[0]
    owner.preparation_step()
    pending = owner._preparation_policy.pending_proposal
    assert pending is not None and owner._preparation_command is None
    allowed[0] = True
    session.actor_action.reset_mock()
    assert owner.preparation_step(allow_new=False) is None
    assert owner._preparation_policy.pending_proposal == pending
    assert all(c.args[1] in (Verb.REGISTER_SELECTORS, Verb.OBSERVE_ACTOR)
               for c in session.actor_action.call_args_list)


def test_passive_step_polls_only_the_original_published_command(actor_setup, monkeypatch):
    from shadowbane_lab.client_extension.actor_action_wire import LocalSettlement

    owner, session, _ = maintenance(actor_setup)
    _, original_send = configure(owner, session, monkeypatch)

    def send(grant, verb, command, **kwargs):
        result = original_send(grant, verb, command, **kwargs)
        if verb in (Verb.SUBMIT, Verb.ACTION_STATUS):
            result.receipt = replace(result.receipt, local_settlement=LocalSettlement.PENDING)
        return result

    session.actor_action.side_effect = send
    owner.preparation_step()
    command = owner._preparation_command
    assert command is not None
    owner._preparation_admission = lambda: False
    session.actor_action.reset_mock()
    owner.preparation_step(allow_new=False)
    actions = [c.args[1:3] for c in session.actor_action.call_args_list
               if c.args[1] not in (Verb.REGISTER_SELECTORS, Verb.OBSERVE_ACTOR)]
    assert actions == [(Verb.ACTION_STATUS, command)]
    assert owner._preparation_command == command


@pytest.mark.parametrize("retired", [None, "replacement"])
def test_process_retirement_disposes_without_native_cleanup(actor_setup, monkeypatch, retired):
    owner, session, tickets = maintenance(actor_setup)
    inspector = Mock()
    inspector.inspect.return_value = (
        None
        if retired is None
        else SimpleNamespace(
            process_id=owner.parent.client_pid,
            process_started_at_100ns=owner.parent.client_creation + 1,
        )
    )
    monkeypatch.setattr(
        "shadowbane_lab.manager.supervisor.Win32ProcessLifetimeInspector", lambda: inspector
    )
    session.actor_action.reset_mock()
    assert owner.close_retired_process()
    assert owner._obligation.released and owner._last_owner_result[1] is None
    tickets[-1].close.assert_called_once_with(revoke=False)
    session.actor_action.assert_not_called()


def test_live_or_unreadable_process_does_not_dispose_pending_owner(actor_setup, monkeypatch):
    owner, _, tickets = maintenance(actor_setup)
    inspector = Mock()
    inspector.inspect.return_value = SimpleNamespace(
        process_id=owner.parent.client_pid, process_started_at_100ns=owner.parent.client_creation
    )
    monkeypatch.setattr(
        "shadowbane_lab.manager.supervisor.Win32ProcessLifetimeInspector", lambda: inspector
    )
    assert not owner.close_retired_process()
    inspector.inspect.side_effect = OSError("access denied")
    with pytest.raises(OSError):
        owner.close_retired_process()
    assert not owner._obligation.released
    tickets[-1].close.assert_not_called()
