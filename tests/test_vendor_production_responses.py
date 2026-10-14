import struct
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.vendor_production_responses import (
    CAPACITY,
    HEADER,
    PAYLOAD,
    RECORD,
    RECORD_SIZE,
    SIZE,
    VendorProductionError,
    VendorProductionReader,
    parse_snapshot,
)


def fixture(sequence=3, *, stopped=0, rejected=0, drops=0):
    data = bytearray(SIZE)
    HEADER.pack_into(data, 0, b"WBPRD2\0\0", 2, RECORD_SIZE, CAPACITY, 7, 11,
                     sequence, max(0, sequence - CAPACITY), stopped, rejected, drops)
    for seq in range(max(1, sequence - CAPACITY + 1), sequence + 1):
        offset = HEADER.size + (seq - 1) % CAPACITY * RECORD_SIZE
        RECORD.pack_into(data, offset, seq, 1000, 10, 1, seq, 5, 20, 53, 3, 0x3625BC)
        PAYLOAD.pack_into(data, offset + RECORD.size, 8, 0, 1, 123, 8, 456, 42,
                          26990, 0, 10, 0, 0, 0, 789, 40, 26990, 10, 166,
                          300, 336, 1, 0, 0, 0, 0, 0, 0, 0)
    return data


class Memory:
    def __init__(self, data):
        self.data = data

    def read(self, name, size):
        assert name == "Local\\ShadowbaneLab.Extension.VendorProduction.v2.7.11"
        assert size == SIZE
        return bytes(self.data)


def test_cpp_layout_and_received_quantity_are_preserved():
    prefix = bytes.fromhex((Path(__file__).parent / "fixtures" /
                            "native_vendor_production_v2.hex").read_text().strip())
    assert len(prefix) == HEADER.size + 3 * RECORD_SIZE
    snapshot = parse_snapshot(prefix + bytes(SIZE - len(prefix)), process_id=7, creation=11)
    received = snapshot["records"][2]
    assert received["stage"] == "returned" and received["flags"] == 7
    assert received["decode_sequence"] == 1 and received["scene_epoch"] == 7
    assert received["payload"]["item"] == (4294925624, 40)
    assert received["payload"]["remaining_count_raw"] == 10


def test_old_mislabeled_protocol_is_preserved_but_cannot_be_used_as_v2_evidence():
    prefix = bytes.fromhex((Path(__file__).parent / "fixtures" /
                            "native_vendor_production_v1.hex").read_text().strip())
    with pytest.raises(VendorProductionError, match="identity or layout"):
        parse_snapshot(prefix + bytes(SIZE - len(prefix)), process_id=7, creation=11)


@pytest.mark.parametrize("offset,value", [
    (0, 0), (8, 1), (12, 0), (16, 32), (20, 8), (24, 12), (40, 1), (48, 2),
    (64, 0), (64 + 20, 4), (64 + 24, 0), (64 + 32, 0), (64 + 48, 7),
    (64 + 56, 12), (64 + 56 + 8, 16), (64 + 56 + 8, 0),
    (64 + 56 + 14 * 4, 0), (64 + 56 + 20 * 4, 0),
    (64 + 56 + 21 * 4, 1), (64 + 56 + 22 * 4, 123),
    (64 + 56 + 26 * 4, 100), (64 + 56 + 27 * 4, 1),
])
def test_rejects_foreign_identity_torn_records_and_noncanonical_bodies(offset, value):
    data = fixture()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(VendorProductionError):
        parse_snapshot(data, process_id=7, creation=11)


def test_new_job_bookmark_labels_prior_history_without_claiming_it():
    memory = Memory(fixture(1000, rejected=2, drops=3))
    reader = VendorProductionReader(7, 11, memory)
    with pytest.raises(VendorProductionError, match="bookmark"):
        reader.drain()
    initial = reader.bookmark()
    assert initial["history_discarded"] == CAPACITY and initial["history_missing"] == 744
    assert initial["cursor"]["sequence"] == 1000 and not initial["command_admitted"]
    memory.data = fixture(1003, rejected=2, drops=3)
    result = reader.drain()
    assert [r["sequence"] for r in result["records"]] == [1001, 1002, 1003]
    assert not result["capture_incomplete"] and not result["server_acceptance_verified"]
    with pytest.raises(VendorProductionError, match="cannot be reset"):
        reader.bookmark()


@pytest.mark.parametrize("change", ["gap", "rejection", "ticket"])
def test_loss_after_create_bookmark_is_sticky_across_restart(change):
    memory = Memory(fixture())
    reader = VendorProductionReader(7, 11, memory)
    reader.bookmark()
    memory.data = fixture(1000 if change == "gap" else 6,
                          rejected=int(change == "rejection"), drops=int(change == "ticket"))
    result = reader.drain()
    assert result["capture_incomplete"]
    restored = VendorProductionReader(7, 11, memory, resume_cursor=result["cursor"])
    assert restored.drain()["capture_incomplete"] and not restored.drain()["records"]
    with pytest.raises(VendorProductionError, match="cannot be reset"):
        restored.bookmark()


def test_saved_cursor_only_drains_unseen_records_in_same_lifetime():
    memory = Memory(fixture())
    first = VendorProductionReader(7, 11, memory)
    first.bookmark()
    memory.data = fixture(6)
    restored = VendorProductionReader(7, 11, memory, resume_cursor=first.cursor)
    result = restored.drain()
    assert [r["sequence"] for r in result["records"]] == [4, 5, 6]
    bad = dict(result["cursor"], creation=12)
    with pytest.raises(ValueError):
        VendorProductionReader(7, 11, memory, resume_cursor=bad)


@pytest.mark.parametrize("mode", ["regression", "stopped"])
def test_closed_or_regressed_stream_cannot_rebind(mode):
    memory = Memory(fixture())
    reader = VendorProductionReader(7, 11, memory)
    reader.bookmark()
    memory.data = fixture(2) if mode == "regression" else fixture(stopped=1)
    with pytest.raises(VendorProductionError, match="cannot rebind"):
        reader.drain()
    memory.data = fixture(6)
    with pytest.raises(VendorProductionError, match="cannot rebind"):
        reader.drain()


def test_read_failure_is_preserved_in_saved_cursor(tmp_path):
    memory = Memory(fixture())
    reader = VendorProductionReader(7, 11, memory)
    reader.bookmark()
    memory.data = fixture()[:-1]
    with pytest.raises(VendorProductionError, match="size"):
        reader.drain()
    assert reader.cursor["capture_incomplete"] and reader.cursor["read_errors"] == 1
    memory.data = fixture(6)
    restored = VendorProductionReader(7, 11, memory, resume_cursor=reader.cursor)
    assert restored.drain()["capture_incomplete"]
