import threading
from dataclasses import replace
from types import SimpleNamespace

from shadowbane_lab.client_extension.action_channel import NativeActionChannelTimeout
from shadowbane_lab.client_extension.movement_session import NativeMovementError
from shadowbane_lab.client_extension.movement_wire import Outcome, Owner
from shadowbane_lab.manager.movement import OperationMovement
from tests.test_native_movement_dispatcher import setup


def context():
    session, dispatcher, decision = setup()
    grant = dispatcher.grant
    session.acquire_calls = []
    session.stop_calls = []
    session.renew_calls = []
    session.closed = 0

    def acquire(*args):
        session.acquire_calls.append(args)
        return grant

    def stop(*args):
        session.stop_calls.append(args)

    def close():
        session.closed += 1

    session.acquire = acquire
    session.stop = stop
    session.close = close
    session.renew = session.renew_calls.append
    parent = threading.Event()
    operation = SimpleNamespace(worker_id="worker", operation_id="operation")
    return OperationMovement(operation, session, parent), session, decision


def test_manual_takeover_latches_both_dispatch_and_renewal_without_reacquisition():
    movement, session, decision = context()
    assert movement.acquire()
    movement.maintain()
    assert len(session.renew_calls) == 1
    old = session.observed
    session.observed = replace(old, owner=Owner.MANUAL, generation=old.generation + 1)
    assert movement.is_set()
    session.observed = old  # Old apparent status cannot revive the latched operation.
    movement.maintain()
    assert movement.is_set()
    assert len(session.acquire_calls) == len(session.renew_calls) == 1
    assert movement.finish() is None
    assert session.stop_calls[0][0].ownership == old
    assert session.closed == 1
    assert movement.finish() is None
    assert session.closed == 1


def test_revoked_permit_stops_exact_grant_even_after_gate_closes():
    movement, session, _ = context()
    assert movement.acquire()
    movement.parent.set()
    movement.maintain()
    assert not session.renew_calls
    assert movement.is_set()
    assert movement.finish() is None
    assert len(session.stop_calls) == 1


def test_ambiguous_acquire_reuses_original_snapshot_and_uuid():
    movement, session, _ = context()
    original = session.acquire

    def delayed(*args):
        grant = original(*args)
        if len(session.acquire_calls) == 1:
            raise NativeActionChannelTimeout("held receipt")
        return grant

    session.acquire = delayed
    assert movement.acquire()
    assert session.acquire_calls[0] == session.acquire_calls[1]
    assert session.acquire_calls[0][0] is session.acquire_calls[1][0]
    movement.finish()


def test_stale_cleanup_never_acquires_replacement_and_timeout_retains_stop_uuid():
    movement, session, _ = context()
    assert movement.acquire()

    def delayed(*args):
        session.stop_calls.append(args)
        if len(session.stop_calls) == 1:
            raise NativeActionChannelTimeout("held stop")
        raise NativeMovementError(Outcome.STALE)

    session.stop = delayed
    assert movement.finish() is None
    assert session.stop_calls[0] == session.stop_calls[1]
    assert len(session.acquire_calls) == 1
    assert session.closed == 1


def test_blocked_acquisition_does_not_block_another_clients_maintenance():
    movement, session, _ = context()
    other, other_session, _ = context()
    assert other.acquire()
    entered, release = threading.Event(), threading.Event()
    original = session.acquire

    def held(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    session.acquire = held
    thread = threading.Thread(target=movement.acquire)
    thread.start()
    try:
        assert entered.wait(5)
        movement.maintain()  # Nonblocking while own acquisition is held.
        other.maintain()
        assert len(other_session.renew_calls) == 1
        assert not session.renew_calls
    finally:
        release.set()
        thread.join(5)
        movement.finish()
        other.finish()
    assert not thread.is_alive()


def test_terminal_cleanup_serializes_with_held_renewal_and_never_revives():
    movement, session, _ = context()
    assert movement.acquire()
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def held(grant):
        entered.set()
        assert release.wait(5)
        assert session.closed == 0
        session.renew_calls.append(grant)

    session.renew = held
    renewal = threading.Thread(target=movement.maintain)
    cleanup = threading.Thread(target=lambda: (movement.finish(), finished.set()))
    renewal.start()
    try:
        assert entered.wait(5)
        cleanup.start()
        assert not finished.is_set()
    finally:
        release.set()
        renewal.join(5)
        cleanup.join(5)
    assert finished.is_set()
    movement.maintain()
    assert len(session.renew_calls) == 1
    assert session.closed == 1


def test_unresolved_stop_is_reported_and_lease_closed():
    movement, session, _ = context()
    assert movement.acquire()

    def timeout(*args):
        raise NativeActionChannelTimeout("still pending")

    session.stop = timeout
    problem = movement.finish()
    assert "unresolved" in problem and movement.stop_key in problem
    assert session.closed == 1


def make_executor(tmp_path, session):
    from shadowbane_lab.cli_commands.manager import _ExactWorkerEngineExecutor
    from shadowbane_lab.manager.worker_runtime import ExactClientWorkerBinding

    binding = ExactClientWorkerBinding("client", "instance", 123, 456, 789, "worker")
    return _ExactWorkerEngineExecutor(
        binding,
        destination_state_path=tmp_path / "destinations.json",
        client_profile_path=tmp_path / "client.json",
        native_position_profile_path=None,
        native_vitals_profile_path=None,
        pve_client_profile_path=tmp_path / "pve.json",
        pve_hotbar_config_path=None,
        pve_evidence_directory=tmp_path / "evidence",
        navigation_cache_directory=tmp_path / "cache",
        learned_navigation_state_path=tmp_path / "learned.json",
        pve_max_kills=1,
        pve_max_seconds=10,
        pve_max_encounter_seconds=5,
        pve_recovery_timeout_seconds=5,
        pve_poll_ms=100,
        pve_camp_radius=20,
        pve_retained_trace_steps=5,
        travel_max_seconds=10,
        travel_poll_ms=100,
        travel_click_interval_ms=100,
        movement_session_factory=lambda identity, window: session,
    )


def test_executor_reserves_before_ipc_and_passes_same_gate_and_grant(tmp_path, monkeypatch):
    from shadowbane_lab.cli_commands import manager
    from shadowbane_lab.manager import WorkerOperationKind, WorkerOperationState

    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    operation = SimpleNamespace(
        client_id="client",
        instance_id="instance",
        worker_id="worker",
        operation_id="route",
        kind=WorkerOperationKind.TRAVEL,
        destination=SimpleNamespace(lt=30, lg=40, radius=2),
    )
    entered, release = threading.Event(), threading.Event()
    results = []

    def travel(**kwargs):
        assert kwargs["movement_dispatcher"] is executor._movement.dispatcher
        assert kwargs["stop_signal"] is executor._movement
        entered.set()
        assert release.wait(5)
        return 0

    monkeypatch.setattr(manager, "_run_travel", travel)
    thread = threading.Thread(
        target=lambda: results.append(executor.execute(operation, stop_signal=threading.Event()))
    )
    thread.start()
    try:
        assert entered.wait(5)
        duplicate = executor.execute(operation, stop_signal=threading.Event())
        assert duplicate.state == WorkerOperationState.FAILED
        executor.maintain(operation, threading.Event())
        assert len(session.renew_calls) == 1
        assert len(session.acquire_calls) == 1
    finally:
        release.set()
        thread.join(5)
    assert results[0].state == WorkerOperationState.SUCCEEDED
    assert executor._movement is None
    assert len(session.stop_calls) == session.closed == 1
    assert (tmp_path / "learned.json").is_file()


def test_idle_stop_does_not_create_session_or_stop_manual_owner(tmp_path):
    from shadowbane_lab.manager import WorkerOperationKind, WorkerOperationState

    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    operation = SimpleNamespace(
        client_id="client",
        instance_id="instance",
        worker_id="worker",
        kind=WorkerOperationKind.STOP,
    )
    assert executor.execute(operation, stop_signal=threading.Event()).state == (
        WorkerOperationState.SUCCEEDED
    )
    assert not session.acquire_calls and not session.stop_calls
    assert session.closed == 0


def test_operation_context_uses_real_native_interprocess_movement():
    import os
    import subprocess
    import sys
    import uuid
    from pathlib import Path

    import pytest

    from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
    from shadowbane_lab.client_extension.movement_session import NativeMovementSession
    from shadowbane_lab.travel.model import TravelPhase

    configured = os.environ.get("WONDERBANE_MOVEMENT_RUNTIME_TEST")
    if sys.platform != "win32" or not configured:
        pytest.skip("requires the Windows native runtime fixture")
    binary = Path(configured)
    assert binary.is_file()
    process = subprocess.Popen(
        [str(binary), "ipc"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    movement = None
    try:
        pid, creation, window = map(int, process.stdout.readline().split())
        session = NativeMovementSession(NativeClientProcessIdentity(pid, creation), window)
        operation = SimpleNamespace(worker_id="worker", operation_id=str(uuid.uuid4()))
        movement = OperationMovement(operation, session, threading.Event())
        assert movement.acquire()  # 1st receipt
        _, _, decision = setup()
        assert movement.dispatcher.dispatch(decision).accepted  # 2nd
        terminal = replace(
            decision,
            phase=TravelPhase.COMPLETE,
            terminal_reason="arrived",
            minimap_direction=None,
            click_destination=None,
            maneuver=None,
        )
        assert movement.dispatcher.stop_movement(terminal).accepted  # 3rd
        movement.maintain()
        assert not movement.is_set()
        assert movement.dispatcher.dispatch(replace(decision, decision_id=2)).accepted  # 4th
        assert movement.dispatcher.stop_movement(replace(terminal, decision_id=2)).accepted  # 5th
        assert movement.finish() is None  # 6th: terminal grant stop
        output, error = process.communicate(timeout=5)
        assert process.returncode == 0, output + error
    finally:
        if movement is not None:
            movement.finish()
        if process.poll() is None:
            process.kill()
            process.communicate()
