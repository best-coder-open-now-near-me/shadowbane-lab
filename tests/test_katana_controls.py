import ctypes
import math
from types import SimpleNamespace

import pytest

from shadowbane_lab.graphics_lab import katana


def block(length=1, desired=0, pid=7):
    return katana.HEADER.pack(0x4B574257, 1, 64, pid, 1234, desired, 0, 0, length, 2, 0) + bytes(16)


def test_wire_identity_and_ranges():
    target = SimpleNamespace(process_id=7, process_creation_filetime_utc=1234)
    assert katana.unpack(block(), target) == (1, 0, 0, 0, 2, 0)
    for length in [0.6, 0.85, 1.2]:
        assert math.isclose(katana.unpack(block(length), target)[0], length, abs_tol=1e-6)
    for data in [block(pid=8), block(desired=1), block(float("nan")), block(0.5), block(1.3), b""]:
        with pytest.raises(ValueError):
            katana.unpack(data, target)


def test_writer_bounds_and_sequencing(monkeypatch):
    memory = ctypes.create_string_buffer(block(), 64)
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
