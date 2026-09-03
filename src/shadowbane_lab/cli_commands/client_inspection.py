"""Inspection client command implementations."""

from __future__ import annotations

import json
import ntpath
import sys
import time
from pathlib import Path

from shadowbane_lab.client_action import (
    ClientActionEvidenceError,
    ClientActionRunner,
    WorldMapDestinationClickAction,
    save_client_action_evidence,
)
from shadowbane_lab.client_extension import (
    open_windows_extension_event_consumer,
)
from shadowbane_lab.client_input import (
    ArcaneHotbarLoadError,
    ArcaneHotkeyLoadError,
    CalibrationLoadError,
    ForegroundWindowGuard,
    GuardedInputExecutor,
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
    NativePlayerPositionError,
    NativePlayerProgressionCoreError,
    NativePlayerSnapshotError,
    NativePlayerSnapshotProfiles,
    NativePlayerTrainingError,
    NativePlayerVitalsError,
    NativePositionProfileLoadError,
    NativeProgressionCoreProfileLoadError,
    NativeRunegateRegistryError,
    NativeRunegateRegistryProfileLoadError,
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
    load_bundled_native_player_snapshot_profiles,
    load_bundled_native_position_profile,
    load_bundled_native_progression_core_profile,
    load_bundled_native_runegate_registry_profile,
    load_bundled_native_target_identity_profile,
    load_bundled_native_target_position_profile,
    load_bundled_native_training_profile,
    load_bundled_native_vitals_profile,
    load_bundled_native_world_map_profile,
    load_bundled_native_zone_profile,
    load_native_character_population_profile,
    load_native_group_profile,
    load_native_health_profile,
    load_native_position_profile,
    load_native_progression_core_profile,
    load_native_runegate_registry_profile,
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
    open_windows_native_player_position_reader,
    open_windows_native_player_progression_core_reader,
    open_windows_native_player_snapshot_reader,
    open_windows_native_player_training_reader,
    open_windows_native_player_vitals_reader,
    open_windows_native_runegate_registry_reader,
    open_windows_native_target_health_reader,
    open_windows_native_target_identity_reader,
    open_windows_native_target_position_reader,
    open_windows_native_vendor_dialog_tracer,
    open_windows_native_world_map_reader,
)
from shadowbane_lab.progression import (
    audit_proc_assassin_training,
    irekei_proc_assassin_roadmap,
    load_wonderbane_irekei_proc_profile,
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

from .character import _snapshot_payload
from .client_runtime import _PVE_TARGET_ACTIONS, _wait_for_guarded_client
from .common import _error


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
            print(f"{action['display_name']} [{action['native_action_code']}]: {rendered}")
    return 0


def _inspect_active_character_config(*, process_id: int | None, as_json: bool) -> int:
    from shadowbane_lab.client_input.character_config import open_active_character_config

    try:
        with open_active_character_config(process_id=process_id) as session:
            table = load_arcane_hotbar(session.binding.config_path)
            session.require_current()
            payload = {
                "ok": True,
                **session.binding.as_dict(),
                "current_set_index": table.current_set_index,
                "active_slots": [
                    {"key": slot.activation_key, "power": slot.power_name}
                    for slot in table.current_set.slots if slot.occupied
                ],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"active profile inspection failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Character: {payload['character_name']} ({payload['server_name']})")
        print(f"Profile: {payload['config_path']}")
        for slot in payload["active_slots"]:
            print(f"{slot['key'].upper()}: {slot['power']}")
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


def _observe_native_snapshot(
    progression_profile_path: Path | None,
    training_profile_path: Path | None,
    vitals_profile_path: Path | None,
    *,
    process_id: int | None,
    as_json: bool,
) -> int:
    try:
        bundled = load_bundled_native_player_snapshot_profiles()
        profiles = NativePlayerSnapshotProfiles(
            progression=(
                load_native_progression_core_profile(progression_profile_path)
                if progression_profile_path is not None
                else bundled.progression
            ),
            training=(
                load_native_training_profile(training_profile_path)
                if training_profile_path is not None
                else bundled.training
            ),
            vitals=(
                load_native_vitals_profile(vitals_profile_path)
                if vitals_profile_path is not None
                else bundled.vitals
            ),
        )
        with open_windows_native_player_snapshot_reader(
            profiles,
            process_id=process_id,
        ) as reader:
            snapshot = reader.observe()
    except (
        NativePlayerProgressionCoreError,
        NativePlayerSnapshotError,
        NativePlayerTrainingError,
        NativePlayerVitalsError,
        NativeProgressionCoreProfileLoadError,
        NativeTrainingProfileLoadError,
        NativeVitalsProfileLoadError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"native player snapshot failed: {exc}", as_json=as_json)
    payload = snapshot.as_dict()
    if as_json:
        print(json.dumps(payload, allow_nan=False, sort_keys=True))
    else:
        identity = snapshot.exact_process_identity
        print(f"Process: {identity[0]} created {identity[1]}")
        print(f"Snapshot: {snapshot.snapshot_token}")
        print(f"Captured: {payload['captured_at_utc']}")
        print(f"Level: {snapshot.progression.level}")
        print(f"Skills/Powers: {len(snapshot.training.skills)}/{len(snapshot.training.powers)}")
        print(
            f"Health: {snapshot.vitals.current_health:g}/"
            f"{snapshot.vitals.maximum_health:g}"
        )
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
