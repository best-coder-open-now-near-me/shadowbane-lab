from __future__ import annotations

import base64
import copy
import hashlib
import json
import struct

import pytest

from shadowbane_lab.diagnostics.terrain_material_analysis import (
    Mask,
    Tile,
    analyze_material_boundaries,
    main,
)
from shadowbane_lab.diagnostics.terrain_material_poll import PROFILE
from shadowbane_lab.diagnostics.terrain_mesh_snapshot import LAYOUT_SIGNATURES


def buffer(raw, components=None, scalar=None):
    result = {"bytes_base64": base64.b64encode(raw).decode(), "byte_count": len(raw),
              "sha256": hashlib.sha256(raw).hexdigest()}
    if components is not None:
        result.update(components=components, scalar=scalar)
    return result


def material(resource):
    return {"reviewed_color_texture": True,
            "token": {"archive_group": 0, "archive_resource": resource}}


def layer(value, index=0, token=20):
    return {"index": index, "color": material(token), "source_mask": {"resident_alpha": {
        "state": "captured", "storage": "resident_cpu_alpha8", "width": 64, "height": 64,
        **buffer(bytes([value]) * 4096)}}}


def fingerprint(snapshot):
    raw = json.dumps({"source": snapshot["source"], "mesh": snapshot.get("mesh")},
                     sort_keys=True, separators=(",", ":")).encode()
    snapshot["fingerprint_sha256"] = hashlib.sha256(raw).hexdigest()
    return snapshot


def tile(ordinal=1, x=0, z=0, height=0, divisions=1, alpha=64):
    positions, uv, indices = [], [], []
    for row in range(divisions + 1):
        for column in range(divisions + 1):
            positions.extend((x + column / divisions, height, z + row / divisions))
            uv.extend((column / divisions, row / divisions))
    for row in range(divisions):
        for column in range(divisions):
            a = row * (divisions + 1) + column
            b, c = a + 1, a + divisions + 1
            indices.extend((a, b, c, b, c + 1, c))
    mesh = {"state": "captured", "topology": "triangles",
            "vertex_count": len(positions) // 3, "index_count": len(indices)}
    for name, values, components, scalar in (
        ("positions", positions, 3, "f"), ("uv", uv, 2, "f"), ("indices", indices, 1, "H"),
    ):
        mesh[name] = buffer(struct.pack(f"<{len(values)}{scalar}", *values), components,
                            "little_endian_float32" if scalar == "f" else "little_endian_uint16")
    source = {"address": f"0x{ordinal:08x}", "base": material(10), "layers": [layer(alpha)],
              "layer_vector_counts_agree": True, "mask_rotation_degrees": 0}
    return fingerprint({"ordinal": ordinal, "mesh": mesh, "source": source,
                        "source_pointer": source["address"], "ownership_consistency": "whole-read"})


def capture(*snapshots):
    signatures = {
        "draw_entry": PROFILE.draw_signature.hex(),
        "shader_vtable": f"0x{0x400000 + PROFILE.shader_vtable_rva:08x}",
        "pixel_accessor": PROFILE.pixel_accessor_signature.hex(),
        "mesh_layout_signatures": {f"0x{rva:08x}": raw.hex() for rva, raw in LAYOUT_SIGNATURES},
        "repaired_branches": {b.label: b.signature.hex() for b in PROFILE.branch_profile.branches},
    }
    return {"schema_version": 4, "status": "captured", "profile_id": PROFILE.profile_id,
            "executable_sha256": PROFILE.branch_profile.executable_sha256,
            "extension_sha256": PROFILE.branch_profile.extension_sha256, "image_base": "0x00400000",
            "process_id": 123, "process_creation_filetime_utc": 456,
            "signatures_before": signatures, "signatures_after": copy.deepcopy(signatures),
            "snapshots": list(snapshots)}


def test_same_weights_on_differently_subdivided_connected_edge():
    result = analyze_material_boundaries(capture(tile(divisions=4), tile(2, x=1)))
    edge, = result["boundaries"]
    assert not result["skipped_snapshots"]
    assert edge["fragment_count"] == 4
    assert edge["compared_projected_length"] == 1
    assert edge["sampled_max_weight_distance"] == edge["length_weighted_mean_distance"] == 0
    assert edge["sample_count"] == 132


def test_constant_mask_difference_is_length_weighted():
    result = analyze_material_boundaries(capture(tile(alpha=0), tile(2, x=1, alpha=255)))
    edge, = result["boundaries"]
    assert edge["sampled_max_weight_distance"] == edge["length_weighted_mean_distance"] == 1
    assert result["scope"]["framebuffer_color"] is False


def test_between_vertex_mask_peak_is_sampled():
    left = tile(alpha=0)
    mask = left["source"]["layers"][0]["source_mask"]["resident_alpha"]
    pixels = bytearray(4096)
    pixels[31 * 64:33 * 64] = bytes([255]) * 128
    mask.update(buffer(bytes(pixels)))
    result = analyze_material_boundaries(capture(fingerprint(left), tile(2, x=1, alpha=0)))
    edge, = result["boundaries"]
    assert edge["sampled_max_weight_distance"] == 1
    assert edge["worst_sample"]["position"][2] == pytest.approx(0.4921875)


@pytest.mark.parametrize(("x", "z"), [(1, 1), (2, 0), (0, 0), (1.00001, 0)])
def test_corner_gap_overlapping_tiles_and_nearby_planes_are_not_shared_edges(x, z):
    assert not analyze_material_boundaries(capture(tile(), tile(2, x=x, z=z)))["boundaries"]


def test_same_source_observed_twice_is_not_its_own_neighbor():
    right = tile(2, x=1)
    right["source_pointer"] = right["source"]["address"] = "0x00000001"
    fingerprint(right)
    assert not analyze_material_boundaries(capture(tile(), right))["boundaries"]


def test_vertical_gap_is_reported_not_composed():
    edge, = analyze_material_boundaries(capture(tile(), tile(2, x=1, height=0.01)))["boundaries"]
    assert edge["rejected_height_fragments"] == 1
    assert edge["fragment_count"] == 0
    assert edge["sampled_max_weight_distance"] is None


def test_alpha_filter_clamps_at_edges_and_interpolates_between_texel_centers():
    mask = Mask("test", 2, bytes((0, 255, 255, 0)))
    assert mask.sample((-1, -1)) == 0
    assert mask.sample((2, -1)) == 1
    assert mask.sample((0.5, 0.5)) == 0.5


def test_ordered_repeated_material_weights_and_negative_z_rotation():
    masks = [Mask("b", 1, bytes([128])), Mask("a", 1, bytes([64]))]
    item = Tile(1, "s", "a", masks, 90, {})
    assert item.rotate((1, 0.5)) == pytest.approx((0.5, 0))
    weights = item.weights((0, 0))
    assert weights["b"] == pytest.approx((128 / 255) * (1 - 64 / 255))
    assert sum(weights.values()) == pytest.approx(1)


def test_missing_alpha_is_skipped_not_zero_filled():
    left = tile()
    left["source"]["layers"][0]["source_mask"]["resident_alpha"] = {"state": "not_resident"}
    result = analyze_material_boundaries(capture(fingerprint(left), tile(2, x=1)))
    assert len(result["skipped_snapshots"]) == 1
    assert not result["boundaries"]


@pytest.mark.parametrize("field", ["schema_version", "profile_id", "executable_sha256",
                                   "extension_sha256", "signatures_after"])
def test_unreviewed_capture_is_rejected(field):
    payload = capture(tile())
    payload[field] = None
    with pytest.raises(ValueError):
        analyze_material_boundaries(payload)


def test_modified_snapshot_digest_is_rejected():
    left = tile()
    left["source"]["mask_rotation_degrees"] = 90
    with pytest.raises(ValueError, match="fingerprint"):
        analyze_material_boundaries(capture(left))


@pytest.mark.parametrize("bad", ["hash", "index", "nan", "uv", "topology", "count"])
def test_bad_mesh_is_explicitly_skipped(bad):
    left = tile()
    mesh = left["mesh"]
    if bad == "hash":
        mesh["positions"]["sha256"] = "bad"
    elif bad == "index":
        mesh["indices"] = buffer(struct.pack("<6H", 0, 1, 200, 1, 3, 2),
                                 1, "little_endian_uint16")
    elif bad in ("nan", "uv"):
        mesh["uv"] = buffer(struct.pack("<8f", float("nan") if bad == "nan" else 2,
                                        0, 1, 0, 0, 1, 1, 1), 2, "little_endian_float32")
    elif bad == "topology":
        mesh["topology"] = "triangle_strip"
    else:
        mesh["vertex_count"] = 1000000
    result = analyze_material_boundaries(capture(fingerprint(left), tile(2, x=1)))
    assert len(result["skipped_snapshots"]) == 1
    assert not result["boundaries"]


def test_budget_failure_does_not_write_partial_analysis(tmp_path, monkeypatch):
    import shadowbane_lab.diagnostics.terrain_material_analysis as module

    monkeypatch.setattr(module, "MAX_SAMPLES", 1)
    path, output = tmp_path / "capture.json", tmp_path / "result.json"
    path.write_text(json.dumps(capture(tile(), tile(2, x=1))))
    assert main([str(path), "--output", str(output)]) == 1
    assert not output.exists()


def test_cli_output_is_create_only_and_includes_input_digest(tmp_path):
    path, output = tmp_path / "capture.json", tmp_path / "result.json"
    path.write_text(json.dumps(capture(tile(), tile(2, x=1))))
    args = [str(path), "--output", str(output)]
    assert main(args) == 0
    original = output.read_bytes()
    assert json.loads(original)["input_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert main(args) == 1
    assert output.read_bytes() == original
