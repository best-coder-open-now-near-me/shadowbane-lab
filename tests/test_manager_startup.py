import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from shadowbane_lab.manager.dashboard import DashboardServer
from shadowbane_lab.manager.desktop_launcher import StartupPending, wait_for_startup
from shadowbane_lab.manager.startup import (
    StartupConfig,
    StartupError,
    StartupStore,
    startup_payload,
)


class Inspector:
    def __init__(self):
        self.rows = {}

    def inspect(self, pid):
        return self.rows.get(pid)

    def add(self, pid, creation, parent=0):
        self.rows[pid] = NS(
            process_id=pid, process_started_at_100ns=creation, parent_process_id=parent
        )


@pytest.fixture
def case(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    config = StartupConfig.create(
        manifest,
        "node",
        52740,
        tmp_path / "workers",
        tmp_path / "token",
        tmp_path / "pid",
        Path("python"),
    )
    inspector = Inspector()
    store = StartupStore(tmp_path, inspector)
    calls = []

    def spawn(generation):
        calls.append(generation)
        inspector.add(100, 1000)
        return NS(pid=100)

    return store, config, inspector, spawn, calls


def claimed(case):
    store, config, inspector, spawn, calls = case
    record = store.launch_or_reuse(config, spawn, listener_present=lambda: False)
    inspector.add(101, 1001, 100)
    record = store.claim(config, record["generation"], 101)
    return record


def test_concurrent_clicks_spawn_once(case):
    store, c, i, spawn, calls = case
    with ThreadPoolExecutor(8) as pool:
        records = list(
            pool.map(
                lambda _: store.launch_or_reuse(c, spawn, listener_present=lambda: False), range(16)
            )
        )
    assert len(calls) == 1 and len({r["generation"] for r in records}) == 1


def test_timeout_then_next_click_reuses_pending_exact_child(case):
    store, c, i, spawn, calls = case
    record = store.launch_or_reuse(c, spawn, listener_present=lambda: False)
    now = [0.0]
    with pytest.raises(StartupPending):
        wait_for_startup(
            store,
            c,
            record,
            "token",
            deadline=1,
            clock=lambda: now[0],
            sleep=lambda t: now.__setitem__(0, now[0] + t),
            request=lambda *a: None,
        )
    assert store.launch_or_reuse(c, spawn, listener_present=lambda: True) == record
    i.add(101, 1001, 100)
    record = store.claim(c, record["generation"], 101)
    assert (
        wait_for_startup(
            store,
            c,
            record,
            "token",
            deadline=now[0] + 1,
            clock=lambda: now[0],
            request=lambda *a: startup_payload(record),
        )
        == record
    )
    assert len(calls) == 1


def test_crash_before_identity_is_unknown_not_a_second_launch(case):
    store, c, i, _, calls = case

    def crash(generation):
        calls.append(generation)
        raise OSError("spawn outcome unknown")

    with pytest.raises(OSError):
        store.launch_or_reuse(c, crash, listener_present=lambda: False)
    record = store.launch_or_reuse(c, crash, listener_present=lambda: False)
    assert record["launcher"] is None and len(calls) == 1


def test_child_exit_does_not_restart_same_wait(case):
    store, c, i, spawn, calls = case
    record = store.launch_or_reuse(c, spawn, listener_present=lambda: False)
    i.rows.clear()
    with pytest.raises(StartupError, match="exited"):
        wait_for_startup(store, c, record, "token", deadline=1, clock=lambda: 0)
    assert len(calls) == 1


def test_positive_retirement_allows_new_attempt_but_pid_reuse_is_not_adopted(case):
    record = claimed(case)
    store, c, i, spawn, calls = case
    i.rows.clear()
    i.add(101, 9999, 100)
    with pytest.raises(StartupError, match="lifetime"):
        store.verify_listener(c, record["generation"], startup_payload(record))
    fresh = store.launch_or_reuse(c, spawn, listener_present=lambda: False)
    assert fresh["generation"] != record["generation"] and len(calls) == 2


def test_access_failure_never_authorizes_launch(case):
    claimed(case)
    store, c, i, spawn, calls = case

    def denied(pid):
        raise PermissionError("unknown")

    i.inspect = denied
    with pytest.raises(PermissionError):
        store.launch_or_reuse(c, spawn, listener_present=lambda: False)
    assert len(calls) == 1


def test_foreign_listener_no_spawn_no_record(case):
    store, c, i, spawn, calls = case
    with pytest.raises(StartupError, match="unverified listener"):
        store.launch_or_reuse(c, spawn, listener_present=lambda: True)
    assert not calls and store.read() is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", "0" * 32),
        ("manifest", "wrong"),
        ("node_id", "wrong"),
        ("state", "ready"),
        ("manager", {"pid": 99, "creation": 1}),
    ],
)
def test_listener_identity_exact(case, field, value):
    record = claimed(case)
    store, c, *_ = case
    payload = startup_payload(record)
    payload[field] = value
    with pytest.raises(StartupError):
        store.verify_listener(c, record["generation"], payload)


def test_direct_child_and_exact_generation_required(case):
    store, c, i, spawn, calls = case
    record = store.launch_or_reuse(c, spawn, listener_present=lambda: False)
    i.add(101, 1001, 777)
    with pytest.raises(StartupError, match="direct child"):
        store.claim(c, record["generation"], 101)
    i.add(101, 1001, 100)
    with pytest.raises(StartupError):
        store.claim(c, "0" * 32, 101)


def test_manifest_change_before_claim_rejected_but_live_expansion_reused(case):
    store, c, i, spawn, calls = case
    record = store.launch_or_reuse(c, spawn, listener_present=lambda: False)
    i.add(101, 1001, 100)
    Path(c.manifest).write_text('{"changed":true}')
    with pytest.raises(StartupError):
        store.claim(c, record["generation"], 101)
    Path(c.manifest).write_text("{}")
    record = store.claim(c, record["generation"], 101)
    Path(c.manifest).write_text('{"expanded":true}')
    assert store.launch_or_reuse(c, spawn, listener_present=lambda: True) == record
    assert store.verify_listener(c, record["generation"], startup_payload(record)) == record


def test_authenticated_startup_responds_while_status_is_blocked(case):
    record = claimed(case)
    started = threading.Event()
    release = threading.Event()

    class Service:
        def status(self):
            started.set()
            release.wait(5)
            return {"ok": True}

        def execute(self, *a, **k):
            raise AssertionError("no action")

    with DashboardServer(Service(), startup_record=record) as server, ThreadPoolExecutor(1) as pool:
        token = server.authorization_token
        url = f"http://127.0.0.1:{server.port}"

        def get(path, auth=True):
            r = urllib.request.Request(
                url + path, headers={"Authorization": "Bearer " + token} if auth else {}
            )
            with urllib.request.urlopen(r, timeout=2) as response:
                return json.load(response)

        slow = pool.submit(get, "/api/v1/status")
        try:
            assert started.wait(1)
            assert get("/api/v1/startup") == startup_payload(record)
            record["manager"]["pid"] = (
                999  # Frozen encoded response is independent of caller mutation.
            )
            assert get("/api/v1/startup")["manager"]["pid"] == 101
            with pytest.raises(urllib.error.HTTPError) as denied:
                get("/api/v1/startup", False)
            assert denied.value.code == 401
        finally:
            release.set()
        assert slow.result()["ok"]
