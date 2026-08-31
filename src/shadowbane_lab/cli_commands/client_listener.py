"""Listener client command implementations."""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.client_input import (
    AnyStopSignal,
    ArcaneClientPower,
    ArcaneHotbarLoadError,
    CalibrationLoadError,
    ClientInputAdapter,
    DecisionInputCompiler,
    EventEmergencyStop,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    HotkeyCommand,
    InputExecutionError,
    InputPlan,
    KeyPressCommand,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    WaitCommand,
    WindowGuardError,
    WindowsForegroundWindowInspector,
    WindowsHotkeyEmergencyStop,
    WindowsVisibleWindowInspector,
    load_arcane_hotkeys,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    NativePlayerPositionError,
    NativePositionProfileLoadError,
    NativeWorldMapError,
    load_bundled_native_position_profile,
    load_bundled_native_runegate_registry_profile,
    load_bundled_native_world_map_profile,
    load_native_position_profile,
    load_native_runegate_registry_profile,
    load_native_world_map_profile,
    open_windows_native_player_position_reader,
    open_windows_native_world_map_reader,
)
from shadowbane_lab.manager import (
    ExactExtensionEventRouter,
    ForegroundWorkerOperationIngress,
    ManifestClientRegistryProvider,
    WorkerHeartbeatLedger,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationState,
    WorkerTravelDestination,
    load_manager_manifest,
)
from shadowbane_lab.pve import (
    PvEIntent,
)
from shadowbane_lab.travel import (
    PhysicalPointerInteraction,
    SparseNavigationMap,
    TravelDestination,
    TravelDestinationStateError,
    WindowsGoChatCommandListener,
    WindowsZoneSearchOverlay,
    ZoneSearchResult,
    load_learned_navigation_map,
    load_world_destination_catalog,
    parse_go_command,
    parse_named_go_command,
    parse_zone_search_command,
    resolve_travel_destination,
    save_learned_navigation_map,
)

from .client_pve import (
    _run_pve,
    _verify_hotbar_power_mapping,
)
from .client_runtime import _require_window_process_id
from .client_travel import _catalog_with_live_runegates, _run_travel
from .common import _error


def _listen_for_go_commands(
    *,
    destination_state_path: Path,
    client_profile_path: Path,
    native_position_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    native_runegate_profile_path: Path | None,
    world_def_path: Path | None,
    named_destination_overrides_path: Path | None,
    pve_client_profile_path: Path | None,
    pve_hotbar_config_path: Path | None,
    pve_evidence_directory: Path | None,
    navigation_cache_directory: Path | None,
    pve_max_kills: int,
    pve_max_seconds: float,
    pve_max_encounter_seconds: float,
    pve_recovery_timeout_seconds: float,
    pve_poll_ms: int,
    max_seconds: float,
    wait_for_client_seconds: float,
    poll_ms: int,
    click_interval_ms: int,
    live: bool,
    as_json: bool,
    pve_continuous: bool = False,
    pve_camp_radius: float = 120.0,
    pve_retained_trace_steps: int = 2_000,
    native_world_map_profile_path: Path | None = None,
    hotkey_config_path: Path | None = None,
    learned_navigation_state_path: Path | None = None,
    manager_manifest_path: Path | None = None,
    worker_state_directory: Path | None = None,
) -> int:
    if not live:
        return _error("chat travel requires the explicit --live flag", as_json=as_json)
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        guard = ForegroundWindowGuard(client_profile, WindowsForegroundWindowInspector())
        if (manager_manifest_path is None) != (worker_state_directory is None):
            raise ValueError(
                "--manager-manifest and --worker-state-directory must be supplied together"
            )
        worker_ingress = None
        extension_router = None
        if manager_manifest_path is not None:
            assert worker_state_directory is not None
            manager_manifest = load_manager_manifest(manager_manifest_path)
            manager_registry = ManifestClientRegistryProvider(
                WindowsVisibleWindowInspector(),
                manager_manifest,
            )
            worker_ingress = ForegroundWorkerOperationIngress(
                manager_manifest,
                manager_registry,
                WorkerHeartbeatLedger(manager_manifest, worker_state_directory),
                WorkerOperationLedger(manager_manifest, worker_state_directory),
            )
            extension_router = ExactExtensionEventRouter(
                manager_manifest,
                manager_registry,
                worker_ingress,
            )
        named_catalog = (
            None
            if world_def_path is None
            else load_world_destination_catalog(
                world_def_path,
                overrides_path=named_destination_overrides_path,
            )
        )
        if named_destination_overrides_path is not None and world_def_path is None:
            raise ValueError("named-destination overrides require --world-def")
        runegate_profile = (
            None
            if named_catalog is None
            else (
                load_native_runegate_registry_profile(native_runegate_profile_path)
                if native_runegate_profile_path is not None
                else load_bundled_native_runegate_registry_profile()
            )
        )
        world_map_profile = (
            load_native_world_map_profile(native_world_map_profile_path)
            if native_world_map_profile_path is not None
            else load_bundled_native_world_map_profile()
        )
        world_map_close_plan = None
        if hotkey_config_path is not None:
            world_map_bindings = load_arcane_hotkeys(hotkey_config_path).bindings_for_argument(
                "WorldMap"
            )
            if len(world_map_bindings) != 1:
                raise ValueError(
                    "hotkey config must contain exactly one WorldMap binding; "
                    f"found {len(world_map_bindings)}"
                )
            world_map_keys = world_map_bindings[0].input_keys
            world_map_command = (
                KeyPressCommand(world_map_keys[0])
                if len(world_map_keys) == 1
                else HotkeyCommand(world_map_keys)
            )
            world_map_close_plan = InputPlan(
                correlation_id="travel:world-map-close",
                action_key="client.world-map.close",
                commands=(WaitCommand(75), world_map_command),
            )
        pve_profile = None
        if pve_client_profile_path is not None:
            pve_profile = load_calibration(pve_client_profile_path)
            if not pve_profile.live_input_enabled:
                raise ValueError("PvE client profile is not enabled for live input")
            if pve_profile.target != client_profile.target:
                raise ValueError("travel and PvE profiles target different client windows")
        if pve_evidence_directory is not None:
            pve_evidence_directory.mkdir(parents=True, exist_ok=True)
        if pve_continuous and pve_evidence_directory is None:
            raise ValueError("continuous /pve requires a PvE evidence directory")
        if learned_navigation_state_path is not None and navigation_cache_directory is None:
            raise ValueError("learned navigation state requires --navigation-cache-directory")
        shared_navigation_map = (
            None
            if navigation_cache_directory is None
            else (
                SparseNavigationMap()
                if learned_navigation_state_path is None
                else load_learned_navigation_map(learned_navigation_state_path)
            )
        )
    except (
        ArcaneHotbarLoadError,
        CalibrationLoadError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        return _error(f"chat control failed: {exc}", as_json=as_json)

    commands: queue.Queue[str | tuple[PhysicalPointerInteraction, float]] = queue.Queue()
    active_lock = threading.Lock()
    active_operation_stop: EventEmergencyStop | None = None

    def cancel_active_operation() -> None:
        if worker_ingress is not None:
            commands.put("/stop")
            return
        with active_lock:
            if active_operation_stop is not None:
                active_operation_stop.trip()

    def submit_command(command: str) -> None:
        commands.put(command)

    def submit_pointer(interaction: PhysicalPointerInteraction) -> None:
        if interaction.button == "right":
            commands.put((interaction, time.monotonic()))

    extension_dispatch_times: dict[int, float] = {}
    extension_router_diagnostics: dict[str, object] | None = None
    extension_router_stable_state: tuple[object, ...] | None = None

    def poll_extension_events() -> None:
        nonlocal extension_router_diagnostics, extension_router_stable_state
        if extension_router is None:
            return
        result = extension_router.poll_once()
        observed_at = time.monotonic()
        for process_id in result.dispatched_process_ids:
            extension_dispatch_times[process_id] = observed_at
        extension_router_diagnostics = {
            "connected_clients": result.connected_clients,
            "dispatched_events": result.dispatched_events,
            "rejected_events": result.rejected_events,
            "pending_events": result.pending_events,
            "dispatched_process_ids": list(result.dispatched_process_ids),
            "issues": list(result.issues),
        }
        stable_state = (
            result.connected_clients,
            result.pending_events,
            result.issues,
        )
        state_change_is_notable = stable_state != extension_router_stable_state and (
            result.connected_clients > 0 or result.pending_events > 0 or bool(result.issues)
        )
        if state_change_is_notable or result.dispatched_events > 0 or result.rejected_events > 0:
            _print_go_listener_event(
                "extension_router",
                as_json=as_json,
                extension_router_diagnostics=extension_router_diagnostics,
            )
        extension_router_stable_state = stable_state

    def dispatch_to_exact_worker(
        kind: WorkerOperationKind,
        command: str,
        *,
        process_id: int,
        destination: WorkerTravelDestination | None = None,
        resolved_name: str | None = None,
        candidate_count: int | None = None,
        destination_source: str | None = None,
    ) -> bool:
        if worker_ingress is None:
            raise RuntimeError("exact-worker ingress is not configured")
        try:
            dispatch = worker_ingress.dispatch(
                kind,
                command,
                destination=destination,
                expected_process_id=process_id,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            _print_go_listener_event(
                "rejected",
                as_json=as_json,
                command=command,
                reason=str(exc),
            )
            return False
        acknowledgement = dispatch.acknowledgement
        if acknowledgement is not None and acknowledgement.state in {
            WorkerOperationState.FAILED,
            WorkerOperationState.CANCELLED,
            WorkerOperationState.EXPIRED,
            WorkerOperationState.REJECTED,
        }:
            _print_go_listener_event(
                "rejected",
                as_json=as_json,
                command=command,
                reason=(
                    acknowledgement.detail or f"exact worker reported {acknowledgement.state.value}"
                ),
                operation_id=dispatch.operation.operation_id,
                client_id=dispatch.operation.client_id,
                operation_state=acknowledgement.state.value,
            )
            return False
        _print_go_listener_event(
            "accepted" if acknowledgement is not None else "submitted",
            as_json=as_json,
            command=command,
            reason=(
                None
                if acknowledgement is not None
                else "exact worker acknowledgement timed out; operation remains visible"
            ),
            resolved_name=resolved_name,
            lt=None if destination is None else destination.lt,
            lg=None if destination is None else destination.lg,
            candidate_count=candidate_count,
            destination_source=destination_source,
            operation_id=dispatch.operation.operation_id,
            client_id=dispatch.operation.client_id,
            operation_state=(None if acknowledgement is None else acknowledgement.state.value),
        )
        return True

    world_map_reader = None
    listener_callbacks = {
        "on_command": submit_command,
        "on_interaction": cancel_active_operation,
        "on_pointer": submit_pointer,
    }
    if extension_router is not None:
        listener_callbacks["pointer_claims_interaction"] = lambda interaction: (
            interaction.button == "right"
        )
    listener = WindowsGoChatCommandListener(guard, **listener_callbacks)

    try:
        with (
            WindowsHotkeyEmergencyStop() as service_stop,
            listener,
            WindowsZoneSearchOverlay() as zone_overlay,
        ):
            stop_adapter = ClientInputAdapter(
                DecisionInputCompiler(client_profile, StaticBindingPointResolver()),
                GuardedInputExecutor(
                    guard=guard,
                    backend=PyAutoGuiBackend(),
                    stop_signal=service_stop,
                ),
            )
            world_map_executor = GuardedInputExecutor(
                guard=guard,
                backend=PyAutoGuiBackend(),
                stop_signal=service_stop,
            )
            stop_sequence = 0
            _print_go_listener_event("listening", as_json=as_json)
            next_listener_heartbeat = time.monotonic() + 30.0
            while not service_stop.is_set():
                poll_extension_events()
                if getattr(listener, "is_alive", True) is False:
                    failure_detail = getattr(listener, "failure_detail", None)
                    raise RuntimeError(
                        "Windows input hook stopped unexpectedly"
                        + ("" if not failure_detail else f": {failure_detail}")
                    )
                if time.monotonic() >= next_listener_heartbeat:
                    _print_go_listener_event(
                        "heartbeat",
                        as_json=as_json,
                        hook_diagnostics=getattr(listener, "diagnostics", None),
                        extension_router_diagnostics=extension_router_diagnostics,
                    )
                    next_listener_heartbeat = time.monotonic() + 30.0
                try:
                    interaction = commands.get(timeout=0.1)
                except queue.Empty:
                    continue

                pointer_destination = None
                pointer_observed_at = None
                destination_source = None
                if isinstance(interaction, tuple):
                    interaction, pointer_observed_at = interaction
                    command = (
                        f"world-map right-click ({interaction.screen_x}, {interaction.screen_y})"
                    )
                    normalized = None
                else:
                    command = interaction
                    normalized = command.strip().casefold()
                named_resolution = None
                if normalized == "/stop" and worker_ingress is None:
                    stop_sequence += 1
                    result = stop_adapter.dispatch_movement_stop(
                        correlation_id=f"travel:chat-stop:{stop_sequence}"
                    )
                    _print_go_stop_result(
                        accepted=result.accepted,
                        reason=result.reason,
                        as_json=as_json,
                    )
                    continue
                try:
                    command_process_id = _require_window_process_id(guard.require_target())
                except WindowGuardError as exc:
                    _print_go_listener_event(
                        "rejected",
                        as_json=as_json,
                        command=command,
                        reason=str(exc),
                    )
                    continue
                if normalized == "/stop":
                    dispatch_to_exact_worker(
                        WorkerOperationKind.STOP,
                        command,
                        process_id=command_process_id,
                    )
                    continue
                if isinstance(interaction, PhysicalPointerInteraction):
                    if extension_router is not None:
                        assert pointer_observed_at is not None
                        for attempt in range(4):
                            if (
                                extension_dispatch_times.get(command_process_id, -1.0)
                                >= pointer_observed_at
                            ):
                                break
                            if attempt:
                                time.sleep(0.025)
                            poll_extension_events()
                        if (
                            extension_dispatch_times.get(command_process_id, -1.0)
                            >= pointer_observed_at
                        ):
                            continue
                        if not dispatch_to_exact_worker(
                            WorkerOperationKind.STOP,
                            f"extension-fallback-stop:{command}",
                            process_id=command_process_id,
                        ):
                            continue
                    try:
                        if (
                            world_map_reader is None
                            or world_map_reader.process_id != command_process_id
                        ):
                            if world_map_reader is not None:
                                world_map_reader.close()
                            world_map_reader = open_windows_native_world_map_reader(
                                world_map_profile,
                                process_id=command_process_id,
                            )
                        point = world_map_reader.resolve_screen_point(
                            interaction.screen_x,
                            interaction.screen_y,
                        )
                        pointer_destination = TravelDestination(point.lt, point.lg)
                        destination_source = "native_world_map"
                    except (NativeWorldMapError, OSError, RuntimeError, ValueError) as exc:
                        _print_go_listener_event(
                            "world_map_click_ignored",
                            as_json=as_json,
                            command=command,
                            reason=str(exc),
                        )
                        continue
                if normalized is not None and (
                    normalized == "/zone" or normalized.startswith("/zone ")
                ):
                    try:
                        query = parse_zone_search_command(command)
                        if named_catalog is None:
                            raise ValueError("/zone requires --world-def")
                        active_named_catalog = _catalog_with_live_runegates(
                            named_catalog,
                            runegate_profile,
                            process_id=command_process_id,
                        )
                        results = active_named_catalog.search(query, limit=5)
                    except (
                        OSError,
                        RuntimeError,
                        UnicodeError,
                        ValueError,
                    ) as exc:
                        _print_go_listener_event(
                            "rejected",
                            as_json=as_json,
                            command=command,
                            reason=str(exc),
                        )
                        continue
                    presentation_error = None
                    try:
                        zone_overlay.show(query, results)
                    except (OSError, RuntimeError, ValueError) as exc:
                        presentation_error = str(exc)
                    _print_zone_search_results(
                        query,
                        results,
                        presentation_error=presentation_error,
                        as_json=as_json,
                    )
                    continue
                if normalized == "/pve":
                    if worker_ingress is not None:
                        dispatch_to_exact_worker(
                            WorkerOperationKind.PVE,
                            command,
                            process_id=command_process_id,
                        )
                        continue
                    if pve_client_profile_path is None or pve_profile is None:
                        _print_go_listener_event(
                            "rejected",
                            as_json=as_json,
                            command=command,
                            reason="the listener was started without a PvE profile",
                        )
                        continue
                    try:
                        _verify_hotbar_power_mapping(
                            pve_profile.actions,
                            pve_hotbar_config_path,
                            action_key=PvEIntent.CAST_SHADOW_TOUCH.value,
                            power_name=ArcaneClientPower.SHADOW_TOUCH,
                        )
                    except (ArcaneHotbarLoadError, OSError, ValueError) as exc:
                        _print_go_listener_event(
                            "rejected",
                            as_json=as_json,
                            command=command,
                            reason=str(exc),
                        )
                        continue
                    operation_stop = EventEmergencyStop()
                    with active_lock:
                        active_operation_stop = operation_stop
                    evidence_output = (
                        None
                        if pve_evidence_directory is None
                        else _new_chat_pve_evidence_path(pve_evidence_directory)
                    )
                    try:
                        _print_go_listener_event(
                            "accepted",
                            as_json=as_json,
                            command=command,
                        )
                        _run_pve(
                            client_profile_path=pve_client_profile_path,
                            combat_log_path=None,
                            hotbar_config_path=pve_hotbar_config_path,
                            native_health_profile_path=None,
                            native_vitals_profile_path=native_vitals_profile_path,
                            native_position_profile_path=native_position_profile_path,
                            native_target_position_profile_path=None,
                            native_target_action_profile_path=None,
                            navigation_cache_directory=navigation_cache_directory,
                            max_kills=pve_max_kills,
                            max_seconds=pve_max_seconds,
                            max_encounter_seconds=pve_max_encounter_seconds,
                            recovery_timeout_seconds=pve_recovery_timeout_seconds,
                            wait_for_client_seconds=0,
                            poll_ms=pve_poll_ms,
                            policy="proc-assassin",
                            live=live,
                            as_json=as_json,
                            evidence_output_path=evidence_output,
                            combat_source="state",
                            stop_signal=AnyStopSignal(service_stop, operation_stop),
                            client_process_id=command_process_id,
                            continuous=pve_continuous,
                            camp_radius=pve_camp_radius,
                            retained_trace_steps=pve_retained_trace_steps,
                            navigation_map=shared_navigation_map,
                        )
                    finally:
                        if learned_navigation_state_path is not None:
                            assert shared_navigation_map is not None
                            save_learned_navigation_map(
                                learned_navigation_state_path,
                                shared_navigation_map,
                            )
                        with active_lock:
                            if active_operation_stop is operation_stop:
                                active_operation_stop = None
                    continue
                if pointer_destination is not None:
                    destination = pointer_destination
                    lt = destination.lt
                    lg = destination.lg
                    radius = destination.arrival_radius
                elif normalized == "/go":
                    lt = None
                    lg = None
                    radius = None
                else:
                    try:
                        plan = parse_go_command(command)
                        destination = plan.destinations[0]
                    except ValueError:
                        try:
                            query = parse_named_go_command(command)
                            if named_catalog is None:
                                raise ValueError("named /go destinations require --world-def")
                            position_profile = (
                                load_native_position_profile(native_position_profile_path)
                                if native_position_profile_path is not None
                                else load_bundled_native_position_profile()
                            )
                            with open_windows_native_player_position_reader(
                                position_profile,
                                process_id=command_process_id,
                            ) as position_reader:
                                origin = position_reader.observe()
                            active_named_catalog = _catalog_with_live_runegates(
                                named_catalog,
                                runegate_profile,
                                process_id=command_process_id,
                            )
                            named_resolution = active_named_catalog.resolve(
                                query,
                                origin=origin,
                            )
                            destination = named_resolution.destination
                        except (
                            NativePlayerPositionError,
                            NativePositionProfileLoadError,
                            OSError,
                            RuntimeError,
                            UnicodeError,
                            ValueError,
                        ) as exc:
                            _print_go_listener_event(
                                "rejected",
                                as_json=as_json,
                                command=command,
                                reason=str(exc),
                            )
                            continue
                    lt = destination.lt
                    lg = destination.lg
                    radius = destination.arrival_radius

                if worker_ingress is not None:
                    try:
                        resolved_destination = resolve_travel_destination(
                            destination_state_path,
                            lt=lt,
                            lg=lg,
                            radius=radius,
                        )
                    except (TravelDestinationStateError, ValueError) as exc:
                        _print_go_listener_event(
                            "rejected",
                            as_json=as_json,
                            command=command,
                            reason=str(exc),
                        )
                        continue
                    if pointer_destination is not None and world_map_close_plan is not None:
                        try:
                            world_map_executor.execute(world_map_close_plan)
                        except InputExecutionError as exc:
                            _print_go_listener_event(
                                "rejected",
                                as_json=as_json,
                                command=command,
                                reason=f"could not close world map: {exc}",
                            )
                            continue
                    worker_destination = WorkerTravelDestination(
                        resolved_destination.lt,
                        resolved_destination.lg,
                        resolved_destination.arrival_radius,
                    )
                    dispatch_to_exact_worker(
                        WorkerOperationKind.TRAVEL,
                        command,
                        process_id=command_process_id,
                        destination=worker_destination,
                        resolved_name=(
                            None if named_resolution is None else named_resolution.matched_name
                        ),
                        candidate_count=(
                            None if named_resolution is None else named_resolution.candidate_count
                        ),
                        destination_source=(
                            destination_source
                            if named_resolution is None
                            else named_resolution.source
                        ),
                    )
                    continue

                route_stop = EventEmergencyStop()
                with active_lock:
                    active_operation_stop = route_stop
                try:
                    if pointer_destination is not None and world_map_close_plan is not None:
                        try:
                            world_map_executor.execute(world_map_close_plan)
                        except InputExecutionError as exc:
                            _print_go_listener_event(
                                "rejected",
                                as_json=as_json,
                                command=command,
                                reason=f"could not close world map: {exc}",
                            )
                            continue
                    _print_go_listener_event(
                        "accepted",
                        as_json=as_json,
                        command=command,
                        resolved_name=(
                            None if named_resolution is None else named_resolution.matched_name
                        ),
                        lt=lt,
                        lg=lg,
                        candidate_count=(
                            None if named_resolution is None else named_resolution.candidate_count
                        ),
                        destination_source=(
                            destination_source
                            if named_resolution is None
                            else named_resolution.source
                        ),
                    )
                    _run_travel(
                        lt=lt,
                        lg=lg,
                        radius=radius,
                        destination_state_path=destination_state_path,
                        client_profile_path=client_profile_path,
                        native_position_profile_path=native_position_profile_path,
                        native_vitals_profile_path=native_vitals_profile_path,
                        max_seconds=max_seconds,
                        wait_for_client_seconds=wait_for_client_seconds,
                        poll_ms=poll_ms,
                        click_interval_ms=click_interval_ms,
                        live=live,
                        as_json=as_json,
                        stop_signal=AnyStopSignal(service_stop, route_stop),
                        client_process_id=command_process_id,
                        navigation_cache_directory=navigation_cache_directory,
                        navigation_map=shared_navigation_map,
                    )
                finally:
                    if learned_navigation_state_path is not None:
                        assert shared_navigation_map is not None
                        save_learned_navigation_map(
                            learned_navigation_state_path,
                            shared_navigation_map,
                        )
                    with active_lock:
                        if active_operation_stop is route_stop:
                            active_operation_stop = None
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"chat control failed: {exc}", as_json=as_json)
    finally:
        if extension_router is not None:
            extension_router.close()
        if world_map_reader is not None:
            world_map_reader.close()

    _print_go_listener_event("stopped", as_json=as_json)
    return 0


def _new_chat_pve_evidence_path(directory: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = directory / f"pve-chat-{timestamp}-{time.time_ns()}.json"
    if candidate.exists():
        raise RuntimeError(f"refusing to overwrite PvE evidence: {candidate}")
    return candidate


def _print_go_listener_event(
    event: str,
    *,
    as_json: bool,
    command: str | None = None,
    reason: str | None = None,
    resolved_name: str | None = None,
    lt: float | None = None,
    lg: float | None = None,
    candidate_count: int | None = None,
    destination_source: str | None = None,
    operation_id: str | None = None,
    client_id: str | None = None,
    operation_state: str | None = None,
    hook_diagnostics: dict[str, int | str | None] | None = None,
    extension_router_diagnostics: dict[str, object] | None = None,
) -> None:
    if as_json:
        payload = {"ok": event != "rejected", "event": event}
        if command is not None:
            payload["command"] = command
        if reason is not None:
            payload["reason"] = reason
        if resolved_name is not None:
            payload["resolved_name"] = resolved_name
        if lt is not None and lg is not None:
            payload["destination"] = {"lt": lt, "lg": lg}
        if candidate_count is not None:
            payload["candidate_count"] = candidate_count
        if destination_source is not None:
            payload["destination_source"] = destination_source
        if operation_id is not None:
            payload["operation_id"] = operation_id
        if client_id is not None:
            payload["client_id"] = client_id
        if operation_state is not None:
            payload["operation_state"] = operation_state
        if hook_diagnostics is not None:
            payload["hook_diagnostics"] = hook_diagnostics
        if extension_router_diagnostics is not None:
            payload["extension_router_diagnostics"] = extension_router_diagnostics
        print(json.dumps(payload, sort_keys=True), flush=True)
        return
    if event == "listening":
        print(
            "Listening for foreground Shadowbane commands (/go, /zone, /pve, /stop).",
            flush=True,
        )
    elif event == "stopped":
        print("Stopped listening for Shadowbane commands.", flush=True)
    elif event == "heartbeat":
        print("Shadowbane command listener is healthy.", flush=True)
    elif event == "extension_router":
        print(
            f"Shadowbane extension router: {extension_router_diagnostics}",
            flush=True,
        )
    elif event in {"accepted", "submitted"}:
        detail = "" if resolved_name is None else f" -> {resolved_name} at LT {lt:g}, LG {lg:g}"
        verb = "Accepted" if event == "accepted" else "Submitted"
        worker_detail = "" if client_id is None else f" [{client_id}]"
        print(
            f"{verb} chat command{worker_detail}: {command}{detail}",
            flush=True,
        )
    elif event == "world_map_click_ignored":
        print(f"Ignored {command}: {reason}", flush=True)
    else:
        print(f"Rejected chat command {command!r}: {reason}", file=sys.stderr, flush=True)


def _print_go_stop_result(
    *,
    accepted: bool,
    reason: str | None,
    as_json: bool,
) -> None:
    event = "movement_stopped" if accepted else "movement_stop_rejected"
    if as_json:
        payload = {"ok": accepted, "event": event}
        if reason is not None:
            payload["reason"] = reason
        print(json.dumps(payload, sort_keys=True), flush=True)
        return
    if accepted:
        print("Stopped Shadowbane click-to-move.", flush=True)
    else:
        print(f"Could not stop Shadowbane movement: {reason}", file=sys.stderr, flush=True)


def _print_zone_search_results(
    query: str,
    results: Sequence[ZoneSearchResult],
    *,
    presentation_error: str | None,
    as_json: bool,
) -> None:
    if as_json:
        payload: dict[str, object] = {
            "ok": True,
            "event": "zone_results",
            "query": query,
            "match_count": len(results),
            "results": [
                {
                    "canonical_name": result.canonical_name,
                    "aliases": list(result.aliases),
                    "score": result.score,
                    "template_id": result.template_id,
                    "source": result.source,
                    "destination": {
                        "lt": result.destination.lt,
                        "lg": result.destination.lg,
                    },
                }
                for result in results
            ],
        }
        if presentation_error is not None:
            payload["presentation_error"] = presentation_error
        print(json.dumps(payload, sort_keys=True), flush=True)
        return
    print(f"Zone matches for {query!r}:", flush=True)
    for result in results:
        print(
            f"  {result.canonical_name}: LT {result.destination.lt:g}, "
            f"LG {result.destination.lg:g}",
            flush=True,
        )
    if not results:
        print("  no matches", flush=True)
    if presentation_error is not None:
        print(
            f"Zone overlay unavailable: {presentation_error}",
            file=sys.stderr,
            flush=True,
        )
