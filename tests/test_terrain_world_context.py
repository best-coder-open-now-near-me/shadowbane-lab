from dataclasses import replace
from types import SimpleNamespace

import pytest

import shadowbane_lab.diagnostics.terrain_world_context as context
from shadowbane_lab.client_observation.native_position import NativePlayerPositionObservation
from shadowbane_lab.client_observation.native_zone import (
    NativeCurrentZoneObservation,
    NativeZoneGeometry,
    NativeZoneIdentity,
)


def zone(name="Sea Dog's Rest"):
    geometry = NativeZoneGeometry(
        -384, -384, 384, 384, 1, 0, 0, 0, 88704, -44928, 0, 0, 384, 384
    )
    identity = NativeZoneIdentity(0, name, 0, 10400, 1, 99, geometry)
    return NativeCurrentZoneObservation(name, "opaque-zone-token", 0, (identity,))


@pytest.fixture
def observers(monkeypatch):
    process = SimpleNamespace(pid=960, process_creation_filetime_utc=12345)
    observations = [zone(), zone()]
    events = []

    class Zones:
        def __init__(self, profile, backend):
            assert backend is process
            events.append("zone-init")

        def observe(self):
            events.append("zone-read")
            value = observations.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        def close(self):
            pytest.fail("borrowed handle must not be closed")

    class Positions:
        def __init__(self, profile, backend):
            assert backend is process
            events.append("position-init")

        def observe(self):
            events.append("position-read")
            return NativePlayerPositionObservation(88745, 45059, 28)

        def close(self):
            pytest.fail("borrowed handle must not be closed")

    monkeypatch.setattr(context, "NativeCurrentZoneReader", Zones)
    monkeypatch.setattr(context, "NativePlayerPositionReader", Positions)
    return process, observations, events


def test_context_reuses_same_handle_and_preserves_geometry(observers):
    process, _, events = observers
    result = context.observe_terrain_world_context(process, expected_creation_filetime=12345)
    assert result["status"] == "captured"
    assert events == ["zone-init", "position-init", "zone-read", "position-read", "zone-read"]
    assert result["zone_before"] == result["zone_after"]
    assert result["zone_before"]["chain"][0]["geometry"]["absolute_center_x"] == 88704
    assert result["player_position"]["altitude"] == 28
    assert result["process_id"] == 960
    assert result["process_creation_filetime_utc"] == 12345
    assert result["started_monotonic_ns"] <= result["completed_monotonic_ns"]
    assert result["atomic"] is False
    assert result["per_draw_ownership"] is False


def test_zone_change_is_preserved_not_mislabeled_stable(observers):
    process, observations, _ = observers
    observations[1] = zone("Snow Orc Village")
    result = context.observe_terrain_world_context(process, expected_creation_filetime=12345)
    assert result["status"] == "zone_changed_during_sample"
    assert result["zone_before"]["name"] == "Sea Dog's Rest"
    assert result["zone_after"]["name"] == "Snow Orc Village"


def test_same_name_but_changed_geometry_is_not_stable(observers):
    process, observations, _ = observers
    original = observations[1]
    moved = replace(original.chain[0].geometry, absolute_center_x=89000)
    observations[1] = replace(original, chain=(replace(original.chain[0], geometry=moved),))
    result = context.observe_terrain_world_context(process, expected_creation_filetime=12345)
    assert result["status"] == "zone_changed_during_sample"


def test_unavailable_read_has_no_partial_or_guessed_context(observers):
    process, observations, _ = observers
    observations[1] = context.NativeCurrentZoneError("zone not available")
    result = context.observe_terrain_world_context(process, expected_creation_filetime=12345)
    assert result["status"] == "unavailable"
    assert result["reason"] == "zone not available"
    assert "player_position" not in result
    assert "zone_before" not in result


def test_position_compatibility_failure_never_reads_zone(observers, monkeypatch):
    process, _, events = observers

    def reject(*args):
        raise context.NativePlayerPositionError("unreviewed build")

    monkeypatch.setattr(context, "NativePlayerPositionReader", reject)
    result = context.observe_terrain_world_context(process, expected_creation_filetime=12345)
    assert result["status"] == "unavailable"
    assert events == ["zone-init"]


@pytest.mark.parametrize("creation", [0, -1, True, 1.5, None])
def test_invalid_requested_lifetime_fails_before_read(observers, creation):
    process, _, events = observers
    with pytest.raises(ValueError):
        context.observe_terrain_world_context(process, expected_creation_filetime=creation)
    assert events == []


def test_lifetime_mismatch_fails_before_read(observers):
    process, _, events = observers
    with pytest.raises(context.TerrainWorldContextIdentityError, match="lifetime"):
        context.observe_terrain_world_context(process, expected_creation_filetime=54321)
    assert events == []


@pytest.mark.parametrize("field,value", [("pid", 961), ("process_creation_filetime_utc", 54321)])
def test_identity_change_aborts_publication_even_on_read_failure(
    observers, monkeypatch, field, value
):
    process, _, _ = observers

    class ChangingPosition:
        def __init__(self, *args):
            pass

        def observe(self):
            setattr(process, field, value)
            raise context.NativePlayerPositionError("process changed")

    monkeypatch.setattr(context, "NativePlayerPositionReader", ChangingPosition)
    with pytest.raises(context.TerrainWorldContextIdentityError, match="changed"):
        context.observe_terrain_world_context(process, expected_creation_filetime=12345)
