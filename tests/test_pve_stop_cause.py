"""A native stop must survive operation, runner, journal and CLI classification."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from test_native_movement_operation import setup as operation_fixture
from test_pve_native_proposals import observe

from shadowbane_lab.client_extension.action_channel import NativeActionChannelError
from shadowbane_lab.client_extension.movement_wire import Grant, Owner
from shadowbane_lab.client_input import AnyStopSignal, EventEmergencyStop
from shadowbane_lab.client_input.stop import StopCause, observed_stop_cause
from shadowbane_lab.client_observation import NativeGroupObservation
from shadowbane_lab.pve import PvEController, PvEControllerConfig, PvERunner
from shadowbane_lab.pve.model import PvECombatCleanupResult

setup = operation_fixture


def run_stopped(signal, *, cleanup_failure=False):
    controller = PvEController(PvEControllerConfig())
    if cleanup_failure:
        controller.step(observe())  # Reserve an exact target before interruption.
    def source(field):
        return SimpleNamespace(process_id=123, observe=lambda: getattr(observe(), field))
    cleanup = SimpleNamespace(cleanup=lambda request: PvECombatCleanupResult(
        request, not cleanup_failure, error='unconfirmed' if cleanup_failure else None))
    steps, progress = [], []
    result = PvERunner(controller=controller, health_reader=source('target'),
        player_vitals_reader=source('player'), player_position_reader=source('player_position'),
        target_position_reader=source('target_position'), population_reader=source('population'),
        player_action_reader=SimpleNamespace(process_id=123,
            observe_player=lambda: observe().player_action),
        group_reader=SimpleNamespace(process_id=123,
            observe=lambda: NativeGroupObservation(False, False, ())), party_group_id='party',
        dispatcher=SimpleNamespace(advance=MagicMock()), combat_cleanup=cleanup,
        stop_signal=signal, trace_sink=steps.append, progress_sink=progress.append).run()
    assert steps and steps[0].stop_cause == result.stop_cause
    assert steps[0].as_dict()['stop_cause'] == result.stop_cause.as_dict()
    assert progress[0].reason == steps[0].decision.terminal_reason
    return result


def assert_cli(result, *, successful):
    # Exercise the original CLI serialization/footer/exit path using the actual
    # operation->runner result, with only native discovery/launch fixtures mocked.
    from test_cli import ClientCliTests
    ClientCliTests()._assert_pve_process_binding(policy='basic', check_preparation=True,
        run_result=result, expected_exit=0 if successful else 2)


@pytest.mark.parametrize('failure,reason', [
    ('unavailable', 'native_movement_unavailable'),
    ('status', 'native_movement_status:NativeActionChannelError'),
    ('revoked', 'native_movement_owner_revoked'),
    ('guard', 'native_movement_guard:ValueError'),
    ('renew', 'native_movement_renew:NativeActionChannelError'),
])
def test_native_first_cause_survives_runner_cli_and_later_cancel(setup, failure, reason):
    operation, session, guard, parent, _, _ = setup
    with operation:
        if failure == 'unavailable':
            session.snapshot.return_value.flags = 0
        elif failure == 'status':
            session.snapshot.side_effect = NativeActionChannelError('unreadable')
        elif failure == 'revoked':
            session.snapshot.return_value.grant = Grant(11, 20, Owner.MANUAL)
        elif failure == 'guard':
            guard.require_target.side_effect = ValueError('replaced')
        else:
            session.renew.side_effect = NativeActionChannelError('renew failed')
            assert operation._cancelled.wait(2)
        assert operation.is_set()
        assert operation.interruption_reason == reason
        reads = session.snapshot.call_count
        cause = observed_stop_cause(operation)
        assert cause == StopCause(reason, 'interrupted')
        assert session.snapshot.call_count == reads  # Passive evidence never polls.
        parent.set()
        result = run_stopped(operation)
        assert result.terminal_reason == reason
        assert result.stop_cause == cause
        assert_cli(result, successful=False)
    assert operation.stop_cause == cause  # close cannot replace the initiating reason.
    session.acquire.assert_called_once()
    session.move.assert_not_called()


@pytest.mark.parametrize('requested_by', ['timer', 'hotkey'])
def test_external_stop_stays_requested_without_inventing_which_event(setup, requested_by):
    operation, _, _, _, _, _ = setup
    timer, hotkey = EventEmergencyStop(), EventEmergencyStop()
    operation.parent = AnyStopSignal(timer, hotkey)
    with operation:
        (timer if requested_by == 'timer' else hotkey).trip()
        result = run_stopped(operation)
        assert result.terminal_reason == 'emergency_stop'
        assert result.stop_cause == StopCause('emergency_stop', 'requested')
        assert_cli(result, successful=True)


def test_cleanup_failure_keeps_initiating_native_evidence(setup):
    operation, session, _, _, _, _ = setup
    with operation:
        session.snapshot.return_value.flags = 0
        result = run_stopped(operation, cleanup_failure=True)
        assert result.terminal_reason == 'combat_cleanup_unconfirmed'
        assert result.stop_cause == StopCause('native_movement_unavailable', 'interrupted')
        assert result.trace[-1].combat_cleanup.confirmed is False
        assert result.trace[-1].stop_cause == result.stop_cause
        assert_cli(result, successful=False)


def test_composite_preserves_observed_native_first_cause_without_polling_property():
    external = EventEmergencyStop()
    native = SimpleNamespace(is_set=MagicMock(return_value=True),
                             interruption_reason='native_movement_unavailable')
    combined = AnyStopSignal(external, native)
    assert combined.is_set()
    native.is_set.assert_called_once()
    assert observed_stop_cause(combined) == StopCause('native_movement_unavailable', 'interrupted')
    external.trip()
    assert combined.is_set()
    assert observed_stop_cause(combined).kind == 'interrupted'
    native.is_set.assert_called_once()


def test_manager_operation_reason_is_not_external_cancel():
    from shadowbane_lab.manager.movement import OperationMovement
    movement = OperationMovement(SimpleNamespace(), MagicMock(), EventEmergencyStop())
    movement.interrupt('native movement renewal failed: NativeActionChannelError')
    result = run_stopped(movement)
    assert result.stop_cause.kind == 'interrupted'
    assert result.terminal_reason == movement.reason
    assert_cli(result, successful=False)


def test_generic_emergency_label_without_requested_proof_is_not_success(setup):
    operation, _, _, parent, _, _ = setup
    with operation:
        parent.set()
        result = run_stopped(operation)
        assert_cli(replace(result, stop_cause=None), successful=False)

@pytest.mark.parametrize('cause,expected', [
    ('cancel', 'cancelled'), ('stop', 'cancelled'),
    ('permit', 'failed'), ('inbox', 'failed'), ('native', 'failed'),
    ('cancel_cleanup_failure', 'failed'),
])
def test_actual_worker_executor_preserves_requested_vs_interrupted(tmp_path, monkeypatch,
                                                                 cause, expected):
    from test_manager_movement import context, make_executor

    from shadowbane_lab.cli_commands import manager
    from shadowbane_lab.manager.operation import WorkerOperationKind
    from shadowbane_lab.manager.worker import WorkerDispatchGate
    from shadowbane_lab.manager.worker_runtime import _OperationStopSignal

    _, session, _ = context()
    executor = make_executor(tmp_path, session)
    gate = MagicMock(spec=WorkerDispatchGate)
    gate.denial_reason.return_value = None
    ledger = MagicMock()
    ledger.pending_for.return_value = ()
    parent = _OperationStopSignal(gate, ledger, executor._binding, 'worker', 222, 333)
    operation = SimpleNamespace(client_id='client', instance_id='instance', worker_id='worker',
        operation_id='pve-run', kind=WorkerOperationKind.PVE)
    observed = []

    def pve(**kwargs):
        # Model the real post-setup boundary before injecting an active-run stop.
        assert not session.acquire_calls
        dispatcher = kwargs['movement_acquirer']()
        assert dispatcher is executor._movement.dispatcher
        assert len(session.acquire_calls) == 1
        if cause in ('cancel', 'cancel_cleanup_failure', 'stop'):
            kind = WorkerOperationKind.STOP if cause == 'stop' else WorkerOperationKind.CANCEL
            ledger.pending_for.return_value = (SimpleNamespace(kind=kind),)
        elif cause == 'permit':
            gate.denial_reason.return_value = 'dispatch permit expired 0.010s ago'
        elif cause == 'inbox':
            ledger.pending_for.side_effect = PermissionError('inbox locked')
        else:
            session.observed = Grant(11, 20, Owner.MANUAL)
        result = run_stopped(kwargs['stop_signal'],
                             cleanup_failure=cause == 'cancel_cleanup_failure')
        observed.append(result)
        successful = result.terminal_reason == 'emergency_stop'
        assert_cli(result, successful=successful)
        return 0 if successful else 2

    monkeypatch.setattr(manager, '_run_pve', pve)
    result = executor.execute(operation, stop_signal=parent)
    assert result.state.value == expected
    assert len(observed) == 1
    stop_cause = observed[0].stop_cause
    assert stop_cause.reason in result.detail
    if cause in ('cancel', 'stop', 'cancel_cleanup_failure'):
        assert stop_cause.kind == 'requested'
        assert stop_cause.reason == 'explicit cancel or stop operation is pending'
        if cause == 'cancel_cleanup_failure':
            assert 'status 2' in result.detail
    else:
        assert stop_cause.kind == 'interrupted'
    assert len(session.acquire_calls) == len(session.stop_calls) == session.closed == 1
