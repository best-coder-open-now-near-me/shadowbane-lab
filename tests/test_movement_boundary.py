import struct

import pytest

from shadowbane_lab.client_extension.movement_boundary import (
    CAPACITY,
    HEADER,
    RECORD,
    SIZE,
    mapping_name,
    stable_records,
)


def snapshot(sequence=1, pid=17, creation=29):
    data = bytearray(SIZE)
    HEADER.pack_into(data, 0, b"WBMVTR1\0", 1, RECORD.size, CAPACITY, pid, creation, sequence, 0, 1)
    for value in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        RECORD.pack_into(
            data,
            HEADER.size + ((value - 1) % CAPACITY) * RECORD.size,
            value,
            value * 16,
            0.016,
            12,
            12,
            pid,
            123,
            456,
            2,
            0,
            0,
            3,
            5,
            789,
            1,
        )
    return data


def test_native_layout_and_exact_identity():
    assert HEADER.size == 48 and RECORD.size == 72
    assert mapping_name(17, 29).endswith(".17.29")
    data = snapshot()
    assert stable_records(data, data, 17, 29)[0]["movement_state"] == 5
    with pytest.raises(ValueError, match="identity"):
        stable_records(data, data, 18, 29)
    with pytest.raises(ValueError, match="identity"):
        stable_records(data, data, 17, 30)
    with pytest.raises(ValueError, match="size"):
        stable_records(data[:-1], data, 17, 29)


def test_in_flight_slot_rejected_and_ring_overwrite_bounded():
    first, second = snapshot(256), snapshot(257)
    records = stable_records(first, second, 17, 29)
    assert [r["sequence"] for r in records] == list(range(2, 257))
    second = snapshot(256)
    struct.pack_into("<Q", second, HEADER.size, 0)
    assert len(stable_records(first, second, 17, 29)) == 255
    second = snapshot(256)
    struct.pack_into("<I", second, HEADER.size + 24, 99)
    assert len(stable_records(first, second, 17, 29)) == 255
    with pytest.raises(ValueError, match="regressed"):
        stable_records(snapshot(2), snapshot(1), 17, 29)


def test_invalid_delta_is_not_evidence():
    data = snapshot()
    struct.pack_into("<d", data, HEADER.size + 16, float("nan"))
    assert stable_records(data, data, 17, 29) == []
