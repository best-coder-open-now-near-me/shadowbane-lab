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
