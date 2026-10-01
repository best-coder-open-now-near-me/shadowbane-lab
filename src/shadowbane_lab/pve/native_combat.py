"""One native engagement owner for NPC and saved manual-player actions."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from shadowbane_lab.client_extension.combat_wire_v2 import (
    CLEANUP_REQUIRED,
    OUTBOUND_QUEUED,
    Action,
    ClosureProof,
    Command,
    Outcome,
    Phase,
    Receipt,
    Verb,
    identity_digest,
)
from shadowbane_lab.client_extension.movement_wire import Outcome as MovementOutcome
from shadowbane_lab.pve.model import (
    PvECombatAcknowledgement,
    PvECombatCleanupResult,
    PvECombatDisposition,
    PvECombatKind,
    PvECombatProposal,
)


@dataclass(frozen=True, slots=True)
class NativeCombatUpdate:
    acknowledgement: PvECombatAcknowledgement
    receipt: Receipt | None = None
    detail: str | None = None

    def as_dict(self):
        value = self.receipt
        return {
            "disposition": self.acknowledgement.disposition.value,
            "native_entered": self.acknowledgement.native_entered,
            "cleanup_required": self.acknowledgement.cleanup_required,
            "engagement": None if value is None else value.engagement.encode().hex(),
            "request": None if value is None else value.request.encode().hex(),
            "verb": None if value is None else value.verb.name.lower(),
            "action": None if value is None else value.action.name.lower(),
            "power_id": None if value is None else value.power_id,
            "outcome": None if value is None else value.outcome.name.lower(),
            "flags": None if value is None else value.flags,
            "entry_state": None if value is None else value.entry_state.name.lower(),
            "phase": None if value is None else value.phase.name.lower(),
            "closure": None if value is None else value.closure.name.lower(),
            "outbound_queued": None if value is None else bool(value.flags & OUTBOUND_QUEUED),
            "binding_digest": None if value is None else value.binding_digest.hex(),
            "detail": self.detail,
        }


class NativeCombatCoordinator:
    """Retain exact action IDs through timeouts and cleanup through ownership loss.

    Only correlated receipts supply action or closure evidence. Policy and object
    observations choose work; diagnostic text never changes admission or state.
    """

    def __init__(self, *, session, grant, population, character_session, store) -> None:
        self.session, self.grant = session, grant
        self.population, self.character_session, self.store = population, character_session, store
        session.require_combat_available(grant)
        self._ids = session.combat_ordinals(grant)
        self._ticket = self._binding = self._command = None
        self._proposal = self._verb = self._stop_command = None
        self._target_token = self._target_key = None
        self._last_receipt = None
        self._cleanup_obligation = None
        self._last_stop_result = (False, None, "native cleanup not confirmed")
        self._adopted = False
        self._pause_key = None
        self._stopping = False
        self._pending_since = None

    @property
    def actor_key(self):
        return self.character_session.binding.object_key

    @property
    def active(self):
        return self._ticket is not None or self._adopted

    @property
    def pending(self):
        return self._proposal

    @property
    def engagement(self):
        return None if self._binding is None else self._binding.engagement

    def _uncertain(self, detail):
        return NativeCombatUpdate(PvECombatAcknowledgement(
            PvECombatDisposition.UNCERTAIN, None, True), detail=detail)

    def _bind(self, proposal, observation, listed):
        from shadowbane_lab.client_extension.combat_fence_windows import create_npc_engagement

        self.character_session.require_current()
        frame = observation.population
        if frame is None or frame.local_player_object_key is None:
            raise ValueError("combat requires a coherent local object key")
        actor, target = self.population.resolve_combat_addresses(
            local_key=frame.local_player_object_key, target_token=proposal.target_token,
            target_key=proposal.target_key,
        )
        if frame.local_player_object_key != self.character_session.binding.object_key:
            raise ValueError("combat actor differs from native character lifetime")
        engagement = self._ids.next_engagement()
        common = dict(
            client_pid=self.grant.process_identity.process_id,
            client_creation=self.grant.process_identity.creation_filetime_utc,
            host=self.grant.host, grant=self.grant.ownership,
            local_key=frame.local_player_object_key, engagement=engagement,
            actor_address_hint=actor, target_address_hint=target,
        )
        if listed is None:
            ticket, binding = create_npc_engagement(
                **common, target_key=proposal.target_key,
                owner_digest=bytes.fromhex(self.store.owner.storage_key),
            )
        else:
            if (listed.character.token != proposal.target_token
                    or listed.character.object_key != proposal.target_key):
                raise ValueError("manual authority differs from exact proposed target")
            ticket, binding = self.store.register_combat_engagement(
                listed.entry.entry_id, expected_revision=listed.revision, **common,
            )
        self._ticket, self._binding = ticket, binding
        self._target_token, self._target_key = proposal.target_token, proposal.target_key
        self._adopted = proposal.adopted_existing_action

    def advance(self, proposal, observation, *, listed=None):
        if not isinstance(proposal, PvECombatProposal):
            raise ValueError("native combat requires a typed immutable proposal")
        if self._proposal is not None and proposal != self._proposal:
            raise ValueError("another immutable native action remains unresolved")
        if (self._adopted and self._binding is None and not proposal.adopted_existing_action):
            raise ValueError("adopted native action still requires binding or cleanup")
        if self._stopping:
            confirmed, receipt, detail = self.stop("native_action_resolution_timeout")
            if confirmed:
                return NativeCombatUpdate(PvECombatAcknowledgement(
                    PvECombatDisposition.REJECTED, None, False), receipt, detail)
            return self._uncertain("native engagement cleanup pending")
        if self._proposal is not None:
            if proposal != self._proposal:
                raise ValueError("another immutable native action remains unresolved")
            if observation.now_ms - self._pending_since >= 5_000:
                self._stopping = True
                return self.advance(proposal, observation, listed=listed)
            return self.poll_pending()
        if proposal.kind is PvECombatKind.SELF_POWER:
            self.session.require_combat_available(self.grant, self_power=True)
        if self._cleanup_obligation is None:
            self._cleanup_obligation = self.session.cleanup.register(self.grant)
            self._last_stop_result = (False, None, "native cleanup not confirmed")
        # Adoption creates a cleanup obligation before its BIND can be acknowledged.
        if proposal.adopted_existing_action:
            if self.active and (proposal.target_token, proposal.target_key) != (
                self._target_token, self._target_key,
            ):
                raise ValueError("adopted action already owns another exact target")
            self._target_token, self._target_key = proposal.target_token, proposal.target_key
            self._adopted = True
        if self._binding is None:
            try:
                self._bind(proposal, observation, listed)
            except BaseException:
                if not self.active:
                    self.session.cleanup.release(self._cleanup_obligation)
                    self._cleanup_obligation = None
                raise
        else:
            if (proposal.target_token != self._target_token
                    or (proposal.target_key.object_type, proposal.target_key.object_uuid)
                    != self._binding.target_key):
                raise ValueError("retarget requires exact engagement cleanup first")
            self.character_session.require_current()
            actor, target = self.population.resolve_combat_addresses(
                local_key=observation.population.local_player_object_key,
                target_token=proposal.target_token, target_key=proposal.target_key,
            )
            if (actor, target) != (self._binding.actor_address_hint,
                                   self._binding.target_address_hint):
                raise ValueError("combat object address changed")
        kind = {PvECombatKind.BIND: Action.NONE, PvECombatKind.ATTACK: Action.ATTACK,
                PvECombatKind.CAST: Action.CAST,
                PvECombatKind.SELF_POWER: Action.SELF_POWER}[proposal.kind]
        identity = self.character_session.binding.identity
        command = Command(
            self.grant.host, self.grant.window, self.grant.ownership, self._binding,
            self._ids.next_request(self._binding.engagement), kind, proposal.power_id,
            identity_digest(identity.character_name), identity_digest(identity.server_name),
        )
        verb = Verb.BIND_ENGAGEMENT if kind is Action.NONE else Verb.SUBMIT
        command.require_verb(verb)
        self._proposal, self._command, self._verb = proposal, command, verb
        self._pending_since = observation.now_ms
        return self._send(verb)

    def poll_pending(self):
        if self._proposal is None:
            raise ValueError("no pending native action")
        return self._send(Verb.ENGAGEMENT_STATUS if self._command.action is Action.NONE
                          else Verb.ACTION_STATUS)

    def _send(self, verb):
        try:
            result = self.session.combat(self.grant, verb, self._command)
            receipt = result.receipt
            receipt.require_command(self._command, verb)
        except Exception as exc:
            return self._uncertain(f"native receipt unavailable:{type(exc).__name__}")
        self._last_receipt = receipt
        cleanup = bool(receipt.flags & CLEANUP_REQUIRED) or self._adopted
        disposition = PvECombatDisposition.UNCERTAIN
        if receipt.phase is Phase.BOUND and receipt.outcome not in (
            Outcome.UNCERTAIN, Outcome.PENDING, Outcome.HISTORY_EXPIRED,
        ):
            if self._command.action is Action.NONE and receipt.outcome in (
                Outcome.BOUND, Outcome.OBSERVED,
            ):
                disposition = PvECombatDisposition.BOUND
            elif receipt.flags & OUTBOUND_QUEUED:
                disposition = PvECombatDisposition.QUEUED
        if receipt.outcome is Outcome.DEFERRED:
            disposition = PvECombatDisposition.DEFERRED
        elif receipt.outcome in (Outcome.NATIVE_REJECTED, Outcome.STALE, Outcome.INVALID,
                                 Outcome.UNAVAILABLE, Outcome.EXHAUSTED,
                                 Outcome.ACTION_CANCELLED, Outcome.ENGAGEMENT_CLOSED):
            disposition = PvECombatDisposition.REJECTED
        # A historical action in a closed/retired engagement cannot authorize new input.
        if receipt.phase in (Phase.CLOSED, Phase.RETIRED):
            if receipt.closure is ClosureProof.NEVER_BOUND and not self._adopted:
                self._release()
                cleanup = False
            elif receipt.cleanup_confirmed:
                self._release()
                cleanup = False
                disposition = PvECombatDisposition.REJECTED
        acknowledgement = PvECombatAcknowledgement(disposition, receipt.native_entered, cleanup)
        if disposition is not PvECombatDisposition.UNCERTAIN:
            self._proposal = None
        return NativeCombatUpdate(acknowledgement, receipt, result.native_detail)

    def _release(self):
        if self._ticket is not None:
            self._ticket.close(timeout_ms=self.session.cleanup.timeout_ms(self.grant, 750))
        self._ticket = self._binding = self._command = self._proposal = None
        self._verb = self._stop_command = self._target_token = self._target_key = None
        self._adopted = self._stopping = False
        self._pause_key = None
        if self._cleanup_obligation is not None:
            self.session.cleanup.release(self._cleanup_obligation)
            self._cleanup_obligation = None

    def observe(self):
        if self._binding is None:
            return self._last_receipt, None
        identity = self.character_session.binding.identity
        command = Command(
            self.grant.host, self.grant.window, self.grant.ownership, self._binding,
            self._ids.next_request(self._binding.engagement), Action.NONE, 0,
            identity_digest(identity.character_name), identity_digest(identity.server_name),
        )
        try:
            result = self.session.combat(self.grant, Verb.ENGAGEMENT_STATUS, command)
            result.receipt.require_command(command, Verb.ENGAGEMENT_STATUS)
            self._last_receipt = result.receipt
            return result.receipt, result.native_detail
        except Exception as exc:
            return None, f"native engagement status unavailable:{type(exc).__name__}"

    def stop(self, reason):
        if self._cleanup_obligation is not None:
            self.session.cleanup.begin(self._cleanup_obligation)
        self._last_stop_result = self._stop_once(reason)
        return self._last_stop_result

    def _stop_once(self, reason):
        if not self.active:
            return True, self._last_receipt, None
        self._stopping = True
        try:
            if self._ticket is not None:
                self._ticket.revoke(timeout_ms=self.session.cleanup.timeout_ms(self.grant, 750))
            if self._binding is not None:
                if self._stop_command is None:
                    identity = self.character_session.binding.identity
                    self._stop_command = Command(
                        self.grant.host, self.grant.window, self.grant.ownership, self._binding,
                        self._ids.next_request(self._binding.engagement), Action.NONE, 0,
                        identity_digest(identity.character_name),
                        identity_digest(identity.server_name),
                    )
                result = self.session.combat(self.grant, Verb.STOP_ENGAGEMENT, self._stop_command)
                receipt = result.receipt
                receipt.require_command(self._stop_command, Verb.STOP_ENGAGEMENT)
                self._last_receipt = receipt
                if receipt.cleanup_confirmed:
                    self._release()
                    return True, receipt, result.native_detail
                if receipt.closure is not ClosureProof.NEVER_BOUND:
                    return False, receipt, result.native_detail
                if not self._adopted:
                    self._release()
                    return True, receipt, result.native_detail
            if self._adopted:
                # Unknown STOP never proves that an already-running adopted action stopped.
                self._pause_key = self._pause_key or str(uuid4())
                value = self.session.pause(self.grant, self._pause_key)
                if (value.outcome != MovementOutcome.ACCEPTED or value.grant != self.grant.ownership
                        or value.host != self.grant.host or value.window != self.grant.window
                        or value.request_key != self._pause_key):
                    raise RuntimeError("adopted native cleanup acknowledgement differs")
                self._release()
                return True, self._last_receipt, None
        except Exception as exc:
            return False, self._last_receipt, f"{reason}:{type(exc).__name__}"
        return False, self._last_receipt, reason

    def cleanup(self, request):
        if self.active and (request.target_token, request.object_key) != (
            self._target_token, self._target_key,
        ):
            raise ValueError("cleanup target differs from owned engagement")
        confirmed, receipt, detail = self.finish(request.reason)
        key = str(uuid4()) if receipt is None else receipt.engagement.encode().hex()
        return PvECombatCleanupResult(
            request, confirmed, key, None if confirmed else (detail or "native cleanup pending")
        )

    def finish(self, reason):
        obligation = self._cleanup_obligation
        if obligation is None:
            return self.stop(reason)
        return self.session.cleanup.settle(obligation, lambda: self.stop(reason),
                                           self._last_stop_result)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        if not self.finish("combat_scope_closed")[0]:
            raise RuntimeError("native combat cleanup remains unconfirmed")
