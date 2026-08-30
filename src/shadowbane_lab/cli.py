"""Command-line diagnostics used by the WonderBane VM bootstrap."""

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
from shadowbane_lab.client_action import (
    ClientActionEvidenceError,
    ClientActionRunner,
    WorldMapDestinationClickAction,
    save_client_action_evidence,
)
from shadowbane_lab.client_extension import (
    ExtensionHeartbeatStatusProvider,
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


def _integer_argument(value: str) -> int:
    try:
        parsed = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer or 0x-prefixed value") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def _add_process_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pid", type=int, help="target one client when multiple are open")
    parser.add_argument(
        "--process",
        action="append",
        dest="process_names",
        help="allowed executable name; may be repeated (default: Shadowbane.exe)",
    )


def _add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    _add_process_arguments(parser)
    parser.add_argument("--max-matches", type=int, default=50)
    parser.add_argument("--max-scan-mib", type=int, default=256)
    parser.add_argument("--context-bytes", type=int, default=32)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shadowbane-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    client = commands.add_parser("client", help="inspect and validate client integration")
    client_commands = client.add_subparsers(dest="client_command", required=True)

    character = commands.add_parser(
        "character",
        help="discover and capture read-only WonderBane character state",
    )
    character_commands = character.add_subparsers(dest="character_command", required=True)

    validate_layout = character_commands.add_parser(
        "validate-layout",
        help="strictly validate a process-memory character layout",
    )
    validate_layout.add_argument("layout", type=Path)
    validate_layout.add_argument("--json", action="store_true")

    inspect_process = character_commands.add_parser(
        "inspect-process",
        help="pin the running client PID, executable hash, pointer size, and modules",
    )
    _add_process_arguments(inspect_process)
    inspect_process.add_argument("--json", action="store_true")

    scan_text = character_commands.add_parser(
        "scan-text",
        help="scan readable pages for a character or item name without dumping memory",
    )
    scan_text.add_argument("text")
    scan_text.add_argument(
        "--encoding",
        action="append",
        dest="encodings",
        help="text encoding; may be repeated (defaults: cp1252, utf-8, utf-16le)",
    )
    _add_scan_arguments(scan_text)

    scan_pointer = character_commands.add_parser(
        "scan-pointer",
        help="find read-only pointer references to a candidate address",
    )
    scan_pointer.add_argument("address", type=_integer_argument)
    _add_scan_arguments(scan_pointer)

    snapshot = character_commands.add_parser(
        "snapshot",
        help="capture declared character fields from a hash-pinned layout",
    )
    snapshot.add_argument("layout", type=Path)
    snapshot.add_argument("--output", type=Path)
    snapshot.add_argument("--pid", type=int)
    snapshot.add_argument("--json", action="store_true")

    inspect = client_commands.add_parser(
        "inspect",
        help="read the current foreground Win32 client without sending input",
    )
    inspect.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    discover = client_commands.add_parser(
        "discover",
        help="find one visible client by its executable directory without changing focus",
    )
    discover.add_argument(
        "--process-directory",
        type=Path,
        required=True,
        help="directory containing the expected game process executable",
    )
    discover.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="maximum time to wait for exactly one matching visible window",
    )
    discover.add_argument(
        "--poll-seconds",
        type=float,
        default=0.5,
        help="delay between visible-window scans while waiting",
    )
    discover.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    validate = client_commands.add_parser(
        "validate-profile",
        help="strictly load a client calibration profile",
    )
    validate.add_argument("profile", type=Path)
    validate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    inspect_hotkeys = client_commands.add_parser(
        "inspect-hotkeys",
        help="read native target-cycle bindings from ArcanePref.cfg without changing them",
    )
    inspect_hotkeys.add_argument("preferences", type=Path)
    inspect_hotkeys.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    inspect_hotbar = client_commands.add_parser(
        "inspect-hotbar",
        help="read F1-F12 power assignments from a character SCREEN_GAME config",
    )
    inspect_hotbar.add_argument("character_config", type=Path)
    inspect_hotbar.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    inspect_world_data = client_commands.add_parser(
        "inspect-world-data",
        help="inspect local world, terrain, mesh, and collision cache indexes",
    )
    inspect_world_data.add_argument(
        "cache_directory",
        type=Path,
        help="client cache directory containing TerrainAlpha.cache and related archives",
    )
    inspect_world_data.add_argument(
        "--world-def",
        type=Path,
        help="optional Config/WorldDef.cfg placement tree",
    )
    inspect_world_data.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_target = client_commands.add_parser(
        "observe-target",
        help="read target presence and health from the guarded foreground client",
    )
    observe_target.add_argument(
        "--client-profile",
        type=Path,
        required=True,
        help="validated client input/window profile",
    )
    observe_target.add_argument(
        "--observation-profile",
        type=Path,
        required=True,
        help="target-frame pixel calibration paired with the client profile",
    )
    observe_target.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="maximum time to wait for the calibrated client to become foreground",
    )
    observe_target.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    read_combat_log = client_commands.add_parser(
        "read-combat-log",
        help="read exact messages from a Shadowbane text HUD's native log file",
    )
    read_combat_log.add_argument("path", type=Path)
    read_combat_log.add_argument(
        "--limit",
        type=int,
        help="return only the newest N complete records",
    )
    read_combat_log.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    observe_native_target = client_commands.add_parser(
        "observe-native-target",
        help="read exact selected-target health from a calibrated Shadowbane build",
    )
    observe_native_target.add_argument(
        "--profile",
        type=Path,
        help="native health profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_target.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_target_position = client_commands.add_parser(
        "observe-native-target-position",
        help="read exact selected-target LT, LG, and altitude from a calibrated build",
    )
    observe_native_target_position.add_argument(
        "--profile",
        type=Path,
        help=("native target-position profile; defaults to the verified bundled WonderBane build"),
    )
    observe_native_target_position.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_target_identity = client_commands.add_parser(
        "observe-native-target-identity",
        help="read exact selected-target trainer and service-role flags",
    )
    observe_native_target_identity.add_argument(
        "--profile",
        type=Path,
        help=("native target-identity profile; defaults to the verified bundled WonderBane build"),
    )
    observe_native_target_identity.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_population = client_commands.add_parser(
        "observe-native-population",
        help="enumerate loaded characters without changing the selected target",
    )
    observe_native_population.add_argument(
        "--profile",
        type=Path,
        help=(
            "native character-population profile; defaults to the verified bundled WonderBane build"
        ),
    )
    observe_native_population.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_runegates = client_commands.add_parser(
        "observe-native-runegates",
        help="read the active server-supplied runegate registry from a calibrated build",
    )
    observe_native_runegates.add_argument(
        "--profile",
        type=Path,
        help="native runegate profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_runegates.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_world_map = client_commands.add_parser(
        "observe-native-world-map",
        help="read the live world-map bounds, visibility, zoom, and pan",
    )
    observe_native_world_map.add_argument(
        "--profile",
        type=Path,
        help="native world-map profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_world_map.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    test_world_map_click = client_commands.add_parser(
        "test-world-map-click",
        help="dispatch and natively verify one bounded world-map destination click",
    )
    test_world_map_click.add_argument("--client-profile", type=Path, required=True)
    test_world_map_click.add_argument(
        "--native-world-map-profile",
        type=Path,
        help="native world-map profile; defaults to the verified bundled WonderBane build",
    )
    test_world_map_click.add_argument(
        "--map-x-fraction",
        type=float,
        required=True,
        help="horizontal test point in the live map rectangle, from 0 through 1",
    )
    test_world_map_click.add_argument(
        "--map-y-fraction",
        type=float,
        required=True,
        help="vertical test point in the live map rectangle, from 0 through 1",
    )
    test_world_map_click.add_argument(
        "--wait-for-client-seconds",
        type=float,
        default=15.0,
        help="time allowed to foreground the exact client with its world map open",
    )
    test_world_map_click.add_argument(
        "--timeout-seconds",
        type=float,
        default=2.0,
        help="bounded wait for the matching native extension event",
    )
    test_world_map_click.add_argument(
        "--evidence-output",
        type=Path,
        help="write a new versioned action-lifecycle evidence artifact",
    )
    test_world_map_click.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    test_world_map_click.add_argument(
        "--json", action="store_true", help="emit machine-readable lifecycle evidence"
    )

    observe_native_player = client_commands.add_parser(
        "observe-native-player",
        help="read exact local-player health, mana, and stamina from a calibrated build",
    )
    observe_native_player.add_argument(
        "--profile",
        type=Path,
        help="native vitals profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_player.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_position = client_commands.add_parser(
        "observe-native-position",
        help="read exact local-player LT, LG, and altitude from a calibrated build",
    )
    observe_native_position.add_argument(
        "--profile",
        type=Path,
        help="native position profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_position.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_zone = client_commands.add_parser(
        "observe-native-zone",
        help="read the current zone already resolved by a calibrated Shadowbane build",
    )
    observe_native_zone.add_argument(
        "--profile",
        type=Path,
        help="native zone profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_zone.add_argument(
        "--cache-directory",
        type=Path,
        help="optionally join the active zone chain to CZone and TerrainAlpha caches",
    )
    observe_native_zone.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_group = client_commands.add_parser(
        "observe-native-group",
        help="read the current group roster, resources, positions, and follow state",
    )
    observe_native_group.add_argument(
        "--profile",
        type=Path,
        help="native group profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_group.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_progression = client_commands.add_parser(
        "observe-native-progression",
        help="read level, unspent points, attack ratings, and defense from a calibrated build",
    )
    observe_native_progression.add_argument(
        "--profile",
        type=Path,
        help="native progression profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_progression.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_training = client_commands.add_parser(
        "observe-native-training",
        help="read exact local-player skill and power vectors from a calibrated build",
    )
    observe_native_training.add_argument(
        "--profile",
        type=Path,
        help="native training profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_training.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    trace_native_vendor_dialog = client_commands.add_parser(
        "trace-native-vendor-dialog",
        help="capture decrypted ArcMerchantMessage traffic without patching client code",
    )
    trace_native_vendor_dialog.add_argument(
        "--profile",
        type=Path,
        help="native vendor-dialog profile; defaults to the verified WonderBane build",
    )
    trace_native_vendor_dialog.add_argument(
        "--process-id",
        type=int,
        help="specific sb.exe process id; defaults to the unique running process",
    )
    trace_native_vendor_dialog.add_argument("--output", type=Path, required=True)
    trace_native_vendor_dialog.add_argument("--label", required=True)
    trace_native_vendor_dialog.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="maximum time to wait for the first vendor message",
    )
    trace_native_vendor_dialog.add_argument(
        "--settle-seconds",
        type=float,
        default=2.0,
        help="stop after this quiet interval once vendor traffic begins",
    )
    trace_native_vendor_dialog.add_argument(
        "--json", action="store_true", help="emit a machine-readable session summary"
    )

    advise_irekei_proc = client_commands.add_parser(
        "advise-irekei-proc",
        help="compare the live character's exact ranks with the sourced proc-Assassin roadmap",
    )
    advise_irekei_proc.add_argument(
        "--progression-profile",
        type=Path,
        help="native scalar progression profile; defaults to the verified WonderBane build",
    )
    advise_irekei_proc.add_argument(
        "--training-profile",
        type=Path,
        help="native skill/power profile; defaults to the verified WonderBane build",
    )
    advise_irekei_proc.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    run_pve = client_commands.add_parser(
        "run-pve",
        help="run native-observation PvE against nearby mobiles",
    )
    run_pve.add_argument("--client-profile", type=Path, required=True)
    run_pve.add_argument(
        "--combat-source",
        choices=("state", "hud", "log"),
        help=(
            "combat evidence source; state uses exact health/action observations, HUD is "
            "the default unless --combat-log is supplied for legacy file logging"
        ),
    )
    run_pve.add_argument("--combat-log", type=Path)
    run_pve.add_argument(
        "--hotbar-config",
        type=Path,
        help="character SCREEN_GAME config; required by policies that activate hotbar powers",
    )
    run_pve.add_argument("--native-health-profile", type=Path)
    run_pve.add_argument("--native-message-hud-profile", type=Path)
    run_pve.add_argument("--native-vitals-profile", type=Path)
    run_pve.add_argument("--native-position-profile", type=Path)
    run_pve.add_argument("--native-target-position-profile", type=Path)
    run_pve.add_argument("--native-target-action-profile", type=Path)
    run_pve.add_argument("--native-target-identity-profile", type=Path)
    run_pve.add_argument("--native-character-population-profile", type=Path)
    run_pve.add_argument(
        "--navigation-cache-directory",
        type=Path,
        help=(
            "client cache directory used to seed the approach A* cost map from the "
            "active zone's height field"
        ),
    )
    run_pve.add_argument("--max-kills", type=int, default=1)
    run_pve.add_argument("--max-seconds", type=float, default=120.0)
    run_pve.add_argument("--max-encounter-seconds", type=float, default=120.0)
    run_pve.add_argument(
        "--continuous",
        action="store_true",
        help="run until explicitly stopped while remaining inside the starting camp",
    )
    run_pve.add_argument(
        "--camp-radius",
        type=float,
        default=120.0,
        help="continuous target-admission radius around the starting LT/LG",
    )
    run_pve.add_argument(
        "--retained-trace-steps",
        type=int,
        default=2_000,
        help="maximum continuous trace tail retained in memory",
    )
    run_pve.add_argument("--recovery-timeout-seconds", type=float, default=30.0)
    run_pve.add_argument("--recovery-health-fraction", type=float, default=0.75)
    run_pve.add_argument("--recovery-mana-fraction", type=float, default=0.15)
    run_pve.add_argument("--recovery-stamina-fraction", type=float, default=0.25)
    run_pve.add_argument("--wait-for-client-seconds", type=float, default=15.0)
    run_pve.add_argument("--poll-ms", type=int, default=100)
    run_pve.add_argument(
        "--evidence-output",
        type=Path,
        help="write final versioned evidence; continuous mode adds a JSONL journal",
    )
    run_pve.add_argument(
        "--policy",
        choices=("basic", "proc-assassin"),
        default="basic",
        help=(
            "control policy; proc-assassin accepts auto-targets and uses "
            "Shadow Touch to interrupt a native queued attack"
        ),
    )
    run_pve.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    run_pve.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    calibrate_pve = client_commands.add_parser(
        "calibrate-pve",
        help="compile one or more versioned live PvE traces into simulator evidence",
    )
    calibrate_pve.add_argument(
        "--evidence",
        type=Path,
        nargs="+",
        required=True,
        help="versioned PvE evidence artifacts produced by client run-pve",
    )
    calibrate_pve.add_argument("--output", type=Path, required=True)
    calibrate_pve.add_argument("--json", action="store_true", help="emit the compiled calibration")

    go = client_commands.add_parser(
        "go",
        help="travel to an LT/LG destination through bounded, feedback-checked minimap clicks",
    )
    go.add_argument("lt", type=float, nargs="?")
    go.add_argument("lg", type=float, nargs="?")
    go.add_argument(
        "--radius",
        type=float,
        help="arrival radius; bare go reuses the remembered radius when omitted",
    )
    go.add_argument(
        "--destination-state",
        type=Path,
        default=Path.home() / ".shadowbane-lab" / "last-travel-destination.json",
        help="local state file used to remember the last explicit destination",
    )
    go.add_argument("--client-profile", type=Path, required=True)
    go.add_argument("--native-position-profile", type=Path)
    go.add_argument("--native-vitals-profile", type=Path)
    go.add_argument(
        "--navigation-cache-directory",
        type=Path,
        help="client cache directory used for adaptive active-zone A* travel",
    )
    go.add_argument("--max-seconds", type=float, default=300.0)
    go.add_argument("--wait-for-client-seconds", type=float, default=30.0)
    go.add_argument("--poll-ms", type=int, default=200)
    go.add_argument("--click-interval-ms", type=int, default=2_000)
    go.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    go.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    listen_go = client_commands.add_parser(
        "listen-go",
        help="listen for foreground in-game /go, /zone, /pve, and /stop commands",
    )
    listen_go.add_argument(
        "--destination-state",
        type=Path,
        default=Path.home() / ".shadowbane-lab" / "last-travel-destination.json",
        help="local state file used to remember the last explicit destination",
    )
    listen_go.add_argument("--client-profile", type=Path, required=True)
    listen_go.add_argument("--native-position-profile", type=Path)
    listen_go.add_argument("--native-vitals-profile", type=Path)
    listen_go.add_argument("--native-runegate-profile", type=Path)
    listen_go.add_argument("--native-world-map-profile", type=Path)
    listen_go.add_argument(
        "--hotkey-config",
        type=Path,
        help="config containing BEGINHOTKEYS, used to close the world map",
    )
    listen_go.add_argument(
        "--world-def",
        type=Path,
        help="installed Config/WorldDef.cfg used to resolve named /go destinations",
    )
    listen_go.add_argument(
        "--named-destination-overrides",
        type=Path,
        help="emulator-confirmed named destinations layered over client WorldDef entries",
    )
    listen_go.add_argument(
        "--pve-client-profile",
        type=Path,
        help="live PvE input profile; enables the in-game /pve command",
    )
    listen_go.add_argument(
        "--pve-hotbar-config",
        type=Path,
        help="current character SCREEN_GAME config used to verify Shadow Touch",
    )
    listen_go.add_argument(
        "--pve-evidence-directory",
        type=Path,
        help="directory for one timestamped evidence artifact per /pve run",
    )
    listen_go.add_argument(
        "--navigation-cache-directory",
        "--pve-navigation-cache-directory",
        dest="navigation_cache_directory",
        type=Path,
        help="client cache directory used for adaptive /go and /pve A* routes",
    )
    listen_go.add_argument(
        "--learned-navigation-state",
        type=Path,
        help="durable exact obstacle cells learned from stalled /go and /pve movement",
    )
    listen_go.add_argument("--pve-max-kills", type=int, default=3)
    listen_go.add_argument("--pve-max-seconds", type=float, default=300.0)
    listen_go.add_argument("--pve-max-encounter-seconds", type=float, default=120.0)
    listen_go.add_argument(
        "--pve-continuous",
        action="store_true",
        help="make /pve run until stopped inside a camp anchored at startup",
    )
    listen_go.add_argument("--pve-camp-radius", type=float, default=120.0)
    listen_go.add_argument("--pve-retained-trace-steps", type=int, default=2_000)
    listen_go.add_argument("--pve-recovery-timeout-seconds", type=float, default=30.0)
    listen_go.add_argument("--pve-poll-ms", type=int, default=100)
    listen_go.add_argument("--max-seconds", type=float, default=300.0)
    listen_go.add_argument("--wait-for-client-seconds", type=float, default=30.0)
    listen_go.add_argument("--poll-ms", type=int, default=200)
    listen_go.add_argument("--click-interval-ms", type=int, default=2_000)
    listen_go.add_argument(
        "--manager-manifest",
        type=Path,
        help="manager manifest used to resolve the foreground client to its exact worker",
    )
    listen_go.add_argument(
        "--worker-state-directory",
        type=Path,
        help="node-local manager worker state containing permits and operation inboxes",
    )
    listen_go.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    listen_go.add_argument("--json", action="store_true", help="emit JSON Lines events")

    manager = commands.add_parser(
        "manager",
        help="inspect local client instances without focusing them or sending input",
    )
    manager_commands = manager.add_subparsers(dest="manager_command", required=True)
    manager_inspect = manager_commands.add_parser(
        "inspect",
        help="emit a node-tagged inventory of matching visible clients",
    )
    manager_inspect.add_argument(
        "--node-id",
        required=True,
        help="stable identifier for this PC in manager evidence and client identities",
    )
    manager_inspect.add_argument(
        "--process-directory",
        type=Path,
        help="optional exact directory containing the expected game executable",
    )
    manager_inspect.add_argument(
        "--executable-name",
        dest="executable_names",
        action="append",
        metavar="NAME",
        help="allowed executable file name; repeatable and defaults to sb.exe",
    )
    manager_inspect.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    manager_preflight = manager_commands.add_parser(
        "preflight",
        help="validate a local lifecycle manifest and inventory its matching clients",
    )
    manager_preflight.add_argument(
        "manifest",
        type=Path,
        help="strict schema-v1 manager manifest JSON",
    )
    manager_preflight.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    manager_slots = manager_commands.add_parser(
        "configure-slots",
        help="expand and deterministically tile local manifest client slots",
    )
    manager_slots.add_argument("manifest", type=Path)
    manager_slots.add_argument("--count", type=int, required=True)
    manager_slots.add_argument("--display-width", type=int, default=1920)
    manager_slots.add_argument("--display-height", type=int, default=955)
    manager_slots.add_argument(
        "--apply",
        action="store_true",
        help="required because this atomically replaces the manifest after making a backup",
    )
    manager_slots.add_argument("--json", action="store_true")
    manager_build = manager_commands.add_parser(
        "configure-build",
        help="atomically retarget all slots to one reviewed client directory",
    )
    manager_build.add_argument("manifest", type=Path)
    manager_build.add_argument("game_directory")
    manager_build.add_argument("--executable-name", default="sb.exe")
    manager_build.add_argument(
        "--apply",
        action="store_true",
        help="required because this atomically replaces the manifest after making a backup",
    )
    manager_build.add_argument("--json", action="store_true")
    manager_app = manager_commands.add_parser(
        "app",
        help="run the authenticated localhost lifecycle dashboard",
    )
    manager_app.add_argument(
        "manifest",
        type=Path,
        help="strict schema-v1 manager manifest JSON",
    )
    manager_app.add_argument(
        "--port",
        type=int,
        default=0,
        help="loopback TCP port; defaults to an ephemeral available port",
    )
    manager_app.add_argument("--launch-timeout-seconds", type=float, default=30.0)
    manager_app.add_argument("--poll-ms", type=int, default=500)
    manager_app.add_argument(
        "--worker-state-directory",
        type=Path,
        help=("local worker heartbeat root; defaults beneath LOCALAPPDATA\\ShadowbaneLab\\workers"),
    )
    manager_app.add_argument(
        "--pid-file",
        type=Path,
        help="runtime-owned PID file written by the actual manager interpreter",
    )
    manager_app.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authenticated dashboard URL without opening a browser",
    )
    manager_app.add_argument(
        "--live",
        action="store_true",
        help="required because dashboard actions may launch, tile, or close clients",
    )
    manager_worker = manager_commands.add_parser(
        "worker",
        help="run one exact game-instance worker safety/runtime host",
    )
    manager_worker.add_argument(
        "manifest",
        type=Path,
        help="strict schema-v1 manager manifest JSON",
    )
    manager_worker.add_argument("--worker-state-directory", type=Path, required=True)
    manager_worker.add_argument("--client-id", required=True)
    manager_worker.add_argument("--instance-id", required=True)
    manager_worker.add_argument("--game-process-id", type=int, required=True)
    manager_worker.add_argument(
        "--game-process-started-at-100ns",
        type=int,
        required=True,
    )
    manager_worker.add_argument("--game-window-handle", type=int, required=True)
    manager_worker.add_argument("--heartbeat-ms", type=int, default=1_000)
    manager_worker.add_argument(
        "--destination-state",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag\bounded-route-state.json"),
    )
    manager_worker.add_argument(
        "--client-profile",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag\wonderbane-travel.local.json"),
    )
    manager_worker.add_argument("--native-position-profile", type=Path)
    manager_worker.add_argument("--native-vitals-profile", type=Path)
    manager_worker.add_argument(
        "--pve-client-profile",
        type=Path,
        default=Path(r"\\VBOXSVR\codexrepo\configs\wonderbane-pve.local.json"),
    )
    manager_worker.add_argument("--pve-hotbar-config", type=Path)
    manager_worker.add_argument(
        "--pve-evidence-directory",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag"),
    )
    manager_worker.add_argument(
        "--navigation-cache-directory",
        type=Path,
        default=(Path.home() / "Downloads" / "WonderbaneClient" / "Wonderbane" / "cache"),
    )
    manager_worker.add_argument(
        "--learned-navigation-state",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag\learned-navigation-state.json"),
    )
    manager_worker.add_argument("--pve-max-kills", type=int, default=3)
    manager_worker.add_argument("--pve-max-seconds", type=float, default=300.0)
    manager_worker.add_argument("--pve-max-encounter-seconds", type=float, default=120.0)
    manager_worker.add_argument("--pve-recovery-timeout-seconds", type=float, default=30.0)
    manager_worker.add_argument("--pve-poll-ms", type=int, default=100)
    manager_worker.add_argument("--pve-camp-radius", type=float, default=120.0)
    manager_worker.add_argument("--pve-retained-trace-steps", type=int, default=2_000)
    manager_worker.add_argument("--travel-max-seconds", type=float, default=300.0)
    manager_worker.add_argument("--travel-poll-ms", type=int, default=200)
    manager_worker.add_argument("--travel-click-interval-ms", type=int, default=2_000)
    manager_worker.add_argument(
        "--live",
        action="store_true",
        help="required because this worker is the live-input ownership boundary",
    )

    progression = commands.add_parser(
        "progression",
        help="import and inspect sourced character-progression data",
    )
    progression_commands = progression.add_subparsers(
        dest="progression_command",
        required=True,
    )
    import_calculator = progression_commands.add_parser(
        "import-wonderbane-calculator",
        help="snapshot and safely parse the public WonderBane calculator declarations",
    )
    calculator_source = import_calculator.add_mutually_exclusive_group(required=True)
    calculator_source.add_argument(
        "--snapshot",
        type=Path,
        help="existing WonderBane home-page HTML snapshot",
    )
    calculator_source.add_argument(
        "--download",
        action="store_true",
        help="download the bounded HTTPS home page without rendering or executing it",
    )
    import_calculator.add_argument(
        "--output",
        type=Path,
        required=True,
        help="directory for the timestamped HTML, manifest, and normalized catalog",
    )
    import_calculator.add_argument(
        "--retrieved-at",
        help="optional ISO-8601 retrieval timestamp; defaults to current UTC",
    )
    import_calculator.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable result metadata",
    )
    return parser


_PVE_TARGET_ACTIONS = (
    (
        "client.pve.target_next_mobile",
        "Target Next Mob",
        ArcaneClientAction.TARGET_NEXT_MOB,
    ),
    (
        "client.pve.target_previous_mobile",
        "Target Previous Mob",
        ArcaneClientAction.TARGET_PREVIOUS_MOB,
    ),
    (
        "client.pve.clear_selection",
        "Clear Target",
        ArcaneClientAction.CLEAR_TARGET,
    ),
)


def _validate_character_layout(path: Path, *, as_json: bool) -> int:
    try:
        layout = load_character_layout(path)
    except (CharacterLayoutError, OSError) as exc:
        return _error(f"character layout validation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "layout_id": layout.layout_id,
        "schema_version": layout.schema_version,
        "live_capture_enabled": layout.target.live_capture_enabled,
        "expected_sha256": layout.target.expected_sha256,
        "pointer_size": layout.target.pointer_size,
        "executable_names": list(layout.target.executable_names),
        "root_count": len(layout.roots),
        "value_count": len(layout.values),
        "record_count": len(layout.records),
        "collection_count": len(layout.collections),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Layout: {layout.layout_id}")
        print(f"Pointer size: {layout.target.pointer_size}")
        print(f"Live capture enabled: {layout.target.live_capture_enabled}")
        print(
            "Declarations: "
            f"{len(layout.roots)} roots, {len(layout.values)} values, "
            f"{len(layout.records)} records, {len(layout.collections)} collections"
        )
    return 0


def _process_names(values: list[str] | None) -> tuple[str, ...]:
    return tuple(values) if values else ("Shadowbane.exe",)


def _inspect_character_process(
    *, process_names: list[str] | None, process_id: int | None, as_json: bool
) -> int:
    try:
        with WindowsProcessMemory.open(
            executable_names=_process_names(process_names), process_id=process_id
        ) as memory:
            payload = {
                "ok": True,
                "process": memory.process_info.as_dict(),
                "modules": [item.as_dict() for item in memory.modules()],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"character process inspection failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        process = payload["process"]
        assert isinstance(process, dict)
        print(f"PID: {process['process_id']}")
        print(f"Executable: {process['executable_path']}")
        print(f"SHA-256: {process['executable_sha256']}")
        print(f"Pointer size: {process['pointer_size']}")
        print(f"Loaded modules: {len(payload['modules'])}")
    return 0


def _scan_character_text(
    *,
    text: str,
    encodings: list[str] | None,
    process_names: list[str] | None,
    process_id: int | None,
    max_matches: int,
    max_scan_mib: int,
    context_bytes: int,
    as_json: bool,
) -> int:
    try:
        with WindowsProcessMemory.open(
            executable_names=_process_names(process_names), process_id=process_id
        ) as memory:
            matches = memory.scan_text(
                text,
                encodings=(tuple(encodings) if encodings else ("cp1252", "utf-8", "utf-16le")),
                max_matches=max_matches,
                max_scan_bytes=max_scan_mib * 1024 * 1024,
                context_bytes=context_bytes,
            )
            payload = {
                "ok": True,
                "process": memory.process_info.as_dict(),
                "query": text,
                "matches": [item.as_dict() for item in matches],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"character text scan failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Matches: {len(matches)}")
        for match in matches:
            print(f"0x{match.address:x} [{match.encoding}] {match.preview_text}")
    return 0


def _scan_character_pointer(
    *,
    address: int,
    process_names: list[str] | None,
    process_id: int | None,
    max_matches: int,
    max_scan_mib: int,
    context_bytes: int,
    as_json: bool,
) -> int:
    try:
        with WindowsProcessMemory.open(
            executable_names=_process_names(process_names), process_id=process_id
        ) as memory:
            matches = memory.scan_pointer(
                address,
                max_matches=max_matches,
                max_scan_bytes=max_scan_mib * 1024 * 1024,
                context_bytes=context_bytes,
            )
            payload = {
                "ok": True,
                "process": memory.process_info.as_dict(),
                "query_address": f"0x{address:x}",
                "matches": [item.as_dict() for item in matches],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"character pointer scan failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Pointer references to 0x{address:x}: {len(matches)}")
        for match in matches:
            print(f"0x{match.address:x} {match.preview_text}")
    return 0


def _capture_character_snapshot(
    *, layout_path: Path, output_path: Path | None, process_id: int | None, as_json: bool
) -> int:
    try:
        layout = load_character_layout(layout_path)
        with WindowsProcessMemory.open(
            executable_names=layout.target.executable_names,
            process_id=process_id,
            expected_sha256=layout.target.expected_sha256,
            required_pointer_size=layout.target.pointer_size,
        ) as memory:
            capture = capture_character(layout, memory)
        payload = capture.as_dict()
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(encoded, encoding="utf-8")
    except (
        CharacterCaptureError,
        CharacterLayoutError,
        MemoryAccessError,
        ProcessSelectionError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"character snapshot failed: {exc}", as_json=as_json)

    if as_json or output_path is None:
        print(encoded, end="")
    else:
        print(f"Character snapshot: {output_path}")
        character = payload.get("character")
        identity = character.get("identity") if isinstance(character, dict) else None
        if isinstance(identity, dict) and identity.get("name"):
            print(f"Character: {identity['name']}")
        print(f"Warnings: {len(payload['warnings'])}")
    return 0


def _snapshot_payload(snapshot: WindowSnapshot) -> dict[str, object]:
    bounds = snapshot.client_bounds
    return {
        "ok": True,
        "executable_name": snapshot.executable_name,
        "title": snapshot.title,
        "client_bounds": {
            "left": bounds.left,
            "top": bounds.top,
            "width": bounds.width,
            "height": bounds.height,
        },
        "dpi_scale": snapshot.dpi_scale,
        "is_foreground": snapshot.is_foreground,
        "is_visible": snapshot.is_visible,
        "executable_path": snapshot.executable_path,
    }


def _inspect_client(*, as_json: bool) -> int:
    try:
        snapshot = WindowsForegroundWindowInspector().inspect()
    except (OSError, RuntimeError) as exc:
        return _error(f"client inspection failed: {exc}", as_json=as_json)
    if snapshot is None:
        return _error(
            "no foreground window could be inspected; focus WonderBane and try again",
            as_json=as_json,
        )
    _print_snapshot(snapshot, as_json=as_json)
    return 0


def _inspect_manager(
    *,
    node_id: str,
    executable_names: Sequence[str],
    process_directory: Path | None,
    as_json: bool,
) -> int:
    if process_directory is not None and not process_directory.is_dir():
        return _error(
            f"process directory does not exist: {process_directory}",
            as_json=as_json,
        )
    resolved_names = tuple(executable_names) or ("sb.exe",)
    try:
        snapshot = ClientWindowRegistry(
            WindowsVisibleWindowInspector(),
            node_id=node_id,
            executable_names=resolved_names,
            process_directory=process_directory,
        ).inspect()
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager inspection failed: {exc}", as_json=as_json)

    payload = {"ok": True, **snapshot.as_dict()}
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return 0

    print(f"Node: {snapshot.node_id}")
    print(f"Attachable clients: {len(snapshot.clients)}")
    for client in snapshot.clients:
        print(
            f"- {client.instance_id}: pid={client.process_id} "
            f"hwnd={client.window_handle} {client.executable_name} {client.title!r}"
        )
    print(f"Rejected windows: {len(snapshot.rejected)}")
    for window in snapshot.rejected:
        reasons = ", ".join(reason.value for reason in window.reasons)
        print(f"- {window.executable_name} {window.title!r}: {reasons}")
    return 0


def _manager_path_status(path: Path, *, kind: str) -> dict[str, object]:
    exists = path.exists()
    correct_kind = path.is_file() if kind == "file" else path.is_dir()
    return {
        "path": str(path),
        "expected_kind": kind,
        "exists": exists,
        "correct_kind": correct_kind,
        "ready": exists and correct_kind,
    }


def _preflight_manager(manifest_path: Path, *, as_json: bool) -> int:
    try:
        manifest = load_manager_manifest(manifest_path)
        inspector = WindowsVisibleWindowInspector()
        group_sizes: dict[tuple[tuple[str, ...], str], int] = {}
        snapshots: dict[tuple[tuple[str, ...], str], ClientRegistrySnapshot] = {}
        keys: list[tuple[tuple[str, ...], str]] = []
        for config in manifest.clients:
            key = (
                tuple(sorted(name.casefold() for name in config.expected_executable_names)),
                ntpath.normcase(
                    ntpath.normpath(ntpath.abspath(str(config.expected_process_directory)))
                ).casefold(),
            )
            keys.append(key)
            group_sizes[key] = group_sizes.get(key, 0) + 1
            if key not in snapshots:
                snapshots[key] = ClientWindowRegistry(
                    inspector,
                    node_id=manifest.node_id,
                    executable_names=config.expected_executable_names,
                    process_directory=config.expected_process_directory,
                ).inspect()

        clients: list[dict[str, object]] = []
        ready = True
        for config, key in zip(manifest.clients, keys, strict=True):
            snapshot = snapshots[key]
            launch_executable = _manager_path_status(
                Path(config.launch.executable),
                kind="file",
            )
            working_directory = _manager_path_status(
                Path(config.launch.working_directory),
                kind="directory",
            )
            process_directory = _manager_path_status(
                Path(config.expected_process_directory),
                kind="directory",
            )
            environment_ready = all(
                item["ready"] for item in (launch_executable, working_directory, process_directory)
            )
            if snapshot.rejected:
                binding_status = "unsafe_identity"
            elif not snapshot.clients:
                binding_status = "ready_to_launch"
            elif len(snapshot.clients) == 1 and group_sizes[key] == 1:
                binding_status = "attachable"
            else:
                binding_status = "selection_required"
            client_ready = environment_ready and binding_status != "unsafe_identity"
            ready = ready and client_ready
            clients.append(
                {
                    "client_id": config.client_id,
                    "environment_ready": environment_ready,
                    "binding_status": binding_status,
                    "filesystem": {
                        "launch_executable": launch_executable,
                        "working_directory": working_directory,
                        "expected_process_directory": process_directory,
                    },
                    "expected_executable_names": list(config.expected_executable_names),
                    "window_tile": (
                        None if config.window_tile is None else config.window_tile.to_dict()
                    ),
                    "matching_instances": [client.to_dict() for client in snapshot.clients],
                    "rejected_windows": [window.to_dict() for window in snapshot.rejected],
                }
            )
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager preflight failed: {exc}", as_json=as_json)

    payload = {
        "ok": True,
        "ready": ready,
        "schema_version": manifest.schema_version,
        "node_id": manifest.node_id,
        "clients": clients,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return 0

    print(f"Node: {manifest.node_id}")
    print(f"Lifecycle preflight ready: {'yes' if ready else 'no'}")
    for client in clients:
        print(
            f"- {client['client_id']}: {client['binding_status']} "
            f"environment_ready={str(client['environment_ready']).lower()}"
        )
    return 0


def _configure_manager_slots(
    manifest_path: Path,
    *,
    count: int,
    display_width: int,
    display_height: int,
    apply: bool,
    as_json: bool,
) -> int:
    if not apply:
        return _error(
            "slot configuration replaces the manager manifest; pass --apply to confirm",
            as_json=as_json,
        )
    try:
        current = load_manager_manifest(manifest_path)
        configured = expand_manager_slots(
            current,
            count,
            display_width=display_width,
            display_height=display_height,
        )
        backup_path = replace_manager_manifest(
            manifest_path,
            expected=current,
            replacement=configured,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager slot configuration failed: {exc}", as_json=as_json)

    result = {
        "ok": True,
        "manifest": str(manifest_path),
        "backup": str(backup_path),
        "slot_count": len(configured.clients),
        "client_ids": [client.client_id for client in configured.clients],
        "restart_required": True,
    }
    if as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"Configured {result['slot_count']} manager client slots.")
        print(f"Manifest: {manifest_path}")
        print(f"Backup: {backup_path}")
        print("Restart the WonderBane Control Center to load the new slot list.")
    return 0


def _configure_manager_build(
    manifest_path: Path,
    *,
    game_directory: str,
    executable_name: str,
    apply: bool,
    as_json: bool,
) -> int:
    if not apply:
        return _error(
            "build configuration replaces the manager manifest; pass --apply to confirm",
            as_json=as_json,
        )
    try:
        current = load_manager_manifest(manifest_path)
        configured = retarget_manager_clients(
            current,
            game_directory,
            executable_name=executable_name,
        )
        executable = Path(str(configured.clients[0].launch.executable))
        if not executable.is_file():
            raise ValueError(f"reviewed client executable was not found: {executable}")
        backup_path = replace_manager_manifest(
            manifest_path,
            expected=current,
            replacement=configured,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager build configuration failed: {exc}", as_json=as_json)

    result = {
        "ok": True,
        "manifest": str(manifest_path),
        "backup": str(backup_path),
        "slot_count": len(configured.clients),
        "game_directory": str(configured.clients[0].expected_process_directory),
        "executable": str(configured.clients[0].launch.executable),
        "restart_required": True,
    }
    if as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"Configured {result['slot_count']} manager slots for {result['executable']}.")
        print(f"Manifest: {manifest_path}")
        print(f"Backup: {backup_path}")
        print("Restart the WonderBane Control Center to load the reviewed client build.")
    return 0


def _write_manager_pid_file(path: Path) -> None:
    pid_path = path.resolve(strict=False)
    if pid_path.exists() and (pid_path.is_symlink() or not pid_path.is_file()):
        raise RuntimeError(f"manager PID path is not a regular file: {pid_path}")
    parent = pid_path.parent
    if not parent.exists() or parent.is_symlink() or not parent.is_dir():
        raise RuntimeError(f"manager PID directory is not a regular directory: {parent}")
    temporary = pid_path.with_name(f".{pid_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("xb") as destination:
            destination.write(f"{os.getpid()}\n".encode("ascii"))
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(pid_path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_manager_pid_file(path: Path) -> None:
    pid_path = path.resolve(strict=False)
    try:
        value = pid_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return
    if value == str(os.getpid()):
        pid_path.unlink(missing_ok=True)


def _run_manager_app(
    manifest_path: Path,
    *,
    port: int,
    launch_timeout_seconds: float,
    poll_ms: int,
    worker_state_directory: Path | None,
    pid_file: Path | None,
    open_browser: bool,
    live: bool,
) -> int:
    if not live:
        return _error(
            "manager app is live lifecycle control; pass --live to enable it",
            as_json=False,
        )
    if (
        isinstance(launch_timeout_seconds, bool)
        or not isinstance(launch_timeout_seconds, (int, float))
        or not 1.0 <= launch_timeout_seconds <= 600.0
    ):
        return _error(
            "launch-timeout-seconds must be in [1, 600]",
            as_json=False,
        )
    if isinstance(poll_ms, bool) or not isinstance(poll_ms, int) or not 25 <= poll_ms <= 10_000:
        return _error("poll-ms must be in [25, 10000]", as_json=False)

    try:
        manifest = load_manager_manifest(manifest_path)
        missing_environment: list[str] = []
        for config in manifest.clients:
            checks = (
                (
                    "launch executable",
                    _manager_path_status(Path(config.launch.executable), kind="file"),
                ),
                (
                    "working directory",
                    _manager_path_status(
                        Path(config.launch.working_directory),
                        kind="directory",
                    ),
                ),
                (
                    "expected process directory",
                    _manager_path_status(
                        Path(config.expected_process_directory),
                        kind="directory",
                    ),
                ),
            )
            missing_environment.extend(
                f"{config.client_id} {label}: {check['path']}"
                for label, check in checks
                if not check["ready"]
            )
        if missing_environment:
            return _error(
                "manager app environment is not ready: " + "; ".join(missing_environment),
                as_json=False,
            )

        if worker_state_directory is None:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise RuntimeError("LOCALAPPDATA is required for default worker state")
            manager_state_root = Path(local_app_data) / "ShadowbaneLab"
            heartbeat_root = manager_state_root / "workers"
        else:
            heartbeat_root = worker_state_directory
            manager_state_root = heartbeat_root.parent
        local_app_data = os.environ.get("LOCALAPPDATA")
        extension_status = (
            None
            if not local_app_data
            else ExtensionHeartbeatStatusProvider(
                Path(local_app_data) / "ShadowbaneLab" / "client-extension"
            )
        )

        def build_application(
            application_manifest: ManagerManifest,
        ) -> ManagerDashboardApplication:
            if not isinstance(application_manifest, ManagerManifest):
                raise ValueError("application manifest has the wrong type")
            inspector = WindowsVisibleWindowInspector()
            process_inspector = Win32ProcessLifetimeInspector()
            worker_ledger = WorkerHeartbeatLedger(application_manifest, heartbeat_root)
            worker_supervisor = WorkerSupervisor(worker_ledger, process_inspector)
            worker_controller = ManagedWorkerController(
                application_manifest,
                worker_ledger,
                process_inspector,
                SubprocessWorkerLauncher(
                    manifest_path=manifest_path,
                    worker_state_directory=heartbeat_root,
                    log_directory=manager_state_root / "logs",
                ),
            )
            aggregate_registry = ManifestClientRegistryProvider(
                inspector,
                application_manifest,
            )
            window_control = GuardedWindowControl(aggregate_registry, Win32WindowApi())
            supervisor = ClientLifecycleSupervisor(
                VisibleWindowRegistrySource(inspector),
                launcher=SubprocessLauncher(process_inspector),
                window_controller=window_control,
                process_inspector=process_inspector,
            )
            session = ManagerSession(application_manifest, supervisor)
            application = ManagerDashboardApplication(
                application_manifest,
                session,
                aggregate_registry,
                worker_supervisor,
                worker_controller=worker_controller,
                operation_status=WorkerOperationLedger(
                    application_manifest,
                    heartbeat_root,
                ),
                extension_status=extension_status,
                launch_timeout_seconds=launch_timeout_seconds,
                poll_seconds=poll_ms / 1_000.0,
            )
            recovery = recover_manager_bindings(
                application_manifest,
                aggregate_registry,
                worker_ledger,
                session,
                worker_controller,
            )
            if recovery.recovered_client_ids:
                print(
                    "Recovered exact manager binding(s): "
                    + ", ".join(recovery.recovered_client_ids)
                )
            for issue in recovery.issues:
                print(
                    f"Could not recover {issue.client_id}: {issue.detail}",
                    file=sys.stderr,
                )
            return application

        application = LiveConfiguredManagerApplication(
            manifest_path,
            manifest,
            build_application,
        )
        application.status()
        server = DashboardServer(application, port=port)
        with server:
            try:
                if pid_file is not None:
                    _write_manager_pid_file(pid_file)
                print(f"Manager dashboard: {server.suggested_url}")
                print(f"Worker heartbeat root: {heartbeat_root}")
                print("Press Ctrl+C to stop the dashboard; managed clients will remain open.")
                if open_browser:
                    try:
                        if not webbrowser.open(server.suggested_url, new=1):
                            print("Could not open a browser; use the printed dashboard URL.")
                    except (OSError, webbrowser.Error):
                        print("Could not open a browser; use the printed dashboard URL.")
                try:
                    while server.is_running:
                        application.status()
                        time.sleep(0.75)
                except KeyboardInterrupt:
                    print("Stopping manager dashboard...")
                    return 0
            finally:
                try:
                    application.revoke_all_workers(
                        reason="manager dashboard shutdown revoked worker dispatch"
                    )
                except (OSError, RuntimeError, ValueError) as exc:
                    print(f"Could not persist worker shutdown revocation: {exc}", file=sys.stderr)
                if pid_file is not None:
                    try:
                        _remove_manager_pid_file(pid_file)
                    except OSError as exc:
                        print(f"Could not remove manager PID file: {exc}", file=sys.stderr)
            raise RuntimeError("manager dashboard stopped unexpectedly")
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager app failed: {exc}", as_json=False)


def _run_manager_worker(
    manifest_path: Path,
    *,
    worker_state_directory: Path,
    client_id: str,
    instance_id: str,
    game_process_id: int,
    game_process_started_at_100ns: int,
    game_window_handle: int,
    heartbeat_ms: int,
    destination_state_path: Path,
    client_profile_path: Path,
    native_position_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    pve_client_profile_path: Path,
    pve_hotbar_config_path: Path | None,
    pve_evidence_directory: Path,
    navigation_cache_directory: Path,
    learned_navigation_state_path: Path,
    pve_max_kills: int,
    pve_max_seconds: float,
    pve_max_encounter_seconds: float,
    pve_recovery_timeout_seconds: float,
    pve_poll_ms: int,
    pve_camp_radius: float,
    pve_retained_trace_steps: int,
    travel_max_seconds: float,
    travel_poll_ms: int,
    travel_click_interval_ms: int,
    live: bool,
) -> int:
    if not live:
        return _error(
            "manager worker is a live-input ownership boundary; pass --live to enable it",
            as_json=False,
        )
    if (
        isinstance(heartbeat_ms, bool)
        or not isinstance(heartbeat_ms, int)
        or not 100 <= heartbeat_ms <= 4_000
    ):
        return _error("heartbeat-ms must be in [100, 4000]", as_json=False)
    try:
        manifest = load_manager_manifest(manifest_path)
        binding = ExactClientWorkerBinding(
            client_id=client_id,
            instance_id=instance_id,
            game_process_id=game_process_id,
            game_process_started_at_100ns=game_process_started_at_100ns,
            game_window_handle=game_window_handle,
        )
        binding.validate_for(manifest)
        inspector = WindowsVisibleWindowInspector()
        process_inspector = Win32ProcessLifetimeInspector()
        runtime = ExactClientWorkerRuntime(
            manifest,
            binding,
            WorkerHeartbeatLedger(manifest, worker_state_directory),
            ManifestClientRegistryProvider(inspector, manifest),
            process_inspector,
            operation_ledger=WorkerOperationLedger(
                manifest,
                worker_state_directory,
            ),
            operation_executor=_ExactWorkerEngineExecutor(
                binding,
                destination_state_path=destination_state_path,
                client_profile_path=client_profile_path,
                native_position_profile_path=native_position_profile_path,
                native_vitals_profile_path=native_vitals_profile_path,
                pve_client_profile_path=pve_client_profile_path,
                pve_hotbar_config_path=pve_hotbar_config_path,
                pve_evidence_directory=pve_evidence_directory,
                navigation_cache_directory=navigation_cache_directory,
                learned_navigation_state_path=learned_navigation_state_path,
                pve_max_kills=pve_max_kills,
                pve_max_seconds=pve_max_seconds,
                pve_max_encounter_seconds=pve_max_encounter_seconds,
                pve_recovery_timeout_seconds=pve_recovery_timeout_seconds,
                pve_poll_ms=pve_poll_ms,
                pve_camp_radius=pve_camp_radius,
                pve_retained_trace_steps=pve_retained_trace_steps,
                travel_max_seconds=travel_max_seconds,
                travel_poll_ms=travel_poll_ms,
                travel_click_interval_ms=travel_click_interval_ms,
            ),
            heartbeat_interval_seconds=heartbeat_ms / 1_000.0,
        )
        return runtime.serve()
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager worker failed: {exc}", as_json=False)


class _ExactWorkerEngineExecutor:
    """Compose existing travel/PvE engines behind one exact worker dispatch gate."""

    def __init__(
        self,
        binding: ExactClientWorkerBinding,
        *,
        destination_state_path: Path,
        client_profile_path: Path,
        native_position_profile_path: Path | None,
        native_vitals_profile_path: Path | None,
        pve_client_profile_path: Path,
        pve_hotbar_config_path: Path | None,
        pve_evidence_directory: Path,
        navigation_cache_directory: Path,
        learned_navigation_state_path: Path,
        pve_max_kills: int,
        pve_max_seconds: float,
        pve_max_encounter_seconds: float,
        pve_recovery_timeout_seconds: float,
        pve_poll_ms: int,
        pve_camp_radius: float,
        pve_retained_trace_steps: int,
        travel_max_seconds: float,
        travel_poll_ms: int,
        travel_click_interval_ms: int,
    ) -> None:
        self._binding = binding
        self._destination_state_path = destination_state_path
        self._client_profile_path = client_profile_path
        self._native_position_profile_path = native_position_profile_path
        self._native_vitals_profile_path = native_vitals_profile_path
        self._pve_client_profile_path = pve_client_profile_path
        self._pve_hotbar_config_path = pve_hotbar_config_path
        self._pve_evidence_directory = pve_evidence_directory
        self._navigation_cache_directory = navigation_cache_directory
        self._learned_navigation_state_path = learned_navigation_state_path
        self._pve_max_kills = pve_max_kills
        self._pve_max_seconds = pve_max_seconds
        self._pve_max_encounter_seconds = pve_max_encounter_seconds
        self._pve_recovery_timeout_seconds = pve_recovery_timeout_seconds
        self._pve_poll_ms = pve_poll_ms
        self._pve_camp_radius = pve_camp_radius
        self._pve_retained_trace_steps = pve_retained_trace_steps
        self._travel_max_seconds = travel_max_seconds
        self._travel_poll_ms = travel_poll_ms
        self._travel_click_interval_ms = travel_click_interval_ms
        self._navigation_map = load_learned_navigation_map(learned_navigation_state_path)

    def execute(
        self,
        operation: WorkerOperation,
        *,
        stop_signal: StopSignal,
    ) -> WorkerOperationExecution:
        if operation.instance_id != self._binding.instance_id:
            return WorkerOperationExecution(
                WorkerOperationState.FAILED,
                "operation does not own this exact game instance",
            )
        if stop_signal.is_set():
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED,
                "worker dispatch gate closed before execution",
            )
        try:
            if operation.kind is WorkerOperationKind.STOP:
                result = self._execute_stop(stop_signal=stop_signal)
            elif operation.kind is WorkerOperationKind.TRAVEL:
                result = self._execute_travel(operation, stop_signal=stop_signal)
            elif operation.kind is WorkerOperationKind.PVE:
                result = self._execute_pve(stop_signal=stop_signal)
            else:
                raise ValueError(f"unsupported operation kind {operation.kind!r}")
        finally:
            save_learned_navigation_map(
                self._learned_navigation_state_path,
                self._navigation_map,
            )
        return result

    def _execute_stop(self, *, stop_signal: StopSignal) -> WorkerOperationExecution:
        profile = load_calibration(self._client_profile_path)
        guard = ForegroundWindowGuard(
            profile,
            WindowsForegroundWindowInspector(),
            expected_process_id=self._binding.game_process_id,
        )
        adapter = ClientInputAdapter(
            DecisionInputCompiler(profile, StaticBindingPointResolver()),
            GuardedInputExecutor(
                guard=guard,
                backend=PyAutoGuiBackend(),
                stop_signal=stop_signal,
            ),
        )
        result = adapter.dispatch_movement_stop(
            correlation_id=f"worker:{self._binding.client_id}:stop"
        )
        return WorkerOperationExecution(
            (WorkerOperationState.SUCCEEDED if result.accepted else WorkerOperationState.FAILED),
            result.reason,
        )

    def _execute_travel(
        self,
        operation: WorkerOperation,
        *,
        stop_signal: StopSignal,
    ) -> WorkerOperationExecution:
        destination = operation.destination
        if destination is None:
            raise ValueError("travel operation lacks a resolved destination")
        result = _run_travel(
            lt=destination.lt,
            lg=destination.lg,
            radius=destination.radius,
            destination_state_path=self._destination_state_path,
            client_profile_path=self._client_profile_path,
            native_position_profile_path=self._native_position_profile_path,
            native_vitals_profile_path=self._native_vitals_profile_path,
            max_seconds=self._travel_max_seconds,
            wait_for_client_seconds=0,
            poll_ms=self._travel_poll_ms,
            click_interval_ms=self._travel_click_interval_ms,
            live=True,
            as_json=True,
            stop_signal=stop_signal,
            client_process_id=self._binding.game_process_id,
            navigation_cache_directory=self._navigation_cache_directory,
            navigation_map=self._navigation_map,
        )
        if stop_signal.is_set():
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED,
                "travel stopped by priority or dispatch revocation",
            )
        return WorkerOperationExecution(
            WorkerOperationState.SUCCEEDED if result == 0 else WorkerOperationState.FAILED,
            "travel completed" if result == 0 else f"travel exited with status {result}",
        )

    def _execute_pve(self, *, stop_signal: StopSignal) -> WorkerOperationExecution:
        hotbar_path = self._pve_hotbar_config_path
        if hotbar_path is None:
            candidates = tuple(
                sorted(
                    (Path.home() / "Downloads" / "WonderbaneClient" / "Wonderbane" / "Config").glob(
                        "SCREEN_GAME_*_Wonderbane.cfg"
                    )
                )
            )
            if len(candidates) == 1:
                hotbar_path = candidates[0]
        self._pve_evidence_directory.mkdir(parents=True, exist_ok=True)
        evidence_output = _new_chat_pve_evidence_path(self._pve_evidence_directory)
        result = _run_pve(
            client_profile_path=self._pve_client_profile_path,
            combat_log_path=None,
            hotbar_config_path=hotbar_path,
            native_health_profile_path=None,
            native_vitals_profile_path=self._native_vitals_profile_path,
            native_position_profile_path=self._native_position_profile_path,
            native_target_position_profile_path=None,
            native_target_action_profile_path=None,
            navigation_cache_directory=self._navigation_cache_directory,
            max_kills=self._pve_max_kills,
            max_seconds=self._pve_max_seconds,
            max_encounter_seconds=self._pve_max_encounter_seconds,
            recovery_timeout_seconds=self._pve_recovery_timeout_seconds,
            wait_for_client_seconds=0,
            poll_ms=self._pve_poll_ms,
            policy="proc-assassin",
            live=True,
            as_json=True,
            evidence_output_path=evidence_output,
            combat_source="state",
            stop_signal=stop_signal,
            client_process_id=self._binding.game_process_id,
            continuous=True,
            camp_radius=self._pve_camp_radius,
            retained_trace_steps=self._pve_retained_trace_steps,
            navigation_map=self._navigation_map,
        )
        if stop_signal.is_set():
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED,
                "PvE stopped by priority or dispatch revocation",
            )
        return WorkerOperationExecution(
            WorkerOperationState.SUCCEEDED if result == 0 else WorkerOperationState.FAILED,
            "PvE completed" if result == 0 else f"PvE exited with status {result}",
        )


def _print_snapshot(snapshot: WindowSnapshot, *, as_json: bool) -> None:
    payload = _snapshot_payload(snapshot)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Executable: {payload['executable_name']}")
        print(f"Title: {payload['title']}")
        bounds = payload["client_bounds"]
        assert isinstance(bounds, dict)
        print(
            "Client bounds: "
            f"left={bounds['left']} top={bounds['top']} "
            f"width={bounds['width']} height={bounds['height']}"
        )
        print(f"DPI scale: {payload['dpi_scale']}")


def _windows_directory(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(ntpath.abspath(path)))


def _matches_process_directory(snapshot: WindowSnapshot, process_directory: Path) -> bool:
    if snapshot.executable_path is None:
        return False
    executable_directory = ntpath.dirname(snapshot.executable_path)
    return _windows_directory(executable_directory) == _windows_directory(str(process_directory))


def _candidate_description(snapshot: WindowSnapshot) -> str:
    title = snapshot.title or "<untitled>"
    return f"{snapshot.executable_name} ({title!r})"


def _discover_client(
    process_directory: Path,
    *,
    wait_seconds: float,
    poll_seconds: float,
    as_json: bool,
) -> int:
    if wait_seconds < 0:
        return _error("wait-seconds must not be negative", as_json=as_json)
    if poll_seconds <= 0:
        return _error("poll-seconds must be positive", as_json=as_json)
    if not process_directory.is_dir():
        return _error(
            f"process directory does not exist: {process_directory}",
            as_json=as_json,
        )
    try:
        inspector = WindowsVisibleWindowInspector()
    except (OSError, RuntimeError) as exc:
        return _error(f"client discovery failed: {exc}", as_json=as_json)

    deadline = time.monotonic() + wait_seconds
    matches: tuple[WindowSnapshot, ...] = ()
    while True:
        try:
            snapshots = inspector.inspect_all()
        except OSError as exc:
            return _error(f"client discovery failed: {exc}", as_json=as_json)
        matches = tuple(
            snapshot
            for snapshot in snapshots
            if _matches_process_directory(snapshot, process_directory)
        )
        if len(matches) == 1:
            _print_snapshot(matches[0], as_json=as_json)
            return 0
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_seconds, remaining))

    if not matches:
        return _error(
            f"no visible client window was found in {process_directory}",
            as_json=as_json,
        )
    candidates = ", ".join(_candidate_description(snapshot) for snapshot in matches)
    return _error(
        f"multiple visible client windows matched {process_directory}: {candidates}",
        as_json=as_json,
    )


def _validate_profile(path: Path, *, as_json: bool) -> int:
    try:
        profile = load_calibration(path)
    except (CalibrationLoadError, OSError) as exc:
        return _error(f"profile validation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "schema_version": profile.schema_version,
        "live_input_enabled": profile.live_input_enabled,
        "action_count": len(profile.actions),
        "movement_action_key": profile.movement.action_key,
        "executable_names": list(profile.target.executable_names),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Profile: {profile.profile_id}")
        print(f"Schema version: {profile.schema_version}")
        print(f"Mapped actions: {len(profile.actions)}")
        print(f"Live input enabled: {profile.live_input_enabled}")
    return 0


def _inspect_arcane_hotkeys(path: Path, *, as_json: bool) -> int:
    try:
        table = load_arcane_hotkeys(path)
    except ArcaneHotkeyLoadError as exc:
        return _error(f"hotkey inspection failed: {exc}", as_json=as_json)
    actions = []
    for semantic_action, display_name, action in _PVE_TARGET_ACTIONS:
        bindings = table.bindings_for(action)
        actions.append(
            {
                "semantic_action": semantic_action,
                "display_name": display_name,
                "native_action_code": int(action),
                "bound": bool(bindings),
                "bindings": [
                    {
                        "arcane_key": item.key,
                        "input_keys": list(item.input_keys),
                        "parameter_one": item.parameter_one,
                        "parameter_two": item.parameter_two,
                        "argument": item.argument,
                    }
                    for item in bindings
                ],
            }
        )
    payload = {
        "ok": True,
        "preferences": str(path),
        "total_bindings": len(table.bindings),
        "target_actions": actions,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"ArcanePref bindings: {len(table.bindings)}")
        for action in actions:
            chords = ["+".join(item["input_keys"]) for item in action["bindings"]]
            rendered = ", ".join(chords) if chords else "unbound"
            print(f"{action['display_name']} [{action['native_action_code']}]: {rendered}")
    return 0


def _inspect_arcane_hotbar(path: Path, *, as_json: bool) -> int:
    try:
        table = load_arcane_hotbar(path)
    except ArcaneHotbarLoadError as exc:
        return _error(f"hotbar inspection failed: {exc}", as_json=as_json)
    sets = [
        {
            "set_index": hotbar_set.set_index,
            "active": hotbar_set.set_index == table.current_set_index,
            "slots": [
                {
                    "slot_index": slot.slot_index,
                    "activation_key": slot.activation_key,
                    "occupied": slot.occupied,
                    "item_type": slot.item_type,
                    "power_name": slot.power_name,
                }
                for slot in hotbar_set.slots
            ],
        }
        for hotbar_set in table.sets
    ]
    payload = {
        "ok": True,
        "character_config": str(path),
        "current_set_index": table.current_set_index,
        "set_count": len(table.sets),
        "sets": sets,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Current hotbar set: {table.current_set_index}")
        for slot in table.current_set.slots:
            assignment = slot.power_name or (slot.item_type if slot.occupied else "empty")
            print(f"{slot.activation_key.upper()}: {assignment}")
    return 0


def _inspect_world_data(
    cache_directory: Path,
    world_def_path: Path | None,
    *,
    as_json: bool,
) -> int:
    archive_names = (
        "CZone.cache",
        "CObjects.cache",
        "Mesh.cache",
        "TerrainAlpha.cache",
        "Tile.cache",
        "Render.cache",
    )
    try:
        archives: dict[str, object] = {}
        terrain_payload: dict[str, object] | None = None
        for name in archive_names:
            path = cache_directory / name
            if not path.is_file():
                continue
            with CacheArchive(path) as archive:
                archives[name] = {
                    "resources": archive.header.resource_count,
                    "groups": len({entry.group_id for entry in archive.entries}),
                    "file_size": archive.header.file_size,
                }
                if name == "TerrainAlpha.cache":
                    maps = index_terrain_alpha_maps(archive)
                    first_tile = TerrainAlphaTile.parse(archive.read_resource(archive.entries[0]))
                    terrain_payload = {
                        "tiles": len(archive.entries),
                        "maps": len(maps),
                        "complete_maps": sum(item.is_complete for item in maps),
                        "sample_width": first_tile.width,
                        "sample_height": first_tile.height,
                        "map_shapes": sorted(
                            {f"{item.width_tiles}x{item.height_tiles}" for item in maps}
                        ),
                    }
        if not archives:
            raise ValueError(f"no supported Shadowbane caches found in {cache_directory}")

        world_payload: dict[str, object] | None = None
        if world_def_path is not None:
            world = load_world_definition(world_def_path)
            zones = world.walk_zones()
            world_payload = {
                "name": world.name,
                "number": world.number,
                "width": world.width,
                "length": world.length,
                "zones": len(zones),
                "zone_templates": len({zone.template_id for zone in zones}),
                "zone_load_files": sorted(
                    {zone.zone_load_file for zone in zones if zone.zone_load_file is not None}
                ),
            }
    except (
        CacheArchiveFormatError,
        OSError,
        TerrainAlphaFormatError,
        ValueError,
        WorldDefinitionFormatError,
    ) as exc:
        return _error(f"world-data inspection failed: {exc}", as_json=as_json)

    payload = {
        "ok": True,
        "cache_directory": str(cache_directory),
        "archives": archives,
        "terrain_alpha": terrain_payload,
        "world": world_payload,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"World caches: {len(archives)}")
        for name, summary in archives.items():
            print(f"{name}: {summary['resources']} resources, {summary['groups']} groups")
        if terrain_payload is not None:
            print(
                "TerrainAlpha: "
                f"{terrain_payload['maps']} maps / {terrain_payload['tiles']} tiles / "
                f"{terrain_payload['sample_width']}x{terrain_payload['sample_height']} samples"
            )
        if world_payload is not None:
            print(f"WorldDef: {world_payload['name']} / {world_payload['zones']} placements")
    return 0


def _observe_target(
    client_profile_path: Path,
    observation_profile_path: Path,
    *,
    wait_seconds: float,
    as_json: bool,
) -> int:
    if wait_seconds < 0:
        return _error("wait-seconds must not be negative", as_json=as_json)
    try:
        client_profile = load_calibration(client_profile_path)
        observation_profile = load_observation_calibration(observation_profile_path)
        observer = ClientTargetObserver(
            client_profile,
            observation_profile,
            WindowsForegroundWindowInspector(),
            PyAutoGuiFrameCapture(),
        )
    except (
        CalibrationLoadError,
        ObservationCalibrationLoadError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        return _error(f"target observation failed: {exc}", as_json=as_json)

    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            observation = observer.observe()
            break
        except WindowGuardError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _error(f"target observation failed: {exc}", as_json=as_json)
            time.sleep(min(0.1, remaining))
        except (ObservationDetectionError, OSError, RuntimeError, ValueError) as exc:
            return _error(f"target observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": observation_profile.profile_id,
        "target_present": observation.target_present,
        "health_fraction": observation.health_fraction,
        "leading_filled_columns": observation.leading_filled_columns,
        "total_filled_columns": observation.total_filled_columns,
        "total_columns": observation.total_columns,
        "red_pixel_count": observation.red_pixel_count,
        "stray_filled_columns": observation.stray_filled_columns,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Target present: {observation.target_present}")
        if observation.health_fraction is not None:
            print(f"Health: {observation.health_fraction:.1%}")
        print(
            f"Health fill: {observation.leading_filled_columns}/{observation.total_columns} columns"
        )
        print(f"Stray filled columns: {observation.stray_filled_columns}")
    return 0


def _read_combat_log(path: Path, *, limit: int | None, as_json: bool) -> int:
    if limit is not None and limit <= 0:
        return _error("combat log limit must be positive", as_json=as_json)
    if not path.is_file():
        return _error(f"combat log does not exist: {path}", as_json=as_json)
    try:
        entries = NativeCombatLogReader(path).read_new_entries(finalize=True)
    except (NativeCombatLogFormatError, OSError, UnicodeError, ValueError) as exc:
        return _error(f"combat log read failed: {exc}", as_json=as_json)
    selected = entries[-limit:] if limit is not None else entries
    payload = {
        "ok": True,
        "path": str(path),
        "entry_count": len(entries),
        "returned_count": len(selected),
        "entries": [
            {
                "sequence": entry.sequence,
                "timestamp": entry.timestamp,
                "message": entry.message,
            }
            for entry in selected
        ],
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for entry in selected:
            print(f"({entry.timestamp}) {entry.message}")
    return 0


def _observe_native_target(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_health_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_health_profile()
        )
        with open_windows_native_target_health_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (NativeHealthProfileLoadError, NativeTargetHealthError, OSError, ValueError) as exc:
        return _error(f"native target observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "target_present": observation.target_present,
        "target_token": observation.target_token,
        "current_health": observation.current_health,
        "maximum_health": observation.maximum_health,
        "health_fraction": observation.health_fraction,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Target present: {observation.target_present}")
        if observation.target_present:
            assert observation.current_health is not None
            assert observation.maximum_health is not None
            print(
                f"Health: {observation.current_health:g}/{observation.maximum_health:g} "
                f"({observation.health_fraction:.1%})"
            )
    return 0


def _observe_native_target_position(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_target_position_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_target_position_profile()
        )
        with open_windows_native_target_position_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativeTargetPositionError,
        NativeTargetPositionProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native target-position observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "target_present": observation.target_present,
        "target_token": observation.target_token,
        "lt": observation.lt,
        "lg": observation.lg,
        "altitude": observation.altitude,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Target present: {observation.target_present}")
        if observation.target_present:
            assert observation.lt is not None
            assert observation.lg is not None
            assert observation.altitude is not None
            print(f"LT: {observation.lt:.2f}")
            print(f"LG: {observation.lg:.2f}")
            print(f"ALT: {observation.altitude:.2f}")
    return 0


def _observe_native_target_identity(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_target_identity_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_target_identity_profile()
        )
        with open_windows_native_target_identity_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativeTargetIdentityError,
        NativeTargetIdentityProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native target-identity observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "target_present": observation.target_present,
        "target_token": observation.target_token,
        "classification_available": observation.classification_available,
        "classification_error": observation.classification_error,
        "arc_character": observation.arc_character,
        "merchant": observation.merchant,
        "shopkeeper": observation.shopkeeper,
        "banker": observation.banker,
        "trainer": observation.trainer,
        "minion": observation.minion,
        "protected_roles": list(observation.protected_roles),
        "attack_eligible": observation.attack_eligible,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Target present: {observation.target_present}")
        if observation.target_present:
            roles = ", ".join(observation.protected_roles) or "none"
            print(f"Protected roles: {roles}")
            print(f"Attack eligible: {observation.attack_eligible}")
    return 0


def _observe_native_population(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_character_population_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_character_population_profile()
        )
        with open_windows_native_character_population_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativeCharacterPopulationError,
        NativeCharacterPopulationProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(
            f"native character-population observation failed: {exc}",
            as_json=as_json,
        )
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "scan_generation": observation.scan_generation,
        "rejected_candidates": observation.rejected_candidates,
        "selected_target_token": observation.selected_target_token,
        "player_action_target_token": observation.player_action_target_token,
        "characters": [
            {
                "token": character.token,
                "current_health": character.current_health,
                "maximum_health": character.maximum_health,
                "lt": character.lt,
                "lg": character.lg,
                "altitude": character.altitude,
                "protected_roles": list(character.protected_roles),
                "attack_eligible": character.attack_eligible,
                "action_target_token": character.action_target_token,
            }
            for character in observation.characters
        ],
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Loaded characters: {len(observation.characters)}")
        print(f"Rejected candidates: {observation.rejected_candidates}")
        for character in observation.characters:
            roles = ",".join(character.protected_roles) or "attackable"
            print(
                f"{character.token} {character.current_health:g}/"
                f"{character.maximum_health:g} LT={character.lt:.2f} "
                f"LG={character.lg:.2f} {roles}"
            )
    return 0


def _observe_native_runegates(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_runegate_registry_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_runegate_registry_profile()
        )
        with open_windows_native_runegate_registry_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativeRunegateRegistryError,
        NativeRunegateRegistryProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(
            f"native runegate-registry observation failed: {exc}",
            as_json=as_json,
        )
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "registry_token": observation.registry_token,
        "runegate_count": len(observation.runegates),
        "runegates": [
            {
                "object_type": runegate.object_type,
                "object_uuid": runegate.object_uuid,
                "zone_name": runegate.zone_name,
                "lt": runegate.lt,
                "lg": runegate.lg,
                "altitude": runegate.altitude,
            }
            for runegate in observation.runegates
        ],
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Server runegates: {len(observation.runegates)}")
        for runegate in observation.runegates:
            label = runegate.zone_name or f"object {runegate.object_uuid}"
            print(
                f"{label}: LT {runegate.lt:.2f}, LG {runegate.lg:.2f}, ALT {runegate.altitude:.2f}"
            )
    return 0


def _observe_native_world_map(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_world_map_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_world_map_profile()
        )
        with open_windows_native_world_map_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (NativeWorldMapError, OSError, ValueError) as exc:
        return _error(f"native world-map observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "is_open": observation.is_open,
        "rectangle": {
            "left": observation.left,
            "top": observation.top,
            "right": observation.right,
            "bottom": observation.bottom,
        },
        "padding": {
            "left": observation.left_padding,
            "top": observation.top_padding,
            "right": observation.right_padding,
            "bottom": observation.bottom_padding,
        },
        "zoom": observation.zoom,
        "pan": {
            "horizontal": observation.horizontal_pan,
            "vertical": observation.vertical_pan,
        },
        "world": {
            "length": observation.world_length,
            "width": observation.world_width,
        },
        "snapshot_token": observation.snapshot_token,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        state = "open" if observation.is_open else "closed"
        print(
            f"World map {state}: ({observation.left}, {observation.top})-"
            f"({observation.right}, {observation.bottom}), zoom {observation.zoom:g}, "
            f"pan ({observation.horizontal_pan}, {observation.vertical_pan})"
        )
    return 0


def _test_world_map_click(
    *,
    client_profile_path: Path,
    native_world_map_profile_path: Path | None,
    map_x_fraction: float,
    map_y_fraction: float,
    wait_for_client_seconds: float,
    timeout_seconds: float,
    evidence_output_path: Path | None,
    live: bool,
    as_json: bool,
) -> int:
    if not live:
        return _error(
            "world-map click testing requires the explicit --live flag",
            as_json=as_json,
        )
    if not 0.0 <= map_x_fraction <= 1.0 or not 0.0 <= map_y_fraction <= 1.0:
        return _error("map fractions must be in [0, 1]", as_json=as_json)
    if not 0.0 <= wait_for_client_seconds <= 300.0:
        return _error(
            "wait-for-client-seconds must be in [0, 300]",
            as_json=as_json,
        )
    if not 0.1 <= timeout_seconds <= 30.0:
        return _error("timeout-seconds must be in [0.1, 30]", as_json=as_json)
    if evidence_output_path is not None and evidence_output_path.exists():
        return _error(
            f"client-action evidence destination already exists: {evidence_output_path}",
            as_json=as_json,
        )

    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        world_map_profile = (
            load_native_world_map_profile(native_world_map_profile_path)
            if native_world_map_profile_path is not None
            else load_bundled_native_world_map_profile()
        )
        inspector = WindowsForegroundWindowInspector()
        initial_guard = ForegroundWindowGuard(client_profile, inspector)
        window = _wait_for_guarded_client(
            initial_guard,
            wait_seconds=wait_for_client_seconds,
        )
        if (
            window.process_id is None
            or window.process_started_at_100ns is None
            or window.window_handle is None
        ):
            raise WindowGuardError("foreground client lacks an exact process/window lifetime")
        guard = ForegroundWindowGuard(
            client_profile,
            inspector,
            expected_process_id=window.process_id,
            expected_process_started_at_100ns=window.process_started_at_100ns,
            expected_window_handle=window.window_handle,
        )
        with (
            open_windows_native_world_map_reader(
                world_map_profile,
                process_id=window.process_id,
            ) as world_map_reader,
            open_windows_extension_event_consumer(
                window.process_id,
                window.process_started_at_100ns,
            ) as event_consumer,
            WindowsHotkeyEmergencyStop() as emergency_stop,
        ):
            executor = GuardedInputExecutor(
                guard=guard,
                backend=WorldMapTestInputBackend(),
                stop_signal=emergency_stop,
            )
            result = ClientActionRunner().run(
                WorldMapDestinationClickAction(
                    window_guard=guard,
                    world_map=world_map_reader,
                    events=event_consumer,
                    executor=executor,
                    map_x_fraction=map_x_fraction,
                    map_y_fraction=map_y_fraction,
                    timeout_ms=round(timeout_seconds * 1000),
                )
            )
        if evidence_output_path is not None:
            save_client_action_evidence(evidence_output_path, result)
    except (
        CalibrationLoadError,
        ClientActionEvidenceError,
        NativeWorldMapError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        return _error(f"world-map click test failed: {exc}", as_json=as_json)

    payload = {"ok": result.succeeded, **result.to_dict()}
    if evidence_output_path is not None:
        payload["evidence_output"] = str(evidence_output_path)
    if as_json:
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
    else:
        for boundary in result.boundaries:
            print(f"{boundary.at_ms:06d}ms {boundary.boundary.value.upper():<20} {boundary.detail}")
        status = "PASS" if result.succeeded else "FAIL"
        print(f"{status}: {result.terminal_reason}")
        if evidence_output_path is not None:
            print(f"Evidence: {evidence_output_path}")
    return 0 if result.succeeded else 2


def _observe_native_player(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_vitals_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_vitals_profile()
        )
        with open_windows_native_player_vitals_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (NativePlayerVitalsError, NativeVitalsProfileLoadError, OSError, ValueError) as exc:
        return _error(f"native player observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "current_health": observation.current_health,
        "maximum_health": observation.maximum_health,
        "health_fraction": observation.health_fraction,
        "current_mana": observation.current_mana,
        "maximum_mana": observation.maximum_mana,
        "mana_fraction": observation.mana_fraction,
        "current_stamina": observation.current_stamina,
        "maximum_stamina": observation.maximum_stamina,
        "stamina_fraction": observation.stamina_fraction,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Health: {observation.current_health:g}/{observation.maximum_health:g} "
            f"({observation.health_fraction:.1%})"
        )
        print(
            f"Mana: {observation.current_mana:g}/{observation.maximum_mana:g} "
            f"({observation.mana_fraction:.1%})"
        )
        print(
            f"Stamina: {observation.current_stamina:g}/{observation.maximum_stamina:g} "
            f"({observation.stamina_fraction:.1%})"
        )
    return 0


def _observe_native_position(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_position_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_position_profile()
        )
        with open_windows_native_player_position_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativePlayerPositionError,
        NativePositionProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native position observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "lt": observation.lt,
        "lg": observation.lg,
        "altitude": observation.altitude,
        "transform_count": observation.transform_count,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"LT: {observation.lt:.2f}")
        print(f"LG: {observation.lg:.2f}")
        print(f"ALT: {observation.altitude:.2f}")
        print(f"Canonical position sources: {observation.transform_count}")
    return 0


def _observe_native_zone(
    profile_path: Path | None,
    cache_directory: Path | None,
    *,
    as_json: bool,
) -> int:
    try:
        profile = (
            load_native_zone_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_zone_profile()
        )
        with open_windows_native_current_zone_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
        terrain_by_depth: dict[int, object] = {}
        if cache_directory is not None:
            with (
                CacheArchive(cache_directory / "CZone.cache") as zones,
                CacheArchive(cache_directory / "TerrainAlpha.cache") as terrain,
            ):
                for identity in observation.chain:
                    if not identity.cache_resolvable:
                        continue
                    correlation = correlate_zone_terrain(
                        zones,
                        terrain,
                        identity.template_group_id,
                        identity.template_id,
                    )
                    terrain_by_depth[identity.depth] = {
                        "tile_references": correlation.tile_reference_count,
                        "maps": [
                            {
                                "layer_index": item.layer_index,
                                "layer_kind": (
                                    "height" if item.is_height_map else "material_alpha"
                                ),
                                "group_id": item.group_id,
                                "map_id": item.map_id,
                                "width_tiles": item.width_tiles,
                                "height_tiles": item.height_tiles,
                                "tile_count": item.tile_count,
                            }
                            for item in correlation.maps
                        ],
                    }
    except (
        CacheArchiveFormatError,
        NativeCurrentZoneError,
        NativeZoneProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native zone observation failed: {exc}", as_json=as_json)
    current = observation.current
    chain = [
        {
            "depth": identity.depth,
            "name": identity.name,
            "template_group_id": identity.template_group_id,
            "template_id": identity.template_id,
            "cache_resolvable": identity.cache_resolvable,
            "object_type": identity.object_type,
            "object_uuid": identity.object_uuid,
            "geometry": {
                "minimum_local_x": identity.geometry.minimum_local_x,
                "minimum_local_z": identity.geometry.minimum_local_z,
                "maximum_local_x": identity.geometry.maximum_local_x,
                "maximum_local_z": identity.geometry.maximum_local_z,
                "rotation": {
                    "w": identity.geometry.rotation_w,
                    "x": identity.geometry.rotation_x,
                    "y": identity.geometry.rotation_y,
                    "z": identity.geometry.rotation_z,
                },
                "center_lt": identity.geometry.center_lt,
                "center_lg": identity.geometry.center_lg,
                "absolute_center_x": identity.geometry.absolute_center_x,
                "absolute_center_z": identity.geometry.absolute_center_z,
                "local_center_x": identity.geometry.local_center_x,
                "local_center_z": identity.geometry.local_center_z,
                "radius_x": identity.geometry.radius_x,
                "radius_z": identity.geometry.radius_z,
            },
            "terrain": terrain_by_depth.get(identity.depth),
        }
        for identity in observation.chain
    ]
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "name": observation.name,
        "zone_token": observation.zone_token,
        "name_source_depth": observation.name_source_depth,
        "template_group_id": current.template_group_id,
        "template_id": current.template_id,
        "cache_resolvable": current.cache_resolvable,
        "object_type": current.object_type,
        "object_uuid": current.object_uuid,
        "chain": chain,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Zone: {observation.name}")
        print(f"Zone token: {observation.zone_token}")
        print(f"Template: {current.template_group_id}:{current.template_id}")
        print(f"Object: {current.object_type}:{current.object_uuid}")
        print(f"Name source depth: {observation.name_source_depth}")
        for item in chain:
            terrain = item["terrain"]
            if terrain is None:
                continue
            maps = terrain["maps"]
            map_names = ", ".join(f"{entry['group_id']}:{entry['map_id']}" for entry in maps)
            print(f"Terrain depth {item['depth']}: {map_names or 'none'}")
    return 0


def _observe_native_group(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_group_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_group_profile()
        )
        with open_windows_native_group_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativeGroupError,
        NativeGroupProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native group observation failed: {exc}", as_json=as_json)
    leader = observation.leader
    members = [
        {
            "first_name": member.first_name,
            "last_name": member.last_name,
            "full_name": member.full_name,
            "object_type": member.object_type,
            "object_uuid": member.object_uuid,
            "health_percent": member.health_percent,
            "stamina_percent": member.stamina_percent,
            "mana_percent": member.mana_percent,
            "lt": member.lt,
            "lg": member.lg,
            "altitude": member.altitude,
            "role_code": member.role_code,
            "is_leader": member.is_leader,
            "follow_enabled": member.follow_enabled,
        }
        for member in observation.members
    ]
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        "grouped": observation.grouped,
        "split_gold_enabled": observation.split_gold_enabled,
        "local_follow_enabled": observation.local_follow_enabled,
        "leader_uuid": leader.object_uuid if leader is not None else None,
        "members": members,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Grouped: {observation.grouped}")
        print(f"Split gold: {observation.split_gold_enabled}")
        print(f"Following: {observation.local_follow_enabled}")
        for member in members:
            role = "leader" if member["is_leader"] else "member"
            print(
                f"{member['full_name']} ({role}, {member['object_uuid']}): "
                f"LT {member['lt']:.2f}, LG {member['lg']:.2f}, "
                f"ALT {member['altitude']:.2f}; "
                f"H/S/M {member['health_percent']}/"
                f"{member['stamina_percent']}/{member['mana_percent']}"
            )
    return 0


def _observe_native_progression(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_progression_core_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_progression_core_profile()
        )
        with open_windows_native_player_progression_core_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativePlayerProgressionCoreError,
        NativeProgressionCoreProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native progression observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        **observation.as_dict(),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Level: {observation.level}")
        print(f"Ability points: {observation.unspent_ability_points}")
        print(f"Training points: {observation.unspent_training_points}")
        print(
            f"Attack rating: {observation.left_attack_rating}/"
            f"{observation.right_attack_rating} (left/right)"
        )
        print(f"Defense: {observation.defense}")
    return 0


def _observe_native_training(profile_path: Path | None, *, as_json: bool) -> int:
    try:
        profile = (
            load_native_training_profile(profile_path)
            if profile_path is not None
            else load_bundled_native_training_profile()
        )
        with open_windows_native_player_training_reader(profile) as reader:
            observation = reader.observe()
            process_id = reader.process_id
    except (
        NativePlayerTrainingError,
        NativeTrainingProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native training observation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "process_id": process_id,
        **observation.as_dict(),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print("Skills:")
        for entry in observation.skills:
            print(
                f"  {entry.display_name}: {entry.effective_rank} "
                f"(trained {entry.trained_rank}, max {entry.effective_rank_max})"
            )
        print("Powers:")
        for entry in observation.powers:
            print(
                f"  {entry.display_name}: {entry.effective_rank} "
                f"(trained {entry.trained_rank}, max {entry.effective_rank_max})"
            )
    return 0


def _trace_native_vendor_dialog(
    profile_path: Path | None,
    *,
    process_id: int | None,
    output_path: Path,
    label: str,
    timeout_seconds: float,
    settle_seconds: float,
    as_json: bool,
) -> int:
    try:
        if profile_path is None:
            profile, tracer = open_windows_bundled_native_vendor_dialog_tracer(
                process_id=process_id
            )
        else:
            profile = load_native_vendor_dialog_profile(profile_path)
            tracer = open_windows_native_vendor_dialog_tracer(
                profile,
                process_id=process_id,
            )

        def announce_armed() -> None:
            print(
                f"Vendor-dialog trace armed for PID {tracer.backend.pid}; trigger {label} now.",
                file=sys.stderr,
                flush=True,
            )

        summary = tracer.trace(
            output_path,
            label=label,
            timeout_seconds=timeout_seconds,
            settle_seconds=settle_seconds,
            armed_callback=announce_armed,
        )
    except (
        NativeVendorDialogError,
        NativeVendorDialogProfileLoadError,
        FileExistsError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native vendor-dialog trace failed: {exc}", as_json=as_json)
    payload = summary.as_dict()
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Captured {summary.complete_message_count} complete vendor message(s) across "
            f"{summary.hit_count} breakpoint hit(s)."
        )
        print(f"Evidence: {summary.output_path}")
    return 0


def _advise_irekei_proc(
    progression_profile_path: Path | None,
    training_profile_path: Path | None,
    *,
    as_json: bool,
) -> int:
    try:
        progression_profile = (
            load_native_progression_core_profile(progression_profile_path)
            if progression_profile_path is not None
            else load_bundled_native_progression_core_profile()
        )
        training_profile = (
            load_native_training_profile(training_profile_path)
            if training_profile_path is not None
            else load_bundled_native_training_profile()
        )
        with open_windows_native_player_progression_core_reader(
            progression_profile
        ) as progression_reader:
            progression = progression_reader.observe()
            progression_process_id = progression_reader.process_id
        with open_windows_native_player_training_reader(training_profile) as training_reader:
            training = training_reader.observe()
            training_process_id = training_reader.process_id
        if progression_process_id != training_process_id:
            raise ValueError("native progression sources resolved different processes")
        roadmap = irekei_proc_assassin_roadmap(
            load_wonderbane_irekei_proc_profile(),
            level=progression.level,
        )
        audit = audit_proc_assassin_training(
            roadmap,
            skill_ranks={item.key: item.effective_rank for item in training.skills},
            power_ranks={item.key: item.effective_rank for item in training.powers},
            unspent_training_points=progression.unspent_training_points,
        )
    except (
        NativePlayerProgressionCoreError,
        NativePlayerTrainingError,
        NativeProgressionCoreProfileLoadError,
        NativeTrainingProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"proc-Assassin advice failed: {exc}", as_json=as_json)

    payload = {
        "ok": True,
        "process_id": progression_process_id,
        "progression_profile_id": progression_profile.profile_id,
        "training_profile_id": training_profile.profile_id,
        "unresolved_power_tokens": [
            f"0x{item.token:08X}" for item in training.powers if not item.catalogued
        ],
        "audit": audit.as_dict(),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Level {audit.level}: {audit.unspent_training_points} training points remain")
        unmet_powers = [item for item in audit.power_targets if not item.target_met]
        print("Power rank increases:")
        for item in unmet_powers:
            print(f"  {item.key}: {item.current_rank} -> {item.target_rank} (+{item.rank_gap})")
        print(
            f"Power ranks needed: {audit.power_rank_increments_needed}; "
            f"reserve after those ranks: {audit.power_training_reserve_after_targets}"
        )
        print("End-state displayed skill gaps (not training-point costs):")
        for item in audit.skill_targets:
            if not item.target_met:
                print(
                    f"  {item.key}: {item.current_rank} -> {item.target_rank} "
                    f"(displayed gap {item.rank_gap})"
                )
    return 0


def _run_pve(
    *,
    client_profile_path: Path,
    combat_log_path: Path | None,
    hotbar_config_path: Path | None,
    native_health_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    native_position_profile_path: Path | None,
    native_target_position_profile_path: Path | None,
    native_target_action_profile_path: Path | None,
    navigation_cache_directory: Path | None,
    max_kills: int,
    max_seconds: float,
    wait_for_client_seconds: float,
    poll_ms: int,
    policy: str,
    live: bool,
    as_json: bool,
    evidence_output_path: Path | None = None,
    combat_source: str | None = None,
    native_message_hud_profile_path: Path | None = None,
    native_target_identity_profile_path: Path | None = None,
    max_encounter_seconds: float = 120.0,
    recovery_timeout_seconds: float = 30.0,
    recovery_health_fraction: float = 0.75,
    recovery_mana_fraction: float = 0.15,
    recovery_stamina_fraction: float = 0.25,
    stop_signal: StopSignal | None = None,
    client_process_id: int | None = None,
    continuous: bool = False,
    camp_radius: float = 120.0,
    retained_trace_steps: int = 2_000,
    native_character_population_profile_path: Path | None = None,
    navigation_map: SparseNavigationMap | None = None,
) -> int:
    if not live:
        return _error("PvE execution requires the explicit --live flag", as_json=as_json)
    if isinstance(max_kills, bool) or not 1 <= max_kills <= 10:
        return _error("max-kills must be in [1, 10]", as_json=as_json)
    if not isinstance(continuous, bool):
        return _error("continuous must be a boolean", as_json=as_json)
    if not 20.0 <= camp_radius <= 1_000.0:
        return _error("camp-radius must be in [20, 1000]", as_json=as_json)
    if isinstance(retained_trace_steps, bool) or not 100 <= retained_trace_steps <= 100_000:
        return _error(
            "retained-trace-steps must be in [100, 100000]",
            as_json=as_json,
        )
    if continuous and evidence_output_path is None:
        return _error(
            "continuous PvE requires --evidence-output for its durable journal",
            as_json=as_json,
        )
    if not 1.0 <= max_seconds <= 900.0:
        return _error("max-seconds must be in [1, 900]", as_json=as_json)
    if not 5.0 <= max_encounter_seconds <= 300.0:
        return _error("max-encounter-seconds must be in [5, 300]", as_json=as_json)
    if not 1.0 <= recovery_timeout_seconds <= 300.0:
        return _error("recovery-timeout-seconds must be in [1, 300]", as_json=as_json)
    for value, field_name in (
        (recovery_health_fraction, "recovery-health-fraction"),
        (recovery_mana_fraction, "recovery-mana-fraction"),
        (recovery_stamina_fraction, "recovery-stamina-fraction"),
    ):
        if not 0.0 <= value <= 1.0:
            return _error(f"{field_name} must be in [0, 1]", as_json=as_json)
    if 0.0 < recovery_health_fraction < 0.5:
        return _error(
            "recovery-health-fraction cannot be below the 0.5 safety threshold",
            as_json=as_json,
        )
    if not 0.0 <= wait_for_client_seconds <= 300.0:
        return _error("wait-for-client-seconds must be in [0, 300]", as_json=as_json)
    if isinstance(poll_ms, bool) or not 50 <= poll_ms <= 1_000:
        return _error("poll-ms must be in [50, 1000]", as_json=as_json)
    if policy not in ("basic", "proc-assassin"):
        return _error("policy must be basic or proc-assassin", as_json=as_json)
    resolved_combat_source = combat_source or ("log" if combat_log_path is not None else "hud")
    if resolved_combat_source not in ("state", "hud", "log"):
        return _error("combat-source must be state, hud, or log", as_json=as_json)
    if resolved_combat_source == "log":
        if combat_log_path is None:
            return _error("combat-source log requires --combat-log", as_json=as_json)
        if not combat_log_path.is_file():
            return _error(f"combat log does not exist: {combat_log_path}", as_json=as_json)
    journal_path = (
        evidence_output_path.with_name(f"{evidence_output_path.stem}.events.jsonl")
        if continuous and evidence_output_path is not None
        else None
    )
    terrain_navigation_payload: dict[str, object] = {
        "enabled": navigation_cache_directory is not None,
        "status": "not_configured",
    }
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        if client_profile.movement.button is not MouseButton.RIGHT:
            raise ValueError("PvE approach movement must use right-click input")
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=max_kills,
                maximum_session_ms=round(max_seconds * 1000),
                engagement_timeout_ms=round(max_encounter_seconds * 1000),
                recovery_timeout_ms=round(recovery_timeout_seconds * 1000),
                minimum_recovery_health_fraction=recovery_health_fraction,
                minimum_recovery_mana_fraction=recovery_mana_fraction,
                minimum_recovery_stamina_fraction=recovery_stamina_fraction,
                accept_automatic_targets=policy == "proc-assassin",
                interrupt_intent=(
                    PvEIntent.CAST_SHADOW_TOUCH if policy == "proc-assassin" else None
                ),
                interrupt_mana_cost=55.0 if policy == "proc-assassin" else 0.0,
                interrupt_cooldown_ms=2_000 if policy == "proc-assassin" else 0,
                maximum_interrupts_per_target=1 if policy == "proc-assassin" else 0,
                automatic_attack_expected=policy == "proc-assassin",
                automatic_target_requires_combat_event=policy == "proc-assassin",
                require_target_identity=True,
                use_native_population=True,
                maximum_stalled_retargets=4 if policy == "proc-assassin" else 0,
                nearest_target_sample_count=1,
                target_sample_interval_ms=350,
                continuous=continuous,
                camp_radius=camp_radius if continuous else None,
            )
        )
        mapped_actions = {mapping.action_key for mapping in client_profile.actions}
        required_actions = {intent.value for intent in controller.required_intents}
        missing_actions = required_actions - mapped_actions
        if missing_actions:
            raise ValueError(
                f"client profile is missing PvE mappings: {', '.join(sorted(missing_actions))}"
            )
        if policy == "proc-assassin":
            _verify_hotbar_power_mapping(
                client_profile.actions,
                hotbar_config_path,
                action_key=PvEIntent.CAST_SHADOW_TOUCH.value,
                power_name=ArcaneClientPower.SHADOW_TOUCH,
            )
        health_profile = (
            load_native_health_profile(native_health_profile_path)
            if native_health_profile_path is not None
            else load_bundled_native_health_profile()
        )
        message_hud_profile = None
        if resolved_combat_source == "hud":
            message_hud_profile = (
                load_native_message_hud_profile(native_message_hud_profile_path)
                if native_message_hud_profile_path is not None
                else load_bundled_native_message_hud_profile()
            )
        vitals_profile = (
            load_native_vitals_profile(native_vitals_profile_path)
            if native_vitals_profile_path is not None
            else load_bundled_native_vitals_profile()
        )
        position_profile = (
            load_native_position_profile(native_position_profile_path)
            if native_position_profile_path is not None
            else load_bundled_native_position_profile()
        )
        target_position_profile = (
            load_native_target_position_profile(native_target_position_profile_path)
            if native_target_position_profile_path is not None
            else load_bundled_native_target_position_profile()
        )
        target_action_profile = (
            load_native_target_action_profile(native_target_action_profile_path)
            if native_target_action_profile_path is not None
            else load_bundled_native_target_action_profile()
        )
        target_identity_profile = (
            load_native_target_identity_profile(native_target_identity_profile_path)
            if native_target_identity_profile_path is not None
            else load_bundled_native_target_identity_profile()
        )
        character_population_profile = (
            load_native_character_population_profile(native_character_population_profile_path)
            if native_character_population_profile_path is not None
            else load_bundled_native_character_population_profile()
        )
        zone_profile = (
            None if navigation_cache_directory is None else load_bundled_native_zone_profile()
        )
        if navigation_cache_directory is not None and not navigation_cache_directory.is_dir():
            raise ValueError(
                f"navigation cache directory does not exist: {navigation_cache_directory}"
            )
        native_profile_hashes = {
            health_profile.executable_sha256,
            vitals_profile.executable_sha256,
            position_profile.executable_sha256,
            target_position_profile.executable_sha256,
            target_action_profile.executable_sha256,
            target_identity_profile.executable_sha256,
            character_population_profile.executable_sha256,
        }
        if message_hud_profile is not None:
            native_profile_hashes.add(message_hud_profile.executable_sha256)
        if zone_profile is not None:
            native_profile_hashes.add(zone_profile.executable_sha256)
        if len(native_profile_hashes) != 1:
            raise ValueError("native PvE profiles target different client builds")
        inspector = WindowsForegroundWindowInspector()
        selection_guard = ForegroundWindowGuard(client_profile, inspector)
        if client_process_id is None:
            selected_window = _wait_for_guarded_client(
                selection_guard,
                wait_seconds=wait_for_client_seconds,
            )
            process_id = _require_window_process_id(selected_window)
        else:
            process_id = client_process_id
        guard = ForegroundWindowGuard(
            client_profile,
            inspector,
            expected_process_id=process_id,
        )
        if client_process_id is not None:
            _wait_for_guarded_client(guard, wait_seconds=wait_for_client_seconds)
        with ExitStack() as stack:
            health_reader = stack.enter_context(
                open_windows_native_target_health_reader(
                    health_profile,
                    process_id=process_id,
                )
            )
            player_vitals_reader = stack.enter_context(
                open_windows_native_player_vitals_reader(
                    vitals_profile,
                    process_id=process_id,
                )
            )
            player_position_reader = stack.enter_context(
                open_windows_native_player_position_reader(
                    position_profile,
                    process_id=process_id,
                )
            )
            target_position_reader = stack.enter_context(
                open_windows_native_target_position_reader(
                    target_position_profile,
                    process_id=process_id,
                )
            )
            target_action_reader = stack.enter_context(
                open_windows_native_target_action_reader(
                    target_action_profile,
                    process_id=process_id,
                )
            )
            target_identity_reader = stack.enter_context(
                open_windows_native_target_identity_reader(
                    target_identity_profile,
                    process_id=process_id,
                )
            )
            population_reader = stack.enter_context(
                open_windows_native_character_population_reader(
                    character_population_profile,
                    process_id=process_id,
                )
            )
            active_navigation_map = navigation_map
            zone_reader = None
            if zone_profile is not None:
                assert navigation_cache_directory is not None
                zone_reader = stack.enter_context(
                    open_windows_native_current_zone_reader(
                        zone_profile,
                        process_id=process_id,
                    )
                )
                zone_observation = zone_reader.observe()
                terrain_origin = player_position_reader.observe()
                terrain_arguments = (
                    {}
                    if active_navigation_map is None
                    else {"navigation_map": active_navigation_map}
                )
                active_terrain = load_active_zone_terrain_navigation(
                    navigation_cache_directory,
                    zone_observation,
                    terrain_origin,
                    **terrain_arguments,
                )
                active_navigation_map = active_terrain.navigation_map
                terrain_seed = active_terrain.seed
                terrain_navigation_payload = {
                    "enabled": True,
                    "status": "seeded" if terrain_seed is not None else "no_height_layer",
                    "zone_name": zone_observation.name,
                    "zone_token": zone_observation.zone_token,
                }
                if terrain_seed is not None:
                    terrain_navigation_payload["seed"] = {
                        "zone_depth": terrain_seed.zone_depth,
                        "template_group_id": terrain_seed.template_group_id,
                        "template_id": terrain_seed.template_id,
                        "terrain_group_id": terrain_seed.terrain_group_id,
                        "terrain_map_id": terrain_seed.terrain_map_id,
                        "raster_width": terrain_seed.raster_width,
                        "raster_height": terrain_seed.raster_height,
                        "window_center_lt": terrain_seed.window_center_lt,
                        "window_center_lg": terrain_seed.window_center_lg,
                        "window_radius": terrain_seed.window_radius,
                        "sampled_cells": terrain_seed.sampled_cells,
                        "blocked_cells": len(terrain_seed.blocked_cells),
                        "water_cells": len(terrain_seed.water_cells),
                        "object_density_cells": len(terrain_seed.object_density_cells),
                        "object_density_layers": [
                            {
                                "layer_index": layer.layer_index,
                                "terrain_group_id": layer.terrain_group_id,
                                "terrain_map_id": layer.terrain_map_id,
                                "object_count": layer.object_count,
                                "population_capacity": layer.population_capacity,
                                "maximum_horizontal_radius": (layer.maximum_horizontal_radius),
                            }
                            for layer in terrain_seed.object_density_layers
                        ],
                        "water_sample_threshold": terrain_seed.water_sample_threshold,
                        "weighted_cells": len(terrain_seed.costs),
                    }
            if resolved_combat_source == "state":
                combat_reader = EmptyCombatLogSource()
            elif message_hud_profile is None:
                assert combat_log_path is not None
                combat_reader = NativeCombatLogReader(combat_log_path, start_at_end=True)
            else:
                combat_reader = stack.enter_context(
                    open_windows_native_message_hud_reader(
                        message_hud_profile,
                        process_id=process_id,
                        start_at_end=True,
                    )
                )
                combat_reader.attach()
            active_stop_signal = stop_signal
            if active_stop_signal is None:
                active_stop_signal = stack.enter_context(WindowsHotkeyEmergencyStop())
            reader_process_ids = {
                health_reader.process_id,
                player_vitals_reader.process_id,
                player_position_reader.process_id,
                target_position_reader.process_id,
                target_action_reader.process_id,
                target_identity_reader.process_id,
                population_reader.process_id,
            }
            if message_hud_profile is not None:
                reader_process_ids.add(combat_reader.process_id)
            if zone_reader is not None:
                reader_process_ids.add(zone_reader.process_id)
            if len(reader_process_ids) != 1:
                raise ValueError("native PvE readers resolved different client processes")
            executor = GuardedInputExecutor(
                guard=guard,
                backend=PyAutoGuiBackend(),
                stop_signal=active_stop_signal,
            )
            adapter = ClientInputAdapter(
                DecisionInputCompiler(client_profile, StaticBindingPointResolver()),
                executor,
            )
            journal = (
                None
                if journal_path is None
                else stack.enter_context(
                    PvETraceJournal(
                        journal_path,
                        {
                            "run_mode": "continuous",
                            "policy": policy,
                            "process_id": process_id,
                            "executable_sha256": health_profile.executable_sha256,
                            "camp_radius": camp_radius,
                            "poll_ms": poll_ms,
                            "terrain_navigation": terrain_navigation_payload,
                        },
                    )
                )
            )
            result = PvERunner(
                controller=controller,
                health_reader=health_reader,
                player_vitals_reader=player_vitals_reader,
                player_position_reader=player_position_reader,
                target_position_reader=target_position_reader,
                target_action_reader=target_action_reader,
                player_action_reader=target_action_reader,
                target_identity_reader=target_identity_reader,
                population_reader=population_reader,
                combat_log_reader=combat_reader,
                dispatcher=ClientPvEIntentDispatcher(adapter),
                approach_controller=PvEApproachController(
                    navigation_map=active_navigation_map,
                ),
                movement_dispatcher=ClientTravelDecisionDispatcher(adapter),
                stop_signal=active_stop_signal,
                poll_interval_ms=poll_ms,
                maximum_retained_trace_steps=(retained_trace_steps if continuous else None),
                trace_sink=(
                    None if journal is None else lambda step: journal.append_step(step.as_dict())
                ),
            ).run()
            if journal is not None:
                journal.finish(
                    {
                        "final_phase": result.final_phase.value,
                        "terminal_reason": result.terminal_reason,
                        "kills": result.kills,
                        "total_steps": getattr(result, "total_steps", len(result.trace)),
                    }
                )
    except (
        CalibrationLoadError,
        ArcaneHotbarLoadError,
        NativeHealthProfileLoadError,
        NativeCharacterPopulationError,
        NativeCharacterPopulationProfileLoadError,
        NativeMessageHudError,
        NativeMessageHudProfileLoadError,
        NativePlayerVitalsError,
        NativePlayerPositionError,
        NativePositionProfileLoadError,
        NativeTargetHealthError,
        NativeTargetActionError,
        NativeTargetActionProfileLoadError,
        NativeTargetIdentityError,
        NativeTargetIdentityProfileLoadError,
        NativeTargetPositionError,
        NativeTargetPositionProfileLoadError,
        NativeVitalsProfileLoadError,
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        WindowGuardError,
    ) as exc:
        return _error(f"PvE run failed: {exc}", as_json=as_json)

    dispatched = [
        {
            "decision_id": step.decision.decision_id,
            "at_ms": step.decision.now_ms,
            "intent": step.decision.intent.value,
            "accepted": step.input_accepted,
            "reason": step.input_reason,
        }
        for step in result.trace
        if step.decision.intent is not None
    ]
    total_steps = getattr(result, "total_steps", len(result.trace))
    trace_truncated = getattr(result, "trace_truncated", total_steps > len(result.trace))
    camp = controller.camp
    successful = result.final_phase.value == "complete" or (
        continuous and result.terminal_reason == "emergency_stop"
    )
    payload = {
        "trace_schema_version": PVE_TRACE_SCHEMA_VERSION,
        "ok": successful,
        "final_phase": result.final_phase.value,
        "terminal_reason": result.terminal_reason,
        "run_mode": "continuous" if continuous else "bounded",
        "policy": policy,
        "kills": result.kills,
        "steps": len(result.trace),
        "total_steps": total_steps,
        "trace_truncated": trace_truncated,
        "journal_path": None if journal_path is None else str(journal_path),
        "camp_lease": (
            None
            if camp is None
            else {
                "anchor_lt": camp.anchor_lt,
                "anchor_lg": camp.anchor_lg,
                "radius": camp.radius,
                "return_radius": camp.return_radius,
                "return_trigger_radius": camp.return_trigger_radius,
            }
        ),
        "farm_limits": (
            None
            if continuous
            else {
                "maximum_kills": max_kills,
                "maximum_session_seconds": max_seconds,
                "maximum_encounter_seconds": max_encounter_seconds,
                "recovery_timeout_seconds": recovery_timeout_seconds,
                "recovery_health_fraction": recovery_health_fraction,
                "recovery_mana_fraction": recovery_mana_fraction,
                "recovery_stamina_fraction": recovery_stamina_fraction,
            }
        ),
        "continuous_policy": (
            None
            if not continuous
            else {
                "camp_radius": camp_radius,
                "retained_trace_steps": retained_trace_steps,
                "encounter_timeout_seconds": max_encounter_seconds,
                "failed_targets_expire": True,
            }
        ),
        "dispatched": dispatched,
        "native_observation": {
            "process_id": process_id,
            "executable_sha256": health_profile.executable_sha256,
            "target_health_profile_id": health_profile.profile_id,
            "character_population_profile_id": character_population_profile.profile_id,
            "player_vitals_profile_id": vitals_profile.profile_id,
            "player_position_profile_id": position_profile.profile_id,
            "target_position_profile_id": target_position_profile.profile_id,
            "target_action_profile_id": target_action_profile.profile_id,
            "target_identity_profile_id": target_identity_profile.profile_id,
            "combat_source": resolved_combat_source,
            "message_hud_profile_id": (
                None if message_hud_profile is None else message_hud_profile.profile_id
            ),
        },
        "terrain_navigation": terrain_navigation_payload,
        "trace": [step.as_dict() for step in result.trace],
    }
    if evidence_output_path is not None:
        try:
            save_pve_trace_evidence(evidence_output_path, payload)
        except PvETraceEvidenceError as exc:
            return _error(f"PvE evidence save failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"PvE phase: {result.final_phase.value}")
        print(f"Reason: {result.terminal_reason}")
        print(f"Kills: {result.kills}")
        print(f"Guarded inputs: {len(dispatched)}")
    return 0 if payload["ok"] else 2


def _calibrate_pve(
    evidence_paths: Sequence[Path],
    output_path: Path,
    *,
    as_json: bool,
) -> int:
    if any(path.absolute() == output_path.absolute() for path in evidence_paths):
        return _error(
            "PvE calibration output cannot overwrite an input evidence artifact",
            as_json=as_json,
        )
    try:
        calibration = compile_pve_combat_calibration_files(evidence_paths)
        save_pve_combat_calibration(output_path, calibration)
    except (OSError, PvECombatCalibrationError, ValueError) as exc:
        return _error(f"PvE calibration failed: {exc}", as_json=as_json)
    payload = calibration.as_dict()
    payload["output_path"] = str(output_path)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Compiled {len(calibration.source_trace_sha256s)} PvE traces into "
            f"{calibration.profile_id}."
        )
        print(f"Calibration: {output_path}")
    return 0


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

    def poll_extension_events() -> None:
        if extension_router is None:
            return
        result = extension_router.poll_once()
        observed_at = time.monotonic()
        for process_id in result.dispatched_process_ids:
            extension_dispatch_times[process_id] = observed_at

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


def _verify_hotbar_power_mapping(
    mappings: Sequence[ActionInputMapping],
    hotbar_config_path: Path | None,
    *,
    action_key: str,
    power_name: ArcaneClientPower,
) -> None:
    if hotbar_config_path is None:
        raise ValueError("proc-assassin policy requires --hotbar-config")
    hotbar = load_arcane_hotbar(hotbar_config_path)
    slots = hotbar.current_slots_for_power(power_name)
    if len(slots) != 1:
        raise ValueError(
            f"active hotbar must contain exactly one {power_name} slot; found {len(slots)}"
        )
    mapping = next(item for item in mappings if item.action_key == action_key)
    expected = slots[0].activation
    if mapping.activation != expected:
        raise ValueError(
            f"client profile maps {action_key} to {mapping.activation}, "
            f"but active hotbar maps {power_name} to {expected}"
        )


def _wait_for_guarded_client(
    guard: ForegroundWindowGuard,
    *,
    wait_seconds: float,
) -> WindowSnapshot:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return guard.require_target()
        except WindowGuardError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.1, remaining))


def _require_window_process_id(snapshot: WindowSnapshot) -> int:
    if snapshot.process_id is None:
        raise WindowGuardError("foreground process identity is unavailable")
    return snapshot.process_id


def _import_wonderbane_calculator(
    snapshot_path: Path | None,
    output_directory: Path,
    *,
    download: bool,
    retrieved_at_text: str | None,
    as_json: bool,
) -> int:
    try:
        retrieved_at = _parse_retrieved_at(retrieved_at_text)
        if download:
            artifacts = capture_wonderbane_calculator_snapshot(
                output_directory,
                retrieved_at=retrieved_at,
            )
        else:
            if snapshot_path is None:
                raise WonderbaneCalculatorImportError(
                    "calculator import requires --snapshot or --download"
                )
            artifacts = import_wonderbane_calculator_snapshot(
                snapshot_path,
                output_directory,
                retrieved_at=retrieved_at,
            )
    except (OSError, ValueError, WonderbaneCalculatorImportError) as exc:
        return _error(f"WonderBane calculator import failed: {exc}", as_json=as_json)

    catalog = artifacts.catalog
    payload = {
        "ok": catalog.review_status is CalculatorReviewStatus.ACCEPTED,
        "review_status": catalog.review_status.value,
        "evidence_status": catalog.evidence_status,
        "snapshot_path": str(artifacts.snapshot_path),
        "snapshot_sha256": catalog.snapshot_sha256,
        "manifest_path": str(artifacts.manifest_path),
        "catalog_path": str(artifacts.catalog_path),
        "declaration_sha256": catalog.declaration_sha256,
        "review_profile_id": catalog.review_profile_id,
        "counts": catalog.to_dict()["counts"],
        "unresolved_references": list(catalog.unresolved_references),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Snapshot: {artifacts.snapshot_path}")
        print(f"SHA-256: {catalog.snapshot_sha256}")
        print(f"Catalog: {artifacts.catalog_path}")
        print(f"Review: {catalog.review_status.value}")
        counts = payload["counts"]
        print(
            "Records: "
            f"{counts['race_records']} race/sex, "
            f"{counts['base_classes']} bases, "
            f"{counts['promotions']} promotions, "
            f"{counts['runes']} runes"
        )
    return 0 if catalog.review_status is CalculatorReviewStatus.ACCEPTED else 2


def _parse_retrieved_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WonderbaneCalculatorImportError("retrieved-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise WonderbaneCalculatorImportError("retrieved-at must include a UTC offset")
    return parsed.astimezone(UTC)


def _error(message: str, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    else:
        print(message, file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
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
    if arguments.command == "manager" and arguments.manager_command == "app":
        return _run_manager_app(
            arguments.manifest,
            port=arguments.port,
            launch_timeout_seconds=arguments.launch_timeout_seconds,
            poll_ms=arguments.poll_ms,
            worker_state_directory=arguments.worker_state_directory,
            pid_file=arguments.pid_file,
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
