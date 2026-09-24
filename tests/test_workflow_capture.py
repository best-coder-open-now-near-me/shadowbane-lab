import json
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_observation.reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES
from shadowbane_lab.client_observation.workflow_capture import (
    read_window_context,
    record_workflow,
)
from tests.test_native_guard_upgrade import BUTTON, fixture


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def memory():
    return SimpleNamespace(
        pid=7, process_creation_filetime_utc=11, executable_name="sb.exe",
        pointer_size=4, executable_sha256=next(iter(REVIEWED_VENDOR_EXECUTABLES)),
    )


def run(tmp_path, readers, **kwargs):
    clock = Clock()
    result = record_workflow(
        memory(), tmp_path / "capture.jsonl", tmp_path / "stop", process_id=7,
        creation=11, duration=0.6, interval=0.2, readers=readers,
        clock=clock, sleep=clock.sleep, alive=lambda: True, **kwargs,
    )
    records = [json.loads(line) for line in (tmp_path / "capture.jsonl").read_text().splitlines()]
    return result, records


def test_continues_through_absent_windows_and_retains_later_transitions(tmp_path):
    calls = 0

    def reader(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("quote not open")
        return {"funds": 100 if calls == 2 else 80}

    result, records = run(tmp_path, {"quote": reader, "other": lambda _: {"visible": True}})
    changes = [r for r in records if r["record_type"] == "channel_change"]
    quote = [r for r in changes if r["channel"] == "quote"]
    assert [r["state"] for r in quote] == ["unavailable", "observed", "observed"]
    assert quote[-1]["data"]["funds"] == 80
    assert len([r for r in changes if r["channel"] == "other"]) == 1
    assert result["reason"] == "deadline"
    assert records[-1]["counts"]["quote"] == {"observed": 2, "unavailable": 1}
    assert not records[-1]["workflow_completeness_verified"]


def test_explicit_stop_flushes_end_record(tmp_path):
    result, records = run(
        tmp_path, {"menu": lambda _: {}},
        armed=lambda: (tmp_path / "stop").write_text("stop"),
    )
    assert result["reason"] == "requested"
    assert records[-1]["samples"] == 1


def test_exited_process_never_rebinds_or_samples(tmp_path):
    result = record_workflow(
        memory(), tmp_path / "capture", tmp_path / "stop", process_id=7, creation=11,
        readers={"never": lambda _: pytest.fail("sampled dead process")}, alive=lambda: False,
    )
    assert result["reason"] == "process_unavailable"
    assert result["samples"] == 0


def test_identity_mismatch_leaves_no_capture(tmp_path):
    with pytest.raises(RuntimeError, match="identity"):
        record_workflow(memory(), tmp_path / "capture", tmp_path / "stop",
                        process_id=7, creation=12)
    assert not (tmp_path / "capture").exists()


def test_existing_capture_not_overwritten(tmp_path):
    path = tmp_path / "capture.jsonl"
    path.write_text("keep")
    with pytest.raises(FileExistsError):
        run(tmp_path, {"menu": lambda _: {}})
    assert path.read_text() == "keep"


def test_unknown_hud_is_retained_without_parsing_unknown_controls():
    m = fixture()
    m.put(0x190200 + 8, "<I", 0x510000)
    m.put(0x510000, "<I", m.base_address + 0x123456)
    out = read_window_context(m)
    assert out["huds"][-1] == {"address": 0x510000, "class_rva": 0x123456}
    assert not any(address == 0x510054 for address, _ in m.reads)


def test_control_change_during_capture_is_rejected():
    m = fixture()
    original = m.read_block
    calls = 0

    def read(address, size):
        nonlocal calls
        data = original(address, size)
        if address == BUTTON + 0x1A8:
            calls += 1
            if calls > 1:
                return (1).to_bytes(4, "little")
        return data

    m.read_block = read
    with pytest.raises(RuntimeError, match="changed"):
        read_window_context(m)


@pytest.mark.parametrize("vendors", [False, True])
def test_vendor_capture_cli_is_opt_in_and_retains_exact_lifetime(tmp_path, monkeypatch, vendors):
    from unittest.mock import Mock

    from shadowbane_lab.client_observation import workflow_capture
    from tests.test_native_vendor_queue import add_recipe, fixture

    m = add_recipe(fixture())
    m.put(m.base_address, "<2s", b"MZ")
    m.close = Mock()
    opened = Mock(return_value=m)
    monkeypatch.setattr(workflow_capture.WindowsReadOnlyProcessMemory, "open_for_process", opened)
    args = ["workflow_capture", "--process-id", str(m.pid), "--creation", "100",
            "--output", str(tmp_path / "capture"), "--stop-file", str(tmp_path / "stop"),
            "--duration", "0.05", "--interval", "0.05"]
    if vendors:
        args.append("--vendors")
    monkeypatch.setattr("sys.argv", args)
    assert workflow_capture.main() == 0
    opened.assert_called_once_with("sb.exe", m.pid)
    m.close.assert_called_once_with()
    records = [json.loads(line) for line in (tmp_path / "capture").read_text().splitlines()]
    start = records[0]
    assert start["process_id"] == m.pid
    assert start["process_creation_filetime_utc"] == 100
    assert start["executable_sha256"] == m.executable_sha256
    assert start["read_only"] and not start["server_acceptance_verified"]
    assert ("vendor_roster" in start["channels"]) == vendors
    assert ("vendor_queue" in start["channels"]) == vendors
    if vendors:
        queue = next(r for r in records if r.get("channel") == "vendor_queue")
        assert queue["state"] == "observed"
        assert queue["data"]["creation_recipe"]["template"]["object_id"] == 26990
        assert queue["data"]["vendor"]["object_id"] == 2517204
        assert not queue["data"]["command_admitted"]


def test_vendor_capture_preserves_closed_recipe_inventory_transitions(tmp_path):
    from shadowbane_lab.client_observation.workflow_capture import VENDOR_READERS
    from tests.test_native_vendor_inventory import ITEM_ID, inventory_fixture
    from tests.test_native_vendor_queue import MANAGER, add_recipe, fixture

    m = fixture()
    m.put(MANAGER + 0x78, "<I", 0)
    clock = Clock()
    stages = iter((add_recipe(fixture()), inventory_fixture()))

    def sleep(seconds):
        clock.sleep(seconds)
        next_stage = next(stages, None)
        if next_stage is not None:
            m.data = next_stage.data
            m.reads.clear()

    result = record_workflow(
        m, tmp_path / "capture", tmp_path / "stop", process_id=m.pid, creation=100,
        duration=0.6, interval=0.2, readers={"windows": read_window_context, **VENDOR_READERS},
        clock=clock, sleep=sleep, alive=lambda: True,
    )
    records = [json.loads(line) for line in (tmp_path / "capture").read_text().splitlines()]
    queue = [r for r in records if r.get("channel") == "vendor_queue"]
    assert [r["state"] for r in queue] == ["unavailable", "observed", "observed"]
    assert "data" not in queue[0]
    assert queue[1]["data"]["creation_recipe"]["qualified_random_scepter"]
    assert queue[1]["data"]["inventory"] is None
    assert queue[2]["data"]["creation_recipe"] is None
    inventory = queue[2]["data"]["inventory"]
    assert inventory["items"][0]["item"]["object_id"] == ITEM_ID
    assert not inventory["complete_inventory"] and inventory["capacity"] is None
    assert result["counts"]["vendor_queue"] == {"observed": 2, "unavailable": 1}
    assert all(r["state"] == "unavailable" for r in records
               if r.get("channel") == "vendor_roster")
    assert records[-1]["reason"] == "deadline"


def test_vendor_roster_capture_retains_unverified_membership(tmp_path):
    from shadowbane_lab.client_observation.workflow_capture import VENDOR_READERS
    from tests.test_native_vendor_roster import roster_fixture

    m, clock = roster_fixture(), Clock()
    record_workflow(
        m, tmp_path / "capture", tmp_path / "stop", process_id=m.pid, creation=100,
        duration=0.2, interval=0.2, readers=VENDOR_READERS,
        clock=clock, sleep=clock.sleep, alive=lambda: True,
    )
    records = [json.loads(line) for line in (tmp_path / "capture").read_text().splitlines()]
    roster = next(r for r in records if r.get("channel") == "vendor_roster")
    assert roster["state"] == "observed"
    assert [row["vendor"]["object_id"] for row in roster["data"]["vendors"]] == [101, 102]
    assert not roster["data"]["town_membership_verified"]
    assert not roster["data"]["management_permission_verified"]
    queue = next(r for r in records if r.get("channel") == "vendor_queue")
    assert queue["state"] == "unavailable" and "data" not in queue


@pytest.mark.parametrize("furniture,condemn", [(False, False), (True, False), (True, True)])
def test_response_cli_opt_in_lifetime_and_independent_channels(
    tmp_path, monkeypatch, furniture, condemn,
):
    from unittest.mock import Mock

    from shadowbane_lab.client_extension import event_reader
    from shadowbane_lab.client_observation import workflow_capture
    from tests.test_condemn_responses import fixture as condemn_fixture
    from tests.test_furniture_responses import fixture as furniture_fixture

    m = memory()
    m.base_address = 0x400000
    m.read_block = lambda *_: b"MZ"
    m.close = Mock()
    opened = Mock(return_value=m)
    monkeypatch.setattr(workflow_capture.WindowsReadOnlyProcessMemory, "open_for_process", opened)
    monkeypatch.setattr(workflow_capture, "READERS", {"windows": lambda _: {"open": True}})
    calls = []

    class SharedMemory:
        def read(self, name, size):
            calls.append((name, size))
            return bytes(furniture_fixture() if ".Furniture." in name else condemn_fixture())

    monkeypatch.setattr(event_reader, "WindowsSharedMemorySnapshotReader", SharedMemory)
    args = ["workflow_capture", "--process-id", "7", "--creation", "11",
            "--output", str(tmp_path / "capture"), "--stop-file", str(tmp_path / "stop"),
            "--duration", "0.05", "--interval", "0.05"]
    if furniture:
        args.append("--furniture-responses")
    if condemn:
        args.append("--condemn-responses")
    monkeypatch.setattr("sys.argv", args)
    assert workflow_capture.main() == 0
    opened.assert_called_once_with("sb.exe", 7)
    m.close.assert_called_once_with()
    records = [json.loads(line) for line in (tmp_path / "capture").read_text().splitlines()]
    assert ("furniture_responses" in records[0]["channels"]) == furniture
    assert ("condemn_responses" in records[0]["channels"]) == condemn
    observations = {}
    for record in records:
        if record["record_type"] == "channel_change":
            observations.setdefault(record["channel"], record)
    for name, enabled, operation in (("furniture", furniture, 2), ("condemn", condemn, 13)):
        if enabled:
            data = observations[f"{name}_responses"]["data"]
            assert data["process_id"] == 7 and data["process_creation_filetime_utc"] == 11
            assert data["records"][0]["payload"]["operation"] == operation
            assert not data["command_admitted"] and not data["server_acceptance_verified"]
    assert len(calls) >= 2 * (furniture + condemn)
    assert len(calls) % 2 == 0
    assert all(name.endswith(".7.11") for name, _ in calls)


def test_unavailable_furniture_mapping_does_not_hide_window_context(tmp_path):
    from shadowbane_lab.client_extension.furniture_responses import FurnitureResponseReader

    class AbsentMemory:
        def read(self, *_):
            raise OSError("furniture recorder unavailable")

    reader = FurnitureResponseReader(7, 11, AbsentMemory())
    result, records = run(tmp_path, {
        "furniture_responses": lambda _: reader.drain(),
        "windows": lambda _: {"open": True},
    })
    assert result["counts"]["furniture_responses"] == {"observed": 0, "unavailable": 3}
    furniture = next(r for r in records if r.get("channel") == "furniture_responses")
    assert furniture["state"] == "unavailable" and "data" not in furniture
    windows = next(r for r in records if r.get("channel") == "windows")
    assert windows["state"] == "observed"
