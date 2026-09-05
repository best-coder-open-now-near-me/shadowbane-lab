"""Native travel/PvE movement under one immutable operation grant."""

from __future__ import annotations

import uuid

from shadowbane_lab.protocol import DispatchResult
from shadowbane_lab.travel.model import TravelDecision

from .action_channel import NativeActionChannelError
from .movement_session import NativeMovementGrant, NativeMovementSession


class NativeMovementTravelDispatcher:
    def __init__(self, session: NativeMovementSession, immutable_grant: NativeMovementGrant):
        self.session, self.grant = session, immutable_grant
        self._interruption_reason: str | None = None

    @property
    def interruption_reason(self) -> str | None:
        return self._interruption_reason

    def _interrupt(self, reason: str) -> None:
        if self._interruption_reason is None:
            self._interruption_reason = reason

    def is_set(self) -> bool:
        """Read-only stop signal: a manual takeover also stops PvE combat dispatch."""
        if self._interruption_reason is not None:
            return True
        try:
            snapshot = self.session.snapshot()
            if snapshot.grant != self.grant.ownership:
                self._interrupt("native_movement_owner_revoked")
            elif not snapshot.flags & 2 or snapshot.flags & 8:
                self._interrupt("native_movement_unavailable")
        except (NativeActionChannelError, ValueError) as exc:
            self._interrupt(f"native_movement_status:{type(exc).__name__}")
        return self._interruption_reason is not None

    def _request(self, kind: str, decision: TravelDecision) -> str:
        # A bounded deterministic UUID has no per-waypoint receipt cache. Different
        # immutable operation acquisitions never reuse a decision UUID namespace.
        return str(uuid.uuid5(uuid.UUID(self.grant.request_key), f"{kind}:{decision.decision_id}"))

    def dispatch(self, decision: TravelDecision) -> DispatchResult:
        if not isinstance(decision, TravelDecision) or decision.click_destination is None:
            raise ValueError("travel decision must have its accepted bounded destination")
        correlation = f"travel:{decision.decision_id}:native"
        if not self.is_set():
            destination = decision.click_destination
            try:
                # Canonical observation mapping is LT=native X, LG=-native Z.
                # Native terrain query/raycast supplies Y and parent attachment.
                self.session.move(
                    self.grant,
                    (destination.x, 0.0, -destination.y),
                    self._request("move", decision),
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
            except (NativeActionChannelError, ValueError) as exc:
                self._interrupt(f"native_movement_pause:{type(exc).__name__}")
        return DispatchResult(
            "native_movement",
            correlation,
            self._interruption_reason is None,
            self._interruption_reason,
        )
