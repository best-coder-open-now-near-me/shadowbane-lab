"""Target-context facade over the one shared native actor owner."""
from __future__ import annotations

from dataclasses import dataclass

from shadowbane_lab.client_extension.actor_action_wire import (
    OUTBOUND_QUEUED,
    Closure,
    ClosureScope,
    Command,
    Phase,
    Receipt,
)
from shadowbane_lab.pve.model import PvECombatAcknowledgement


def context_cleanup_confirmed(receipt):
    return bool(receipt is not None and receipt.closure_scope is ClosureScope.CONTEXT
        and receipt.context_phase in (Phase.CLOSED, Phase.RETIRED)
        and receipt.closure in (Closure.NATIVE_STOPPED, Closure.LOCAL_RELEASED,
                                Closure.SCENE_RETIRED))


@dataclass(frozen=True, slots=True)
class NativeCombatUpdate:
    acknowledgement: PvECombatAcknowledgement
    receipt: Receipt | None = None
    detail: str | None = None
    command: Command | None = None
    terminal_reason: str | None = None
    preceding_replies: tuple[NativeCombatUpdate, ...] = ()

    def as_dict(self):
        r = self.receipt
        if r is not None and self.command is not None:
            r.require_command(self.command, r.verb)
        return {
            "disposition": self.acknowledgement.disposition.value,
            "not_ready_reason": (None if self.acknowledgement.not_ready_reason is None
                                 else self.acknowledgement.not_ready_reason.value),
            "native_entered": self.acknowledgement.native_entered,
            "cleanup_required": self.acknowledgement.cleanup_required,
            "parent": None if r is None or r.parent_id is None else r.parent_id.encode().hex(),
            "context": None if r is None or r.context_id is None else r.context_id.encode().hex(),
            "request": None if r is None else r.request.encode().hex(),
            "verb": None if r is None else r.verb.name.lower(),
            "action": None if r is None else r.action.name.lower(),
            "power_id": None if self.command is None else self.command.power_id,
            "outcome": None if r is None else r.outcome.name.lower(),
            "native_reason": None if r is None else r.reason.name.lower(),
            "flags": None if r is None else r.flags,
            "entry_state": None if r is None else r.entry.name.lower(),
            "local_settlement": None if r is None else r.local_settlement.name.lower(),
            "application": None if r is None else r.application.name.lower(),
            "owner_phase": None if r is None else r.owner_phase.name.lower(),
            "context_phase": None if r is None else r.context_phase.name.lower(),
            "closure": None if r is None else r.closure.name.lower(),
            "closure_scope": None if r is None else r.closure_scope.name.lower(),
            "outbound_queued": None if r is None else bool(r.flags & OUTBOUND_QUEUED),
            "command_digest": (self.command.digest.hex() if self.command is not None
                               else None if r is None else r.command_digest.hex()),
            "command_request": (None if self.command is None
                                else self.command.request.encode().hex()),
            "terminal_reason": self.terminal_reason,
            "preceding_replies": [reply.as_dict() for reply in self.preceding_replies],
            "detail": self.detail,
        }


class NativeCombatCoordinator:
    """Own no writer, lease or parent; finish only the retained target context."""

    def __init__(self, *, owner):
        from .native_actor import NativeActorCoordinator
        if not isinstance(owner, NativeActorCoordinator):
            raise ValueError("combat requires the shared native actor coordinator")
        self.owner = owner

    @property
    def actor_key(self):
        return self.owner.actor_key

    @property
    def active(self):
        return self.owner.active

    @property
    def pending(self):
        return self.owner.pending

    @property
    def cleanup_expired(self):
        return self.owner.cleanup_expired

    @property
    def engagement(self):
        return self.owner.engagement

    def advance(self, proposal, observation, *, listed=None):
        return self.owner.advance_combat(proposal, observation, listed=listed)

    def observe(self):
        return self.owner.observe_context()

    def stop(self, reason):
        return self.owner.stop_context(reason)

    def finish(self, reason):
        return self.owner.finish_context(reason)

    def cleanup(self, request):
        return self.owner.cleanup_context(request)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if not self.finish("combat_scope_closed")[0]:
            raise RuntimeError("native target context cleanup remains unconfirmed")
