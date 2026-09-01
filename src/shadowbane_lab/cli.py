"""Command-line diagnostics used by the WonderBane VM bootstrap."""

# This compatibility facade deliberately preserves the dependency names historically
# patched through ``shadowbane_lab.cli`` while implementations live in domain modules.
# ruff: noqa: F401

from __future__ import annotations

import argparse
import json
import ntpath
import os
import queue
import sys
import threading
import time
import webbrowser
from collections.abc import Sequence
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.character_capture import (
    CharacterCaptureError,
    CharacterLayoutError,
    MemoryAccessError,
    ProcessSelectionError,
    WindowsProcessMemory,
    capture_character,
    load_character_layout,
)
from shadowbane_lab.cli_commands import cases as _case_commands
from shadowbane_lab.cli_commands import character as _character_commands
from shadowbane_lab.cli_commands import client_inspection as _client_inspection_commands
from shadowbane_lab.cli_commands import client_listener as _client_listener_commands
from shadowbane_lab.cli_commands import client_pve as _client_pve_commands
from shadowbane_lab.cli_commands import client_runtime as _client_runtime_commands
from shadowbane_lab.cli_commands import client_travel as _client_travel_commands
from shadowbane_lab.cli_commands import common as _common_commands
from shadowbane_lab.cli_commands import diagnostics as _diagnostic_commands
from shadowbane_lab.cli_commands import evidence as _evidence_commands
from shadowbane_lab.cli_commands import fingerprint as _fingerprint_commands
from shadowbane_lab.cli_commands import manager as _manager_commands
from shadowbane_lab.cli_commands import parser as _parser_commands
from shadowbane_lab.cli_commands import progression as _progression_commands
from shadowbane_lab.client_action import (
    ClientActionEvidenceError,
    ClientActionRunner,
    WorldMapDestinationClickAction,
    save_client_action_evidence,
)
from shadowbane_lab.client_extension import (
    ExtensionHeartbeatStatusProvider,
    load_patch_manifest,
    open_windows_extension_event_consumer,
)
from shadowbane_lab.client_input import (
    ActionInputMapping,
    AnyStopSignal,
    ArcaneClientAction,
    ArcaneClientPower,
    ArcaneHotbarLoadError,
    ArcaneHotkeyLoadError,
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
    MouseButton,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    StopSignal,
    WaitCommand,
    WindowGuardError,
    WindowsForegroundWindowInspector,
    WindowsHotkeyEmergencyStop,
    WindowSnapshot,
    WindowsVisibleWindowInspector,
    WorldMapTestInputBackend,
    load_arcane_hotbar,
    load_arcane_hotkeys,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    ClientTargetObserver,
    NativeCharacterPopulationError,
    NativeCharacterPopulationProfileLoadError,
    NativeCombatLogFormatError,
    NativeCombatLogReader,
    NativeCurrentZoneError,
    NativeGroupError,
    NativeGroupProfileLoadError,
    NativeHealthProfileLoadError,
    NativeMessageHudError,
    NativeMessageHudProfileLoadError,
    NativePlayerPositionError,
    NativePlayerProgressionCoreError,
    NativePlayerSnapshotError,
    NativePlayerSnapshotProfiles,
    NativePlayerTrainingError,
    NativePlayerVitalsError,
    NativePositionProfileLoadError,
    NativeProgressionCoreProfileLoadError,
    NativeRunegateRegistryError,
    NativeRunegateRegistryProfile,
    NativeRunegateRegistryProfileLoadError,
    NativeTargetActionError,
    NativeTargetActionProfileLoadError,
    NativeTargetHealthError,
    NativeTargetIdentityError,
    NativeTargetIdentityProfileLoadError,
    NativeTargetPositionError,
    NativeTargetPositionProfileLoadError,
    NativeTrainingProfileLoadError,
    NativeVendorDialogError,
    NativeVendorDialogProfileLoadError,
    NativeVitalsProfileLoadError,
    NativeWorldMapError,
    NativeZoneProfileLoadError,
    ObservationCalibrationLoadError,
    ObservationDetectionError,
    PyAutoGuiFrameCapture,
    load_bundled_native_character_population_profile,
    load_bundled_native_group_profile,
    load_bundled_native_health_profile,
    load_bundled_native_message_hud_profile,
    load_bundled_native_player_snapshot_profiles,
    load_bundled_native_position_profile,
    load_bundled_native_progression_core_profile,
    load_bundled_native_runegate_registry_profile,
    load_bundled_native_target_action_profile,
    load_bundled_native_target_identity_profile,
    load_bundled_native_target_position_profile,
    load_bundled_native_training_profile,
    load_bundled_native_vitals_profile,
    load_bundled_native_world_map_profile,
    load_bundled_native_zone_profile,
    load_native_character_population_profile,
    load_native_group_profile,
    load_native_health_profile,
    load_native_message_hud_profile,
    load_native_position_profile,
    load_native_progression_core_profile,
    load_native_runegate_registry_profile,
    load_native_target_action_profile,
    load_native_target_identity_profile,
    load_native_target_position_profile,
    load_native_training_profile,
    load_native_vendor_dialog_profile,
    load_native_vitals_profile,
    load_native_world_map_profile,
    load_native_zone_profile,
    load_observation_calibration,
    open_windows_bundled_native_vendor_dialog_tracer,
    open_windows_native_character_population_reader,
    open_windows_native_current_zone_reader,
    open_windows_native_group_reader,
    open_windows_native_message_hud_reader,
    open_windows_native_player_position_reader,
    open_windows_native_player_progression_core_reader,
    open_windows_native_player_snapshot_reader,
    open_windows_native_player_training_reader,
    open_windows_native_player_vitals_reader,
    open_windows_native_runegate_registry_reader,
    open_windows_native_target_action_reader,
    open_windows_native_target_health_reader,
    open_windows_native_target_identity_reader,
    open_windows_native_target_position_reader,
    open_windows_native_vendor_dialog_tracer,
    open_windows_native_world_map_reader,
)
from shadowbane_lab.manager import (
    ClientLifecycleSupervisor,
    ClientRegistrySnapshot,
    ClientWindowRegistry,
    DashboardServer,
    ExactClientWorkerBinding,
    ExactClientWorkerRuntime,
    ExactExtensionEventRouter,
    ForegroundWorkerOperationIngress,
    GuardedWindowControl,
    IsolatedRuntimeCapacityProvisioner,
    LiveConfiguredManagerApplication,
    ManagedWorkerController,
    ManagerDashboardApplication,
    ManagerManifest,
    ManagerSession,
    ManifestClientRegistryProvider,
    SubprocessLauncher,
    SubprocessWorkerLauncher,
    VisibleWindowRegistrySource,
    Win32ProcessLifetimeInspector,
    Win32WindowApi,
    WorkerHeartbeatLedger,
    WorkerOperation,
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationLedger,
    WorkerOperationState,
    WorkerSupervisor,
    WorkerTravelDestination,
    expand_manager_slots,
    load_manager_manifest,
    provision_isolated_client_runtimes,
    recover_manager_bindings,
    replace_manager_manifest,
    retarget_manager_clients,
)
from shadowbane_lab.progression import (
    CalculatorReviewStatus,
    WonderbaneCalculatorImportError,
    audit_proc_assassin_training,
    capture_wonderbane_calculator_snapshot,
    import_wonderbane_calculator_snapshot,
    irekei_proc_assassin_roadmap,
    load_wonderbane_irekei_proc_profile,
)
from shadowbane_lab.pve import (
    PVE_TRACE_SCHEMA_VERSION,
    ClientPvEIntentDispatcher,
    EmptyCombatLogSource,
    PvEApproachController,
    PvECombatCalibrationError,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvERunner,
    PvETraceEvidenceError,
    PvETraceJournal,
    compile_pve_combat_calibration_files,
    save_pve_combat_calibration,
    save_pve_trace_evidence,
)
from shadowbane_lab.travel import (
    ActiveZoneTerrainNavigationSource,
    AStarTravelController,
    ClientTravelDecisionDispatcher,
    PhysicalPointerInteraction,
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
    WindowsGoChatCommandListener,
    WindowsZoneSearchOverlay,
    WorldDestinationCatalog,
    ZoneSearchResult,
    load_active_zone_terrain_navigation,
    load_learned_navigation_map,
    load_world_destination_catalog,
    parse_go_command,
    parse_named_go_command,
    parse_zone_search_command,
    resolve_travel_destination,
    save_learned_navigation_map,
)
from shadowbane_lab.world_data import (
    CacheArchive,
    CacheArchiveFormatError,
    TerrainAlphaFormatError,
    TerrainAlphaTile,
    WorldDefinitionFormatError,
    correlate_zone_terrain,
    index_terrain_alpha_maps,
    load_world_definition,
)

_DOMAIN_EXPORTS = {
    _parser_commands: (
        "_integer_argument",
        "_add_process_arguments",
        "_add_scan_arguments",
        "_parser",
    ),
    _character_commands: (
        "_validate_character_layout",
        "_process_names",
        "_inspect_character_process",
        "_scan_character_text",
        "_scan_character_pointer",
        "_capture_character_snapshot",
        "_snapshot_payload",
    ),
    _manager_commands: (
        "_inspect_manager",
        "_manager_path_status",
        "_preflight_manager",
        "_configure_manager_slots",
        "_configure_manager_build",
        "_provision_manager_runtimes",
        "_write_manager_pid_file",
        "_remove_manager_pid_file",
        "_run_manager_app",
        "_run_manager_worker",
        "_ExactWorkerEngineExecutor",
    ),
    _client_inspection_commands: (
        "_inspect_client",
        "_print_snapshot",
        "_windows_directory",
        "_matches_process_directory",
        "_candidate_description",
        "_discover_client",
        "_validate_profile",
        "_inspect_arcane_hotkeys",
        "_inspect_arcane_hotbar",
        "_inspect_world_data",
        "_observe_target",
        "_read_combat_log",
        "_observe_native_target",
        "_observe_native_target_position",
        "_observe_native_target_identity",
        "_observe_native_population",
        "_observe_native_runegates",
        "_observe_native_world_map",
        "_test_world_map_click",
        "_observe_native_snapshot",
        "_observe_native_player",
        "_observe_native_position",
        "_observe_native_zone",
        "_observe_native_group",
        "_observe_native_progression",
        "_observe_native_training",
        "_trace_native_vendor_dialog",
        "_advise_irekei_proc",
    ),
    _client_pve_commands: (
        "_run_pve",
        "_calibrate_pve",
        "_verify_hotbar_power_mapping",
    ),
    _client_runtime_commands: (
        "_PVE_TARGET_ACTIONS",
        "_wait_for_guarded_client",
        "_require_window_process_id",
    ),
    _client_travel_commands: (
        "_run_travel",
        "_catalog_with_live_runegates",
    ),
    _client_listener_commands: (
        "_listen_for_go_commands",
        "_load_world_map_close_plan",
        "_new_chat_pve_evidence_path",
        "_print_go_listener_event",
        "_print_go_stop_result",
        "_print_zone_search_results",
    ),
    _progression_commands: ("_import_wonderbane_calculator", "_parse_retrieved_at"),
    _common_commands: ("_error",),
}
_DOMAIN_ORIGINALS = {
    module: {name: getattr(module, name) for name in names}
    for module, names in _DOMAIN_EXPORTS.items()
}


def _sync_domain_compatibility(_module: object) -> None:
    for module, defaults in _DOMAIN_MODULE_DEFAULTS.items():
        namespace = vars(module)
        for name, original in defaults.items():
            if name not in _FACADE_DEFAULTS or name not in globals():
                continue
            facade_value = globals()[name]
            default_value = _FACADE_DEFAULTS[name]
            namespace[name] = original if facade_value is default_value else facade_value


def _domain_facade(module: object, name: str):
    implementation = _DOMAIN_ORIGINALS[module][name]

    def call(*args, **kwargs):
        _sync_domain_compatibility(module)
        return implementation(*args, **kwargs)

    call.__name__ = name
    call.__qualname__ = name
    call.__doc__ = implementation.__doc__
    return call


_DOMAIN_MODULE_DEFAULTS = {module: dict(vars(module)) for module in _DOMAIN_EXPORTS}
_integer_argument = _domain_facade(_parser_commands, "_integer_argument")
_add_process_arguments = _domain_facade(_parser_commands, "_add_process_arguments")
_add_scan_arguments = _domain_facade(_parser_commands, "_add_scan_arguments")
_parser = _domain_facade(_parser_commands, "_parser")
_validate_character_layout = _domain_facade(_character_commands, "_validate_character_layout")
_process_names = _domain_facade(_character_commands, "_process_names")
_inspect_character_process = _domain_facade(_character_commands, "_inspect_character_process")
_scan_character_text = _domain_facade(_character_commands, "_scan_character_text")
_scan_character_pointer = _domain_facade(_character_commands, "_scan_character_pointer")
_capture_character_snapshot = _domain_facade(_character_commands, "_capture_character_snapshot")
_snapshot_payload = _domain_facade(_character_commands, "_snapshot_payload")
_inspect_manager = _domain_facade(_manager_commands, "_inspect_manager")
_manager_path_status = _domain_facade(_manager_commands, "_manager_path_status")
_preflight_manager = _domain_facade(_manager_commands, "_preflight_manager")
_configure_manager_slots = _domain_facade(_manager_commands, "_configure_manager_slots")
_configure_manager_build = _domain_facade(_manager_commands, "_configure_manager_build")
_provision_manager_runtimes = _domain_facade(_manager_commands, "_provision_manager_runtimes")
_write_manager_pid_file = _domain_facade(_manager_commands, "_write_manager_pid_file")
_remove_manager_pid_file = _domain_facade(_manager_commands, "_remove_manager_pid_file")
_run_manager_app = _domain_facade(_manager_commands, "_run_manager_app")
_run_manager_worker = _domain_facade(_manager_commands, "_run_manager_worker")
_ExactWorkerEngineExecutor = _manager_commands._ExactWorkerEngineExecutor
_inspect_client = _domain_facade(_client_inspection_commands, "_inspect_client")
_print_snapshot = _domain_facade(_client_inspection_commands, "_print_snapshot")
_windows_directory = _domain_facade(_client_inspection_commands, "_windows_directory")
_matches_process_directory = _domain_facade(
    _client_inspection_commands, "_matches_process_directory"
)
_candidate_description = _domain_facade(_client_inspection_commands, "_candidate_description")
_discover_client = _domain_facade(_client_inspection_commands, "_discover_client")
_validate_profile = _domain_facade(_client_inspection_commands, "_validate_profile")
_inspect_arcane_hotkeys = _domain_facade(_client_inspection_commands, "_inspect_arcane_hotkeys")
_inspect_arcane_hotbar = _domain_facade(_client_inspection_commands, "_inspect_arcane_hotbar")
_inspect_world_data = _domain_facade(_client_inspection_commands, "_inspect_world_data")
_observe_target = _domain_facade(_client_inspection_commands, "_observe_target")
_read_combat_log = _domain_facade(_client_inspection_commands, "_read_combat_log")
_observe_native_target = _domain_facade(_client_inspection_commands, "_observe_native_target")
_observe_native_target_position = _domain_facade(
    _client_inspection_commands, "_observe_native_target_position"
)
_observe_native_target_identity = _domain_facade(
    _client_inspection_commands, "_observe_native_target_identity"
)
_observe_native_population = _domain_facade(
    _client_inspection_commands, "_observe_native_population"
)
_observe_native_runegates = _domain_facade(_client_inspection_commands, "_observe_native_runegates")
_observe_native_world_map = _domain_facade(_client_inspection_commands, "_observe_native_world_map")
_test_world_map_click = _domain_facade(_client_inspection_commands, "_test_world_map_click")
_observe_native_snapshot = _domain_facade(
    _client_inspection_commands, "_observe_native_snapshot"
)
_observe_native_player = _domain_facade(_client_inspection_commands, "_observe_native_player")
_observe_native_position = _domain_facade(_client_inspection_commands, "_observe_native_position")
_observe_native_zone = _domain_facade(_client_inspection_commands, "_observe_native_zone")
_observe_native_group = _domain_facade(_client_inspection_commands, "_observe_native_group")
_observe_native_progression = _domain_facade(
    _client_inspection_commands, "_observe_native_progression"
)
_observe_native_training = _domain_facade(_client_inspection_commands, "_observe_native_training")
_trace_native_vendor_dialog = _domain_facade(
    _client_inspection_commands, "_trace_native_vendor_dialog"
)
_advise_irekei_proc = _domain_facade(_client_inspection_commands, "_advise_irekei_proc")
_run_pve = _domain_facade(_client_pve_commands, "_run_pve")
_calibrate_pve = _domain_facade(_client_pve_commands, "_calibrate_pve")
_run_travel = _domain_facade(_client_travel_commands, "_run_travel")
_catalog_with_live_runegates = _domain_facade(
    _client_travel_commands, "_catalog_with_live_runegates"
)
_listen_for_go_commands = _domain_facade(_client_listener_commands, "_listen_for_go_commands")
_load_world_map_close_plan = _domain_facade(
    _client_listener_commands, "_load_world_map_close_plan"
)
_new_chat_pve_evidence_path = _domain_facade(
    _client_listener_commands, "_new_chat_pve_evidence_path"
)
_print_go_listener_event = _domain_facade(_client_listener_commands, "_print_go_listener_event")
_print_go_stop_result = _domain_facade(_client_listener_commands, "_print_go_stop_result")
_print_zone_search_results = _domain_facade(_client_listener_commands, "_print_zone_search_results")
_verify_hotbar_power_mapping = _domain_facade(_client_pve_commands, "_verify_hotbar_power_mapping")
_wait_for_guarded_client = _domain_facade(_client_runtime_commands, "_wait_for_guarded_client")
_require_window_process_id = _domain_facade(_client_runtime_commands, "_require_window_process_id")
_PVE_TARGET_ACTIONS = _client_runtime_commands._PVE_TARGET_ACTIONS
_import_wonderbane_calculator = _domain_facade(
    _progression_commands, "_import_wonderbane_calculator"
)
_parse_retrieved_at = _domain_facade(_progression_commands, "_parse_retrieved_at")
_error = _domain_facade(_common_commands, "_error")
_FACADE_DEFAULTS = dict(globals())


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "evidence":
        return _evidence_commands.handle(arguments)
    if arguments.command == "fingerprint":
        return _fingerprint_commands.handle(arguments)
    if arguments.command == "case":
        return _case_commands.handle_case(arguments)
    if arguments.command == "experiment":
        return _case_commands.handle_experiment(arguments)
    if arguments.command == "diagnose":
        return _diagnostic_commands.handle(arguments)
    if arguments.command == "character" and arguments.character_command == "validate-layout":
        return _validate_character_layout(arguments.layout, as_json=arguments.json)
    if arguments.command == "character" and arguments.character_command == "inspect-process":
        return _inspect_character_process(
            process_names=arguments.process_names,
            process_id=arguments.pid,
            as_json=arguments.json,
        )
    if arguments.command == "character" and arguments.character_command == "scan-text":
        return _scan_character_text(
            text=arguments.text,
            encodings=arguments.encodings,
            process_names=arguments.process_names,
            process_id=arguments.pid,
            max_matches=arguments.max_matches,
            max_scan_mib=arguments.max_scan_mib,
            context_bytes=arguments.context_bytes,
            as_json=arguments.json,
        )
    if arguments.command == "character" and arguments.character_command == "scan-pointer":
        return _scan_character_pointer(
            address=arguments.address,
            process_names=arguments.process_names,
            process_id=arguments.pid,
            max_matches=arguments.max_matches,
            max_scan_mib=arguments.max_scan_mib,
            context_bytes=arguments.context_bytes,
            as_json=arguments.json,
        )
    if arguments.command == "character" and arguments.character_command == "snapshot":
        return _capture_character_snapshot(
            layout_path=arguments.layout,
            output_path=arguments.output,
            process_id=arguments.pid,
            as_json=arguments.json,
        )
    if arguments.command == "manager" and arguments.manager_command == "inspect":
        return _inspect_manager(
            node_id=arguments.node_id,
            executable_names=arguments.executable_names or (),
            process_directory=arguments.process_directory,
            as_json=arguments.json,
        )
    if arguments.command == "manager" and arguments.manager_command == "preflight":
        return _preflight_manager(arguments.manifest, as_json=arguments.json)
    if arguments.command == "manager" and arguments.manager_command == "configure-slots":
        return _configure_manager_slots(
            arguments.manifest,
            count=arguments.count,
            display_width=arguments.display_width,
            display_height=arguments.display_height,
            apply=arguments.apply,
            as_json=arguments.json,
        )
    if arguments.command == "manager" and arguments.manager_command == "configure-build":
        return _configure_manager_build(
            arguments.manifest,
            game_directory=arguments.game_directory,
            executable_name=arguments.executable_name,
            apply=arguments.apply,
            as_json=arguments.json,
        )
    if arguments.command == "manager" and arguments.manager_command == "provision-runtimes":
        return _provision_manager_runtimes(
            arguments.manifest,
            frozen_directory=arguments.frozen_directory,
            deployment_directory=arguments.deployment_directory,
            patch_manifest_path=arguments.patch_manifest,
            extension_artifact=arguments.extension_artifact,
            deployment_id=arguments.deployment_id,
            slot_count=arguments.slot_count,
            executable_name=arguments.executable_name,
            resolution_width=arguments.resolution_width,
            resolution_height=arguments.resolution_height,
            apply=arguments.apply,
            as_json=arguments.json,
        )
    if arguments.command == "manager" and arguments.manager_command == "app":
        return _run_manager_app(
            arguments.manifest,
            port=arguments.port,
            launch_timeout_seconds=arguments.launch_timeout_seconds,
            poll_ms=arguments.poll_ms,
            worker_state_directory=arguments.worker_state_directory,
            pid_file=arguments.pid_file,
            authorization_token_file=arguments.authorization_token_file,
            open_browser=not arguments.no_browser,
            live=arguments.live,
        )
    if arguments.command == "manager" and arguments.manager_command == "worker":
        return _run_manager_worker(
            arguments.manifest,
            worker_state_directory=arguments.worker_state_directory,
            client_id=arguments.client_id,
            instance_id=arguments.instance_id,
            game_process_id=arguments.game_process_id,
            game_process_started_at_100ns=arguments.game_process_started_at_100ns,
            game_window_handle=arguments.game_window_handle,
            heartbeat_ms=arguments.heartbeat_ms,
            destination_state_path=arguments.destination_state,
            client_profile_path=arguments.client_profile,
            native_position_profile_path=arguments.native_position_profile,
            native_vitals_profile_path=arguments.native_vitals_profile,
            pve_client_profile_path=arguments.pve_client_profile,
            pve_hotbar_config_path=arguments.pve_hotbar_config,
            pve_evidence_directory=arguments.pve_evidence_directory,
            navigation_cache_directory=arguments.navigation_cache_directory,
            learned_navigation_state_path=arguments.learned_navigation_state,
            pve_max_kills=arguments.pve_max_kills,
            pve_max_seconds=arguments.pve_max_seconds,
            pve_max_encounter_seconds=arguments.pve_max_encounter_seconds,
            pve_recovery_timeout_seconds=arguments.pve_recovery_timeout_seconds,
            pve_poll_ms=arguments.pve_poll_ms,
            pve_camp_radius=arguments.pve_camp_radius,
            pve_retained_trace_steps=arguments.pve_retained_trace_steps,
            travel_max_seconds=arguments.travel_max_seconds,
            travel_poll_ms=arguments.travel_poll_ms,
            travel_click_interval_ms=arguments.travel_click_interval_ms,
            live=arguments.live,
        )
    if (
        arguments.command == "progression"
        and arguments.progression_command == "import-wonderbane-calculator"
    ):
        return _import_wonderbane_calculator(
            arguments.snapshot,
            arguments.output,
            download=arguments.download,
            retrieved_at_text=arguments.retrieved_at,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "inspect":
        return _inspect_client(as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "discover":
        return _discover_client(
            arguments.process_directory,
            wait_seconds=arguments.wait_seconds,
            poll_seconds=arguments.poll_seconds,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "validate-profile":
        return _validate_profile(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "inspect-hotkeys":
        return _inspect_arcane_hotkeys(arguments.preferences, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "inspect-hotbar":
        return _inspect_arcane_hotbar(arguments.character_config, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "inspect-world-data":
        return _inspect_world_data(
            arguments.cache_directory,
            arguments.world_def,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "observe-target":
        return _observe_target(
            arguments.client_profile,
            arguments.observation_profile,
            wait_seconds=arguments.wait_seconds,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "read-combat-log":
        return _read_combat_log(
            arguments.path,
            limit=arguments.limit,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "observe-native-target":
        return _observe_native_target(arguments.profile, as_json=arguments.json)
    if (
        arguments.command == "client"
        and arguments.client_command == "observe-native-target-position"
    ):
        return _observe_native_target_position(arguments.profile, as_json=arguments.json)
    if (
        arguments.command == "client"
        and arguments.client_command == "observe-native-target-identity"
    ):
        return _observe_native_target_identity(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-population":
        return _observe_native_population(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-runegates":
        return _observe_native_runegates(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-world-map":
        return _observe_native_world_map(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "test-world-map-click":
        return _test_world_map_click(
            client_profile_path=arguments.client_profile,
            native_world_map_profile_path=arguments.native_world_map_profile,
            map_x_fraction=arguments.map_x_fraction,
            map_y_fraction=arguments.map_y_fraction,
            wait_for_client_seconds=arguments.wait_for_client_seconds,
            timeout_seconds=arguments.timeout_seconds,
            evidence_output_path=arguments.evidence_output,
            live=arguments.live,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "observe-native-snapshot":
        return _observe_native_snapshot(
            arguments.progression_profile,
            arguments.training_profile,
            arguments.vitals_profile,
            process_id=arguments.process_id,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "observe-native-player":
        return _observe_native_player(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-position":
        return _observe_native_position(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-zone":
        return _observe_native_zone(
            arguments.profile,
            arguments.cache_directory,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "observe-native-group":
        return _observe_native_group(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-progression":
        return _observe_native_progression(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-training":
        return _observe_native_training(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "trace-native-vendor-dialog":
        return _trace_native_vendor_dialog(
            arguments.profile,
            process_id=arguments.process_id,
            output_path=arguments.output,
            label=arguments.label,
            timeout_seconds=arguments.timeout_seconds,
            settle_seconds=arguments.settle_seconds,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "advise-irekei-proc":
        return _advise_irekei_proc(
            arguments.progression_profile,
            arguments.training_profile,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "calibrate-pve":
        return _calibrate_pve(
            arguments.evidence,
            arguments.output,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "run-pve":
        return _run_pve(
            client_profile_path=arguments.client_profile,
            combat_log_path=arguments.combat_log,
            combat_source=arguments.combat_source,
            hotbar_config_path=arguments.hotbar_config,
            native_health_profile_path=arguments.native_health_profile,
            native_message_hud_profile_path=arguments.native_message_hud_profile,
            native_vitals_profile_path=arguments.native_vitals_profile,
            native_position_profile_path=arguments.native_position_profile,
            native_target_position_profile_path=arguments.native_target_position_profile,
            native_target_action_profile_path=arguments.native_target_action_profile,
            native_target_identity_profile_path=arguments.native_target_identity_profile,
            native_character_population_profile_path=(
                arguments.native_character_population_profile
            ),
            navigation_cache_directory=arguments.navigation_cache_directory,
            max_kills=arguments.max_kills,
            max_seconds=arguments.max_seconds,
            max_encounter_seconds=arguments.max_encounter_seconds,
            recovery_timeout_seconds=arguments.recovery_timeout_seconds,
            recovery_health_fraction=arguments.recovery_health_fraction,
            recovery_mana_fraction=arguments.recovery_mana_fraction,
            recovery_stamina_fraction=arguments.recovery_stamina_fraction,
            wait_for_client_seconds=arguments.wait_for_client_seconds,
            poll_ms=arguments.poll_ms,
            policy=arguments.policy,
            live=arguments.live,
            as_json=arguments.json,
            evidence_output_path=arguments.evidence_output,
            continuous=arguments.continuous,
            camp_radius=arguments.camp_radius,
            retained_trace_steps=arguments.retained_trace_steps,
        )
    if arguments.command == "client" and arguments.client_command == "go":
        return _run_travel(
            lt=arguments.lt,
            lg=arguments.lg,
            radius=arguments.radius,
            destination_state_path=arguments.destination_state,
            client_profile_path=arguments.client_profile,
            native_position_profile_path=arguments.native_position_profile,
            native_vitals_profile_path=arguments.native_vitals_profile,
            max_seconds=arguments.max_seconds,
            wait_for_client_seconds=arguments.wait_for_client_seconds,
            poll_ms=arguments.poll_ms,
            click_interval_ms=arguments.click_interval_ms,
            live=arguments.live,
            as_json=arguments.json,
            navigation_cache_directory=arguments.navigation_cache_directory,
        )
    if arguments.command == "client" and arguments.client_command == "listen-go":
        return _listen_for_go_commands(
            destination_state_path=arguments.destination_state,
            client_profile_path=arguments.client_profile,
            native_position_profile_path=arguments.native_position_profile,
            native_vitals_profile_path=arguments.native_vitals_profile,
            native_runegate_profile_path=arguments.native_runegate_profile,
            native_world_map_profile_path=arguments.native_world_map_profile,
            hotkey_config_path=arguments.hotkey_config,
            world_def_path=arguments.world_def,
            named_destination_overrides_path=arguments.named_destination_overrides,
            pve_client_profile_path=arguments.pve_client_profile,
            pve_hotbar_config_path=arguments.pve_hotbar_config,
            pve_evidence_directory=arguments.pve_evidence_directory,
            navigation_cache_directory=arguments.navigation_cache_directory,
            learned_navigation_state_path=arguments.learned_navigation_state,
            pve_max_kills=arguments.pve_max_kills,
            pve_max_seconds=arguments.pve_max_seconds,
            pve_max_encounter_seconds=arguments.pve_max_encounter_seconds,
            pve_recovery_timeout_seconds=arguments.pve_recovery_timeout_seconds,
            pve_poll_ms=arguments.pve_poll_ms,
            pve_continuous=arguments.pve_continuous,
            pve_camp_radius=arguments.pve_camp_radius,
            pve_retained_trace_steps=arguments.pve_retained_trace_steps,
            max_seconds=arguments.max_seconds,
            wait_for_client_seconds=arguments.wait_for_client_seconds,
            poll_ms=arguments.poll_ms,
            click_interval_ms=arguments.click_interval_ms,
            manager_manifest_path=arguments.manager_manifest,
            worker_state_directory=arguments.worker_state_directory,
            live=arguments.live,
            as_json=arguments.json,
        )
    raise RuntimeError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
