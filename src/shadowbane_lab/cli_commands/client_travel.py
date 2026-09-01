"""Travel client command implementations."""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path

from shadowbane_lab.client_input import (
    CalibrationLoadError,
    ClientInputAdapter,
    DecisionInputCompiler,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    MouseButton,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    StopSignal,
    WindowGuardError,
    WindowsForegroundWindowInspector,
    WindowsHotkeyEmergencyStop,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    NativePlayerPositionError,
    NativePlayerVitalsError,
    NativePositionProfileLoadError,
    NativeRunegateRegistryError,
    NativeRunegateRegistryProfile,
    NativeVitalsProfileLoadError,
    load_bundled_native_position_profile,
    load_bundled_native_vitals_profile,
    load_bundled_native_zone_profile,
    load_native_position_profile,
    load_native_vitals_profile,
    open_windows_native_current_zone_reader,
    open_windows_native_player_position_reader,
    open_windows_native_player_vitals_reader,
    open_windows_native_runegate_registry_reader,
)
from shadowbane_lab.travel import (
    ActiveZoneTerrainNavigationSource,
    AStarTravelController,
    ClientTravelDecisionDispatcher,
    SparseNavigationMap,
    TravelController,
    TravelControllerConfig,
    TravelDestination,
    TravelDestinationStateError,
    TravelPhase,
    TravelPlan,
    TravelRunner,
    WeightedAStarConfig,
    WeightedAStarPlanner,
    WorldDestinationCatalog,
    resolve_travel_destination,
)

from .client_runtime import _require_window_process_id, _wait_for_guarded_client
from .common import _error


def _run_travel(
    *,
    lt: float | None,
    lg: float | None,
    radius: float | None,
    destination_state_path: Path,
    client_profile_path: Path,
    native_position_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    max_seconds: float,
    wait_for_client_seconds: float,
    poll_ms: int,
    click_interval_ms: int,
    live: bool,
    as_json: bool,
    stop_signal: StopSignal | None = None,
    client_process_id: int | None = None,
    navigation_cache_directory: Path | None = None,
    navigation_map: SparseNavigationMap | None = None,
) -> int:
    if not live:
        return _error("travel execution requires the explicit --live flag", as_json=as_json)
    if radius is not None and not 5.0 <= radius <= 1_000.0:
        return _error("radius must be in [5, 1000]", as_json=as_json)
    astar_controller = None
    terrain_source = None
    try:
        destination = resolve_travel_destination(
            destination_state_path,
            lt=lt,
            lg=lg,
            radius=radius,
        )
    except (TravelDestinationStateError, ValueError) as exc:
        return _error(f"could not resolve travel destination: {exc}", as_json=as_json)
    lt = destination.lt
    lg = destination.lg
    radius = destination.arrival_radius
    if not 5.0 <= radius <= 1_000.0:
        return _error("radius must be in [5, 1000]", as_json=as_json)
    if not 1.0 <= max_seconds <= 1_800.0:
        return _error("max-seconds must be in [1, 1800]", as_json=as_json)
    if not 0.0 <= wait_for_client_seconds <= 300.0:
        return _error("wait-for-client-seconds must be in [0, 300]", as_json=as_json)
    if isinstance(poll_ms, bool) or not 50 <= poll_ms <= 1_000:
        return _error("poll-ms must be in [50, 1000]", as_json=as_json)
    if isinstance(click_interval_ms, bool) or not 500 <= click_interval_ms <= 30_000:
        return _error("click-interval-ms must be in [500, 30000]", as_json=as_json)
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        if client_profile.movement.button is not MouseButton.RIGHT:
            raise ValueError("travel profile movement must use right-click input")
        position_profile = (
            load_native_position_profile(native_position_profile_path)
            if native_position_profile_path is not None
            else load_bundled_native_position_profile()
        )
        vitals_profile = (
            load_native_vitals_profile(native_vitals_profile_path)
            if native_vitals_profile_path is not None
            else load_bundled_native_vitals_profile()
        )
        if position_profile.executable_sha256 != vitals_profile.executable_sha256:
            raise ValueError("native position and player-vitals profiles target different builds")
        zone_profile = (
            None if navigation_cache_directory is None else load_bundled_native_zone_profile()
        )
        if navigation_cache_directory is not None and not navigation_cache_directory.is_dir():
            raise ValueError(
                f"navigation cache directory does not exist: {navigation_cache_directory}"
            )
        if (
            zone_profile is not None
            and zone_profile.executable_sha256 != position_profile.executable_sha256
        ):
            raise ValueError("native zone and position profiles target different builds")
        plan = TravelPlan(
            plan_id=f"go:{lt:g}:{lg:g}:{radius:g}",
            destinations=(TravelDestination(lt, lg, radius),),
        )
        travel_config = TravelControllerConfig(
            maximum_session_ms=round(max_seconds * 1000),
            click_interval_ms=click_interval_ms,
            maximum_clicks=min(
                500,
                max(1, round(max_seconds * 1000 / click_interval_ms)),
            ),
            minimum_progress=8.0,
            maximum_no_progress_clicks=2,
        )
        inspector = WindowsForegroundWindowInspector()
        selection_guard = ForegroundWindowGuard(client_profile, inspector)
        if client_process_id is None:
            selected_window = _wait_for_guarded_client(
                selection_guard,
                wait_seconds=wait_for_client_seconds,
            )
            selected_process_id = _require_window_process_id(selected_window)
        else:
            selected_process_id = client_process_id
        guard = ForegroundWindowGuard(
            client_profile,
            inspector,
            expected_process_id=selected_process_id,
        )
        if client_process_id is not None:
            _wait_for_guarded_client(guard, wait_seconds=wait_for_client_seconds)
        with ExitStack() as stack:
            position_reader = stack.enter_context(
                open_windows_native_player_position_reader(
                    position_profile,
                    process_id=selected_process_id,
                )
            )
            player_vitals_reader = stack.enter_context(
                open_windows_native_player_vitals_reader(
                    vitals_profile,
                    process_id=selected_process_id,
                )
            )
            active_stop_signal = stop_signal
            if active_stop_signal is None:
                active_stop_signal = stack.enter_context(WindowsHotkeyEmergencyStop())
            if position_reader.process_id != player_vitals_reader.process_id:
                raise ValueError(
                    "native position and player-vitals readers resolved different processes"
                )
            if zone_profile is None:
                controller = TravelController(plan, travel_config)
            else:
                assert navigation_cache_directory is not None
                zone_reader = stack.enter_context(
                    open_windows_native_current_zone_reader(
                        zone_profile,
                        process_id=selected_process_id,
                    )
                )
                if zone_reader.process_id != position_reader.process_id:
                    raise ValueError(
                        "native position and current-zone readers resolved different processes"
                    )
                terrain_source_arguments = (
                    {} if navigation_map is None else {"navigation_map": navigation_map}
                )
                terrain_source = ActiveZoneTerrainNavigationSource(
                    navigation_cache_directory,
                    zone_reader,
                    **terrain_source_arguments,
                )
                astar_controller = AStarTravelController(
                    destination,
                    travel_config,
                    terrain_source,
                    planner=WeightedAStarPlanner(
                        WeightedAStarConfig(
                            obstacle_clearance_cells=0,
                            waypoint_radius_fraction=0.5,
                        )
                    ),
                    plan_id=plan.plan_id,
                )
                controller = astar_controller
            executor = GuardedInputExecutor(
                guard=guard,
                backend=PyAutoGuiBackend(),
                stop_signal=active_stop_signal,
            )
            adapter = ClientInputAdapter(
                DecisionInputCompiler(client_profile, StaticBindingPointResolver()),
                executor,
            )
            result = TravelRunner(
                controller=controller,
                position_reader=position_reader,
                player_vitals_reader=player_vitals_reader,
                dispatcher=ClientTravelDecisionDispatcher(adapter),
                stop_signal=active_stop_signal,
                poll_interval_ms=poll_ms,
            ).run()
    except (
        CalibrationLoadError,
        NativePlayerPositionError,
        NativePlayerVitalsError,
        NativePositionProfileLoadError,
        NativeVitalsProfileLoadError,
        OSError,
        RuntimeError,
        ValueError,
        WindowGuardError,
    ) as exc:
        return _error(f"travel run failed: {exc}", as_json=as_json)

    final_position = result.final_position
    dispatched = [
        {
            "decision_id": step.decision.decision_id,
            "at_ms": step.decision.now_ms,
            "distance_remaining": step.decision.distance_remaining,
            "maneuver": step.decision.maneuver.value,
            "accepted": step.input_accepted,
            "reason": step.input_reason,
        }
        for step in result.trace
        if step.decision.minimap_direction is not None
    ]
    payload = {
        "ok": result.final_phase is TravelPhase.COMPLETE,
        "final_phase": result.final_phase.value,
        "terminal_reason": result.terminal_reason,
        "destination": {"lt": lt, "lg": lg, "radius": radius},
        "final_position": (
            None
            if final_position is None
            else {
                "lt": final_position.lt,
                "lg": final_position.lg,
                "altitude": final_position.altitude,
            }
        ),
        "clicks": result.clicks,
        "stop_input_accepted": result.stop_input_accepted,
        "stop_input_reason": result.stop_input_reason,
        "steps": len(result.trace),
        "dispatched": dispatched,
        "pathfinding": {
            "enabled": astar_controller is not None,
            "replans": 0 if astar_controller is None else astar_controller.replan_count,
            "direct_fallbacks": (
                0 if astar_controller is None else astar_controller.direct_fallback_count
            ),
            "partial_routes": (
                0 if astar_controller is None else astar_controller.partial_route_count
            ),
            "route_mode": None if astar_controller is None else astar_controller.route_mode,
            "navigation_token": (
                None if astar_controller is None else astar_controller.navigation_token
            ),
            "terrain_refreshes": (0 if terrain_source is None else terrain_source.refresh_count),
            "zone_name": (None if terrain_source is None else terrain_source.last_zone_name),
        },
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Travel phase: {result.final_phase.value}")
        print(f"Reason: {result.terminal_reason}")
        if final_position is not None:
            print(f"Position: LT {final_position.lt:.2f}, LG {final_position.lg:.2f}")
        print(f"Guarded minimap clicks: {result.clicks}")
        if result.stop_input_accepted is not None:
            print(f"Movement stop accepted: {result.stop_input_accepted}")
    return 0 if payload["ok"] else 2


def _catalog_with_live_runegates(
    catalog: WorldDestinationCatalog,
    profile: NativeRunegateRegistryProfile | None,
    *,
    process_id: int,
) -> WorldDestinationCatalog:
    if profile is None:
        return catalog
    try:
        with open_windows_native_runegate_registry_reader(
            profile,
            process_id=process_id,
        ) as reader:
            registry = reader.observe()
    except NativeRunegateRegistryError:
        # Confirmed overrides and client placements remain available while CityData is
        # temporarily absent or changing.
        return catalog
    return catalog.with_authoritative_runegates(registry)
