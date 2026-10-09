"""Restart recovery uses the recorded interpreter lifetime, never launcher exit."""
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot
from shadowbane_lab.manager.worker import WorkerRuntimeState
from shadowbane_lab.manager.worker_runtime import (
    ExactClientWorkerError,
    ManagedWorkerController,
    SubprocessWorkerLauncher,
    WorkerActivationState,
)
from tests import test_manager_application as app
from tests import test_manager_worker_runtime as f
from tests import test_worker_activation as a
from tests import test_worker_startup_handshake as h


def restarted(tmp_path, *, heartbeat=True):
    ledger, inspector, _, _, _, path, binding = a.pending(tmp_path)
    record = (h.publish(ledger, binding, runtime_state=WorkerRuntimeState.STOPPED,
                        emergency_stop=True, dispatch_ready=False) if heartbeat else None)
    launcher = SubprocessWorkerLauncher(manifest_path=tmp_path / "manifest.json",
        worker_state_directory=tmp_path, log_directory=tmp_path / "logs",
        startup_timeout_seconds=0.01)
    controller = ManagedWorkerController(f._manifest(), ledger, inspector, launcher)
    return ledger, inspector, launcher, controller, path, binding, record


@pytest.mark.parametrize("reused", [False, True])
@pytest.mark.parametrize("entry", ["stop", "recover", "replace"])
def test_restart_retires_exited_interpreter_and_can_launch_replacement(tmp_path, reused, entry):
    ledger, inspector, launcher, controller, path, binding, record = restarted(tmp_path)
    if reused:
        inspector.processes[7028] = ProcessLifetimeSnapshot(7028, 201)
    else:
        del inspector.processes[7028]
    # The original redirector remains alive: it is not the exit predicate.
    assert inspector.inspect(1736) is not None
    if entry == "stop":
        assert controller.request_stop(f.CLIENT_ID, reason="explicit stop") == 0
        assert not path.exists()
    elif entry == "recover":
        result = controller.recover_activation(f.CLIENT_ID, f._client())
        assert result.state is WorkerActivationState.ABSENT
        assert not path.exists()
    else:
        inspector.processes[8000] = ProcessLifetimeSnapshot(8000, 300)
        inspector.processes[8001] = ProcessLifetimeSnapshot(8001, 301, parent_process_id=8000)
        child = SimpleNamespace(pid=8000, poll=lambda: None)
        def launch(argv, **kwargs):
            new_binding = replace(binding,
                instance_id=f._client(process_id=202).instance_id,
                worker_id=argv[argv.index("--worker-id") + 1])
            h.publish(ledger, new_binding, pid=8001, creation=301)
            return child
        with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen",
                   side_effect=launch) as popen:
            assert controller.ensure_started(f.CLIENT_ID, f._client(process_id=202)) == 8001
            assert controller.ensure_started(f.CLIENT_ID, f._client(process_id=202)) == 8001
            assert popen.call_count == 1
        assert json.loads(path.read_text())["worker_id"] != binding.worker_id
    assert record in ledger.inspect(f.CLIENT_ID).records
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id) is None


@pytest.mark.parametrize("bad", [
    "live", "missing", "wrong_instance", "wrong_worker", "malformed", "os_error", "wrong_pid",
])
def test_restart_does_not_adopt_or_retire_ambiguous_worker(tmp_path, bad):
    ledger, inspector, launcher, controller, path, binding, record = restarted(
        tmp_path, heartbeat=bad not in {"missing", "wrong_instance", "wrong_worker"})
    if bad == "wrong_instance":
        h.publish(ledger, replace(binding, instance_id=f._client(process_id=202).instance_id))
    elif bad == "wrong_worker":
        h.publish(ledger, replace(binding, worker_id="worker-" + "f" * 32))
    elif bad == "malformed":
        (path.parent / (binding.worker_id + ".json")).write_text("{}")
    if bad != "live":
        inspector.processes.pop(7028, None)
    else:
        # Launcher absence and a matching heartbeat (even STOPPED) do not prove exit.
        del inspector.processes[1736]
    before = path.read_bytes()
    with patch.object(launcher, "launch", side_effect=AssertionError("no launch")):
        if bad == "os_error":
            inspector.inspect = lambda pid: (_ for _ in ()).throw(OSError("access denied"))
        elif bad == "wrong_pid":
            inspector.inspect = lambda pid: ProcessLifetimeSnapshot(9999, 200)
        with pytest.raises((ExactClientWorkerError, OSError)):
            controller.request_stop(f.CLIENT_ID, reason="explicit stop")
    assert path.read_bytes() == before
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id) is None


@pytest.mark.parametrize("change", ["heartbeat", "reservation", "lifetime"])
def test_recovery_rechecks_evidence_before_retiring(tmp_path, change):
    ledger, inspector, _, controller, path, binding, record = restarted(tmp_path)
    before = path.read_bytes()
    calls = 0
    def inspect(pid):
        nonlocal calls
        calls += 1
        if calls == 1:
            if change == "heartbeat":
                h.publish(ledger, binding, sequence=record.sequence + 1)
            elif change == "reservation":
                value = json.loads(before)
                value["process_id"] = 3333
                path.write_text(json.dumps(value))
            return None
        return ProcessLifetimeSnapshot(7028, 200) if change == "lifetime" else None
    inspector.inspect = inspect
    with pytest.raises(ExactClientWorkerError, match="changed during recovery"):
        controller.request_stop(f.CLIENT_ID, reason="explicit stop")
    assert path.exists()
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id) is None


def test_manager_attach_recovers_stopped_predecessor_after_restart(tmp_path):
    ledger, inspector, _, controller, path, binding, record = restarted(tmp_path)
    del inspector.processes[7028]
    del inspector.processes[1736]
    session = app._RecordingSession(app.ManagerSessionSnapshot(
        node_id=f.NODE_ID, slots=(app._slot(f.CLIENT_ID),)))
    application, _ = app._application(session, f._client(), worker_controller=controller)
    child = SimpleNamespace(pid=8000, poll=lambda: None)
    inspector.processes[8000] = ProcessLifetimeSnapshot(8000, 300)
    inspector.processes[8001] = ProcessLifetimeSnapshot(8001, 301, parent_process_id=8000)
    with patch("shadowbane_lab.manager.worker_runtime.subprocess.Popen",
               side_effect=h.popen_publish(ledger, child, pid=8001, creation=301)) as popen:
        application.execute("attach", client_id=f.CLIENT_ID, instance_id=f._client().instance_id)
        application.reconcile_instances()
        assert popen.call_count == 1
    assert record in ledger.inspect(f.CLIENT_ID).records
    assert ledger.inspect_stop_request(f.CLIENT_ID, binding.worker_id) is None
    assert json.loads(path.read_text())["process_id"] == 8001
