"""Resource evidence must remain rooted, bounded and independent of selection."""
import pytest

from shadowbane_lab.client_observation import native_furnishing_resources as resources
from shadowbane_lab.client_observation.native_furnishing_preview import (
    read_native_furnishing_preview,
)
from shadowbane_lab.client_observation.native_vendor_dialog import NativeVendorDialogCaptureError
from tests.test_native_furnishing_preview import MODEL, furnishing_fixture
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST

RENDER, TEMPLATE, MESH_SET, MESH = 0x500000, 0x510000, 0x520000, 0x530000
TEXTURE_SET, TEXTURE, RESOURCE = 0x540000, 0x550000, 0x560000
MESH_VECTOR, TEXTURE_VECTOR, CHILD_VECTOR = 0x570000, 0x580000, 0x590000
KEY = (5017277, 30)
TQS = (1., 2., 3., 1., 0., 0., 0., 1., 1., 1.)


def render_node(m, pointer):
    m.put(pointer, "<I", m.base_address + resources.RENDER_RVA)
    m.put(pointer + 0x30, "<I", m.base_address + 0x1149D94)
    m.put(pointer + 0x48, "<10f", *TQS)
    m.put(pointer + 0x70, "<10f", *TQS)
    m.put(pointer + 0xCC, "<f", 1.)


def vector(m, owner, offset, storage, values):
    end = storage + len(values) * 4
    m.put(owner + offset, "<III", storage, end, end)
    if values:
        m.put(storage, "<" + "I" * len(values), *values)


def resource_fixture():
    m = furnishing_fixture(selected=False)
    for at, value in (
        (MODEL, m.base_address + resources.STATIC_MODEL_RVA),
        (MODEL + 0x44, m.base_address + 0x114350C), (MODEL + 0xC0, RENDER),
        (RENDER + 0xC4, TEMPLATE), (RENDER + 0xE8, TEXTURE_SET),
        (TEMPLATE, m.base_address + resources.TEMPLATE_RVA), (TEMPLATE + 0x1C, MESH_SET),
        (MESH_SET, m.base_address + resources.MESH_SET_RVA),
        (MESH, m.base_address + 0x114965C),
        (TEXTURE_SET, m.base_address + resources.TEXTURE_SET_RVA),
        (TEXTURE, m.base_address + resources.SINGLE_TEXTURE_RVA), (TEXTURE + 0x5C, RESOURCE),
        (RESOURCE, m.base_address + resources.IMAGE_RVA),
    ):
        m.put(at, "<I", value)
    m.put(RESOURCE + 0x38, "<II", 256, 256)
    m.put(RESOURCE + 0x44, "<I", 74)
    m.put(RESOURCE + 0x50, "<I", 0x100)
    render_node(m, RENDER)
    vector(m, MESH_SET, 0x24, MESH_VECTOR, [MESH])
    vector(m, TEXTURE_SET, 0x24, TEXTURE_VECTOR, [TEXTURE])
    return m


def capture(m):
    return read_native_furnishing_preview(m, resource_entry_key=KEY)


def evidence(result):
    return result["rows"][0]["render_resources_raw"]


@pytest.mark.parametrize("texture_rva", [resources.SINGLE_TEXTURE_RVA, resources.COLOR_TEXTURE_RVA])
def test_unselected_owned_row_yields_resource_evidence_without_render_admission(texture_rva):
    m = resource_fixture()
    m.put(TEXTURE, "<I", m.base_address + texture_rva)
    result = capture(m)
    assert result["selected_entry_address"] == 0
    assert result["list_selected_control_address_raw"] == 0
    assert result["rows"][0]["selected"] is False
    graph = evidence(result)
    assert graph["scope"] == "owned_row_resource_evidence"
    assert graph["root_reference"]["address"] == RENDER
    assert graph["unreviewed_class_rvas"] == []
    node = graph["nodes"][0]
    assert node["world_tqs_raw"] == list(TQS)
    assert node["local_tqs_raw"] == list(TQS)
    assert node["template"]["mesh_references"][0]["address"] == MESH
    texture = node["texture_set"]["textures"][0]
    assert texture["shared_resource_reference"]["address"] == RESOURCE
    assert texture["image_raw"] == {
        "width": 256, "height": 256, "texture_name": 74, "status_bytes": [0, 1],
    }
    assert {at for at, _ in m.reads if RESOURCE < at < RESOURCE + 0x1000} == {
        RESOURCE + 0x38, RESOURCE + 0x44, RESOURCE + 0x50,
    }
    for flag in ("selection_admitted", "render_lifetime_owned", "resource_readiness_verified",
                 "native_calls_made"):
        assert graph[flag] is False
    assert not result["command_admitted"]


def test_default_reader_does_not_follow_render_resources():
    m = resource_fixture()
    result = read_native_furnishing_preview(m)
    assert "render_resources_raw" not in result["rows"][0]
    assert (MODEL + 0xC0, 4) not in m.reads


@pytest.mark.parametrize("at,blocked", [
    (MODEL, MODEL + 0xC0), (RENDER, RENDER + 0x3C),
    (TEMPLATE, TEMPLATE + 0x1C), (MESH_SET, MESH_SET + 0x24),
    (TEXTURE_SET, TEXTURE_SET + 0x24), (TEXTURE, TEXTURE + 0x5C),
    (RESOURCE, RESOURCE + 0x38),
])
def test_unknown_classes_are_references_and_never_grant_field_interpretation(at, blocked):
    m = resource_fixture()
    m.put(at, "<I", m.base_address + 0x1140010)
    graph = evidence(capture(m))
    assert 0x1140010 in graph["unreviewed_class_rvas"]
    assert not any(address == blocked for address, _ in m.reads)


@pytest.mark.parametrize("at", [ENTRY + 0x24, MODEL + 0xC0, RENDER + 0xC4,
                                RENDER + 0xE8, TEXTURE + 0x5C])
def test_null_loading_references_are_not_readiness(at):
    m = resource_fixture()
    m.put(at, "<I", 0)
    assert evidence(capture(m))["resource_readiness_verified"] is False


@pytest.mark.parametrize("at,size", [
    (ENTRY + 0x10, 8), (ENTRY + 0x24, 4), (MODEL + 0xC0, 4),
    (RENDER + 0x30, 4), (RENDER + 0x3C, 12), (RENDER + 0x48, 40),
    (RENDER + 0x148, 4), (RENDER + 0xE8, 4), (TEXTURE_SET + 0x24, 12),
    (TEXTURE_VECTOR, 4), (TEXTURE + 0x5C, 4), (RESOURCE, 4),
    (RESOURCE + 0x38, 8), (RESOURCE + 0x44, 4), (RESOURCE + 0x50, 4),
])
def test_changed_resource_or_owner_invalidates_whole_snapshot(at, size):
    m = resource_fixture()
    m.change = (at, size, b"\xff" * size)
    with pytest.raises(NativeVendorDialogCaptureError):
        capture(m)


@pytest.mark.parametrize("key", [[], [1, 30], (1,), (0, 30), (-1, 30),
                                (True, 30), (1, 2**32), (1, "30")])
def test_invalid_request_key_fails_before_reading(key):
    m = resource_fixture()
    with pytest.raises(NativeVendorDialogCaptureError, match="entry key"):
        read_native_furnishing_preview(m, resource_entry_key=key)
    assert not m.reads


def test_request_cannot_follow_a_detached_or_missing_row():
    m = resource_fixture()
    m.put(ENTRY + 0x10, "<II", 9, 30)
    with pytest.raises(NativeVendorDialogCaptureError, match="one owned"):
        capture(m)
    assert (MODEL + 0xC0, 4) not in m.reads


def test_ambiguous_key_in_distinct_owned_rows_is_rejected():
    m = resource_fixture()
    control2, entry2 = 0x610000, 0x620000
    for at, value in ((control2, m.base_address + 0x116AEBC), (control2 + 0x3BC, HUD),
                      (control2 + 0x458, LIST), (control2 + 0x44C, entry2),
                      (entry2, m.base_address + 0x1169908), (entry2 + 8, 0x25)):
        m.put(at, "<I", value)
    m.put(entry2 + 0x10, "<II", *KEY)
    vector(m, LIST, 0x408, 0x170000, [CONTROL, control2])
    with pytest.raises(NativeVendorDialogCaptureError, match="one owned"):
        capture(m)


@pytest.mark.parametrize("children", [[RENDER], [0]])
def test_cycles_and_null_children_fail_bounded_capture(children):
    m = resource_fixture()
    vector(m, RENDER, 0x3C, CHILD_VECTOR, children)
    with pytest.raises(NativeVendorDialogCaptureError):
        capture(m)


def test_graph_depth_is_bounded():
    m = resource_fixture()
    for depth in range(resources.MAX_RENDER_DEPTH + 1):
        parent = RENDER if depth == 0 else 0x700000 + (depth - 1) * 0x1000
        child = 0x700000 + depth * 0x1000
        render_node(m, child)
        vector(m, parent, 0x3C, 0x680000 + depth * 16, [child])
    with pytest.raises(NativeVendorDialogCaptureError, match="graph limit"):
        capture(m)


def test_total_nodes_are_bounded_across_child_vectors():
    m = resource_fixture()
    children = [0x700000 + n * 0x1000 for n in range(resources.MAX_RENDER_NODES - 1)]
    for child in children:
        render_node(m, child)
    vector(m, RENDER, 0x3C, CHILD_VECTOR, children)
    assert len(evidence(capture(m))["nodes"]) == resources.MAX_RENDER_NODES
    child = 0x780000
    render_node(m, child)
    vector(m, children[0], 0x3C, 0x690000, [child])
    with pytest.raises(NativeVendorDialogCaptureError, match="graph limit"):
        capture(m)


def test_member_budget_applies_across_mesh_and_texture_sets(monkeypatch):
    m = resource_fixture()
    monkeypatch.setattr(resources, "MAX_TOTAL_SET_MEMBERS", 1)
    with pytest.raises(NativeVendorDialogCaptureError, match="member limit"):
        capture(m)


@pytest.mark.parametrize("at,value", [(MODEL + 0x44, 0), (RENDER + 0x30, 0),
                                     (MODEL + 0xC0, 0xFFFFFFFF),
                                     (TEXTURE_SET + 0x28, TEXTURE_VECTOR + 1000)])
def test_malformed_interfaces_pointers_and_vectors_are_rejected(at, value):
    m = resource_fixture()
    m.put(at, "<I", value)
    with pytest.raises(NativeVendorDialogCaptureError):
        capture(m)


@pytest.mark.parametrize("at", [RENDER + 0x48, RENDER + 0x70, RENDER + 0xCC])
def test_nonfinite_transforms_and_opacity_are_rejected(at):
    m = resource_fixture()
    m.put(at, "<f", float("nan"))
    with pytest.raises(NativeVendorDialogCaptureError, match="nonfinite"):
        capture(m)


def test_selected_row_resource_copy_still_does_not_grant_runtime_admission():
    m = resource_fixture()
    m.put(TEXTURE, "<I", m.base_address + resources.COLOR_TEXTURE_RVA)
    m.put(HUD + 0x660, "<I", ENTRY)
    m.put(LIST + 0x404, "<I", CONTROL)
    result = capture(m)
    assert result["rows"][0]["selected"] is True
    assert result["list_selected_control_address_raw"] == CONTROL
    assert evidence(result)["nodes"][0]["texture_set"]["textures"][0][
        "shared_resource_reference"]["address"] == RESOURCE
    assert not evidence(result)["selection_admitted"]
    assert not result["command_admitted"]
