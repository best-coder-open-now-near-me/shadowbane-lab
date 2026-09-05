"""Production ownership regressions with controlled thread/process boundaries."""

from __future__ import annotations

import json
import multiprocessing
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from shadowbane_lab.manager.session import ManagerSession, SessionSlotBoundError
from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot, Win32ProcessLifetimeInspector
from shadowbane_lab.manager.worker import (
    WorkerHeartbeatError,
    WorkerHeartbeatLedger,
    WorkerHeartbeatPublisher,
    WorkerRuntimeState,
)
from shadowbane_lab.manager.worker_runtime import ExactClientWorkerError, ManagedWorkerController
from tests import test_manager_application as app_fixture
from tests import test_manager_session as session_fixture
from tests import test_manager_worker as heartbeat_fixture
from tests import test_manager_worker_runtime as worker_fixture


class ProcessInspector:
    def inspect(self, pid):
        if os.name == "nt":
            return Win32ProcessLifetimeInspector().inspect(pid)
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            return ProcessLifetimeSnapshot(pid, int(fields[19]))
        except FileNotFoundError:
            return None


def hold_worker(stop):
    stop.wait(20)


def launch_contender(root, barrier, results, stop):
    context = multiprocessing.get_context("spawn")
    children = []

    class Launcher:
        def launch(self, binding):
            child = context.Process(target=hold_worker, args=(stop,))
            child.start()
            children.append(child)
            return child.pid

    ledger = WorkerHeartbeatLedger(worker_fixture._manifest(), Path(root))
    controller = ManagedWorkerController(
        worker_fixture._manifest(),
        ledger,
        ProcessInspector(),
        Launcher(),
    )
    try:
        barrier.wait(10)
        results.put(
            ("ok", controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client()))
        )
    except Exception as exc:
        import traceback

        results.put(("error", f"{exc!r}\n{traceback.format_exc()}"))
    finally:
        for child in children:
            child.join(20)


def test_two_process_controllers_reserve_before_first_heartbeat(tmp_path):
    context = multiprocessing.get_context("spawn")
    barrier, results, stop = context.Barrier(2), context.Queue(), context.Event()
    contenders = [
        context.Process(target=launch_contender, args=(str(tmp_path), barrier, results, stop))
        for _ in range(2)
    ]
    for contender in contenders:
        contender.start()
    try:
        outcomes = [results.get(timeout=15) for _ in contenders]
        assert all(kind == "ok" for kind, _ in outcomes), outcomes
        assert sum(pid is not None for _, pid in outcomes) == 1
        ledger = WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path)
        assert ledger.inspect(worker_fixture.CLIENT_ID).records == ()
        controller = ManagedWorkerController(
            worker_fixture._manifest(),
            ledger,
            ProcessInspector(),
            worker_fixture._RecordingLauncher(),
        )
        assert controller.request_stop(worker_fixture.CLIENT_ID, reason="pre-heartbeat stop") == 1
        reservation = json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())
        request = ledger.inspect_stop_request(worker_fixture.CLIENT_ID, reservation["worker_id"])
        assert request.process_id == reservation["process_id"]
    finally:
        stop.set()
        for contender in contenders:
            contender.join(15)
            assert contender.exitcode == 0


def test_unverified_worker_launch_remains_recoverable(tmp_path):
    class Inspector:
        def inspect(self, pid):
            return None

    class Launcher:
        calls = 0

        def launch(self, binding):
            self.calls += 1
            return 1234

    launcher = Launcher()
    ledger = WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path)
    controller = ManagedWorkerController(worker_fixture._manifest(), ledger, Inspector(), launcher)
    with pytest.raises(ExactClientWorkerError, match="1234"):
        controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client())
    with pytest.raises(ExactClientWorkerError, match="recovery"):
        controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client())
    assert launcher.calls == 1
    record = json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())
    assert record["process_id"] == 1234 and record["state"] == "unverified"


def test_terminal_heartbeat_close_serializes_against_publish(tmp_path):
    entered, release, concurrent = threading.Event(), threading.Event(), threading.Event()

    class Ledger(WorkerHeartbeatLedger):
        def publish(self, heartbeat):
            if heartbeat.runtime_state is WorkerRuntimeState.STOPPED:
                entered.set()
                assert release.wait(5)
            return super().publish(heartbeat)

    ledger = Ledger(heartbeat_fixture._manifest(), tmp_path)
    publisher = WorkerHeartbeatPublisher(
        ledger,
        node_id=heartbeat_fixture.NODE_ID,
        client_id=heartbeat_fixture.CLIENT_ID,
        instance_id=heartbeat_fixture.INSTANCE_ID,
        process=ProcessLifetimeSnapshot(101, heartbeat_fixture.PROCESS_STARTED_AT),
    )

    def publish_running():
        concurrent.set()
        with pytest.raises(WorkerHeartbeatError, match="closed"):
            publisher.publish(WorkerRuntimeState.RUNNING)

    with ThreadPoolExecutor(2) as pool:
        closing = pool.submit(publisher.close)
        assert entered.wait(5)
        publishing = pool.submit(publish_running)
        assert concurrent.wait(5)
        release.set()
        closing.result(5)
        publishing.result(5)
    assert (
        ledger.inspect(heartbeat_fixture.CLIENT_ID).records[0].runtime_state
        is WorkerRuntimeState.STOPPED
    )


def test_terminal_history_does_not_consume_active_record_limit(tmp_path):
    manifest = heartbeat_fixture._manifest()
    ledger = WorkerHeartbeatLedger(manifest, tmp_path, max_records_per_slot=2)
    for number in range(8):
        ledger.publish(
            heartbeat_fixture._heartbeat(
                worker_id=f"worker-{number:032x}",
                runtime_state=WorkerRuntimeState.STOPPED,
                dispatch_ready=False,
            )
        )
    ledger.publish(heartbeat_fixture._heartbeat())
    reloaded = WorkerHeartbeatLedger(manifest, tmp_path, max_records_per_slot=2).inspect(
        heartbeat_fixture.CLIENT_ID
    )
    assert not reloaded.issues
    assert len(reloaded.records) == 9


def test_session_launch_reservation_does_not_block_another_client():
    entered, release = threading.Event(), threading.Event()

    class Supervisor(session_fixture.FakeSupervisor):
        def launch_and_attach(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().launch_and_attach(*args, **kwargs)

    supervisor = Supervisor()
    manifest = session_fixture._manifest()
    selector = session_fixture.selector_from_config(manifest.node_id, manifest.clients[0])
    supervisor.start_outcomes = [session_fixture._managed(selector, "instance-a", 101)]
    supervisor.attach_results["instance-b"] = session_fixture._managed(
        selector, "instance-b", 102, launched=False
    )
    session = ManagerSession(manifest, supervisor)
    session.attach("client-02", instance_id="instance-b")
    with ThreadPoolExecutor(2) as pool:
        launching = pool.submit(session.start, "client-01")
        assert entered.wait(5)
        try:
            pool.submit(session.pause, "client-02").result(2)
            with pytest.raises(SessionSlotBoundError, match="progress"):
                pool.submit(session.start, "client-01").result(2)
        finally:
            release.set()
        assert launching.result(5).instance_id == "instance-a"


def test_application_launch_does_not_block_renewal_or_pause():
    entered, release = threading.Event(), threading.Event()

    class Session(app_fixture._RecordingSession):
        def start(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            return super().start(*args, **kwargs)

    session = Session(
        app_fixture.ManagerSessionSnapshot(
            node_id=app_fixture.NODE_ID,
            slots=(
                app_fixture._slot("client-01"),
                app_fixture._slot("client-02", instance_id="instance-b"),
            ),
        )
    )
    application, registry = app_fixture._application(
        session, app_fixture._client("instance-b", 102)
    )
    with ThreadPoolExecutor(2) as pool:
        launching = pool.submit(application.execute, "start", client_id="client-01")
        assert entered.wait(5)
        try:
            pool.submit(application.supervise).result(2)
            pool.submit(
                application.execute, "pause", client_id="client-02", instance_id="instance-b"
            ).result(2)
            assert registry.worker_supervisor.revocations[-1][0] == "client-02"
        finally:
            release.set()
        launching.result(5)


def test_supervisor_polling_does_not_hold_global_ownership_lock():
    from tests import test_manager_supervisor as fixture

    entered, release = threading.Event(), threading.Event()
    old, new = fixture._client(101), fixture._client(202, process_started_at_100ns=202000)
    registry = fixture.FakeRegistry(
        [
            fixture._snapshot(old),
            fixture._snapshot(old),
            fixture._snapshot(old),
            fixture._snapshot(old, new),
        ]
    )
    clock = fixture.FakeClock()

    class Sleeper(fixture.AdvancingSleeper):
        def sleep(self, seconds):
            entered.set()
            assert release.wait(5)
            super().sleep(seconds)

    supervisor = fixture._supervisor(
        registry, clock=clock, sleeper=Sleeper(clock), launcher=fixture.FakeLauncher(process_id=202)
    )
    supervisor.attach(fixture._selector(), instance_id=old.instance_id)
    command = fixture.ReviewedLaunchCommand((r"C:\Games\WonderBane\launcher.exe",))
    with ThreadPoolExecutor(2) as pool:
        launching = pool.submit(
            supervisor.launch_and_attach,
            fixture._selector(),
            command,
            timeout_seconds=2,
            poll_seconds=0.25,
        )
        assert entered.wait(5)
        try:
            assert not pool.submit(supervisor.pause, old.instance_id).result(2).dispatch_enabled
        finally:
            release.set()
        assert launching.result(5).client == new


def test_live_configuration_renewal_and_other_actions_continue_during_launch(tmp_path):
    from tests import test_manager_live_configuration as fixture

    entered, release, renewed = threading.Event(), threading.Event(), threading.Event()
    manifest = fixture.parse_manager_manifest(fixture._manifest_payload())

    class Application(fixture._FakeApplication):
        def execute(self, action, **kwargs):
            if action == "start":
                entered.set()
                assert release.wait(5)
            return super().execute(action, **kwargs)

        def supervise(self):
            renewed.set()

    application = fixture.LiveConfiguredManagerApplication(
        tmp_path / "manifest.json", manifest, lambda value: Application(value, [])
    )
    with ThreadPoolExecutor(2) as pool:
        launching = pool.submit(application.execute, "start", client_id="client-01")
        assert entered.wait(5)
        try:
            pool.submit(application.supervise).result(2)
            assert renewed.is_set()
            pool.submit(
                application.execute, "pause", client_id="client-02", instance_id="b"
            ).result(2)
        finally:
            release.set()
        launching.result(5)


def test_stale_but_running_worker_is_not_replaced(tmp_path):
    ledger = WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path)
    ledger.publish(worker_fixture._heartbeat(instance_id=worker_fixture._client().instance_id))
    inspector = worker_fixture._ProcessInspector(
        ProcessLifetimeSnapshot(
            worker_fixture.WORKER_PROCESS_ID, worker_fixture.WORKER_PROCESS_STARTED
        )
    )
    launcher = worker_fixture._RecordingLauncher()
    controller = ManagedWorkerController(
        worker_fixture._manifest(), ledger, inspector, launcher, clock=lambda: 10000.0
    )
    assert controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client()) is None
    assert launcher.bindings == []


def claim_operation(root, operation, barrier, results):
    from shadowbane_lab.manager.operation import WorkerOperationLedger
    from tests.test_manager_operation import _manifest

    ledger = WorkerOperationLedger(_manifest(), root, clock=lambda: 100.0)
    barrier.wait(15)
    results.put(ledger.claim_for_execution(operation, now=100.5))


def test_independent_process_claims_execute_once_and_terminal_receipt_cannot_regress(tmp_path):
    from shadowbane_lab.manager.operation import (
        WorkerOperationKind,
        WorkerOperationLedger,
        WorkerOperationLedgerError,
        WorkerOperationReceipt,
        WorkerOperationState,
        new_worker_operation,
    )
    from tests.test_manager_operation import _manifest, _permit

    operation = new_worker_operation(_permit(), WorkerOperationKind.PVE, "/pve", now=100.0)
    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100.0)
    ledger.submit(operation)
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(2), context.Queue()
    contenders = [
        context.Process(target=claim_operation, args=(str(tmp_path), operation, barrier, results))
        for _ in range(2)
    ]
    for contender in contenders:
        contender.start()
    try:
        assert sorted(results.get(timeout=15) for _ in contenders) == [False, True]
        for contender in contenders:
            contender.join(15)
            assert contender.exitcode == 0
    finally:
        for contender in contenders:
            if contender.is_alive():
                contender.terminate()
            contender.join(5)
    terminal = WorkerOperationReceipt.for_operation(
        operation, WorkerOperationState.CANCELLED, observed_at=101.0
    )
    ledger.publish_receipt(terminal)
    with pytest.raises(WorkerOperationLedgerError, match="terminal"):
        ledger.publish_receipt(
            WorkerOperationReceipt.for_operation(
                operation, WorkerOperationState.ACTIVE, observed_at=102.0
            )
        )
    assert not ledger.claim_for_execution(operation, now=102.0)
    assert ledger.inspect_receipt(operation.client_id, operation.operation_id) == terminal


def test_operation_interruption_stays_latched_after_renewal_or_cancel_receipt():
    from types import SimpleNamespace

    from shadowbane_lab.manager.operation import WorkerOperationKind
    from shadowbane_lab.manager.worker_runtime import _OperationStopSignal

    class Gate:
        stopped = False

        def is_set(self):
            return self.stopped

    class Ledger:
        pending = ()

        def pending_for(self, **kwargs):
            return self.pending

    for source in ("permit", "cancel"):
        gate, ledger = Gate(), Ledger()
        signal = _OperationStopSignal(
            gate,
            ledger,
            SimpleNamespace(client_id="client-01", instance_id="instance-1"),
            "worker-1",
            123,
            456,
        )
        assert not signal.is_set()
        if source == "permit":
            gate.stopped = True
        else:
            ledger.pending = (SimpleNamespace(kind=WorkerOperationKind.CANCEL),)
        assert signal.is_set()
        gate.stopped, ledger.pending = False, ()
        assert signal.is_set()
        # A separately admitted operation remains independent.
        replacement = _OperationStopSignal(
            gate,
            ledger,
            SimpleNamespace(client_id="client-02", instance_id="instance-2"),
            "worker-2",
            234,
            567,
        )
        assert not replacement.is_set()


def test_failed_attachment_recovers_original_launch_provenance_without_relaunch():
    from shadowbane_lab.manager.supervisor import LaunchTimeoutError, ReviewedLaunchCommand
    from tests import test_manager_supervisor as fixture

    registry = fixture.FakeRegistry([fixture._snapshot()])
    launcher = fixture.FakeLauncher(process_id=9000)
    supervisor = fixture._supervisor(registry, launcher=launcher)
    with pytest.raises(LaunchTimeoutError, match="9000/9000000"):
        supervisor.launch_and_attach(
            fixture._selector(),
            ReviewedLaunchCommand((r"C:\Games\WonderBane\sb.exe",)),
            timeout_seconds=0,
        )
    registry.snapshots = [fixture._snapshot(fixture._client(9000))]
    recovered = supervisor.attach(fixture._selector(), instance_id="client-9000")
    assert recovered.launched_by_manager
    assert recovered.launcher_process_id == 9000
    assert recovered.launcher_process_started_at_100ns == 9000000
    assert len(launcher.commands) == 1
    assert supervisor._pending_launches == {}


def test_unverified_real_child_remains_owned_and_recovery_rejects_exited_lifetime():
    import sys

    from shadowbane_lab.manager.supervisor import (
        ReviewedLaunchCommand,
        SubprocessLauncher,
        UnverifiedLaunchError,
    )

    class Inspector:
        available = False

        def inspect(self, pid):
            return ProcessInspector().inspect(pid) if self.available else None

    inspector = Inspector()
    launcher = SubprocessLauncher(inspector)
    # stdin is not used: this task-owned child waits on its own process-local event.
    command = ReviewedLaunchCommand(
        (sys.executable, "-c", "import threading; threading.Event().wait(30)")
    )
    with pytest.raises(UnverifiedLaunchError) as failure:
        launcher.launch(command)
    pid = failure.value.process_id
    child = launcher._children[pid]
    try:
        assert child.poll() is None
        inspector.available = True
        receipt = launcher.recover(pid)
        assert receipt.process_id == pid
        assert (
            receipt.process_started_at_100ns
            == ProcessInspector().inspect(pid).process_started_at_100ns
        )
    finally:
        child.terminate()  # Exact retained task-created Popen handle, never PID/name routing.
        child.wait(timeout=10)
    with pytest.raises(UnverifiedLaunchError):
        launcher.recover(pid)


@pytest.mark.parametrize("action", ["tile", "request_close"])
def test_blocked_window_action_does_not_block_other_client_pause_refresh_or_status(action):
    from tests import test_manager_supervisor as fixture

    entered, release = threading.Event(), threading.Event()

    class Controller(fixture.FakeWindowController):
        def tile(self, expected, rectangle):
            entered.set()
            assert release.wait(5)
            return super().tile(expected, rectangle)

        def request_graceful_close(self, expected):
            entered.set()
            assert release.wait(5)
            return super().request_graceful_close(expected)

    first = session_fixture._instance("instance-a", 101)
    second = session_fixture._instance("instance-b", 102)
    registry = fixture.FakeRegistry([fixture._snapshot(first, second)])
    supervisor = fixture._supervisor(registry, controller=Controller())
    session = ManagerSession(session_fixture._manifest(), supervisor)
    session.attach("client-01", instance_id=first.instance_id)
    session.attach("client-02", instance_id=second.instance_id)
    with ThreadPoolExecutor(2) as pool:
        blocked = pool.submit(getattr(session, action), "client-01")
        assert entered.wait(5)
        try:
            paused = pool.submit(session.pause, "client-02").result(2)
            assert not paused.dispatch_enabled
            assert not pool.submit(session.refresh, "client-02").result(2).dispatch_enabled
            assert len(pool.submit(session.snapshot).result(2).slots) == 3
            if action == "request_close":
                assert not supervisor.status(first.instance_id).dispatch_enabled
        finally:
            release.set()
        assert blocked.result(5).instance_id == first.instance_id
    assert not session.status("client-02").dispatch_enabled


def blocked_launch_contender(root, entered, release, result, stop):
    context = multiprocessing.get_context("spawn")
    child = None

    class Launcher:
        def launch(self, binding):
            nonlocal child
            child = context.Process(target=hold_worker, args=(stop,))
            child.start()
            entered.set()
            assert release.wait(15)
            return child.pid

    controller = ManagedWorkerController(
        worker_fixture._manifest(),
        WorkerHeartbeatLedger(worker_fixture._manifest(), Path(root)),
        ProcessInspector(),
        Launcher(),
    )
    try:
        result.put(controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client()))
    finally:
        if child is not None:
            child.join(20)


def stop_launch_contender(root, acquiring, result):
    from contextlib import contextmanager
    from unittest.mock import patch

    from shadowbane_lab.record_store import exclusive_record_lock

    @contextmanager
    def observed_lock(path):
        acquiring.set()
        with exclusive_record_lock(path):
            yield

    controller = ManagedWorkerController(
        worker_fixture._manifest(),
        WorkerHeartbeatLedger(worker_fixture._manifest(), Path(root)),
        ProcessInspector(),
        worker_fixture._RecordingLauncher(),
    )
    with patch("shadowbane_lab.manager.worker_runtime.exclusive_record_lock", observed_lock):
        result.put(controller.request_stop(worker_fixture.CLIENT_ID, reason="stop during launch"))


def test_interprocess_stop_waits_for_inflight_launch_reservation(tmp_path):
    context = multiprocessing.get_context("spawn")
    entered, release, acquiring, stop = [context.Event() for _ in range(4)]
    launch_result, stop_result = context.Queue(), context.Queue()
    launching = context.Process(
        target=blocked_launch_contender,
        args=(str(tmp_path), entered, release, launch_result, stop),
    )
    stopping = context.Process(
        target=stop_launch_contender,
        args=(str(tmp_path), acquiring, stop_result),
    )
    launching.start()
    try:
        assert entered.wait(10)
        stopping.start()
        assert acquiring.wait(10)
        release.set()
        pid = launch_result.get(timeout=10)
        assert stop_result.get(timeout=10) == 1
        record = json.loads(next(tmp_path.rglob(".launch-reservation")).read_text())
        ledger = WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path)
        request = ledger.inspect_stop_request(worker_fixture.CLIENT_ID, record["worker_id"])
        assert request.process_id == pid
        assert request.process_started_at_100ns == record["process_started_at_100ns"]
    finally:
        release.set()
        stop.set()
        launching.join(15)
        if stopping.pid is not None:
            stopping.join(15)
        assert launching.exitcode == stopping.exitcode == 0


def test_retained_worker_child_recovers_failed_attachment_without_relaunch(tmp_path):
    import subprocess
    import sys
    from unittest.mock import patch

    from shadowbane_lab.manager.worker_runtime import SubprocessWorkerLauncher

    class Inspector(ProcessInspector):
        unavailable = True

        def inspect(self, pid):
            return None if self.unavailable else super().inspect(pid)

    inspector = Inspector()
    launcher = SubprocessWorkerLauncher(
        manifest_path=tmp_path / "manifest.json",
        worker_state_directory=tmp_path,
        log_directory=tmp_path / "logs",
    )
    controller = ManagedWorkerController(
        worker_fixture._manifest(),
        WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path),
        inspector,
        launcher,
    )
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
        stdin=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        with patch(
            "shadowbane_lab.manager.worker_runtime.subprocess.Popen", return_value=child
        ) as popen:
            with pytest.raises(ExactClientWorkerError, match="attachment recovery"):
                controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client())
            inspector.unavailable = False
            assert (
                controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client())
                is None
            )
            assert popen.call_count == 1
        assert controller.request_stop(worker_fixture.CLIENT_ID, reason="recovered stop") == 1
        child.stdin.close()
        child.wait(10)
        assert launcher.recover(child.pid, inspector) is None
        with pytest.raises(ExactClientWorkerError, match="no retained"):
            launcher.recover(os.getpid(), inspector)
    finally:
        if not child.stdin.closed:
            child.stdin.close()
        child.wait(10)


@pytest.mark.parametrize("value", [[], {"schema_version": 1, "worker_id": 42}])
def test_malformed_launch_reservation_preserves_evidence(tmp_path, value):
    ledger = WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path)
    path = (
        tmp_path
        / worker_fixture._manifest().node_id
        / worker_fixture.CLIENT_ID
        / ".launch-reservation"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value))
    controller = ManagedWorkerController(
        worker_fixture._manifest(),
        ledger,
        ProcessInspector(),
        worker_fixture._RecordingLauncher(),
    )
    with pytest.raises(ExactClientWorkerError, match="invalid worker launch reservation"):
        controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client())
    assert json.loads(path.read_text()) == value


def test_failure_before_worker_creation_releases_only_its_reservation(tmp_path):
    from unittest.mock import patch

    from shadowbane_lab.manager.worker_runtime import SubprocessWorkerLauncher

    launcher = SubprocessWorkerLauncher(
        manifest_path=tmp_path / "manifest.json",
        worker_state_directory=tmp_path,
        log_directory=tmp_path / "logs",
    )
    controller = ManagedWorkerController(
        worker_fixture._manifest(),
        WorkerHeartbeatLedger(worker_fixture._manifest(), tmp_path),
        ProcessInspector(),
        launcher,
    )
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen", side_effect=OSError("injected")
    ) as popen:
        for _ in range(2):
            with pytest.raises(ExactClientWorkerError, match="could not launch"):
                controller.ensure_started(worker_fixture.CLIENT_ID, worker_fixture._client())
        assert popen.call_count == 2
    assert list(tmp_path.rglob(".launch-reservation")) == []
