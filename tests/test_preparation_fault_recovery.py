import pytest
from test_preparation_service import Owner

from shadowbane_lab.manager.preparation_service import PersistentPreparationService


class PumpDone(BaseException):
    pass


def pump(service, cycles):
    class Wake:
        def wait(self, interval):
            nonlocal cycles
            cycles -= 1
            if cycles == 0:
                raise PumpDone

        def clear(self):
            pass

        def set(self):
            pass

    service._wake = Wake()
    with pytest.raises(PumpDone):
        service._run()


class FaultOwner(Owner):
    def step(self, *, allow_new):
        super().step(allow_new=allow_new)
        if allow_new:
            raise RuntimeError('native observation failed')


def setup_service(intent=lambda: (True, 5)):
    first, second = FaultOwner(), Owner()
    created = []

    def factory():
        owner = (first, second)[len(created)]
        created.append(owner)
        return owner

    value = PersistentPreparationService(owner_factory=factory, intent=intent)
    return value, first, second, created


def test_internal_fault_recovers_only_after_exact_late_closure():
    value, first, second, created = setup_service()
    pump(value, 1)
    assert value.snapshot.state == 'needs_attention'
    assert 'native observation failed' in value.snapshot.detail
    assert not value.admission_allowed()
    pump(value, 1)
    assert [c[0] for c in first.calls].count('finish') == 1
    pump(value, 2)
    assert created == [first] and not second.calls
    assert 'native observation failed' in value.snapshot.detail
    first.closure = True
    pump(value, 1)
    assert created == [first]
    pump(value, 1)
    assert created == [first, second]
    assert value.snapshot.state == 'maintaining'
    assert [c[0] for c in first.calls].count('close') == 1
    assert [c[0] for c in first.calls].count('finish') == 1


def test_confirmed_internal_cleanup_does_not_reserve_a_finite_handoff():
    value, first, second, created = setup_service()
    first.finish_result = True
    pump(value, 3)
    assert created == [first, second]
    assert value.snapshot.state == 'maintaining'


@pytest.mark.parametrize('when', ['failed_step', 'pending_close'])
def test_fault_recovery_cannot_clear_concurrent_finite_handoff(when):
    value, first, second, created = setup_service()
    if when == 'failed_step':
        original = first.step

        def step(**kwargs):
            assert not value.request_handoff()
            original(**kwargs)

        first.step = step
    pump(value, 1)
    if when == 'pending_close':
        assert not value.request_handoff()
    first.finish_result = True
    pump(value, 2)
    assert created == [first]
    assert value.snapshot.state == 'yielding'
    assert not value.admission_allowed()
    assert value.request_handoff()
    value.release_handoff(cleanup_confirmed=True)
    pump(value, 1)
    assert created == [first, second]


@pytest.mark.parametrize('control', ['disabled', 'supervision', 'stop', 'unreadable'])
def test_fault_cleanup_respects_current_control(control):
    enabled = [True]
    unreadable = [False]

    def intent():
        if unreadable[0]:
            raise ValueError('control unavailable')
        return enabled[0], 5

    value, first, second, created = setup_service(intent)
    pump(value, 1)
    if control == 'disabled':
        enabled[0] = False
    elif control == 'supervision':
        value.supervise(allowed=False)
    elif control == 'stop':
        value.request_stop()
    else:
        unreadable[0] = True
    first.finish_result = True
    if control == 'stop':
        value._run()
    else:
        pump(value, 3)
    assert created == [first] and not second.calls
    assert not value.admission_allowed()
    assert [c[0] for c in first.calls].count('finish') == 1
    if control != 'stop':
        enabled[0], unreadable[0] = True, False
        value.supervise(allowed=True)
        pump(value, 1)
        assert created == [first, second]


def test_unconfirmed_finite_handback_remains_blocked_after_fault_cleanup():
    value, first, second, created = setup_service()
    pump(value, 1)
    assert not value.request_handoff()
    first.finish_result = True
    pump(value, 1)
    assert value.request_handoff()
    value.release_handoff(cleanup_confirmed=False)
    pump(value, 3)
    assert created == [first]
    assert value.snapshot.state == 'needs_attention'
    assert not value.admission_allowed()


def test_cleanup_inspection_failure_retains_first_fault_and_same_owner():
    value, first, second, created = setup_service()
    pump(value, 2)
    original = first.inspect_owner_closure

    def unavailable():
        raise OSError('inspection unavailable')

    first.inspect_owner_closure = unavailable
    pump(value, 2)
    assert created == [first]
    assert 'native observation failed' in value.snapshot.detail
    first.inspect_owner_closure = original
    first.closure = True
    pump(value, 2)
    assert created == [first, second]
    assert [c[0] for c in first.calls].count('finish') == 1


def test_status_getter_failure_cannot_kill_recovery_thread():
    class StatusFailure(Owner):
        @property
        def preparation_status(self):
            raise ValueError('owner status unavailable')

    first, second = StatusFailure(), Owner()
    first.finish_result = True
    owners = iter([first, second])
    value = PersistentPreparationService(
        owner_factory=lambda: next(owners), intent=lambda: (True, 5))
    pump(value, 1)
    assert 'owner status unavailable' in value.snapshot.detail
    pump(value, 2)
    assert second.calls[-1][:2] == ('step', True)


def test_ordinary_manual_deferral_keeps_recovered_owner_without_forced_cleanup():
    value, first, second, created = setup_service()
    first.finish_result = True
    manual = [True]
    entries = []

    def step(*, allow_new):
        if allow_new and not manual[0]:
            entries.append('native-entry')

    second.step = step
    pump(value, 5)
    assert created == [first, second]
    assert not entries and not any(c[0] == 'finish' for c in second.calls)
    manual[0] = False
    pump(value, 1)
    assert entries == ['native-entry']
    assert not any(c[0] == 'finish' for c in second.calls)
