"""Command-line diagnostics used by the WonderBane VM bootstrap."""

from __future__ import annotations

import argparse
import json
import ntpath
import queue
import sys
import threading
import time
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

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
    MouseButton,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    StopSignal,
    WindowGuardError,
    WindowsForegroundWindowInspector,
    WindowsHotkeyEmergencyStop,
    WindowSnapshot,
    WindowsVisibleWindowInspector,
    load_arcane_hotbar,
    load_arcane_hotkeys,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    ClientTargetObserver,
    NativeCombatLogFormatError,
    NativeCombatLogReader,
    NativeCurrentZoneError,
    NativeGroupError,
    NativeGroupProfileLoadError,
    NativeHealthProfileLoadError,
    NativePlayerPositionError,
    NativePlayerProgressionCoreError,
    NativePlayerTrainingError,
    NativePlayerVitalsError,
    NativePositionProfileLoadError,
    NativeProgressionCoreProfileLoadError,
    NativeTargetHealthError,
    NativeTargetPositionError,
    NativeTargetPositionProfileLoadError,
    NativeTrainingProfileLoadError,
    NativeVitalsProfileLoadError,
    NativeZoneProfileLoadError,
    ObservationCalibrationLoadError,
    ObservationDetectionError,
    PyAutoGuiFrameCapture,
    load_bundled_native_group_profile,
    load_bundled_native_health_profile,
    load_bundled_native_position_profile,
    load_bundled_native_progression_core_profile,
    load_bundled_native_target_position_profile,
    load_bundled_native_training_profile,
    load_bundled_native_vitals_profile,
    load_bundled_native_zone_profile,
    load_native_group_profile,
    load_native_health_profile,
    load_native_position_profile,
    load_native_progression_core_profile,
    load_native_target_position_profile,
    load_native_training_profile,
    load_native_vitals_profile,
    load_native_zone_profile,
    load_observation_calibration,
    open_windows_native_current_zone_reader,
    open_windows_native_group_reader,
    open_windows_native_player_position_reader,
    open_windows_native_player_progression_core_reader,
    open_windows_native_player_training_reader,
    open_windows_native_player_vitals_reader,
    open_windows_native_target_health_reader,
    open_windows_native_target_position_reader,
)
from shadowbane_lab.progression import (
    audit_proc_assassin_training,
    irekei_proc_assassin_roadmap,
    load_wonderbane_irekei_proc_profile,
)
from shadowbane_lab.pve import (
    ClientPvEIntentDispatcher,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvERunner,
)
from shadowbane_lab.travel import (
    ClientTravelDecisionDispatcher,
    TravelController,
    TravelControllerConfig,
    TravelDestination,
    TravelDestinationStateError,
    TravelPhase,
    TravelPlan,
    TravelRunner,
    WindowsGoChatCommandListener,
    parse_go_command,
    resolve_travel_destination,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shadowbane-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    client = commands.add_parser("client", help="inspect and validate client integration")
    client_commands = client.add_subparsers(dest="client_command", required=True)

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
    inspect_hotkeys.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    inspect_hotbar = client_commands.add_parser(
        "inspect-hotbar",
        help="read F1-F12 power assignments from a character SCREEN_GAME config",
    )
    inspect_hotbar.add_argument("character_config", type=Path)
    inspect_hotbar.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

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
        help=(
            "native target-position profile; defaults to the verified bundled "
            "WonderBane build"
        ),
    )
    observe_native_target_position.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
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
        help="run a bounded native-observation PvE loop against nearby mobiles",
    )
    run_pve.add_argument("--client-profile", type=Path, required=True)
    run_pve.add_argument("--combat-log", type=Path, required=True)
    run_pve.add_argument(
        "--hotbar-config",
        type=Path,
        help="character SCREEN_GAME config; required by policies that activate hotbar powers",
    )
    run_pve.add_argument("--native-health-profile", type=Path)
    run_pve.add_argument("--native-vitals-profile", type=Path)
    run_pve.add_argument("--native-position-profile", type=Path)
    run_pve.add_argument("--native-target-position-profile", type=Path)
    run_pve.add_argument("--max-kills", type=int, default=1)
    run_pve.add_argument("--max-seconds", type=float, default=120.0)
    run_pve.add_argument("--wait-for-client-seconds", type=float, default=15.0)
    run_pve.add_argument("--poll-ms", type=int, default=100)
    run_pve.add_argument(
        "--policy",
        choices=("basic", "proc-assassin"),
        default="basic",
        help=(
            "bounded control policy; proc-assassin accepts auto-targets and opens "
            "with Shadow Touch"
        ),
    )
    run_pve.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    run_pve.add_argument("--json", action="store_true", help="emit machine-readable JSON")

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
    go.add_argument("--max-seconds", type=float, default=300.0)
    go.add_argument("--wait-for-client-seconds", type=float, default=30.0)
    go.add_argument("--poll-ms", type=int, default=200)
    go.add_argument("--click-interval-ms", type=int, default=4_000)
    go.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    go.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    listen_go = client_commands.add_parser(
        "listen-go",
        help="listen for foreground in-game /go commands and run bounded travel",
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
    listen_go.add_argument("--max-seconds", type=float, default=300.0)
    listen_go.add_argument("--wait-for-client-seconds", type=float, default=30.0)
    listen_go.add_argument("--poll-ms", type=int, default=200)
    listen_go.add_argument("--click-interval-ms", type=int, default=4_000)
    listen_go.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    listen_go.add_argument("--json", action="store_true", help="emit JSON Lines events")
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
            print(
                f"{action['display_name']} [{action['native_action_code']}]: {rendered}"
            )
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
                            {
                                f"{item.width_tiles}x{item.height_tiles}"
                                for item in maps
                            }
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
            map_names = ", ".join(
                f"{entry['group_id']}:{entry['map_id']}" for entry in maps
            )
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
    combat_log_path: Path,
    hotbar_config_path: Path | None,
    native_health_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    native_position_profile_path: Path | None,
    native_target_position_profile_path: Path | None,
    max_kills: int,
    max_seconds: float,
    wait_for_client_seconds: float,
    poll_ms: int,
    policy: str,
    live: bool,
    as_json: bool,
) -> int:
    if not live:
        return _error("PvE execution requires the explicit --live flag", as_json=as_json)
    if isinstance(max_kills, bool) or not 1 <= max_kills <= 10:
        return _error("max-kills must be in [1, 10]", as_json=as_json)
    if not 1.0 <= max_seconds <= 900.0:
        return _error("max-seconds must be in [1, 900]", as_json=as_json)
    if not 0.0 <= wait_for_client_seconds <= 300.0:
        return _error("wait-for-client-seconds must be in [0, 300]", as_json=as_json)
    if isinstance(poll_ms, bool) or not 50 <= poll_ms <= 1_000:
        return _error("poll-ms must be in [50, 1000]", as_json=as_json)
    if policy not in ("basic", "proc-assassin"):
        return _error("policy must be basic or proc-assassin", as_json=as_json)
    if not combat_log_path.is_file():
        return _error(f"combat log does not exist: {combat_log_path}", as_json=as_json)
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=max_kills,
                maximum_session_ms=round(max_seconds * 1000),
                accept_automatic_targets=policy == "proc-assassin",
                opening_intent=(
                    PvEIntent.CAST_SHADOW_TOUCH if policy == "proc-assassin" else None
                ),
                opening_mana_cost=55.0 if policy == "proc-assassin" else 0.0,
                automatic_attack_expected=policy == "proc-assassin",
                automatic_target_requires_combat_event=policy == "proc-assassin",
                maximum_stalled_retargets=1 if policy == "proc-assassin" else 0,
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
        native_profile_hashes = {
            health_profile.executable_sha256,
            vitals_profile.executable_sha256,
            position_profile.executable_sha256,
            target_position_profile.executable_sha256,
        }
        if len(native_profile_hashes) != 1:
            raise ValueError("native PvE profiles target different client builds")
        inspector = WindowsForegroundWindowInspector()
        guard = ForegroundWindowGuard(client_profile, inspector)
        _wait_for_guarded_client(
            guard,
            wait_seconds=wait_for_client_seconds,
        )
        combat_reader = NativeCombatLogReader(combat_log_path, start_at_end=True)
        with ExitStack() as stack:
            health_reader = stack.enter_context(
                open_windows_native_target_health_reader(health_profile)
            )
            player_vitals_reader = stack.enter_context(
                open_windows_native_player_vitals_reader(vitals_profile)
            )
            player_position_reader = stack.enter_context(
                open_windows_native_player_position_reader(position_profile)
            )
            target_position_reader = stack.enter_context(
                open_windows_native_target_position_reader(target_position_profile)
            )
            stop_signal = stack.enter_context(WindowsHotkeyEmergencyStop())
            reader_process_ids = {
                health_reader.process_id,
                player_vitals_reader.process_id,
                player_position_reader.process_id,
                target_position_reader.process_id,
            }
            if len(reader_process_ids) != 1:
                raise ValueError("native PvE readers resolved different client processes")
            process_id = health_reader.process_id
            executor = GuardedInputExecutor(
                guard=guard,
                backend=PyAutoGuiBackend(),
                stop_signal=stop_signal,
            )
            adapter = ClientInputAdapter(
                DecisionInputCompiler(client_profile, StaticBindingPointResolver()),
                executor,
            )
            result = PvERunner(
                controller=controller,
                health_reader=health_reader,
                player_vitals_reader=player_vitals_reader,
                player_position_reader=player_position_reader,
                target_position_reader=target_position_reader,
                combat_log_reader=combat_reader,
                dispatcher=ClientPvEIntentDispatcher(adapter),
                stop_signal=stop_signal,
                poll_interval_ms=poll_ms,
            ).run()
    except (
        CalibrationLoadError,
        ArcaneHotbarLoadError,
        NativeHealthProfileLoadError,
        NativePlayerVitalsError,
        NativePlayerPositionError,
        NativePositionProfileLoadError,
        NativeTargetHealthError,
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
    payload = {
        "trace_schema_version": 1,
        "ok": result.final_phase.value == "complete",
        "final_phase": result.final_phase.value,
        "terminal_reason": result.terminal_reason,
        "policy": policy,
        "kills": result.kills,
        "steps": len(result.trace),
        "dispatched": dispatched,
        "native_observation": {
            "process_id": process_id,
            "executable_sha256": health_profile.executable_sha256,
            "target_health_profile_id": health_profile.profile_id,
            "player_vitals_profile_id": vitals_profile.profile_id,
            "player_position_profile_id": position_profile.profile_id,
            "target_position_profile_id": target_position_profile.profile_id,
        },
        "trace": [step.as_dict() for step in result.trace],
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"PvE phase: {result.final_phase.value}")
        print(f"Reason: {result.terminal_reason}")
        print(f"Kills: {result.kills}")
        print(f"Guarded inputs: {len(dispatched)}")
    return 0 if payload["ok"] else 2


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
) -> int:
    if not live:
        return _error("travel execution requires the explicit --live flag", as_json=as_json)
    if radius is not None and not 5.0 <= radius <= 1_000.0:
        return _error("radius must be in [5, 1000]", as_json=as_json)
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
        plan = TravelPlan(
            plan_id=f"go:{lt:g}:{lg:g}:{radius:g}",
            destinations=(TravelDestination(lt, lg, radius),),
        )
        controller = TravelController(
            plan,
            TravelControllerConfig(
                maximum_session_ms=round(max_seconds * 1000),
                click_interval_ms=click_interval_ms,
                maximum_clicks=min(500, max(1, round(max_seconds * 1000 / click_interval_ms))),
            ),
        )
        guard = ForegroundWindowGuard(client_profile, WindowsForegroundWindowInspector())
        with ExitStack() as stack:
            position_reader = stack.enter_context(
                open_windows_native_player_position_reader(position_profile)
            )
            player_vitals_reader = stack.enter_context(
                open_windows_native_player_vitals_reader(vitals_profile)
            )
            active_stop_signal = stop_signal
            if active_stop_signal is None:
                active_stop_signal = stack.enter_context(WindowsHotkeyEmergencyStop())
            if position_reader.process_id != player_vitals_reader.process_id:
                raise ValueError(
                    "native position and player-vitals readers resolved different processes"
                )
            _wait_for_guarded_client(guard, wait_seconds=wait_for_client_seconds)
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


def _listen_for_go_commands(
    *,
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
) -> int:
    if not live:
        return _error("chat travel requires the explicit --live flag", as_json=as_json)
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        guard = ForegroundWindowGuard(client_profile, WindowsForegroundWindowInspector())
    except (CalibrationLoadError, OSError, RuntimeError, ValueError) as exc:
        return _error(f"chat travel failed: {exc}", as_json=as_json)

    commands: queue.Queue[str] = queue.Queue()
    active_lock = threading.Lock()
    active_route_stop: EventEmergencyStop | None = None

    def cancel_active_route() -> None:
        with active_lock:
            if active_route_stop is not None:
                active_route_stop.trip()

    def submit_command(command: str) -> None:
        commands.put(command)

    try:
        with (
            WindowsHotkeyEmergencyStop() as service_stop,
            WindowsGoChatCommandListener(
                guard,
                on_command=submit_command,
                on_interaction=cancel_active_route,
            ),
        ):
            stop_adapter = ClientInputAdapter(
                DecisionInputCompiler(client_profile, StaticBindingPointResolver()),
                GuardedInputExecutor(
                    guard=guard,
                    backend=PyAutoGuiBackend(),
                    stop_signal=service_stop,
                ),
            )
            stop_sequence = 0
            _print_go_listener_event("listening", as_json=as_json)
            while not service_stop.is_set():
                try:
                    command = commands.get(timeout=0.1)
                except queue.Empty:
                    continue

                normalized = command.strip().casefold()
                if normalized == "/stop":
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
                if normalized == "/go":
                    lt = None
                    lg = None
                    radius = None
                else:
                    try:
                        plan = parse_go_command(command)
                    except ValueError as exc:
                        _print_go_listener_event(
                            "rejected",
                            as_json=as_json,
                            command=command,
                            reason=str(exc),
                        )
                        continue
                    destination = plan.destinations[0]
                    lt = destination.lt
                    lg = destination.lg
                    radius = destination.arrival_radius

                route_stop = EventEmergencyStop()
                with active_lock:
                    active_route_stop = route_stop
                try:
                    _print_go_listener_event(
                        "accepted",
                        as_json=as_json,
                        command=command,
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
                    )
                finally:
                    with active_lock:
                        if active_route_stop is route_stop:
                            active_route_stop = None
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"chat travel failed: {exc}", as_json=as_json)

    _print_go_listener_event("stopped", as_json=as_json)
    return 0


def _print_go_listener_event(
    event: str,
    *,
    as_json: bool,
    command: str | None = None,
    reason: str | None = None,
) -> None:
    if as_json:
        payload = {"ok": event != "rejected", "event": event}
        if command is not None:
            payload["command"] = command
        if reason is not None:
            payload["reason"] = reason
        print(json.dumps(payload, sort_keys=True), flush=True)
        return
    if event == "listening":
        print("Listening for foreground Shadowbane travel commands (/go, /stop).", flush=True)
    elif event == "stopped":
        print("Stopped listening for Shadowbane travel commands.", flush=True)
    elif event == "accepted":
        print(f"Accepted chat command: {command}", flush=True)
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
) -> None:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            guard.require_target()
            return
        except WindowGuardError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.1, remaining))


def _error(message: str, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    else:
        print(message, file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
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
    if arguments.command == "client" and arguments.client_command == "advise-irekei-proc":
        return _advise_irekei_proc(
            arguments.progression_profile,
            arguments.training_profile,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "run-pve":
        return _run_pve(
            client_profile_path=arguments.client_profile,
            combat_log_path=arguments.combat_log,
            hotbar_config_path=arguments.hotbar_config,
            native_health_profile_path=arguments.native_health_profile,
            native_vitals_profile_path=arguments.native_vitals_profile,
            native_position_profile_path=arguments.native_position_profile,
            native_target_position_profile_path=arguments.native_target_position_profile,
            max_kills=arguments.max_kills,
            max_seconds=arguments.max_seconds,
            wait_for_client_seconds=arguments.wait_for_client_seconds,
            poll_ms=arguments.poll_ms,
            policy=arguments.policy,
            live=arguments.live,
            as_json=arguments.json,
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
        )
    if arguments.command == "client" and arguments.client_command == "listen-go":
        return _listen_for_go_commands(
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
        )
    raise RuntimeError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
