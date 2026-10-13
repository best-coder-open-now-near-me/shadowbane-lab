import importlib
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_extension.action_channel import (
    NativeActionChannelUnavailable,
    NativeClientProcessIdentity,
)
from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_navigation_wire import (
    IN_FLIGHT,
    READY,
    UNRESOLVED,
    Host,
    Outcome,
    Receipt,
)
from shadowbane_lab.manager.operation import WorkerOperationKind, WorkerOperationState
from shadowbane_lab.manager.vendor_control import VendorWorkerExecutor
from shadowbane_lab.manager.vendor_job import VendorJobStore
from shadowbane_lab.manager.vendor_navigation import require_failed_discovery_idle
from tests.test_vendor_navigation import KEY, OPENED, STATE

FAMILIES = [
    ("vendor_navigation", "NativeVendorNavigationSession", "inspect", ()),
    ("vendor_menu", "NativeVendorMenuSession", "inspect", ()),
    ("guard_funding", "NativeGuardFundingSession", "inspect", (1,)),
    ("city_window", "NativeCityWindowSession", "inspect", ()),
    ("vendor", "NativeVendorSession", "inspect", ()),
    ("vendor", "NativeVendorSession", "inspect_random", ()),
]


@pytest.mark.parametrize("module,cls,method,args,stale,flags,count", [
    (*family, stale, flags, count)
    for family in FAMILIES
    for stale, flags, count in [(2, 0, 3), (3, 0, 3), (3, UNRESOLVED, 1)]
    if family[0] != "city_window" or flags == 0
])
def test_typed_stale_inspection_is_bounded_and_never_retries_unresolved(
    module, cls, method, args, stale, flags, count
):
    mod = importlib.import_module("shadowbane_lab.client_extension." + module + "_session")
    session = getattr(mod, cls).__new__(getattr(mod, cls))
    session._submit = Mock(side_effect=[
        SimpleNamespace(outcome=Outcome.STALE, flags=flags)
        for _ in range(stale)
    ] + [SimpleNamespace(outcome=Outcome.OBSERVED, flags=0)])
    with patch.object(mod.time, "sleep"):
        result = getattr(session, method)(*args)
    calls = session._submit.call_args_list
    assert len(calls) == count
    assert len({call.args[1] for call in calls}) == count
    assert all(call.args[0].name in {"INSPECT", "INSPECT_RANDOM"} for call in calls)
    assert result.outcome == (Outcome.OBSERVED if stale == 2 else Outcome.STALE)


@pytest.mark.parametrize("module,cls,method,args", FAMILIES)
def test_lost_producer_is_never_retried(module, cls, method, args):
    mod = importlib.import_module("shadowbane_lab.client_extension." + module + "_session")
    session = getattr(mod, cls).__new__(getattr(mod, cls))
    session._submit = Mock(side_effect=NativeActionChannelUnavailable("producer changed"))
    with pytest.raises(NativeActionChannelUnavailable):
        getattr(session, method)(*args)
    assert session._submit.call_count == 1


@pytest.fixture
def failed_scan(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    binding = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=1234567,
                              game_window_handle=1000, client_id="client",
                              instance_id="instance", worker_id="worker")
    operation = SimpleNamespace(operation_id="operation-123", kind=WorkerOperationKind.VENDOR,
                                command="vendor discover", client_id="client",
                                instance_id="instance", worker_id="worker", node_id="node")
    record = dict(schema_version=1, identity=list(store.identity),
                  operation_id=operation.operation_id, game_process_id=988,
                  game_creation_filetime=1234567, state="review", scene=1, root=100,
                  attempts=[dict(request_key=KEY, building_id=123, vendor_id=0,
                                 expected=STATE.encode().hex(), outcome="SUBMITTED",
                                 state="observed")])
    session = Mock(identity=NativeClientProcessIdentity(988, 1234567))
    session.inspect.return_value = Receipt(KEY, Host(1, 1, 1), 1000, Outcome.OBSERVED,
                                            READY, OPENED, KEY)
    path = store.root / "navigation" / (operation.operation_id + ".json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record))
    return store, binding, operation, session, path, record


def test_failed_scan_handback_preserves_original_failure_evidence(failed_scan):
    store, binding, operation, session, path, _ = failed_scan
    original = path.read_bytes()
    require_failed_discovery_idle(store, binding, operation, session)
    assert path.read_bytes() == original
    session.inspect.assert_called_once_with()


@pytest.mark.parametrize("change", [
    {"identity": ["other", "client", "instance"]}, {"operation_id": "operation-other"},
    {"game_process_id": 989}, {"game_creation_filetime": 1234568}, {"state": "opening"},
    {"scene": 2}, {"root": 101}, {"attempts": []},
])
def test_failed_scan_handback_rejects_wrong_owner_before_native_read(failed_scan, change):
    store, binding, operation, session, path, record = failed_scan
    record.update(change)
    path.write_text(json.dumps(record))
    with pytest.raises(VendorBatchStopped):
        require_failed_discovery_idle(store, binding, operation, session)
    session.inspect.assert_not_called()


@pytest.mark.parametrize("change", [
    {"state": "prepared"}, {"state": "submitted"}, {"state": "not_submitted"},
    {"outcome": "STALE"}, {"building_id": 0}, {"vendor_id": -1},
])
def test_failed_scan_handback_rejects_unconfirmed_transition(failed_scan, change):
    store, binding, operation, session, path, record = failed_scan
    record["attempts"][0].update(change)
    path.write_text(json.dumps(record))
    with pytest.raises(VendorBatchStopped):
        require_failed_discovery_idle(store, binding, operation, session)
    session.inspect.assert_not_called()


@pytest.mark.parametrize("change", [
    {"outcome": Outcome.STALE}, {"flags": IN_FLIGHT}, {"flags": UNRESOLVED},
    {"transition_request": None}, {"window": 1001},
    {"snapshot": replace(OPENED, scene=2)},
    {"snapshot": replace(OPENED, manager=201)},
    {"snapshot": replace(OPENED, building_id=124)},
])
def test_failed_scan_handback_requires_fresh_exact_idle_receipt(failed_scan, change):
    store, binding, operation, session, _, _ = failed_scan
    session.inspect.return_value = replace(session.inspect.return_value, **change)
    with pytest.raises(VendorBatchStopped):
        require_failed_discovery_idle(store, binding, operation, session)


def test_failed_scan_handback_rejects_duplicate_intent(failed_scan):
    store, binding, operation, session, path, record = failed_scan
    record["attempts"] *= 2
    path.write_text(json.dumps(record))
    with pytest.raises(VendorBatchStopped):
        require_failed_discovery_idle(store, binding, operation, session)
    session.inspect.assert_not_called()


def test_failed_scan_handback_cannot_release_an_uncertain_spending_job(failed_scan):
    store, binding, operation, session, _, _ = failed_scan
    with patch.object(store, "current", return_value={"state": "review"}):
        with pytest.raises(VendorBatchStopped):
            require_failed_discovery_idle(store, binding, operation, session)
    session.inspect.assert_not_called()


def test_executor_reports_failure_with_confirmed_cleanup_after_exact_proof(failed_scan):
    from shadowbane_lab.client_extension.city_window_wire import Receipt as CityReceipt
    from shadowbane_lab.client_extension.city_window_wire import Snapshot as CitySnapshot

    store, binding, operation, session, path, _ = failed_scan
    original = path.read_bytes()
    city = Mock(identity=session.identity)
    city.inspect.return_value = CityReceipt(KEY, Host(1, 1, 1), 1000, Outcome.OBSERVED,
                                             0, CitySnapshot())
    executor = VendorWorkerExecutor(
        store.root.parents[4], "node", binding,
        city_session_factory=lambda _: city, navigation_session_factory=lambda _: session,
    )
    with (
        patch("shadowbane_lab.manager.vendor_control.VendorJobStore", return_value=store),
        patch("shadowbane_lab.manager.vendor_control.run_discovery", return_value={}),
        patch("shadowbane_lab.manager.vendor_control.run_building_discovery",
              side_effect=VendorBatchStopped("read-only observation rejected")),
    ):
        result = executor.execute(operation, stop_signal=Mock(is_set=lambda: False))
    assert result.state == WorkerOperationState.FAILED
    assert result.detail == "read-only observation rejected"
    assert result.native_cleanup_confirmed
    assert path.read_bytes() == original
    session.close.assert_called_once_with()
