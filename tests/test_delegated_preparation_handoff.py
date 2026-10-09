from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.condemn_progress import CondemnProgressStore
from shadowbane_lab.client_extension.guard_spending_journal import GuardSpendingJournal
from shadowbane_lab.manager.condemn_control import CondemnWorkerExecutor
from shadowbane_lab.manager.guard_control import GuardWorkerExecutor
from shadowbane_lab.manager.operation import WorkerOperationExecution, WorkerOperationState
from tests.test_guard_upgrade_journal import COMMAND, FINISHED, IDENTITY, SUBMITTED


@pytest.mark.parametrize("executor_class", [GuardWorkerExecutor, CondemnWorkerExecutor])
@pytest.mark.parametrize("journal_kind", ["guard", "condemn"])
def test_delegate_return_does_not_hide_pending_native_intent(
        tmp_path, executor_class, journal_kind):
    executor = object.__new__(executor_class)
    executor.store = lambda: SimpleNamespace(root=tmp_path)
    completed = WorkerOperationExecution(WorkerOperationState.SUCCEEDED, "job returned")
    if journal_kind == "guard":
        journal = GuardSpendingJournal(tmp_path)
        def entered(*args, **kwargs):
            journal.submit(IDENTITY, COMMAND, lambda: SUBMITTED)
            return completed
        def finish():
            journal.observe(IDENTITY, FINISHED)
    else:
        from tests.test_condemn_progress import TARGET, complete, row, setup
        journal, window, request, receipt = setup(tmp_path)
        def entered(*args, **kwargs):
            journal.submit(request, TARGET, window, row(False), lambda: receipt)
            return completed
        def finish():
            complete(journal, window, request)
    executor._execute = entered
    with pytest.raises(RuntimeError):
        executor.execute(None, stop_signal=None)
    # Only actual correlated native completion releases the retained intent.
    finish()
    executor._execute = lambda *args, **kwargs: completed
    result = executor.execute(None, stop_signal=None)
    assert result.native_cleanup_confirmed
    assert result.state is WorkerOperationState.SUCCEEDED
    GuardSpendingJournal(tmp_path).assert_idle()
    CondemnProgressStore(tmp_path).assert_idle()


@pytest.mark.parametrize("executor_class", [GuardWorkerExecutor, CondemnWorkerExecutor])
def test_delegate_exception_never_manufactures_cleanup_proof(tmp_path, executor_class):
    executor = object.__new__(executor_class)
    def failed(*args, **kwargs):
        raise TimeoutError("reply unknown")
    executor._execute = failed
    executor.store = lambda: (_ for _ in ()).throw(AssertionError("must not infer idle"))
    with pytest.raises(TimeoutError):
        executor.execute(None, stop_signal=None)



@pytest.mark.parametrize("fault", [
    "missing_create", "missing_keep", "pending_menu", "pending_keep", "wrong_window",
])
def test_completed_vendor_label_cannot_replace_native_journal_proof(fault):
    import json
    import threading

    from shadowbane_lab.manager.vendor_job import require_vendor_handoff_idle
    from tests import test_manager_vendor_control as vendor_tests
    case = vendor_tests.VendorExecutorTests()
    case.setUp()
    try:
        original = case.session.inspect
        def inspect():
            value = original()
            if case.session.state.free_slots == 0:
                case.session.finish_cooking()
            return value
        case.session.inspect = inspect
        result = case.executor.execute(case.op, stop_signal=threading.Event())
        assert result.native_cleanup_confirmed
        record = case.store.current()
        directory = case.store.directory(record["job_id"])
        if fault == "missing_create":
            (directory / "create.json").unlink()
        elif fault == "missing_keep":
            assert record["kept"] or record["excluded"]
            (directory / "keep.json").unlink()
        elif fault == "pending_menu":
            (directory / "inventory-menu.json").write_text(json.dumps({"state":"pending"}))
        elif fault == "pending_keep":
            (directory / "keep.json").write_text(json.dumps({"state":"pending"}))
        else:
            case.session.window += 1
        with pytest.raises((ValueError, RuntimeError)):
            require_vendor_handoff_idle(case.store, case.session, record)
    finally:
        case.doCleanups()


@pytest.mark.parametrize("fault", ["identity", "window", "pending", "unknown", "untyped"])
def test_vendor_local_observation_requires_typed_current_nonpending_receipt(fault):
    from dataclasses import replace

    from shadowbane_lab.client_extension.action_channel import NativeClientProcessIdentity
    from shadowbane_lab.client_extension.movement_wire import Host
    from shadowbane_lab.client_extension.vendor_navigation_wire import Outcome, Receipt, Snapshot
    from shadowbane_lab.manager.vendor_control import _require_local_idle
    binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=123,
                              game_window_handle=1000)
    receipt = Receipt("11111111-2222-4333-8444-555555555555", Host(1,2,3),1000,
                      Outcome.OBSERVED,0,Snapshot(),None)
    identity = NativeClientProcessIdentity(988,123)
    if fault == "identity":
        identity = NativeClientProcessIdentity(988,124)
    elif fault == "window":
        receipt = replace(receipt,window=1001)
    elif fault == "pending":
        receipt = replace(receipt,flags=2)
    elif fault == "unknown":
        receipt = replace(receipt,flags=4)
    else:
        receipt = SimpleNamespace(**receipt.__dict__) if hasattr(receipt,"__dict__") else None
    session = SimpleNamespace(identity=identity,inspect=lambda:receipt)
    with pytest.raises(RuntimeError):
        _require_local_idle(session,binding,Receipt)
