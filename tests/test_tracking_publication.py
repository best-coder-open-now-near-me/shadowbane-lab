import struct

import pytest

from shadowbane_lab.client_extension.tracking_publication import (
    CAPACITY,
    HEADER,
    PAYLOAD,
    RECORD,
    RECORD_SIZE,
    ROW,
    SIZE,
    TrackingResponseError,
    TrackingResponseReader,
    parse_snapshot,
)


def fixture(sequence=3, *, count=1, stopped=0, rejected=0, drops=0):
    data = bytearray(SIZE)
    HEADER.pack_into(data, 0, b"WBTRK1\0\0", 1, RECORD_SIZE, CAPACITY, 7, 11,
                     sequence, max(0, sequence - CAPACITY), stopped, rejected, drops)
    for seq in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        start = HEADER.size + (seq - 1) % CAPACITY * RECORD_SIZE
        stage = (seq - 1) % 3 + 1
        decode = seq - stage + 1
        generation = 0 if stage == 1 else decode + 1
        RECORD.pack_into(data, start, seq, 1000 + seq, 10, stage, decode, generation,
                         5, 20, 53, 3 if stage == 1 else 7, 0x3625BC)
        PAYLOAD.pack_into(data, start + RECORD.size, 429578587, count)
        if count:
            ROW.pack_into(data, start + RECORD.size + PAYLOAD.size,
                          200, 53, 6, 1, "Praeda".encode("utf-16-le"))
    return data


class Memory:
    def __init__(self, data):
        self.data = data

    def read(self, name, size):
        assert name == "Local\\ShadowbaneLab.Extension.Tracking.v1.7.11"
        assert size == SIZE
        return bytes(self.data)


def parse(data):
    return parse_snapshot(data, process_id=7, creation=11)


def test_native_wire_layout_copied_rows_and_monotonic_identical_empty_responses():
    assert HEADER.size == RECORD.size == 64 and ROW.size == 208
    memory = Memory(fixture())
    reader = TrackingResponseReader(7, 11, memory)
    first = reader.drain()
    record = first["records"][-1]
    assert record["stage"] == "returned" and record["processing_generation"] == 2
    assert record["payload"] == {"power_id": 429578587, "contacts": [
        {"object_key": (200, 53), "name": "Praeda", "flags_raw": 1},
    ]}
    assert first["initial_history"] and not first["query_correlation_verified"]
    assert not first["server_character_session_verified"]
    assert not reader.drain()["records"]
    memory.data = fixture(6)
    identical = reader.drain()
    assert not identical["initial_history"]
    assert identical["records"][-1]["processing_generation"] == 5
    memory.data = fixture(9, count=0)
    empty = reader.drain()["records"][-1]
    assert empty["processing_generation"] == 8
    assert empty["payload"] == {"power_id": 429578587, "contacts": []}


@pytest.mark.parametrize("offset,value", [
    (0, 0), (8, 2), (12, 0), (16, 32), (20, 8), (24, 12),
    (40, 1), (48, 2), (52, 0xFFFFFFFF), (60, 0xFFFFFFFF),
    (64, 0), (64 + 20, 4), (64 + 24, 0), (64 + 32, 1),
    (64 + 40, 0), (64 + 56, 8), (128, 0), (132, 257),
    (136 + 8, 97), (136 + 12, 256),
])
def test_corrupt_layout_metadata_and_payload_rejected(offset, value):
    data = fixture()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(TrackingResponseError):
        parse(data)


@pytest.mark.parametrize("change", ["surrogate", "padding", "duplicate", "partial", "null"])
def test_no_truncated_or_partial_names_or_duplicate_contacts(change):
    data = fixture()
    at = HEADER.size + RECORD.size
    if change == "null":
        struct.pack_into("<II", data, at + PAYLOAD.size, 0, 0)
    elif change == "surrogate":
        struct.pack_into("<H", data, at + PAYLOAD.size + 16, 0xD800)
    elif change == "padding":
        data[at + PAYLOAD.size + 16 + 12] = 1
    elif change == "duplicate":
        struct.pack_into("<I", data, at + 4, 2)
        data[at + PAYLOAD.size + ROW.size:at + PAYLOAD.size + 2 * ROW.size] = (
            data[at + PAYLOAD.size:at + PAYLOAD.size + ROW.size]
        )
    else:
        struct.pack_into("<I", data, HEADER.size + 56, 2)
    with pytest.raises(TrackingResponseError):
        parse(data)


def test_gap_is_reported_but_later_complete_response_is_preserved():
    memory = Memory(fixture())
    reader = TrackingResponseReader(7, 11, memory)
    reader.drain()
    memory.data = fixture(15)
    result = reader.drain()
    assert result["missed_records"] == 4 and result["capture_incomplete"]
    assert result["records"][-1]["processing_generation"] == 14
    assert result["records"][-1]["flags"] == 7
    memory.data = fixture(16, stopped=1)
    assert reader.drain()["stopped"]
    with pytest.raises(TrackingResponseError, match="stopped"):
        reader.drain()


def test_cross_scene_return_is_unqualified_and_counter_regression_terminal():
    data = fixture()
    at = HEADER.size + 2 * RECORD_SIZE
    struct.pack_into("<Q", data, at + 24, 0)
    struct.pack_into("<Q", data, at + 40, 0)
    struct.pack_into("<III", data, at + 48, 0, 0, 1)
    assert parse(data)["records"][-1]["flags"] == 1
    memory = Memory(data)
    reader = TrackingResponseReader(7, 11, memory)
    reader.drain()
    memory.data = fixture(0)
    with pytest.raises(TrackingResponseError, match="regressed"):
        reader.drain()


def test_incomplete_publication_retries_without_advancing_cursor():
    memory = Memory(fixture(9))
    reader = TrackingResponseReader(7, 11, memory)
    reader.drain()
    next_slot = HEADER.size + (9 % CAPACITY) * RECORD_SIZE
    struct.pack_into("<Q", memory.data, next_slot, 0)
    with pytest.raises(TrackingResponseError, match="changed"):
        reader.drain()
    memory.data = fixture(12)
    out = reader.drain()
    assert [r["sequence"] for r in out["records"]] == [10, 11, 12]
    assert out["read_errors"] == 1


def test_real_native_tracking_frame_roundtrip(tmp_path):
    import os
    import subprocess

    executable = os.environ.get("WONDERBANE_TRACKING_RESPONSES_TEST_EXE")
    if not executable:
        pytest.skip("requires actual x86 native publication fixture")
    output = tmp_path / "native-frame.bin"
    result = subprocess.run([executable, "dump", str(output)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    data = output.read_bytes()
    pid = HEADER.unpack_from(data)[4]
    parsed = parse_snapshot(data, process_id=pid, creation=123456789)
    assert parsed["sequence"] == 3 and parsed["rejected"] == 0
    last = parsed["records"][-1]
    assert last["processing_generation"] == 2 and last["decode_sequence"] == 1
    assert last["flags"] == 7 and last["scene_epoch"] == 7 and last["local"] == (42, 53)
    assert last["payload"] == {"power_id": 429578587, "contacts": [
        {"object_key": (42, 53), "name": "Test", "flags_raw": 1},
    ]}


def test_nested_returns_preserve_entry_generation_not_return_order():
    data = fixture(6)
    # Process A entered at 2; B at 5 and returned first. A then returns at 6.
    for seq, generation in ((5, 4), (6, 2)):
        offset = HEADER.size + (seq - 1) * RECORD_SIZE
        RECORD.pack_into(data, offset, seq, 1000 + seq, 10, 3, 1, generation,
                         5, 20, 53, 7, 0x3625BC)
    records = parse(data)["records"][-2:]
    assert [r["processing_generation"] for r in records] == [4, 2]
    assert max(records, key=lambda r: r["processing_generation"])["sequence"] == 5
