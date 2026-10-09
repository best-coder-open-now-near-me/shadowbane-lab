import ctypes
import math
from types import SimpleNamespace

import pytest

from shadowbane_lab.graphics_lab import katana


def block(length=1, desired=0, pid=7, selection=0, version=3):
    return katana.HEADER.pack(
        0x4B574257,
        version,
        96,
        pid,
        1234,
        desired,
        0,
        0,
        length,
        2,
        0,
        *katana.FireSettings().values(),
        0,
        0,
        selection,
    ) + bytes(8)


def test_wire_identity_and_ranges():
    target = SimpleNamespace(process_id=7, process_creation_filetime_utc=1234)
    assert katana.unpack(block(), target)[:6] == (1, 0, 0, 0, 2, 0)
    for length in [0.6, 0.85, 1.2]:
        assert math.isclose(katana.unpack(block(length), target)[0], length, abs_tol=1e-6)
    for data in [block(pid=8), block(desired=1), block(float("nan")), block(0.5), block(1.3), b""]:
        with pytest.raises(ValueError):
            katana.unpack(data, target)


def test_writer_bounds_and_sequencing(monkeypatch):
    memory = ctypes.create_string_buffer(block(), 96)
    client = katana.KatanaClient.__new__(katana.KatanaClient)
    client.address = ctypes.addressof(memory)
    client.mutex = 1
    client.target = SimpleNamespace(process_id=7, process_creation_filetime_utc=1234)
    monkeypatch.setattr(katana.control, "target_process_is_alive", lambda _: True)
    released = []
    api = SimpleNamespace(
        WaitForSingleObject=lambda *_: 0, ReleaseMutex=lambda _: released.append(1)
    )
    monkeypatch.setattr(katana.control, "_kernel32", api)
    for value in [60, 85, 100, 120]:
        client.write(value)
        length, desired, *_ = client.read()
        assert math.isclose(length, value / 100, abs_tol=1e-6) and desired % 2 == 0
    assert len(released) == 4
    before = memory.raw
    for value in [True, 0, 121, float("nan")]:
        with pytest.raises(ValueError):
            client.write(value)
    assert memory.raw == before


def test_fire_writer_preserves_length_and_rejects_invalid_settings(monkeypatch):
    memory = ctypes.create_string_buffer(block(0.8), 96)
    client = katana.KatanaClient.__new__(katana.KatanaClient)
    client.address = ctypes.addressof(memory)
    client.mutex = 1
    client.target = SimpleNamespace(process_id=7, process_creation_filetime_utc=1234)
    monkeypatch.setattr(katana.control, "target_process_is_alive", lambda _: True)
    monkeypatch.setattr(
        katana.control,
        "_kernel32",
        SimpleNamespace(WaitForSingleObject=lambda *_: 0, ReleaseMutex=lambda _: None),
    )
    client.write(80, katana.FireSettings(enabled=0, pulse=0, strength=0))
    snapshot = client.read()
    assert math.isclose(snapshot[0], 0.8, abs_tol=1e-6)
    assert snapshot[6].enabled == 0 and snapshot[6].pulse == 0 and snapshot[6].strength == 0
    client.write(85)
    assert client.read()[6] == snapshot[6]
    before = memory.raw
    for settings in (
        katana.FireSettings(enabled=2),
        katana.FireSettings(size=float("nan")),
        katana.FireSettings(width=5),
    ):
        with pytest.raises(ValueError):
            client.write(80, settings)
    assert memory.raw == before


def test_selected_character_protocol_and_writer(monkeypatch):
    target = SimpleNamespace(process_id=7, process_creation_filetime_utc=1234)
    assert katana.unpack(block(selection=1), target)[9] == 1
    for data in (block(version=2), block(selection=2)):
        with pytest.raises(ValueError):
            katana.unpack(data, target)
    memory = ctypes.create_string_buffer(block(0.8), 96)
    client = katana.KatanaClient.__new__(katana.KatanaClient)
    client.address = ctypes.addressof(memory)
    client.mutex = 1
    client.target = target
    monkeypatch.setattr(katana.control, "target_process_is_alive", lambda _: True)
    monkeypatch.setattr(katana.control, "_kernel32", SimpleNamespace(
        WaitForSingleObject=lambda *_: 0, ReleaseMutex=lambda _: None,
    ))
    original_fire = client.read()[6]
    client.write(80, selection=1)
    assert client.read()[9] == 1 and client.read()[6] == original_fire
    client.write(85)
    assert client.read()[9] == 1
    before = memory.raw
    for selection in (True, -1, 2, 1.0, "1"):
        with pytest.raises(ValueError):
            client.write(80, selection=selection)
    assert memory.raw == before
    client.write(85, selection=0)
    assert client.read()[9] == 0
