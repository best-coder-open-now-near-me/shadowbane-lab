import json
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_extension import condemn_progress
from shadowbane_lab.manager.condemn_control import ManagerCondemnControl
from shadowbane_lab.manager.manifest import MAX_MANAGER_CLIENT_SLOTS
from tests.test_condemn_job import cycle_setup, setup  # noqa: F401


def test_summary_reuses_verified_proof_but_reads_fresh_records(setup, monkeypatch):  # noqa: F811
    f = setup
    f.run()
    store = f.base.store
    control = ManagerCondemnControl(store.root.parents[2], store.identity[0], Mock(), Mock())
    # Use the fixture's real identity path, without changing admission or execution.
    monkeypatch.setattr(control, "store", lambda *_: store)
    validate = Mock(wraps=condemn_progress._validate_attempt)
    monkeypatch.setattr(condemn_progress, "_validate_attempt", validate)
    first = control.summary("client", "instance")
    assert first["job"]["completed"] == 4
    assert validate.call_count == 4
    first["job"]["completed"] = -1
    saved_job = f.jobs.current()
    saved_job["detail"] = "Fresh completion detail"
    f.jobs.save(saved_job)
    second = control.summary("client", "instance")
    assert second["job"]["completed"] == 4 and second["job"]["detail"] == "Fresh completion detail"
    assert validate.call_count == 4
    # Changed proof must be validated and rejected, even after warming the cache.
    path = f.jobs.native_progress.path
    saved = json.loads(path.read_bytes())
    saved["attempts"][0]["owner"] = "invalid"
    path.write_text(json.dumps(saved), encoding="utf-8")
    assert "error" in control.summary("client", "instance")
    assert validate.call_count == 5


def test_summary_cache_is_bounded_and_drops_changed_or_unbound_lifetimes(tmp_path):
    control = ManagerCondemnControl(tmp_path, "node", Mock(), Mock())
    first = control._summary_store("client", "one")
    assert control._summary_store("client", "one") is first
    assert control._summary_store("client", "two") is not first
    assert ("client", "one") not in control._summary_jobs
    assert control.summary("client", None) is None
    assert not control._summary_jobs
    for index in range(MAX_MANAGER_CLIENT_SLOTS):
        control.summary(f"client-{index}", "instance")
    oldest = control._summary_store("client-0", "instance")
    control.summary("new-client", "instance")
    assert len(control._summary_jobs) == MAX_MANAGER_CLIENT_SLOTS
    assert ("client-1", "instance") not in control._summary_jobs
    assert control._summary_store("client-0", "instance") is oldest


@pytest.mark.parametrize("change", ["cycle", "job", "missing"])
def test_warm_summary_still_rejects_changed_job_or_cycle(setup, monkeypatch, change):  # noqa: F811
    f = setup
    result = f.run()
    control = ManagerCondemnControl(f.base.store.root, "node", Mock(), Mock())
    monkeypatch.setattr(control, "store", lambda *_: f.base.store)
    assert control.summary("client", "instance")["job"]["completed"] == 4
    if change == "cycle":
        name = result["cycles"][0]["operation_id"] + ".json"
        path = f.base.store.root / "condemn-cycles" / name
        record = json.loads(path.read_bytes())
        record["actions"][0]["request"] = "changed"
    else:
        path = f.jobs.path(result["job_id"])
        record = json.loads(path.read_bytes())
        record["selection"]["targets"].pop()
    if change == "missing":
        path.unlink()
    else:
        path.write_text(json.dumps(record), encoding="utf-8")
    assert "error" in control.summary("client", "instance")
