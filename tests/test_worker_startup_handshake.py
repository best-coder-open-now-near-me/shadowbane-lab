"""Worker launch/stop identity handoff, including Windows redirector PIDs."""

import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot
from shadowbane_lab.manager.worker import WorkerHeartbeatLedger, WorkerRuntimeState
from shadowbane_lab.manager.worker_runtime import (
    ExactClientWorkerBinding,
    ExactClientWorkerError,
    ManagedWorkerController,
    SubprocessWorkerLauncher,
)
from tests import test_manager_application as app
from tests import test_manager_worker_runtime as f


def setup(tmp_path):
    ledger = WorkerHeartbeatLedger(f._manifest(), tmp_path)
    inspector = f._ProcessInspector(
        ProcessLifetimeSnapshot(1736, 100),
        ProcessLifetimeSnapshot(7028, 200, parent_process_id=1736),
    )
    launcher = SubprocessWorkerLauncher(
        manifest_path=tmp_path / "manifest.json",
        worker_state_directory=tmp_path,
        log_directory=tmp_path / "logs",
        startup_timeout_seconds=0.02,
    )
    controller = ManagedWorkerController(f._manifest(), ledger, inspector, launcher)
    child = SimpleNamespace(pid=1736, poll=lambda: None)
    return ledger, inspector, launcher, controller, child


def publish(ledger, binding, *, pid=7028, creation=200, **changes):
    record = replace(
        f._heartbeat(instance_id=binding.instance_id),
        worker_id=binding.worker_id,
        process_id=pid,
        process_started_at_100ns=creation,
        **changes,
    )
    ledger.publish(record)
    return record


def popen_publish(ledger, child, **changes):
    def popen(argv, **kwargs):
        binding = replace(
            ExactClientWorkerBinding.from_client(f.CLIENT_ID, f._client()),
            worker_id=argv[argv.index("--worker-id") + 1],
        )
        publish(ledger, binding, **changes)
        return child

    return popen


def test_redirector_pid_never_becomes_worker_stop_address(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=popen_publish(ledger, child),
    ):
        assert controller.ensure_started(f.CLIENT_ID, f._client()) == 7028
    reservation = json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())
    assert (reservation["process_id"], reservation["process_started_at_100ns"]) == (7028, 200)
    assert controller.request_stop(f.CLIENT_ID, reason="exact attachment replaced") == 1
    request = ledger.inspect_stop_request(f.CLIENT_ID, reservation["worker_id"])
    assert (request.process_id, request.process_started_at_100ns) == (7028, 200)
    # Existing worker runtime must still fail closed on the redirector tuple.
    runtime = f.ExactClientWorkerRuntime(
        f._manifest(),
        replace(
            ExactClientWorkerBinding.from_client(f.CLIENT_ID, f._client()),
            worker_id=reservation["worker_id"],
        ),
        ledger,
        f._StaticRegistry(f._client()),
        inspector,
        process_id=7028,
        game_identity_guard_factory=f._GameIdentityGuard,
    )
    assert runtime.serve() == 0
    assert ledger.inspect(f.CLIENT_ID).records[0].runtime_state is WorkerRuntimeState.STOPPED


def test_timeout_keeps_reservation_and_stop_resolves_later_heartbeat(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child
    ) as popen:
        for _ in range(2):
            with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
                controller.ensure_started(f.CLIENT_ID, f._client())
        with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
            controller.request_stop(f.CLIENT_ID, reason="stop during startup")
        assert popen.call_count == 1
    reservation = json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())
    assert reservation["state"] == "unverified"
    assert ledger.inspect_stop_request(f.CLIENT_ID, reservation["worker_id"]) is None
    binding = launcher._bindings[reservation["worker_id"]]
    publish(ledger, binding)
    assert controller.request_stop(f.CLIENT_ID, reason="stop during startup") == 1
    request = ledger.inspect_stop_request(f.CLIENT_ID, reservation["worker_id"])
    assert request.process_id == 7028
    assert controller.ensure_started(f.CLIENT_ID, f._client()) is None


@pytest.mark.parametrize("bad", ["instance", "pid", "creation", "worker"])
def test_wrong_startup_identity_cannot_complete_handoff(tmp_path, bad):
    ledger, inspector, launcher, controller, child = setup(tmp_path)

    def popen(argv, **kwargs):
        binding = replace(
            ExactClientWorkerBinding.from_client(f.CLIENT_ID, f._client()),
            worker_id=argv[argv.index("--worker-id") + 1],
        )
        if bad == "instance":
            binding = replace(binding, instance_id=f._client(process_id=202).instance_id)
        if bad == "worker":
            binding = replace(binding, worker_id="worker-" + "a" * 32)
        publish(
            ledger,
            binding,
            pid=999 if bad == "pid" else 7028,
            creation=201 if bad == "creation" else 200,
        )
        return child

    with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen", side_effect=popen):
        with pytest.raises(ExactClientWorkerError, match="identity mismatch|attachment recovery"):
            controller.ensure_started(f.CLIENT_ID, f._client())
    assert (
        json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())["state"] == "unverified"
    )


def test_verified_handshake_rejects_same_uuid_new_process_lifetime(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=popen_publish(ledger, child),
    ):
        controller.ensure_started(f.CLIENT_ID, f._client())
    binding = next(iter(launcher._bindings.values()))
    publish(ledger, binding, creation=201, sequence=2)
    inspector.processes[7028] = ProcessLifetimeSnapshot(7028, 201)
    with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
        launcher.recover(1736, inspector, worker_id=binding.worker_id, ledger=ledger,
                         client_id=f.CLIENT_ID, instance_id=binding.instance_id)


def test_reattach_waits_for_real_exit_then_starts_one_replacement(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    # The logical slot is detached; its prior exact worker has not exited yet.
    session = app._RecordingSession(
        app.ManagerSessionSnapshot(
            node_id=f.NODE_ID, slots=(app._slot(f.CLIENT_ID),)
        )
    )
    application, _ = app._application(session, f._client(), worker_controller=controller)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=popen_publish(ledger, child),
    ) as popen:
        controller.ensure_started(f.CLIENT_ID, f._client())
        old = ledger.inspect(f.CLIENT_ID).records[0]
        application.execute("attach", client_id=f.CLIENT_ID, instance_id=f._client().instance_id)
        assert ledger.inspect_stop_request(f.CLIENT_ID, old.worker_id).process_id == 7028
        application.reconcile_instances()
        assert popen.call_count == 1
        # Positive OS exit, followed by the next explicitly pending reconciliation.
        del inspector.processes[7028]
        next_child = SimpleNamespace(pid=1800, poll=lambda: None)
        inspector.processes[7030] = ProcessLifetimeSnapshot(7030, 300, parent_process_id=1800)
        inspector.processes[1800] = ProcessLifetimeSnapshot(1800, 250)
        popen.side_effect = popen_publish(ledger, next_child, pid=7030, creation=300)
        application.reconcile_instances()
        assert popen.call_count == 2
        replacement = [r for r in ledger.inspect(f.CLIENT_ID).records if r.process_id == 7030][0]
        assert replacement.dispatch_ready and replacement.worker_id != old.worker_id
        assert ledger.inspect_stop_request(f.CLIENT_ID, replacement.worker_id) is None
        application.reconcile_instances()
        assert popen.call_count == 2


@pytest.mark.parametrize("cancel", ["pause", "detach", "close", "lifetime", "shutdown"])
def test_pending_replacement_is_cancelled_by_exact_lifecycle(tmp_path, cancel):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    # The logical slot is detached; its prior exact worker has not exited yet.
    session = app._RecordingSession(
        app.ManagerSessionSnapshot(
            node_id=f.NODE_ID, slots=(app._slot(f.CLIENT_ID),)
        )
    )
    application, _ = app._application(session, f._client(), worker_controller=controller)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=popen_publish(ledger, child),
    ) as popen:
        controller.ensure_started(f.CLIENT_ID, f._client())
        application.execute("attach", client_id=f.CLIENT_ID, instance_id=f._client().instance_id)
        if cancel == "shutdown":
            application.revoke_all_workers(reason="shutdown")
        elif cancel == "lifetime":
            session.snapshot_value = app.ManagerSessionSnapshot(
                node_id=f.NODE_ID,
                slots=(app._slot(f.CLIENT_ID, instance_id=f._client(process_id=202).instance_id),),
            )
        else:
            application.execute(cancel, client_id=f.CLIENT_ID, instance_id=f._client().instance_id)
        del inspector.processes[7028]
        application.reconcile_instances()
        assert popen.call_count == 1


def test_real_interpreter_startup_and_exact_stop_without_game(tmp_path):
    """Exercise real Popen/venv redirection with the production worker loop."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    from tests.test_runtime_hardening import ProcessInspector

    ledger = WorkerHeartbeatLedger(f._manifest(), tmp_path)
    launcher = SubprocessWorkerLauncher(
        manifest_path=tmp_path / "manifest.json",
        worker_state_directory=tmp_path,
        log_directory=tmp_path / "logs",
    )
    controller = ManagedWorkerController(f._manifest(), ledger, ProcessInspector(), launcher)
    original_popen = subprocess.Popen
    script = """
import sys, time
from dataclasses import replace
from pathlib import Path
from tests import test_manager_worker_runtime as f
from tests.test_runtime_hardening import ProcessInspector
from shadowbane_lab.manager.worker_runtime import ExactClientWorkerBinding, ExactClientWorkerRuntime
from shadowbane_lab.manager.worker import WorkerHeartbeatLedger
binding = replace(ExactClientWorkerBinding.from_client(f.CLIENT_ID, f._client()),
                  worker_id=sys.argv[2])
class Bound:
    deadline = time.monotonic() + 8
    def is_set(self):
        return time.monotonic() >= self.deadline
runtime = ExactClientWorkerRuntime(f._manifest(), binding,
    WorkerHeartbeatLedger(f._manifest(), Path(sys.argv[1])),
    f._StaticRegistry(f._client()), ProcessInspector(), heartbeat_interval_seconds=0.1,
    game_identity_guard_factory=f._GameIdentityGuard)
sys.exit(runtime.serve(stop_signal=Bound()))
"""
    children = []

    def launch_test_runtime(argv, **kwargs):
        env = dict(
            os.environ, PYTHONPATH=os.pathsep.join((str(Path.cwd() / "src"), str(Path.cwd())))
        )
        child = original_popen(
            [sys.executable, "-c", script, str(tmp_path), argv[argv.index("--worker-id") + 1]],
            env=env,
            **kwargs,
        )
        children.append(child)
        return child

    try:
        with patch(
            "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
            side_effect=launch_test_runtime,
        ):
            pid = controller.ensure_started(f.CLIENT_ID, f._client())
        record = ledger.inspect(f.CLIENT_ID).records[0]
        assert pid == record.process_id
        if os.name == "nt" and sys.prefix != sys.base_prefix:
            assert children[0].pid != pid  # Actual venv redirector, not a synthetic assumption.
        assert controller.request_stop(f.CLIENT_ID, reason="synthetic worker completed") == 1
        assert children[0].wait(timeout=12) == 0
        final = ledger.inspect(f.CLIENT_ID).records[0]
        assert final.runtime_state is WorkerRuntimeState.STOPPED
        assert final.detail == "synthetic worker completed"
        assert not final.emergency_stop
    finally:
        for child in children:
            child.wait(timeout=12)


@pytest.mark.parametrize("parent,creation", [(999, 200), (None, 200), (1736, 99)])
def test_heartbeat_must_descend_from_retained_launcher(tmp_path, parent, creation):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    inspector.processes[7028] = ProcessLifetimeSnapshot(7028, creation, parent_process_id=parent)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=popen_publish(ledger, child, creation=creation),
    ):
        with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
            controller.ensure_started(f.CLIENT_ID, f._client())


@pytest.mark.parametrize("pid,creation", [(1736, 100), (7028, 201)])
def test_runtime_still_rejects_wrong_stop_lifetime(tmp_path, pid, creation):
    from shadowbane_lab.manager.worker import WorkerStopRequest

    ledger, inspector, launcher, controller, child = setup(tmp_path)
    binding = replace(
        ExactClientWorkerBinding.from_client(f.CLIENT_ID, f._client()),
        worker_id="worker-" + "1" * 32,
    )
    ledger.publish_stop_request(
        WorkerStopRequest(
            node_id=f.NODE_ID,
            client_id=f.CLIENT_ID,
            worker_id=binding.worker_id,
            process_id=pid,
            process_started_at_100ns=creation,
            requested_at=100.0,
            reason="wrong lifetime must fail",
        )
    )
    runtime = f.ExactClientWorkerRuntime(
        f._manifest(), binding, ledger, f._StaticRegistry(f._client()), inspector, process_id=7028,
        game_identity_guard_factory=f._GameIdentityGuard,
    )
    assert runtime.serve() == 1
    record = ledger.inspect(f.CLIENT_ID).records[0]
    assert record.emergency_stop
    assert "does not own this exact process lifetime" in record.detail


def test_launcher_exit_does_not_retire_live_published_interpreter(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child):
        with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
            controller.ensure_started(f.CLIENT_ID, f._client())
    binding = next(iter(launcher._bindings.values()))
    publish(ledger, binding)
    child.poll = lambda: 0
    with pytest.raises(ExactClientWorkerError, match="outlived or lost its launcher"):
        controller.ensure_started(f.CLIENT_ID, f._client())
    reservation = json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())
    assert reservation["state"] == "unverified"


def test_no_heartbeat_launcher_exit_cannot_authorize_relaunch(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child
    ) as popen:
        with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
            controller.ensure_started(f.CLIENT_ID, f._client())
        child.poll = lambda: 0
        for _ in range(2):
            with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
                controller.ensure_started(f.CLIENT_ID, f._client())
        with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
            controller.request_stop(f.CLIENT_ID, reason="stop unresolved startup")
        assert popen.call_count == 1
    assert (
        json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())["state"] == "unverified"
    )


def test_verified_worker_retains_stop_identity_after_redirector_exit(tmp_path):
    ledger, inspector, launcher, controller, child = setup(tmp_path)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=popen_publish(ledger, child),
    ):
        controller.ensure_started(f.CLIENT_ID, f._client())
    binding = next(iter(launcher._bindings.values()))
    child.poll = lambda: 0
    actual = launcher.recover(1736, inspector, worker_id=binding.worker_id, ledger=ledger,
                         client_id=f.CLIENT_ID, instance_id=binding.instance_id)
    assert actual.process_id == 7028
    assert controller.request_stop(f.CLIENT_ID, reason="stop orphaned exact worker") == 1
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id).process_id == 7028
    del inspector.processes[7028]
    assert launcher.recover(1736, inspector, worker_id=binding.worker_id, ledger=ledger,
                         client_id=f.CLIENT_ID, instance_id=binding.instance_id) is None
