"""Travel receipts preserve the initiating stop through real manager cleanup."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from test_manager_movement import context, make_executor

from shadowbane_lab.cli_commands import manager
from shadowbane_lab.client_extension.action_channel import NativeActionChannelError
from shadowbane_lab.client_extension.movement_wire import Owner
from shadowbane_lab.manager.operation import WorkerOperationKind
from shadowbane_lab.manager.worker import WorkerDispatchGate
from shadowbane_lab.manager.worker_runtime import _OperationStopSignal


def setup_executor(tmp_path):
    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    gate = MagicMock(spec=WorkerDispatchGate)
    gate.denial_reason.return_value = None
    ledger = MagicMock()
    ledger.pending_for.return_value = ()
    parent = _OperationStopSignal(gate, ledger, executor._binding, "worker", 222, 333)
    operation = SimpleNamespace(
        client_id="client", instance_id="instance", worker_id="worker",
        operation_id="travel-run", kind=WorkerOperationKind.TRAVEL,
        destination=SimpleNamespace(lt=30, lg=40, radius=2),
    )
    return executor, session, gate, ledger, parent, operation


@pytest.mark.parametrize("trigger,code,state,reason", [
    ("cancel", 0, "cancelled", "explicit cancel or stop operation is pending"),
    ("stop", 0, "cancelled", "explicit cancel or stop operation is pending"),
    ("cancel", 2, "failed",
     "explicit cancel or stop operation is pending; travel exited with status 2"),
    ("permit", 0, "failed", "dispatch permit expired 0.010s ago"),
    ("inbox", 0, "failed", "operation inbox read failed: PermissionError: inbox locked"),
    ("native", 0, "failed", "native_movement_owner_revoked"),
    ("native", 2, "failed", "native_movement_owner_revoked"),
])
def test_travel_preserves_first_stop_cause(tmp_path, monkeypatch, trigger, code, state, reason):
    executor, session, gate, ledger, parent, operation = setup_executor(tmp_path)
    observed = []

    def travel(**kwargs):
        movement = kwargs["stop_signal"]
        assert movement is executor._movement
        assert len(session.acquire_calls) == 1
        if trigger in ("cancel", "stop"):
            kind = WorkerOperationKind.CANCEL if trigger == "cancel" else WorkerOperationKind.STOP
            ledger.pending_for.return_value = (SimpleNamespace(kind=kind),)
        elif trigger == "permit":
            gate.denial_reason.return_value = "dispatch permit expired 0.010s ago"
        elif trigger == "inbox":
            ledger.pending_for.side_effect = PermissionError("inbox locked")
        else:
            session.observed = replace(session.observed, owner=Owner.NONE,
                                       generation=session.observed.generation + 1)
        assert movement.is_set()
        observed.append(movement.stop_cause)
        # A later cancellation and final closure cannot relabel a native failure.
        ledger.pending_for.side_effect = None
        ledger.pending_for.return_value = (SimpleNamespace(kind=WorkerOperationKind.CANCEL),)
        return code

    monkeypatch.setattr(manager, "_run_travel", travel)
    result = executor.execute(operation, stop_signal=parent)
    assert result.state.value == state
    assert result.detail == reason
    assert observed[0].kind == ("requested" if trigger in ("cancel", "stop") else "interrupted")
    assert len(session.acquire_calls) == len(session.stop_calls) == session.closed == 1
    assert executor._movement is None


@pytest.mark.parametrize("execution_error", [False, True])
def test_travel_cleanup_failure_appends_without_erasing_primary(tmp_path, monkeypatch,
                                                              execution_error):
    executor, session, _, _, parent, operation = setup_executor(tmp_path)

    def travel(**kwargs):
        kwargs["stop_signal"].interrupt("native movement renewal failed: original evidence")
        if execution_error:
            raise ValueError("primary route failure")
        return 2

    def failed_stop(*args):
        session.stop_calls.append(args)
        raise NativeActionChannelError("cleanup transport failed")

    session.stop = failed_stop
    monkeypatch.setattr(manager, "_run_travel", travel)
    result = executor.execute(operation, stop_signal=parent)
    assert result.state.value == "failed"
    primary, cleanup = result.detail.split("; cleanup: ", 1)
    assert ("primary route failure" if execution_error else
            "native movement renewal failed: original evidence") in primary
    assert "native stop unresolved" in cleanup
    assert result.native_cleanup_confirmed is False
    assert len(session.acquire_calls) == len(session.stop_calls) == session.closed == 1
    assert executor._movement is None


@pytest.mark.parametrize("trigger", [
    "cancel", "stop", "native", "failure_then_cancel", "cancel_cleanup_failure",
])
def test_real_travel_runner_cli_and_executor_stop_contract(tmp_path, monkeypatch, trigger):
    from test_cli import ClientCliTests

    from shadowbane_lab.travel import TravelController, TravelPhase, TravelRunner, parse_go_command

    executor, session, _, ledger, parent, operation = setup_executor(tmp_path)

    def travel(**kwargs):
        movement = kwargs["stop_signal"]
        if trigger in ("cancel", "stop", "cancel_cleanup_failure"):
            kind = WorkerOperationKind.CANCEL if trigger != "stop" else WorkerOperationKind.STOP
            ledger.pending_for.return_value = (SimpleNamespace(kind=kind),)
        elif trigger == "native":
            session.observed = replace(session.observed, owner=Owner.NONE,
                                       generation=session.observed.generation + 1)
        reader = SimpleNamespace(observe=MagicMock(side_effect=ValueError("position unavailable")))
        result = TravelRunner(
            controller=TravelController(parse_go_command("go 30 40 2")),
            position_reader=reader, player_vitals_reader=reader,
            dispatcher=kwargs["movement_dispatcher"], stop_signal=movement,
            sleeper=lambda _: None,
        ).run()
        assert result.final_phase is TravelPhase.STOPPED
        requested = trigger in ("cancel", "stop", "cancel_cleanup_failure")
        if trigger == "failure_then_cancel":
            assert result.terminal_reason != "emergency_stop"
            ledger.pending_for.return_value = (SimpleNamespace(kind=WorkerOperationKind.CANCEL),)
        else:
            assert result.terminal_reason == "emergency_stop"
        # Only native discovery is substituted by the shared CLI fixture. The
        # actual runner result passes through the production JSON/exit boundary.
        return ClientCliTests()._assert_travel_process_binding(
            native_movement=True, run_result=result, stop_signal=movement,
            expected_exit=0 if requested else 2, expected_cancelled=requested,
        )

    if trigger == "cancel_cleanup_failure":
        def failed_stop(*args):
            session.stop_calls.append(args)
            raise NativeActionChannelError("cleanup transport failed")
        session.stop = failed_stop
    monkeypatch.setattr(manager, "_run_travel", travel)
    result = executor.execute(operation, stop_signal=parent)
    assert result.state.value == ("cancelled" if trigger in ("cancel", "stop") else "failed")
    if trigger == "native":
        assert result.detail == "native_movement_owner_revoked"
    elif trigger == "failure_then_cancel":
        assert result.detail.endswith("travel exited with status 2")
    elif trigger == "cancel_cleanup_failure":
        assert result.detail.startswith("explicit cancel or stop operation is pending; cleanup:")
        assert result.native_cleanup_confirmed is False
    else:
        assert result.detail == "explicit cancel or stop operation is pending"
    assert len(session.acquire_calls) == len(session.stop_calls) == session.closed == 1
