"""Command-line diagnostics used by the WonderBane VM bootstrap."""

from __future__ import annotations

import argparse
import json
import ntpath
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.client_input import (
    CalibrationLoadError,
    ClientInputAdapter,
    DecisionInputCompiler,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    WindowGuardError,
    WindowsForegroundWindowInspector,
    WindowsHotkeyEmergencyStop,
    WindowSnapshot,
    WindowsVisibleWindowInspector,
    load_calibration,
)
from shadowbane_lab.client_observation import (
    ClientTargetObserver,
    NativeCombatLogFormatError,
    NativeCombatLogReader,
    NativeHealthProfileLoadError,
    NativePlayerProgressionCoreError,
    NativePlayerTrainingError,
    NativePlayerVitalsError,
    NativeProgressionCoreProfileLoadError,
    NativeRuneAnnouncementWatcher,
    NativeTargetHealthError,
    NativeTrainingProfileLoadError,
    NativeVitalsProfileLoadError,
    ObservationCalibrationLoadError,
    ObservationDetectionError,
    PyAutoGuiFrameCapture,
    load_bundled_native_health_profile,
    load_bundled_native_progression_core_profile,
    load_bundled_native_training_profile,
    load_bundled_native_vitals_profile,
    load_native_health_profile,
    load_native_progression_core_profile,
    load_native_training_profile,
    load_native_vitals_profile,
    load_observation_calibration,
    open_windows_native_player_progression_core_reader,
    open_windows_native_player_training_reader,
    open_windows_native_player_vitals_reader,
    open_windows_native_target_health_reader,
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

    watch_rune = client_commands.add_parser(
        "watch-rune-announcement",
        help="passively wait for a rare-rune announcement in a native System-HUD log",
    )
    watch_rune.add_argument("path", type=Path)
    watch_rune.add_argument(
        "--target",
        action="append",
        default=[],
        help="case-insensitive required term; repeat to require multiple terms",
    )
    watch_rune.add_argument(
        "--timeout-seconds",
        type=float,
        help="stop cleanly after this duration; omit to watch until interrupted",
    )
    watch_rune.add_argument("--poll-seconds", type=float, default=0.5)
    watch_rune.add_argument(
        "--from-start",
        action="store_true",
        help="include existing records instead of watching only newly appended messages",
    )
    watch_rune.add_argument(
        "--no-bell",
        action="store_true",
        help="do not emit a terminal alert bell when a match arrives",
    )
    watch_rune.add_argument("--json", action="store_true", help="emit machine-readable JSON")

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
    run_pve.add_argument("--native-health-profile", type=Path)
    run_pve.add_argument("--native-vitals-profile", type=Path)
    run_pve.add_argument("--max-kills", type=int, default=1)
    run_pve.add_argument("--max-seconds", type=float, default=120.0)
    run_pve.add_argument("--wait-for-client-seconds", type=float, default=15.0)
    run_pve.add_argument("--poll-ms", type=int, default=100)
    run_pve.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    run_pve.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


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


def _watch_rune_announcement(
    path: Path,
    *,
    targets: Sequence[str],
    timeout_seconds: float | None,
    poll_seconds: float,
    from_start: bool,
    bell: bool,
    as_json: bool,
) -> int:
    if not path.is_file():
        return _error(f"native System-HUD log does not exist: {path}", as_json=as_json)
    try:
        reader = NativeCombatLogReader(path, start_at_end=not from_start)
        announcement = NativeRuneAnnouncementWatcher(reader).wait(
            terms=targets,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
    except (NativeCombatLogFormatError, OSError, UnicodeError, ValueError) as exc:
        return _error(f"rune announcement watch failed: {exc}", as_json=as_json)

    payload: dict[str, object] = {
        "ok": True,
        "path": str(path),
        "targets": list(targets),
        "matched": announcement is not None,
        "announcement": None if announcement is None else announcement.as_dict(),
    }
    if announcement is not None and bell:
        print("\a", end="", file=sys.stderr, flush=True)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    elif announcement is None:
        print("Rune announcement watch ended without a match.")
    else:
        print(f"({announcement.timestamp}) {announcement.message}")
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
    native_health_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    max_kills: int,
    max_seconds: float,
    wait_for_client_seconds: float,
    poll_ms: int,
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
    if not combat_log_path.is_file():
        return _error(f"combat log does not exist: {combat_log_path}", as_json=as_json)
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        mapped_actions = {mapping.action_key for mapping in client_profile.actions}
        required_actions = {intent.value for intent in PvEIntent}
        missing_actions = required_actions - mapped_actions
        if missing_actions:
            raise ValueError(
                f"client profile is missing PvE mappings: {', '.join(sorted(missing_actions))}"
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
        if health_profile.executable_sha256 != vitals_profile.executable_sha256:
            raise ValueError("native health and player-vitals profiles target different builds")
        inspector = WindowsForegroundWindowInspector()
        guard = ForegroundWindowGuard(client_profile, inspector)
        _wait_for_guarded_client(
            guard,
            wait_seconds=wait_for_client_seconds,
        )
        combat_reader = NativeCombatLogReader(combat_log_path, start_at_end=True)
        with (
            open_windows_native_target_health_reader(health_profile) as health_reader,
            open_windows_native_player_vitals_reader(vitals_profile) as player_vitals_reader,
            WindowsHotkeyEmergencyStop() as stop_signal,
        ):
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
                controller=PvEController(
                    PvEControllerConfig(
                        maximum_kills=max_kills,
                        maximum_session_ms=round(max_seconds * 1000),
                    )
                ),
                health_reader=health_reader,
                player_vitals_reader=player_vitals_reader,
                combat_log_reader=combat_reader,
                dispatcher=ClientPvEIntentDispatcher(adapter),
                stop_signal=stop_signal,
                poll_interval_ms=poll_ms,
            ).run()
    except (
        CalibrationLoadError,
        NativeHealthProfileLoadError,
        NativePlayerVitalsError,
        NativeTargetHealthError,
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
        "ok": result.final_phase.value == "complete",
        "final_phase": result.final_phase.value,
        "terminal_reason": result.terminal_reason,
        "kills": result.kills,
        "steps": len(result.trace),
        "dispatched": dispatched,
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"PvE phase: {result.final_phase.value}")
        print(f"Reason: {result.terminal_reason}")
        print(f"Kills: {result.kills}")
        print(f"Guarded inputs: {len(dispatched)}")
    return 0 if payload["ok"] else 2


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
    if arguments.command == "client" and arguments.client_command == "watch-rune-announcement":
        return _watch_rune_announcement(
            arguments.path,
            targets=arguments.target,
            timeout_seconds=arguments.timeout_seconds,
            poll_seconds=arguments.poll_seconds,
            from_start=arguments.from_start,
            bell=not arguments.no_bell,
            as_json=arguments.json,
        )
    if arguments.command == "client" and arguments.client_command == "observe-native-target":
        return _observe_native_target(arguments.profile, as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "observe-native-player":
        return _observe_native_player(arguments.profile, as_json=arguments.json)
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
            native_health_profile_path=arguments.native_health_profile,
            native_vitals_profile_path=arguments.native_vitals_profile,
            max_kills=arguments.max_kills,
            max_seconds=arguments.max_seconds,
            wait_for_client_seconds=arguments.wait_for_client_seconds,
            poll_ms=arguments.poll_ms,
            live=arguments.live,
            as_json=arguments.json,
        )
    raise RuntimeError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
