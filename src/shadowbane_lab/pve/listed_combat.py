"""One listed encounter, owned by the existing native movement session."""

from collections.abc import Callable
from dataclasses import dataclass

from shadowbane_lab.client_extension.actor_action_wire import (
    OUTBOUND_QUEUED,
    Phase,
    Receipt,
)
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementError,
)
from shadowbane_lab.pve.attack_list import AttackListStore
from shadowbane_lab.pve.listed_target import ListedTarget, listed_targets
from shadowbane_lab.pve.model import (
    PvECampLease,
    PvECombatDisposition,
    PvECombatKind,
    PvECombatProposal,
    PvEObservation,
)
from shadowbane_lab.pve.native_combat import (
    NativeCombatCoordinator,
    context_cleanup_confirmed,
)


class ListedCombatInterruptionError(RuntimeError):
    """The old PvE action or admission boundary could not be established safely."""

    def __init__(self, stage: str, cause: Exception) -> None:
        self.stage = stage
        self.cause_type = type(cause).__name__
        self.cause_detail = " ".join(str(cause).split())[:160]
        self.movement_outcome = cause.outcome if isinstance(cause, NativeMovementError) else None
        self.movement_receipt = cause.receipt if isinstance(cause, NativeMovementError) else None
        detail = f"listed interruption failed:{stage}:{self.cause_type}"
        if self.movement_outcome is not None:
            detail += f":outcome={self.movement_outcome.name.lower()}"
            detail += f":receipt={'present' if self.movement_receipt is not None else 'absent'}"
        if self.cause_detail:
            detail += f":{self.cause_detail}"
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class ListedCombatUpdate:
    reason: str
    request: str | None
    receipt: Receipt | None = None
    recovered: bool = False
    terminal_reason: str | None = None
    native_detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        receipt = self.receipt
        return {
            "reason": self.reason, "request": self.request,
            "outcome": None if receipt is None else receipt.outcome.name.lower(),
            "phase": None if receipt is None else receipt.context_phase.name.lower(),
            "flags": None if receipt is None else receipt.flags,
            "outbound_queued": None if receipt is None else bool(receipt.flags & OUTBOUND_QUEUED),
            "mode": None if receipt is None else receipt.mode,
            "action_state": None if receipt is None else receipt.action_state,
            "combat_target_present": None if receipt is None else receipt.combat_target_present,
            # Diagnostic text is retained verbatim; it never supplies state proof.
            "native_detail": self.native_detail,
            "cleanup_confirmed": receipt is not None and context_cleanup_confirmed(receipt),
            "recovered": self.recovered, "terminal_reason": self.terminal_reason,
        }


class ListedCombatCoordinator:
    """Saved-list ranking layered over the same NPC/native engagement owner."""

    def __init__(self, *, store: AttackListStore, combat: NativeCombatCoordinator,
                 require_current: Callable[[], object], engagement_timeout_ms=30_000):
        if not callable(require_current):
            raise ValueError("listed combat requires current native character validation")
        if type(engagement_timeout_ms) is not int or engagement_timeout_ms <= 0:
            raise ValueError("engagement_timeout_ms must be positive")
        self.store, self.combat, self.require_current = store, combat, require_current
        self.engagement_timeout_ms = engagement_timeout_ms
        self._candidate: ListedTarget | None = None
        self._proposal = None
        self._started_at = None
        self._cancel_reason = None
        self._active = False
        self._cleanup_attempts = 0
        self._quarantined: set[tuple[int, str]] = set()
        self._sequence = 0

    @property
    def active(self):
        return self._active

    def prepare(self, observation: PvEObservation, camp: PvECampLease | None):
        try:
            self.require_current()
            saved = self.store.snapshot()
            candidates = listed_targets(saved, self.store.owner, observation, camp)
        except Exception:
            if not self.active:
                self._candidate = None
                raise
            self._cancel_reason = "listed_identity_unavailable"
            return True
        population = observation.population
        alive_keys = set() if population is None else {
            character.object_key for character in population.characters if character.alive
        }
        present_ids = {entry.entry_id for entry in saved.entries
                       if entry.player_identity is not None
                       and entry.player_identity.object_key in alive_keys}
        self._quarantined.intersection_update((saved.revision, key) for key in present_ids)
        if self.active:
            if population is None or population.local_player_object_key != self.combat.actor_key:
                self._cancel_reason = "listed_local_identity_changed"
            if not any(item.entry == self._candidate.entry
                       and item.revision == self._candidate.revision for item in candidates):
                self._cancel_reason = "listed_target_no_longer_eligible"
            if (self._started_at is not None
                    and observation.now_ms - self._started_at >= self.engagement_timeout_ms):
                self._cancel_reason = "listed_engagement_timeout"
            return True
        self._candidate = next((item for item in candidates
                                if (item.revision, item.entry.entry_id)
                                not in self._quarantined), None)
        return self._candidate is not None

    def advance(self, observation: PvEObservation):
        if self._candidate is None:
            raise RuntimeError("listed combat requires prepared saved intent")
        self._active = True
        if self._cancel_reason:
            return self.cancel(self._cancel_reason)
        if self._proposal is None:
            # An intentional policy retarget cleans the old NPC engagement once.
            # Ordinary repeated actions never pass through this transition.
            if self.combat.active:
                confirmed, receipt, detail = self.combat.stop("listed_target_interrupt")
                if not confirmed:
                    self._cleanup_attempts += 1
                    return self._update("listed_previous_cleanup_pending", receipt, detail)
                if receipt is not None and receipt.owner_phase in (Phase.CLOSED, Phase.RETIRED):
                    return self._cancel_complete(True, receipt, detail, "listed_target_interrupt")
            candidate = self._candidate
            self._sequence += 1
            self._proposal = PvECombatProposal(
                self._sequence, candidate.character.token, candidate.character.object_key,
                PvECombatKind.ATTACK,
            )
            self._started_at = observation.now_ms
            self._quarantined.add((candidate.revision, candidate.entry.entry_id))
            self._cleanup_attempts = 0
            try:
                update = self.combat.advance(self._proposal, observation, listed=candidate)
            except Exception as exc:
                self._cancel_reason = "listed_admission_failed"
                raise ListedCombatInterruptionError("native_admission", exc) from exc
        elif self.combat.pending is not None:
            update = self.combat.advance(self._proposal, observation, listed=self._candidate)
        else:
            receipt, detail = self.combat.observe()
            if receipt is None:
                self._cancel_reason = "listed_status_unconfirmed"
            elif receipt.context_phase is not Phase.BOUND:
                self._cancel_reason = "listed_engagement_closed"
            return self._update(self._cancel_reason or "listed_combat_engaged", receipt, detail)
        if update.acknowledgement.disposition in (
            PvECombatDisposition.REJECTED, PvECombatDisposition.DEFERRED,
        ):
            self._cancel_reason = "listed_native_rejected"
        return self._update(self._cancel_reason or "listed_combat_engaged",
                            update.receipt, update.detail)

    @property
    def preparation_allowed(self):
        """Refresh only after listed health/closure checks and settled admission."""
        return (self._active and self._proposal is not None
                and self._cancel_reason is None and self.combat.pending is None)

    def _update(self, reason, receipt=None, detail=None):
        return ListedCombatUpdate(
            reason, (None if receipt is None or receipt.context_id is None
                     else receipt.context_id.encode().hex()), receipt,
            terminal_reason=("listed_combat_cleanup_unconfirmed"
                             if self.combat.cleanup_expired else None),
            native_detail=detail,
        )

    def cancel(self, reason="listed_combat_cancelled"):
        if not self.active:
            self._candidate = None
            return ListedCombatUpdate(reason, None)
        self._cancel_reason = reason
        self._cleanup_attempts += 1
        confirmed, receipt, detail = self.combat.stop(reason)
        if not confirmed:
            return self._update(reason, receipt, detail)
        return self._cancel_complete(confirmed, receipt, detail, reason)

    def _cancel_complete(self, confirmed, receipt, detail, reason):
        if not confirmed:
            return self._update(reason, receipt, detail)
        retired = receipt is not None and (receipt.context_phase is Phase.RETIRED
                                           or receipt.owner_phase is Phase.RETIRED)
        owner_closed = receipt is not None and receipt.owner_phase in (Phase.CLOSED, Phase.RETIRED)
        self._active = False
        self._candidate = self._proposal = self._started_at = self._cancel_reason = None
        self._cleanup_attempts = 0
        return ListedCombatUpdate(
            "listed_scene_retired" if retired else "listed_local_cleanup_confirmed",
            (None if receipt is None or receipt.context_id is None
             else receipt.context_id.encode().hex()), receipt,
            recovered=not owner_closed,
            terminal_reason=("listed_combat_scene_retired" if retired
                             else "listed_actor_owner_closed" if owner_closed else None),
            native_detail=detail,
        )

    def finish(self, reason):
        if not self.active:
            return self.cancel(reason)
        self._cancel_reason = reason
        return self._cancel_complete(*self.combat.finish(reason), reason)
