import pytest

from shadowbane_lab.client_observation.native_vendor_cost import (
    random_cost,
    read_native_vendor_cost,
)
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from tests.test_native_vendor_queue import CREATION, add_recipe, fixture


def memory():
    m = add_recipe(fixture())
    m.executable_sha256 = "366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a"
    m.put(CREATION + 0x3DC, "<f", 0.1)
    m.put(CREATION + 0x53C, "<I", 0x210000)
    m.put(0x210000, "<II", 0x210100, 0x210100)
    m.put(0x210100, "<IIII", 0x210000, 0x210000, 2308551, 151)
    return m


def test_owned_random_cost_includes_markup_without_spending():
    queue, costs = read_native_vendor_cost(memory())
    assert queue["vendor"]["object_id"] == 2517204
    assert costs == {2308551: 166}
    assert queue["command_admitted"] is False


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
        (CREATION + 0x4D4, "<I", 2),
        (CREATION + 0x3D8, "<I", 1),
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
