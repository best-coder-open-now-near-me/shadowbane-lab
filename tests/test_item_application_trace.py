"""Optional diagnostics never become application or action authority."""

import json
import os
import struct
import subprocess

import pytest

from shadowbane_lab.client_extension import item_application_trace as t


def record(seq=1, stage=1, kind=1, **changes):
    values = dict(
        seq=seq,
        tick=9,
        thread=3,
        stage=stage,
        kind=kind,
        flags=3,
        decode=seq if stage == 1 else 0,
        scene=7,
        local_id=42,
        local_type=53,
        caller=0x3625BC if stage == 1 else 0,
        returned=0,
        request=bytes(16),
        command=bytes(32),
        outcome=0,
        entry=0,
        settled=0,
        history=0,
        body=[2, 1, 99, 30, 0, 0, 0, 0, 0, 0, 0],
        reserved=0,
    )
    if stage == 4:
        values.update(
            request=b"r" * 16, command=b"d" * 32, outcome=1, entry=2, settled=2, history=4
        )
    values.update(changes)
    return t.RECORD.pack(
        *(
            values[k]
            for k in (
                "seq",
                "tick",
                "thread",
                "stage",
                "kind",
                "flags",
                "decode",
                "scene",
                "local_id",
                "local_type",
                "caller",
                "returned",
                "request",
                "command",
                "outcome",
                "entry",
                "settled",
                "history",
            )
        ),
        *values["body"],
        values["reserved"],
    )


def snapshot(count=1, *, stopped=0, rejected=0, drops=0, rows=None):
    data = bytearray(t.SIZE)
    t.HEADER.pack_into(
        data,
        0,
        b"WBITEM1\0",
        1,
        t.RECORD_SIZE,
        t.CAPACITY,
        11,
        22,
        count,
        max(0, count - t.CAPACITY),
        stopped,
        rejected,
        drops,
    )
    for seq in range(max(1, count - t.CAPACITY + 1), count + 1):
        row = (rows or {}).get(seq, record(seq))
        offset = t.HEADER.size + ((seq - 1) % t.CAPACITY) * t.RECORD_SIZE
        data[offset : offset + t.RECORD_SIZE] = row
    return bytes(data)


class Memory:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def read(self, name, size):
        self.calls.append((name, size))
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def test_four_stages_remain_independent_raw_evidence():
    power = [429021400, 40, 42, 53, 0, 0, 1, 2, 3, 1, 7]
    rows = {
        1: record(),
        2: record(2, 2, flags=7, decode=1),
        3: record(3, 3, flags=7, decode=1, returned=0),
        4: record(4, 4),
        5: record(5, 1, 2, body=power),
    }
    parsed = t.parse_snapshot(snapshot(5, rows=rows), process_id=11, creation=22)
    assert [r["stage"] for r in parsed["records"]] == [
        "decoded",
        "processing",
        "returned",
        "owned_return",
        "decoded",
    ]
    assert parsed["records"][3]["command_digest"] == (b"d" * 32).hex()
    assert parsed["records"][4]["payload_words"] == power
    assert all(r["request"] is None for r in parsed["records"] if r["stage"] != "owned_return")


@pytest.mark.parametrize(
    "changes",
    [
        {"flags": 8},
        {"reserved": 1},
        {"kind": 3},
        {"stage": 0},
        {"thread": 0},
        {"decode": 2},
        {"caller": 0},
        {"scene": 0},
        {"local_type": 37},
        {"returned": 1},
        {"request": b"x" * 16},
        {"command": b"x" * 32},
        {"history": 4},
        {"flags": 2},
        {"body": [1, 1, 99, 30, 1, 0, 0, 0, 0, 0, 0]},
        {"body": [2, 1, 99, 30, 0, 0, 1, 0, 0, 0, 0]},
    ],
)
def test_incoherent_or_invented_provenance_rejected(changes):
    with pytest.raises(t.ItemApplicationTraceError):
        t.parse_snapshot(snapshot(rows={1: record(**changes)}), process_id=11, creation=22)


@pytest.mark.parametrize(
    "changes",
    [
        {"history": 1},
        {"kind": 2},
        {"request": bytes(16)},
        {"command": bytes(32)},
        {"flags": 7},
        {"entry": 3},
    ],
)
def test_owned_return_strict(changes):
    with pytest.raises(t.ItemApplicationTraceError):
        t.parse_snapshot(snapshot(rows={1: record(1, 4, **changes)}), process_id=11, creation=22)


def test_lifetime_size_and_counter_bounds():
    data = snapshot()
    for pid, born in [(12, 22), (11, 23)]:
        with pytest.raises(t.ItemApplicationTraceError):
            t.parse_snapshot(data, process_id=pid, creation=born)
    with pytest.raises(t.ItemApplicationTraceError):
        t.parse_snapshot(data[:-1], process_id=11, creation=22)
    with pytest.raises(ValueError):
        t.mapping_name(True, 22)
    corrupt = bytearray(data)
    struct.pack_into("<q", corrupt, 40, 1)
    with pytest.raises(t.ItemApplicationTraceError):
        t.parse_snapshot(bytes(corrupt), process_id=11, creation=22)


def test_reader_exact_read_only_mapping_no_replay_and_explicit_gaps():
    memory = Memory(snapshot())
    reader = t.ItemApplicationTraceReader(11, 22, memory)
    first = reader.drain()
    assert first["initial_history"] and not first["command_admitted"]
    assert not first["server_acceptance_verified"]
    assert not reader.drain()["records"]
    memory.data = snapshot(300, rejected=1, drops=2)
    later = reader.drain()
    assert later["missed_records"] == 43 and later["capture_incomplete"]
    assert memory.calls == [(t.mapping_name(11, 22), t.SIZE)] * 6
    memory.data = snapshot(301, stopped=1, rejected=1, drops=2)
    assert reader.drain()["stopped"]
    with pytest.raises(t.ItemApplicationTraceError, match="stopped"):
        reader.drain()


def test_unknown_body_or_scene_makes_capture_incomplete():
    memory = Memory(
        snapshot(rows={1: record(flags=0, scene=0, local_id=0, local_type=0, body=[0] * 11)})
    )
    assert t.ItemApplicationTraceReader(11, 22, memory).drain()["capture_incomplete"]


def test_ring_publication_window_is_bounded_unavailable_not_corruption():
    data = bytearray(snapshot(256))
    struct.pack_into("<q", data, t.HEADER.size, 0)
    memory = Memory(bytes(data))
    reader = t.ItemApplicationTraceReader(11, 22, memory)
    with pytest.raises(t.ItemApplicationTraceError, match="changed"):
        reader.drain()
    assert len(memory.calls) == 6
    memory.data = snapshot(257)
    assert reader.drain()["read_errors"] == 1


def test_counter_regression_cannot_rebind():
    memory = Memory(snapshot(2))
    reader = t.ItemApplicationTraceReader(11, 22, memory)
    reader.drain()
    memory.data = snapshot(1)
    with pytest.raises(t.ItemApplicationTraceError, match="regressed"):
        reader.drain()
    memory.data = snapshot(3)
    with pytest.raises(t.ItemApplicationTraceError, match="regressed"):
        reader.drain()


def test_cli_unavailable_writes_unknown_without_producer(tmp_path, monkeypatch):
    memory = Memory(OSError("mapping disabled or unsupported"))
    monkeypatch.setattr(t, "WindowsSharedMemorySnapshotReader", lambda: memory)
    path = tmp_path / "diagnostic.jsonl"
    assert t.main(["--process-id", "11", "--creation-filetime", "22", "--output", str(path)]) == 1
    result = json.loads(path.read_text())
    assert result["diagnostic_state"] == "unknown" and not result["command_admitted"]
    assert len(memory.calls) == 1


def test_actual_native_layout(tmp_path):
    executable = os.environ.get("WONDERBANE_ITEM_TRACE_TEST")
    if not executable:
        pytest.skip("optional compiled native trace fixture")
    path = tmp_path / "native-trace.bin"
    subprocess.run([executable, "snapshot", str(path)], check=True, timeout=15)
    raw = path.read_bytes()
    pid, born = t.HEADER.unpack_from(raw)[4:6]
    result = t.parse_snapshot(raw, process_id=pid, creation=born)
    owned = result["records"][-1]
    assert owned["stage"] == "owned_return" and owned["payload_words"][2:4] == [5802955, 30]
    assert result["overwritten"] > 0 and result["ticket_drops"] > 0


def test_process_without_decode_lineage_is_explicitly_incomplete():
    memory = Memory(snapshot(rows={1: record(1, 2)}))
    result = t.ItemApplicationTraceReader(11, 22, memory).drain()
    assert result["capture_incomplete"]
    assert result["records"][0]["stage"] == "processing"
    assert result["records"][0]["decode_sequence"] == 0
    assert not result["server_acceptance_verified"]
