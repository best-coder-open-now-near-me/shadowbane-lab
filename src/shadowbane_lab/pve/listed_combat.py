"""One listed encounter, owned by the existing native movement session."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from shadowbane_lab.client_extension.combat_wire import Outcome, Phase, Receipt, Verb
from shadowbane_lab.client_extension.movement_session import (
    NativeMovementGrant,
    NativeMovementSession,
)
from shadowbane_lab.pve.attack_list import AttackListStore
from shadowbane_lab.pve.listed_target import ListedTarget, listed_targets
from shadowbane_lab.pve.model import PvECampLease, PvEObservation


class ListedCombatInterruptionError(RuntimeError):
    """The old PvE action or admission boundary could not be established safely."""


@dataclass(frozen=True, slots=True)
class ListedCombatUpdate:
    reason: str
    request: str | None
    receipt: Receipt | None = None
    recovered: bool = False
    terminal_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        receipt = self.receipt
        return {
            "reason": self.reason, "request": self.request,
            "outcome": None if receipt is None else receipt.outcome.name.lower(),
            "phase": None if receipt is None else receipt.phase.name.lower(),
            "cleanup_confirmed": receipt is not None and receipt.cleanup_confirmed,
            "recovered": self.recovered, "terminal_reason": self.terminal_reason,
        }


class ListedCombatCoordinator:
    """Keep the immutable admission alive through uncertain entry and cancellation.

    prepare() only ranks intent. advance() is called after controller safety checks.
    A rejected candidate is quarantined for its saved revision until observed
    absent/dead, preventing a hot retry loop without deleting durable intent.
    """

    def __init__(
        self, *, store: AttackListStore, session: NativeMovementSession,
        grant: NativeMovementGrant, require_current: Callable[[], object],
        engagement_timeout_ms: int = 30_000,
    ) -> None:
        if not callable(require_current):
            raise ValueError("listed combat requires current character validation")
        if type(engagement_timeout_ms) is not int or engagement_timeout_ms <= 0:
            raise ValueError("engagement_timeout_ms must be positive")
        self.store, self.session, self.grant = store, session, grant
        self.require_current = require_current
        self.engagement_timeout_ms = engagement_timeout_ms
        self._candidate: ListedTarget | None = None
        self._ticket = None
        self._command = None
        self._started_at = None
        self._cancel_reason = None
        self._cleanup_attempts = 0
        self._quarantined: set[tuple[int, str]] = set()

    @property
    def active(self) -> bool:
        return self._ticket is not None

    def prepare(self, observation: PvEObservation, camp: PvECampLease | None) -> bool:
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
        self._quarantined.intersection_update(
            (saved.revision, entry_id) for entry_id in present_ids
        )
        if self.active:
            assert self._candidate is not None
            assert self._command is not None
            local = None if population is None else population.local_player_object_key
            if (local is None or (local.object_type, local.object_uuid)
                    != self._command.binding.local_key):
                self._cancel_reason = "listed_local_identity_changed"
            if not any(candidate.entry == self._candidate.entry
                       and candidate.revision == self._candidate.revision
                       for candidate in candidates):
                self._cancel_reason = "listed_target_no_longer_eligible"
            if (self._started_at is not None
                    and observation.now_ms - self._started_at >= self.engagement_timeout_ms):
                self._cancel_reason = "listed_engagement_timeout"
            return True
        self._candidate = next((candidate for candidate in candidates
                                if (candidate.revision, candidate.entry.entry_id)
                                not in self._quarantined), None)
        return self._candidate is not None

    def advance(self, observation: PvEObservation) -> ListedCombatUpdate:
        if not self.active:
            candidate = self._candidate
            if candidate is None or observation.population is None:
                raise RuntimeError("listed combat advance requires prepared intent")
            self.require_current()
            local_key = observation.population.local_player_object_key
            if local_key is None:
                raise ValueError("listed combat requires exact local player key")
            try:
                self.session.require_combat_available(self.grant)
                # Even a START that expires without entering must not leave the
                # interrupted PvE action running while the host later recovers.
                # pause() proves NativeStop under this exact unchanged Grant.
                self.session.pause(self.grant, str(uuid4()))
                self._ticket, self._command = self.store.register_combat_admission(
                    candidate.entry.entry_id, expected_revision=candidate.revision,
                    client_pid=self.grant.process_identity.process_id,
                    client_creation=self.grant.process_identity.creation_filetime_utc,
                    host=self.grant.host, window=self.grant.window, grant=self.grant.ownership,
                    local_key=local_key,
                )
            except Exception as exc:
                self._candidate = None
                raise ListedCombatInterruptionError(
                    f"listed interruption failed:{type(exc).__name__}"
                ) from exc
            self._started_at = observation.now_ms
            self._quarantined.add((candidate.revision, candidate.entry.entry_id))
            return self._submit(Verb.START)
        if self._cancel_reason:
            return self.cancel(self._cancel_reason)
        return self._submit(Verb.STATUS)

    def cancel(self, reason: str = "listed_combat_cancelled") -> ListedCombatUpdate:
        if not self.active:
            self._candidate = None
            return ListedCombatUpdate(reason, None)
        self._cancel_reason = reason
        self._cleanup_attempts += 1
        try:
            # Revocation precedes native cleanup; no subsequent entry can race it.
            self._ticket.revoke(timeout_ms=750)
        except Exception as exc:
            return self._unconfirmed(f"listed_revoke_failure:{type(exc).__name__}")
        return self._submit(Verb.CANCEL)

    def finish(self, reason: str) -> ListedCombatUpdate:
        """Bounded terminal cleanup; failed confirmation retains the ticket handles."""
        update = ListedCombatUpdate(reason, None)
        for _ in range(3):
            update = self.cancel(reason)
            if not self.active:
                return update
        return ListedCombatUpdate(
            update.reason, update.request, update.receipt,
            terminal_reason="listed_combat_cleanup_unconfirmed",
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.finish("listed_scope_closed")
        if self.active:
            raise RuntimeError("listed combat cleanup remains unconfirmed")

    def _unconfirmed(self, reason: str) -> ListedCombatUpdate:
        assert self._command is not None
        return ListedCombatUpdate(
            reason, self._command.binding.request.hex(),
            terminal_reason=("listed_combat_cleanup_unconfirmed"
                             if self._cleanup_attempts >= 3 else None),
        )

    def _submit(self, verb: Verb) -> ListedCombatUpdate:
        assert self._command is not None and self._ticket is not None
        request = self._command.binding.request.hex()
        try:
            receipt = self.session.combat(self.grant, verb, self._command)
        except Exception as exc:
            # Transport/decoding failures cannot prove whether START entered.
            # Never manufacture a second START or drop the original admission.
            self._cancel_reason = f"listed_combat_unconfirmed:{type(exc).__name__}"
            return self._unconfirmed(self._cancel_reason)
        if receipt.cleanup_confirmed:
            try:
                self._ticket.close(timeout_ms=750)
            except Exception as exc:
                self._cancel_reason = f"listed_ticket_release_failure:{type(exc).__name__}"
                return self._unconfirmed(self._cancel_reason)
            retired = receipt.phase is Phase.RETIRED
            self._ticket = self._command = self._candidate = None
            self._cancel_reason = self._started_at = None
            self._cleanup_attempts = 0
            return ListedCombatUpdate(
                "listed_scene_retired" if retired else "listed_local_cleanup_confirmed",
                request, receipt, recovered=not retired,
                terminal_reason="listed_combat_scene_retired" if retired else None,
            )
        if (receipt.outcome not in (Outcome.CLIENT_OUTBOUND_QUEUED, Outcome.OBSERVED)
                or receipt.phase is not Phase.ENGAGED):
            self._cancel_reason = f"listed_native_{receipt.outcome.name.lower()}"
        return ListedCombatUpdate(
            self._cancel_reason or "listed_combat_engaged", request, receipt,
            terminal_reason=("listed_combat_cleanup_unconfirmed"
                             if self._cleanup_attempts >= 3 else None),
        )
