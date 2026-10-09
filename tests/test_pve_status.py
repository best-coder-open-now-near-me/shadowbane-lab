import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_manager_operation import _manifest, _permit

from shadowbane_lab.client_extension.actor_publication import AdmissionBlock
from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationLedgerError,
    WorkerOperationReceipt,
    WorkerOperationSnapshot,
    WorkerOperationState,
    new_worker_operation,
)
from shadowbane_lab.manager.pve_status import (
    PvEProgressPublisher,
    WorkerPvEProgress,
    project_status,
)
from shadowbane_lab.manager.worker import (
    WorkerHealthState,
    WorkerHeartbeat,
    WorkerRuntimeState,
    WorkerSlotHealthSnapshot,
)
from shadowbane_lab.pve.preparation import (
    ActorIdentity,
    Coverage,
    CoverageEvidence,
    GroupStatus,
    PowerOperand,
    PreparationAction,
    PreparationDecision,
    PreparationGroup,
    PreparationObservation,
    Readiness,
    ReadinessEvidence,
)
from shadowbane_lab.pve.preparation_status import PreparationStatus, PvEProgress, capture_status

ACTOR = ActorIdentity(101, 1001, 1, (123, 53), "actor-exact")
GROUPS = (PreparationGroup("precision", (PreparationAction("precision", power_id=429545819),)),)


def observation(coverage=Coverage.PRESENT, *, complete=True):
    return PreparationObservation(
        ACTOR,
        17,
        complete,
        (CoverageEvidence("precision", coverage),),
        (ReadinessEvidence("precision", Readiness.READY, PowerOperand(429545819)),),
        5,
        0,
        capture_sequence=8,
    )


def progress(*, captured=100.0, observed=100.0, coverage=Coverage.PRESENT, local=False):
    return PvEProgress(
        observed,
        "engaging",
        "engaging",
        0,
        capture_status(
            GROUPS, observation(coverage), None, captured_at=captured, local_pending=local
        ),
    )


def operation():
    return new_worker_operation(_permit(), WorkerOperationKind.PVE, "/pve", now=100.0)


def health(op):
    heartbeat = WorkerHeartbeat(
        op.node_id,
        op.client_id,
        op.instance_id,
        op.worker_id,
        op.worker_process_id,
        op.worker_process_started_at_100ns,
        1,
        100,
        WorkerRuntimeState.RUNNING,
        True,
        False,
    )
    return WorkerSlotHealthSnapshot(op.client_id, WorkerHealthState.HEALTHY, True, 1, heartbeat)


def snapshot(op, state=WorkerOperationState.ACTIVE):
    return WorkerOperationSnapshot(
        op, WorkerOperationReceipt.for_operation(op, state, observed_at=100.0)
    )


def test_projection_never_infers_coverage_from_queue_or_local_completion():
    decision = PreparationDecision(
        None, False, (GroupStatus("precision", Coverage.MISSING, True),), "application_pending"
    )
    status = capture_status(
        GROUPS, observation(Coverage.MISSING), decision, captured_at=100, local_pending=False
    )
    assert status.groups[0].coverage is Coverage.MISSING
    assert status.groups[0].application_pending
    assert not status.local_pending
    assert PreparationStatus.from_dict(status.to_dict()) == status
    assert PvEProgress.from_dict(progress().to_dict()) == progress()


def test_incomplete_and_failed_capture_do_not_retain_known_coverage():
    status = capture_status(
        GROUPS, observation(complete=False), None, captured_at=100, local_pending=True
    )
    assert status.groups[0].coverage is Coverage.UNKNOWN
    assert status.groups[0].actions[0].readiness is Readiness.UNKNOWN
    assert status.local_pending and not status.complete
    lost = capture_status(GROUPS, None, None, captured_at=None, local_pending=True)
    assert lost.actor is None and lost.capture_sequence is None and lost.local_pending
    with pytest.raises(ValueError):
        replace(status, groups=progress().preparation.groups)


@pytest.mark.parametrize(
    "field,value",
    [
        ("capture_sequence", 3),
        ("capture_sequence", True),
        ("publication_revision", 0),
        ("admission_blocks", 64),
        ("captured_at", float("nan")),
    ],
)
def test_malformed_native_status_is_rejected(field, value):
    with pytest.raises(ValueError):
        replace(progress().preparation, **{field: value})


def test_ledger_exact_operation_roundtrip_terminal_and_replaced_writer_refused(tmp_path):
    op = operation()
    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100)
    ledger.submit(op)
    with pytest.raises(WorkerOperationLedgerError):
        ledger.publish_pve_progress(WorkerPvEProgress(op, progress()))
    ledger.claim_for_execution(op, now=100)
    record = WorkerPvEProgress(op, progress())
    ledger.publish_pve_progress(record)
    assert ledger.inspect_pve_progress(op.client_id) == record
    with pytest.raises(WorkerOperationLedgerError):
        ledger.publish_pve_progress(replace(record, operation=replace(op, command="/other")))
    ledger.publish_receipt(
        WorkerOperationReceipt.for_operation(
            op, WorkerOperationState.FAILED, observed_at=101, detail="cleanup unconfirmed"
        )
    )
    with pytest.raises(WorkerOperationLedgerError):
        ledger.publish_pve_progress(record)
    assert len(list(tmp_path.rglob("pve-progress.json"))) == 1
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize(
    "case,expected",
    [
        ("fresh", "current"),
        ("capture_stale", "stale"),
        ("writer_stale", "stale"),
        ("future", "stale"),
        ("ended", "ended"),
        ("worker_lost", "worker_unavailable"),
        ("replaced", "worker_unavailable"),
        ("instance_lost", "worker_unavailable"),
        ("unknown", "unknown"),
        ("disabled", "disabled"),
    ],
)
def test_status_freshness_worker_and_terminal_truth(case, expected):
    op = operation()
    sample, worker, snap, now, instance = progress(), health(op), snapshot(op), 101, op.instance_id
    if case == "capture_stale":
        sample = progress(captured=90)
    if case == "writer_stale":
        now = 110
    if case == "future":
        now = 99
    if case == "ended":
        snap = snapshot(op, WorkerOperationState.FAILED)
    if case == "worker_lost":
        worker = replace(worker, state=WorkerHealthState.MISSING)
    if case == "replaced":
        worker = replace(
            worker,
            heartbeat=replace(
                worker.heartbeat,
                process_started_at_100ns=worker.heartbeat.process_started_at_100ns + 1,
            ),
        )
    if case == "instance_lost":
        instance = None
    if case == "unknown":
        sample = replace(
            sample,
            preparation=capture_status(GROUPS, None, None, captured_at=None, local_pending=False),
        )
    if case == "disabled":
        sample = replace(sample, preparation=PreparationStatus.disabled())
    result = project_status(WorkerPvEProgress(op, sample), snap, worker, instance, now=now)
    assert result["state"] == expected
    assert result["current"] is (expected == "current")
    assert result["progress"] == sample.to_dict()  # Historical evidence retained, labelled.


def test_other_operation_cannot_borrow_current_status():
    op, other = operation(), operation()
    assert (
        project_status(
            WorkerPvEProgress(op, progress()),
            snapshot(other),
            health(other),
            other.instance_id,
            now=100,
        )["progress"]
        is None
    )


def test_publisher_coalesces_without_disk_on_gameplay_thread_and_checks_actor():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def write(record):
        calls.append((threading.get_ident(), record))
        entered.set()
        release.wait(2)

    publisher = PvEProgressPublisher(
        SimpleNamespace(publish_pve_progress=write),
        operation(),
        process_id=101,
        process_creation=1001,
        interval=0.05,
    )
    try:
        publisher(progress())
        assert entered.wait(1)
        for n in range(20):
            publisher(replace(progress(), kills=n))
        assert len(calls) == 1  # Slow filesystem cannot block or queue every frame.
        assert calls[0][0] != threading.get_ident()
        foreign = replace(progress().preparation, actor=replace(ACTOR, process_creation=1002))
        with pytest.raises(ValueError, match="binding"):
            publisher(replace(progress(), preparation=foreign))
        release.set()
    finally:
        release.set()
        publisher.close()
    assert len(calls) <= 2 and calls[-1][1].progress.kills == 19


def test_dashboard_joins_real_ledger_and_hides_ended_operation_as_current(tmp_path, monkeypatch):
    from test_manager_application import _application, _client, _RecordingSession, _slot

    from shadowbane_lab.manager.session import ManagerSessionSnapshot

    op = operation()
    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100)
    ledger.submit(op)
    ledger.claim_for_execution(op, now=100)
    ledger.publish_pve_progress(WorkerPvEProgress(op, progress()))
    session = _RecordingSession(
        ManagerSessionSnapshot(op.node_id, (_slot(op.client_id, instance_id=op.instance_id),))
    )
    app, registry = _application(session, _client(op.instance_id, 101), operation_status=ledger)
    monkeypatch.setattr(registry.worker_supervisor, "inspect", lambda *a, **k: health(op))
    monkeypatch.setattr("shadowbane_lab.manager.pve_status.time.time", lambda: 101)
    value = app.status()["slots"][0]["pve"]
    assert (
        value["state"] == "current"
        and value["progress"]["preparation"]["groups"][0]["coverage"] == "present"
    )
    ledger.publish_receipt(
        WorkerOperationReceipt.for_operation(op, WorkerOperationState.FAILED, observed_at=102)
    )
    assert app.status()["slots"][0]["pve"]["state"] == "ended"


def test_current_pending_projection_replaces_stale_decision_without_clearing_native_history():
    old = PreparationDecision(
        None, False, (GroupStatus("precision", Coverage.PRESENT, True),), "old_pending"
    )
    now = capture_status(
        GROUPS,
        observation(),
        old,
        captured_at=100,
        local_pending=False,
        application_pending_groups=frozenset(),
    )
    assert not now.groups[0].application_pending
    native = replace(observation(), pending_applications=frozenset({"precision"}))
    now = capture_status(
        GROUPS,
        native,
        old,
        captured_at=100,
        local_pending=False,
        application_pending_groups=frozenset(),
    )
    assert now.groups[0].application_pending


def test_abandoned_active_operation_cannot_overwrite_replacement_progress(tmp_path):
    from dataclasses import replace

    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100)
    old = operation()
    ledger.submit(old)
    ledger.claim_for_execution(old, now=100)
    ledger.publish_pve_progress(WorkerPvEProgress(old, progress()))
    new = new_worker_operation(
        replace(_permit(), process_started_at_100ns=9002), WorkerOperationKind.PVE, "/pve", now=101
    )
    ledger.submit(new)
    ledger.claim_for_execution(new, now=101)
    record = WorkerPvEProgress(new, progress(observed=101))
    ledger.publish_pve_progress(record)
    with pytest.raises(WorkerOperationLedgerError, match="superseded"):
        ledger.publish_pve_progress(WorkerPvEProgress(old, progress(observed=102)))
    assert ledger.inspect_pve_progress(new.client_id) == record


@pytest.mark.parametrize(
    "raw",
    ["{}", '{"schema_version":1,"schema_version":1}', "x" * 65537],
    ids=["missing", "duplicate", "oversize"],
)
def test_malformed_status_never_breaks_dashboard_or_becomes_current(tmp_path, raw):
    op = operation()
    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100)
    ledger.submit(op)
    path = tmp_path / op.node_id / op.client_id / "operations" / "pve-progress.json"
    path.write_text(raw, encoding="utf-8")
    from shadowbane_lab.manager.application import ManagerDashboardApplication

    app = object.__new__(ManagerDashboardApplication)
    app._operation_status = ledger
    assert app._pve_summary(op.client_id, {}, health(op), op.instance_id) == {
        "state": "unavailable",
        "current": False,
        "progress": None,
    }


def test_dashboard_renderer_uses_text_only_and_labels_historical_or_unknown_states():
    import json
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the dashboard renderer")
    html = (
        Path(__file__).parents[1] / "src/shadowbane_lab/manager/static/dashboard.html"
    ).read_text(encoding="utf-8")
    script = html.split('<script nonce="__CSP_NONCE__">', 1)[1].split("</script>", 1)[0]
    subprocess.run([node, "--check"], input=script, text=True, check=True, capture_output=True)
    renderer = script[script.index("function renderPveStatus") : script.index("const text =")]
    values = []
    for state in ("current", "stale", "ended", "unknown", "worker_unavailable", "disabled"):
        sample = progress()
        if state == "disabled":
            sample = replace(sample, preparation=PreparationStatus.disabled())
        if state == "unknown":
            sample = replace(
                sample,
                preparation=capture_status(
                    GROUPS, None, None, captured_at=None, local_pending=False
                ),
            )
        values.append(
            dict(
                state=state,
                current=state == "current",
                age_seconds=4,
                operation_state="active",
                progress=sample.to_dict(),
            )
        )
    code = (
        """
const assert = require('assert');
const text = value => String(value ?? '-');
function element() { return {children: [], textContent: '',
  append(...xs) { this.children.push(...xs); },
  set innerHTML(_) { throw Error('untrusted status must use textContent'); }}; }
const document = {createElement: element};
function flatten(e) { return [e.textContent, ...e.children.flatMap(flatten)].join(' '); }
"""
        + renderer
        + "\nconst values = "
        + json.dumps(values)
        + ";"
        + """
for (const value of values) {
  const root = element(); renderPveStatus(root, value); const visible = flatten(root);
  assert(visible.includes(value.state));
  if (value.current) assert(visible.includes('precision · present'));
  else if (value.state === 'disabled') assert(visible.includes('Automatic buffs disabled'));
  else assert(visible.includes('current buff state is unavailable'));
  if (['stale','ended','worker_unavailable'].includes(value.state))
    assert(visible.includes('last present'));
}
const root = element(); renderPveStatus(root, {state: 'unavailable', progress: null});
assert.equal(root.children.length, 0);
renderPveStatus(root, {state: 'unavailable', operation_id: 'operation-1', progress: null});
assert(flatten(root).includes('status unavailable'));
assert(!flatten(root).includes('disabled'));
"""
    )
    subprocess.run([node], input=code, text=True, encoding="utf-8", check=True, capture_output=True)


def test_active_pve_without_snapshot_shows_unavailable_but_non_pve_has_no_card():
    from shadowbane_lab.manager.application import ManagerDashboardApplication

    app = object.__new__(ManagerDashboardApplication)
    app._operation_status = None
    op = operation()
    selected = snapshot(op).to_dict()
    value = app._pve_summary(op.client_id, {"active": selected}, health(op), op.instance_id)
    assert value["state"] == "unavailable" and value["progress"] is None
    assert value["operation_id"] == op.operation_id
    selected["operation"]["kind"] = "travel"
    value = app._pve_summary(op.client_id, {"active": selected}, health(op), op.instance_id)
    assert "operation_id" not in value


def test_all_native_admission_bits_survive_policy_and_status_projection():
    supported = sum(int(flag) for flag in AdmissionBlock)
    for blocks in [*(int(flag) for flag in AdmissionBlock), supported]:
        observed = replace(observation(), admission_blocks=blocks)
        status = capture_status(GROUPS, observed, None, captured_at=100, local_pending=False)
        assert status.admission_blocks == blocks
        assert PreparationStatus.from_dict(status.to_dict()) == status
    unknown = 1 << supported.bit_length()
    with pytest.raises(ValueError):
        replace(observation(), admission_blocks=unknown)
    with pytest.raises(ValueError):
        replace(progress().preparation, admission_blocks=unknown)

def tracking_status(*, count=1, age=2):
    from shadowbane_lab.pve.tracking import TrackingActor, TrackingContact, TrackingStatus
    return TrackingStatus(
        enabled=True, state='current', current=True, generation=3,
        observed_at=100, response_age_seconds=age,
        contacts=tuple(TrackingContact((i + 1, 53), 'Player ' + str(i), 0) for i in range(count)),
        actor=TrackingActor(101, 1001, 1, (123, 53)),
    )


def test_tracking_remains_current_with_buffs_disabled_and_expires_independently():
    op = operation()
    sample = replace(
        progress(), preparation=PreparationStatus.disabled(), tracking=tracking_status())
    result = project_status(WorkerPvEProgress(op, sample), snapshot(op), health(op), op.instance_id,
                            now=101)
    assert not result['current']  # Existing buff projection is disabled.
    assert result['tracking']['current']
    assert result['tracking']['response_age_seconds'] == 3
    old = replace(sample, tracking=tracking_status(age=20))
    result = project_status(WorkerPvEProgress(op, old), snapshot(op), health(op), op.instance_id,
                            now=101)
    assert result['tracking']['state'] == 'stale'
    assert result['tracking']['contacts'][0]['name'] == 'Player 0'


@pytest.mark.parametrize('case', ['stopped', 'replaced', 'stale'])
def test_tracking_cannot_outlive_its_exact_active_worker(case):
    op = operation()
    snap, worker, now = snapshot(op), health(op), 101
    if case == 'stopped':
        snap = snapshot(op, WorkerOperationState.CANCELLED)
    elif case == 'replaced':
        worker = replace(worker, state=WorkerHealthState.MISSING)
    else:
        now = 110
    result = project_status(WorkerPvEProgress(op, replace(progress(), tracking=tracking_status())),
                            snap, worker, op.instance_id, now=now)
    assert not result['tracking']['current']
    assert result['tracking']['contacts']


def test_full_unicode_tracking_list_roundtrips_in_status_ledger(tmp_path):
    from shadowbane_lab.pve.tracking import TrackingContact
    op = operation()
    ledger = WorkerOperationLedger(_manifest(), tmp_path, clock=lambda: 100)
    ledger.submit(op)
    ledger.claim_for_execution(op, now=100)
    contacts = tuple(TrackingContact((i + 1, 53), '\u732b' * 96, 0) for i in range(256))
    tracking = replace(tracking_status(), contacts=contacts)
    record = WorkerPvEProgress(op, replace(progress(), tracking=tracking))
    ledger.publish_pve_progress(record)
    assert ledger.inspect_pve_progress(op.client_id) == record
