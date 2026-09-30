"""Exact-owner ordinary combat cleanup, independent of UI selection and snapshots."""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import uuid4

from shadowbane_lab.client_extension.movement_session import (
    NativeMovementGrant,
    NativeMovementSession,
)
from shadowbane_lab.client_extension.movement_wire import Outcome, Receipt
from shadowbane_lab.pve.model import PvECombatCleanupRequest, PvECombatCleanupResult


@runtime_checkable
class PvECombatCleanup(Protocol):
    def cleanup(self, request: PvECombatCleanupRequest) -> PvECombatCleanupResult: ...


class NativePvECombatCleanup:
    """Qualify the process-pinned stop service before input; retain one exact owner.

    A later readiness drop must not prevent PAUSE. Timeouts and negative receipts
    remain unconfirmed and are latched; this boundary never retries or reacquires.
    """

    def __init__(self, session: NativeMovementSession, grant: NativeMovementGrant) -> None:
        self._session, self._grant = session, grant
        session.require_combat_available(grant)
        self._result: PvECombatCleanupResult | None = None

    def cleanup(self, request: PvECombatCleanupRequest) -> PvECombatCleanupResult:
        if not isinstance(request, PvECombatCleanupRequest):
            raise ValueError("cleanup requires a typed immutable engagement request")
        if self._result is not None:
            if request == self._result.request:
                return self._result
            if request.sequence <= self._result.request.sequence:
                raise ValueError("retired cleanup request cannot be replayed or rebound")
            if not self._result.confirmed:
                raise RuntimeError("previous cleanup remains unconfirmed")
        key = str(uuid4())
        try:
            self._pause(key)
        except Exception as exc:
            detail = " ".join(str(exc).split())[:160]
            outcome = getattr(exc, "outcome", None)
            suffix = "" if outcome is None else f":outcome={outcome.name.lower()}"
            result = PvECombatCleanupResult(
                request, False, key, f"{type(exc).__name__}{suffix}:{detail}"
            )
        else:
            result = PvECombatCleanupResult(request, True, key)
        self._result = result
        return result

    def _pause(self, key: str) -> None:
        receipt = self._session.pause(self._grant, key)
        if (not isinstance(receipt, Receipt) or receipt.outcome != Outcome.ACCEPTED
                or receipt.grant != self._grant.ownership or receipt.host != self._grant.host
                or receipt.window != self._grant.window or receipt.request_key != key):
            raise RuntimeError("native cleanup acknowledgment changed request or ownership")
