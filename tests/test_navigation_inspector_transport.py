"""Real Windows mapping lifecycle and pure control-boundary tests."""

import ctypes
import hashlib
import os
import struct
import sys
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.graphics_lab.control import GraphicsControlTarget
from shadowbane_lab.navigation_inspector.events import ContextEvent, MotionEvent
from shadowbane_lab.navigation_inspector.geometry import prepare_geometry
from shadowbane_lab.navigation_inspector.protocol import (
    HEADER,
    MAGIC,
    VERSION,
    encode_frame,
    mapping_name,
)
from shadowbane_lab.navigation_inspector.snapshot import Collector, SourceIdentity
from shadowbane_lab.navigation_inspector.transport import (
    MAPPING_BYTES,
    Channel,
    Controls,
    _windows_api,
)


def target():
    return GraphicsControlTarget(42, 123, Path("sb.exe"), "a" * 64, "unused", Path("status.json"))


def test_control_identity_checksum_and_session():
    settings = Controls(2, 17, xray=True, command=1)
    payload = settings.encode(target())
    assert Controls.decode(payload, target(), 17, 2) == settings
    for identity, session, after in (
        (replace(target(), process_id=43), 17, 2),
        (target(), 18, 2),
        (target(), 17, 4),
    ):
        with pytest.raises(ValueError):
            Controls.decode(payload, identity, session, after)
    changed = bytearray(payload)
    changed[52] ^= 1
    with pytest.raises(ValueError, match="checksum"):
        Controls.decode(bytes(changed), target(), 17, 2)


@pytest.fixture
def live_mapping():
    if os.name != "nt":
        pytest.skip("real Win32 mapping lifecycle")
    api = _windows_api()
    api.CreateFileMappingW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    api.CreateFileMappingW.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.GetProcessTimes.restype = wintypes.BOOL
    process = api.OpenProcess(0x1000, False, os.getpid())
    times = [wintypes.FILETIME() for _ in range(4)]
    assert api.GetProcessTimes(process, *(ctypes.byref(value) for value in times))
    api.CloseHandle(process)
    creation = times[0].dwLowDateTime | (times[0].dwHighDateTime << 32)
    executable = Path(sys.executable).resolve()
    identity = GraphicsControlTarget(
        os.getpid(),
        creation,
        executable,
        hashlib.sha256(executable.read_bytes()).hexdigest(),
        "unused",
        Path("unused"),
    )
    handle = api.CreateFileMappingW(
        ctypes.c_void_p(-1).value,
        None,
        4,
        0,
        MAPPING_BYTES,
        mapping_name(identity.process_id, creation),
    )
    assert handle
    address = api.MapViewOfFile(handle, 6, 0, 0, MAPPING_BYTES)
    assert address
    header = bytearray(HEADER.size)
    struct.pack_into(
        "<6IQ", header, 0, MAGIC, VERSION, HEADER.size, 0, identity.process_id, 0, creation
    )
    ctypes.memmove(address, bytes(header), len(header))
    try:
        yield identity, address, api
    finally:
        api.UnmapViewOfFile(address)
        api.CloseHandle(handle)


def test_real_mapping_publisher_panel_reader_and_exclusive_ownership(live_mapping):
    identity, address, api = live_mapping
    with (
        Channel(identity, role="producer") as writer,
        Channel(identity, role="panel") as panel,
        Channel(identity) as reader,
    ):
        with pytest.raises(OSError, match="already owns"):
            Channel(identity, role="producer")
        with pytest.raises(ValueError, match="complete"):
            reader.read()
        collector = Collector(
            SourceIdentity(
                identity.process_id,
                identity.process_creation_filetime_utc,
                identity.executable_sha256,
                "unavailable",
                "test",
                "unavailable",
            ),
            17,
        )
        now = writer.clock_ms()
        collector.observe(ContextEvent("context", "test-zone", "map", "fixture only"), now)
        collector.observe(MotionEvent("motion", "observation", "test", 0, position=(3, 4, 5)), now)
        snapshot = collector.snapshot()
        payload = encode_frame(
            snapshot, prepare_geometry(snapshot), sequence=2, lease_ms=now, live_zone="test-zone"
        )
        writer.publish(payload)
        assert reader.snapshot(reader.read()) == snapshot
        controls = Controls(2, 17, enabled=False, command=1)
        panel.set_controls(controls)
        assert writer.controls(17) == controls
        assert writer.controls(18) is None
        ctypes.c_uint32.from_address(address + 12).value = 3
        with pytest.raises(ValueError, match="complete"):
            reader.read()
        writer.publish(payload)
        ctypes.c_uint32.from_address(address + 8).value = MAPPING_BYTES + 1
        with pytest.raises(ValueError, match="capacity"):
            reader.read()
        writer.publish(payload)
    # Closing releases both the handle and the lifetime ownership claim.
    with Channel(identity, role="producer") as reopened:
        assert reopened.snapshot(reopened.read()) == snapshot


def test_wrong_client_creation_and_channel_header_fail_closed(live_mapping):
    identity, address, _api = live_mapping
    with pytest.raises(OSError, match="identity"):
        Channel(replace(identity, process_creation_filetime_utc=1), role="producer")
    ctypes.c_uint32.from_address(address + 16).value = identity.process_id + 1
    with pytest.raises(OSError, match="identity"):
        Channel(identity, role="producer")
    ctypes.c_uint32.from_address(address + 16).value = identity.process_id
    with Channel(identity, role="producer"):
        pass
