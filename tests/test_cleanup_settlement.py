from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.cleanup_settlement import CleanupSettlement


def fake_cleanup():
    clock = SimpleNamespace(now=0.0)
    def sleep(seconds):
        clock.now += seconds
    return CleanupSettlement(clock=lambda: clock.now, sleeper=sleep), clock


def test_delayed_confirmation_is_paced_and_releases_only_exact_obligation():
    cleanup, clock = fake_cleanup()
    owner = cleanup.register('owner')
    cleanup.request_terminal('owner')
    times = []
    def attempt():
        times.append(clock.now)
        if len(times) == 4:
            cleanup.release(owner)
            return True, 'exact closure'
        return False, 'pending'
    assert cleanup.settle(owner, attempt, (False, None)) == (True, 'exact closure')
    assert times == pytest.approx([0, .1, .2, .3])
    assert cleanup.blocked('owner') and not cleanup.maintain('owner')
    with pytest.raises(RuntimeError, match='terminal'):
        cleanup.register('owner')


def test_timeout_preserves_obligation_and_original_deadline_across_callers():
    cleanup, clock = fake_cleanup()
    owner = cleanup.register('owner')
    cleanup.begin(owner)
    clock.now = 2
    cleanup.request_terminal('owner')
    count = 0
    def pending():
        nonlocal count
        count += 1
        return False, 'last correlated pending'
    value = cleanup.settle(owner, pending, (False, None))
    assert value == (False, 'last correlated pending')
    assert clock.now == 3 and not owner.released and not cleanup.maintain('owner')
    before = count
    assert cleanup.settle(owner, pending, value) == value
    assert count == before and cleanup.blocked('owner')


def test_normal_encounter_cleanup_allows_next_encounter_but_not_duplicate_owner():
    cleanup, _ = fake_cleanup()
    first = cleanup.register('owner')
    with pytest.raises(RuntimeError, match='already'):
        cleanup.register('owner')
    cleanup.begin(first)
    cleanup.release(first)
    assert not cleanup.blocked('owner')
    assert cleanup.register('owner') is not first


def test_aborted_or_different_owner_never_borrows_cleanup_heartbeat():
    cleanup, _ = fake_cleanup()
    owner = cleanup.register('old')
    cleanup.request_terminal('old')
    assert cleanup.maintain('old') and not cleanup.maintain('replacement')
    cleanup.abort('old')
    assert not cleanup.maintain('old') and not owner.released


def test_command_budget_uses_earliest_deadline_and_never_renews_it():
    cleanup, clock = fake_cleanup()
    owner = cleanup.register('owner')
    cleanup.begin(owner)
    assert cleanup.timeout_ms('owner', 750) == 750
    clock.now=2.95
    assert 49 <= cleanup.timeout_ms('owner', 750) <= 50
    cleanup.request_terminal('owner')
    clock.now=3
    with pytest.raises(TimeoutError,match='deadline expired'):
        cleanup.timeout_ms('owner',750)
    assert not owner.released


def actor_context_cleanup():
    from dataclasses import dataclass

    from test_actor_action_wire import fixture

    from shadowbane_lab.client_extension.actor_action_wire import (
        OWNER_CLEANUP,
        Action,
        Closure,
        ClosureScope,
        Command,
        Outcome,
        Phase,
        Receipt,
        Verb,
    )

    @dataclass(frozen=True)
    class Grant:
        ownership: object
        host: object
        window: int

    parent, context, source, _ = fixture()
    command = Command(source.host, source.window, source.grant, source.request,
        parent.owner_id, context.context_id, parent.digest, context.digest)
    receipt = Receipt(command.request, command.host, command.window, Outcome.OBSERVED,
        OWNER_CLEANUP, command.grant, command.parent_id, command.context_id, command.digest,
        Verb.STOP_CONTEXT, Action.NONE, owner_phase=Phase.BOUND, context_phase=Phase.CLOSED,
        closure=Closure.NATIVE_STOPPED, closure_scope=ClosureScope.CONTEXT, mode=1)
    receipt.require_command(command, Verb.STOP_CONTEXT)
    return Grant(command.grant, command.host, command.window), command, receipt


def test_context_closure_preserves_one_parent_and_can_start_next_settlement():
    from dataclasses import replace

    from shadowbane_lab.client_extension.actor_action_fence import ContextId, RequestId

    cleanup, clock = fake_cleanup()
    grant, command, receipt = actor_context_cleanup()
    owner = cleanup.register(grant)
    assert cleanup.begin_context(owner, command) == 3
    clock.now = 1
    cleanup.continue_owner(owner, receipt)
    assert not owner.released and owner.deadline is None
    with pytest.raises(RuntimeError, match="already"):
        cleanup.register(grant)
    following = replace(command, context_id=ContextId(2), request=RequestId(2),
                        context_digest=b"x" * 32)
    assert cleanup.begin_context(owner, following) == 4
    with pytest.raises(ValueError):
        cleanup.continue_owner(owner, receipt)
    assert owner.deadline == 4


def test_context_settlement_cannot_change_identity_or_extend_terminal_budget():
    from dataclasses import replace

    from shadowbane_lab.client_extension.actor_action_fence import RequestId

    cleanup, clock = fake_cleanup()
    grant, command, receipt = actor_context_cleanup()
    owner = cleanup.register(grant)
    cleanup.begin_context(owner, command)
    with pytest.raises(RuntimeError, match="unresolved"):
        cleanup.begin_context(owner, replace(command, request=RequestId(2)))
    clock.now = 2
    cleanup.request_terminal(grant)
    with pytest.raises(RuntimeError, match="terminal"):
        cleanup.continue_owner(owner, receipt)
    assert owner.deadline == 3 and not owner.released
    clock.now = 3
    with pytest.raises(TimeoutError):
        cleanup.timeout_ms(grant, 100)


def test_context_settlement_requires_registered_exact_owner_and_positive_proof():
    from dataclasses import replace

    from shadowbane_lab.client_extension.actor_action_wire import (
        CONTEXT_CLEANUP,
        Closure,
        ClosureScope,
        Phase,
    )

    cleanup, _ = fake_cleanup()
    grant, command, receipt = actor_context_cleanup()
    owner = cleanup.register(grant)
    with pytest.raises(ValueError):
        cleanup.begin_context(owner, replace(command, window=command.window+1))
    cleanup.begin_context(owner, command)
    pending = replace(receipt, flags=receipt.flags|CONTEXT_CLEANUP,
                      context_phase=Phase.STOPPING, closure=Closure.NONE,
                      closure_scope=ClosureScope.NONE)
    with pytest.raises(ValueError):
        cleanup.continue_owner(owner, pending)
    assert owner.deadline == 3 and not owner.released
