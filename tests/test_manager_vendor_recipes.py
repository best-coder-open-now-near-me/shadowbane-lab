"""Saved recipe workflow through actual durable menu, job and completion adapters."""
import json
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_extension.vendor_completion import validate_completed_batch
from shadowbane_lab.client_extension.vendor_menu import open_recipe_catalog, validate_completed_menu
from shadowbane_lab.client_extension.vendor_menu_wire import IN_FLIGHT, Outcome, Receipt
from shadowbane_lab.client_extension.vendor_recipe import RandomRecipeSpec
from shadowbane_lab.manager.dashboard import _RequestError, _validate_action_payload
from shadowbane_lab.manager.vendor_job import VendorJobStore, run_vendor_job
from shadowbane_lab.manager.vendor_recipes import (
    VendorRecipeStore,
    require_saved_owner,
    run_recipe_selection,
)
from tests.test_manager_vendor_job import JobMenus, JobSession
from tests.test_vendor_menu import Session as MenuSession

OWNER = dict(server="Test World", character="Test Player", key=[123, 53])
BINDING = SimpleNamespace(game_process_id=988, game_process_started_at_100ns=1234567,
                          game_window_handle=1000)


class Menus(JobMenus):
    def send(self, name, expected, key, template=0):
        records = [json.loads(path.read_text()) for path in self.parent.store.root.rglob("*.json")]
        matches = [r for r in records if r.get("requests")
                   and r["requests"][-1].get("request_key") == key]
        assert len(matches) == 1 and matches[0]["requests"][-1]["state"] == "prepared"
        assert expected == self.inspect().snapshot
        self.parent.menu_calls.append(name)
        if self.parent.menu_failure:
            raise TimeoutError("lost menu acknowledgement")
        changes = {"revision": self.parent.state.revision + 1}
        if name == "open_recipe":
            changes.update(recipe=400, inventory=0, multiple=0, quantity=1)
        elif name == "select_recipe":
            changes.update(item_template=template, table=self.parent.tables[template], mode=0)
        elif name == "random_mode":
            changes.update(mode=1, table=self.parent.tables[expected.item_template],
                           prefix=3362971591, suffix=3362971591)
        elif name == "close_recipe":
            changes.update(recipe=0)
        elif name == "close_inventory":
            changes.update(inventory=0)
        else:
            changes.update(inventory=900)
        self.parent.state = replace(self.parent.state, **changes)
        self.transition = key
        self.parent.after_menu(name)
        return Receipt(key, self.inspect().host, 1000, Outcome.SUBMITTED, IN_FLIGHT, expected)

    def open_recipe(self, expected, key):
        return self.send("open_recipe", expected, key)

    def select_recipe(self, expected, template, key):
        return self.send("select_recipe", expected, key, template)

    def random_mode(self, expected, key):
        return self.send("random_mode", expected, key)

    def close_inventory(self, expected, key):
        return self.send("close_inventory", expected, key)


class Session(JobSession):
    def __init__(self, store):
        super().__init__(store)
        self.tables = {26990: 12, 25860: 16}
        self.closed_count = 0

    def close(self):
        self.closed_count += 1

    def menu_session(self):
        return Menus(self)

    def inspect_random(self):
        return self.inspect()

    def create_random(self, expected, key):
        return self.create(expected, key)

    def reader(self, binding, *, catalog=False):
        s = self.menu_session().inspect().snapshot
        observation = dict(root_address=s.root, manager_address=s.manager, menu_address=s.menu,
                           recipe_address=s.recipe, list_address=s.recipe_list,
                           building=dict(object_id=s.building, object_type=8),
                           vendor=dict(object_id=s.vendor, object_type=42),
                           recipes=[dict(template=dict(object_id=t, object_type=0),
                                         display_name=label, selected=s.item_template == t,
                                         activated=s.item_template == t)
                                    for t, label in ((26990, "Scepter"), (25860, "Dagger"))])
        return dict(OWNER), observation if catalog else None

    def cook(self, seconds):
        self.state = replace(self.state, slots=tuple(replace(s, state=2) if s.item else s
                                                   for s in self.state.slots))


def setup(tmp_path):
    store = VendorJobStore(tmp_path, "node", "client", "instance")
    session = Session(store)
    return store, session, VendorRecipeStore(store)


def operation():
    return SimpleNamespace(operation_id="operation-" + uuid.uuid4().hex)


def save_recipe(store, session, template=25860):
    run_recipe_selection(store, BINDING, operation(), session, reader=session.reader)
    catalog = VendorRecipeStore(store).catalog()
    run_recipe_selection(store, BINDING, operation(), session, reader=session.reader,
                         catalog_id=catalog["catalog_id"], template=template)
    return VendorRecipeStore(store).current()


def admit(saved, session):
    return require_saved_owner(saved, BINDING, session, reader=session.reader)


@pytest.mark.parametrize("template", [25860, 26990])
def test_saved_selection_prepares_fills_opens_inventory_and_keeps_one_batch(tmp_path, template):
    store, session, recipes = setup(tmp_path)
    saved = save_recipe(store, session, template)
    assert saved["recipe_spec"] == RandomRecipeSpec(template, session.tables[template]).as_dict()
    session.state = replace(session.state, recipe=0, inventory=900)
    result = run_vendor_job(store, session, 1000, selection=admit(saved, session),
                            sleeper=session.cook)
    assert (result["state"], result["created"], result["kept"], result["excluded"]) == (
        "complete", 2, 2, 0)
    directory = store.directory(result["job_id"])
    batch, initial = validate_completed_batch((directory / "create.json").read_bytes())
    assert batch["schema_version"] == 3 and initial.item_template == template
    assert "close_inventory" in session.menu_calls and "open_recipe" in session.menu_calls
    assert "open_inventory" in session.menu_calls
    assert len(session.calls) == len(session.keeps) == 2
    assert recipes.current()["revision"] == saved["revision"]


def test_preferences_rebind_by_stable_owner_and_vendor_across_client_lifetimes(tmp_path):
    store, session, recipes = setup(tmp_path)
    saved = save_recipe(store, session)
    new = VendorRecipeStore(VendorJobStore(tmp_path, "node", "client", "new-instance"))
    assert new.current() is None
    assert new.activate(OWNER, saved["building"], saved["vendor"]) == saved
    assert new.activate(dict(OWNER, key=[999, 53]), saved["building"], saved["vendor"]) is None
    assert recipes.current() == saved


def test_catalog_save_rejects_stale_id_missing_recipe_and_replaced_owner(tmp_path):
    store, session, recipes = setup(tmp_path)
    run_recipe_selection(store, BINDING, operation(), session, reader=session.reader)
    catalog = recipes.catalog()
    for token, template, changed in (("f" * 32, 25860, False),
                                      (catalog["catalog_id"], 999, False),
                                      (catalog["catalog_id"], 25860, True)):
        if changed:
            session.state = replace(session.state, scene=2)
        with pytest.raises((ValueError, VendorBatchStopped)):
            run_recipe_selection(store, BINDING, operation(), session, reader=session.reader,
                                 catalog_id=token, template=template)
    assert recipes.current() is None and not session.calls


def test_changed_table_rejected_before_spending(tmp_path):
    store, session, _ = setup(tmp_path)
    saved = save_recipe(store, session)
    session.tables[25860] = 17
    session.state = replace(session.state, table=17)
    with pytest.raises(VendorBatchStopped, match="table"):
        run_vendor_job(store, session, 1000, selection=admit(saved, session), sleeper=session.cook)
    assert store.current()["state"] == "review" and not session.calls


def test_lost_preparation_receipt_stays_review_and_is_never_replayed(tmp_path):
    store, session, _ = setup(tmp_path)
    saved = save_recipe(store, session)
    session.state = replace(session.state, recipe=0)
    session.menu_failure = True
    with pytest.raises(TimeoutError):
        run_vendor_job(store, session, 1000, selection=admit(saved, session), sleeper=session.cook)
    attempts = len(session.menu_calls)
    with pytest.raises(VendorBatchStopped):
        run_vendor_job(store, session, 1000, resume=True, sleeper=session.cook)
    assert not session.calls and len(session.menu_calls) == attempts


def test_crash_after_complete_preparation_reuses_evidence_without_replaying_menu(tmp_path):
    store, session, _ = setup(tmp_path)
    saved = save_recipe(store, session)
    session.state = replace(session.state, recipe=0)
    original = store.save
    def crash(record):
        if record["phase"] == "filling":
            raise SystemExit("simulated process death after menu journal commit")
        original(record)
    store.save = crash
    with pytest.raises(SystemExit):
        run_vendor_job(store, session, 1000, selection=admit(saved, session), sleeper=session.cook)
    assert not session.calls and store.current()["phase"] == "preparing"
    attempts = session.menu_calls.count("open_recipe")
    store.save = original
    result = run_vendor_job(store, session, 1000, resume=True, sleeper=session.cook)
    assert result["state"] == "complete" and len(session.calls) == 2
    assert session.menu_calls.count("open_recipe") == attempts


def test_scene_change_between_owner_admission_and_begin_cannot_spend(tmp_path):
    store, session, _ = setup(tmp_path)
    saved = admit(save_recipe(store, session), session)
    session.state = replace(session.state, scene=2)
    with pytest.raises(VendorBatchStopped):
        run_vendor_job(store, session, 1000, selection=saved, sleeper=session.cook)
    assert store.current() is None and not session.calls


def test_wrong_character_and_changed_owner_during_read_cannot_admit(tmp_path):
    store, session, _ = setup(tmp_path)
    saved = save_recipe(store, session)
    for owners in ((dict(OWNER, key=[456, 53]),) * 2, (OWNER, dict(OWNER, server="Other"))):
        values = iter(owners)
        with pytest.raises(VendorBatchStopped):
            require_saved_owner(
                saved, BINDING, session, reader=lambda _, values=values: (next(values), None))
    assert not session.calls


def test_recipe_catalog_menu_operation_is_durable_without_template_selection(tmp_path):
    session = MenuSession(tmp_path / "catalog.json")
    result = open_recipe_catalog(session, session.path, session.snapshot,
                                 clock=lambda: session.time, sleeper=session.sleep)
    assert result["state"] == "complete" and session.calls == ["open_recipe"]
    validate_completed_menu(session.path.read_bytes())


@pytest.mark.parametrize("selection", [None, {}, {"catalog_id": "a" * 32, "template": True},
                                      {"catalog_id": "a" * 32, "template": 2**32},
                                      {"catalog_id": "../x", "template": 25860}])
def test_dashboard_rejects_invalid_recipe_selection(selection):
    with pytest.raises(_RequestError):
        _validate_action_payload(dict(action="vendor-recipe-save", client_id="client",
                                      instance_id="instance", selection=selection))


def test_dashboard_carries_exact_catalog_and_saved_revision():
    for action, selection in (("vendor-recipe-save", {"catalog_id": "a" * 32, "template": 25860}),
                              ("vendor-start", {"recipe_revision": "b" * 32})):
        value = _validate_action_payload(dict(action=action, client_id="client",
                                             instance_id="instance", selection=selection))
        assert value[-1] == selection


def test_save_rechecks_exact_completed_preparation_owner_before_publishing(tmp_path, monkeypatch):
    import shadowbane_lab.manager.vendor_recipes as module
    store, session, recipes = setup(tmp_path)
    run_recipe_selection(store, BINDING, operation(), session, reader=session.reader)
    catalog = recipes.catalog()
    original = module.prepare_recipe
    def switch_after_preparation(*args, **kwargs):
        result = original(*args, **kwargs)
        session.state = replace(session.state, vendor=session.state.vendor + 1, table=99)
        return result
    monkeypatch.setattr(module, "prepare_recipe", switch_after_preparation)
    with pytest.raises(VendorBatchStopped, match="changed before saving"):
        run_recipe_selection(store, BINDING, operation(), session, reader=session.reader,
                             catalog_id=catalog["catalog_id"], template=25860)
    assert recipes.current() is None and not session.calls


def test_full_capacity_is_no_work_without_opening_recipe_or_touching_existing_items(tmp_path):
    from shadowbane_lab.client_extension.vendor_wire import Slot
    store, session, _ = setup(tmp_path)
    saved = save_recipe(store, session)
    session.state = replace(session.state, recipe=0, slots=(Slot(600, 40, 1), Slot(700, 41, 2)))
    attempts = list(session.menu_calls)
    initial = session.state.slots
    result = run_vendor_job(store, session, 1000, selection=admit(saved, session),
                            sleeper=session.cook)
    assert result["state"] == "complete" and result["created"] == result["kept"] == 0
    assert session.menu_calls == attempts and not session.calls and not session.keeps
    assert session.state.slots == initial


@pytest.fixture
def control_setup():
    from tests.test_manager_vendor_control import VendorControlTests
    test = VendorControlTests()
    test.setUp()
    try:
        yield test
    finally:
        test.doCleanups()


def test_http_live_manager_saves_recipe_and_starts_exact_worker(control_setup):
    import http.client
    import threading

    from shadowbane_lab.manager.dashboard import DashboardError, DashboardServer
    from shadowbane_lab.manager.live_configuration import LiveConfiguredManagerApplication
    from shadowbane_lab.manager.operation import WorkerOperationReceipt, WorkerOperationState
    from shadowbane_lab.manager.session import ManagerSessionSnapshot
    from shadowbane_lab.manager.vendor_control import VendorWorkerExecutor
    from shadowbane_lab.manager.worker_runtime import ExactClientWorkerBinding
    from tests.test_manager_application import (
        _application,
        _client,
        _manifest,
        _RecordingSession,
        _slot,
    )
    from tests.test_manager_operation import CLIENT_ID, INSTANCE_ID, NODE_ID, WORKER_ID
    test = control_setup
    session = Session(test.store)
    original_inspect = session.inspect
    def complete_observation():
        observed = original_inspect()
        if not session.state.free_slots:
            session.cook(0)
            observed = replace(observed, snapshot=session.state)
        return observed
    session.inspect = complete_observation
    binding = ExactClientWorkerBinding(CLIENT_ID, INSTANCE_ID, 988, 1234567, 1000, WORKER_ID)
    worker = VendorWorkerExecutor(test.root, NODE_ID, binding, session_factory=lambda _: session,
                                  recipe_reader=session.reader)
    lifecycle = _RecordingSession(ManagerSessionSnapshot(
        node_id=NODE_ID,
        slots=(_slot(CLIENT_ID, instance_id=INSTANCE_ID), _slot("client-02")),
    ))
    application, _ = _application(
        lifecycle, _client(INSTANCE_ID, 988), vendor_control=test.control,
    )
    facade = LiveConfiguredManagerApplication(
        test.root / "manager.json", _manifest(), lambda manifest: application,
    )
    def request(action, selection=None, *, instance_id=INSTANCE_ID):
        payload = dict(action=action, client_id=CLIENT_ID, instance_id=instance_id)
        if selection is not None:
            payload["selection"] = selection
        connection = http.client.HTTPConnection(server.host, server.port, timeout=3)
        try:
            connection.request("POST", "/api/v1/actions", body=json.dumps(payload), headers={
                "Authorization": "Bearer " + server.authorization_token,
                "Content-Type": "application/json",
            })
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()
    def execute(action, selection=None):
        status, response = request(action, selection)
        assert status == 200 and response["ok"], response
        entries = test.operations.inspect_slot(CLIENT_ID)
        pending = [entry for entry in entries if entry.receipt is None]
        assert len(pending) == 1
        op = pending[0].operation
        result = worker.execute(op, stop_signal=threading.Event())
        assert result.state == WorkerOperationState.SUCCEEDED
        test.operations.publish_receipt(WorkerOperationReceipt.for_operation(
            op, WorkerOperationState.SUCCEEDED, observed_at=101))
        return op
    with DashboardServer(facade, port=0) as server:
        # Both HTTP schemas and exact manager bindings remain fail-closed.
        for action, selection in (
            ("vendor-recipe-save", {"catalog_id": "a" * 32, "template": True}),
            ("vendor-start", {"recipe_revision": "b" * 32, "extra": 1}),
            ("vendor-recipes", {"recipe_revision": "b" * 32}),
        ):
            assert request(action, selection)[0] == 400
        assert not test.operations.inspect_slot(CLIENT_ID)
        assert execute("vendor-recipes").command == "vendor recipes"
        recipes = VendorRecipeStore(test.store)
        catalog_id = recipes.catalog()["catalog_id"]
        op = execute("vendor-recipe-save", dict(catalog_id=catalog_id, template=25860))
        assert op.command == f"vendor recipe {catalog_id} 25860"
        revision = recipes.current()["revision"]
        op = execute("vendor-start", dict(recipe_revision=revision))
        assert op.command == "vendor start " + revision
        assert test.store.current()["state"] == "complete" and len(session.calls) == 2
        assert session.closed_count == 3
        assert test.control.recipe_summary(CLIENT_ID, INSTANCE_ID)["saved"]["revision"] == revision
        completed = test.operations.inspect_slot(CLIENT_ID)
        status, _ = request("vendor-start", dict(recipe_revision=revision),
                            instance_id="another-instance")
        assert status != 200 and test.operations.inspect_slot(CLIENT_ID) == completed
        for target in (facade, application):
            with pytest.raises(DashboardError, match="does not accept a selection"):
                target.execute("start-all", selection=dict(recipe_revision=revision))
        assert not lifecycle.calls



def test_stale_saved_revision_and_old_worker_cannot_queue_start(control_setup):
    from tests.test_manager_operation import CLIENT_ID, INSTANCE_ID
    test = control_setup
    session = Session(test.store)
    saved = save_recipe(test.store, session)
    for revision in ("f" * 32, saved["revision"]):
        if revision == saved["revision"]:
            (test.store.root / "vendor-recipe-capability.json").unlink()
        with pytest.raises(VendorBatchStopped):
            test.control.execute("vendor-start", CLIENT_ID, INSTANCE_ID,
                                 selection=dict(recipe_revision=revision))
    assert not test.operations.inspect_slot(CLIENT_ID) and not session.calls


def test_idle_stop_keeps_interrupted_preparation_in_review(control_setup):
    from tests.test_manager_operation import CLIENT_ID, INSTANCE_ID
    test = control_setup
    session = Session(test.store)
    saved = admit(save_recipe(test.store, session), session)
    record = test.store.begin(session, 1000, 100, selection=saved)
    path = test.store.directory(record["job_id"]) / "recipe-preparation.json"
    path.write_text(json.dumps({"state": "review", "requests": [{"state": "prepared"}]}))
    test.control.execute("vendor-stop", CLIENT_ID, INSTANCE_ID, job_id=record["job_id"])
    assert test.store.current()["state"] == "review" and not session.calls
