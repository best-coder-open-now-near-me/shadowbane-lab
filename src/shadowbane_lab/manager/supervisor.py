"""Fail-closed lifecycle supervision for locally discovered game clients.

The supervisor owns manager bindings, not game processes.  Pausing a binding only
disables manager dispatch, and closing a binding is always a graceful window-close
request delegated to an injected controller.
"""

from __future__ import annotations

import ntpath
import subprocess
import threading
import time
from dataclasses import dataclass
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


class ManagedClientState(StrEnum):
    ATTACHED = "attached"
    PAUSED = "paused"
    CLOSE_REQUESTED = "close_requested"
    STALE = "stale"
    DETACHED = "detached"


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
class LaunchReceipt:
    """Identity of the process directly created by a launcher.

    The launched process may be a bootstrapper whose child becomes the registered
    game client, so this PID is audit information rather than an attach criterion.
    """

    process_id: int

    def __post_init__(self) -> None:
        _positive_integer(self.process_id, "process_id")


@dataclass(frozen=True, slots=True)
class ManagedClientSnapshot:
    """Immutable operator-facing status for one manager-owned binding."""

    selector: ClientInstanceSelector
    client: ClientInstanceSnapshot
    state: ManagedClientState
    dispatch_enabled: bool
    launched_by_manager: bool
    launcher_process_id: int | None
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
        if self.launched_by_manager != (self.launcher_process_id is not None):
            raise ValueError("manager-launched clients require a launcher process ID")
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


class SubprocessLauncher:
    """Launch reviewed argv commands directly with ``shell=False``."""

    def __init__(self) -> None:
        self._children: dict[int, subprocess.Popen[bytes]] = {}

    def launch(self, command: ReviewedLaunchCommand) -> LaunchReceipt:
        if not isinstance(command, ReviewedLaunchCommand):
            raise ValueError("command must be ReviewedLaunchCommand")
        self._reap_finished_children()
        process = subprocess.Popen(
            command.argv,
            cwd=command.working_directory,
            shell=False,
        )
        self._children[process.pid] = process
        return LaunchReceipt(process_id=process.pid)

    def _reap_finished_children(self) -> None:
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
        self._bindings: dict[str, _ManagedBinding] = {}
        self._lock = threading.RLock()

    def attach(
        self,
        selector: ClientInstanceSelector,
        *,
        instance_id: str | None = None,
    ) -> ManagedClientSnapshot:
        """Attach to one client, requiring an exact ID when filters are ambiguous."""

        with self._lock:
            snapshot = self._read_snapshot(selector)
            if snapshot.rejected:
                raise UnsafeClientIdentityError(
                    f"{len(snapshot.rejected)} matching window(s) lack complete identity"
                )
            if not snapshot.clients:
                raise NoMatchingClientError("no matching pre-existing client was found")
            if instance_id is not None:
                _require_canonical_text(instance_id, "instance_id")
                matches = tuple(
                    client for client in snapshot.clients if client.instance_id == instance_id
                )
                if not matches:
                    raise NoMatchingClientError(
                        f"registered client {instance_id!r} did not match the selector"
                    )
                if len(matches) != 1:
                    raise AmbiguousClientError(f"registered client {instance_id!r} was not unique")
                return self._bind(selector, matches[0], launch_receipt=None)
            if len(snapshot.clients) != 1:
                raise AmbiguousClientError(
                    f"found {len(snapshot.clients)} pre-existing clients; "
                    "select an exact instance_id"
                )
            return self._bind(selector, snapshot.clients[0], launch_receipt=None)

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

        with self._lock:
            baseline = self._read_safe_snapshot(selector)
            baseline_by_id = {client.instance_id: client for client in baseline.clients}
            receipt = self._launcher.launch(command)
            if not isinstance(receipt, LaunchReceipt):
                raise SupervisorError("launcher must return LaunchReceipt")

            deadline = self._now() + timeout_seconds
            while True:
                current = self._read_safe_snapshot(selector)
                current_by_id = {client.instance_id: client for client in current.clients}
                missing = tuple(sorted(set(baseline_by_id) - set(current_by_id)))
                if missing:
                    raise StaleManagedClientError(
                        "baseline client identities disappeared during launch: "
                        + ", ".join(missing)
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
                if len(new_clients) > 1:
                    raise AmbiguousClientError(
                        f"launch produced {len(new_clients)} new matching clients"
                    )
                if len(new_clients) == 1:
                    return self._bind(selector, new_clients[0], launch_receipt=receipt)

                now = self._now()
                remaining = deadline - now
                if remaining <= 0:
                    raise LaunchTimeoutError(
                        "launch produced no new matching client before the timeout"
                    )
                self._sleeper.sleep(min(float(poll_seconds), remaining))

    def pause(self, instance_id: str) -> ManagedClientSnapshot:
        """Disable manager dispatch without suspending the operating-system process."""

        with self._lock:
            binding = self._require_binding(instance_id)
            if binding.state is ManagedClientState.STALE:
                raise StaleManagedClientError(binding.status_detail or "client binding is stale")
            if binding.state is ManagedClientState.CLOSE_REQUESTED:
                raise InvalidLifecycleTransitionError("cannot pause after close was requested")
            binding.state = ManagedClientState.PAUSED
            binding.dispatch_enabled = False
            binding.status_detail = None
            return binding.snapshot()

    def resume(self, instance_id: str) -> ManagedClientSnapshot:
        """Re-enable dispatch only after re-verifying the immutable client identity."""

        with self._lock:
            binding = self._require_binding(instance_id)
            if binding.state is ManagedClientState.CLOSE_REQUESTED:
                raise InvalidLifecycleTransitionError("cannot resume after close was requested")
            binding = self._refresh_binding(binding)
            if binding.state is ManagedClientState.STALE:
                raise StaleManagedClientError(binding.status_detail or "client binding is stale")
            binding.state = ManagedClientState.ATTACHED
            binding.dispatch_enabled = True
            binding.status_detail = None
            return binding.snapshot()

    def refresh(self, instance_id: str) -> ManagedClientSnapshot:
        """Refresh one status, permanently failing its dispatch closed if identity is stale."""

        with self._lock:
            return self._refresh_binding(self._require_binding(instance_id)).snapshot()

    def dispatch_is_enabled(self, instance_id: str) -> bool:
        """Revalidate an immutable binding before authorizing any manager dispatch."""

        with self._lock:
            binding = self._refresh_binding(self._require_binding(instance_id))
            return binding.dispatch_enabled

    def status(self, instance_id: str) -> ManagedClientSnapshot:
        with self._lock:
            return self._require_binding(instance_id).snapshot()

    def snapshots(self) -> tuple[ManagedClientSnapshot, ...]:
        with self._lock:
            return tuple(
                self._bindings[instance_id].snapshot() for instance_id in sorted(self._bindings)
            )

    def detach(self, instance_id: str) -> ManagedClientSnapshot:
        """Forget a binding without closing, killing, or suspending its process."""

        with self._lock:
            binding = self._require_binding(instance_id)
            del self._bindings[instance_id]
            binding.state = ManagedClientState.DETACHED
            binding.dispatch_enabled = False
            binding.status_detail = "detached by manager"
            return binding.snapshot()

    def request_close(self, instance_id: str) -> ManagedClientSnapshot:
        """Disable dispatch and request a graceful window close through the controller."""

        with self._lock:
            if self._window_controller is None:
                raise WindowControllerUnavailableError("no window controller is configured")
            binding = self._require_binding(instance_id)
            if binding.state is ManagedClientState.CLOSE_REQUESTED:
                raise InvalidLifecycleTransitionError("close was already requested")
            binding = self._refresh_binding(binding)
            if binding.state is ManagedClientState.STALE:
                raise StaleManagedClientError(binding.status_detail or "client binding is stale")
            binding.state = ManagedClientState.PAUSED
            binding.dispatch_enabled = False
            binding.status_detail = "graceful close request pending"
            try:
                current = self._window_controller.request_graceful_close(binding.client)
            except Exception as exc:
                binding.status_detail = f"graceful close request failed: {exc}"
                raise SupervisorError(binding.status_detail) from exc
            self._accept_window_result(binding, current)
            binding.state = ManagedClientState.CLOSE_REQUESTED
            binding.status_detail = "graceful close requested"
            return binding.snapshot()

    def tile(
        self,
        instance_id: str,
        rectangle: WindowRectangle,
    ) -> ManagedClientSnapshot:
        """Place one verified window without activating it or changing its Z-order."""

        with self._lock:
            if self._window_controller is None:
                raise WindowControllerUnavailableError("no window controller is configured")
            if not isinstance(rectangle, WindowRectangle):
                raise ValueError("rectangle must be WindowRectangle")
            binding = self._refresh_binding(self._require_binding(instance_id))
            if binding.state is ManagedClientState.STALE:
                raise StaleManagedClientError(binding.status_detail or "client binding is stale")
            if binding.state is ManagedClientState.CLOSE_REQUESTED:
                raise InvalidLifecycleTransitionError(
                    "cannot tile a client after close was requested"
                )
            try:
                current = self._window_controller.tile(binding.client, rectangle)
            except Exception as exc:
                raise SupervisorError(f"window tile failed: {exc}") from exc
            self._accept_window_result(binding, current)
            return binding.snapshot()

    def _bind(
        self,
        selector: ClientInstanceSelector,
        client: ClientInstanceSnapshot,
        *,
        launch_receipt: LaunchReceipt | None,
    ) -> ManagedClientSnapshot:
        self._reject_managed_duplicate(client)
        now = self._now()
        binding = _ManagedBinding(
            selector=selector,
            client=client,
            state=ManagedClientState.ATTACHED,
            dispatch_enabled=True,
            launched_by_manager=launch_receipt is not None,
            launcher_process_id=(launch_receipt.process_id if launch_receipt is not None else None),
            attached_at=now,
            last_verified_at=now,
        )
        self._bindings[client.instance_id] = binding
        return binding.snapshot()

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
        if binding.state is ManagedClientState.STALE:
            return binding
        try:
            snapshot = self._read_snapshot(binding.selector)
            matches = tuple(
                client
                for client in snapshot.clients
                if client.instance_id == binding.client.instance_id
            )
            if len(matches) != 1:
                return self._mark_stale(
                    binding,
                    "immutable client identity is no longer present exactly once",
                )
            current = matches[0]
            if _immutable_identity(current) != _immutable_identity(binding.client):
                return self._mark_stale(binding, "immutable client identity changed")
        except (OSError, RuntimeError, ValueError) as exc:
            return self._mark_stale(binding, f"client verification failed: {exc}")
        binding.client = current
        binding.last_verified_at = self._now()
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
    "LaunchTimeoutError",
    "ManagedClientSnapshot",
    "ManagedClientState",
    "MonotonicClock",
    "NoMatchingClientError",
    "ProcessLauncher",
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
    "VisibleWindowRegistrySource",
    "WindowControllerUnavailableError",
    "WindowLifecycleController",
    "launch_command_from_config",
    "selector_from_config",
    "window_rectangle_from_config",
]
