import pytest

from shadowbane_lab.client_observation.native_vendor_cost import (
    random_cost,
    read_native_vendor_cost,
)
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from tests.test_native_vendor_queue import CREATION, add_recipe, fixture

COST_LIST, COST_CONTROL, COST_ENTRY = 0x220000, 0x230000, 0x240000


def text(m, address, value, buffer):
    raw = value.encode("utf-16-le")
    m.put(address + 4, "<III", buffer, buffer + len(raw), buffer + len(raw))
    m.put(buffer, f"<{len(raw)}s", raw)


def memory():
    m = add_recipe(fixture())
    m.executable_sha256 = "366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a"
    m.put(CREATION + 0x3DC, "<f", 0.1)
    m.put(CREATION + 0x53C, "<I", 0x210000)
    m.put(0x210000, "<II", 0x210100, 0x210100)
    m.put(0x210100, "<IIII", 0x210000, 0x210000, 2308551, 151)
    m.put(CREATION + 0x54, "<III", 0x250000, 0x250004, 0x250004)
    m.put(0x250000, "<I", COST_LIST)
    m.put(COST_LIST, "<I", m.base_address + 0x116ACF0)
    m.put(COST_LIST + 0x3BC, "<I", CREATION)
    text(m, COST_LIST + 0x164, "ResourceCostList", 0x260000)
    m.put(COST_LIST + 0x408, "<III", 0x250100, 0x250104, 0x250104)
    m.put(0x250100, "<I", COST_CONTROL)
    m.put(COST_CONTROL, "<I", m.base_address + 0x116AEBC)
    m.put(COST_CONTROL + 0x3BC, "<I", CREATION)
    m.put(COST_CONTROL + 0x458, "<I", COST_LIST)
    m.put(COST_CONTROL + 0x44C, "<I", COST_ENTRY)
    m.put(COST_ENTRY, "<I", m.base_address + 0x116F258)
    m.put(COST_ENTRY + 0x20, "<I", 2308551)
    m.put(COST_ENTRY + 0x48, "<I", 166)
    text(m, COST_ENTRY + 0x30, "Gold", 0x260100)
    return m


@pytest.mark.parametrize("digest", [
    "366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a",
    "6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad",
])
def test_owned_random_cost_includes_markup_without_spending(digest):
    m = memory()
    m.executable_sha256 = digest
    queue, costs = read_native_vendor_cost(m)
    assert queue["vendor"]["object_id"] == 2517204
    assert costs == {2308551: 166}
    assert queue["command_admitted"] is False
    assert queue["recipe_resource_costs"] == {"2308551": {"label": "Gold", "amount": 166}}


@pytest.mark.parametrize(
    "amount,markup,cost", [(151, 0.1, 166), (1, 0.5, 2), (151, 0, 151), (100, 1, 200)]
)
def test_native_rounding(amount, markup, cost):
    assert random_cost(amount, markup) == cost


@pytest.mark.parametrize(
    "amount,markup",
    [
        (True, 0.1),
        (0, 0.1),
        (-1, 0.1),
        (2**31 - 1, 1),
        (10, float("nan")),
        (10, float("inf")),
        (10, -0.1),
    ],
)
def test_invalid_or_overflow_cost_is_unavailable(amount, markup):
    with pytest.raises(NativeVendorDialogCaptureError):
        random_cost(amount, markup)


@pytest.mark.parametrize(
    "address,fmt,value",
    [
        (CREATION + 0x404, "<I", 0),
        (CREATION + 0x4D4, "<I", 11),
        (CREATION + 0x4D4, "<I", 0),
        (CREATION + 0x540, "<I", 256),
        (0x210100 + 4, "<I", 0),
        (0x210100, "<I", 0x210100),
        (0x210100 + 8, "<I", 0),
        (0x210100 + 12, "<I", 0),
    ],
)
def test_changed_recipe_or_malformed_requirements_are_rejected(address, fmt, value):
    m = memory()
    m.put(address, fmt, value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_vendor_cost(m)


def test_changing_cost_is_never_adopted_by_retry():
    m = memory()
    m.change = (0x210100 + 12, 4, (999).to_bytes(4, "little"))
    with pytest.raises(NativeVendorDialogCaptureError, match="changed"):
        read_native_vendor_cost(m)


@pytest.mark.parametrize("multiple", [0, 1])
@pytest.mark.parametrize("digest", [
    "366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a",
    "6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad",
])
def test_ten_per_slot_cost_rounds_markup_before_quantity_without_granting_actions(multiple, digest):
    m = memory()
    m.executable_sha256 = digest
    m.put(CREATION + 0x4D4, "<I", 10)
    m.put(CREATION + 0x3D8, "<I", multiple)
    m.put(COST_ENTRY + 0x48, "<I", 1660)
    queue, costs = read_native_vendor_cost(m)
    assert costs == {2308551: 1660}  # Rounding only after multiplying would produce 1661.
    assert queue["creation_recipe"]["quantity"] == 10
    assert queue["creation_recipe"]["multiple_slots"] is bool(multiple)
    assert queue["command_admitted"] is False


@pytest.mark.parametrize("quantity", [True, 0, -1, 11, 1.5])
def test_invalid_per_slot_quantity_is_rejected(quantity):
    with pytest.raises(NativeVendorDialogCaptureError):
        random_cost(151, .1, quantity)


def test_quantity_overflow_is_rejected_after_native_markup_rounding():
    with pytest.raises(NativeVendorDialogCaptureError, match="quantity cost"):
        random_cost(2**30, 0, 10)


def test_quantity_change_during_observation_is_rejected():
    m = memory()
    m.change = (CREATION + 0x4D4, 4, (10).to_bytes(4, "little"))
    with pytest.raises(NativeVendorDialogCaptureError, match="changed"):
        read_native_vendor_cost(m)


@pytest.mark.parametrize("address,value", [
    (COST_LIST + 0x3BC, CREATION + 4), (COST_CONTROL, 0),
    (COST_CONTROL + 0x3BC, CREATION + 4), (COST_CONTROL + 0x458, COST_LIST + 4),
    (COST_ENTRY, 0), (COST_ENTRY + 0x20, 777), (COST_ENTRY + 0x48, 167),
])
def test_displayed_resource_owner_and_cost_must_match_requirements(address, value):
    m = memory()
    m.put(address, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        read_native_vendor_cost(m)


def test_gold_label_does_not_assume_a_resource_key():
    m = memory()
    m.put(COST_ENTRY + 0x20, "<I", 777)
    m.put(0x210100 + 8, "<I", 777)
    queue, costs = read_native_vendor_cost(m)
    assert costs == {777: 166}
    assert queue["recipe_resource_costs"] == {"777": {"label": "Gold", "amount": 166}}
