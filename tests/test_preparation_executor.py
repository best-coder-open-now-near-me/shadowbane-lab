from types import SimpleNamespace

import pytest
from test_manager_movement import context


@pytest.mark.parametrize("kind", ["vendor", "guard", "condemn"])
def test_unconfigured_executor_is_proven_no_native_work(tmp_path, kind):
    import threading

    from test_manager_movement import make_executor

    from shadowbane_lab.manager.operation import WorkerOperationKind
    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    operation = SimpleNamespace(client_id="client", instance_id="instance", worker_id="worker",
        operation_id="no-resource", kind=WorkerOperationKind(kind))
    result = executor.execute(operation, stop_signal=threading.Event())
    assert result.native_cleanup_confirmed
    assert session.acquire_calls == session.stop_calls == []


def test_session_construction_failure_has_no_native_acquisition(tmp_path):
    import threading

    from test_manager_movement import make_executor

    from shadowbane_lab.manager.operation import WorkerOperationKind
    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    def failed(*args):
        raise OSError("transport cannot open")
    executor._movement_session_factory = failed
    operation = SimpleNamespace(client_id="client", instance_id="instance", worker_id="worker",
        operation_id="no-resource", kind=WorkerOperationKind.PVE)
    result = executor.execute(operation, stop_signal=threading.Event())
    assert result.native_cleanup_confirmed
    assert session.acquire_calls == session.stop_calls == []
