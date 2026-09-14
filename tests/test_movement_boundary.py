import struct

import pytest

from shadowbane_lab.client_extension.movement_boundary import (
    CAPACITY,
    HEADER,
    INPUT_CURRENT_OFFSET,
    INPUT_EVENTS_OFFSET,
    INPUT_LOSS_OFFSET,
    INPUT_RECORD,
    RECORD,
    SIZE,
    V2_HEADER_SIZE,
    V2_SIZE,
    mapping_name,
    stable_input_records,
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


def input_snapshot(sequence=1):
    data = bytearray(V2_SIZE)
    HEADER.pack_into(data, 0, b"WBMVTR2\0", 2, RECORD.size, CAPACITY, 17, 29, 0, 0, 1)
    struct.pack_into("<Q", data, HEADER.size, sequence)

    def put(offset, value, kind=1, reason=0xFFFFFFFF, event=0):
        INPUT_RECORD.pack_into(
            data,
            offset,
            value,
            1000,
            990,
            16,
            2,
            3,
            1,
            12,
            123,
            2,
            0,
            reason,
            kind,
            9,
            9,
            0,
            255,
            193,
            event,
        )

    put(INPUT_CURRENT_OFFSET, sequence)
    put(INPUT_LOSS_OFFSET, 1, 2, 3)
    for value in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        put(INPUT_EVENTS_OFFSET + ((value - 1) % CAPACITY) * INPUT_RECORD.size, value, 3, event=44)
    return data


def test_input_layout_identity_and_legacy_compatibility():
    assert INPUT_RECORD.size == 104 and V2_HEADER_SIZE == 26888 and V2_SIZE == 45320
    assert ".v2." in mapping_name(17, 29, 2) and ".v2." not in mapping_name(17, 29, 1)
    data = input_snapshot()
    result = stable_input_records(data, data, 17, 29)
    assert result["last_owner_loss"]["stop_reason"] == "ui"
    assert result["events"][0]["key_event"] == 44
    assert result["events"][0]["keys"] == 9
    with pytest.raises(ValueError, match="identity"):
        stable_input_records(data, data, 18, 29)
    with pytest.raises(ValueError, match="schema 2"):
        stable_input_records(snapshot(), snapshot(), 17, 29)
    with pytest.raises(ValueError, match="size"):
        stable_records(snapshot(), data, 17, 29)


def test_input_loss_survives_event_overwrite_and_torn_reads_are_rejected():
    first, second = input_snapshot(400), input_snapshot(401)
    result = stable_input_records(first, second, 17, 29)
    assert result["current"] is None
    assert result["last_owner_loss"]["sequence"] == 1
    assert [event["sequence"] for event in result["events"]] == list(range(146, 401))
    second = bytearray(first)
    struct.pack_into("<Q", second, INPUT_LOSS_OFFSET, 0)
    assert stable_input_records(first, second, 17, 29)["last_owner_loss"] is None
    with pytest.raises(ValueError, match="regressed"):
        stable_input_records(input_snapshot(2), input_snapshot(1), 17, 29)


@pytest.mark.parametrize(
    "word,value", [(11, 255), (12, 4), (13, 16), (16, 4096), (17, 512), (18, 255)]
)
def test_invalid_input_record_is_not_evidence(word, value):
    data = input_snapshot()
    values = list(INPUT_RECORD.unpack_from(data, INPUT_EVENTS_OFFSET))
    values[word] = value
    INPUT_RECORD.pack_into(data, INPUT_EVENTS_OFFSET, *values)
    assert stable_input_records(data, data, 17, 29)["events"] == []


def test_native_input_publisher_reader_interoperability(tmp_path):
    import os
    import subprocess

    executable = os.environ.get("WONDERBANE_MOVEMENT_BOUNDARY_TEST")
    if not executable:
        pytest.skip("requires native movement-boundary regression executable")
    output = tmp_path / "native-input-trace.bin"
    subprocess.run([executable, "input-diagnostics", str(output)], check=True, timeout=15)
    data = output.read_bytes()
    header = HEADER.unpack_from(data)
    result = stable_input_records(data, data, header[4], header[5])
    assert result["last_owner_loss"]["stop_reason"] == "ui"
    assert result["last_owner_loss"]["keys"] == 9
    assert len(result["events"]) == CAPACITY
    assert result["current"]["owner"] == 0


def lifetime_snapshot():
    from shadowbane_lab.client_extension.movement_boundary import (
        LIFETIME_CURRENT_OFFSET,
        LIFETIME_EVENTS_OFFSET,
        LIFETIME_FIRST_OFFSET,
        LIFETIME_RECORD,
        V3_SIZE,
    )

    data = bytearray(V3_SIZE)
    data[:V2_SIZE] = input_snapshot()
    HEADER.pack_into(data, 0, b"WBMVTR3\0", 3, RECORD.size, CAPACITY, 17, 29, 0, 0, 1)
    struct.pack_into("<QQ", data, V2_SIZE, 1000, 2)
    origin = (1, 900, 1, 2, 1, 1, 6, 0, 0, 0, 0, 1, 1, 12)
    current = (2, 990, 2, 3, 3, 3, 12, 2, 0, 0, 63, 0, 0, 12)
    LIFETIME_RECORD.pack_into(data, LIFETIME_FIRST_OFFSET, *origin)
    LIFETIME_RECORD.pack_into(data, LIFETIME_CURRENT_OFFSET, *current)
    LIFETIME_RECORD.pack_into(data, LIFETIME_EVENTS_OFFSET, *origin)
    LIFETIME_RECORD.pack_into(data, LIFETIME_EVENTS_OFFSET + LIFETIME_RECORD.size, *current)
    return data


def test_lifetime_schema_freshness_and_retained_origin():
    from shadowbane_lab.client_extension.movement_boundary import (
        LIFETIME_RECORD,
        V3_SIZE,
        stable_lifetime_records,
    )

    assert LIFETIME_RECORD.size == 80 and V3_SIZE == 50616
    assert ".v3." in mapping_name(17, 29, 3)
    data = lifetime_snapshot()
    result = stable_lifetime_records(data, data, 17, 29)
    assert result["current"]["cause_name"] == "rearmed"
    assert result["current"]["retained"] is False
    assert result["first_invalidation"]["cause_name"] == "reference_notice"
    assert result["first_invalidation"]["retained"] is True
    assert result["first_invalidation"]["age_ms"] == 100
    assert stable_input_records(data, data, 17, 29)["last_owner_loss"]["stop_reason"] == "ui"
    with pytest.raises(ValueError, match="identity"):
        stable_lifetime_records(data, data, 18, 29)
    with pytest.raises(ValueError, match="schema 3"):
        stable_lifetime_records(input_snapshot(), input_snapshot(), 17, 29)
    for old in (snapshot(), input_snapshot()):
        stable_records(old, old, 17, 29)


def test_lifetime_torn_regressed_or_invalid_records_rejected():
    from shadowbane_lab.client_extension.movement_boundary import (
        LIFETIME_FIRST_OFFSET,
        LIFETIME_RECORD,
        stable_lifetime_records,
    )

    data = lifetime_snapshot()
    torn = bytearray(data)
    struct.pack_into("<Q", torn, LIFETIME_FIRST_OFFSET, 0)
    assert stable_lifetime_records(data, torn, 17, 29)["first_invalidation"] is None
    for word, invalid in ((6, 13), (7, 3), (8, 15), (9, 64), (10, 64), (11, 8)):
        malformed = bytearray(data)
        record = list(LIFETIME_RECORD.unpack_from(malformed, LIFETIME_FIRST_OFFSET))
        record[word] = invalid
        LIFETIME_RECORD.pack_into(malformed, LIFETIME_FIRST_OFFSET, *record)
        assert stable_lifetime_records(malformed, malformed, 17, 29)["first_invalidation"] is None
    regressed = bytearray(data)
    struct.pack_into("<Q", regressed, V2_SIZE + 8, 1)
    with pytest.raises(ValueError, match="regressed"):
        stable_lifetime_records(data, regressed, 17, 29)


def test_native_lifetime_publisher_reader_interoperability(tmp_path):
    import os
    import subprocess

    from shadowbane_lab.client_extension.movement_boundary import stable_lifetime_records

    executable = os.environ.get("WONDERBANE_MOVEMENT_BOUNDARY_TEST")
    if not executable:
        pytest.skip("requires native movement-boundary regression executable")
    output = tmp_path / "native-lifetime-trace.bin"
    subprocess.run([executable, "lifetime-diagnostics", str(output)], check=True, timeout=15)
    data = output.read_bytes()
    header = HEADER.unpack_from(data)
    result = stable_lifetime_records(data, data, header[4], header[5])
    assert result["first_invalidation"]["cause_name"] == "reference_notice"
    assert result["first_invalidation"]["notice_role"] == 1
    assert result["first_invalidation"]["finalizer_flags"] == 1
    assert result["first_invalidation"]["sequence"] == 1
    assert result["first_invalidation"]["retained"] is True
    assert result["current"]["sequence"] == 200
    assert len(result["events"]) == 64
