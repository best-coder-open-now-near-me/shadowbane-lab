import ctypes
import hashlib
import json
import math
import struct
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.graphics_lab import sky
from shadowbane_lab.graphics_lab.sky_panel import SkyPanel


def test_asset_identity_and_authored_content():
    folder = Path(__file__).resolve().parents[1] / "assets/sky-horizon"
    data = json.loads((folder / "clear-day.json").read_text())
    values = []
    for field in ("zenith", "horizon", "nadir", "sun", "sun_color", "cloud_color"):
        values.extend(data[field])
    for cloud in data["clouds"]:
        az, el = map(math.radians, (cloud["azimuth"], cloud["elevation"]))
        values.extend(
            (
                math.sin(az) * math.cos(el),
                math.sin(el),
                -math.cos(az) * math.cos(el),
                math.cos(az),
                0,
                math.sin(az),
                math.sin(math.radians(cloud["width"])),
                math.sin(math.radians(cloud["height"])),
                cloud["opacity"],
            )
        )
    expected = struct.pack("<4I126f", 0x594B5357, 1, 12, 520, *values)
    content = (folder / "clear-day.sky").read_bytes()
    assert content == expected
    assert hashlib.sha256(content).hexdigest() == sky.ASSET_SHA256
    assert json.loads((folder / "manifest.json").read_text())["sha256"] == sky.ASSET_SHA256


@pytest.mark.parametrize(
    "field,bad",
    [
        ("enabled", 2),
        ("enabled", True),
        ("intensity", math.nan),
        ("sun", math.inf),
        ("clouds", -1),
        ("orientation", 181),
        ("horizon_width", 0),
        ("fog_match", "1"),
    ],
)
def test_invalid_settings(field, bad):
    with pytest.raises(ValueError):
        replace(sky.SkySettings(), **{field: bad}).pack()


def test_float_endpoints_and_preset_roundtrip():
    for field, (low, high) in sky.RANGES.items():
        for endpoint in (low, high):
            value = replace(sky.SkySettings(), **{field: endpoint})
            assert getattr(sky.unpack(value.pack()), field) == pytest.approx(endpoint)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "appearance.json"
        expected = sky.SkySettings(enabled=1, orientation=73)
        sky.save_settings(path, expected)
        assert sky.load_settings(path) == expected
        assert list(Path(temporary).iterdir()) == [path]
        data = json.loads(path.read_text())
        data["asset_sha256"] = "0" * 64
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            sky.load_settings(path)


def client_buffer():
    client = sky.SkyClient.__new__(sky.SkyClient)
    client.target = SimpleNamespace(process_id=321, process_creation_filetime_utc=456)
    client._mutex = 1
    data = sky.HEADER.pack(0x534B4257, 1, sky.SIZE, 321, 456, 2, 2, 0, 0)
    data += sky.SkySettings(enabled=1).pack() + bytes(32) + bytes.fromhex(sky.ASSET_SHA256)
    buffer = ctypes.create_string_buffer(data)
    client._address = ctypes.addressof(buffer)
    return client, buffer


def test_channel_identity_torn_reads_and_safe_restore():
    client, buffer = client_buffer()
    assert client.read()[0].enabled == 1
    kernel = Mock()
    kernel.WaitForSingleObject.return_value = 0
    with patch.object(sky.control, "_kernel32", kernel):
        # Invalid channel settings may be repaired, but the exact-process header and asset
        # are revalidated before any write. This supports restore-original after corruption.
        ctypes.c_float.from_address(client._address + 48).value = math.nan
        with pytest.raises(ValueError):
            client.read()
        assert client.write(sky.SkySettings()) == 4
        assert client.read()[0].enabled == 0
        ctypes.c_long.from_address(client._address + 24).value = 5
        with pytest.raises(RuntimeError):
            client.read()
        ctypes.c_long.from_address(client._address + 24).value = 6
        ctypes.c_uint.from_address(client._address + 12).value = 999
        with pytest.raises(ValueError):
            client.write(sky.SkySettings())
    assert buffer.raw


def test_disable_ignores_bad_pending_field_edits():
    client = Mock()
    client.read.return_value = (sky.SkySettings(enabled=1), (), 0, 0, 0)
    panel = SimpleNamespace(
        client=client,
        enabled=Mock(),
        status=Mock(),
        get=Mock(side_effect=ValueError("bad unapplied edit")),
    )
    SkyPanel.disable(panel)
    assert client.write.call_args.args[0].enabled == 0
    panel.get.assert_not_called()


def test_sky_panel_uses_existing_connected_app():
    import tkinter as tk

    from shadowbane_lab.graphics_lab import app as module

    with patch.object(module, "discover_graphics_targets", return_value=()):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            pytest.skip(f"Windowing unavailable: {error}")
        root.withdraw()
        application = module.GraphicsLabApp(root)
        assert application.sky_panel.get() == sky.SkySettings()
        application.close()
