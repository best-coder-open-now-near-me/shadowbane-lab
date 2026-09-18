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
