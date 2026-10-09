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


def test_idle_tracking_projects_without_buff_coverage_and_preserves_legacy_records(tmp_path):
    from test_pve_status import tracking_status
    value = record()
    legacy = value.to_dict()
    legacy.pop('tracking')
    assert WorkerPreparationStatus.parse(legacy).service.tracking.enabled is False
    value = replace(value, service=replace(value.service, state='maintaining',
                                           tracking=tracking_status(count=256)))
    ledger = WorkerOperationLedger(_manifest(), tmp_path)
    ledger.publish_preparation_status(value)
    assert ledger.inspect_preparation_status(CLIENT_ID) == value
    worker = SimpleNamespace(state=WorkerHealthState.HEALTHY, heartbeat=value.heartbeat)
    binding = SimpleNamespace(instance_id=INSTANCE_ID, process_id=101,
                              process_started_at_100ns=1001)
    view = project_status(value, worker, binding, now=101.)
    assert not view['current']
    assert view['tracking']['current'] and len(view['tracking']['contacts']) == 256
    paused = replace(value, service=replace(value.service, state='paused'))
    assert project_status(paused, worker, binding, now=101.)['tracking']['state'] == 'paused'
    foreign = replace(value, service=replace(value.service,
        tracking=replace(value.service.tracking,
                         actor=replace(value.service.tracking.actor, process_id=102))))
    assert project_status(foreign, worker, binding, now=101.)['state'] == 'unavailable'


def test_tracking_panel_distinguishes_empty_from_unavailable_and_escapes_names():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required to execute the dashboard renderer')
    html = Path('src/shadowbane_lab/manager/static/dashboard.html').read_text(encoding='utf-8')
    renderer = html[html.index('function renderTrackingStatus'):html.index('const text =')]
    code = '''
const assert = require('assert');
const text = x => String(x);
const element = () => ({textContent:'', children:[], append(x) {this.children.push(x)},
  set innerHTML(_) {throw Error('unsafe name rendering')}});
const document = {createElement: element};
const flatten = x => [x.textContent, ...x.children.map(flatten)].join(' ');
''' + renderer + '''
const root=element();
renderTrackingStatus(root,{enabled:true,current:true,state:'current',contacts:[]});
assert(flatten(root).includes('No players in the latest Hunt Foe result'));
const missing=element();
renderTrackingStatus(missing,{enabled:true,current:false,state:'unavailable',contacts:[]});
assert(!flatten(missing).includes('No players'));
const old=element();
renderTrackingStatus(old,{enabled:true,current:false,state:'stale',
 contacts:[{name:'<img src=x onerror=alert(1)>'}],response_age_seconds:30});
assert(flatten(old).includes('Last seen: <img src=x onerror=alert(1)>'));
assert(flatten(old).includes('30.0s ago'));
'''
    subprocess.run([node, '-e', code], check=True, capture_output=True, text=True)
