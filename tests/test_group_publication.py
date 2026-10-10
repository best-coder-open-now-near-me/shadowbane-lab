import os
import struct
import subprocess
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.group_publication import (
    CAPACITY,
    CONTEXT,
    HEADER,
    LAYOUTS,
    RECORD,
    ROW,
    GroupPublicationError,
    GroupPublicationReader,
    parse_snapshot,
)


def frame(kind="messages", seq=3):
    magic, _, size = LAYOUTS[kind]
    data = bytearray(64 + CAPACITY * size)
    HEADER.pack_into(data, 0, magic, 1, size, CAPACITY, 55, 66, seq,
                     max(0, seq - CAPACITY), 0, 0, 0)
    words = [0x315047, 0x10000, 0x20000, 0x30000, 1,
             0x40000, 0x50000, 123, 53, 0x15] + [0] * 45
    for n in range(max(1, seq - CAPACITY + 1), seq + 1):
        stage = (n - 1) % 3 + 1
        offset = 64 + (n - 1) % CAPACITY * size
        decode = n if stage == 1 else n - stage + 1
        generation = 0 if stage == 1 else n if stage == 2 else n - 1
        flags = 3 if stage == 1 else 15
        RECORD.pack_into(data, offset, n, 1000, 1, stage, decode, generation,
                         7, 42, 53, flags, 0)
        payload = offset + 64
        CONTEXT.pack_into(data, payload, *(words if flags == 15 else [0] * 55),
                          *((123, 53) if kind == "messages" and flags == 15 else (0, 0)), 0)
        if kind == "messages":
            struct.pack_into("<4I", data, payload + 232, 14, 5, 5, 0)
            data[payload + 248:payload + 258] = "Alice".encode("utf-16-le")
            data[payload + 440:payload + 450] = "/come".encode("utf-16-le")
        else:
            struct.pack_into("<2I", data, payload + 232, 5, 1)
            ROW.pack_into(data, payload + 240, 123, 53, 70000, 100, -50000, 0)
    return bytes(data)


@pytest.mark.parametrize("kind", ["messages", "updates"])
def test_strict_layout_and_qualified_context(kind):
    result = parse_snapshot(frame(kind), process_id=55, creation=66, kind=kind)
    assert result["records"][-1]["flags"] == 15
    assert result["records"][-1]["payload"]["group_digest"]
    with pytest.raises(GroupPublicationError):
        parse_snapshot(frame(kind), process_id=55, creation=67, kind=kind)


@pytest.mark.parametrize("offset,value", [(64 + 2 * 760 + 64 + 228, 1),
                                         (64 + 2 * 760 + 56, 16),
                                         (64 + 2 * 760 + 64 + 4 * 4, 11)])
def test_partial_or_unknown_fields_rejected(offset, value):
    data = bytearray(frame())
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(GroupPublicationError):
        parse_snapshot(data, process_id=55, creation=66, kind="messages")


def test_reader_marks_history_gap_and_never_rewinds():
    class Memory:
        data = frame()
        def read(self, name, size):
            return self.data
    memory = Memory()
    reader = GroupPublicationReader(55, 66, memory, kind="messages")
    assert reader.drain()["initial_history"]
    assert not reader.drain()["records"]
    memory.data = frame(seq=39)
    assert reader.drain()["gap"]
    memory.data = frame()
    with pytest.raises(GroupPublicationError, match="regressed"):
        reader.drain()


def _real_frame(tmp_path, kind, variable):
    exe = os.environ.get(variable)
    if not exe:
        pytest.skip("actual native group fixture not configured")
    assert Path(exe).is_file()
    target = tmp_path / (kind + ".bin")
    subprocess.run([exe, str(target)], check=True, timeout=30, capture_output=True)
    data = target.read_bytes()
    pid = struct.unpack_from("<I", data, 20)[0]
    result = parse_snapshot(data, process_id=pid, creation=123456789, kind=kind)
    record = result["records"][-1]
    assert record["flags"] == 15
    assert record["stage"] == 3
    assert record["payload"]["group_digest"]
    return record["payload"]


def test_group_message_native_frame_roundtrip(tmp_path):
    payload = _real_frame(tmp_path, "messages", "WONDERBANE_GROUP_MESSAGES_TEST_EXE")
    assert payload["sender"] == "Alice"
    assert payload["sender_key"] == (123, 53)
    assert payload["text"] == "/come"


def test_group_update_native_frame_roundtrip(tmp_path):
    payload = _real_frame(tmp_path, "updates", "WONDERBANE_GROUP_UPDATES_TEST_EXE")
    assert payload["kind"] == 5
    assert payload["positions"] == [{"key": (123, 53), "xyz": (70000., 100., -50000.)}]
