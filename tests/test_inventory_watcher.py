import importlib.util
import struct
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "inventory_watcher", Path(__file__).parents[1] / "scripts/watch-wonderbane-inventory.py"
)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


class Memory:
    base_address = 0x400000
    pointer_size = 4
    executable_sha256 = watcher.PREPARED_14

    def __init__(self):
        self.data = {}

    def put(self, at, *words):
        self.data[at] = struct.pack("<" + "I" * len(words), *words)

    def read_block(self, at, size):
        return self.data[at][:size]


def fixture():
    m = Memory()
    m.put(m.base_address + 0x16A2D98, 0x200000)
    m.put(0x200000, m.base_address + 0x114165C)
    m.put(0x200008, m.base_address + 0x11417D4)
    m.put(0x200018, 123, 53)
    for offset, table, head in ((0x688, 0x11415E4, 0x300000), (0x6F0, 0x11415CC, 0x310000)):
        m.put(0x200000 + offset, m.base_address + table)
        m.put(0x200000 + offset + 0x44, head)
        m.put(head + 4, 0, head, head)
    m.put(0x300004, 0x320000, 0x320000, 0x320000)
    m.put(0x320004, 0x300000, 0, 0, 400, 40, 0x330000)
    m.put(0x330000, m.base_address + 0x1142748)
    m.put(0x330018, 400, 40)
    m.put(0x330010, 980066, 0)
    m.put(0x330744, 10)
    return m


def test_reads_actor_owned_item_without_hud():
    items = watcher.inventory_snapshot(fixture(), (123, 53))
    assert items[0]["item_key"] == [400, 40]
    assert items[0]["template_key"] == [980066, 0]
    assert items[0]["quantity_raw"] == 10


@pytest.mark.parametrize("at,words", [
    (0x320004, (0x300000, 0x320000, 0, 400, 40, 0x330000)),
    (0x330018, (401, 40)), (0x300004, (0x320000, 0x300000, 0x320000)),
    (0x200018, (124, 53)), (0x330000, (0,)),
])
def test_rejects_invalid_identity_tree_and_class(at, words):
    m = fixture()
    m.put(at, *words)
    with pytest.raises(ValueError):
        watcher.inventory_snapshot(m, (123, 53))


def test_rejects_mutating_quantity():
    m = fixture()
    original = m.read_block
    reads = 0

    def changing(at, size):
        nonlocal reads
        if at == 0x330744:
            reads += 1
            if reads > 1:
                return struct.pack("<I", 9)
        return original(at, size)

    m.read_block = changing
    with pytest.raises(ValueError, match="changed"):
        watcher.inventory_snapshot(m, (123, 53))


def test_derived_items_do_not_invent_quantities():
    m = fixture()
    m.put(0x330000, m.base_address + 0x1143278)
    del m.data[0x330744]
    assert watcher.inventory_snapshot(m, (123, 53))[0]["quantity_raw"] is None


def test_deltas_distinguish_initial_presence_arrival_and_quantity_change():
    first = watcher.inventory_snapshot(fixture(), (123, 53))
    assert watcher.inventory_delta(None, first)["kind"] == "initial_inventory"
    assert watcher.inventory_delta(first, list(reversed(first))) is None
    assert watcher.inventory_delta([], first)["first_observed"] == first
    changed = [dict(first[0], quantity_raw=9)]
    assert watcher.inventory_delta(first, changed)["changed"][0]["before"]["quantity_raw"] == 10
    assert watcher.inventory_delta(first, [])["no_longer_observed"] == first


def test_busy_summary_rename_does_not_stop_journal_collection(tmp_path, monkeypatch):
    original = Path.replace
    calls = 0

    def busy_once(path, target):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("shared-folder reader")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", busy_once)
    monkeypatch.setattr(watcher.time, "sleep", lambda _: None)
    assert watcher.write_json(tmp_path / "status.json", {"samples": 1})
    assert calls == 2
    assert not (tmp_path / "status.tmp").exists()
