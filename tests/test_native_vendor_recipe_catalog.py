import struct

import pytest

from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_recipe_catalog import (
    EXACT_EXECUTABLE_SHA256,
    read_native_vendor_recipe_catalog,
)
from tests.test_native_vendor_queue import (
    CREATION,
    HUD,
    MANAGER,
    ROOT,
    TEMPLATE,
    VENDOR,
    add_recipe,
    fixture,
)

PAGES, TAB, CALLBACK = 0x210000, 0x211000, 0x212000
PANEL, BORDER, LIST, LEAF = 0x220000, 0x230000, 0x240000, 0x250000
ROWS, ENTRIES = (0x260000, 0x261000), (0x270000, 0x271000)


def recipe_fixture():
    """Synthetic owned tab graph; no private captures or executable bytes."""
    m = add_recipe(fixture())
    m.executable_sha256 = EXACT_EXECUTABLE_SHA256
    m.next_array, m.next_text = 0x500000, 0x600000

    def vector(address, values):
        begin = m.next_array
        m.next_array += max(16, len(values) * 4)
        m.put(address, "<III", begin, begin + len(values) * 4, begin + len(values) * 4)
        if values:
            m.put(begin, "<" + "I" * len(values), *values)
        return begin

    def text(address, value):
        raw = value.encode("utf-16-le")
        begin = m.next_text
        m.next_text += ((len(raw) + 3) // 4) * 4 + 4
        m.put(address + 4, "<III", begin, begin + len(raw), begin + len(raw))
        m.put(begin, f"<{len(raw)}s", raw)
        return begin

    m.vector, m.text = vector, text
    vector(CREATION + 0x54, [PAGES])
    m.put(CREATION + 0x518, "<I", PAGES)
    m.put(CREATION + 0x520, "<I", LIST)
    for node, cls in ((PAGES, 0x116B510), (PANEL, 0x1169EC0), (BORDER, 0x11657C8),
                      (LIST, 0x116ACF0), (LEAF, 0x116B138)):
        m.put(node, "<I", m.base_address + cls)
        m.put(node + 0x3BC, "<I", CREATION)
    text(PAGES + 0x164, "ItemCreationPages")
    text(LIST + 0x164, "ITEMLIST")
    vector(PAGES + 0x400, [TAB])
    m.put(TAB + 4, "<I", PANEL)
    m.put(TAB + 0x50, "<I", CALLBACK)
    m.put(CALLBACK, "<IIII", m.base_address + 0x116C2C0, CREATION,
          m.base_address + 0x238AD, 0)
    vector(PANEL + 0x40, [BORDER])
    vector(BORDER + 0x40, [LIST, LEAF])
    vector(LIST + 0x408, ROWS)
    for row, entry, template, label in zip(
        ROWS, ENTRIES, (26990, 25860), ("Gilded Scepter", "Balanced Dagger"), strict=True,
    ):
        m.put(row, "<I", m.base_address + 0x116AEBC)
        m.put(row + 0x3BC, "<I", CREATION)
        m.put(row + 0x458, "<I", LIST)
        m.put(row + 0x44C, "<I", entry)
        m.put(entry, "<I", m.base_address + 0x116C2D0)
        m.put(entry + 0x10, "<II", template, 0)
        text(entry + 0x20, label)
    m.put(LIST + 0x404, "<I", ROWS[0])
    m.put(CREATION + 0x45C, "<I", ENTRIES[0])
    return m


def test_reads_owned_catalog_with_typed_keys_labels_and_separate_selection_state():
    memory = recipe_fixture()
    result = read_native_vendor_recipe_catalog(memory)
    assert result["recipe_count"] == 2
    assert result["recipes"] == [
        dict(template=dict(object_id=26990, object_type=0), display_name="Gilded Scepter",
             selected=True, activated=True),
        dict(template=dict(object_id=25860, object_type=0), display_name="Balanced Dagger",
             selected=False, activated=False),
    ]
    assert result["building"] == {"object_id": 2229645, "object_type": 8}
    assert result["vendor"] == {"object_id": 2517204, "object_type": 42}
    assert result["root_address"] == ROOT and result["list_address"] == LIST
    assert result["process_id"] == 988 and result["process_creation_filetime_utc"] == 100
    assert result["read_consistency_verified"] is True
    assert result["scene_epoch"] is None
    for key in ("scene_lifetime_verified", "command_admitted", "cache_freshness_verified",
                "complete_server_catalog_verified"):
        assert result[key] is False


def test_highlight_is_distinct_from_activation_and_does_not_admit_crafting():
    memory = recipe_fixture()
    memory.put(LIST + 0x404, "<I", ROWS[1])
    result = read_native_vendor_recipe_catalog(memory)
    assert result["selected_template"]["object_id"] == 25860
    assert result["activated_template"] == result["retained_template"]
    assert result["retained_template"]["object_id"] == 26990
    assert not result["command_admitted"]


@pytest.mark.parametrize("field,value", [
    ("executable_sha256", "6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19"),
    ("executable_sha256", "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"),
    ("executable_sha256", "0" * 64), ("executable_name", "other.exe"),
    ("pointer_size", 8), ("pid", True), ("pid", 0),
    ("process_creation_filetime_utc", None), ("process_creation_filetime_utc", 2**64),
    ("base_address", 1),
])
def test_exact_prepared_build_and_process_lifetime_required_before_any_read(field, value):
    memory = recipe_fixture()
    setattr(memory, field, value)
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_vendor_recipe_catalog(memory)
    assert not memory.reads


@pytest.mark.parametrize("address,value", [
    (ROOT + 0x64, 0), (ROOT + 0xA4, 0), (MANAGER + 0x78, 0),
    (MANAGER + 0xD8, 1), (HUD + 0x104, 0), (MANAGER + 0xF8, 555),
    (MANAGER + 0xF4, 42), (VENDOR + 0x14, 37), (CREATION + 0x3C0, 999),
    (CREATION + 0x3B8, 0), (CREATION + 0x518, 123456),
    (PAGES + 0x40C, 1), (PAGES + 0x3BC, HUD), (PANEL + 0x3BC, HUD),
    (CALLBACK + 4, HUD), (CALLBACK + 8, 0), (CALLBACK + 12, 4),
    (LIST + 0x3BC, HUD), (ROWS[0] + 0x458, 0), (ROWS[0] + 0x3BC, HUD),
    (ROWS[0], 0), (ENTRIES[0], 0), (ENTRIES[0] + 0x14, 40),
    (ENTRIES[0] + 0x10, 0), (ENTRIES[1] + 0x10, 26990),
    (ROWS[1] + 0x44C, ENTRIES[0]), (LIST + 0x404, 0x290000),
    (CREATION + 0x45C, 0x290000), (TEMPLATE + 0x10, 25860),
    (TEMPLATE + 0x14, 40), (CREATION + 0x400, 0), (CREATION + 0x404, 3),
    (CREATION + 0x3D8, 2), (LEAF, 0x400000 + 0xDEAD),
])
def test_rejects_malformed_owner_graph_rows_and_selection(address, value):
    memory = recipe_fixture()
    memory.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_vendor_recipe_catalog(memory)


@pytest.mark.parametrize("address,size", [
    (0x1AA7BFC, 4), (ROOT + 0x64, 4), (MANAGER + 0xF0, 8),
    (MANAGER + 0x384, 4), (CREATION + 0x520, 4), (CALLBACK + 8, 4),
    (BORDER + 0x40, 12), (ROWS[0] + 0x44C, 4), (ENTRIES[0] + 0x10, 8),
    (ENTRIES[0] + 0x24, 12), (TEMPLATE + 0x10, 8),
])
def test_reverse_validation_rejects_changed_ownership_or_payload(address, size):
    memory = recipe_fixture()
    memory.change = (address, size, bytes([255]) * size)
    with pytest.raises(NativeVendorDialogCaptureError, match="changed"):
        read_native_vendor_recipe_catalog(memory)


def test_reverse_validation_rechecks_label_bytes_and_same_address_row_array():
    for target in ("text", "array"):
        memory = recipe_fixture()
        if target == "text":
            address = struct.unpack("<I", memory.read_block(ENTRIES[0] + 0x24, 4))[0]
            size = len("Gilded Scepter".encode("utf-16-le"))
        else:
            address = struct.unpack("<I", memory.read_block(LIST + 0x408, 4))[0]
            size = 8
        memory.change = (address, size, bytes([255]) * size)
        with pytest.raises(NativeVendorDialogCaptureError, match="changed"):
            read_native_vendor_recipe_catalog(memory)


@pytest.mark.parametrize("case", ["cycle", "oversize", "detached", "duplicate_row",
                                  "malformed_vector", "deep", "no_tabs"])
def test_rejects_bounded_graph_and_vector_failures(case):
    memory = recipe_fixture()
    if case == "cycle":
        memory.vector(BORDER + 0x40, [PANEL])
    elif case == "oversize":
        memory.put(LIST + 0x408, "<III", 0x500000, 0x500404, 0x500404)
    elif case == "detached":
        memory.vector(BORDER + 0x40, [LEAF])
    elif case == "duplicate_row":
        memory.vector(LIST + 0x408, [ROWS[0], ROWS[0]])
    elif case == "malformed_vector":
        memory.put(LIST + 0x408, "<III", 0x500000, 0x4FFFFC, 0x500000)
    elif case == "no_tabs":
        memory.put(PAGES + 0x400, "<III", 0, 0, 0)
    else:
        parent = PANEL
        for index in range(9):
            child = 0x700000 + index * 0x1000
            memory.put(child, "<I", memory.base_address + 0x1169EC0)
            memory.put(child + 0x3BC, "<I", CREATION)
            memory.vector(parent + 0x40, [child])
            parent = child
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_vendor_recipe_catalog(memory)


@pytest.mark.parametrize(
    "case", ["bad_name", "unpaired_surrogate", "control_character", "oversize"],
)
def test_rejects_unknown_list_name_and_malformed_labels(case):
    memory = recipe_fixture()
    if case == "bad_name":
        memory.text(LIST + 0x164, "OtherList")
    elif case == "oversize":
        memory.put(ENTRIES[0] + 0x24, "<III", 0x610000, 0x610800, 0x610800)
    else:
        pointer = memory.text(ENTRIES[0] + 0x20, "X")
        memory.put(pointer, "<H", 0xD800 if case == "unpaired_surrogate" else 1)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_vendor_recipe_catalog(memory)


def test_owned_empty_list_does_not_claim_complete_server_catalog():
    memory = recipe_fixture()
    memory.vector(LIST + 0x408, [])
    for address in (LIST + 0x404, CREATION + 0x45C, CREATION + 0x408):
        memory.put(address, "<I", 0)
    result = read_native_vendor_recipe_catalog(memory)
    assert result["recipes"] == []
    assert result["retained_template"] is None
    assert not result["complete_server_catalog_verified"]


def test_process_lifetime_is_rechecked_after_memory_consistency_pass():
    memory = recipe_fixture()
    read = memory.read_block

    def changing(address, size):
        result = read(address, size)
        if address == 0x1AA7BFC and memory.reads[address, size] == 2:
            memory.process_creation_filetime_utc += 1
        return result

    memory.read_block = changing
    with pytest.raises(NativeVendorDialogCaptureError, match="identity changed"):
        read_native_vendor_recipe_catalog(memory)
