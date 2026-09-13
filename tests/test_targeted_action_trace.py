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


def test_v2_context_is_explicit_and_never_combat_authority():
    data = snapshot()
    data[:8] = b"WBTACT2\0"
    struct.pack_into("<I", data, 8, 2)
    struct.pack_into("<4I", data, HEADER.size + 24 + 12 * 4, 7, 1, 1901199, 53)
    record, = stable_records(data, data, 19, 23, schema=2)
    assert record["decode_scene_epoch"] == (1 << 32) + 7
    assert record["decode_local_key"] == [1901199, 53]
    assert record["combat_authority"] is False
    with pytest.raises(ValueError):
        stable_records(data, data, 19, 23)
    assert ".v2." in mapping_name(19, 23, schema=2)


@pytest.mark.parametrize("context", [(0, 0, 1, 53), (7, 0, 0, 53), (7, 0, 1, 0)])
def test_v2_rejects_partial_lifecycle_context(context):
    data = snapshot()
    data[:8] = b"WBTACT2\0"
    struct.pack_into("<I", data, 8, 2)
    struct.pack_into("<4I", data, HEADER.size + 24 + 12 * 4, *context)
    with pytest.raises(ValueError, match="lifecycle"):
        stable_records(data, data, 19, 23, schema=2)


def test_both_schemas_preserve_unbound_diagnostics():
    for schema in (1, 2):
        data = snapshot()
        data[:8] = f"WBTACT{schema}\0".encode()
        struct.pack_into("<I", data, 8, schema)
        record, = stable_records(data, data, 19, 23, schema=schema)
        assert record["decode_scene_epoch"] is None
        assert record["decode_local_key"] is None
        assert record["combat_authority"] is False


@pytest.mark.parametrize("schema", [1, 2])
@pytest.mark.parametrize("fresh", [False, True])
def test_collector_cli_selects_mapping_and_preserves_context(tmp_path, monkeypatch, schema, fresh):
    import json
    import sys

    from shadowbane_lab.client_extension import targeted_action_trace as trace

    data = snapshot()
    data[:8] = f"WBTACT{schema}\0".encode()
    struct.pack_into("<I", data, 8, schema)
    struct.pack_into("<I", data, 48, 1)  # Stopped mapping terminates without sleeps.
    if schema == 2:
        struct.pack_into("<4I", data, HEADER.size + 72, 9, 0, 1901199, 53)
    names = []

    class Memory:
        def read(self, name, size):
            names.append(name)
            assert size == SIZE
            return data

    output = tmp_path / "capture.jsonl"
    args = ["trace", "--process-id", "19", "--creation-filetime", "23",
            "--output", str(output)]
    if schema == 1:
        args += ["--schema", "1"]
    if fresh:
        args += ["--fresh-only"]
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(trace, "WindowsSharedMemorySnapshotReader", Memory)
    trace.main()
    assert names == [mapping_name(19, 23, schema=schema)] * 2
    if fresh:
        assert output.read_text() == ""
    else:
        record = json.loads(output.read_text())
        assert record["decode_scene_epoch"] == (9 if schema == 2 else None)
        assert record["combat_authority"] is False
    with pytest.raises(FileExistsError):
        trace.main()


def test_cursor_rejects_regression_between_individually_valid_pairs():
    from shadowbane_lab.client_extension.targeted_action_trace import TraceCursor

    cursor = TraceCursor(19, 23, schema=1)
    newer = snapshot()
    struct.pack_into("<q", newer, 32, 2)
    cursor.read(newer, newer)
    older = snapshot()
    with pytest.raises(ValueError, match="regressed"):
        cursor.read(older, older)
    with pytest.raises(ValueError, match="closed"):
        cursor.read(newer, newer)


def test_fresh_cursor_skips_startup_history_and_second_snapshot_publication():
    from shadowbane_lab.client_extension.targeted_action_trace import TraceCursor

    cursor = TraceCursor(19, 23, schema=1, include_history=False)
    first = snapshot()
    second = snapshot()
    struct.pack_into("<q", second, 32, 2)
    fields = RECORD.unpack_from(second, HEADER.size)[4:]
    RECORD.pack_into(second, HEADER.size + RECORD.size, 2, 101, 17, 0x3625BC, *fields)
    assert cursor.read(first, second) == []
    assert cursor.read(second, second) == []
    third = bytearray(second)
    struct.pack_into("<q", third, 32, 3)
    RECORD.pack_into(third, HEADER.size + 2 * RECORD.size, 3, 102, 17, 0x3625BC, *fields)
    event, = cursor.read(third, third)
    assert event["sequence"] == 3
    assert event["missing_before"] == 0
    assert event["combat_authority"] is False
    assert cursor.read(third, third) == []


def test_cursor_closure_and_identity_failure_cannot_be_reopened():
    from shadowbane_lab.client_extension.targeted_action_trace import TraceCursor

    for stop in (True, False):
        cursor = TraceCursor(19, 23, schema=1)
        data = snapshot()
        if stop:
            struct.pack_into("<I", data, 48, 1)
            assert len(cursor.read(data, data)) == 1
        else:
            struct.pack_into("<I", data, 24, 20)
            with pytest.raises(ValueError):
                cursor.read(data, data)
        with pytest.raises(ValueError, match="closed"):
            cursor.read(snapshot(), snapshot())


def test_cursor_reports_ring_overflow_without_replaying_old_slots():
    from shadowbane_lab.client_extension.targeted_action_trace import TraceCursor

    cursor = TraceCursor(19, 23, schema=1, include_history=False)
    first = snapshot()
    assert cursor.read(first, first) == []
    wrapped = snapshot()
    fields = RECORD.unpack_from(wrapped, HEADER.size)[4:]
    struct.pack_into("<q", wrapped, 32, 258)
    struct.pack_into("<q", wrapped, 40, 2)
    RECORD.pack_into(wrapped, HEADER.size + RECORD.size, 258, 200, 17, 0x3625BC, *fields)
    event, = cursor.read(wrapped, wrapped)
    assert event["sequence"] == 258
    assert event["missing_before"] == 256
    assert event["overwritten"] == 2
    regressed = bytearray(wrapped)
    struct.pack_into("<q", regressed, 40, 1)
    with pytest.raises(ValueError, match="regressed"):
        cursor.read(regressed, regressed)


@pytest.mark.parametrize("age,accepted", [(0, True), (50, True), (51, False)])
def test_cursor_observation_age_boundary(age, accepted):
    from shadowbane_lab.client_extension.targeted_action_trace import TraceCursor

    cursor = TraceCursor(19, 23, schema=1, max_age_ms=50)
    data = snapshot()
    result = cursor.read(data, data, now_tick_ms=100 + age)
    assert bool(result) == accepted
    assert cursor.expired_records == (0 if accepted else 1)
    assert cursor.read(data, data, now_tick_ms=200) == []


@pytest.mark.parametrize("now", [None, -1, True, 99])
def test_age_check_requires_matching_monotonic_clock_and_revokes_on_failure(now):
    from shadowbane_lab.client_extension.targeted_action_trace import TraceCursor

    cursor = TraceCursor(19, 23, schema=1, max_age_ms=50)
    data = snapshot()
    with pytest.raises(ValueError):
        cursor.read(data, data, now_tick_ms=now)
    assert cursor.closed
