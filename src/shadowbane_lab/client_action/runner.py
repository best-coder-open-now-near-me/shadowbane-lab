"""Deterministic orchestration for bounded client-action contracts."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from .model import (
    ClientActionBoundary,
    ClientActionBoundaryRecord,
    ClientActionCheckpoint,
    ClientActionEffectObservation,
    ClientActionResult,
    ClientActionSpec,
)


@runtime_checkable
class BoundedClientAction(Protocol):
    """One prepared semantic action with explicit lifecycle operations."""

    @property
    def action_id(self) -> str: ...

    @property
    def spec(self) -> ClientActionSpec: ...

    def prepare(self) -> ClientActionCheckpoint: ...

    def dispatch(self) -> ClientActionCheckpoint: ...

    def observe_effect(self) -> ClientActionEffectObservation: ...

    def cleanup(self) -> ClientActionCheckpoint | None: ...


class ClientActionRunner:
    """Run one action serially and preserve every externally meaningful boundary."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(clock) or not callable(sleeper):
            raise ValueError("clock and sleeper must be callable")
        self._clock = clock
        self._sleeper = sleeper

    def run(self, action: BoundedClientAction) -> ClientActionResult:
        if not isinstance(action, BoundedClientAction):
            raise ValueError("action must implement BoundedClientAction")
        if not isinstance(action.spec, ClientActionSpec):
            raise ValueError("action spec must be ClientActionSpec")
        if not isinstance(action.action_id, str) or not action.action_id.strip():
            raise ValueError("action_id must be a non-empty string")

        started_at = self._clock()
        boundaries: list[ClientActionBoundaryRecord] = []

        def record(boundary: ClientActionBoundary, checkpoint: ClientActionCheckpoint) -> None:
            boundaries.append(
                ClientActionBoundaryRecord(
                    sequence=len(boundaries),
                    at_ms=max(0, round((self._clock() - started_at) * 1000)),
                    boundary=boundary,
                    detail=checkpoint.detail,
                    evidence=dict(checkpoint.evidence),
                )
            )

        record(
            ClientActionBoundary.STARTED,
            ClientActionCheckpoint(
                f"{action.spec.key} started",
                {
                    "timeout_ms": action.spec.timeout_ms,
                    "verification": action.spec.verification.value,
                },
            ),
        )

        try:
            prepared = action.prepare()
        except Exception as exc:
            return self._failed(
                action,
                started_at,
                boundaries,
                "precondition_failed",
                exc,
                record,
            )
        record(ClientActionBoundary.PRECONDITION_PASSED, prepared)

        dispatch_attempted = True
        terminal_reason: str | None = None
        terminal_error: Exception | None = None
        try:
            dispatched = action.dispatch()
            record(ClientActionBoundary.INPUT_DISPATCHED, dispatched)
            deadline = started_at + action.spec.timeout_ms / 1000.0
            while True:
                observation = action.observe_effect()
                if observation.observed:
                    record(ClientActionBoundary.EFFECT_OBSERVED, observation.checkpoint)
                    terminal_reason = "effect_observed"
                    break
                now = self._clock()
                if now >= deadline:
                    terminal_reason = "effect_timeout"
                    terminal_error = TimeoutError(observation.checkpoint.detail)
                    break
                self._sleeper(
                    min(
                        action.spec.poll_interval_ms / 1000.0,
                        max(0.0, deadline - now),
                    )
                )
        except Exception as exc:
            terminal_reason = (
                "dispatch_failed"
                if len(boundaries) == 2
                else "effect_observation_failed"
            )
            terminal_error = exc

        assert dispatch_attempted
        try:
            cleanup = action.cleanup()
        except Exception as exc:
            terminal_reason = "cleanup_failed"
            terminal_error = exc
        else:
            if cleanup is not None:
                record(ClientActionBoundary.CLEANUP_COMPLETED, cleanup)

        if terminal_error is not None:
            return self._failed(
                action,
                started_at,
                boundaries,
                terminal_reason or "action_failed",
                terminal_error,
                record,
            )

        assert terminal_reason == "effect_observed"
        record(
            ClientActionBoundary.SUCCEEDED,
            ClientActionCheckpoint(
                "required action effect was independently observed",
                {"terminal_reason": terminal_reason},
            ),
        )
        return ClientActionResult(
            action_id=action.action_id,
            action_key=action.spec.key,
            verification=action.spec.verification,
            succeeded=True,
            terminal_reason=terminal_reason,
            duration_ms=max(0, round((self._clock() - started_at) * 1000)),
            boundaries=tuple(boundaries),
        )

    def _failed(
        self,
        action: BoundedClientAction,
        started_at: float,
        boundaries: list[ClientActionBoundaryRecord],
        terminal_reason: str,
        error: Exception,
        record: Callable[[ClientActionBoundary, ClientActionCheckpoint], None],
    ) -> ClientActionResult:
        message = " ".join(str(error).split())
        detail = terminal_reason if not message else f"{terminal_reason}: {message[:240]}"
        record(
            ClientActionBoundary.FAILED,
            ClientActionCheckpoint(
                detail,
                {
                    "error_type": type(error).__name__,
                    "terminal_reason": terminal_reason,
                },
            ),
        )
        return ClientActionResult(
            action_id=action.action_id,
            action_key=action.spec.key,
            verification=action.spec.verification,
            succeeded=False,
            terminal_reason=terminal_reason,
            duration_ms=max(0, round((self._clock() - started_at) * 1000)),
            boundaries=tuple(boundaries),
        )


__all__ = ["BoundedClientAction", "ClientActionRunner"]
