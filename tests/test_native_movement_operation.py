import threading
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shadowbane_lab.client_extension import movement_operation as module
from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelError,
    NativeActionChannelTimeout,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementError,
    NativeMovementGrant,
)
from shadowbane_lab.client_extension.movement_wire import Grant, Host, Outcome, Owner
from shadowbane_lab.protocol import Vector2
from shadowbane_lab.travel.model import TravelDecision, TravelManeuver, TravelPhase


@pytest.fixture
def setup(monkeypatch):
    grant = NativeMovementGrant(
        NativeClientProcessIdentity(123, 456),
        789,
        Grant(10, 20, Owner.AUTOMATION, "worker", "operation"),
        Host(22, 3, 44),
        str(uuid.uuid4()),
    )
    session = MagicMock()
    session.snapshot.return_value = SimpleNamespace(grant=grant.ownership, flags=3)
    session.acquire.return_value = grant
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(module, "NativeMovementSession", factory)
    guard = MagicMock()
    guard.require_target.return_value = SimpleNamespace(
        process_id=123, process_started_at_100ns=456, window_handle=789
    )
    parent = threading.Event()
    operation = module.NativeMovementOperation(guard, parent)
    decision = TravelDecision(
        1,
        1,
        TravelPhase.TRAVELING,
        0,
        50,
        1,
        minimap_direction=Vector2(1, 0),
        maneuver=TravelManeuver.DIRECT,
        click_destination=Vector2(123, 456),
    )
    return operation, session, guard, parent, decision, factory


def test_idle_planner_keeps_immutable_grant_and_closes_with_real_stop(setup):
    operation, session, _, _, decision, factory = setup
    renewed = threading.Event()
    session.renew.side_effect = lambda grant: renewed.set()
    with operation:
        assert operation.dispatch(decision).accepted
        assert renewed.wait(2), "slow planner must not expire native lease"
        assert not operation.is_set()
    factory.assert_called_once_with(NativeClientProcessIdentity(123, 456), 789)
    session.acquire.assert_called_once()
    assert session.move.call_args.args[1] == (123, 0.0, -456)
    assert session.stop.call_args.args[0] == session.acquire.return_value
    session.close.assert_called_once()
    assert not operation._thread.is_alive()
    assert not operation.dispatch(decision).accepted
    with pytest.raises(RuntimeError):
        operation.__enter__()


@pytest.mark.parametrize("cause", ["parent", "takeover", "window", "creation", "process", "focus"])
def test_cancellation_latches_and_does_not_reacquire_or_resume(setup, cause):
    operation, session, guard, parent, decision, _ = setup
    with operation:
        original = guard.require_target.return_value
        if cause == "parent":
            parent.set()
        elif cause == "takeover":
            session.snapshot.return_value.grant = Grant(11, 20, Owner.MANUAL)
        elif cause == "focus":
            guard.require_target.side_effect = RuntimeError("focus lost")
        else:
            values = vars(original).copy()
            values[
                {
                    "window": "window_handle",
                    "creation": "process_started_at_100ns",
                    "process": "process_id",
                }[cause]
            ] += 1
            guard.require_target.return_value = SimpleNamespace(**values)
        assert operation.is_set()
        parent.clear()
        guard.require_target.side_effect = None
        guard.require_target.return_value = original
        session.snapshot.return_value.grant = session.acquire.return_value.ownership
        assert operation.is_set() and not operation.dispatch(decision).accepted
    session.acquire.assert_called_once()
    session.move.assert_not_called()
    assert session.stop.call_args.args[0] == session.acquire.return_value


def test_ambiguous_acquire_and_stop_retry_original_identity(setup):
    operation, session, *_ = setup
    grant = session.acquire.return_value
    session.acquire.side_effect = [NativeActionChannelTimeout("delayed"), grant]
    session.stop.side_effect = [NativeActionChannelTimeout("delayed"), None]
    with operation:
        pass
    assert session.acquire.call_args_list[0] == session.acquire.call_args_list[1]
    assert session.stop.call_args_list[0] == session.stop.call_args_list[1]
    session.close.assert_called_once()


def test_renew_failure_stops_and_never_rearms(setup):
    operation, session, _, _, decision, _ = setup
    stopped = threading.Event()
    session.renew.side_effect = NativeActionChannelError("lease lost")
    session.stop.side_effect = lambda *args: stopped.set()
    with operation:
        assert stopped.wait(2)
        assert operation.is_set() and not operation.dispatch(decision).accepted
    session.acquire.assert_called_once()
    session.stop.assert_called_once()


@pytest.mark.parametrize("outcome", [Outcome.STALE, Outcome.STOP_FAILED])
def test_terminal_rejection_is_safe_for_new_owner_and_reports_failure(setup, outcome):
    operation, session, *_ = setup
    session.stop.side_effect = NativeMovementError(outcome)
    if outcome == Outcome.STALE:
        with operation:
            pass
    else:
        with pytest.raises(NativeActionChannelError, match="stop was not confirmed"):
            with operation:
                pass
    session.close.assert_called_once()


def test_unavailable_native_closes_without_acquisition_or_fallback(setup):
    operation, session, *_ = setup
    session.snapshot.return_value.flags = 0
    with pytest.raises(NativeActionChannelError, match="unavailable"):
        with operation:
            pass
    session.acquire.assert_not_called()
    session.close.assert_called_once()


def test_close_waits_for_held_renew_before_terminal_stop(setup):
    operation, session, *_ = setup
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()

    def renew(grant):
        entered.set()
        assert release.wait(3)

    session.renew.side_effect = renew
    operation.__enter__()
    assert entered.wait(2)
    thread = threading.Thread(target=lambda: (operation.close(), closed.set()))
    thread.start()
    try:
        assert not closed.wait(0.05)
        session.stop.assert_not_called()
    finally:
        release.set()
        thread.join(3)
    assert closed.is_set()
    session.stop.assert_called_once()
    session.close.assert_called_once()


def test_standalone_context_real_native_process_renews_across_slow_planner():
    import os
    import subprocess
    from pathlib import Path

    configured = os.environ.get("WONDERBANE_MOVEMENT_RUNTIME_TEST")
    if not configured:
        pytest.skip("set WONDERBANE_MOVEMENT_RUNTIME_TEST to the built native runtime fixture")
    binary = Path(configured)
    assert binary.is_file(), "required native IPC fixture is missing"
    process = subprocess.Popen(
        [str(binary), "ipc"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        pid, creation, window = map(int, process.stdout.readline().split())
        guard = MagicMock()
        guard.require_target.return_value = SimpleNamespace(
            process_id=pid, process_started_at_100ns=creation, window_handle=window
        )
        with module.NativeMovementOperation(guard, threading.Event()) as operation:
            renewed = threading.Event()
            original = operation._session.renew
            count = 0

            def renew(grant):
                nonlocal count
                original(grant)
                count += 1
                if count == 5:
                    renewed.set()

            operation._session.renew = renew
            assert renewed.wait(4), "operation must survive more than the native 1s lease"
            for identifier in range(1, 5):
                decision = TravelDecision(
                    identifier,
                    identifier,
                    TravelPhase.TRAVELING,
                    0,
                    50,
                    1,
                    minimap_direction=Vector2(1, 0),
                    maneuver=TravelManeuver.DIRECT,
                    click_destination=Vector2(30 + identifier, 40 + identifier),
                )
                assert operation.dispatch(decision).accepted
        output, error = process.communicate(timeout=5)
        assert process.returncode == 0, output + error
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
