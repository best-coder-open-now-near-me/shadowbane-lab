import struct

import pytest

from shadowbane_lab.client_extension.targeted_action_trace import (
    CAPACITY,
    HEADER,
    RECORD,
    SIZE,
    mapping_name,
    stable_records,
)


def snapshot(sequence=1):
    data = bytearray(SIZE)
    HEADER.pack_into(data, 0, b"WBTACT1\0", 1, RECORD.size, CAPACITY, 19, 23, sequence, 0, 0, 0)
    fields = [2392387, 53, 1901199, 53, 1, 7, 0x3F800000, 0] + [0] * 8
    RECORD.pack_into(data, HEADER.size, sequence, 100, 17, 0x3625BC, *fields)
    return data


def test_original_keys_and_uninterpreted_payload():
    data = snapshot()
    record, = stable_records(data, data, 19, 23)
    assert record["actor_key"] == [2392387, 53]
    assert record["victim_key"] == [1901199, 53]
    assert record["primary_raw"] == [1, 7, 0x3F800000, 0]
    assert record["combat_authority"] is False
    assert record["stage"] == "decoded_before_queue_publication"
    assert mapping_name(19, 23).endswith(".19.23")


def test_changed_payload_and_uncommitted_slot_are_excluded():
    first = snapshot()
    second = snapshot()
    second[HEADER.size + 32] ^= 1
    assert stable_records(first, second, 19, 23) == []
    struct.pack_into("<Q", first, HEADER.size, 0)
    assert stable_records(first, first, 19, 23) == []


@pytest.mark.parametrize("offset,value", [(24, 99), (8, 2), (48, 2), (52, 1)])
def test_rejects_wrong_identity_schema_and_state(offset, value):
    data = snapshot()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError):
        stable_records(data, data, 19, 23)


def test_rejects_reserved_payload_and_foreign_caller():
    for offset in (HEADER.size + 20, HEADER.size + 24 + 12 * 4):
        data = snapshot()
        struct.pack_into("<I", data, offset, 1)
        with pytest.raises(ValueError):
            stable_records(data, data, 19, 23)


def test_wrap_discards_overwritten_old_snapshot():
    first = snapshot()
    second = snapshot()
    struct.pack_into("<q", second, 32, 257)
    assert stable_records(first, second, 19, 23) == []
