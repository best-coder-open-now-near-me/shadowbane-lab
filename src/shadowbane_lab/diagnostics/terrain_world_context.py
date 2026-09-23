"""Borrow existing read-only observers to contextualize a terrain capture."""

from __future__ import annotations

import time
from dataclasses import asdict
from datetime import UTC, datetime

from shadowbane_lab.client_observation.native_health import ReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_position import (
    NativePlayerPositionError,
    NativePlayerPositionReader,
    load_bundled_native_position_profile,
)
from shadowbane_lab.client_observation.native_zone import (
    NativeCurrentZoneError,
    NativeCurrentZoneReader,
    load_bundled_native_zone_profile,
)


class TerrainWorldContextIdentityError(RuntimeError):
    """The borrowed handle no longer identifies the requested lifetime."""


def observe_terrain_world_context(
    process: ReadOnlyProcessMemory,
    *,
    expected_creation_filetime: int,
) -> dict[str, object]:
    """Read a zone/position/zone sandwich, never owning or closing the handle.

    Context is explicitly separate from per-draw ownership: the player's current
    zone does not identify the owner of every visible terrain tile. Failed native
    observers produce unavailable context, not guessed coordinates or offsets.
    """
    if (
        isinstance(expected_creation_filetime, bool)
        or not isinstance(expected_creation_filetime, int)
        or expected_creation_filetime <= 0
    ):
        raise ValueError("expected_creation_filetime must be a positive integer")
    identity = (process.pid, getattr(process, "process_creation_filetime_utc", None))
    if identity[1] != expected_creation_filetime:
        raise TerrainWorldContextIdentityError("terrain context process lifetime mismatch")
    started = time.monotonic_ns()
    result: dict[str, object] = {
        "schema_version": 1,
        "process_id": identity[0],
        "process_creation_filetime_utc": identity[1],
        "started_at_utc": datetime.now(UTC).isoformat(),
        "started_monotonic_ns": started,
        "atomic": False,
        "per_draw_ownership": False,
    }
    try:
        zone_profile = load_bundled_native_zone_profile()
        position_profile = load_bundled_native_position_profile()
        result["zone_profile_id"] = zone_profile.profile_id
        result["position_profile_id"] = position_profile.profile_id
        # Do not use context managers: both readers borrow the caller's handle.
        zones = NativeCurrentZoneReader(zone_profile, process)
        positions = NativePlayerPositionReader(position_profile, process)
        before = zones.observe()
        position = positions.observe()
        after = zones.observe()
        result.update(
            status="captured" if before == after else "zone_changed_during_sample",
            zone_before=asdict(before),
            player_position=asdict(position),
            zone_after=asdict(after),
        )
    except (NativeCurrentZoneError, NativePlayerPositionError) as error:
        result.update(status="unavailable", error_type=type(error).__name__, reason=str(error))
    finally:
        # No silent rebinding, retries against another PID, or partial publication.
        current = (process.pid, getattr(process, "process_creation_filetime_utc", None))
        if current != identity:
            raise TerrainWorldContextIdentityError("terrain context identity changed during read")
    result["completed_at_utc"] = datetime.now(UTC).isoformat()
    result["completed_monotonic_ns"] = time.monotonic_ns()
    return result
