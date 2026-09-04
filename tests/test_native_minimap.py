import struct

import pytest

from shadowbane_lab.client_observation.native_minimap import (
    NativeMinimapError,
    NativeMinimapObservation,
    NativeMinimapReader,
)


class Process:
    pid = 8652
    executable_name = "sb.exe"
    executable_sha256 = "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13"
    pointer_size = 4
    base_address = 0x400000

    def __init__(self):
        self.memory = {}
        self.hits = [0x200000]
        self.closed = False
        self.changing = False
        self.reads = 0
        self.put(0x15661A4, struct.pack("<f", 0.13))
        for slot, target in ((0x14C, 0x10A87), (0x154, 0x87EC), (0x158, 0x20478)):
            self.put(0x156DA48 + slot, struct.pack("<I", 0x400000 + target))
        self.parent = bytearray(0x380)
        struct.pack_into("<2I", self.parent, 0, 0x156DA48, 0x156DA0C)
        struct.pack_into("<4i", self.parent, 8, 1710, 14, 1920, 224)
        struct.pack_into("<2I", self.parent, 0x54, 0x210000, 0x210004)
        struct.pack_into("<f", self.parent, 0x37C, 2.078929901123047)
        self.child = bytearray(0x2F4)
        struct.pack_into("<I4i", self.child, 0, 0x1569EC0, 3, 3, 207, 207)
        struct.pack_into("<I", self.child, 0x2F0, 0x4A)
        self.put(0x210000, struct.pack("<I", 0x220000))
        self.put(0x1569EDC, struct.pack("<I", 0x425167))

    def put(self, address, value):
        self.memory[address] = value

    def read_block(self, address, size):
        if address == 0x200000:
            self.reads += 1
            if self.changing:
                struct.pack_into("<f", self.parent, 0x37C, 2 + (self.reads % 2))
            return bytes(self.parent[:size])
        if address == 0x220000:
            return bytes(self.child[:size])
        return self.memory[address][:size]

    def find_all(self, needles, **kwargs):
        assert kwargs["maximum_results_per_needle"] == 16
        return {needles[0]: self.hits}

    def close(self):
        self.closed = True


def test_live_geometry_uses_content_center_and_actual_zoom():
    process = Process()
    with NativeMinimapReader(process) as reader:
        projection = reader.observe()
        assert projection.center == (1815, 119)
        assert (projection.left, projection.top, projection.right, projection.bottom) == (
            1713,
            17,
            1917,
            221,
        )
        assert projection.pixels_per_world_unit == pytest.approx(0.270260877)
        assert projection.destination_pixel(
            lt=89054.25, lg=44857, player_lt=89009.25, player_lg=44857, radius_x=82, radius_y=82
        ) == (1827, 119)
        assert projection.destination_pixel(
            lt=88964.25, lg=44857, player_lt=89009.25, player_lg=44857, radius_x=82, radius_y=82
        ) == (1803, 119)
        assert projection.destination_pixel(
            lt=89009.25, lg=44902, player_lt=89009.25, player_lg=44857, radius_x=82, radius_y=82
        ) == (1815, 107)
    assert process.closed


def test_far_destination_is_shortened_but_near_destination_is_not_extended():
    p = NativeMinimapObservation(0, 0, 210, 210, 0.25)

    def project(lt, lg):
        return p.destination_pixel(lt=lt, lg=lg, player_lt=0, player_lg=0, radius_x=80, radius_y=80)

    assert project(40, 0) == (115, 105)
    assert project(1000, 0) == (185, 105)
    assert project(1000, 1000) == (162, 48)
    assert project(0, 0) == (105, 105)


def test_zoom_changes_are_observed_and_never_use_a_cached_scale():
    process = Process()
    reader = NativeMinimapReader(process)
    first = reader.observe()
    struct.pack_into("<f", process.parent, 0x37C, 4)
    assert reader.observe().pixels_per_world_unit > first.pixels_per_world_unit
    process.changing = True
    with pytest.raises(NativeMinimapError, match="changed during every"):
        reader.observe()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: setattr(p, "executable_sha256", "a" * 64),
        lambda p: setattr(p, "pointer_size", 8),
        lambda p: p.put(0x15661A4, struct.pack("<f", 0.25)),
        lambda p: p.put(0x156DA48 + 0x14C, struct.pack("<I", 0x401234)),
    ],
)
def test_unreviewed_identity_scale_or_dispatch_is_rejected(mutation):
    p = Process()
    mutation(p)
    with pytest.raises(NativeMinimapError):
        NativeMinimapReader(p)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.parent.__setitem__(0xD0, 1),
        lambda p: struct.pack_into("<I", p.parent, 4, 0x156DA10),
        lambda p: struct.pack_into("<f", p.parent, 0x37C, float("nan")),
        lambda p: struct.pack_into("<2I", p.parent, 0x54, 0x210000, 0x310000),
        lambda p: struct.pack_into("<4i", p.child, 4, -1, 3, 207, 207),
        lambda p: p.put(0x1569EDC, struct.pack("<I", 0x401234)),
        lambda p: setattr(p, "hits", []),
        lambda p: setattr(p, "hits", [0x200000, 0x200000]),
    ],
)
def test_invalid_or_ambiguous_live_geometry_fails_closed(mutation):
    p = Process()
    mutation(p)
    with pytest.raises(NativeMinimapError):
        NativeMinimapReader(p).observe()


def test_parent_rectangle_is_used_only_when_content_child_is_absent():
    p = Process()
    struct.pack_into("<2I", p.parent, 0x54, 0, 0)
    assert NativeMinimapReader(p).observe().left == 1710


def test_closed_and_partial_reads_are_rejected():
    p = Process()
    reader = NativeMinimapReader(p)
    reader.close()
    with pytest.raises(NativeMinimapError, match="closed"):
        reader.observe()
    p = Process()
    p.parent = p.parent[:12]
    with pytest.raises(NativeMinimapError):
        NativeMinimapReader(p).observe()
