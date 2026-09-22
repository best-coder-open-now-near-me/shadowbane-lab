import json
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
from shadowbane_lab.client_extension.vendor_navigation_wire import READY, UNRESOLVED, Outcome
from shadowbane_lab.manager.dashboard import _RequestError, _validate_action_payload
from shadowbane_lab.manager.guard_control import GuardWorkerExecutor, ManagerGuardControl
from shadowbane_lab.manager.guard_funding_cycle import GuardFundingCycleStopped
from shadowbane_lab.manager.operation import (
    WorkerOperationFormatError,
    WorkerOperationKind,
    WorkerOperationState,
    loads_worker_operation,
    new_worker_operation,
)
from tests.test_guard_job import CONTEXT, DISCOVERY, JOB
from tests.test_guard_job import setup as make_setup
from tests.test_manager_operation import WORKER_ID, _permit


@pytest.fixture
def setup(tmp_path):
    f = make_setup.__wrapped__(tmp_path)
    f.binding.client_id, f.binding.instance_id, f.binding.worker_id = (
        "client",
        "instance",
        WORKER_ID,
    )
    f.permit = replace(_permit(), node_id="node", client_id="client", instance_id="instance")
    f.operations = Mock()
    f.operations.inspect_slot.return_value = []
    f.permits = SimpleNamespace(inspect_permit=lambda _: f.permit)
    f.control = ManagerGuardControl(tmp_path, "node", f.permits, f.operations, clock=lambda: 100)
    f.session = Mock(identity=NativeClientProcessIdentity(988, 123), window=1000)
    f.session.inspect.return_value = SimpleNamespace(
        outcome=Outcome.OBSERVED, flags=READY, snapshot=CONTEXT
    )

    def discover(*args, **kwargs):
        f.session.close.assert_called_once_with()
        assert not kwargs["cancelled"]()

    f.executor = GuardWorkerExecutor(
        tmp_path,
        "node",
        f.binding,
        session_factory=lambda *args, **kwargs: f.session,
        discover=discover,
        owner_reader=f.owner_reader,
        runner=lambda *args, **kwargs: f.run(),
    )
    f.executor.initialize(
        WORKER_ID,
        SimpleNamespace(
            process_id=f.permit.process_id,
            process_started_at_100ns=f.permit.process_started_at_100ns,
        ),
    )

    def operation(command, operation_id=DISCOVERY):
        return new_worker_operation(
            f.permit, WorkerOperationKind.GUARD, command, now=100, operation_id=operation_id
        )

    f.operation = operation
    f.stop = threading.Event()
    return f


def test_discover_is_typed_and_uses_exact_ledger(setup):
    f = setup
    f.control.execute("guard-discover", "client", "instance")
    operation = f.operations.submit.call_args.args[0]
    assert operation.kind is WorkerOperationKind.GUARD and operation.command == "guard discover"
    assert loads_worker_operation(json.dumps(operation.to_dict())) == operation
    assert f.control.summary("client", "instance") == {"prepared": None, "job": None}


@pytest.mark.parametrize("reason", ["expired", "wrong_instance", "capability", "busy"])
def test_guard_admission_rejects_stale_or_busy_worker(setup, reason):
    f = setup
    if reason == "expired":
        f.control.clock = lambda: f.permit.expires_at
    elif reason == "wrong_instance":
        f.permit = replace(f.permit, instance_id="other")
    elif reason == "capability":
        (f.store.root / "guard-worker-capability.json").unlink()
    else:
        f.operations.inspect_slot.return_value = [
            SimpleNamespace(operation=f.operation("guard discover"), receipt=None)
        ]
    with pytest.raises(GuardFundingCycleStopped):
        f.control.execute("guard-discover", "client", "instance")
    f.operations.submit.assert_not_called()


def test_discovery_closes_observer_before_scan_and_prepares_without_spending(setup):
    f = setup
    result = f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    assert result.state is WorkerOperationState.SUCCEEDED
    assert f.jobs.current() is None
    assert not (f.store.root / "guard-funding-cycles").exists()
    summary = f.control.summary("client", "instance")
    assert summary["prepared"]["guards"] == 2 and summary["prepared"]["buildings"] == 2
    assert summary["job"] is None
    with pytest.raises(GuardFundingCycleStopped, match="already attempted"):
        f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    assert f.session.inspect.call_count == 1


@pytest.mark.parametrize("reason", ["wrong_window", "pending", "empty_scene"])
def test_discovery_cannot_adopt_foreign_or_pending_window(setup, reason):
    f = setup
    if reason == "wrong_window":
        f.session.window += 1
    elif reason == "pending":
        f.session.inspect.return_value.flags |= UNRESOLVED
    else:
        f.session.inspect.return_value.snapshot = type(CONTEXT)()
    with pytest.raises(GuardFundingCycleStopped):
        f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    f.session.close.assert_called_once_with()
    assert f.control.summary("client", "instance")["prepared"] is None


def test_start_and_summary_use_prepared_selection_and_real_guard_queue(setup):
    f = setup
    f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    f.control.execute("guard-start", "client", "instance", job_id=DISCOVERY)
    submitted = f.operations.submit.call_args.args[0]
    assert submitted.command == "guard start " + DISCOVERY
    f.executor.execute(f.operation(submitted.command, JOB), stop_signal=f.stop)
    summary = f.control.summary("client", "instance")["job"]
    assert summary["state"] == "unavailable" and summary["guards"] == 2
    assert not summary["maximum_rank_verified"] and not summary["town_coverage_verified"]
    assert [c["target"]["guard"] for c in f.calls] == [777, 778]


def test_prepared_lifetime_change_stops_before_job_creation(setup):
    f = setup
    f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    f.binding.game_process_started_at_100ns += 1
    with pytest.raises(GuardFundingCycleStopped, match="selection changed"):
        f.executor.execute(f.operation("guard start " + DISCOVERY, JOB), stop_signal=f.stop)
    assert f.jobs.current() is None


def test_stop_idle_job_acknowledges_and_cannot_be_resumed(setup):
    f = setup
    f.begin()
    f.control.execute("guard-stop", "client", "instance", job_id=JOB)
    assert f.jobs.current()["state"] == "stopped"
    with pytest.raises(GuardFundingCycleStopped):
        f.control.execute("guard-resume", "client", "instance", job_id=JOB)
    f.operations.submit.assert_not_called()


def test_pause_and_resume_require_current_job(setup):
    f = setup
    f.begin()
    with pytest.raises(GuardFundingCycleStopped):
        f.control.execute("guard-stop", "client", "instance", job_id=DISCOVERY)
    f.control.execute("guard-pause", "client", "instance", job_id=JOB)
    assert f.jobs.control(JOB) == "pause"
    f.control.execute("guard-resume", "client", "instance", job_id=JOB)
    assert f.operations.submit.call_args.args[0].command == "guard resume " + JOB


def test_idle_stop_preserves_interrupted_cycle_for_review(setup):
    f = setup
    record = f.begin()
    record["active_cycle"] = {"operation_id": DISCOVERY, "index": 0}
    f.jobs.save(record)
    f.control.execute("guard-stop", "client", "instance", job_id=JOB)
    assert f.jobs.current()["state"] == "review"


@pytest.mark.parametrize(
    "command",
    [
        "guard start",
        "guard resume ../escape",
        "guard start " + "a" * 32,
        "guard discover extra",
        "vendor start",
    ],
)
def test_strict_guard_command_schema_rejects_untyped_targets(setup, command):
    with pytest.raises(WorkerOperationFormatError):
        setup.operation(command)


@pytest.mark.parametrize(
    "action", ["guard-discover", "guard-start", "guard-pause", "guard-resume", "guard-stop",
               "guard-travel", "guard-continue"]
)
def test_dashboard_guard_actions_require_exact_instance_and_job(action):
    payload = dict(action=action, client_id="client", instance_id="instance")
    if action in {"guard-start", "guard-pause", "guard-resume", "guard-stop",
                  "guard-travel", "guard-continue"}:
        payload["job_id"] = JOB
    assert _validate_action_payload(payload) == (
        action,
        "client",
        "instance",
        payload.get("job_id"),
        None,
    )
    invalid = dict(payload)
    invalid.pop("instance_id")
    with pytest.raises(_RequestError):
        _validate_action_payload(invalid)
    if "job_id" in payload:
        payload["job_id"] = "a" * 32
        with pytest.raises(_RequestError):
            _validate_action_payload(payload)


def test_worker_cancel_and_foreign_instance_do_not_capture_or_spend(setup):
    f = setup
    f.stop.set()
    assert (
        f.executor.execute(f.operation("guard discover"), stop_signal=f.stop).state
        is WorkerOperationState.CANCELLED
    )
    f.session.inspect.assert_not_called()
    f.stop.clear()
    with pytest.raises(GuardFundingCycleStopped):
        f.executor.execute(
            replace(f.operation("guard discover"), instance_id="other"), stop_signal=f.stop
        )
    f.session.inspect.assert_not_called()


def test_start_cannot_replace_the_dashboard_selected_discovery(setup):
    f = setup
    f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    with pytest.raises(GuardFundingCycleStopped):
        f.control.execute("guard-start", "client", "instance", job_id=JOB)
    f.operations.submit.assert_not_called()


def test_discovery_and_start_work_without_any_warehouse_context(setup):
    f = setup
    assert not CONTEXT.warehouse_hud and not CONTEXT.building_id
    f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    prepared = json.loads((f.store.root / "guard-prepared.json").read_text())
    assert prepared["schema_version"] == 2 and prepared["funding_source"] == "carried"
    assert "warehouse" not in prepared
    f.executor.execute(f.operation("guard start " + DISCOVERY, JOB), stop_signal=f.stop)
    job = f.jobs.read(JOB)
    assert job["funding_source"] == "carried" and job["withdrawn"] == 0
    assert all("warehouse_building" not in t for t in job["plan"]["targets"])


def test_previous_warehouse_worker_cannot_admit_carried_only_job(setup):
    f = setup
    path = f.store.root / "guard-worker-capability.json"
    record = json.loads(path.read_text())
    record["capability"] = "guard_jobs_v1"
    path.write_text(json.dumps(record))
    with pytest.raises(GuardFundingCycleStopped, match="Restart this worker"):
        f.control.execute("guard-discover", "client", "instance")
    f.operations.submit.assert_not_called()


def test_travel_and_continue_require_acknowledged_boundary(setup):
    f = setup
    f.begin()
    with pytest.raises(GuardFundingCycleStopped, match="safe to move"):
        f.control.execute("guard-continue", "client", "instance", job_id=JOB)
    f.control.execute("guard-travel", "client", "instance", job_id=JOB)
    assert f.jobs.current()["state"] == "travel"
    with pytest.raises(GuardFundingCycleStopped):
        f.control.execute("guard-resume", "client", "instance", job_id=JOB)
    f.control.execute("guard-continue", "client", "instance", job_id=JOB)
    operation = f.operations.submit.call_args.args[0]
    assert operation.command == "guard continue " + JOB
    assert loads_worker_operation(json.dumps(operation.to_dict())) == operation


def test_continue_worker_scans_then_runs_same_job(setup):
    from tests.test_guard_job import AREA, travel_scan
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")

    def discover(*args, **kwargs):
        assert f.jobs.current()["state"] == "scanning"
        assert kwargs["remembered"] == {(123, 777), (456, 778)}
        travel_scan(f)
    f.executor.discover = discover
    result = f.executor.execute(f.operation("guard continue " + JOB, AREA), stop_signal=f.stop)
    assert result.state is WorkerOperationState.CANCELLED
    assert f.jobs.current()["job_id"] == JOB
    assert len(f.jobs.current()["guards"]) == 3
    assert {c["target"]["guard"] for c in f.calls} == {777, 779}


def test_failed_area_scan_with_idle_journal_can_travel_without_losing_progress(setup):
    from tests.test_guard_job import AREA
    f = setup
    f.begin()
    f.jobs.request(JOB, "travel")
    f.executor.discover = Mock(side_effect=RuntimeError("scan stopped"))
    with pytest.raises(RuntimeError, match="scan stopped"):
        f.executor.execute(f.operation("guard continue " + JOB, AREA), stop_signal=f.stop)
    assert f.jobs.current()["state"] == "travel"
    assert len(f.jobs.current()["guards"]) == 2 and not f.calls


def test_character_change_during_discovery_never_prepares_or_starts_job(setup):
    f = setup
    def discover(*args, **kwargs):
        f.owner["character_name"] = "another"
    f.executor.discover = discover
    with pytest.raises(GuardFundingCycleStopped, match="character changed"):
        f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    assert f.jobs.current() is None
    assert not (f.store.root / "guard-prepared.json").exists()


def test_character_change_after_preparation_never_starts_job(setup):
    f = setup
    f.executor.execute(f.operation("guard discover"), stop_signal=f.stop)
    f.owner["character_name"] = "another"
    with pytest.raises(GuardFundingCycleStopped, match="character changed"):
        f.executor.execute(f.operation("guard start " + DISCOVERY, JOB), stop_signal=f.stop)
    assert f.jobs.current() is None and not f.calls
