import threading
import time

from shadowbane_lab.manager.preparation_service import PersistentPreparationService
from shadowbane_lab.pve.preparation_status import PreparationStatus


class Owner:
    preparation_status = PreparationStatus.disabled()
    local_pending = False
    changed = False
    finish_result = False
    closure = False

    def __init__(self):
        self.calls = []
        self.step_block = None

    def maintain(self):
        self.calls.append(("maintain", threading.get_ident()))

    def step(self, *, allow_new):
        self.calls.append(("step", allow_new, threading.get_ident()))
        if self.step_block:
            self.step_block.wait(2)

    def settings_changed(self):
        return self.changed

    def finish(self, reason):
        self.calls.append(("finish", reason, threading.get_ident()))
        return self.finish_result, None, "pending"

    def inspect_owner_closure(self):
        self.calls.append(("inspect", threading.get_ident()))
        return self.closure, None, "pending"

    def close(self):
        self.calls.append(("close", threading.get_ident()))


def service(owner, intent=lambda: (True, 1)):
    return PersistentPreparationService(owner_factory=lambda: owner, intent=intent, interval=.001)


def test_handoff_drains_local_pending_without_waiting_for_application():
    owner = Owner()
    value = service(owner)
    value._cycle()
    owner.local_pending = True
    assert not value.request_handoff()
    value._cycle()
    assert any(c[0:2] == ("step", False) for c in owner.calls)
    assert any(c[0] == "finish" for c in owner.calls)
    assert not value.request_handoff()
    owner.local_pending = False
    owner.closure = True
    value._cycle()
    assert value.request_handoff()
    assert [c[0] for c in owner.calls].count("close") == 1


def test_unresolved_finish_uses_only_readonly_terminal_inspection():
    owner = Owner()
    value = service(owner)
    value._cycle()
    value.request_handoff()
    value._cycle()
    value._cycle()
    assert [c[0] for c in owner.calls].count("finish") == 1
    assert [c[0] for c in owner.calls].count("inspect") == 1
    assert not value.request_handoff()
    owner.closure = True
    value._cycle()
    assert value.request_handoff()


def test_unknown_finite_cleanup_cannot_restart_service():
    owner = Owner()
    value = service(owner)
    assert value.request_handoff()
    value.release_handoff(cleanup_confirmed=False)
    value._cycle()
    assert owner.calls == []
    assert value.snapshot.state == "needs_attention"
    assert not value.request_handoff()


def test_positive_finite_cleanup_resumes_saved_intent():
    owner = Owner()
    value = service(owner)
    assert value.request_handoff()
    value.release_handoff(cleanup_confirmed=True)
    value._cycle()
    assert ("step", True) == owner.calls[-1][:2]


def test_settings_change_closes_old_owner_before_replacement():
    first, second = Owner(), Owner()
    owners = iter((first, second))
    value = PersistentPreparationService(owner_factory=lambda: next(owners),
        intent=lambda: (True, 2))
    value._cycle()
    first.changed = True
    first.local_pending = True
    value._cycle()
    assert not second.calls
    first.local_pending = False
    first.closure = True
    value._cycle()
    assert not second.calls
    value._cycle()
    assert second.calls[-1][:2] == ("step", True)


def test_supervisor_handoff_never_blocks_on_native_call():
    owner = Owner()
    owner.step_block = threading.Event()
    value = service(owner)
    value.start()
    deadline = time.monotonic() + 2
    while not any(c[0] == "step" for c in owner.calls):
        assert time.monotonic() < deadline
        time.sleep(.001)
    start = time.monotonic()
    assert not value.request_handoff()
    assert time.monotonic() - start < .1
    owner.finish_result = True
    owner.step_block.set()
    value.request_stop()
    while not value.stopped:
        assert time.monotonic() < deadline
        time.sleep(.001)
    assert len({c[-1] for c in owner.calls}) == 1
    assert owner.calls[0][-1] != threading.get_ident()


def test_disable_preserves_owner_until_exact_closure():
    enabled = [True]
    owner = Owner()
    value = service(owner, intent=lambda: (enabled[0], 4))
    value._cycle()
    enabled[0] = False
    value._cycle()
    assert value.snapshot.state == "needs_attention"
    owner.closure = True
    value._cycle()
    assert value.snapshot.state == "paused"
    value._cycle()
    assert [c[0] for c in owner.calls].count("finish") == 1


def test_resume_during_unresolved_close_only_inspects_old_owner():
    enabled = [True]
    first, second = Owner(), Owner()
    owners = iter((first, second))
    value = PersistentPreparationService(owner_factory=lambda: next(owners),
        intent=lambda: (enabled[0], 1))
    value._cycle()
    enabled[0] = False
    value._cycle()
    enabled[0] = True
    value._cycle()
    assert first.calls[-1][0] == "inspect"
    assert not second.calls
    first.closure = True
    value._cycle()
    value._cycle()
    assert second.calls[-1][:2] == ("step", True)


def test_renewal_failure_does_not_starve_passive_cleanup():
    owner = Owner()
    value = service(owner)
    value._cycle()
    def failed():
        raise RuntimeError("producer renewal unavailable")
    owner.maintain = failed
    value._cycle()
    assert owner.calls[-1][0] == "finish"
    owner.closure = True
    value._cycle()
    assert owner.calls[-2][0] == "inspect"
    assert owner.calls[-1][0] == "close"
    assert [c[0] for c in owner.calls].count("finish") == 1


def test_pause_during_factory_cannot_submit_first_action():
    enabled = [True]
    owner = Owner()
    owner.finish_result = True
    def factory():
        enabled[0] = False
        return owner
    value = PersistentPreparationService(owner_factory=factory,
        intent=lambda: (enabled[0], 2))
    value._cycle()
    assert not any(c[:2] == ("step", True) for c in owner.calls)
    assert any(c[0] == "finish" for c in owner.calls)
    assert not value.admission_allowed()


def test_permit_loss_during_maintain_cannot_submit_new_action():
    enabled = [True]
    owner = Owner()
    value = service(owner, intent=lambda: (enabled[0], 3))
    value._cycle()
    owner.calls.clear()
    def maintain():
        enabled[0] = False
    owner.maintain = maintain
    value._cycle()
    assert not any(c[:2] == ("step", True) for c in owner.calls)
    assert owner.calls[-1][0] == "finish"


def test_entry_admission_observes_stop_after_cycle_check():
    value = service(Owner())
    assert value.admission_allowed()
    value.request_stop()
    assert not value.admission_allowed()


def test_unreadable_control_forbids_entry_but_never_starves_closure():
    failed = [False]
    def intent():
        if failed[0]:
            raise ValueError("invalid control file")
        return True, 1
    owner = Owner()
    value = service(owner, intent)
    value._cycle()
    failed[0] = True
    assert not value.admission_allowed()
    value._cycle()
    assert owner.calls[-1][0] == "finish"
    owner.closure = True
    value._cycle()
    assert owner.calls[-1][0] == "close"
    assert value.snapshot.state == "needs_attention"



def test_failed_finite_handoff_does_not_make_empty_service_unshutdownable():
    owner = Owner()
    value = service(owner)
    assert value.request_handoff()
    value.release_handoff(cleanup_confirmed=False)
    value.request_stop()
    assert value._cycle()
    assert value.snapshot.state == "needs_attention"
    assert not value.request_handoff()
    assert owner.calls == []



def test_finite_handoff_waits_for_potion_without_starting_cleanup_or_new_actions():
    owner = Owner()
    clear = [False]
    value = PersistentPreparationService(owner_factory=lambda: owner,
        intent=lambda: (True, 1), handoff_ready=lambda: clear[0])
    value._cycle()
    assert not value.request_handoff(wait_for_preparation=True)
    value._cycle()
    assert value.snapshot.state == "awaiting_potion_outcome"
    assert [c[0] for c in owner.calls].count("finish") == 0
    assert [c[:2] for c in owner.calls].count(("step", True)) == 1
    clear[0] = True
    owner.finish_result = True
    value._cycle()
    assert not value.request_handoff(wait_for_preparation=True)  # Must refresh after close.
    value._cycle()
    assert value.request_handoff(wait_for_preparation=True)
    assert [c[0] for c in owner.calls].count("finish") == 1


def test_explicit_stop_closes_passively_despite_unresolved_potion():
    owner = Owner()
    value = PersistentPreparationService(owner_factory=lambda: owner,
        intent=lambda: (True, 1), handoff_ready=lambda: False)
    value._cycle()
    value.request_handoff(wait_for_preparation=True)
    value._cycle()
    owner.finish_result = True
    value.request_stop()
    assert value._cycle()
    assert [c[0] for c in owner.calls].count("finish") == 1


def test_startup_handoff_observes_native_barrier_without_opening_owner():
    clear = [False]
    def factory():
        raise AssertionError("handoff observation must not create an owner")
    value = PersistentPreparationService(owner_factory=factory,
        intent=lambda: (False, 1), handoff_ready=lambda: clear[0])
    assert not value.request_handoff(wait_for_preparation=True)
    value._cycle()
    assert not value.request_handoff(wait_for_preparation=True)
    clear[0] = True
    value._cycle()
    assert value.request_handoff(wait_for_preparation=True)
