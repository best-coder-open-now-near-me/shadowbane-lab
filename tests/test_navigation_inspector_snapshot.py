"""Failure-oriented tests through planner, collector, saved capture and viewer wire."""

import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.navigation_inspector.events import ContextEvent, MotionEvent
from shadowbane_lab.navigation_inspector.geometry import (
    WORLD_HEIGHT,
    Layer,
    prepare_geometry,
    swept_circle_overlaps_cell,
)
from shadowbane_lab.navigation_inspector.protocol import (
    decode_frame,
    encode_frame,
    zone_identity,
)
from shadowbane_lab.navigation_inspector.snapshot import (
    MAX_EVENTS,
    MAX_TRAIL,
    Clearance,
    Collector,
    Snapshot,
    SourceIdentity,
)
from shadowbane_lab.travel import (
    NavigationCell,
    SparseNavigationMap,
    TravelDestination,
    WeightedAStarConfig,
    WeightedAStarPlanner,
)


def collector_with_route():
    identity = SourceIdentity(42, 123456, "a" * 64, "b" * 40, "0.1.0", "unavailable")
    collector = Collector(identity, 17, clearance=Clearance(4, 1, 1))
    collector.observe(
        ContextEvent(
            "context", "zone-A", "map-1", "raster discontinuity cells; density is uncertain"
        ),
        100,
    )
    navigation = SparseNavigationMap(cell_size=10)
    navigation.mark_blocked(NavigationCell(3, 1))
    navigation.set_cost(NavigationCell(4, 2), 5)
    WeightedAStarPlanner(
        WeightedAStarConfig(obstacle_clearance_cells=0),
        observer=lambda e: collector.observe(e, 101),
    ).plan(navigation, start_lt=5, start_lg=5, destination=TravelDestination(95, 5, 5))
    collector.observe(MotionEvent("motion", "observation", "go-1", 10, position=(5, 5, 12)), 102)
    collector.observe(
        MotionEvent(
            "motion", "command_requested", "go-1", 20, position=(6, 5, 12.5), destination=(95, 5, 5)
        ),
        103,
    )
    return collector


def test_capture_round_trip_preserves_exact_failure_and_does_not_overwrite(tmp_path):
    collector = collector_with_route()
    collector.observe(
        MotionEvent("motion", "failure", "go-1", 30, position=(6, 5, 12.5), reason="stalled"), 104
    )
    snapshot = collector.snapshot()
    assert snapshot.frozen
    destination = tmp_path / "failure.json"
    snapshot.save(destination)
    loaded = Snapshot.load(destination)
    assert loaded == snapshot
    assert loaded.events[-1].value.reason == "stalled"
    assert loaded.identity.extension_sha256 == "unavailable"
    with pytest.raises(FileExistsError):
        loaded.save(destination)


def test_freeze_retains_failure_but_cannot_cross_zone_boundary():
    collector = collector_with_route()
    collector.freeze()
    frozen = collector.snapshot()
    collector.observe(MotionEvent("motion", "observation", "go-1", 100, position=(25, 5, 14)), 120)
    assert collector.snapshot() == frozen
    collector.resume()
    assert collector.snapshot().trail[-1] == (25, 5, 14)
    collector.freeze()
    collector.observe(ContextEvent("context", "zone-B", "map-2", "raster"), 130)
    snapshot = collector.snapshot()
    assert not snapshot.frozen
    assert snapshot.plan is snapshot.active is None
    assert snapshot.trail == snapshot.events == ()
    assert snapshot.context.zone_token == "zone-B"


def test_event_and_trail_history_is_bounded_and_reports_loss():
    collector = collector_with_route()
    for i in range(MAX_TRAIL + 10):
        collector.observe(
            MotionEvent("motion", "command_requested", "go-1", i, position=(i, 5, 12)), 100 + i
        )
    snapshot = collector.snapshot()
    assert len(snapshot.events) == MAX_EVENTS
    assert len(snapshot.trail) == MAX_TRAIL
    assert snapshot.omitted_events > 0 and snapshot.omitted_trail > 0
    assert Snapshot.from_bytes(snapshot.to_bytes()) == snapshot


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema=2),
        lambda d: d.update(frozen=1),
        lambda d: d.update(trail=[[float("nan"), 1, 2]]),
        lambda d: d.update(trail=[[1, 2, 3]] * (MAX_TRAIL + 1)),
        lambda d: d["identity"].update(process_id=True),
        lambda d: d["plan"].update(physical_blocked=[[0.5, 1]]),
        lambda d: d["plan"].update(destination=[1, 2, -1]),
        lambda d: d["clearance"].update(character_radius=-1),
        lambda d: d["context"].update(height_provenance="x" * 513),
        lambda d: d.update(unrecognized="not versioned"),
    ],
)
def test_replay_rejects_invalid_capture(mutate):
    data = json.loads(collector_with_route().snapshot().to_bytes())
    mutate(data)
    with pytest.raises(ValueError):
        Snapshot.from_bytes(json.dumps(data).encode())


def test_duplicate_fields_and_oversized_input_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        Snapshot.from_bytes(b'{"schema":1,"schema":1}')
    with pytest.raises(ValueError, match="capacity"):
        Snapshot.from_bytes(b" " * 1_048_577)


@pytest.mark.parametrize(
    "start,end,radius,expected",
    [
        ((-5, -1), (15, -1), 0, False),
        ((-5, -1), (15, -1), 1, True),
        ((-2, -2), (-1, -1), 1, False),  # square inflation would incorrectly hit
        ((-2, -2), (-1, -1), 1.42, True),
        ((5, 5), (5, 5), 0, True),
        ((-5, 5), (15, 5), 0, True),
        ((5, -5), (5, 15), 0, True),
        ((20, 20), (30, 30), 4, False),
    ],
)
def test_swept_corridor_includes_real_round_caps(start, end, radius, expected):
    assert swept_circle_overlaps_cell(start, end, (0, 0), 10, radius) is expected


def test_clearance_finds_clipping_while_centerline_and_planner_are_clear():
    snapshot = collector_with_route().snapshot()
    assert snapshot.plan.physical_blocked == ((3, 1),)
    assert snapshot.plan.planner_clearance_cells == 0
    geometry = prepare_geometry(snapshot)
    assert geometry.audit.physical_overlap_segments == (0,)
    narrow = prepare_geometry(replace(snapshot, clearance=Clearance(4, 0, 0)))
    assert not narrow.audit.physical_overlap_segments
    assert all(line.layer == Layer.TRAIL for line in geometry.lines if line.flags & WORLD_HEIGHT)
    trail = next(line for line in geometry.lines if line.layer == Layer.TRAIL)
    assert trail.start == (5, 12, -5) and trail.end == (6, 12.5, -5)
    assert any(line.layer == Layer.UNCERTAIN for line in geometry.lines)


def frame_data(frozen=False):
    collector = collector_with_route()
    if frozen:
        collector.freeze()
    snapshot = collector.snapshot()
    return encode_frame(
        snapshot, prepare_geometry(snapshot), sequence=2, lease_ms=150, live_zone="zone-A"
    )


def test_wire_round_trip_and_saved_evidence_agree():
    frame = decode_frame(
        frame_data(), process_id=42, process_creation=123456, now_ms=200, sequence_after=2
    )
    saved = Snapshot.from_bytes(frame.capture)
    assert frame.session_id == saved.session_id
    assert frame.zone_id == zone_identity(saved.context.zone_token)
    assert frame.route_revision == saved.route_revision
    expected = prepare_geometry(saved).lines
    assert len(frame.lines) == len(expected)
    for actual, original in zip(frame.lines, expected, strict=True):
        assert (actual.layer, actual.flags) == (original.layer, original.flags)
        assert actual.start == pytest.approx(original.start)
        assert actual.end == pytest.approx(original.end)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"process_id": 43}, "process"),
        ({"process_creation": 123457}, "process"),
        ({"sequence_after": 4}, "torn"),
        ({"expected_session": 18}, "session"),
        ({"expected_zone": zone_identity("zone-B")}, "zone"),
        ({"now_ms": 2200}, "lease"),
        ({"now_ms": 149}, "lease"),
    ],
)
def test_wire_rejects_wrong_identity_torn_or_stale_frames(kwargs, match):
    options = dict(process_id=42, process_creation=123456, now_ms=200)
    options.update(kwargs)
    with pytest.raises(ValueError, match=match):
        decode_frame(frame_data(), **options)


def test_checksum_covers_header_and_payload():
    for offset in (48, 128, len(frame_data()) - 1):
        payload = bytearray(frame_data())
        payload[offset] ^= 1
        with pytest.raises(ValueError, match="checksum"):
            decode_frame(bytes(payload), process_id=42, process_creation=123456, now_ms=200)


def test_freeze_keeps_old_sample_only_with_current_matching_zone_lease():
    collector = collector_with_route()
    collector.freeze()
    snapshot = collector.snapshot()
    payload = encode_frame(
        snapshot, prepare_geometry(snapshot), sequence=2, lease_ms=9000, live_zone="zone-A"
    )
    decode_frame(payload, process_id=42, process_creation=123456, now_ms=9001)
    changed = encode_frame(
        snapshot, prepare_geometry(snapshot), sequence=4, lease_ms=9000, live_zone="zone-B"
    )
    with pytest.raises(ValueError, match="zone"):
        decode_frame(changed, process_id=42, process_creation=123456, now_ms=9001)
    with pytest.raises(ValueError, match="lease"):
        decode_frame(payload, process_id=42, process_creation=123456, now_ms=12000)
    stale = encode_frame(
        replace(snapshot, frozen=False),
        prepare_geometry(snapshot),
        sequence=6,
        lease_ms=9000,
        live_zone="zone-A",
    )
    with pytest.raises(ValueError, match="stale"):
        decode_frame(stale, process_id=42, process_creation=123456, now_ms=9001)


def test_empty_projection_and_truncation_are_explicit():
    collector = collector_with_route()
    snapshot = replace(collector.snapshot(), plan=None, active=None, trail=(), events=())
    geometry = prepare_geometry(snapshot)
    assert not geometry.lines
    payload = encode_frame(snapshot, geometry, sequence=2, lease_ms=150, live_zone="zone-A")
    assert (
        decode_frame(payload, process_id=42, process_creation=123456, now_ms=200).view_radius == 50
    )
    changed = replace(collector.snapshot(), plan=replace(collector.plan, omitted_map_cells=1))
    assert prepare_geometry(changed).audit.model_truncated


def test_oversized_and_odd_wire_frames_fail_before_geometry_read():
    payload = bytearray(frame_data())
    struct.pack_into("<I", payload, 12, 3)
    with pytest.raises(ValueError, match="torn"):
        decode_frame(bytes(payload), process_id=42, process_creation=123456, now_ms=200)
    payload = bytearray(frame_data())
    struct.pack_into("<I", payload, 88, 16385)
    with pytest.raises(ValueError, match="capacity"):
        decode_frame(bytes(payload), process_id=42, process_creation=123456, now_ms=200)


def test_cpp_golden_frame_matches_python_capture_and_geometry():
    payload = bytes.fromhex(
        (Path(__file__).parent / "fixtures/navigation-inspector-v1.hex").read_text()
    )
    frame = decode_frame(payload, process_id=42, process_creation=123456, now_ms=200)
    saved = Snapshot.from_bytes(frame.capture)
    assert frame.lines == prepare_geometry(saved).lines
    assert frame.lines[0].start == (3, 5, -4)
    assert saved.identity.process_id == frame.process_id
    assert saved.session_id == frame.session_id == 17
