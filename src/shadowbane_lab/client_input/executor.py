"""Guarded execution of compiled input plans and the semantic decision adapter."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from shadowbane_lab.client_input.backend import (
    ClickInvocation,
    DragInvocation,
    HotkeyInvocation,
    InputBackend,
    KeyPressInvocation,
)
from shadowbane_lab.client_input.compiler import DecisionInputCompiler, InputCompilationError
from shadowbane_lab.client_input.model import (
    CalibrationProfile,
    ClickCommand,
    DragCommand,
    HotkeyCommand,
    InputCommand,
    InputPlan,
    KeyPressCommand,
    WaitCommand,
)
from shadowbane_lab.client_input.stop import StopSignal
from shadowbane_lab.client_input.window import ForegroundWindowGuard, WindowGuardError
from shadowbane_lab.protocol import DecisionMessage, DispatchResult


class InputExecutionError(RuntimeError):
    """Raised when a guarded input plan cannot complete safely."""

    def __init__(self, message: str, *, commands_completed: int = 0) -> None:
        super().__init__(message)
        self.commands_completed = commands_completed


@dataclass(frozen=True, slots=True)
class InputExecutionResult:
    correlation_id: str
    action_key: str
    commands_completed: int


@dataclass(frozen=True, slots=True)
class InputDispatchAudit:
    profile_id: str
    backend_name: str
    correlation_id: str
    action_key: str
    accepted: bool
    commands_completed: int
    reason: str | None = None


class GuardedInputExecutor:
    """Serializes plans and revalidates focus immediately before every input."""

    def __init__(
        self,
        *,
        guard: ForegroundWindowGuard,
        backend: InputBackend,
        stop_signal: StopSignal,
        input_precondition: Callable[[], None] | None = None,
        minimum_input_interval_ms: int = 25,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(guard, ForegroundWindowGuard):
            raise ValueError("guard must be a ForegroundWindowGuard")
        if not isinstance(backend, InputBackend):
            raise ValueError("backend must implement InputBackend")
        if not isinstance(stop_signal, StopSignal):
            raise ValueError("stop_signal must implement StopSignal")
        if input_precondition is not None and not callable(input_precondition):
            raise ValueError("input_precondition must be callable when present")
        if (
            isinstance(minimum_input_interval_ms, bool)
            or not isinstance(minimum_input_interval_ms, int)
            or minimum_input_interval_ms < 0
        ):
            raise ValueError("minimum_input_interval_ms must be a non-negative integer")
        self._guard = guard
        self._backend = backend
        self._stop_signal = stop_signal
        self._input_precondition = input_precondition
        self._minimum_interval_seconds = minimum_input_interval_ms / 1000.0
        self._clock = clock
        self._sleeper = sleeper
        self._last_input_at: float | None = None
        self._lock = threading.Lock()

    @property
    def backend(self) -> InputBackend:
        return self._backend

    @property
    def profile(self) -> CalibrationProfile:
        return self._guard.profile

    def execute(self, plan: InputPlan) -> InputExecutionResult:
        if not isinstance(plan, InputPlan):
            raise InputExecutionError("plan must be an InputPlan")
        if self._backend.produces_desktop_input and not self.profile.live_input_enabled:
            raise InputExecutionError("calibration profile is not enabled for live input")
        with self._lock:
            completed = 0
            try:
                for command in plan.commands:
                    if isinstance(command, WaitCommand):
                        self._sleep_interruptibly(command.duration_ms / 1000.0)
                    else:
                        self._wait_for_rate_limit()
                        self._require_running()
                        if self._input_precondition is not None:
                            try:
                                self._input_precondition()
                            except Exception as exc:
                                raise InputExecutionError(
                                    f"input precondition failed: {exc}"
                                ) from exc
                        snapshot = self._guard.require_target()
                        self._invoke(command, snapshot.client_bounds)
                        self._last_input_at = self._clock()
                    completed += 1
            except (InputExecutionError, WindowGuardError) as exc:
                raise InputExecutionError(
                    str(exc),
                    commands_completed=completed,
                ) from exc
            return InputExecutionResult(
                correlation_id=plan.correlation_id,
                action_key=plan.action_key,
                commands_completed=completed,
            )

    def _invoke(self, command: InputCommand, bounds) -> None:
        try:
            if isinstance(command, ClickCommand):
                self._backend.click(
                    ClickInvocation(
                        point=bounds.resolve(command.point),
                        button=command.button,
                        clicks=command.clicks,
                    )
                )
                return
            if isinstance(command, DragCommand):
                self._backend.drag(
                    DragInvocation(
                        start=bounds.resolve(command.start),
                        end=bounds.resolve(command.end),
                        duration_ms=command.duration_ms,
                        button=command.button,
                    )
                )
                return
            if isinstance(command, KeyPressCommand):
                self._backend.key_press(KeyPressInvocation(command.key))
                return
            if isinstance(command, HotkeyCommand):
                self._backend.hotkey(HotkeyInvocation(command.keys))
                return
            raise InputExecutionError("unsupported input command")
        except InputExecutionError:
            raise
        except Exception as exc:
            raise InputExecutionError(f"input backend failed with {type(exc).__name__}") from exc

    def _wait_for_rate_limit(self) -> None:
        if self._last_input_at is None:
            return
        remaining = self._minimum_interval_seconds - (self._clock() - self._last_input_at)
        if remaining > 0:
            self._sleep_interruptibly(remaining)

    def _sleep_interruptibly(self, duration_seconds: float) -> None:
        deadline = self._clock() + duration_seconds
        while True:
            self._require_running()
            remaining = deadline - self._clock()
            if remaining <= 0:
                return
            self._sleeper(min(remaining, 0.05))

    def _require_running(self) -> None:
        if self._stop_signal.is_set():
            raise InputExecutionError("emergency stop is set")


class ClientInputAdapter:
    """Maps the shared semantic decision contract to guarded client input."""

    def __init__(self, compiler: DecisionInputCompiler, executor: GuardedInputExecutor) -> None:
        if not isinstance(compiler, DecisionInputCompiler):
            raise ValueError("compiler must be a DecisionInputCompiler")
        if not isinstance(executor, GuardedInputExecutor):
            raise ValueError("executor must be a GuardedInputExecutor")
        if compiler.profile != executor.profile:
            raise ValueError("compiler and executor must use the same calibration profile")
        self._compiler = compiler
        self._executor = executor
        self._audits: list[InputDispatchAudit] = []

    @property
    def name(self) -> str:
        return f"client-input/{self._executor.backend.name}"

    @property
    def profile(self) -> CalibrationProfile:
        return self._compiler.profile

    @property
    def audits(self) -> tuple[InputDispatchAudit, ...]:
        return tuple(self._audits)

    def dispatch(self, decision: DecisionMessage) -> DispatchResult:
        try:
            plan = self._compiler.compile(decision)
        except InputCompilationError as exc:
            return self._rejected(decision.correlation_id, decision.action_key, str(exc))
        return self._dispatch_plan(plan)

    def dispatch_camera_drag(
        self,
        *,
        correlation_id: str,
        horizontal: float,
        vertical: float,
    ) -> DispatchResult:
        try:
            plan = self._compiler.compile_camera_drag(
                correlation_id=correlation_id,
                horizontal=horizontal,
                vertical=vertical,
            )
        except InputCompilationError as exc:
            return self._rejected(correlation_id, "client.camera.rotate", str(exc))
        return self._dispatch_plan(plan)

    def dispatch_movement_stop(self, *, correlation_id: str) -> DispatchResult:
        """Report whether a verified immediate-stop input exists; never invent one."""
        try:
            plan = self._compiler.compile_movement_stop(correlation_id=correlation_id)
        except InputCompilationError as exc:
            return self._rejected(
                correlation_id,
                f"{self.profile.movement.action_key}.stop",
                str(exc),
            )
        return self._dispatch_plan(plan)

    def _dispatch_plan(self, plan: InputPlan) -> DispatchResult:
        try:
            execution = self._executor.execute(plan)
        except InputExecutionError as exc:
            return self._rejected(
                plan.correlation_id,
                plan.action_key,
                str(exc),
                commands_completed=exc.commands_completed,
            )
        self._audits.append(
            InputDispatchAudit(
                profile_id=self._compiler.profile.profile_id,
                backend_name=self._executor.backend.name,
                correlation_id=plan.correlation_id,
                action_key=plan.action_key,
                accepted=True,
                commands_completed=execution.commands_completed,
            )
        )
        return DispatchResult(
            adapter_name=self.name,
            correlation_id=plan.correlation_id,
            accepted=True,
        )

    def _rejected(
        self,
        correlation_id: str,
        action_key: str,
        reason: str,
        *,
        commands_completed: int = 0,
    ) -> DispatchResult:
        self._audits.append(
            InputDispatchAudit(
                profile_id=self._compiler.profile.profile_id,
                backend_name=self._executor.backend.name,
                correlation_id=correlation_id,
                action_key=action_key,
                accepted=False,
                commands_completed=commands_completed,
                reason=reason,
            )
        )
        return DispatchResult(
            adapter_name=self.name,
            correlation_id=correlation_id,
            accepted=False,
            reason=reason,
        )
