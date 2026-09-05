"""Fail-closed lifecycle supervision for locally discovered game clients.

The supervisor owns manager bindings, not game processes.  Pausing a binding only
disables manager dispatch, and closing a binding is always a graceful window-close
request delegated to an injected controller.
"""

from __future__ import annotations

import ntpath
import os
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite
from typing import Protocol

from shadowbane_lab.client_input import VisibleWindowInspector

from .manifest import ManagedClientConfig
from .model import ClientInstanceSnapshot, ClientRegistrySnapshot
from .registry import ClientWindowRegistry
from .window_control import WindowRectangle


class SupervisorError(RuntimeError):
    """Base class for lifecycle-supervisor failures."""


class UnverifiedLaunchError(SupervisorError):
    """A created process remains owned by the launcher but lacks a verified lifetime."""

    def __init__(self, process_id: int) -> None:
        self.process_id = process_id
        super().__init__(
            f"launched process PID {process_id} could not be verified; "
            "explicit attach retries verification without launching again"
        )


class RegistryContractError(SupervisorError):
    """Raised when an injected registry violates the requested filter contract."""


class NoMatchingClientError(SupervisorError):
    """Raised when no safe client satisfies an attach request."""


class AmbiguousClientError(SupervisorError):
    """Raised when an attach or launch produces more than one possible client."""


class UnsafeClientIdentityError(SupervisorError):
    """Raised when matching windows include incomplete attach identities."""


class DuplicateManagedClientError(SupervisorError):
    """Raised when one immutable client identity would be managed twice."""


class StaleManagedClientError(SupervisorError):
    """Raised when a binding no longer resolves to its immutable client identity."""


class UnknownManagedClientError(SupervisorError):
    """Raised when an operation names a binding the supervisor does not own."""


class InvalidLifecycleTransitionError(SupervisorError):
    """Raised when an operation is unsafe in the binding's current state."""


class LaunchTimeoutError(NoMatchingClientError):
    """Raised when a launch does not produce exactly one new client in time."""


class WindowControllerUnavailableError(SupervisorError):
    """Raised when a requested window operation has no configured controller."""


class UnownedLaunchBaselineError(SupervisorError):
    """Raised when launch baseline contains a matching client not owned here."""


class UnprovenLaunchProvenanceError(SupervisorError):
    """Raised when a new matching client cannot be tied to the reviewed launch."""


class ManagedClientState(StrEnum):
    ATTACHED = "attached"
    PAUSED = "paused"
    CLOSE_REQUESTED = "close_requested"
    STALE = "stale"
    EXITED = "exited"
    DETACHED = "detached"


class LaunchProvenance(StrEnum):
    """How a manager-launched client was proven to descend from its launch."""

    DIRECT_PROCESS = "direct_process"
    DESCENDANT_PROCESS = "descendant_process"


def _require_canonical_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if value != value.strip() or "\0" in value:
        raise ValueError(f"{field_name} must be canonical and must not contain NUL characters")


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _finite_non_negative(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def _normalized_windows_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(ntpath.abspath(value))).casefold()


@dataclass(frozen=True, slots=True)
class ClientInstanceSelector:
    """Exact local-node filter used for every registry observation of a binding."""

    node_id: str
    executable_names: tuple[str, ...]
    process_directory: str

    def __post_init__(self) -> None:
        _require_canonical_text(self.node_id, "node_id")
        if not isinstance(self.executable_names, tuple) or not self.executable_names:
            raise ValueError("executable_names must be a non-empty tuple")
        normalized_names: list[str] = []
        for executable_name in self.executable_names:
            _require_canonical_text(executable_name, "executable_names item")
            if ntpath.basename(executable_name) != executable_name:
                raise ValueError("executable_names must contain file names, not paths")
            normalized_names.append(executable_name.casefold())
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("executable_names must be unique ignoring case")
        _require_canonical_text(self.process_directory, "process_directory")
        if not ntpath.isabs(self.process_directory):
            raise ValueError("process_directory must be an absolute Windows path")


@dataclass(frozen=True, slots=True)
class ReviewedLaunchCommand:
    """An already-reviewed argv command that is never interpreted by a shell."""

    argv: tuple[str, ...]
    working_directory: str | None = None
    environment: tuple[tuple[str, str | None], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.argv, tuple) or not self.argv:
            raise ValueError("argv must be a non-empty tuple")
        for argument in self.argv:
            if (
                not isinstance(argument, str)
                or not argument
                or "\0" in argument
                or "\r" in argument
                or "\n" in argument
            ):
                raise ValueError(
                    "argv must contain non-empty strings without NUL or line-break characters"
                )
        if not ntpath.isabs(self.argv[0]):
            raise ValueError("argv executable must be an absolute Windows path")
        if self.working_directory is not None:
            _require_canonical_text(self.working_directory, "working_directory")
            if not ntpath.isabs(self.working_directory):
                raise ValueError("working_directory must be an absolute Windows path")
        if not isinstance(self.environment, tuple):
            raise ValueError("environment must be an immutable tuple")
        names: list[str] = []
        for item in self.environment:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
                or any(character in item[0] for character in "=\0\r\n")
                or not (item[1] is None or isinstance(item[1], str))
                or (
                    isinstance(item[1], str)
                    and ("\0" in item[1] or "\r" in item[1] or "\n" in item[1])
                )
            ):
                raise ValueError(
                    "environment must contain name and string-or-None pairs "
                    "without control characters"
                )
            names.append(item[0])
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("environment names must be unique and sorted")


def selector_from_config(
    node_id: str,
    config: ManagedClientConfig,
) -> ClientInstanceSelector:
    """Translate one manifest slot into the supervisor's exact registry filter."""

    if not isinstance(config, ManagedClientConfig):
        raise ValueError("config must be ManagedClientConfig")
    return ClientInstanceSelector(
        node_id=node_id,
        executable_names=config.expected_executable_names,
        process_directory=str(config.expected_process_directory),
    )


def launch_command_from_config(config: ManagedClientConfig) -> ReviewedLaunchCommand:
    """Translate a validated shell-free manifest command into a launch request."""

    if not isinstance(config, ManagedClientConfig):
        raise ValueError("config must be ManagedClientConfig")
    return ReviewedLaunchCommand(
        argv=config.launch.command,
        working_directory=str(config.launch.working_directory),
        environment=config.launch.environment,
    )


def window_rectangle_from_config(config: ManagedClientConfig) -> WindowRectangle | None:
    """Translate an optional manifest tile into the guarded Win32 rectangle type."""

    if not isinstance(config, ManagedClientConfig):
        raise ValueError("config must be ManagedClientConfig")
    tile = config.window_tile
    if tile is None:
        return None
    return WindowRectangle(
        left=tile.left,
        top=tile.top,
        width=tile.width,
        height=tile.height,
    )


@dataclass(frozen=True, slots=True)
class ProcessLifetimeSnapshot:
    """One verified, currently running Windows process lifetime."""

    process_id: int
    process_started_at_100ns: int
    parent_process_id: int | None = None

    def __post_init__(self) -> None:
        _positive_integer(self.process_id, "process_id")
        _positive_integer(self.process_started_at_100ns, "process_started_at_100ns")
        if self.parent_process_id is not None:
            _positive_integer(self.parent_process_id, "parent_process_id")
            if self.parent_process_id == self.process_id:
                raise ValueError("a process cannot be its own parent")


class ProcessLifetimeInspector(Protocol):
    """Resolve only currently running processes to exact PID/creation-time identities."""

    def inspect(self, process_id: int) -> ProcessLifetimeSnapshot | None: ...


@dataclass(frozen=True, slots=True)
class LaunchReceipt:
    """Exact lifetime identity of the reviewed launch's root process.

    A registered game window may bind only when its process is this exact lifetime
    or a verified live descendant of it.
    """

    process_id: int
    process_started_at_100ns: int

    def __post_init__(self) -> None:
        _positive_integer(self.process_id, "process_id")
        _positive_integer(self.process_started_at_100ns, "process_started_at_100ns")


@dataclass(frozen=True, slots=True)
class ManagedClientSnapshot:
    """Immutable operator-facing status for one manager-owned binding."""

    selector: ClientInstanceSelector
    client: ClientInstanceSnapshot
    state: ManagedClientState
    dispatch_enabled: bool
    launched_by_manager: bool
    launcher_process_id: int | None
    launcher_process_started_at_100ns: int | None
    launch_provenance: LaunchProvenance | None
    attached_at: float
    last_verified_at: float
    status_detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.selector, ClientInstanceSelector):
            raise ValueError("selector must be ClientInstanceSelector")
        if not isinstance(self.client, ClientInstanceSnapshot):
            raise ValueError("client must be ClientInstanceSnapshot")
        if not isinstance(self.state, ManagedClientState):
            raise ValueError("state must be ManagedClientState")
        if not isinstance(self.dispatch_enabled, bool):
            raise ValueError("dispatch_enabled must be a boolean")
        if self.dispatch_enabled != (self.state is ManagedClientState.ATTACHED):
            raise ValueError("dispatch is enabled only for attached clients")
        if not isinstance(self.launched_by_manager, bool):
            raise ValueError("launched_by_manager must be a boolean")
        if self.launcher_process_id is not None:
            _positive_integer(self.launcher_process_id, "launcher_process_id")
        if self.launcher_process_started_at_100ns is not None:
            _positive_integer(
                self.launcher_process_started_at_100ns,
                "launcher_process_started_at_100ns",
            )
        has_launch_identity = (
            self.launcher_process_id is not None
            and self.launcher_process_started_at_100ns is not None
            and self.launch_provenance is not None
        )
        if self.launched_by_manager != has_launch_identity:
            raise ValueError(
                "manager-launched clients require complete launcher identity and provenance"
            )
        if self.launch_provenance is not None and not isinstance(
            self.launch_provenance, LaunchProvenance
        ):
            raise ValueError("launch_provenance must be LaunchProvenance or None")
        if not self.launched_by_manager and (
            self.launcher_process_id is not None
            or self.launcher_process_started_at_100ns is not None
            or self.launch_provenance is not None
        ):
            raise ValueError("externally attached clients must not carry launch provenance")
        _finite_non_negative(self.attached_at, "attached_at")
        _finite_non_negative(self.last_verified_at, "last_verified_at")
        if self.last_verified_at < self.attached_at:
            raise ValueError("last_verified_at must not precede attached_at")
        if self.status_detail is not None and (
            not isinstance(self.status_detail, str) or not self.status_detail.strip()
        ):
            raise ValueError("status_detail must be a non-empty string or None")

    @property
    def instance_id(self) -> str:
        return self.client.instance_id


class ClientRegistrySource(Protocol):
    def inspect(self, selector: ClientInstanceSelector) -> ClientRegistrySnapshot: ...


class ProcessLauncher(Protocol):
    def launch(self, command: ReviewedLaunchCommand) -> LaunchReceipt: ...


class MonotonicClock(Protocol):
    def now(self) -> float: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class WindowLifecycleController(Protocol):
    def tile(
        self,
        expected: ClientInstanceSnapshot,
        rectangle: WindowRectangle,
    ) -> ClientInstanceSnapshot: ...

    def request_graceful_close(
        self,
        expected: ClientInstanceSnapshot,
    ) -> ClientInstanceSnapshot: ...


class VisibleWindowRegistrySource:
    """Production registry adapter that applies the selector on every inspection."""

    def __init__(self, inspector: VisibleWindowInspector) -> None:
        if not isinstance(inspector, VisibleWindowInspector):
            raise ValueError("inspector must implement VisibleWindowInspector")
        self._inspector = inspector

    def inspect(self, selector: ClientInstanceSelector) -> ClientRegistrySnapshot:
        return ClientWindowRegistry(
            self._inspector,
            node_id=selector.node_id,
            executable_names=selector.executable_names,
            process_directory=selector.process_directory,
        ).inspect()


class Win32ProcessLifetimeInspector:
    """Read exact running-process lifetimes and live parent links from Windows."""

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _SYNCHRONIZE = 0x00100000
    _TH32CS_SNAPPROCESS = 0x00000002
    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_TIMEOUT = 0x00000102
    _INVALID_HANDLE_VALUE = -1

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Win32 process-lifetime inspection requires Windows")

        import ctypes
        from ctypes import wintypes

        class ProcessEntry32W(ctypes.Structure):
            _fields_ = (
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            )

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry32W),
        )
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry32W),
        )
        kernel32.Process32NextW.restype = wintypes.BOOL
        self._ctypes = ctypes
        self._wintypes = wintypes
        self._kernel32 = kernel32
        self._process_entry_type = ProcessEntry32W

    def inspect(self, process_id: int) -> ProcessLifetimeSnapshot | None:
        _positive_integer(process_id, "process_id")
        self._ctypes.set_last_error(0)
        handle = self._kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION | self._SYNCHRONIZE,
            False,
            process_id,
        )
        if not handle:
            error = self._ctypes.get_last_error()
            if error in {87, 1168}:  # invalid parameter / not found
                return None
            raise OSError(error, f"OpenProcess failed for PID {process_id}")
        try:
            wait_result = self._kernel32.WaitForSingleObject(handle, 0)
            if wait_result == self._WAIT_OBJECT_0:
                return None
            if wait_result != self._WAIT_TIMEOUT:
                raise OSError(
                    self._ctypes.get_last_error(),
                    f"WaitForSingleObject failed for PID {process_id}",
                )
            creation = self._wintypes.FILETIME()
            exit_time = self._wintypes.FILETIME()
            kernel_time = self._wintypes.FILETIME()
            user_time = self._wintypes.FILETIME()
            self._ctypes.set_last_error(0)
            if not self._kernel32.GetProcessTimes(
                handle,
                self._ctypes.byref(creation),
                self._ctypes.byref(exit_time),
                self._ctypes.byref(kernel_time),
                self._ctypes.byref(user_time),
            ):
                raise OSError(
                    self._ctypes.get_last_error(),
                    f"GetProcessTimes failed for PID {process_id}",
                )
            started_at = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            if started_at <= 0:
                raise OSError(
                    f"GetProcessTimes returned invalid creation time for PID {process_id}"
                )
            return ProcessLifetimeSnapshot(
                process_id=process_id,
                process_started_at_100ns=started_at,
                parent_process_id=self._parent_process_id(process_id),
            )
        finally:
            self._kernel32.CloseHandle(handle)

    def _parent_process_id(self, process_id: int) -> int | None:
        self._ctypes.set_last_error(0)
        snapshot = self._kernel32.CreateToolhelp32Snapshot(self._TH32CS_SNAPPROCESS, 0)
        invalid_handle = self._ctypes.c_void_p(self._INVALID_HANDLE_VALUE).value
        if not snapshot or snapshot == invalid_handle:
            raise OSError(self._ctypes.get_last_error(), "process snapshot failed")
        try:
            entry = self._process_entry_type()
            entry.dwSize = self._ctypes.sizeof(entry)
            self._ctypes.set_last_error(0)
            if not self._kernel32.Process32FirstW(snapshot, self._ctypes.byref(entry)):
                raise OSError(self._ctypes.get_last_error(), "Process32FirstW failed")
            while True:
                if entry.th32ProcessID == process_id:
                    parent = int(entry.th32ParentProcessID)
                    return parent if parent > 0 and parent != process_id else None
                self._ctypes.set_last_error(0)
                if not self._kernel32.Process32NextW(snapshot, self._ctypes.byref(entry)):
                    error = self._ctypes.get_last_error()
                    if error == 18:  # ERROR_NO_MORE_FILES
                        return None
                    raise OSError(error, "Process32NextW failed")
        finally:
            self._kernel32.CloseHandle(snapshot)


class SubprocessLauncher:
    """Launch reviewed argv commands directly with ``shell=False``."""

    def __init__(self, process_inspector: ProcessLifetimeInspector | None = None) -> None:
        self._process_inspector = (
            process_inspector if process_inspector is not None else Win32ProcessLifetimeInspector()
        )
        if not callable(getattr(self._process_inspector, "inspect", None)):
            raise ValueError("process_inspector must provide inspect(process_id)")
        self._children: dict[int, subprocess.Popen[bytes]] = {}
        self._children_lock = threading.Lock()

    def launch(self, command: ReviewedLaunchCommand) -> LaunchReceipt:
        if not isinstance(command, ReviewedLaunchCommand):
            raise ValueError("command must be ReviewedLaunchCommand")
        self._reap_finished_children()
        launch_environment = None
        if command.environment:
            launch_environment = os.environ.copy()
            for name, value in command.environment:
                if value is None:
                    launch_environment.pop(name, None)
                else:
                    launch_environment[name] = value
        process = subprocess.Popen(
            command.argv,
            cwd=command.working_directory,
            shell=False,
            **({} if launch_environment is None else {"env": launch_environment}),
        )
        with self._children_lock:
            self._children[process.pid] = process
        return self.recover(process.pid)

    def recover(self, process_id: int) -> LaunchReceipt:
        """Verify only a retained Popen lifetime, never a numeric PID alone."""
        with self._children_lock:
            process = self._children.get(process_id)
        if process is None or process.poll() is not None:
            raise UnverifiedLaunchError(process_id)
        try:
            lifetime = self._process_inspector.inspect(process_id)
        except (OSError, RuntimeError, ValueError) as exc:
            raise UnverifiedLaunchError(process_id) from exc
        if lifetime is None or lifetime.process_id != process_id or process.poll() is not None:
            raise UnverifiedLaunchError(process_id)
        return LaunchReceipt(lifetime.process_id, lifetime.process_started_at_100ns)

    def _reap_finished_children(self) -> None:
        with self._children_lock:
            self._children = {
                process_id: process
                for process_id, process in self._children.items()
                if process.poll() is None
            }


class SystemMonotonicClock:
    def now(self) -> float:
        return time.monotonic()


class SystemSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(slots=True)
class _ManagedBinding:
    selector: ClientInstanceSelector
    client: ClientInstanceSnapshot
    state: ManagedClientState
    dispatch_enabled: bool
    launched_by_manager: bool
    launcher_process_id: int | None
    launcher_process_started_at_100ns: int | None
    launch_provenance: LaunchProvenance | None
    attached_at: float
    last_verified_at: float
    status_detail: str | None = None

    def snapshot(self) -> ManagedClientSnapshot:
        return ManagedClientSnapshot(
            selector=self.selector,
            client=self.client,
            state=self.state,
            dispatch_enabled=self.dispatch_enabled,
            launched_by_manager=self.launched_by_manager,
            launcher_process_id=self.launcher_process_id,
            launcher_process_started_at_100ns=self.launcher_process_started_at_100ns,
            launch_provenance=self.launch_provenance,
            attached_at=self.attached_at,
            last_verified_at=self.last_verified_at,
            status_detail=self.status_detail,
        )


class ClientLifecycleSupervisor:
    """Own lifecycle bindings for exact, immutable client identities on one local node."""

    def __init__(
        self,
        registry: ClientRegistrySource,
        *,
        launcher: ProcessLauncher,
        clock: MonotonicClock | None = None,
        sleeper: Sleeper | None = None,
        window_controller: WindowLifecycleController | None = None,
        process_inspector: ProcessLifetimeInspector | None = None,
    ) -> None:
        if not hasattr(registry, "inspect"):
            raise ValueError("registry must provide inspect(selector)")
        if not hasattr(launcher, "launch"):
            raise ValueError("launcher must provide launch(command)")
        self._registry = registry
        self._launcher = launcher
        self._clock = clock if clock is not None else SystemMonotonicClock()
        self._sleeper = sleeper if sleeper is not None else SystemSleeper()
        self._window_controller = window_controller
        self._process_inspector = (
            process_inspector if process_inspector is not None else Win32ProcessLifetimeInspector()
        )
        if not callable(getattr(self._process_inspector, "inspect", None)):
            raise ValueError("process_inspector must provide inspect(process_id)")
        self._bindings: dict[str, _ManagedBinding] = {}
        self._instance_locks: dict[str, threading.RLock] = {}
        self._pending_launches: dict[str, LaunchReceipt | UnverifiedLaunchError | None] = {}
        self._lock = threading.RLock()

    def attach(
        self,
        selector: ClientInstanceSelector,
        *,
        instance_id: str | None = None,
    ) -> ManagedClientSnapshot:
        """Attach to one client, requiring an exact ID when filters are ambiguous."""

        snapshot = self._read_safe_snapshot(selector)
        if not snapshot.clients:
            raise NoMatchingClientError("no matching pre-existing client was found")
        if instance_id is not None:
            _require_canonical_text(instance_id, "instance_id")
            matches = tuple(
                client for client in snapshot.clients if client.instance_id == instance_id
            )
        else:
            matches = snapshot.clients
        if not matches:
            raise NoMatchingClientError(
                f"registered client {instance_id!r} did not match the selector"
            )
        if len(matches) != 1:
            raise AmbiguousClientError("select one exact instance_id for explicit attach")
        client = matches[0]
        key = repr(selector)
        with self._lock:
            pending = self._pending_launches.get(key)
        receipt = pending if isinstance(pending, LaunchReceipt) else None
        if isinstance(pending, UnverifiedLaunchError):
            recover = getattr(self._launcher, "recover", None)
            if not callable(recover):
                raise pending
            receipt = recover(pending.process_id)
        provenance = self._launch_provenance(client, receipt) if receipt is not None else None
        with self._lock:
            if self._pending_launches.get(key) is not pending:
                raise SupervisorError("launch recovery ownership changed during attachment")
            result = self._bind(
                selector,
                client,
                launch_receipt=receipt if provenance is not None else None,
                launch_provenance=provenance,
            )
            if provenance is not None:
                del self._pending_launches[key]
            return result

    def launch_and_attach(
        self,
        selector: ClientInstanceSelector,
        command: ReviewedLaunchCommand,
        *,
        timeout_seconds: float,
        poll_seconds: float = 0.5,
    ) -> ManagedClientSnapshot:
        """Launch once and bind only the single new immutable registry identity."""

        _finite_non_negative(timeout_seconds, "timeout_seconds")
        if (
            isinstance(poll_seconds, bool)
            or not isinstance(poll_seconds, (int, float))
            or not isfinite(poll_seconds)
            or poll_seconds <= 0
        ):
            raise ValueError("poll_seconds must be finite and positive")
        if not isinstance(command, ReviewedLaunchCommand):
            raise ValueError("command must be ReviewedLaunchCommand")

        key = repr(selector)
        with self._lock:
            if key in self._pending_launches:
                raise SupervisorError(
                    "a prior launch is pending or requires explicit attachment recovery"
                )
            self._pending_launches[key] = None
        try:
            baseline = self._read_safe_snapshot(selector)
            with self._lock:
                unowned_baseline = tuple(
                    client
                    for client in baseline.clients
                    if not self._binding_owns_exact_identity(client)
                )
                if unowned_baseline:
                    raise UnownedLaunchBaselineError(
                        "launch baseline contains matching client(s) not owned by this supervisor; "
                        "explicit attach is required: "
                        + ", ".join(client.instance_id for client in unowned_baseline)
                    )
                baseline_by_id = {client.instance_id: client for client in baseline.clients}
        except Exception:
            # No process has been created yet; this reservation is safe to release.
            with self._lock:
                del self._pending_launches[key]
            raise
        # Retain the reservation on uncertain launch/attachment failure. A receipt
        # records a process we created even when no usable window ever appears.
        try:
            receipt = self._launcher.launch(command)
        except UnverifiedLaunchError as exc:
            with self._lock:
                self._pending_launches[key] = exc
            raise
        except OSError:
            # Popen failure creates no child; SubprocessLauncher wraps all
            # post-creation observation failures as UnverifiedLaunchError.
            if isinstance(self._launcher, SubprocessLauncher):
                with self._lock:
                    del self._pending_launches[key]
            raise
        if not isinstance(receipt, LaunchReceipt):
            raise SupervisorError("launcher must return LaunchReceipt")

        with self._lock:
            self._pending_launches[key] = receipt
        deadline = self._now() + timeout_seconds
        while True:
            current = self._read_safe_snapshot(selector)
            current_by_id = {client.instance_id: client for client in current.clients}
            missing = tuple(sorted(set(baseline_by_id) - set(current_by_id)))
            if missing:
                raise StaleManagedClientError(
                    "baseline client identities disappeared during launch: " + ", ".join(missing)
                )
            for instance_id, baseline_client in baseline_by_id.items():
                if _immutable_identity(current_by_id[instance_id]) != _immutable_identity(
                    baseline_client
                ):
                    raise StaleManagedClientError(
                        f"baseline client identity changed during launch: {instance_id}"
                    )

            new_clients = tuple(
                client for client in current.clients if client.instance_id not in baseline_by_id
            )
            proven: list[tuple[ClientInstanceSnapshot, LaunchProvenance]] = []
            unproven: list[ClientInstanceSnapshot] = []
            for client in new_clients:
                provenance = self._launch_provenance(client, receipt)
                if provenance is None:
                    unproven.append(client)
                else:
                    proven.append((client, provenance))
            if unproven:
                raise UnprovenLaunchProvenanceError(
                    "new matching client(s) were not the reviewed launch process or a "
                    "verified live descendant; explicit attach is required: "
                    + ", ".join(client.instance_id for client in unproven)
                )
            if len(proven) > 1:
                raise AmbiguousClientError(
                    f"launch produced {len(proven)} provenance-matched clients"
                )
            if len(proven) == 1:
                client, provenance = proven[0]
                with self._lock:
                    self._reject_managed_duplicate(client)
                    result = self._bind(
                        selector,
                        client,
                        launch_receipt=receipt,
                        launch_provenance=provenance,
                    )
                    del self._pending_launches[key]
                    return result

            now = self._now()
            remaining = deadline - now
            if remaining <= 0:
                raise LaunchTimeoutError(
                    f"launch PID {receipt.process_id}/{receipt.process_started_at_100ns} "
                    "produced no new matching client before the timeout; "
                    "explicit attach can recover"
                )
            self._sleeper.sleep(min(float(poll_seconds), remaining))

    def _instance_lock(self, instance_id: str) -> threading.RLock:
        with self._lock:
            self._require_binding(instance_id)
            return self._instance_locks.setdefault(instance_id, threading.RLock())

    def _observe_binding(self, instance_id: str) -> _ManagedBinding:
        # Caller owns only this instance. Publish an observation atomically after
        # blocking registry/process inspection, and reject changed ownership.
        with self._lock:
            original = self._require_binding(instance_id)
            candidate = replace(original)
        observed = self._refresh_binding(candidate)
        with self._lock:
            if self._require_binding(instance_id) is not original:
                raise StaleManagedClientError("binding changed during observation")
            self._bindings[instance_id] = observed
            return observed

    def pause(self, instance_id: str) -> ManagedClientSnapshot:
        """Disable dispatch without suspending the operating-system process."""
        with self._instance_lock(instance_id), self._lock:
            binding = self._require_binding(instance_id)
            if binding.state in {ManagedClientState.STALE, ManagedClientState.EXITED}:
                raise StaleManagedClientError(binding.status_detail or "client binding is stale")
            if binding.state is ManagedClientState.CLOSE_REQUESTED:
                raise InvalidLifecycleTransitionError("cannot pause after close was requested")
            binding.state = ManagedClientState.PAUSED
            binding.dispatch_enabled = False
            binding.status_detail = None
            return binding.snapshot()

    def resume(self, instance_id: str) -> ManagedClientSnapshot:
        with self._instance_lock(instance_id):
            with self._lock:
                binding = self._require_binding(instance_id)
                if binding.state in {ManagedClientState.CLOSE_REQUESTED, ManagedClientState.EXITED}:
                    raise InvalidLifecycleTransitionError("cannot resume after close was requested")
            binding = self._observe_binding(instance_id)
            with self._lock:
                if binding.state in {ManagedClientState.STALE, ManagedClientState.EXITED}:
                    raise StaleManagedClientError(
                        binding.status_detail or "client binding is stale"
                    )
                binding.state = ManagedClientState.ATTACHED
                binding.dispatch_enabled = True
                binding.status_detail = None
                return binding.snapshot()

    def refresh(self, instance_id: str) -> ManagedClientSnapshot:
        with self._instance_lock(instance_id):
            binding = self._observe_binding(instance_id)
            with self._lock:
                return binding.snapshot()

    def dispatch_is_enabled(self, instance_id: str) -> bool:
        return self.refresh(instance_id).dispatch_enabled

    def status(self, instance_id: str) -> ManagedClientSnapshot:
        with self._lock:
            return self._require_binding(instance_id).snapshot()

    def snapshots(self) -> tuple[ManagedClientSnapshot, ...]:
        with self._lock:
            return tuple(self._bindings[key].snapshot() for key in sorted(self._bindings))

    def detach(self, instance_id: str) -> ManagedClientSnapshot:
        with self._instance_lock(instance_id), self._lock:
            binding = self._require_binding(instance_id)
            del self._bindings[instance_id]
            binding.state = ManagedClientState.DETACHED
            binding.dispatch_enabled = False
            binding.status_detail = "detached by manager"
            return binding.snapshot()

    def request_close(self, instance_id: str) -> ManagedClientSnapshot:
        """Reserve this lifetime, disable dispatch, then perform the verified close."""
        with self._instance_lock(instance_id):
            if self._window_controller is None:
                raise WindowControllerUnavailableError("no window controller is configured")
            with self._lock:
                if self._require_binding(instance_id).state in {
                    ManagedClientState.CLOSE_REQUESTED,
                    ManagedClientState.EXITED,
                }:
                    raise InvalidLifecycleTransitionError("close was already requested")
            binding = self._observe_binding(instance_id)
            with self._lock:
                if binding.state in {ManagedClientState.STALE, ManagedClientState.EXITED}:
                    raise StaleManagedClientError(
                        binding.status_detail or "client binding is stale"
                    )
                binding.state = ManagedClientState.PAUSED
                binding.dispatch_enabled = False
                binding.status_detail = "graceful close request pending"
                expected = binding.client
            try:
                current = self._window_controller.request_graceful_close(expected)
            except Exception as exc:
                with self._lock:
                    binding.status_detail = f"graceful close request failed: {exc}"
                raise SupervisorError(binding.status_detail) from exc
            with self._lock:
                if self._require_binding(instance_id) is not binding:
                    raise StaleManagedClientError("binding changed during window close")
                self._accept_window_result(binding, current)
                binding.state = ManagedClientState.CLOSE_REQUESTED
                binding.status_detail = "graceful close requested"
                return binding.snapshot()

    def tile(self, instance_id: str, rectangle: WindowRectangle) -> ManagedClientSnapshot:
        with self._instance_lock(instance_id):
            if self._window_controller is None:
                raise WindowControllerUnavailableError("no window controller is configured")
            if not isinstance(rectangle, WindowRectangle):
                raise ValueError("rectangle must be WindowRectangle")
            binding = self._observe_binding(instance_id)
            if binding.state in {ManagedClientState.STALE, ManagedClientState.EXITED}:
                raise StaleManagedClientError(binding.status_detail or "client binding is stale")
            if binding.state is ManagedClientState.CLOSE_REQUESTED:
                raise InvalidLifecycleTransitionError(
                    "cannot tile a client after close was requested"
                )
            try:
                current = self._window_controller.tile(binding.client, rectangle)
            except Exception as exc:
                raise SupervisorError(f"window tile failed: {exc}") from exc
            with self._lock:
                if self._require_binding(instance_id) is not binding:
                    raise StaleManagedClientError("binding changed during window tile")
                self._accept_window_result(binding, current)
                return binding.snapshot()

    def _bind(
        self,
        selector: ClientInstanceSelector,
        client: ClientInstanceSnapshot,
        *,
        launch_receipt: LaunchReceipt | None,
        launch_provenance: LaunchProvenance | None,
    ) -> ManagedClientSnapshot:
        if (launch_receipt is None) != (launch_provenance is None):
            raise SupervisorError("launch receipt and provenance must be recorded together")
        self._reject_managed_duplicate(client)
        now = self._now()
        binding = _ManagedBinding(
            selector=selector,
            client=client,
            state=ManagedClientState.ATTACHED,
            dispatch_enabled=True,
            launched_by_manager=launch_receipt is not None,
            launcher_process_id=(launch_receipt.process_id if launch_receipt is not None else None),
            launcher_process_started_at_100ns=(
                launch_receipt.process_started_at_100ns if launch_receipt is not None else None
            ),
            launch_provenance=launch_provenance,
            attached_at=now,
            last_verified_at=now,
        )
        self._bindings[client.instance_id] = binding
        return binding.snapshot()

    def _binding_owns_exact_identity(self, client: ClientInstanceSnapshot) -> bool:
        binding = self._bindings.get(client.instance_id)
        return binding is not None and _immutable_identity(binding.client) == _immutable_identity(
            client
        )

    def _launch_provenance(
        self,
        client: ClientInstanceSnapshot,
        receipt: LaunchReceipt,
    ) -> LaunchProvenance | None:
        launch_identity = (
            receipt.process_id,
            receipt.process_started_at_100ns,
        )
        client_identity = (
            client.process_id,
            client.process_started_at_100ns,
        )
        if client_identity == launch_identity:
            return LaunchProvenance.DIRECT_PROCESS

        try:
            current = self._process_inspector.inspect(client.process_id)
            if (
                current is None
                or (
                    current.process_id,
                    current.process_started_at_100ns,
                )
                != client_identity
            ):
                return None
            visited = {current.process_id}
            for _ in range(64):
                parent_process_id = current.parent_process_id
                if parent_process_id is None or parent_process_id in visited:
                    return None
                parent = self._process_inspector.inspect(parent_process_id)
                if parent is None or parent.process_id != parent_process_id:
                    return None
                if parent.process_started_at_100ns > current.process_started_at_100ns:
                    return None
                if (
                    parent.process_id,
                    parent.process_started_at_100ns,
                ) == launch_identity:
                    return LaunchProvenance.DESCENDANT_PROCESS
                visited.add(parent_process_id)
                current = parent
        except (OSError, RuntimeError, ValueError):
            return None
        return None

    def _read_safe_snapshot(self, selector: ClientInstanceSelector) -> ClientRegistrySnapshot:
        snapshot = self._read_snapshot(selector)
        if snapshot.rejected:
            raise UnsafeClientIdentityError(
                f"{len(snapshot.rejected)} matching window(s) lack complete identity"
            )
        return snapshot

    def _read_snapshot(self, selector: ClientInstanceSelector) -> ClientRegistrySnapshot:
        if not isinstance(selector, ClientInstanceSelector):
            raise ValueError("selector must be ClientInstanceSelector")
        snapshot = self._registry.inspect(selector)
        if not isinstance(snapshot, ClientRegistrySnapshot):
            raise RegistryContractError("registry must return ClientRegistrySnapshot")
        if snapshot.node_id != selector.node_id:
            raise RegistryContractError(
                f"registry returned node {snapshot.node_id!r} for selector {selector.node_id!r}"
            )
        seen_process_ids: set[int] = set()
        seen_window_handles: set[int] = set()
        for client in snapshot.clients:
            self._require_exact_match(selector, client)
            if client.process_id in seen_process_ids:
                raise RegistryContractError(
                    f"registry returned duplicate process ID {client.process_id}"
                )
            if client.window_handle in seen_window_handles:
                raise RegistryContractError(
                    f"registry returned duplicate window handle {client.window_handle}"
                )
            seen_process_ids.add(client.process_id)
            seen_window_handles.add(client.window_handle)
        return snapshot

    @staticmethod
    def _require_exact_match(
        selector: ClientInstanceSelector,
        client: ClientInstanceSnapshot,
    ) -> None:
        if client.node_id != selector.node_id:
            raise RegistryContractError("registry client belongs to the wrong node")
        allowed_names = {name.casefold() for name in selector.executable_names}
        if client.executable_name.casefold() not in allowed_names:
            raise RegistryContractError("registry client does not match the executable filter")
        if client.executable_path is None:
            raise RegistryContractError("registry client has no executable path")
        client_directory = ntpath.dirname(client.executable_path)
        if _normalized_windows_path(client_directory) != _normalized_windows_path(
            selector.process_directory
        ):
            raise RegistryContractError("registry client does not match the directory filter")

    def _reject_managed_duplicate(self, client: ClientInstanceSnapshot) -> None:
        if client.instance_id in self._bindings:
            raise DuplicateManagedClientError(f"client {client.instance_id} is already managed")
        for binding in self._bindings.values():
            managed = binding.client
            if managed.node_id != client.node_id:
                continue
            if managed.process_id == client.process_id:
                raise DuplicateManagedClientError(
                    f"process ID {client.process_id} is already managed"
                )
            if managed.window_handle == client.window_handle:
                raise DuplicateManagedClientError(
                    f"window handle {client.window_handle} is already managed"
                )

    def _refresh_binding(self, binding: _ManagedBinding) -> _ManagedBinding:
        if binding.state is ManagedClientState.EXITED:
            return binding
        try:
            snapshot = self._read_snapshot(binding.selector)
            matches = tuple(
                client
                for client in snapshot.clients
                if client.instance_id == binding.client.instance_id
            )
            if len(matches) != 1:
                return self._refresh_without_window(
                    binding,
                    (
                        "exact window identity is absent after graceful close request"
                        if binding.state is ManagedClientState.CLOSE_REQUESTED
                        else "immutable client identity is no longer present exactly once"
                    ),
                )
            current = matches[0]
            if _immutable_identity(current) != _immutable_identity(binding.client):
                return self._mark_stale(binding, "immutable client identity changed")
        except (OSError, RuntimeError, ValueError) as exc:
            return self._refresh_without_window(
                binding,
                (
                    f"window verification failed after graceful close request: {exc}"
                    if binding.state is ManagedClientState.CLOSE_REQUESTED
                    else f"client verification failed: {exc}"
                ),
            )
        binding.client = current
        binding.last_verified_at = self._now()
        return binding

    def _refresh_without_window(
        self,
        binding: _ManagedBinding,
        window_detail: str,
    ) -> _ManagedBinding:
        binding.dispatch_enabled = False
        binding.last_verified_at = self._now()
        expected_start = binding.client.process_started_at_100ns
        try:
            lifetime = self._process_inspector.inspect(binding.client.process_id)
        except (OSError, RuntimeError, ValueError) as exc:
            if binding.state is not ManagedClientState.CLOSE_REQUESTED:
                binding.state = ManagedClientState.STALE
            binding.status_detail = (
                f"{window_detail}; exact process-lifetime verification failed: {exc}"
            )
            return binding
        if lifetime is not None and lifetime.process_id != binding.client.process_id:
            if binding.state is not ManagedClientState.CLOSE_REQUESTED:
                binding.state = ManagedClientState.STALE
            binding.status_detail = (
                f"{window_detail}; process inspector returned the wrong PID and exit "
                "could not be verified"
            )
            return binding
        if lifetime is not None and (
            lifetime.process_id == binding.client.process_id
            and lifetime.process_started_at_100ns == expected_start
        ):
            if binding.state is not ManagedClientState.CLOSE_REQUESTED:
                binding.state = ManagedClientState.STALE
            binding.status_detail = f"{window_detail}; exact process lifetime is still running"
            return binding
        binding.state = ManagedClientState.EXITED
        binding.status_detail = (
            "verified exact process lifetime exited after graceful close request"
        )
        return binding

    def _mark_stale(self, binding: _ManagedBinding, detail: str) -> _ManagedBinding:
        binding.state = ManagedClientState.STALE
        binding.dispatch_enabled = False
        binding.status_detail = detail
        binding.last_verified_at = self._now()
        return binding

    def _accept_window_result(
        self,
        binding: _ManagedBinding,
        current: object,
    ) -> None:
        if not isinstance(current, ClientInstanceSnapshot) or (
            _immutable_identity(current) != _immutable_identity(binding.client)
        ):
            self._mark_stale(
                binding,
                "window controller returned a different client identity",
            )
            raise StaleManagedClientError(binding.status_detail or "client binding is stale")
        binding.client = current
        binding.last_verified_at = self._now()

    def _require_binding(self, instance_id: str) -> _ManagedBinding:
        _require_canonical_text(instance_id, "instance_id")
        try:
            return self._bindings[instance_id]
        except KeyError as exc:
            raise UnknownManagedClientError(f"client {instance_id!r} is not managed") from exc

    def _now(self) -> float:
        value = self._clock.now()
        _finite_non_negative(value, "clock value")
        return float(value)


def _immutable_identity(client: ClientInstanceSnapshot) -> tuple[object, ...]:
    return (
        client.node_id,
        client.instance_id,
        client.process_id,
        client.process_started_at_100ns,
        client.window_handle,
        client.executable_name.casefold(),
        None
        if client.executable_path is None
        else _normalized_windows_path(client.executable_path),
    )


__all__ = [
    "AmbiguousClientError",
    "ClientInstanceSelector",
    "ClientLifecycleSupervisor",
    "ClientRegistrySource",
    "DuplicateManagedClientError",
    "InvalidLifecycleTransitionError",
    "LaunchReceipt",
    "LaunchProvenance",
    "LaunchTimeoutError",
    "ManagedClientSnapshot",
    "ManagedClientState",
    "MonotonicClock",
    "NoMatchingClientError",
    "ProcessLauncher",
    "ProcessLifetimeInspector",
    "ProcessLifetimeSnapshot",
    "RegistryContractError",
    "ReviewedLaunchCommand",
    "Sleeper",
    "StaleManagedClientError",
    "SubprocessLauncher",
    "SupervisorError",
    "SystemMonotonicClock",
    "SystemSleeper",
    "UnknownManagedClientError",
    "UnsafeClientIdentityError",
    "UnownedLaunchBaselineError",
    "UnprovenLaunchProvenanceError",
    "VisibleWindowRegistrySource",
    "Win32ProcessLifetimeInspector",
    "WindowControllerUnavailableError",
    "WindowLifecycleController",
    "launch_command_from_config",
    "selector_from_config",
    "window_rectangle_from_config",
]
