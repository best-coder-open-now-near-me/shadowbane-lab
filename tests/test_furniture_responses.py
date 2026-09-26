import struct

import pytest

from shadowbane_lab.client_extension.furniture_responses import (
    CAPACITY,
    CONSUMED_OFFSET,
    HEADER,
    KEY,
    PAYLOAD,
    RECORD,
    RECORD_SIZE,
    ROW,
    SECONDARY_OFFSET,
    SIZE,
    FurnitureResponseError,
    FurnitureResponseReader,
    parse_snapshot,
)


def fixture(sequence=3, *, stopped=0, rejected=0, drops=0):
    data = bytearray(SIZE)
    HEADER.pack_into(data, 0, b"WBFURN1\0", 1, RECORD_SIZE, CAPACITY, 7, 11,
                     sequence, max(0, sequence - CAPACITY), stopped, rejected, drops)
    for seq in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        start = HEADER.size + (seq - 1) % CAPACITY * RECORD_SIZE
        RECORD.pack_into(data, start, seq, 1000, 10, 1, seq, 5, 20, 53, 3, 0x3625BC)
        PAYLOAD.pack_into(data, start + RECORD.size,
                          2, 3, 0, 255, 100, 8, 200, 8, 0, 0,
                          0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0)
        for offset in (PAYLOAD.size, SECONDARY_OFFSET):
            ROW.pack_into(data, start + RECORD.size + offset,
                          300, 8, 400, 8, 500, 8, 1.25, -2.5, 3.75, 45.0,
                          -2147483648, 0xFFFFFFFF, 255, 0)
        KEY.pack_into(data, start + RECORD.size + CONSUMED_OFFSET, 600, 8)
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


def test_native_layout_and_diagnostic_fields_are_preserved_without_acceptance_claim():
    assert (HEADER.size, RECORD.size, PAYLOAD.size, ROW.size) == (64, 56, 96, 56)
    assert RECORD_SIZE == RECORD.size + PAYLOAD.size + 128 * ROW.size + 64 * KEY.size
    assert SIZE == HEADER.size + CAPACITY * RECORD_SIZE
    memory = Memory(fixture())
    reader = FurnitureResponseReader(7, 11, memory)
    out = reader.drain()
    body = out["records"][2]["payload"]
    assert body["building"] == (100, 8) and body["structure"] == (200, 8)
    assert body["refresh_raw"] == 255
    assert body["scene"][0] == body["secondary"][0]
    assert body["scene"][0] == {
        "asset": (300, 8), "instance": (400, 8), "auxiliary": (500, 8),
        "position_raw": (1.25, -2.5, 3.75), "rotation_raw": 45.0,
        "floor_raw": -2147483648, "word34_raw": 0xFFFFFFFF, "flag38_raw": 255,
    }
    assert body["consumed"] == [(600, 8)]
    assert out["initial_history"] and not out["server_acceptance_verified"]
    assert not out["command_admitted"] and not out["capture_incomplete"]
    assert not reader.drain()["records"]
    assert memory.calls == [("Local\\ShadowbaneLab.Extension.Furniture.v1.7.11", SIZE)] * 4


@pytest.mark.parametrize("offset,value", [
    (0, 0), (8, 2), (12, 0), (16, 31), (20, 8), (24, 12), (40, 1), (48, 2),
    (52, 0xFFFFFFFF), (60, 0xFFFFFFFF),
    (64, 0), (64 + 20, 5), (64 + 24, 0), (64 + 32, 0), (64 + 48, 7), (64 + 52, 0x362919),
])
def test_rejects_identity_corruption_and_torn_records(offset, value):
    data = fixture()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(FurnitureResponseError):
        parse(data)


@pytest.mark.parametrize("offset,value", [
    (0, 4), (4, 5), (8, 8), (12, 256), (32, 1), (40, 0x80000000), (56, 1),
    (60, 0), (64, 65), (68, 2), (72, 0), (76, 2), (80, 0), (84, 1), (88, 1), (92, 1),
    (96 + 48, 256), (96 + 52, 1), (96 + 56, 1),
    (SECONDARY_OFFSET + 48, 256), (SECONDARY_OFFSET + 52, 1),
    (SECONDARY_OFFSET + 56, 1), (CONSUMED_OFFSET + 8, 1),
])
def test_rejects_noncanonical_payload_and_unfilled_slots(offset, value):
    data = fixture()
    struct.pack_into("<I", data, HEADER.size + RECORD.size + offset, value)
    with pytest.raises(FurnitureResponseError):
        parse(data)


def test_truncated_mapping_rejected():
    with pytest.raises(FurnitureResponseError, match="size"):
        parse(fixture()[:-1])


def test_gap_is_counted_and_retained_even_after_stream_recovers():
    memory = Memory(fixture())
    reader = FurnitureResponseReader(7, 11, memory)
    reader.drain()
    memory.data = fixture(40)
    out = reader.drain()
    assert out["missed_records"] == 5 and len(out["records"]) == 32
    assert out["capture_incomplete"]
    assert reader.drain()["capture_incomplete"]


def test_initial_history_reports_already_lost_records():
    out = FurnitureResponseReader(7, 11, Memory(fixture(40))).drain()
    assert out["initial_history"] and out["missed_records"] == 8


@pytest.mark.parametrize("field", ["rejected", "drops"])
def test_native_capture_losses_make_capture_incomplete(field):
    out = FurnitureResponseReader(7, 11, Memory(fixture(**{field: 1}))).drain()
    assert out["capture_incomplete"]


def test_stopped_stream_can_drain_final_records_but_never_rebind():
    memory = Memory(fixture(stopped=1))
    reader = FurnitureResponseReader(7, 11, memory)
    assert len(reader.drain()["records"]) == 3
    memory.data = fixture(4)
    with pytest.raises(FurnitureResponseError, match="stopped"):
        reader.drain()


def test_counter_regression_permanently_stops_reader():
    memory = Memory(fixture())
    reader = FurnitureResponseReader(7, 11, memory)
    reader.drain()
    memory.data = fixture(2)
    with pytest.raises(FurnitureResponseError, match="regressed"):
        reader.drain()
    memory.data = fixture(4)
    with pytest.raises(FurnitureResponseError, match="regressed"):
        reader.drain()


def test_changed_copy_stabilizes_without_losing_records_or_marking_loss():
    memory = Memory(fixture())
    original = memory.read

    def changing(name, size):
        result = original(name, size)
        memory.data = fixture(4)
        return result

    memory.read = changing
    reader = FurnitureResponseReader(7, 11, memory)
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
    reader = FurnitureResponseReader(7, 11, memory)
    with pytest.raises(FurnitureResponseError, match="bounded read"):
        reader.drain()
    assert len(memory.calls) == 6
    memory.read = original
    out = reader.drain()
    assert len(out["records"]) == 9 and out["read_errors"] == 1
    assert out["capture_incomplete"]


@pytest.mark.parametrize("slot_sequence,overwritten", [(0, 0), (33, 0), (33, 1)])
def test_ring_wrap_publication_window_retries_before_consuming_cursor(slot_sequence, overwritten):
    memory = Memory(fixture(32))
    reader = FurnitureResponseReader(7, 11, memory)
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
    reader = FurnitureResponseReader(7, 11, memory)
    reader.drain()
    copies = iter([bytes(fixture(4)), bytes(fixture(40)), bytes(fixture(40)), bytes(fixture(40))])
    memory.read = lambda *_: next(copies)
    out = reader.drain()
    assert out["missed_records"] == 5 and out["capture_incomplete"]


def test_stable_malformed_payload_is_not_retried_or_hidden():
    memory = Memory(fixture())
    struct.pack_into("<I", memory.data, HEADER.size + RECORD.size, 99)
    reader = FurnitureResponseReader(7, 11, memory)
    with pytest.raises(FurnitureResponseError, match="payload"):
        reader.drain()
    assert len(memory.calls) == 2


@pytest.mark.parametrize("pid,creation", [(True, 11), (7, 0), (0, 11), (7, -1)])
def test_invalid_lifetime_rejected(pid, creation):
    with pytest.raises(ValueError):
        FurnitureResponseReader(pid, creation, Memory(fixture()))


def test_read_failures_are_counted_even_when_whole_capture_was_already_incomplete():
    memory = Memory(fixture(rejected=2))
    reader = FurnitureResponseReader(7, 11, memory)
    assert reader.drain()["read_errors"] == 0
    original = memory.read
    def fail(*args):
        raise OSError("lost read")
    memory.read = fail
    with pytest.raises(OSError):
        reader.drain()
    memory.read = original
    assert reader.drain()["read_errors"] == 1


def placement_fixture():
    data = fixture(1)
    start = HEADER.size + RECORD.size
    PAYLOAD.pack_into(data, start,
                      3, 5, 0, 0, 100, 8, 0, 0, 900, 8,
                      1.25, -2.5, 3.75, -90, 2147483647, 1, 1, 0, 0, 1, 1, 0, 0, 0)
    data[start + CONSUMED_OFFSET:] = bytes(SIZE - start - CONSUMED_OFFSET)
    return data


def test_operation_three_preserves_raw_placement_without_interpreting_it():
    body = parse(placement_fixture())["records"][0]["payload"]
    assert body["deed"] == (900, 8) and body["structure"] == (0, 0)
    assert body["position_raw"] == (1.25, -2.5, 3.75)
    assert body["rotation_raw"] == -90 and body["floor_raw"] == 2147483647
    assert body["consumed"] == [] and body["refresh_raw"] == 0


@pytest.mark.parametrize("offset,value", [(12, 1), (68, 1), (72, 1), (CONSUMED_OFFSET, 1)])
def test_operation_three_rejects_absent_refresh_and_consumed_fields(offset, value):
    data = placement_fixture()
    struct.pack_into("<I", data, HEADER.size + RECORD.size + offset, value)
    with pytest.raises(FurnitureResponseError):
        parse(data)


@pytest.mark.parametrize("offset", [40, 44, 48, 52, 96 + 24, SECONDARY_OFFSET + 36])
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_transform_rejected(offset, value):
    data = placement_fixture()
    struct.pack_into("<f", data, HEADER.size + RECORD.size + offset, value)
    with pytest.raises(FurnitureResponseError):
        parse(data)


def test_invalid_snapshot_is_canonical_and_marks_capture_incomplete():
    data = fixture(1)
    struct.pack_into("<I", data, HEADER.size + 48, 2)
    data[HEADER.size + RECORD.size:] = bytes(SIZE - HEADER.size - RECORD.size)
    out = FurnitureResponseReader(7, 11, Memory(data)).drain()
    assert out["records"][0]["payload"] is None and out["capture_incomplete"]
    data[HEADER.size + RECORD.size + 1] = 1
    with pytest.raises(FurnitureResponseError, match="partial"):
        parse(data)


@pytest.mark.parametrize("stage", [2, 3])
def test_exact_receive_lineage_requires_prior_decode_and_scene(stage):
    data = fixture(2)
    offset = HEADER.size + RECORD_SIZE
    RECORD.pack_into(data, offset, 2, 1001, 10, stage, 1, 5, 20, 53, 7, 0x362700)
    assert parse(data)["records"][1]["decode_sequence"] == 1
    for field, value in ((24, 2), (32, 0), (48, 5)):
        bad = bytearray(data)
        struct.pack_into("<I", bad, offset + field, value)
        with pytest.raises(FurnitureResponseError):
            parse(bad)


def test_serializing_stage_has_no_receive_lineage_or_send_authority():
    data = fixture(1)
    RECORD.pack_into(data, HEADER.size, 1, 1000, 10, 4, 0, 5, 20, 53, 3, 0x362919)
    out = FurnitureResponseReader(7, 11, Memory(data)).drain()
    assert out["records"][0]["stage"] == "serializing"
    assert out["records"][0]["decode_sequence"] == 0
    assert not out["command_admitted"] and not out["server_acceptance_verified"]
    for field, value in ((24, 1), (48, 7), (52, 0x3625BC)):
        bad = bytearray(data)
        struct.pack_into("<I", bad, HEADER.size + field, value)
        with pytest.raises(FurnitureResponseError):
            parse(bad)


@pytest.mark.parametrize(
    "reported_offset,count_offset,bit", [(60, 64, 1), (68, 72, 2), (76, 80, 4)],
)
def test_truncation_is_preserved_incomplete_and_cannot_grant_lineage(
    reported_offset, count_offset, bit,
):
    data = fixture(2)
    offset = HEADER.size + RECORD_SIZE
    start = offset + RECORD.size
    struct.pack_into("<I", data, start + 8, bit)
    struct.pack_into("<I", data, start + reported_offset, 65)
    struct.pack_into("<I", data, start + count_offset, 64)
    reader = FurnitureResponseReader(7, 11, Memory(data))
    assert reader.drain()["capture_incomplete"]
    reader.memory.data = fixture(3)
    assert reader.drain()["capture_incomplete"]
    RECORD.pack_into(data, offset, 2, 1001, 10, 2, 1, 5, 20, 53, 7, 0x362700)
    with pytest.raises(FurnitureResponseError, match="lineage"):
        parse(data)
