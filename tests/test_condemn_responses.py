import struct

import pytest

from shadowbane_lab.client_extension.condemn_responses import (
    CAPACITY,
    HEADER,
    PAYLOAD,
    RECORD,
    RECORD_SIZE,
    ROW,
    SIZE,
    CondemnResponseError,
    CondemnResponseReader,
    parse_snapshot,
)


def fixture(sequence=3, *, stopped=0, rejected=0, drops=0):
    data = bytearray(SIZE)
    HEADER.pack_into(data, 0, b"WBKOS1\0\0", 1, RECORD_SIZE, CAPACITY, 7, 11,
                     sequence, max(0, sequence - CAPACITY), stopped, rejected, drops)
    for seq in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        start = HEADER.size + (seq - 1) % CAPACITY * RECORD_SIZE
        RECORD.pack_into(data, start, seq, 1000, 10, 1, seq, 5, 20, 53, 3, 0x3625BC)
        PAYLOAD.pack_into(data, start + RECORD.size,
                          13, 0, 0, 1, 100, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 999, 1)
        ROW.pack_into(data, start + RECORD.size + PAYLOAD.size,
                      5, 200, 23, 0, 0, 0, 0, 200, 23, 0x10000)
    return data


class Memory:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def read(self, name, size):
        self.calls.append((name, size))
        return bytes(self.data)


def parse(data):
    return parse_snapshot(data, process_id=7, creation=11)


def test_native_layout_and_absent_scope_are_preserved_without_acceptance_claim():
    memory = Memory(fixture())
    reader = CondemnResponseReader(7, 11, memory)
    out = reader.drain()
    body = out["records"][2]["payload"]
    assert body["scope_raw"] == 0
    assert body["rows"][0]["nation"] == (200, 23)
    assert body["rows"][0]["guild"] == (0, 0)
    assert body["reported_count_raw"] == 999
    assert out["initial_history"] and not out["server_acceptance_verified"]
    assert not out["command_admitted"]
    assert not reader.drain()["records"]
    assert memory.calls == [("Local\\ShadowbaneLab.Extension.Condemn.v1.7.11", SIZE)] * 4


@pytest.mark.parametrize("offset,value", [
    (0, 0), (8, 2), (12, 0), (16, 31), (20, 8), (24, 12), (40, 1), (48, 2),
    (52, 0xFFFFFFFF), (60, 0xFFFFFFFF),
    (64, 0), (64 + 20, 4), (64 + 24, 0), (64 + 32, 0), (64 + 48, 7),
    (64 + 56, 23), (64 + 56 + 8, 5), (64 + 56 + 12, 3),
    (64 + 56 + 32, 123), (64 + 56 + 56, 2), (64 + 56 + 68, 513),
    (64 + 56 + 72 + 36, 0xFF000000), (64 + 56 + 72 + 40, 1),
])
def test_rejects_identity_corruption_torn_records_and_stale_payload(offset, value):
    data = fixture()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(CondemnResponseError):
        parse(data)


def test_truncated_mapping_rejected():
    with pytest.raises(CondemnResponseError, match="size"):
        parse(fixture()[:-1])


def test_gap_is_counted_and_retained_even_after_stream_recovers():
    memory = Memory(fixture())
    reader = CondemnResponseReader(7, 11, memory)
    reader.drain()
    memory.data = fixture(40)
    out = reader.drain()
    assert out["missed_records"] == 5 and len(out["records"]) == 32
    assert out["capture_incomplete"]
    assert reader.drain()["capture_incomplete"]


def test_initial_history_reports_already_lost_records():
    out = CondemnResponseReader(7, 11, Memory(fixture(40))).drain()
    assert out["initial_history"] and out["missed_records"] == 8


@pytest.mark.parametrize("field", ["rejected", "drops"])
def test_native_capture_losses_make_capture_incomplete(field):
    out = CondemnResponseReader(7, 11, Memory(fixture(**{field: 1}))).drain()
    assert out["capture_incomplete"]


def test_stopped_stream_can_drain_final_records_but_never_rebind():
    memory = Memory(fixture(stopped=1))
    reader = CondemnResponseReader(7, 11, memory)
    assert len(reader.drain()["records"]) == 3
    memory.data = fixture(4)
    with pytest.raises(CondemnResponseError, match="stopped"):
        reader.drain()


def test_counter_regression_permanently_stops_reader():
    memory = Memory(fixture())
    reader = CondemnResponseReader(7, 11, memory)
    reader.drain()
    memory.data = fixture(2)
    with pytest.raises(CondemnResponseError, match="regressed"):
        reader.drain()
    memory.data = fixture(4)
    with pytest.raises(CondemnResponseError, match="regressed"):
        reader.drain()


def test_changed_copy_stabilizes_without_losing_records_or_marking_loss():
    memory = Memory(fixture())
    original = memory.read

    def changing(name, size):
        result = original(name, size)
        memory.data = fixture(4)
        return result

    memory.read = changing
    reader = CondemnResponseReader(7, 11, memory)
    out = reader.drain()
    assert len(out["records"]) == 4 and not out["capture_incomplete"]
    assert out["read_errors"] == 0 and len(memory.calls) == 4
    assert not reader.drain()["records"]


def test_continuously_changing_copy_is_bounded_and_does_not_consume_cursor():
    memory = Memory(fixture())
    original = memory.read
    sequence = 3

    def changing(name, size):
        nonlocal sequence
        result = original(name, size)
        sequence += 1
        memory.data = fixture(sequence)
        return result

    memory.read = changing
    reader = CondemnResponseReader(7, 11, memory)
    with pytest.raises(CondemnResponseError, match="bounded read"):
        reader.drain()
    assert len(memory.calls) == 6
    memory.read = original
    out = reader.drain()
    assert len(out["records"]) == 9 and out["read_errors"] == 1
    assert out["capture_incomplete"]


@pytest.mark.parametrize("slot_sequence,overwritten", [(0, 0), (33, 0), (33, 1)])
def test_ring_wrap_publication_window_retries_before_consuming_cursor(slot_sequence, overwritten):
    memory = Memory(fixture(32))
    reader = CondemnResponseReader(7, 11, memory)
    reader.drain()
    publishing = fixture(32)
    struct.pack_into("<Q", publishing, HEADER.size, slot_sequence)
    struct.pack_into("<q", publishing, 40, overwritten)
    copies = iter([bytes(publishing), bytes(publishing), bytes(fixture(33)), bytes(fixture(33))])
    memory.read = lambda *_: next(copies)
    out = reader.drain()
    assert [r["sequence"] for r in out["records"]] == [33]
    assert not out["capture_incomplete"] and out["read_errors"] == 0


def test_stabilization_still_reports_records_lost_while_reading():
    memory = Memory(fixture())
    reader = CondemnResponseReader(7, 11, memory)
    reader.drain()
    copies = iter([bytes(fixture(4)), bytes(fixture(40)), bytes(fixture(40)), bytes(fixture(40))])
    memory.read = lambda *_: next(copies)
    out = reader.drain()
    assert out["missed_records"] == 5 and out["capture_incomplete"]


def test_stable_malformed_payload_is_not_retried_or_hidden():
    memory = Memory(fixture())
    struct.pack_into("<I", memory.data, HEADER.size + RECORD.size, 99)
    reader = CondemnResponseReader(7, 11, memory)
    with pytest.raises(CondemnResponseError, match="payload"):
        reader.drain()
    assert len(memory.calls) == 2


@pytest.mark.parametrize("pid,creation", [(True, 11), (7, 0), (0, 11), (7, -1)])
def test_invalid_lifetime_rejected(pid, creation):
    with pytest.raises(ValueError):
        CondemnResponseReader(pid, creation, Memory(fixture()))


def test_read_failures_are_counted_even_when_whole_capture_was_already_incomplete():
    memory = Memory(fixture(rejected=2))
    reader = CondemnResponseReader(7, 11, memory)
    assert reader.drain()["read_errors"] == 0
    original = memory.read
    def fail(*args):
        raise OSError("lost read")
    memory.read = fail
    with pytest.raises(OSError):
        reader.drain()
    memory.read = original
    assert reader.drain()["read_errors"] == 1
