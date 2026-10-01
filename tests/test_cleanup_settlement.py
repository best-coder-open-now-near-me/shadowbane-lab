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
