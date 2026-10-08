"""Public controller ownership and paused-manager handshake recovery."""

import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from shadowbane_lab.manager.application import ManagerDashboardApplication
from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot
from shadowbane_lab.manager.worker import WorkerHeartbeatLedger, WorkerSupervisor
from shadowbane_lab.manager.worker_runtime import (
    ExactClientWorkerError,
    ManagedWorkerController,
)
from shadowbane_lab.manager.worker_runtime import (
    WorkerActivationState as State,
)
from tests import test_manager_application as app
from tests import test_manager_worker_runtime as f
from tests import test_worker_startup_handshake as h


def pending(tmp_path):
    ledger, inspector, launcher, controller, child = h.setup(tmp_path)
    with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child):
        with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
            controller.ensure_started(f.CLIENT_ID, f._client())
    path = next(tmp_path.rglob(".launch-reservation"))
    binding = next(iter(launcher._bindings.values()))
    return ledger, inspector, launcher, controller, child, path, binding


def manager(ledger, inspector, controller, *, paused=True, clock=lambda: 100.0):
    session = app._RecordingSession(app.ManagerSessionSnapshot(
        node_id=f.NODE_ID, slots=(app._slot(f.CLIENT_ID, instance_id=f._client().instance_id,
            state=app.ManagerSlotState.PAUSED if paused else app.ManagerSlotState.ATTACHED),),
    ))
    registry = f._StaticRegistry(f._client())
    supervisor = WorkerSupervisor(ledger, inspector, clock=clock)
    application = ManagerDashboardApplication(
        f._manifest(), session, registry, supervisor, worker_controller=controller,
    )
    return application, session, registry


def test_paused_healthy_worker_has_pending_attachment_then_recovers_once(tmp_path):
    ledger, inspector, launcher, controller, child, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    application, session, _ = manager(ledger, inspector, controller)
    before = path.read_bytes()
    status = application.status()["slots"][0]
    assert status["worker"]["state"] == "healthy"
    assert status["worker_activation"]["state"] == "pending"
    assert status["worker_activation"]["launcher_process_id"] == 1736
    assert status["worker_activation"]["worker_process_id"] is None
    assert status["dispatch_enabled"] is False
    assert path.read_bytes() == before  # Status is inspection, not attachment.
    with (
        patch.object(launcher, "launch", side_effect=AssertionError("must not launch")),
        patch.object(launcher, "recover", side_effect=AssertionError("must not wait")),
        patch("shadowbane_lab.manager.worker_runtime.time.sleep",
              side_effect=AssertionError("must not sleep")),
    ):
        application.supervise()
        recorded = path.read_bytes()
        application.supervise()
        assert path.read_bytes() == recorded
    status = application.status()["slots"][0]
    assert status["worker"]["state"] == "healthy"
    assert status["worker_activation"]["state"] == "attached"
    assert status["worker_activation"]["worker_process_id"] == 7028
    assert status["worker_activation"]["worker_started_at_100ns"] == 200
    assert status["dispatch_enabled"] is False
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False
    session.snapshot_value = replace(session.snapshot_value,
        slots=(app._slot(f.CLIENT_ID, instance_id=f._client().instance_id),))
    application.supervise()
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is True
    assert controller.request_stop(f.CLIENT_ID, reason="explicit stop") == 1
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id).process_id == 7028


def test_pending_healthy_worker_cannot_dispatch_before_attachment(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    application, _, _ = manager(ledger, inspector, controller, paused=False)
    status = application.status()["slots"][0]
    assert status["lifecycle_dispatch_enabled"] is True
    assert status["worker"]["state"] == "healthy"
    assert "attachment" in status["worker"]["detail"]
    assert "paused" not in status["worker"]["detail"]
    assert status["dispatch_enabled"] is False
    assert json.loads(path.read_text())["state"] == "unverified"


def test_missing_retained_launcher_never_adopts_healthy_heartbeat(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    launcher._children.clear()
    before = path.read_bytes()
    application, _, _ = manager(ledger, inspector, controller, paused=False)
    application.supervise()
    activation = application.status()["slots"][0]["worker_activation"]
    assert activation["state"] == "recovery_required"
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False
    assert path.read_bytes() == before


def test_durable_attachment_survives_manager_restart_without_popen(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    assert controller.recover_activation(f.CLIENT_ID, f._client()).state is State.ATTACHED
    launcher._children.clear()
    launcher._bindings.clear()
    launcher._worker_processes.clear()
    before = path.read_bytes()
    application, _, _ = manager(ledger, inspector, controller, paused=False)
    application.supervise()
    assert application.status()["slots"][0]["worker_activation"]["state"] == "attached"
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is True
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["unbound", "replacement", "shutdown"])
def test_ineligible_slot_does_not_recover_existing_launch(tmp_path, change):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    application, session, registry = manager(ledger, inspector, controller)
    if change == "unbound":
        session.snapshot_value = replace(session.snapshot_value, slots=(app._slot(f.CLIENT_ID),))
    elif change == "replacement":
        registry.clients = (f._client(process_id=202),)
    else:
        application.revoke_all_workers(reason="shutdown")
    before = path.read_bytes()
    with patch.object(launcher, "poll_recovery", side_effect=AssertionError("must not recover")):
        application.supervise()
    assert path.read_bytes() == before
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False


def test_no_heartbeat_poll_does_not_wait_or_launch(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    application, _, _ = manager(ledger, inspector, controller)
    before = path.read_bytes()
    with (
        patch.object(launcher, "launch", side_effect=AssertionError("must not launch")),
        patch("shadowbane_lab.manager.worker_runtime.time.sleep",
              side_effect=AssertionError("must not sleep")),
    ):
        application.supervise()
    assert controller.inspect_activation(f.CLIENT_ID, f._client()).state is State.PENDING
    assert path.read_bytes() == before


def test_launcher_exit_without_verified_child_retains_reservation(tmp_path):
    ledger, inspector, launcher, controller, child, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    child.poll = lambda: 0
    before = path.read_bytes()
    assert controller.recover_activation(f.CLIENT_ID, f._client()).state is State.RECOVERY_REQUIRED
    assert path.read_bytes() == before


def test_verified_child_exit_and_pid_reuse_cannot_be_reported_attached(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    controller.recover_activation(f.CLIENT_ID, f._client())
    inspector.processes[7028] = ProcessLifetimeSnapshot(7028, 201, parent_process_id=1736)
    result = controller.inspect_activation(f.CLIENT_ID, f._client())
    assert result.state is State.EXITED
    assert result.attached_worker is None


def test_attachment_does_not_override_expired_heartbeat(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    application, _, _ = manager(ledger, inspector, controller, paused=False, clock=lambda: 200)
    application.supervise()
    status = application.status()["slots"][0]
    assert status["worker_activation"]["state"] == "attached"
    assert status["worker"]["state"] == "stale"
    assert status["dispatch_enabled"] is False
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False


def test_stop_request_survives_recovery_and_blocks_dispatch(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    controller.request_stop(f.CLIENT_ID, reason="attachment replaced")
    application, _, _ = manager(ledger, inspector, controller, paused=False)
    application.supervise()
    assert application.status()["slots"][0]["worker_activation"]["state"] == "stopping"
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id).process_id == 7028


def test_same_instance_copied_reservation_cannot_borrow_another_slot_launcher(tmp_path):
    ledger, inspector, launcher, _, child = h.setup(tmp_path)
    ledger = WorkerHeartbeatLedger(app._manifest(), tmp_path)
    controller = ManagedWorkerController(app._manifest(), ledger, inspector, launcher)
    with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child):
        with pytest.raises(ExactClientWorkerError):
            controller.ensure_started(f.CLIENT_ID, f._client())
    original = next(tmp_path.rglob(".launch-reservation"))
    copied = original.parent.parent / "client-02" / original.name
    copied.parent.mkdir()
    copied.write_bytes(original.read_bytes())
    binding = next(iter(launcher._bindings.values()))
    h.publish(ledger, binding)
    before = copied.read_bytes()
    assert controller.inspect_activation("client-02", f._client()).state is State.RECOVERY_REQUIRED
    assert controller.recover_activation("client-02", f._client()).state is State.RECOVERY_REQUIRED
    with pytest.raises(ExactClientWorkerError, match="another slot"):
        controller.request_stop("client-02", reason="copied slot")
    assert copied.read_bytes() == before
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id) is None
    assert controller.recover_activation(f.CLIENT_ID, f._client()).state is State.ATTACHED


def test_status_rejects_reservation_changed_during_inspection(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    controller.recover_activation(f.CLIENT_ID, f._client())
    original = controller._read_reservation
    calls = []
    def racing_read(path):
        result = original(path)
        calls.append(True)
        if len(calls) == 2:
            result["worker_id"] = "worker-" + "b" * 32
        return result
    with patch.object(controller, "_read_reservation", side_effect=racing_read):
        result = controller.inspect_activation(f.CLIENT_ID, f._client())
    assert result.state is State.UNAVAILABLE
    assert result.attached_worker is None


def test_supervisor_cannot_publish_permit_for_different_attached_tuple(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    supervisor = WorkerSupervisor(ledger, inspector, clock=lambda: 100)
    result = supervisor.inspect(f.CLIENT_ID, instance_id=binding.instance_id,
        lifecycle_dispatch_enabled=True, attached_worker=(binding.worker_id, 1736, 100))
    assert result.state.value == "healthy"  # Health and attachment are distinct.
    assert result.dispatch_allowed is False
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False


@pytest.mark.parametrize("phase,pid,created", [
    ("started", 7028, None), ("unverified", 7028, 200), ("launching", 1736, None),
])
def test_malformed_phase_cannot_be_used_as_activation_proof(tmp_path, phase, pid, created):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    value = json.loads(path.read_text())
    value.update(state=phase, process_id=pid, process_started_at_100ns=created)
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    result = controller.recover_activation(f.CLIENT_ID, f._client())
    assert result.state is State.RECOVERY_REQUIRED
    assert result.attached_worker is None
    assert path.read_bytes() == before


def test_pending_slot_does_not_starve_unrelated_attached_worker_permit(tmp_path):
    ledger, inspector, launcher, _, child = h.setup(tmp_path)
    manifest = app._manifest()
    ledger = WorkerHeartbeatLedger(manifest, tmp_path)
    controller = ManagedWorkerController(manifest, ledger, inspector, launcher)
    with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child):
        with pytest.raises(ExactClientWorkerError):
            controller.ensure_started(f.CLIENT_ID, f._client())
    second = f._client(process_id=202)
    second_child = type(child)(pid=1800, poll=lambda: None)
    inspector.processes[1800] = ProcessLifetimeSnapshot(1800, 250)
    inspector.processes[7030] = ProcessLifetimeSnapshot(7030, 300, parent_process_id=1800)
    def publish_second(argv, **kwargs):
        ledger.publish(replace(f._heartbeat(instance_id=second.instance_id),
            client_id="client-02", worker_id=argv[argv.index("--worker-id") + 1],
            process_id=7030, process_started_at_100ns=300))
        return second_child
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen", side_effect=publish_second,
    ):
        assert controller.ensure_started("client-02", second) == 7030
    session = app._RecordingSession(app.ManagerSessionSnapshot(node_id=f.NODE_ID, slots=(
        app._slot(f.CLIENT_ID, instance_id=f._client().instance_id),
        app._slot("client-02", instance_id=second.instance_id),
    )))
    application = ManagerDashboardApplication(manifest, session,
        f._StaticRegistry(f._client(), second),
        WorkerSupervisor(ledger, inspector, clock=lambda: 100),
        worker_controller=controller)
    with patch("shadowbane_lab.manager.worker_runtime.time.sleep",
               side_effect=AssertionError("pending slot must not wait")):
        application.supervise()
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False
    assert ledger.inspect_permit("client-02").allowed is True


def test_contended_attachment_is_unavailable_then_recovers_without_relaunch(tmp_path):
    import threading

    from shadowbane_lab.record_store import exclusive_record_lock
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    entered, release = threading.Event(), threading.Event()
    def hold_lock():
        with exclusive_record_lock(path.parent / ".launch.lock"):
            entered.set()
            assert release.wait(3)
    thread = threading.Thread(target=hold_lock)
    thread.start()
    try:
        assert entered.wait(3)
        before = path.read_bytes()
        result = controller.recover_activation(f.CLIENT_ID, f._client())
        assert result.state is State.UNAVAILABLE
        assert result.attached_worker is None
        assert path.read_bytes() == before
    finally:
        release.set()
        thread.join(3)
    assert controller.recover_activation(f.CLIENT_ID, f._client()).state is State.ATTACHED


def test_read_only_handshake_observation_does_not_cache_new_interpreter(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    before = path.read_bytes()
    assert controller.inspect_activation(f.CLIENT_ID, f._client()).state is State.PENDING
    assert launcher._worker_processes == {}
    assert path.read_bytes() == before


def test_bad_heartbeat_reports_recovery_required_without_changing_reservation(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding, creation=201)
    before = path.read_bytes()
    assert controller.inspect_activation(f.CLIENT_ID, f._client()).state is State.RECOVERY_REQUIRED
    assert controller.recover_activation(f.CLIENT_ID, f._client()).state is State.RECOVERY_REQUIRED
    assert path.read_bytes() == before
    assert launcher._worker_processes == {}


def test_explicit_reuse_records_external_worker_but_status_alone_cannot_adopt(tmp_path):
    ledger, inspector, launcher, controller, _ = h.setup(tmp_path)
    record = replace(f._heartbeat(instance_id=f._client().instance_id),
        process_id=7028, process_started_at_100ns=200)
    ledger.publish(record)
    application, _, _ = manager(ledger, inspector, controller, paused=False)
    application.supervise()
    assert application.status()["slots"][0]["worker_activation"]["state"] == "absent"
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is False
    with patch.object(launcher, "launch", side_effect=AssertionError("reuse must not launch")):
        assert controller.ensure_started(f.CLIENT_ID, f._client()) == 7028
    application.supervise()
    assert application.status()["slots"][0]["worker_activation"]["state"] == "attached"
    assert ledger.inspect_permit(f.CLIENT_ID).allowed is True


def test_explicit_reuse_cannot_overwrite_different_live_reserved_lifetime(tmp_path):
    ledger, inspector, launcher, controller, _, path, binding = pending(tmp_path)
    h.publish(ledger, binding)
    controller.recover_activation(f.CLIENT_ID, f._client())
    replacement = replace(ledger.inspect(f.CLIENT_ID).records[0],
        worker_id="worker-" + "c" * 32, process_id=8000, process_started_at_100ns=400)
    inspector.processes[8000] = ProcessLifetimeSnapshot(8000, 400)
    before = path.read_bytes()
    # A lost old heartbeat cannot erase the positive OS proof of its reservation.
    with patch.object(ledger, "inspect", return_value=replace(
        ledger.inspect(f.CLIENT_ID), records=(replacement,))):
        with pytest.raises(ExactClientWorkerError, match="another live reservation"):
            controller.ensure_started(f.CLIENT_ID, f._client())
    assert path.read_bytes() == before


def test_stop_racing_explicit_reuse_does_not_publish_attachment(tmp_path):
    ledger, inspector, launcher, controller, _ = h.setup(tmp_path)
    record = replace(f._heartbeat(instance_id=f._client().instance_id),
        process_id=7028, process_started_at_100ns=200)
    ledger.publish(record)
    with patch.object(ledger, "inspect_stop_request", side_effect=[None, object()]):
        with pytest.raises(ExactClientWorkerError, match="changed during explicit attachment"):
            controller.ensure_started(f.CLIENT_ID, f._client())
    assert not tuple(tmp_path.rglob(".launch-reservation"))
