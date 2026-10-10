"""Manager reserves an operation before setup, and acquires only when prepared."""

import threading
from types import SimpleNamespace

import pytest

from shadowbane_lab.cli_commands import manager
from shadowbane_lab.manager.operation import WorkerOperationKind, WorkerOperationState
from tests.test_manager_movement import context, make_executor


def operation():
    return SimpleNamespace(client_id="client", instance_id="instance", worker_id="worker",
                           operation_id="pve-startup", kind=WorkerOperationKind.PVE)


def test_manager_keeps_startup_reserved_without_exposing_a_native_lease(tmp_path, monkeypatch):
    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    item, parent = operation(), threading.Event()
    entered, release = threading.Event(), threading.Event()
    results = []

    def prepared_run(**kwargs):
        assert kwargs["stop_signal"] is executor._movement
        assert "movement_dispatcher" not in kwargs
        entered.set()
        assert release.wait(5)
        dispatcher = kwargs["movement_acquirer"]()
        assert dispatcher is executor._movement.dispatcher
        executor.maintain(item, parent)
        assert session.renew_calls == [dispatcher.grant]
        return 0

    monkeypatch.setattr(manager, "_run_pve", prepared_run)
    thread = threading.Thread(target=lambda: results.append(executor.execute(item,
                                                                             stop_signal=parent)))
    thread.start()
    try:
        assert entered.wait(5)
        assert not session.acquire_calls
        for _ in range(8):
            executor.maintain(item, parent)
        assert not session.acquire_calls and not session.renew_calls
        duplicate = executor.execute(item, stop_signal=parent)
        assert duplicate.state is WorkerOperationState.FAILED
        assert "retains movement ownership" in duplicate.detail
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert results[0].state is WorkerOperationState.SUCCEEDED
    assert len(session.acquire_calls) == len(session.stop_calls) == 1
    assert session.closed == 1 and executor._movement is None


@pytest.mark.parametrize("failure", ["setup", "cancel"])
def test_pre_acquisition_exit_has_no_native_authority_to_stop(tmp_path, monkeypatch, failure):
    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    item, parent = operation(), threading.Event()

    def prepared_run(**kwargs):
        assert not session.acquire_calls
        if failure == "setup":
            raise OSError("terrain cache unavailable")
        parent.set()
        assert kwargs["movement_acquirer"]() is None
        return 0

    monkeypatch.setattr(manager, "_run_pve", prepared_run)
    result = executor.execute(item, stop_signal=parent)
    assert result.state is (WorkerOperationState.FAILED if failure == "setup"
                            else WorkerOperationState.CANCELLED)
    assert result.native_cleanup_confirmed
    assert not session.acquire_calls and not session.stop_calls and not session.renew_calls
    assert session.closed == 1 and executor._movement is None


def test_setup_failure_does_not_hide_transport_disposal_failure(tmp_path, monkeypatch):
    _, session, _ = context()
    executor = make_executor(tmp_path, session)

    def fail(**kwargs):
        raise OSError("terrain cache unavailable")

    def close():
        raise OSError("transport close failed")

    session.close = close
    monkeypatch.setattr(manager, "_run_pve", fail)
    result = executor.execute(operation(), stop_signal=threading.Event())
    assert result.state is WorkerOperationState.FAILED
    assert not result.native_cleanup_confirmed
    assert "terrain cache unavailable" in result.detail and "cleanup:" in result.detail
    assert not session.acquire_calls and not session.stop_calls
