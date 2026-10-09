from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_manager_operation import (
    CLIENT_ID,
    INSTANCE_ID,
    NODE_ID,
    WORKER_ID,
    WORKER_PROCESS_ID,
    WORKER_PROCESS_STARTED,
    _manifest,
)

from shadowbane_lab.manager.operation import WorkerOperationLedger, WorkerOperationLedgerError
from shadowbane_lab.manager.preparation_service import PreparationServiceSnapshot
from shadowbane_lab.manager.preparation_status import WorkerPreparationStatus, project_status
from shadowbane_lab.manager.worker import WorkerHealthState, WorkerHeartbeat, WorkerRuntimeState
from shadowbane_lab.pve.preparation_status import PreparationStatus


def record():
    heartbeat = WorkerHeartbeat(NODE_ID, CLIENT_ID, INSTANCE_ID, WORKER_ID,
        WORKER_PROCESS_ID, WORKER_PROCESS_STARTED, 2, 100., WorkerRuntimeState.RUNNING,
        True, False)
    return WorkerPreparationStatus(heartbeat, PreparationServiceSnapshot(
        "paused", 4, PreparationStatus.disabled()))


def test_status_roundtrip_without_operation_or_native_read(tmp_path):
    ledger = WorkerOperationLedger(_manifest(), tmp_path)
    value = record()
    ledger.publish_preparation_status(value)
    assert ledger.inspect_preparation_status(CLIENT_ID) == value
    assert ledger.inspect_slot(CLIENT_ID) == ()
    with pytest.raises(WorkerOperationLedgerError, match="superseded"):
        ledger.publish_preparation_status(value)


def test_old_worker_status_cannot_be_current_after_replacement():
    value = record()
    worker = SimpleNamespace(state=WorkerHealthState.HEALTHY,
        heartbeat=replace(value.heartbeat, process_started_at_100ns=WORKER_PROCESS_STARTED+1))
    binding = SimpleNamespace(instance_id=INSTANCE_ID)
    assert project_status(value, worker, binding, now=100.)["state"] == "unavailable"


def test_paused_intent_is_visible_but_does_not_invent_native_capture():
    value = record()
    worker = SimpleNamespace(state=WorkerHealthState.HEALTHY, heartbeat=value.heartbeat)
    binding = SimpleNamespace(instance_id=INSTANCE_ID)
    actual = project_status(value, worker, binding, now=101.)
    assert actual["state"] == "paused" and actual["control_revision"] == 4
    assert actual["current"] is False
    assert project_status(value, worker, binding, now=104.)["state"] == "unavailable"



def test_fresh_heartbeat_cannot_refresh_old_present_coverage():
    from test_pve_status import ACTOR, progress
    value = record()
    value = replace(value, heartbeat=replace(value.heartbeat, observed_at=110.),
        service=replace(value.service, state="maintaining", preparation=progress().preparation))
    worker = SimpleNamespace(state=WorkerHealthState.HEALTHY, heartbeat=value.heartbeat)
    binding = SimpleNamespace(instance_id=INSTANCE_ID, process_id=ACTOR.process_id,
                              process_started_at_100ns=ACTOR.process_creation)
    actual = project_status(value, worker, binding, now=110.)
    assert actual["state"] == "maintaining" and actual["current"] is False
    assert actual["preparation"]["groups"][0]["coverage"] == "present"


def test_dashboard_does_not_present_stale_coverage_as_current():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the dashboard renderer")
    html = Path("src/shadowbane_lab/manager/static/dashboard.html").read_text(encoding="utf-8")
    script = html.split('<script nonce="__CSP_NONCE__">', 1)[1].split("</script>", 1)[0]
    subprocess.run([node, "--check"], input=script, text=True, capture_output=True, check=True)
    renderer = script[script.index("function renderAutomaticBuffs"):
                      script.index("function renderPveStatus")]
    code = r"""
const text = x => String(x);
const element = () => ({textContent:'', children:[], append(x) {this.children.push(x)}});
const document = {createElement: element};
const flatten = x => [x.textContent, ...x.children.map(flatten)].join(' ');
""" + renderer + r"""
const value = {state:'maintaining',current:false,
 preparation:{groups:[{group_id:'precision',coverage:'present'}]}};
const stale = element(); renderAutomaticBuffs(stale,value);
if(flatten(stale).includes('present') || !flatten(stale).includes('Current state unavailable'))
 throw Error('stale capture shown current');
const fresh=element();renderAutomaticBuffs(fresh,{...value,current:true});
if(!flatten(fresh).includes('present')) throw Error('fresh coverage lost');
"""
    subprocess.run([node], input=code, text=True, encoding="utf-8", capture_output=True, check=True)
