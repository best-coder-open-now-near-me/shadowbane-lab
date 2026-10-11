"""Durable stop intent and bounded current-authority contract regressions."""

import json
from dataclasses import replace

import pytest
from test_manager_operation import (
    CLIENT_ID,
    INSTANCE_ID,
    WORKER_ID,
    WORKER_PROCESS_ID,
    WORKER_PROCESS_STARTED,
    _manifest,
    _permit,
)

from shadowbane_lab.manager.operation import (
    WorkerOperationError,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationReceipt,
    WorkerOperationState,
    new_worker_operation,
)


@pytest.fixture
def ledger(tmp_path):
    value = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100.0)
    value.initialize_stop_authority(CLIENT_ID)
    return value


def operation(number=1, kind=WorkerOperationKind.CANCEL, **target):
    return new_worker_operation(
        replace(_permit(), **target), kind,
        "/cancel" if kind is WorkerOperationKind.CANCEL else "/stop",
        now=100.0, operation_id=f"operation-{number:032x}", ttl_seconds=10.0,
    )


def current(ledger, **overrides):
    return ledger.current_stop_authority(**{
        "client_id": CLIENT_ID, "instance_id": INSTANCE_ID, "worker_id": WORKER_ID,
        "worker_process_id": WORKER_PROCESS_ID,
        "worker_process_started_at_100ns": WORKER_PROCESS_STARTED, "now": 101.0,
        **overrides,
    })


def projection_path(ledger):
    return ledger._directory(CLIENT_ID) / "stop-control.json"


def crash_before_envelope(ledger, monkeypatch, request):
    """Fail the real submit boundary after the write-ahead record is durable."""
    target = ledger._directory(CLIENT_ID) / f"{request.operation_id}.json"
    import shadowbane_lab.manager.operation as module

    original = module.publish_atomic_record

    def interrupted(path, *args, **kwargs):
        if path == target:
            def fail_replace(temporary, destination):
                assert temporary.read_bytes()  # Complete temporary bytes remain private.
                assert not destination.exists()
                raise OSError("simulated interruption before envelope replacement")
            return original(path, *args, **kwargs, replacer=fail_replace)
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(module, "publish_atomic_record", interrupted)
        with pytest.raises(WorkerOperationError, match="could not persist operation"):
            ledger.submit(request)
    assert not target.exists()


def resume(ledger, revision):
    return ledger.set_preparation_enabled(
        CLIENT_ID, instance_id=INSTANCE_ID, worker_id=WORKER_ID,
        worker_process_id=WORKER_PROCESS_ID,
        worker_process_creation=WORKER_PROCESS_STARTED,
        enabled=True, expected_revision=revision,
    )


def test_hot_authority_read_never_locks_scans_or_writes_history(ledger, monkeypatch):
    # The live installation has about thirty historical operation pairs.
    for number in range(1, 31):
        item = operation(number, WorkerOperationKind.PVE)
        ledger.submit(item)
        ledger.publish_receipt(WorkerOperationReceipt.for_operation(
            item, WorkerOperationState.CANCELLED, observed_at=100.5))
    stop = operation(31)
    ledger.submit(stop)
    before = {p: p.read_bytes() for p in ledger.root.rglob("*") if p.is_file()}
    reads = []
    original_read = ledger._read

    def read(path, *args, **kwargs):
        reads.append(path.name)
        return original_read(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("current authority touched locked history or publication")

    monkeypatch.setattr(ledger, "_read", read)
    for name in ("_transaction", "_operation_paths", "_inspect_slot_unlocked",
                 "_recover_stop_projection", "_write_stop_projection"):
        monkeypatch.setattr(ledger, name, forbidden)
    pending, control, unresolved = current(ledger)
    assert pending == (stop,) and not control.enabled and not unresolved
    assert len(reads) == 3
    assert reads[0] == reads[-1] == "stop-control.json"
    assert reads[1].startswith("preparation-control-")
    assert before == {p: p.read_bytes() for p in ledger.root.rglob("*") if p.is_file()}


def test_write_ahead_survives_missing_envelope_and_recovers_exact_intent(ledger, monkeypatch):
    stop = operation()
    crash_before_envelope(ledger, monkeypatch, stop)
    assert current(ledger) == ((stop,), None, True)
    recovered = WorkerOperationLedger(_manifest(), ledger.root, clock=lambda: 100.0)
    recovered.initialize_stop_authority(CLIENT_ID)
    pending, control, unresolved = current(recovered)
    assert pending == (stop,) and not control.enabled and not unresolved
    assert recovered.inspect_slot(CLIENT_ID)[0].operation == stop
    assert recovered.submit(stop).duplicate
    assert current(recovered)[0] == (stop,)


def test_write_ahead_survives_envelope_before_preparation_control(ledger, monkeypatch):
    stop = operation()
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_latch_preparation_stop_unlocked",
                      lambda *args: (_ for _ in ()).throw(OSError("control unavailable")))
        with pytest.raises(WorkerOperationError, match="control unavailable"):
            ledger.submit(stop)
    assert current(ledger) == ((stop,), None, True)
    assert (ledger._directory(CLIENT_ID) / f"{stop.operation_id}.json").is_file()
    ledger.initialize_stop_authority(CLIENT_ID)
    assert current(ledger)[1].enabled is False
    assert current(ledger)[2] is False


def test_expired_orphan_still_blocks_preparation_until_recovered(ledger, monkeypatch):
    stop = operation()
    crash_before_envelope(ledger, monkeypatch, stop)
    assert current(ledger, now=stop.expires_at) == ((), None, True)
    ledger.initialize_stop_authority(CLIENT_ID)
    pending, control, unresolved = current(ledger, now=stop.expires_at + 1)
    assert pending == () and not control.enabled and not unresolved


def test_resume_recovers_orphan_before_superseding_exact_stop(ledger, monkeypatch):
    enabled = resume(ledger, 0)
    stop = operation()
    crash_before_envelope(ledger, monkeypatch, stop)
    # Recovery creates persistent Pause, so an old Resume revision cannot override it.
    with pytest.raises(WorkerOperationError, match="control changed"):
        resume(ledger, enabled.revision)
    paused = current(ledger)[1]
    assert not paused.enabled
    resumed = resume(ledger, paused.revision)
    assert resumed.enabled and stop.operation_id in resumed.superseded_stops
    ledger.initialize_stop_authority(CLIENT_ID)
    assert current(ledger)[1] == resumed
    assert ledger.submit(stop).duplicate
    assert current(ledger)[1] == resumed
    # Resume does not erase the still-pending finite-operation cancellation.
    assert current(ledger)[0] == (stop,)


def test_repeated_cancel_when_preparation_already_disabled_remains_visible(ledger):
    first, second = operation(1), operation(2)
    ledger.submit(first)
    disabled = current(ledger)[1]
    ledger.submit(second)
    pending, control, unresolved = current(ledger)
    assert {item.operation_id for item in pending} == {first.operation_id, second.operation_id}
    assert control == disabled and not unresolved


def test_terminal_receipt_is_durable_before_pruning_and_newer_stop_survives(ledger, monkeypatch):
    first, second = operation(1), operation(2)
    ledger.submit(first)
    ledger.submit(second)
    receipt = WorkerOperationReceipt.for_operation(
        first, WorkerOperationState.CANCELLED, observed_at=101.0)
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_write_stop_projection",
                      lambda *args: (_ for _ in ()).throw(OSError("prune interrupted")))
        with pytest.raises(WorkerOperationError, match="prune interrupted"):
            ledger.publish_receipt(receipt)
    assert ledger.inspect_receipt(CLIENT_ID, first.operation_id) == receipt
    assert current(ledger)[0] == (first, second)  # Conservative until cold recovery.
    ledger.initialize_stop_authority(CLIENT_ID)
    assert current(ledger)[0] == (second,)


def test_failed_terminal_receipt_never_clears_stop(ledger, monkeypatch):
    import shadowbane_lab.manager.operation as module

    stop = operation()
    ledger.submit(stop)
    original = module.publish_atomic_record

    def interrupted(path, *args, **kwargs):
        if path.suffix == ".receipt":
            raise OSError("receipt interrupted")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(module, "publish_atomic_record", interrupted)
    with pytest.raises(WorkerOperationError, match="could not persist receipt"):
        ledger.publish_receipt(WorkerOperationReceipt.for_operation(
            stop, WorkerOperationState.CANCELLED, observed_at=101.0))
    assert current(ledger)[0] == (stop,)
    assert ledger.inspect_receipt(CLIENT_ID, stop.operation_id) is None


@pytest.mark.parametrize("damage", [
    "missing", "truncated", "wrong_node", "duplicate", "wrong_kind", "bool_schema",
])
def test_missing_or_malformed_projection_denies_hot_reader(ledger, damage):
    ledger.submit(operation())
    path = projection_path(ledger)
    value = json.loads(path.read_text())
    if damage == "missing":
        path.unlink()
    elif damage == "truncated":
        path.write_text("{")
    else:
        if damage == "wrong_node":
            value["node_id"] = "another-node"
        elif damage == "duplicate":
            value["pending"].append(value["pending"][0])
        elif damage == "bool_schema":
            value["schema_version"] = True
        else:
            value["pending"][0]["operation"]["kind"] = "pve"
        path.write_text(json.dumps(value))
    with pytest.raises(WorkerOperationError):
        current(ledger)


def test_projection_change_during_control_read_denies_mixed_snapshot(ledger, monkeypatch):
    original = ledger._preparation_control_unlocked
    revisions = iter(("a" * 32, "b" * 32, "c" * 32))

    def changed(directory, instance):
        result = original(directory, instance)
        value = json.loads(projection_path(ledger).read_text())
        value["revision"] = next(revisions)
        projection_path(ledger).write_text(json.dumps(value))
        return result

    monkeypatch.setattr(ledger, "_preparation_control_unlocked", changed)
    with pytest.raises(WorkerOperationError, match="changed during read"):
        current(ledger)


def test_stop_committed_after_pending_query_survives_claim_and_initial_read(ledger):
    work = operation(1, WorkerOperationKind.PVE)
    ledger.submit(work)
    assert ledger.pending_for(
        client_id=CLIENT_ID, instance_id=INSTANCE_ID, worker_id=WORKER_ID,
        worker_process_id=WORKER_PROCESS_ID,
        worker_process_started_at_100ns=WORKER_PROCESS_STARTED, now=101.0) == (work,)
    stop = operation(2)
    ledger.submit(stop)
    assert ledger.claim_for_execution(work, now=101.0)
    assert current(ledger)[0] == (stop,)


def test_pending_stop_filters_exact_target_and_original_expiry(ledger):
    stop = operation()
    ledger.submit(stop)
    assert current(ledger, worker_process_started_at_100ns=WORKER_PROCESS_STARTED + 1)[0] == ()
    assert current(ledger, worker_id="worker-" + "f" * 32)[0] == ()
    assert current(ledger, instance_id="another-instance")[0] == ()
    assert current(ledger, now=stop.expires_at)[0] == ()
    assert current(ledger, now=stop.expires_at - .001)[0] == (stop,)


def test_no_op_recovery_and_ordinary_mutation_preserve_projection_revision(ledger):
    before = projection_path(ledger).read_bytes()
    ledger.initialize_stop_authority(CLIENT_ID)
    assert projection_path(ledger).read_bytes() == before
    ledger.submit(operation(1, WorkerOperationKind.PVE))
    assert projection_path(ledger).read_bytes() == before


def test_single_concurrent_stop_publication_yields_fresh_consistent_snapshot(ledger, monkeypatch):
    original = ledger._preparation_control_unlocked
    stop = operation()
    published = False

    def changed(directory, instance):
        nonlocal published
        control = original(directory, instance)
        if not published:
            published = True
            ledger.submit(stop)
        return control

    monkeypatch.setattr(ledger, "_preparation_control_unlocked", changed)
    pending, control, unresolved = current(ledger)
    assert pending == (stop,) and not control.enabled and not unresolved

@pytest.mark.parametrize("interruption", ["preparation", "terminal_projection"])
def test_terminal_history_pruning_cannot_resurrect_write_ahead_stop(
    ledger, monkeypatch, interruption,
):
    stop = operation()
    if interruption == "preparation":
        with monkeypatch.context() as patch:
            patch.setattr(ledger, "_latch_preparation_stop_unlocked",
                          lambda *args: (_ for _ in ()).throw(OSError("latch interrupted")))
            with pytest.raises(WorkerOperationError):
                ledger.submit(stop)
    else:
        ledger.submit(stop)
    receipt = WorkerOperationReceipt.for_operation(
        stop, WorkerOperationState.EXPIRED, observed_at=111.0)
    if interruption == "terminal_projection":
        with monkeypatch.context() as patch:
            patch.setattr(ledger, "_write_stop_projection",
                          lambda *args: (_ for _ in ()).throw(OSError("projection interrupted")))
            with pytest.raises(WorkerOperationError):
                ledger.publish_receipt(receipt)
    else:
        ledger.publish_receipt(receipt)
    assert ledger.inspect_receipt(CLIENT_ID, stop.operation_id) == receipt
    assert ledger.prune_terminal(CLIENT_ID, now=1_000_000_000.0) == 1
    ledger.initialize_stop_authority(CLIENT_ID)
    assert ledger.inspect_slot(CLIENT_ID) == ()
    assert json.loads(projection_path(ledger).read_text())["pending"] == []
