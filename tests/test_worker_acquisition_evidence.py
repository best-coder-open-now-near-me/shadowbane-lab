import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.action_channel import NativeActionChannelTimeout
from shadowbane_lab.client_extension.movement_session import NativeMovementError
from shadowbane_lab.client_extension.movement_wire import (
    Grant,
    Host,
    Outcome,
    Owner,
    Receipt,
    Settings,
    Snapshot,
)
from shadowbane_lab.manager.operation import WorkerOperationKind, WorkerOperationState
from tests.test_manager_movement import context, make_executor


def configured(tmp_path):
    _, session, _ = context()
    original = Snapshot(2, 123, 3, 456, 789, Grant(10, 20, Owner.MANUAL),
                        Settings(), 7, 100)
    session.snapshot = lambda: original
    executor = make_executor(tmp_path, session)
    operation = SimpleNamespace(client_id="client", instance_id="instance", worker_id="worker",
                                operation_id="acquisition-test", kind=WorkerOperationKind.PVE)
    executor._execute_pve = lambda **kwargs: pytest.fail("rejected acquisition entered PvE")
    return session, executor, operation, original


@pytest.mark.parametrize("outcome", [Outcome.INHIBITED, Outcome.STALE, Outcome.UNAVAILABLE,
                                    Outcome.STOP_FAILED, Outcome.INVALID])
def test_native_acquisition_rejection_retains_original_and_returned_evidence(tmp_path, outcome):
    session, executor, operation, original = configured(tmp_path)
    requests = []

    def reject(expected, worker, operation_id, key):
        requests.append(key)
        assert expected is original
        receipt = Receipt(Grant(11, 21, Owner.NONE), key, Host(22, 3, 44), 789,
                          8, Settings(), outcome, 1)
        # Later status is unrelated to the original admission decision.
        session.snapshot = lambda: replace(original, revision=99, tick=900)
        raise NativeMovementError(outcome, receipt)

    session.acquire = reject
    result = executor.execute(operation, stop_signal=threading.Event())
    assert result.state is WorkerOperationState.FAILED
    assert len(requests) == 1
    assert f"NativeMovementError/{outcome.name}" in result.detail
    assert f"acquisition={requests[0]}" in result.detail
    assert "acquire_expected=g10/s20/MANUAL/f3/r7" in result.detail
    assert "receipt=g11/s21/NONE/f1/r8" in result.detail
    assert "game=123/456/hwnd789; snapshot=2@100" in result.detail
    assert "producer=22/44/lease3; receipt_hwnd=789" in result.detail
    assert "r99" not in result.detail
    assert len(result.detail) <= 512
    assert not result.native_cleanup_confirmed
    assert session.closed == 1 and session.stop_calls == []


def test_rejection_survives_secondary_lease_close_failure(tmp_path):
    session, executor, operation, original = configured(tmp_path)
    requests = []

    def reject(expected, worker, operation_id, key):
        requests.append(key)
        raise NativeMovementError(Outcome.INHIBITED, Receipt(
            original.grant, key, Host(22, 3, 44), original.window, original.revision,
            original.settings, Outcome.INHIBITED, 3))

    def failed_close():
        raise OSError("secondary close failure")

    session.acquire, session.close = reject, failed_close
    result = executor.execute(operation, stop_signal=threading.Event())
    assert "NativeMovementError/INHIBITED" in result.detail
    assert f"acquisition={requests[0]}" in result.detail
    assert "receipt=g10/s20/MANUAL/f3/r7" in result.detail
    assert "; cleanup: native lease closure unresolved (OSError)" in result.detail
    assert not result.native_cleanup_confirmed
    assert len(result.detail) <= 512


def test_receiptless_native_rejection_is_not_fabricated(tmp_path):
    session, executor, operation, _ = configured(tmp_path)
    session.acquire = lambda *args: (_ for _ in ()).throw(NativeMovementError(Outcome.UNAVAILABLE))
    result = executor.execute(operation, stop_signal=threading.Event())
    assert "NativeMovementError/UNAVAILABLE" in result.detail
    assert "receipt=absent" in result.detail and "producer=" not in result.detail
    assert not result.native_cleanup_confirmed


def test_ambiguous_timeout_keeps_same_request_and_bounded_detail_with_cleanup_failure(tmp_path):
    session, executor, operation, original = configured(tmp_path)
    requests = []

    def timeout(*args):
        requests.append(args)
        raise NativeActionChannelTimeout("held receipt\n" + "x" * 2000)

    def failed_close():
        raise OSError("secondary close")

    session.acquire, session.close = timeout, failed_close
    result = executor.execute(operation, stop_signal=threading.Event())
    assert len(requests) == 2 and requests[0] == requests[1]
    assert requests[0][0] is original
    assert f"acquisition={requests[0][3]}" in result.detail
    assert "held receipt" in result.detail
    assert "cleanup: native lease closure unresolved" in result.detail
    assert "\n" not in result.detail and len(result.detail) <= 512
    assert not result.native_cleanup_confirmed
