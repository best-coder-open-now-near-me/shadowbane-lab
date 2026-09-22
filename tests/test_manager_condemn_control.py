import json
import threading
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.manager.condemn_control import CondemnWorkerExecutor, ManagerCondemnControl
from shadowbane_lab.manager.condemn_cycle import CondemnCycleStopped
from shadowbane_lab.manager.condemn_job import CondemnJobStore
from shadowbane_lab.manager.dashboard import _RequestError, _validate_action_payload
from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationState,
    loads_worker_operation,
    new_worker_operation,
)
from tests import test_condemn_plan as plan_tests
from tests.test_condemn_cycle import OWNER
from tests.test_condemn_transaction import LIFE
from tests.test_manager_operation import WORKER_ID, _permit


@pytest.fixture
def setup(tmp_path):
    store, plans, preparation, summary = plan_tests.setup.__wrapped__(tmp_path)
    binding = SimpleNamespace(
        game_process_id=LIFE.process_id,
        game_process_started_at_100ns=LIFE.creation,
        game_window_handle=1000,
        client_id="client",
        instance_id="instance",
        worker_id=WORKER_ID,
    )
    permit = replace(_permit(), node_id="node", client_id="client", instance_id="instance")
    permits = Mock()
    permits.inspect_permit.return_value = permit
    operations = Mock()
    operations.inspect_slot.return_value = []
    control = ManagerCondemnControl(tmp_path, "node", permits, operations, clock=lambda: 100)
    runner = Mock(return_value=dict(state="paused", detail="Paused with progress saved."))
    prepare = Mock(return_value=summary)
    executor = CondemnWorkerExecutor(
        tmp_path, "node", binding, runner=runner, prepare=prepare, owner_reader=lambda _: OWNER
    )
    executor.initialize(
        WORKER_ID,
        SimpleNamespace(
            process_id=permit.process_id, process_started_at_100ns=permit.process_started_at_100ns
        ),
    )
    selection = dict(
        preparation_id=preparation, sha256=summary["sha256"], crests=["5:20"], buildings=[100]
    )
    return SimpleNamespace(
        store=store,
        plans=plans,
        permit=permit,
        permits=permits,
        operations=operations,
        control=control,
        executor=executor,
        selection=selection,
        runner=runner,
        prepare=prepare,
        binding=binding,
    )


def test_prepare_routes_to_exact_worker_without_starting_a_job(setup):
    f = setup
    f.control.execute("condemn-prepare", "client", "instance")
    operation = f.operations.submit.call_args.args[0]
    assert operation.kind is WorkerOperationKind.CONDEMN
    assert loads_worker_operation(json.dumps(operation.to_dict())) == operation
    result = f.executor.execute(operation, stop_signal=threading.Event())
    assert result.state is WorkerOperationState.SUCCEEDED
    f.prepare.assert_called_once()
    f.runner.assert_not_called()
    assert CondemnJobStore(f.store).current() is None


def test_start_persists_exact_selection_before_dispatch_and_worker_uses_it(setup):
    f = setup
    f.control.execute("condemn-start", "client", "instance", selection=f.selection)
    operation = f.operations.submit.call_args.args[0]
    request = json.loads(
        (f.store.root / "condemn-requests" / (operation.operation_id + ".json")).read_bytes()
    )
    assert request["selection"] == f.selection
    assert request["target"] == list(operation.target_identity())
    result = f.executor.execute(operation, stop_signal=threading.Event())
    assert result.state is WorkerOperationState.CANCELLED
    current = CondemnJobStore(f.store).current()
    assert current["job_id"] == operation.operation_id
    assert len(current["selection"]["targets"]) == 1
    f.runner.assert_called_once()
    with pytest.raises(CondemnCycleStopped):
        f.executor.execute(operation, stop_signal=threading.Event())
    assert f.runner.call_count == 1


@pytest.mark.parametrize("reason", ["expired", "wrong_instance", "capability", "busy"])
def test_admission_rejects_stale_or_busy_worker(setup, reason):
    f = setup
    if reason == "expired":
        f.control.clock = lambda: f.permit.expires_at
    elif reason == "wrong_instance":
        f.permits.inspect_permit.return_value = replace(f.permit, instance_id="other")
    elif reason == "capability":
        (f.store.root / "condemn-worker-capability.json").unlink()
    else:
        operation = new_worker_operation(
            f.permit, WorkerOperationKind.CONDEMN, "condemn prepare", now=100
        )
        f.operations.inspect_slot.return_value = [
            SimpleNamespace(operation=operation, receipt=None)
        ]
    with pytest.raises(CondemnCycleStopped):
        f.control.execute("condemn-start", "client", "instance", selection=f.selection)
    f.operations.submit.assert_not_called()


def test_changed_selection_request_cannot_rebind_to_new_worker(setup):
    f = setup
    f.control.execute("condemn-start", "client", "instance", selection=f.selection)
    operation = f.operations.submit.call_args.args[0]
    path = f.store.root / "condemn-requests" / (operation.operation_id + ".json")
    request = json.loads(path.read_bytes())
    request["target"][-1] += 1
    path.write_text(json.dumps(request))
    with pytest.raises(CondemnCycleStopped, match="changed owner"):
        f.executor.execute(operation, stop_signal=threading.Event())
    f.runner.assert_not_called()


def test_healthy_summary_exposes_distinct_prepared_choices(setup):
    result = setup.control.summary("client", "instance")
    assert result["job"] is None and len(result["prepared"]["catalog"]["entries"]) == 3
    assert "error" not in result


def test_dashboard_start_requires_bounded_explicit_selection(setup):
    payload = dict(
        action="condemn-start",
        client_id="client",
        instance_id="instance",
        selection=setup.selection,
    )
    parsed = _validate_action_payload(payload)
    assert parsed == ("condemn-start", "client", "instance", None, setup.selection)
    for mutate in [
        lambda p: p.pop("instance_id"),
        lambda p: p.pop("selection"),
        lambda p: p["selection"].update(crests=[]),
        lambda p: p["selection"].update(crests=["3:20"]),
        lambda p: p["selection"].update(crests=["5:20", "5:20"]),
        lambda p: p["selection"].update(buildings=[True]),
        lambda p: p["selection"].update(sha256="wrong"),
        lambda p: p["selection"].update(preparation_id="../unsafe"),
    ]:
        bad = deepcopy(payload)
        mutate(bad)
        with pytest.raises(_RequestError):
            _validate_action_payload(bad)


@pytest.mark.parametrize("action", ["condemn-pause", "condemn-resume", "condemn-stop"])
def test_dashboard_controls_require_exact_job(action):
    payload = dict(
        action=action, client_id="client", instance_id="instance", job_id="operation-" + "a" * 32
    )
    assert _validate_action_payload(payload)[:4] == (
        action,
        "client",
        "instance",
        payload["job_id"],
    )
    payload.pop("job_id")
    with pytest.raises(_RequestError):
        _validate_action_payload(payload)


def test_authenticated_http_start_forwards_the_exact_selection(setup):
    import http.client

    from shadowbane_lab.manager.dashboard import DashboardServer

    service = SimpleNamespace(status=Mock(return_value={"ok": True}),
                              execute=Mock(return_value={"ok": True}))
    server = DashboardServer(service, port=0).start()
    try:
        connection = http.client.HTTPConnection(server.host, server.port, timeout=3)
        body = dict(
            action="condemn-start",
            client_id="client",
            instance_id="instance",
            selection=setup.selection,
        )
        connection.request(
            "POST",
            "/api/v1/actions",
            body=json.dumps(body),
            headers={
                "Authorization": "Bearer " + server.authorization_token,
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        connection.close()
        service.execute.assert_called_once_with(
            "condemn-start", client_id="client", instance_id="instance", selection=setup.selection
        )
    finally:
        server.stop()


def test_other_job_admission_cannot_take_over_an_idle_condemn_job(setup):
    from shadowbane_lab.manager.guard_control import ManagerGuardControl
    from shadowbane_lab.manager.vendor_control import ManagerVendorControl

    f = setup
    f.control.execute("condemn-start", "client", "instance", selection=f.selection)
    operation = f.operations.submit.call_args.args[0]
    f.executor.execute(operation, stop_signal=threading.Event())
    f.operations.submit.reset_mock()
    for cls, action in [
        (ManagerGuardControl, "guard-discover"),
        (ManagerVendorControl, "vendor-start"),
    ]:
        controller = cls(f.control.root, "node", f.permits, f.operations, clock=lambda: 100)
        with pytest.raises(RuntimeError, match="Condemn job first"):
            controller.execute(action, "client", "instance")
    f.operations.submit.assert_not_called()
