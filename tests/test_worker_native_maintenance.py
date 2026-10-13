"""Real movement ownership survives cold ledger work, never expired authority."""
import threading
import time
from dataclasses import replace

from test_manager_movement import context
from test_manager_operation import (
    CLIENT_ID,
    INSTANCE_ID,
    NODE_ID,
    WORKER_ID,
    WORKER_PROCESS_ID,
    WORKER_PROCESS_STARTED,
    _manifest,
    _permit,
)

from shadowbane_lab.manager.operation import WorkerOperationLedger
from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot
from shadowbane_lab.manager.worker import WorkerDispatchGate, WorkerHeartbeatLedger
from shadowbane_lab.manager.worker_runtime import (
    ExactClientWorkerBinding,
    _OperationMaintenance,
    _OperationStopSignal,
)


def setup(tmp_path, clock):
    ledger = WorkerOperationLedger(_manifest(), tmp_path)
    ledger.initialize_stop_authority(CLIENT_ID)
    heartbeats = WorkerHeartbeatLedger(_manifest(), tmp_path)
    permit = _permit()
    heartbeats.publish_permit(permit)
    gate = WorkerDispatchGate(heartbeats, node_id=NODE_ID, client_id=CLIENT_ID,
        instance_id=INSTANCE_ID, worker_id=WORKER_ID,
        process=ProcessLifetimeSnapshot(WORKER_PROCESS_ID, WORKER_PROCESS_STARTED), clock=clock)
    binding = ExactClientWorkerBinding(CLIENT_ID, INSTANCE_ID, 123, 456, 789, WORKER_ID)
    signal = _OperationStopSignal(gate, ledger, binding, WORKER_ID,
                                 WORKER_PROCESS_ID, WORKER_PROCESS_STARTED)
    movement, session, _ = context()
    movement.parent = signal
    assert not signal.is_set()  # Actual permit+projection validated before any acquire.
    assert movement.acquire()
    return ledger, heartbeats, permit, signal, movement, session


def wait_for(predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.005)
    assert predicate()


def test_locked_history_longer_than_native_lease_does_not_block_renewal(tmp_path):
    began = time.monotonic()
    ledger, heartbeats, permit, signal, movement, session = setup(
        tmp_path, lambda: 100 + time.monotonic() - began)
    blocked, release = threading.Event(), threading.Event()

    def history_writer():
        # Same transaction used by reconciliation/report fsync. Actual hot reads
        # must bypass it, not extend authority when the lock fails to arrive.
        with ledger._transaction(ledger._directory(CLIENT_ID)):
            blocked.set()
            assert release.wait(5)

    def current_manager_permits():
        while not release.wait(.15):
            stamp = 100 + time.monotonic() - began
            heartbeats.publish_permit(replace(permit, issued_at=stamp, expires_at=stamp + 2))

    writer = threading.Thread(target=history_writer)
    manager = threading.Thread(target=current_manager_permits)
    writer.start()
    manager.start()
    try:
        assert blocked.wait(3)
        with _OperationMaintenance(movement.operation, signal,
                                   lambda *_: movement.maintain()):
            # Beyond BOTH the native lease and the initial manager permit. Only
            # actually observed fresh permits can keep this same owner alive.
            time.sleep(2.35)
            assert not signal.is_set()
            now = 100 + time.monotonic() - began
            assert now > permit.expires_at
            # A replacement can be issued before the original expires and still
            # authorize this later instant. Requiring issue after that boundary
            # incorrectly rejects valid renewal when the manager is scheduled late.
            assert signal._authority.permit.issued_at > permit.issued_at
            assert signal._authority.permit.expires_at > now
            assert len(session.renew_calls) >= 8
            movement.finish()
            after = len(session.renew_calls)
            time.sleep(.3)
            assert len(session.renew_calls) == after
    finally:
        release.set()
        writer.join(3)
        manager.join(3)
        movement.finish()
    assert session.closed == 1 and len(session.acquire_calls) == 1


def test_blocked_authority_reader_cannot_borrow_unobserved_new_permit(tmp_path, monkeypatch):
    now = [100.]
    ledger, heartbeats, permit, signal, movement, session = setup(tmp_path, lambda: now[0])
    entered, release = threading.Event(), threading.Event()
    original = ledger.current_stop_authority

    def blocked(**kwargs):
        entered.set()
        assert release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(ledger, "current_stop_authority", blocked)
    with _OperationMaintenance(movement.operation, signal, lambda *_: movement.maintain()):
        try:
            assert entered.wait(3)
            heartbeats.publish_permit(replace(permit, issued_at=101., expires_at=103.))
            now[0] = 101.9
            count = len(session.renew_calls)
            wait_for(lambda: len(session.renew_calls) > count)
            now[0] = 102.01
            wait_for(signal.is_set)
            assert "expired" in signal.reason
            after = len(session.renew_calls)
            time.sleep(.3)
            assert len(session.renew_calls) == after
        finally:
            release.set()
        time.sleep(.15)
        # A late read completion or newer permit cannot revive a latched owner.
        assert signal.is_set()
        movement.finish()
    assert session.closed == 1 and len(session.acquire_calls) == 1


def test_actual_finish_serializes_with_pump_renewal_before_session_disposal(tmp_path):
    _, _, _, signal, movement, session = setup(tmp_path, lambda: 100.)
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()

    def renew(grant):
        entered.set()
        assert release.wait(5)
        assert session.closed == 0
        session.renew_calls.append(grant)

    session.renew = renew
    with _OperationMaintenance(movement.operation, signal, lambda *_: movement.maintain()):
        assert entered.wait(3)
        cleanup = threading.Thread(target=lambda: (movement.finish(), closed.set()))
        cleanup.start()
        try:
            assert not closed.wait(.05)
        finally:
            release.set()
            cleanup.join(3)
        assert closed.is_set()
        count = len(session.renew_calls)
        time.sleep(.3)
        assert len(session.renew_calls) == count
    assert session.closed == 1


def test_maintenance_exception_retains_first_failure_and_stops_observer(tmp_path):
    _, _, _, signal, movement, session = setup(tmp_path, lambda: 100.)

    def fail(*_):
        raise RuntimeError("original transport fault")

    pump = _OperationMaintenance(movement.operation, signal, fail)
    with pump:
        wait_for(signal.is_set)
        signal.trip("later explicit cancel", requested=True)
        assert signal.stop_cause.kind == "interrupted"
        assert "original transport fault" in signal.reason
        movement.finish()
    assert not pump.thread.is_alive() and not pump.observer.is_alive()
    assert session.closed == 1


def test_retained_game_handle_close_waits_for_inflight_exact_check():
    from shadowbane_lab.manager.worker_runtime import _SynchronizedGameIdentityGuard
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()

    class Guard:
        def require_current(self):
            entered.set()
            assert release.wait(3)
            assert not closed.is_set()
        def close(self):
            closed.set()

    guard = _SynchronizedGameIdentityGuard(Guard())
    reader = threading.Thread(target=guard.require_current)
    closer = threading.Thread(target=guard.close)
    reader.start()
    try:
        assert entered.wait(3)
        closer.start()
        assert not closed.wait(.05)
    finally:
        release.set()
        reader.join(3)
        closer.join(3)
    assert closed.is_set()


def test_replacement_issued_before_original_expiry_authorizes_later_instant(tmp_path):
    now = [100.]
    _, heartbeats, permit, signal, movement, session = setup(tmp_path, lambda: now[0])
    replacement = replace(permit, issued_at=101.5, expires_at=103.5)
    now[0] = replacement.issued_at
    heartbeats.publish_permit(replacement)
    signal.refresh()  # The real observer reads it while prior authority is valid.
    now[0] = 102.35
    assert permit.expires_at < now[0] < replacement.expires_at
    assert not signal.is_set()
    assert signal._authority.permit == replacement
    assert movement.maintain()
    now[0] = replacement.expires_at
    assert signal.is_set()
    movement.finish()
    assert session.closed == 1
