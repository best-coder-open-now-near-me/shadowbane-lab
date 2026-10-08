import ctypes
import struct
from types import SimpleNamespace

import pytest
from test_object_navigation import _object_payload, _render_payload, _write_cache

from shadowbane_lab.graphics_lab import visual_inspector as vi

TARGET = SimpleNamespace(process_id=42, process_creation_filetime_utc=77)


def wire():
    data = bytearray(vi.SIZE)
    vi.HEADER.pack_into(data, 0, vi.MAGIC, 1, vi.SIZE, 42, 77, 2, 1, 2, 2, 0, 1, 99, 2, 123)
    vi.NODE.pack_into(data, 64, 0x10000, 0xFFFFFFFF, 20, 0)
    vi.NODE.pack_into(data, 80, 0x20000, 0, 21, 0)
    return data


def test_snapshot_parentage_and_exact_identity():
    result = vi.unpack(wire(), TARGET)
    assert result["object_uuid"] == 99
    assert result["nodes"][1]["parent"] == 0
    with pytest.raises(ValueError, match="identity"):
        vi.unpack(wire(), SimpleNamespace(process_id=43, process_creation_filetime_utc=77))


@pytest.mark.parametrize(
    "offset,value",
    [
        (4, 2),
        (24, 3),
        (28, 2),
        (32, 3),
        (40, 7),
        (52, 129),
        (68, 0),
        (84, 2),
        (92, 1),
        (80, 0x10000),
    ],
)
def test_invalid_or_torn_snapshots_rejected(offset, value):
    data = wire()
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError):
        vi.unpack(data, TARGET)


def test_enrich_preserves_ambiguous_ids_and_labels_candidates(tmp_path):
    _write_cache(
        tmp_path / "Render.cache",
        [
            (0, 20, _render_payload(mesh_ids=(30,), collides=False, texture=True)),
            (1, 20, _render_payload(collides=False)),
            (0, 21, b"unsupported"),
        ],
    )
    _write_cache(
        tmp_path / "CObjects.cache",
        [
            (0, 1, _object_payload("Sword A", 20)),
            (0, 2, _object_payload("Sword B", 20)),
            (0, 3, b"opaque"),
        ],
    )
    report = vi.enrich(vi.unpack(wire(), TARGET), tmp_path)
    first = report["nodes"][0]
    assert first["resolution"] == "ambiguous groups/records"
    assert len(first["templates"]) == 2
    template = first["templates"][0]
    assert template["texture_keys"] == ["0:901"]
    assert template["mesh_keys"] == ["0:30"]
    assert len(template["object_candidates"]) == 2
    assert "not verified" in template["object_candidates"][0]["match"]
    assert "error" in report["nodes"][1]["templates"][0]
    assert any("1 CObject" in warning for warning in report["warnings"])
    assert template["missing_resources"] == ["Mesh 0:30: 0 matches", "Textures 0:901: 0 matches"]


def test_nested_animated_texture_references():
    from test_object_navigation import _key, _single_texture

    from shadowbane_lab.world_data.object_navigation import parse_render_navigation_metadata

    payload = _render_payload(collides=False, texture=True)
    leaf = _single_texture()
    animated = (
        struct.pack("<I", 3)
        + _key(999)
        + struct.pack("<I4B", 0, 0, 0, 0, 1)
        + struct.pack("<ffII", 1.0, 1.0, 0, 1)
        + leaf
    )
    meta = parse_render_navigation_metadata(payload.replace(leaf, animated))
    assert [k.resource_id for k in meta.texture_keys] == [999, 901]


def test_request_changes_only_request_fields(monkeypatch):
    data = wire()
    storage = ctypes.create_string_buffer(bytes(data), vi.SIZE)
    api = SimpleNamespace(WaitForSingleObject=lambda *_: 0, ReleaseMutex=lambda *_: None)
    monkeypatch.setattr(vi.control, "_kernel32", api)
    monkeypatch.setattr(vi.control, "target_process_is_alive", lambda _: True)
    client = vi.VisualInspectorClient.__new__(vi.VisualInspectorClient)
    client.target = TARGET
    client.address = ctypes.addressof(storage)
    client.mutex = 1
    assert client.request(0) == 4
    after = storage.raw
    assert after[:24] == data[:24] and after[32:] == data[32:]
    assert struct.unpack_from("<2I", after, 24) == (4, 0)
    with pytest.raises(ValueError):
        client.request(True)
