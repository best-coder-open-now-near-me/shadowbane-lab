"""Kernel census parser negatives plus actual Windows creation-time conformance."""

import ctypes
import os
import struct
from types import SimpleNamespace

import pytest

from shadowbane_lab.manager import process_snapshot as snapshot
from shadowbane_lab.manager.supervisor import Win32ProcessLifetimeInspector


def entry(pid, created, parent=0, *, pointer_size=8, next_offset=0, threads=0):
    size, width, offset = (256, 80, 80) if pointer_size == 8 else (184, 64, 68)
    value = bytearray(size + threads * width)
    struct.pack_into("<II", value, 0, next_offset, threads)
    struct.pack_into("<q", value, 32, created)
    fmt = "<Q" if pointer_size == 8 else "<I"
    struct.pack_into(fmt, value, offset, pid)
    struct.pack_into(fmt, value, offset + pointer_size, parent)
    return bytes(value)


@pytest.mark.parametrize("pointer_size", [4, 8])
def test_complete_snapshot_exact_lifetimes_and_absence(pointer_size):
    size = 256 if pointer_size == 8 else 184
    data = entry(0, 0, pointer_size=pointer_size, next_offset=size) + entry(
        3384, 134358737128098175, 952, pointer_size=pointer_size
    )
    rows = snapshot.parse_process_snapshot(data, pointer_size=pointer_size)
    assert rows[3384] == snapshot.SystemProcessIdentity(3384, 134358737128098175, 952)
    assert rows.get(9999) is None
    assert rows[3384].creation_filetime > 134358558804042547


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\0" * 255,
        entry(1, 123, next_offset=8),
        entry(1, 123, next_offset=264),
        entry(1, 123, next_offset=257) + entry(2, 456),
        entry(1, 123, next_offset=256),
        entry(1, 123, next_offset=256) + entry(1, 456),
        entry(1, 0),
        entry(1, -1),
        entry(2**32, 123),
        entry(1, 123, parent=2**32),
    ],
)
def test_invalid_or_partial_snapshot_never_proves_absence(data):
    with pytest.raises(ValueError):
        snapshot.parse_process_snapshot(data, pointer_size=8)


def test_late_malformed_entry_invalidates_early_target():
    data = entry(3384, 123, next_offset=256) + b"\0" * 16
    with pytest.raises(ValueError):
        snapshot.parse_process_snapshot(data, pointer_size=8)


def test_thread_extent_must_fit():
    data = bytearray(entry(3384, 123))
    struct.pack_into("<I", data, 4, 1)
    with pytest.raises(ValueError):
        snapshot.parse_process_snapshot(bytes(data), pointer_size=8)


@pytest.mark.parametrize("pointer_size", [0, 1, 16])
def test_unsupported_layout(pointer_size):
    with pytest.raises(ValueError):
        snapshot.parse_process_snapshot(entry(1, 2), pointer_size=pointer_size)


class FakeQuery:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    def __call__(self, information_class, buffer, size, returned):
        assert information_class == 5
        self.calls += 1
        status, length, payload = next(self.results)
        returned._obj.value = length
        if payload:
            ctypes.memmove(buffer, payload, len(payload))
        return status


def bind_query(monkeypatch, query):
    monkeypatch.setattr(snapshot.os, "name", "nt")
    monkeypatch.setattr(
        snapshot.ctypes,
        "WinDLL",
        lambda name: SimpleNamespace(NtQuerySystemInformation=query),
        raising=False,
    )


def test_bounded_query_retries_size_churn_only(monkeypatch):
    data = entry(3384, 123, pointer_size=ctypes.sizeof(ctypes.c_void_p))
    query = FakeQuery([(0xC0000004, 80000, b""), (0, len(data), data)])
    bind_query(monkeypatch, query)
    assert snapshot.query_process_snapshot()[3384].creation_filetime == 123
    assert query.calls == 2


@pytest.mark.parametrize(
    "result", [(0xC0000022, 0, b""), (0, 0, b""), (0, 65537, b""), (0, 1, b"X")]
)
def test_query_errors_or_invalid_return_lengths_stay_unknown(monkeypatch, result):
    query = FakeQuery([result])
    bind_query(monkeypatch, query)
    with pytest.raises((OSError, ValueError)):
        snapshot.query_process_snapshot()
    assert query.calls == 1


def test_size_growth_is_bounded(monkeypatch):
    query = FakeQuery([(0xC0000004, 2**31, b"")])
    bind_query(monkeypatch, query)
    with pytest.raises(OSError, match="size limit"):
        snapshot.query_process_snapshot()
    assert query.calls == 1


def test_retry_count_is_bounded(monkeypatch):
    query = FakeQuery([(0xC0000004, 1, b"")] * 8)
    bind_query(monkeypatch, query)
    with pytest.raises(OSError, match="bounded"):
        snapshot.query_process_snapshot()
    assert query.calls == 8


def inspector_with_open_error(error):
    inspector = object.__new__(Win32ProcessLifetimeInspector)
    inspector._ctypes = SimpleNamespace(
        set_last_error=lambda value: None, get_last_error=lambda: error
    )
    inspector._kernel32 = SimpleNamespace(OpenProcess=lambda *args: None)
    return inspector


def test_access_denied_uses_positive_reused_identity(monkeypatch):
    monkeypatch.setattr(
        snapshot,
        "query_process_snapshot",
        lambda: {3384: snapshot.SystemProcessIdentity(3384, 900, 952)},
    )
    value = inspector_with_open_error(5).inspect(3384)
    assert (value.process_id, value.process_started_at_100ns, value.parent_process_id) == (
        3384,
        900,
        952,
    )


def test_denied_unknown_census_propagates(monkeypatch):
    def failed():
        raise OSError("census failed")

    monkeypatch.setattr(snapshot, "query_process_snapshot", failed)
    with pytest.raises(OSError, match="census failed"):
        inspector_with_open_error(5).inspect(3384)


@pytest.mark.parametrize("error", [6, 87, 1168])
def test_non_denial_errors_do_not_use_census(monkeypatch, error):
    def forbidden():
        raise AssertionError("unexpected fallback")

    monkeypatch.setattr(snapshot, "query_process_snapshot", forbidden)
    if error in (87, 1168):
        assert inspector_with_open_error(error).inspect(3384) is None
    else:
        with pytest.raises(OSError):
            inspector_with_open_error(error).inspect(3384)


@pytest.mark.skipif(os.name != "nt", reason="actual Windows kernel snapshot conformance")
def test_actual_windows_census_matches_current_process_handle():
    pid = os.getpid()
    normal = Win32ProcessLifetimeInspector().inspect(pid)
    observed = snapshot.query_process_snapshot()[pid]
    assert normal is not None
    assert (observed.process_id, observed.creation_filetime, observed.parent_process_id) == (
        normal.process_id,
        normal.process_started_at_100ns,
        normal.parent_process_id,
    )


def test_manager_attach_skips_protected_reused_historical_pid(tmp_path, monkeypatch):
    import json
    from unittest.mock import patch

    from shadowbane_lab.manager.supervisor import ProcessLifetimeSnapshot
    from tests import test_worker_reservation_restart as fixtures

    ledger, original, _, controller, path, binding, record = fixtures.restarted(tmp_path)
    protected = inspector_with_open_error(5)
    monkeypatch.setattr(
        snapshot,
        "query_process_snapshot",
        lambda: {
            7028: snapshot.SystemProcessIdentity(7028, 201, 952),
        },
    )
    controller._process_inspector = SimpleNamespace(
        inspect=lambda pid: protected.inspect(pid) if pid == 7028 else original.inspect(pid)
    )
    session = fixtures.app._RecordingSession(
        fixtures.app.ManagerSessionSnapshot(
            node_id=fixtures.f.NODE_ID, slots=(fixtures.app._slot(fixtures.f.CLIENT_ID),)
        )
    )
    application, _ = fixtures.app._application(
        session, fixtures.f._client(), worker_controller=controller
    )
    child = SimpleNamespace(pid=8000, poll=lambda: None)
    original.processes[8000] = ProcessLifetimeSnapshot(8000, 300)
    original.processes[8001] = ProcessLifetimeSnapshot(8001, 301, parent_process_id=8000)
    with patch(
        "shadowbane_lab.manager.worker_runtime.subprocess.Popen",
        side_effect=fixtures.h.popen_publish(ledger, child, pid=8001, creation=301),
    ) as popen:
        application.execute(
            "attach", client_id=fixtures.f.CLIENT_ID, instance_id=fixtures.f._client().instance_id
        )
        application.reconcile_instances()
        assert popen.call_count == 1
    assert record in ledger.inspect(fixtures.f.CLIENT_ID).records
    assert ledger.inspect_stop_request(fixtures.f.CLIENT_ID, binding.worker_id) is None
    assert json.loads(path.read_text())["process_id"] == 8001


def test_successful_complete_census_proves_absence(monkeypatch):
    monkeypatch.setattr(snapshot, "query_process_snapshot", lambda: {})
    assert inspector_with_open_error(5).inspect(3384) is None
