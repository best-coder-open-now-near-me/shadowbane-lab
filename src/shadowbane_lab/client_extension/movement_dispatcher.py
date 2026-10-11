"""Native travel/PvE movement under one immutable operation grant."""

from __future__ import annotations

import uuid

from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.travel.model import TravelDecision

from .action_channel import NativeActionChannelError
from .movement_session import (
    NativeMovementCleanupPending,
    NativeMovementGrant,
    NativeMovementParentPending,
    NativeMovementSession,
)
from .movement_wire import CLEANUP_PENDING, owner_maintenance_available


class NativeMovementTravelDispatcher:
    def __init__(self, session: NativeMovementSession, immutable_grant: NativeMovementGrant):
        self.session, self.grant = session, immutable_grant
        self._interruption_reason: str | None = None
        self._cleanup_pending = False
        self._parent_pending = False

    @property
    def interruption_reason(self) -> str | None:
        return self._interruption_reason

    def _interrupt(self, reason: str) -> None:
        if self._interruption_reason is None:
            self._interruption_reason = reason

    def is_set(self) -> bool:
        """Validate exact ownership; coordinate travel may prove a native successor."""
        if self._interruption_reason is not None:
            return True
        try:
            snapshot = (self.session.synchronize(self.grant) if self.grant.coordinate_only
                        else self.session.snapshot())
            # synchronize validates coordinate ownership under its session lock.
            # A second thread may already acknowledge the next parent after it
            # returns; comparing a separately read current grant would race it.
            if not self.grant.coordinate_only and snapshot.grant != self.grant.ownership:
                self._interrupt("native_movement_owner_revoked")
            elif not owner_maintenance_available(snapshot.flags):
                self._interrupt("native_movement_unavailable")
            else:
                self._cleanup_pending = bool(snapshot.flags & CLEANUP_PENDING)
                self._parent_pending = False
        except NativeMovementParentPending:
            self._cleanup_pending = self._parent_pending = True
        except (NativeActionChannelError, ValueError) as exc:
            self._interrupt(f"native_movement_status:{type(exc).__name__}")
        return self._interruption_reason is not None

    def prepare_dispatch(self) -> None:
        if self.grant.coordinate_only and not self.is_set() and self._parent_pending:
            from shadowbane_lab.travel.runtime import TravelDispatchDeferred
            raise TravelDispatchDeferred("coordinate_parent_cleanup_pending")

    def _request(self, kind: str, decision: TravelDecision) -> str:
        # A bounded deterministic UUID has no per-waypoint receipt cache. Different
        # immutable operation acquisitions never reuse a decision UUID namespace.
        return str(uuid.uuid5(uuid.UUID(self.grant.request_key), f"{kind}:{decision.decision_id}"))

    def dispatch(self, decision: TravelDecision) -> DispatchResult:
        if not isinstance(decision, TravelDecision) or decision.click_destination is None:
            raise ValueError("travel decision must have its accepted bounded destination")
        correlation = f"travel:{decision.decision_id}:native"
        if not self.is_set():
            if self._cleanup_pending:
                if self._parent_pending:
                    from shadowbane_lab.travel.runtime import TravelDispatchDeferred
                    raise TravelDispatchDeferred("coordinate_parent_cleanup_pending")
                return DispatchResult(
                    "native_movement", correlation, False, "native_movement_cleanup_pending"
                )
            destination = decision.click_destination
            try:
                # Canonical observation mapping is LT=native X, LG=-native Z.
                # Native terrain query/raycast supplies Y and parent attachment.
                self.session.move(
                    self.grant,
                    (destination.x, 0.0, -destination.y),
                    self._request("move", decision),
                )
            except NativeMovementCleanupPending as exc:
                if isinstance(exc, NativeMovementParentPending):
                    from shadowbane_lab.travel.runtime import TravelDispatchDeferred
                    raise TravelDispatchDeferred("coordinate_parent_cleanup_pending") from exc
                return DispatchResult(
                    "native_movement", correlation, False, "native_movement_cleanup_pending"
                )
            except (NativeActionChannelError, ValueError) as exc:
                self._interrupt(f"native_movement_dispatch:{type(exc).__name__}")
        return DispatchResult(
            "native_movement",
            correlation,
            self._interruption_reason is None,
            self._interruption_reason,
        )

    def stop_movement(self, decision: TravelDecision) -> DispatchResult:
        if not isinstance(decision, TravelDecision) or not decision.terminal:
            raise ValueError("movement pause requires a terminal approach/travel decision")
        correlation = f"travel:{decision.decision_id}:native_pause"
        if not self.is_set():
            try:
                self.session.pause(self.grant, self._request("pause", decision))
            except NativeMovementCleanupPending:
                return DispatchResult(
                    "native_movement", correlation, False, "native_movement_cleanup_pending"
                )
            except (NativeActionChannelError, ValueError) as exc:
                self._interrupt(f"native_movement_pause:{type(exc).__name__}")
        return DispatchResult(
            "native_movement",
            correlation,
            self._interruption_reason is None,
            self._interruption_reason,
        )
