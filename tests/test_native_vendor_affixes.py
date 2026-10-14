import hashlib

import pytest

from shadowbane_lab.client_observation import native_vendor_affixes as a
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCaptureError,
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_queue import NativeVendorObservationChanged
from shadowbane_lab.equipment.crafting_assessment import compact_affix_token
from tests.test_native_vendor_inventory import (
    EFFECT,
    INSTANCE,
    ITEM,
    ITEM_ID,
    VECTOR,
    inventory_fixture,
)

MANAGER, SENTINEL, NODE, DEFINITION = 0x300000, 0x301000, 0x302000, 0x303000
LABEL, IDENTIFIER = 0x310000, 0x311000


def text(memory, address, buffer, value):
    raw = value.encode("utf-16-le")
    memory.put(address + 4, "<III", buffer, buffer + len(raw), buffer + len(raw) + 2)
    memory.put(buffer, f"<{len(raw)}s", raw)


@pytest.fixture
def observed(monkeypatch):
    effects = ('"EffectPrefix:Hallowed" "Hallowed" "Hallowed" "Hallowed"\n'
               '"EffectPrefix:Mystery" "Mystery" "Mystery" "Mystery"\n'
               '"EffectSuffix:Embers" "of Embers" "of Embers" "of Embers"\n'
               '"EffectSuffix:Genius" "of Genius" "of Genius" "of Genius"\n'
               '"EffectSuffix:Unknown" "of Unlisted" "of Unlisted" "of Unlisted"\n'
               ).encode("utf-16")
    items = b'26990 "Gilded Scepter" N "!PREFIX! !ITEMNAME! !SUFFIX!"\n  \n'
    monkeypatch.setattr(a, "_EFFECTS_SHA", hashlib.sha256(effects).hexdigest())
    monkeypatch.setattr(a, "_ITEMS_SHA", hashlib.sha256(items).hexdigest())
    m = inventory_fixture()
    m.executable_sha256 = a._IMAGE
    parent, child = compact_affix_token("SUF-001"), compact_affix_token("SUF-001A")
    m.put(m.base_address + a._REGISTRY, "<I", MANAGER)
    m.put(MANAGER, "<II", SENTINEL, 1)
    m.put(SENTINEL, "<4I", 0, NODE, NODE, NODE)
    m.put(NODE, "<6I", 0, SENTINEL, SENTINEL, SENTINEL, parent, DEFINITION)
    m.put(DEFINITION, "<I", m.base_address + 0x1148B48)
    m.put(DEFINITION + 0x1C, "<I", parent)
    m.put(DEFINITION + 0x88, "<I", child)
    text(m, DEFINITION + 4, IDENTIFIER, "SUF-001")
    text(m, ITEM + 0xD8, LABEL, "Gilded Scepter of Embers")
    m.put(INSTANCE + 0xB4, "<III", VECTOR + 0x200, VECTOR + 0x208, VECTOR + 0x210)
    m.put(VECTOR + 0x200, "<II", EFFECT, EFFECT + 0x40)
    m.put(EFFECT, "<III", parent, 0, 1)
    m.put(EFFECT + 0x40, "<III", child, 0, 1)
    return m, effects, items


def read(observed, **kwargs):
    memory, effects, items = observed
    return a.read_native_vendor_affixes(memory, building=2229645, vendor=2517204,
                                        effects_dictionary=effects, item_dictionary=items, **kwargs)


def test_complete_owned_low_tier_needs_native_parent_and_child_coverage(observed):
    out = read(observed)
    row, = out["items"]
    assert row["item"]["object_id"] == ITEM_ID
    assert row["assessment"]["disposition"] == "exclude"
    assert row["assessment"]["prefix_tier"] == 0 and row["assessment"]["suffix_tier"] == 2
    assert row["assessment"]["suffix"]["identifier"] == "SUF-001"
    assert not out["command_admitted"] and not row["assessment"]["command_admitted"]
    assert not out["complete_inventory"] and out["scope"] == "displayed_entries"


@pytest.mark.parametrize("label", ["Gilded Scepter of Genius", "Gilded Scepter of Unlisted"])
def test_tier_three_and_unknown_are_both_protected(observed, label):
    text(observed[0], ITEM + 0xD8, LABEL, label)
    row, = read(observed)["items"]
    assert row["assessment"]["disposition"] == "keep"


@pytest.mark.parametrize("prefix,expected", [("Mystery", "keep"), ("Hallowed", "exclude")])
def test_unknown_prefix_overrides_known_tier_two_suffix(observed, prefix, expected):
    m = observed[0]
    parent, child = compact_affix_token("PRE-001"), compact_affix_token("PRE-001A")
    existing = compact_affix_token("SUF-001")
    m.put(MANAGER + 4, "<I", 2)
    m.put(NODE + (8 if parent < existing else 12), "<I", NODE + 0x2000)
    m.put(NODE + 0x2000, "<6I", 0, NODE, SENTINEL, SENTINEL, parent, DEFINITION + 0x2000)
    m.put(DEFINITION + 0x2000, "<I", m.base_address + 0x1148B48)
    m.put(DEFINITION + 0x201C, "<I", parent)
    m.put(DEFINITION + 0x2088, "<I", child)
    text(m, DEFINITION + 0x2004, IDENTIFIER + 0x2000, "PRE-001")
    m.put(INSTANCE + 0xB4, "<III", VECTOR + 0x200, VECTOR + 0x210, VECTOR + 0x210)
    m.put(VECTOR + 0x208, "<II", EFFECT + 0x80, EFFECT + 0xC0)
    m.put(EFFECT + 0x80, "<III", parent, 0, 1)
    m.put(EFFECT + 0xC0, "<III", child, 0, 1)
    text(m, ITEM + 0xD8, LABEL, prefix + " Gilded Scepter of Embers")
    row, = read(observed)["items"]
    assert row["assessment"]["disposition"] == expected
    assert row["assessment"]["suffix_tier"] == 2


@pytest.mark.parametrize("fault", ["extra_effect", "missing_child", "trained", "source",
                                   "role", "unnamed", "custom_name", "unsupported_action"])
def test_unknown_content_overrides_an_otherwise_known_low_tier(observed, fault):
    m = observed[0]
    if fault == "extra_effect":
        m.put(INSTANCE + 0xB8, "<I", VECTOR + 0x20C)
        m.put(VECTOR + 0x208, "<I", EFFECT + 0x80)
        m.put(EFFECT + 0x80, "<III", 999, 0, 1)
    elif fault == "missing_child":
        m.put(INSTANCE + 0xB8, "<I", VECTOR + 0x204)
    elif fault == "trained":
        m.put(EFFECT + 4, "<I", 1)
    elif fault == "source":
        m.put(EFFECT + 8, "<I", 2)
    elif fault == "role":
        text(m, ITEM + 0xD8, LABEL, "Hallowed Gilded Scepter")
    elif fault == "unnamed":
        text(m, ITEM + 0xD8, LABEL, "")
    elif fault == "custom_name":
        text(m, INSTANCE + 0xD0, LABEL + 0x100, "Gilded Scepter of Embers")
    else:
        m.put(DEFINITION, "<I", m.base_address + 0x1148BC0)
    assert read(observed)["items"][0]["assessment"]["disposition"] == "keep"


@pytest.mark.parametrize("fault", ["token", "identifier", "cycle", "ordering", "count"])
def test_corrupt_or_changed_registry_returns_no_partial_assessment(observed, fault):
    m = observed[0]
    if fault == "token":
        m.put(DEFINITION + 0x1C, "<I", 999)
    elif fault == "identifier":
        text(m, DEFINITION + 4, IDENTIFIER, "SUF-002")
    elif fault == "cycle":
        m.put(NODE + 12, "<I", NODE)
    elif fault == "ordering":
        m.put(NODE + 16, "<I", 0)
    else:
        m.put(MANAGER + 4, "<I", 4097)
    with pytest.raises(NativeVendorDialogCaptureError):
        read(observed)


@pytest.mark.parametrize("address,size", [(ITEM + 0xDC, 12), (MANAGER, 8), (NODE, 24)])
def test_successful_reads_that_change_are_not_evidence(observed, address, size):
    observed[0].change = (address, size, b"\xff" * size)
    with pytest.raises((NativeVendorObservationChanged, NativeVendorDialogCaptureError)):
        read(observed)


def test_only_current_image_and_exact_dictionaries_are_eligible(observed):
    m, effects, items = observed
    with pytest.raises(NativeVendorDialogCompatibilityError):
        a.read_native_vendor_affixes(m, building=2229645, vendor=2517204,
                                    effects_dictionary=effects + b"x", item_dictionary=items)
    assert not m.reads
    m.executable_sha256 = "bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87"
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read(observed)
    assert not m.reads


def test_different_vendor_and_exhausted_read_bound_never_produce_a_decision(observed):
    m, effects, items = observed
    with pytest.raises(NativeVendorDialogCaptureError, match="another vendor"):
        a.read_native_vendor_affixes(m, building=2229645, vendor=999,
                                    effects_dictionary=effects, item_dictionary=items)
    reads = a._AffixReadSet(m)
    reads.calls = 32768
    with pytest.raises(NativeVendorDialogCaptureError, match="read bound"):
        reads.word(MANAGER)
