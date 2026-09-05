"""Multi-client manager command implementations."""

from __future__ import annotations

import json
import ntpath
import os
import secrets
import sys
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.client_extension import (
    ExtensionHeartbeatStatusProvider,
    load_patch_manifest,
)
from shadowbane_lab.client_input import (
    ClientInputAdapter,
    DecisionInputCompiler,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    StopSignal,
    WindowsForegroundWindowInspector,
    WindowsVisibleWindowInspector,
    load_calibration,
)
from shadowbane_lab.manager import (
    ClientLifecycleSupervisor,
    ClientRegistrySnapshot,
    ClientWindowRegistry,
    DashboardServer,
    ExactClientWorkerBinding,
    ExactClientWorkerRuntime,
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
    expand_manager_slots,
    load_manager_manifest,
    provision_isolated_client_runtimes,
    recover_manager_bindings,
    replace_manager_manifest,
    retarget_manager_clients,
)
from shadowbane_lab.travel import (
    load_learned_navigation_map,
    save_learned_navigation_map,
)

from .client_listener import _new_chat_pve_evidence_path
from .client_pve import _run_pve
from .client_travel import _run_travel
from .common import _error


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
        if any(client.window_tile is None for client in current.clients):
            raise ValueError(
                "tileless isolated runtime slots have fixed capacity; use manager "
                "provision-runtimes to change their count"
            )
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
        if len(current.clients) != 1:
            raise ValueError(
                "configure-build cannot point multiple slots at one mutable client tree; "
                "use manager provision-runtimes"
            )
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


def _provision_manager_runtimes(
    manifest_path: Path,
    *,
    frozen_directory: Path,
    deployment_directory: Path,
    patch_manifest_path: Path,
    extension_artifact: Path,
    deployment_id: str,
    slot_count: int | None,
    executable_name: str,
    resolution_width: int,
    resolution_height: int,
    apply: bool,
    as_json: bool,
) -> int:
    if not apply:
        return _error(
            "runtime provisioning creates client trees and replaces the manager manifest; "
            "pass --apply to confirm",
            as_json=as_json,
        )
    try:
        patch_manifest = load_patch_manifest(patch_manifest_path)
        result = provision_isolated_client_runtimes(
            manifest_path,
            frozen_directory,
            deployment_directory,
            patch_manifest,
            extension_artifact,
            deployment_id=deployment_id,
            slot_count=slot_count,
            executable_name=executable_name,
            resolution_width=resolution_width,
            resolution_height=resolution_height,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"manager runtime provisioning failed: {exc}", as_json=as_json)

    payload = result.as_dict()
    payload["ok"] = True
    payload["restart_required"] = True
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Provisioned {len(result.slots)} isolated WonderBane runtimes.")
        print(f"Deployment: {result.deployment_directory}")
        print(f"Manifest: {result.manager_manifest_path}")
        print(f"Backup: {result.manager_backup_path}")
        print("Restart the WonderBane Control Center to load the isolated runtimes.")
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


def _load_or_create_dashboard_token(path: Path) -> str:
    token_path = path.resolve(strict=False)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    def read_existing() -> str:
        if token_path.is_symlink() or not token_path.is_file():
            raise RuntimeError(
                f"dashboard authorization token must be a regular file: {token_path}"
            )
        try:
            return token_path.read_text(encoding="ascii").strip()
        except UnicodeError as exc:
            raise RuntimeError("dashboard authorization token must be ASCII") from exc

    if token_path.exists() or token_path.is_symlink():
        return read_existing()

    generated = secrets.token_urlsafe(32)
    try:
        with token_path.open("x", encoding="ascii", newline="\n") as destination:
            destination.write(generated + "\n")
            destination.flush()
            os.fsync(destination.fileno())
    except FileExistsError:
        return read_existing()
    return generated


def _run_manager_app(
    manifest_path: Path,
    *,
    port: int,
    launch_timeout_seconds: float,
    poll_ms: int,
    worker_state_directory: Path | None,
    pid_file: Path | None,
    authorization_token_file: Path | None,
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
        dashboard_token_path = (
            manager_state_root / "dashboard.token"
            if authorization_token_file is None
            else authorization_token_file
        )
        dashboard_token = _load_or_create_dashboard_token(dashboard_token_path)
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
            capacity_provisioner=IsolatedRuntimeCapacityProvisioner(manifest_path),
        )
        application.status()
        server = DashboardServer(
            application,
            port=port,
            authorization_token=dashboard_token,
        )
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
                        application.supervise()
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
    worker_id: str | None = None,
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
            worker_id=worker_id,
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
        if operation.kind is WorkerOperationKind.CANCEL:
            return WorkerOperationExecution(
                WorkerOperationState.SUCCEEDED,
                "in-flight automation cancellation acknowledged without client input",
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
        self._pve_evidence_directory.mkdir(parents=True, exist_ok=True)
        evidence_output = _new_chat_pve_evidence_path(self._pve_evidence_directory)
        result = _run_pve(
            client_profile_path=self._pve_client_profile_path,
            combat_log_path=None,
            hotbar_config_path=self._pve_hotbar_config_path,
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
