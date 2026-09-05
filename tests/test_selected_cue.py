import struct
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.graphics_lab.control import GraphicsControlTarget
from shadowbane_lab.graphics_lab.selected_cue import HEADER, MAGIC, SIZE, CueSettings, unpack


def target():
    return GraphicsControlTarget(
        123, 0x1122334455667788, Path("sb.exe"), "a" * 64, "unused", Path("status")
    )


def frame(settings=None):
    settings = settings or CueSettings()
    return (
        HEADER.pack(MAGIC, 1, SIZE, 123, 0x55667788, 0x11223344, 2, 2, 0, 0)
        + settings.pack()
        + struct.pack("<4I", 1, 3, 0, 0)
    )


def test_native_abi_and_settings_roundtrip():
    settings, status = unpack(frame(), target())
    assert settings.enabled is False
    assert settings.red == pytest.approx(0.2)
    assert status == (2, 2, 0, 0, 1, 3, 0, 0)
    assert len(frame()) == 88


@pytest.mark.parametrize(
    "offset,value", [(0, 0), (4, 2), (8, 89), (12, 1), (16, 1), (20, 1), (24, 3), (40, 2)]
)
def test_bad_identity_version_sequence_or_enable_rejected(offset, value):
    data = bytearray(frame())
    struct.pack_into("<I", data, offset, value)
    with pytest.raises(ValueError):
        unpack(data, target())


@pytest.mark.parametrize(
    "key,value",
    [
        ("opacity", float("nan")),
        ("radius", 13),
        ("red", -1),
        ("indicator_y", 0.05),
        ("indicator_size", 100),
        ("enabled", 1),
    ],
)
def test_invalid_appearance_rejected(key, value):
    with pytest.raises(ValueError):
        replace(CueSettings(), **{key: value}).pack()


def test_wrong_process_lifetime_rejected():
    with pytest.raises(ValueError):
        unpack(frame(), replace(target(), process_creation_filetime_utc=2))


def test_missing_block_rejected():
    with pytest.raises(ValueError):
        unpack(b"", target())
