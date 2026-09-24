"""Bounded copied resource evidence for one owned furnishing row.

No selection, native retain, loading, cloning, drawing or readiness inference.
Unknown classes remain references and do not grant access to class fields.
"""
from __future__ import annotations

import math
import struct

from .native_vendor_dialog import NativeVendorDialogCaptureError
from .native_vendor_queue import _ReadSet

STATIC_MODEL_RVA = 0x1143540
RENDER_RVA = 0x1149DBC
TEMPLATE_RVA = 0x114A074
MESH_SET_RVA = 0x11499F4
TEXTURE_SET_RVA = 0x114A5A4
SINGLE_TEXTURE_RVA = 0x114A2F4
MAX_RENDER_NODES = 64
MAX_RENDER_DEPTH = 8
MAX_SET_MEMBERS = 16
MAX_TOTAL_SET_MEMBERS = 256


def _object_reference(r: _ReadSet, pointer: int) -> dict[str, int] | None:
    if not pointer:
        return None
    table = r.word(pointer)
    if not r.memory.base_address <= table < 0x80000000 or table % 4:
        raise NativeVendorDialogCaptureError("invalid furnishing object class")
    return {"address": pointer, "class_rva": table - r.memory.base_address}


def _reference(r: _ReadSet, address: int) -> dict[str, int] | None:
    """Record a borrowed reference without interpreting an unreviewed class."""
    return _object_reference(r, r.word(address))


def _tqs(r: _ReadSet, address: int) -> list[float]:
    values = struct.unpack("<10f", r.read(address, 40))
    if not all(math.isfinite(value) for value in values):
        raise NativeVendorDialogCaptureError("nonfinite furnishing render transform")
    return list(values)


def read_render_resources(r: _ReadSet, model: dict[str, int] | None) -> dict[str, object]:
    """Use the caller's ownership/read set; caller must reverse-verify afterward.

    Called only for a specifically requested owned row, irrespective of native
    selection. References are evidence, never handles that a renderer may use.
    """
    result: dict[str, object] = {
        "scope": "owned_row_resource_evidence", "model_reference": model,
        "root_reference": None, "nodes": [], "unreviewed_class_rvas": [],
        "selection_admitted": False, "render_lifetime_owned": False,
        "resource_readiness_verified": False, "native_calls_made": False,
    }
    nodes: list[dict[str, object]] = []
    unknown: set[int] = set()
    seen: set[int] = set()
    member_count = 0
    base = r.memory.base_address

    def known(reference: dict[str, int] | None, expected: int) -> bool:
        if reference and reference["class_rva"] != expected:
            unknown.add(reference["class_rva"])
        return reference is not None and reference["class_rva"] == expected

    def members(pointer: int) -> tuple[int, ...]:
        nonlocal member_count
        values = r.vector(pointer + 0x24, MAX_SET_MEMBERS)
        member_count += len(values)
        if member_count > MAX_TOTAL_SET_MEMBERS:
            raise NativeVendorDialogCaptureError("furnishing resource member limit exceeded")
        return values

    def texture_set(reference: dict[str, int] | None) -> dict[str, object]:
        out: dict[str, object] = {"reference": reference}
        if not known(reference, TEXTURE_SET_RVA):
            return out
        assert reference is not None
        pointer = reference["address"]
        textures = []
        for value in members(pointer):
            texture = _object_reference(r, value)
            item: dict[str, object] = {"reference": texture}
            if known(texture, SINGLE_TEXTURE_RVA):
                assert texture is not None
                # +0x5c is retained by native ArcSingleTexture clone 0x1df2d0.
                # Its target class/readiness is deliberately not interpreted.
                item["shared_resource_reference"] = _reference(r, texture["address"] + 0x5C)
            textures.append(item)
        out.update(selected_index_raw=r.word(pointer + 0x30), textures=textures)
        return out

    def template(reference: dict[str, int] | None) -> dict[str, object]:
        out: dict[str, object] = {"reference": reference}
        if not known(reference, TEMPLATE_RVA):
            return out
        assert reference is not None
        mesh_set = _reference(r, reference["address"] + 0x1C)
        out["mesh_set_reference"] = mesh_set
        if known(mesh_set, MESH_SET_RVA):
            assert mesh_set is not None
            pointer = mesh_set["address"]
            out["mesh_references"] = [_object_reference(r, value) for value in members(pointer)]
            out["mesh_selected_index_raw"] = r.word(pointer + 0x30)
        return out

    def visit(reference: dict[str, int] | None, depth: int) -> None:
        if reference is None:
            raise NativeVendorDialogCaptureError("null furnishing render child")
        pointer = reference["address"]
        if pointer in seen:
            raise NativeVendorDialogCaptureError("repeated furnishing render node")
        if depth > MAX_RENDER_DEPTH or len(seen) >= MAX_RENDER_NODES:
            raise NativeVendorDialogCaptureError("furnishing render graph limit exceeded")
        seen.add(pointer)
        node: dict[str, object] = {"reference": reference, "depth": depth}
        nodes.append(node)
        if not known(reference, RENDER_RVA):
            return
        r.require(pointer + 0x30, base + 0x1149D94, "static render interface")
        children = r.vector(pointer + 0x3C, MAX_RENDER_NODES)
        feature = r.read(pointer + 0x148, 4)
        special = r.read(pointer + 0xF0, 4)
        opacity = struct.unpack("<f", r.read(pointer + 0xCC, 4))[0]
        if not math.isfinite(opacity):
            raise NativeVendorDialogCaptureError("nonfinite furnishing render opacity")
        node.update(
            child_addresses_raw=list(children),
            callback_flags_raw=r.read(pointer + 0x38, 4)[0],
            world_tqs_raw=_tqs(r, pointer + 0x48),
            local_tqs_raw=_tqs(r, pointer + 0x70),
            opacity_raw=opacity, feature_flags_raw=list(feature[:2]),
            special_flags_raw=list(special[:2]),
            # This borrowed target is not necessarily polymorphic; no dereference.
            special_data_address_raw=r.word(pointer + 0xF4),
            template=template(_reference(r, pointer + 0xC4)),
            texture_set=texture_set(_reference(r, pointer + 0xE8)),
        )
        for child in children:
            visit(_object_reference(r, child), depth + 1)

    if known(model, STATIC_MODEL_RVA):
        assert model is not None
        r.require(model["address"] + 0x44, base + 0x114350C, "static model interface")
        root = _reference(r, model["address"] + 0xC0)
        result["root_reference"] = root
        if root is not None:
            visit(root, 0)
    result["nodes"] = nodes
    result["unreviewed_class_rvas"] = sorted(unknown)
    return result
