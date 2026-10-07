"""One actor owner, producer and local-action arbiter across preparation and targets."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace

from shadowbane_lab.client_extension.actor_action_fence import (
    ActorBinding,
    Authority,
    ContextBinding,
    ContextId,
    OwnerId,
    RequestId,
    Ticket,
)
from shadowbane_lab.client_extension.actor_action_wire import (
    CONTEXT_CLEANUP,
    OUTBOUND_QUEUED,
    OWNER_CLEANUP,
    ZERO_DIGEST,
    Action,
    Closure,
    ClosureScope,
    Command,
    Entry,
    LocalSettlement,
    Outcome,
    Phase,
    Receipt,
    Recipient,
    Verb,
)
from shadowbane_lab.client_extension.combat_wire_v2 import identity_digest, operation_digest
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationSnapshotChanged,
)
from shadowbane_lab.pve.model import (
    PvECombatAcknowledgement,
    PvECombatCleanupResult,
    PvECombatDisposition,
    PvECombatKind,
    PvECombatNotReadyReason,
    PvECombatProposal,
)


@dataclass(frozen=True, slots=True)
class ActorResult:
    receipt: Receipt | None
    detail: str | None = None


class NativeActorCoordinator:
    """One exact parent cleanup obligation; child closure never releases that owner.

    A successful enqueue and local action settlement are separate. A retained
    local action is polled, never republished; remote application history remains
    native-owned after local settlement and across child-context changes.
    """

    def __init__(
        self,
        *,
        session,
        grant,
        population,
        character_session,
        store,
        manifest=None,
        publication_reader=None,
        ticket_factory=Ticket,
    ):
        session.require_actor_actions(grant)
        self.session, self.grant = session, grant
        self.population, self.character_session, self.store = population, character_session, store
        self.manifest, self.publication_reader = manifest, publication_reader
        self._ticket_factory = ticket_factory
        self._ids = session.actor_ordinals(grant)
        character_session.require_current()
        token, key, _ = population.observe_actor_identity()
        if key != character_session.binding.object_key:
            raise ValueError("parent actor differs from captured character")
        hint = population.resolve_actor_address(local_key=key, token=token)
        identity = character_session.binding.identity
        self.actor_token, self.actor_key = token, key
        self.parent = ActorBinding(
            grant.process_identity.process_id,
            grant.host.process_id,
            grant.process_identity.creation_filetime_utc,
            grant.host.creation_filetime,
            grant.host.lease_generation,
            grant.ownership.generation,
            grant.ownership.scene,
            self._ids.next(OwnerId),
            (key.object_type, key.object_uuid),
            hint,
            identity_digest(identity.character_name),
            identity_digest(identity.server_name),
            bytes.fromhex(store.owner.storage_key),
            operation_digest(grant.ownership),
        )
        self._parent_ticket = ticket_factory(self.parent, create=True)
        try:
            self._parent_ticket.arm()
            self._obligation = session.cleanup.register(grant)
        except BaseException:
            self._parent_ticket.close()
            raise
        self._open_command = self._command()
        self._open_sent = self._opened = self._closed = False
        self.context = self._context_ticket = self._attach_command = None
        self._attach_sent = self._attached = False
        self._target_token = self._target_key = None
        self._local_command = self._local_receipt = None
        self._combat_proposal = self._combat_command = None
        self._combat_started = None
        self._stop_context_command = self._stop_owner_command = None
        self._last_receipt = None
        self._last_context_result = (False, None, "context cleanup unconfirmed")
        self._last_owner_result = (False, None, "actor cleanup unconfirmed")
        self._terminal = False
        self._adopted = False
        self._manifest_mapping = self._register_command = None
        self._registered = False
        self._settings = self._publication = self._preparation_policy = None
        self._preparation_capture_identity = None
        self._preparation_capture_sequence = 0
        self._preparation_capture_revoked = False
        self._preparation_before_combat = None
        self.latest_preparation_status = None
        self._last_preparation_receipt = self._last_preparation_command = None
        self._preparation_proposal = self._preparation_command = None
        self._preparation_last_response = None
        self._preparation_publication = self._preparation_decision = None
        self._status_observation = None
        self._status_capture_sequence = 0
        self._status_captured_at = None

    def _command(self, *, context=None, action=Action.NONE, power_id=0, **kwargs):
        return Command(
            self.grant.host,
            self.grant.window,
            self.grant.ownership,
            self._ids.next(RequestId),
            self.parent.owner_id,
            None if context is None else context.context_id,
            self.parent.digest,
            ZERO_DIGEST if context is None else context.digest,
            action,
            power_id,
            recipient=(
                Recipient.NONE
                if action is Action.NONE
                else Recipient.ACTOR
                if action in (Action.SELF_POWER, Action.USE_ITEM)
                else Recipient.TARGET
            ),
            **kwargs,
        )

    @property
    def active(self):
        return self.context is not None or self._adopted

    @property
    def cleanup_expired(self):
        deadline = self._obligation.deadline
        return deadline is not None and self.session.cleanup.clock() >= deadline

    @property
    def pending(self):
        return self._combat_proposal

    @property
    def engagement(self):
        return None if self.context is None else self.context.context_id

    def _current_actor_identity(self):
        self.character_session.require_current()
        token, key, _ = self.population.observe_actor_identity()
        if (token, key) != (self.actor_token, self.actor_key):
            raise ValueError("parent actor lifetime changed")
        return token, key

    def _current(self):
        token, key = self._current_actor_identity()
        try:
            hint = self.population.resolve_actor_address(local_key=key, token=token)
        except NativeCharacterPopulationSnapshotChanged:
            # Unrelated membership churn must not conceal a changed local lifetime.
            self._current_actor_identity()
            raise
        if hint != self.parent.actor_hint:
            raise ValueError("parent actor address changed")

    def _send(self, verb, command):
        try:
            result = self.session.actor_action(
                self.grant,
                verb,
                command,
                parent=self.parent,
                context=self.context if command.context_id is not None else None,
            )
            result.receipt.require_command(command, verb)
            self._last_receipt = result.receipt
            return ActorResult(result.receipt, result.native_detail)
        except Exception as exc:
            return ActorResult(None, f"actor receipt unavailable:{type(exc).__name__}")

    def _ensure_open(self):
        if self._closed or self._terminal:
            raise RuntimeError("parent actor owner is terminal")
        self._current()
        if self._opened:
            return True
        result = self._send(
            Verb.OWNER_STATUS if self._open_sent else Verb.OPEN_OWNER, self._open_command
        )
        self._open_sent = True
        receipt = result.receipt
        self._opened = bool(
            receipt is not None
            and receipt.owner_phase is Phase.BOUND
            and receipt.outcome in (Outcome.BOUND, Outcome.OBSERVED)
            and receipt.flags == OWNER_CLEANUP
        )
        return self._opened

    def _attach(self, proposal, observation, listed):
        frame = observation.population
        if frame is None or frame.local_player_object_key != self.actor_key:
            raise ValueError("target binding requires coherent exact actor population")
        actor, target = self.population.resolve_combat_addresses(
            local_key=self.actor_key,
            target_token=proposal.target_token,
            target_key=proposal.target_key,
        )
        if actor != self.parent.actor_hint:
            raise ValueError("target context belongs to a different actor address")
        if self.context is None:
            identifier = self._ids.next(ContextId)
            if listed is None:
                binding = ContextBinding(
                    self.parent.digest,
                    identifier,
                    Authority.NPC,
                    target,
                    (proposal.target_key.object_type, proposal.target_key.object_uuid),
                    0,
                    ZERO_DIGEST,
                    ZERO_DIGEST,
                    ZERO_DIGEST,
                )
                ticket = self._ticket_factory(binding, parent=self.parent, create=True)
                try:
                    ticket.arm()
                except BaseException:
                    ticket.close()
                    raise
            else:
                if (listed.character.token, listed.character.object_key) != (
                    proposal.target_token,
                    proposal.target_key,
                ):
                    raise ValueError("manual context differs from proposed object")
                ticket, binding = self.store.register_actor_context(
                    listed.entry.entry_id,
                    expected_revision=listed.revision,
                    parent=self.parent,
                    context_id=identifier,
                    target_hint=target,
                )
            self.context, self._context_ticket = binding, ticket
            self._target_token, self._target_key = proposal.target_token, proposal.target_key
            self._attach_command = self._command(context=binding)
        elif (
            self._target_token != proposal.target_token
            or self._target_key != proposal.target_key
            or target != self.context.target_hint
        ):
            raise ValueError("target replacement requires exact child closure")
        if self._attached:
            return ActorResult(self._last_receipt)
        # ATTACH replay is immutable and carries no action input.
        result = self._send(
            Verb.CONTEXT_STATUS if self._attach_sent else Verb.ATTACH_CONTEXT, self._attach_command
        )
        self._attach_sent = True
        receipt = result.receipt
        self._attached = bool(
            receipt is not None
            and receipt.owner_phase is Phase.BOUND
            and receipt.context_phase is Phase.BOUND
            and receipt.outcome in (Outcome.BOUND, Outcome.OBSERVED)
        )
        return result

    def _local_ready(self):
        if self._local_command is None:
            return True
        command = self._local_command
        self._local_receipt = None
        result = self._send(Verb.ACTION_STATUS, command)
        if result.receipt is not None and self._local_command == command:
            self._local_receipt = result.receipt
        if command == self._preparation_command:
            # A competing lane may poll this action, but its original policy
            # still owns the receipt and remote-application bookkeeping.
            acknowledgement = self._preparation_result(result, self._preparation_proposal, command)
            self._preparation_policy.acknowledge(acknowledgement)
        if result.receipt is None:
            return False
        if result.receipt.owner_phase is not Phase.BOUND:
            return False
        if command.context_id is not None and result.receipt.context_phase is not Phase.BOUND:
            return False
        if result.receipt.local_settlement is not LocalSettlement.SETTLED:
            return False
        if self._local_command == command:
            self._local_command = self._local_receipt = None
        return self._local_command is None

    @staticmethod
    def _live_local_response(command, receipt):
        return (
            receipt is not None
            and receipt.owner_phase is Phase.BOUND
            and (command.context_id is None or receipt.context_phase is Phase.BOUND)
            and (
                receipt.local_settlement is LocalSettlement.SETTLED
                or (
                    receipt.local_settlement is LocalSettlement.PENDING
                    and receipt.outcome
                    in (Outcome.CLIENT_OUTBOUND_QUEUED, Outcome.PENDING, Outcome.UNCERTAIN)
                )
            )
        )

    @staticmethod
    def _uncertain(detail):
        from .native_combat import NativeCombatUpdate

        return NativeCombatUpdate(
            PvECombatAcknowledgement(PvECombatDisposition.UNCERTAIN, None, True), detail=detail
        )

    def advance_combat(self, proposal, observation, *, listed=None):
        from .native_combat import NativeCombatUpdate

        if not isinstance(proposal, PvECombatProposal):
            raise ValueError("typed immutable combat proposal required")
        if self._stop_context_command is not None or self._terminal:
            return self._uncertain("actor context settlement is pending")
        if self._combat_proposal is not None and proposal != self._combat_proposal:
            raise ValueError("another immutable combat proposal is unresolved")
        if self._adopted and (proposal.target_token, proposal.target_key) != (
            self._target_token,
            self._target_key,
        ):
            raise ValueError("adopted native action retains its exact target")
        if self._adopted and not proposal.adopted_existing_action and self.context is None:
            raise ValueError("adopted action requires binding or cleanup first")
        if self._combat_proposal is None:
            self._combat_proposal, self._combat_started = proposal, observation.now_ms
            if proposal.adopted_existing_action:
                self._adopted = True
                self._target_token, self._target_key = proposal.target_token, proposal.target_key
        waiting_local = False
        if self._combat_command is None and self._local_command is not None:
            if not self._ensure_open():
                return self._uncertain("actor owner admission unconfirmed")
            prior_command = self._local_command
            waiting_local = not self._local_ready()
            if not waiting_local or self._live_local_response(prior_command, self._local_receipt):
                # This proposal has not entered. A current response for the
                # original action is progress, not a failed combat transport.
                # Missing/mismatched replies never renew this deadline.
                self._combat_started = observation.now_ms
        if observation.now_ms - self._combat_started >= 5_000:
            confirmed, receipt, detail = self.stop_context("action_resolution_timeout")
            if confirmed:
                return NativeCombatUpdate(
                    PvECombatAcknowledgement(PvECombatDisposition.REJECTED, None, False),
                    receipt,
                    detail,
                )
            return self._uncertain(detail)
        if waiting_local:
            return self._uncertain("previous local action settlement pending")
        if not self._ensure_open():
            return self._uncertain("actor owner admission unconfirmed")
        if self._combat_command is None:
            if not self._local_ready():
                return self._uncertain("previous local action settlement pending")
            result = self._attach(proposal, observation, listed)
            if not self._attached:
                if result.receipt is not None and result.receipt.context_phase in (
                    Phase.CLOSED,
                    Phase.RETIRED,
                ):
                    confirmed, receipt, detail = self.stop_context("context_admission_refused")
                    if confirmed:
                        return NativeCombatUpdate(
                            PvECombatAcknowledgement(PvECombatDisposition.REJECTED, None, False),
                            receipt,
                            detail,
                        )
                return self._uncertain(result.detail or "target context admission unconfirmed")
            if proposal.kind is PvECombatKind.BIND:
                self._combat_proposal = None
                return NativeCombatUpdate(
                    PvECombatAcknowledgement(PvECombatDisposition.BOUND, None, True),
                    result.receipt,
                    result.detail,
                )
            action = {
                PvECombatKind.ATTACK: Action.ATTACK,
                PvECombatKind.CAST: Action.CAST,
                PvECombatKind.SELF_POWER: Action.SELF_POWER,
            }[proposal.kind]
            self._combat_command = self._command(
                context=self.context, action=action, power_id=proposal.power_id
            )
            self._local_command = self._combat_command
            result = self._send(Verb.SUBMIT, self._combat_command)
        else:
            result = self._send(Verb.ACTION_STATUS, self._combat_command)
        return self._combat_result(result)

    def _combat_result(self, result):
        from .native_combat import NativeCombatUpdate

        r = result.receipt
        if r is None:
            return self._uncertain(result.detail)
        live = r.owner_phase is Phase.BOUND and r.context_phase is Phase.BOUND
        disposition, reason = PvECombatDisposition.UNCERTAIN, None
        if (
            live
            and r.flags & OUTBOUND_QUEUED
            and r.outcome not in (Outcome.UNCERTAIN, Outcome.PENDING, Outcome.HISTORY_EXPIRED)
        ):
            disposition = PvECombatDisposition.QUEUED
        elif live and r.outcome is Outcome.POWER_REUSE_BLOCKED and r.entry is Entry.NEVER_ENTERED:
            disposition = PvECombatDisposition.NOT_READY
            reason = PvECombatNotReadyReason.POWER_REUSE
        elif r.outcome is Outcome.DEFERRED and r.entry is Entry.NEVER_ENTERED:
            disposition = PvECombatDisposition.DEFERRED
        elif (
            r.outcome
            in (
                Outcome.NATIVE_REJECTED,
                Outcome.STALE,
                Outcome.INVALID,
                Outcome.UNAVAILABLE,
                Outcome.EXHAUSTED,
                Outcome.ACTION_CANCELLED,
                Outcome.ENGAGEMENT_CLOSED,
            )
            or not live
        ):
            disposition = PvECombatDisposition.REJECTED
        if not live:
            disposition, reason = PvECombatDisposition.REJECTED, None
        command = self._combat_command
        if r.local_settlement is LocalSettlement.SETTLED and self._local_command == command:
            self._local_command = self._local_receipt = None
        if disposition is not PvECombatDisposition.UNCERTAIN:
            self._combat_proposal = self._combat_command = None
        entered = None if r.entry is Entry.UNKNOWN else r.entry is Entry.ENTERED
        return NativeCombatUpdate(
            PvECombatAcknowledgement(disposition, entered, bool(r.flags & CONTEXT_CLEANUP), reason),
            r,
            result.detail,
            command,
        )

    def observe_context(self):
        if self.context is None:
            return self._last_receipt, None
        result = self._send(Verb.CONTEXT_STATUS, self._command(context=self.context))
        return result.receipt, result.detail

    def stop_context(self, reason):
        if self._stop_owner_command is not None:
            # An aggregate stop is terminal. Never fall back to child-only
            # polling or imply that its parent can continue after this proof.
            self._last_context_result = self._stop_owner_once(reason)
            return self._last_context_result
        if self.context is None:
            if self._adopted:
                return self._stop_owner_once(reason)
            return True, self._last_receipt, None
        if self._stop_context_command is None:
            self._stop_context_command = self._command(context=self.context)
        self.session.cleanup.begin_context(self._obligation, self._stop_context_command)
        try:
            self._context_ticket.revoke(timeout_ms=self.session.cleanup.timeout_ms(self.grant, 750))
            result = self._send(Verb.STOP_CONTEXT, self._stop_context_command)
            r = result.receipt
            if (
                r is not None
                and r.closure_scope is ClosureScope.OWNER
                and r.owner_phase is Phase.RETIRED
                and r.context_phase is Phase.RETIRED
                and r.closure is Closure.SCENE_RETIRED
            ):
                self._release_owner(r, result.detail)
                self._last_context_result = True, r, result.detail
                return self._last_context_result
            if r is not None and r.closure is Closure.NEVER_BOUND and self._adopted:
                return self._stop_owner_once(reason)
            if (
                r is not None
                and r.closure_scope is ClosureScope.CONTEXT
                and r.context_phase is Phase.CLOSED
                and r.owner_phase is Phase.BOUND
                and r.closure
                in (Closure.NATIVE_STOPPED, Closure.LOCAL_RELEASED, Closure.NEVER_BOUND)
            ):
                self._context_ticket.close(
                    timeout_ms=self.session.cleanup.timeout_ms(self.grant, 750)
                )
                if not self.session.cleanup.blocked(self.grant):
                    self.session.cleanup.continue_owner(self._obligation, r)
                self.context = self._context_ticket = self._attach_command = None
                self._attach_sent = self._attached = self._adopted = False
                if (
                    self._local_command is not None
                    and self._local_command.context_id == r.context_id
                ):
                    self._local_command = self._local_receipt = None
                self._combat_proposal = self._combat_command = None
                self._target_token = self._target_key = self._stop_context_command = None
                self._last_context_result = True, r, result.detail
                return self._last_context_result
            command = self._local_command
            if (
                r is not None
                and r.owner_phase is Phase.BOUND
                and r.context_phase is Phase.STOPPING
                and r.closure is Closure.NONE
                and command is not None
                and command.context_id is None
                and command.parent_id == self.parent.owner_id
                and command.parent_digest == self.parent.digest
                and command.grant == self.grant.ownership
                and command.host == self.grant.host
                and command.window == self.grant.window
            ):
                # Native child cleanup cannot cancel a separate parent-owned
                # local action. Stop their exact aggregate owner while the
                # original cleanup budget remains; remote application pending
                # alone does not retain _local_command and cannot trigger this.
                # Keep the returned owner-scope receipt, never a fabricated
                # child closure or permission to resume the parent.
                self._last_context_result = self._stop_owner_once(reason)
                return self._last_context_result
            self._last_context_result = False, r, result.detail or reason
        except Exception as exc:
            self._last_context_result = False, self._last_receipt, f"{reason}:{type(exc).__name__}"
        return self._last_context_result

    def finish_context(self, reason):
        if self.context is None:
            return self.stop_context(reason)
        return self.session.cleanup.settle(
            self._obligation, lambda: self.stop_context(reason), self._last_context_result
        )

    def cleanup_context(self, request):
        if self.active and (request.target_token, request.object_key) != (
            self._target_token,
            self._target_key,
        ):
            raise ValueError("cleanup request differs from retained target")
        confirmed, receipt, detail = self.finish_context(request.reason)
        key = (
            self.parent.owner_id.encode().hex()
            if receipt is None
            else receipt.request.encode().hex()
        )
        return PvECombatCleanupResult(
            request, confirmed, key, None if confirmed else detail or "cleanup unconfirmed",
            owner_closed=bool(confirmed and self._closed),
        )

    def _release_owner(self, receipt, detail):
        self.session.cleanup.request_terminal(self.grant)
        for ticket in (self._context_ticket, self._parent_ticket):
            if ticket is not None:
                ticket.close(timeout_ms=self.session.cleanup.timeout_ms(self.grant, 750))
        self.session.cleanup.release(self._obligation)
        if self._manifest_mapping is not None:
            self._manifest_mapping.close()
        self._closed = self._terminal = True
        self._adopted = False
        self.context = self._context_ticket = None
        self._last_owner_result = True, receipt, detail

    def _stop_owner_once(self, reason):
        if self._closed:
            return self._last_owner_result
        self._terminal = True
        self.session.cleanup.request_terminal(self.grant)
        if self._stop_owner_command is None:
            self._stop_owner_command = self._command()
        self.session.cleanup.begin(self._obligation)
        try:
            self._parent_ticket.revoke(timeout_ms=self.session.cleanup.timeout_ms(self.grant, 750))
            result = self._send(Verb.STOP_OWNER, self._stop_owner_command)
            r = result.receipt
            if (
                r is not None
                and r.closure_scope is ClosureScope.OWNER
                and r.owner_phase in (Phase.CLOSED, Phase.RETIRED)
                and (
                    r.closure in (Closure.NATIVE_STOPPED, Closure.SCENE_RETIRED)
                    or (
                        r.closure in (Closure.NEVER_BOUND, Closure.LOCAL_RELEASED)
                        and not self._adopted
                    )
                )
            ):
                self._release_owner(r, result.detail)
                return self._last_owner_result
            self._last_owner_result = False, r, result.detail or reason
        except Exception as exc:
            self._last_owner_result = False, self._last_receipt, f"{reason}:{type(exc).__name__}"
        return self._last_owner_result

    def finish(self, reason):
        return self.session.cleanup.settle(
            self._obligation, lambda: self._stop_owner_once(reason), self._last_owner_result
        )

    def configure_preparation(self, settings):
        from shadowbane_lab.client_extension.actor_publication import Reader
        from shadowbane_lab.client_extension.actor_selector_manifest import (
            Manifest,
            PublishedManifest,
        )

        from .preparation import ActorIdentity, PreparationPolicy

        if self._settings is not None:
            raise RuntimeError("actor preparation settings are immutable")
        manifest = Manifest.for_settings(
            settings,
            client_pid=self.parent.client_pid,
            client_creation=self.parent.client_creation,
            host=self.grant.host,
            identity=self.character_session.binding.identity,
        )
        if self.manifest is not None and self.manifest != manifest:
            raise ValueError("preparation settings differ from registered manifest")
        self._manifest_mapping = PublishedManifest(manifest)
        self.manifest, self._settings = manifest, settings
        self.publication_reader = self.publication_reader or Reader(
            self.character_session, manifest
        )
        self._register_command = Command(
            self.grant.host,
            self.grant.window,
            None,
            self._ids.next(RequestId),
            None,
            None,
            ZERO_DIGEST,
            ZERO_DIGEST,
            selector_index=0,
            manifest_digest=manifest.digest,
        )
        self._preparation_policy = PreparationPolicy(
            ActorIdentity(
                self.parent.client_pid,
                self.parent.client_creation,
                self.parent.scene,
                self.parent.actor_key,
                self.actor_token,
            ),
            tuple(group.policy_group() for group in settings.groups),
        )
        return self._preparation_policy

    @property
    def preparation_status(self):
        """Immutable presentation snapshot; never refresh native action authority."""
        from .preparation_status import PreparationStatus, capture_status

        if self._settings is None or not self._settings.enabled:
            return PreparationStatus.disabled()
        observation = None if self._closed else self._status_observation
        return capture_status(
            tuple(group.policy_group() for group in self._settings.groups),
            observation,
            self._preparation_decision,
            captured_at=self._status_captured_at if observation is not None else None,
            local_pending=(
                not self._closed
                and (
                    self._local_command is not None
                    or self._preparation_policy.pending_proposal is not None
                )
            ),
            application_pending_groups=self._preparation_policy.application_pending_groups,
        )

    def _item_token(self, facts, publication):
        import hashlib
        import struct

        identity = publication.identity
        return hashlib.sha256(
            b"actor-inventory-v1"
            + identity.actor_lifetime
            + struct.pack(
                "<IQ3I",
                identity.process_id,
                identity.process_creation,
                *facts.item_key,
                facts.item_hint,
            )
        ).hexdigest()

    def observe_preparation(self):
        # Failed refreshes cannot present the previous coverage as current. Keep
        # the last sequence/timestamp separately so rereading the same capture
        # after an unavailable response cannot manufacture a newer timestamp.
        self._status_observation = None
        observation = self._observe_preparation()
        if observation is not None:
            if observation.capture_sequence > self._status_capture_sequence:
                self._status_captured_at = time.time()
                self._status_capture_sequence = observation.capture_sequence
            self._status_observation = observation
        return observation

    def _observe_preparation(self):
        from shadowbane_lab.client_extension import actor_publication as native

        from . import preparation as policy

        if self._settings is None:
            raise RuntimeError("preparation requires configured canonical selectors")
        try:
            self._current()
        except NativeCharacterPopulationSnapshotChanged:
            return None
        if self._preparation_capture_revoked:
            raise native.PublicationError("preparation capture lifetime was revoked")
        if not self._registered:
            result = self.session.actor_action(
                None, Verb.REGISTER_SELECTORS, self._register_command
            )
            result.receipt.require_command(self._register_command, Verb.REGISTER_SELECTORS)
            if result.receipt.outcome is not Outcome.OBSERVED:
                raise native.PublicationError("native selector registration unconfirmed")
            self._registered = True
        command = replace(self._register_command, request=self._ids.next(RequestId))
        result = self.session.actor_action(None, Verb.OBSERVE_ACTOR, command)
        result.receipt.require_command(command, Verb.OBSERVE_ACTOR)
        if result.receipt.outcome is not Outcome.OBSERVED:
            # An unavailable capture cannot lend authority from an older mapping.
            return None
        pub = self.publication_reader.read()
        expected = (
            self.parent.client_pid,
            self.parent.client_creation,
            self.parent.scene,
            self.parent.actor_key,
            self.parent.actor_hint,
            self.manifest.digest,
        )
        actual = (
            pub.identity.process_id,
            pub.identity.process_creation,
            pub.identity.scene,
            pub.identity.actor_key,
            pub.identity.actor_address,
            pub.identity.manifest_digest,
        )
        if actual != expected:
            raise native.PublicationError("preparation publication differs from parent actor")
        # This sequence belongs to the persistent native writer and actor lifetime.
        # It is freshness evidence only; it must not alter semantic/admission epochs.
        if (
            type(pub.sequence) is not int
            or not 0 < pub.sequence < 2**63
            or pub.sequence % 2
            or pub.sequence < self._preparation_capture_sequence
            or (
                self._preparation_capture_identity is not None
                and pub.identity != self._preparation_capture_identity
            )
            or (pub.sequence == self._preparation_capture_sequence and pub != self._publication)
        ):
            self._preparation_capture_revoked = True
            raise native.PublicationError("preparation capture sequence or lifetime changed")
        actor = policy.ActorIdentity(
            self.parent.client_pid,
            self.parent.client_creation,
            self.parent.scene,
            self.parent.actor_key,
            self.actor_token,
        )
        coverage, readiness, pending = [], [], set()
        by_index = {facts.selector.index: facts for facts in pub.actions}
        for index, group in enumerate(self._settings.groups):
            states = []
            selectors = [s for s in self.manifest.selectors if s.group == index]
            for alternative, selector in zip(group.alternatives, selectors, strict=True):
                facts = by_index.get(selector.index)
                state, operand = policy.Readiness.UNKNOWN, None
                covered = policy.Coverage.UNKNOWN
                if facts is not None and pub.complete:
                    if facts.selector != selector:
                        raise native.PublicationError("preparation selector changed")
                    covered = policy.Coverage[facts.coverage.name]
                    if facts.readiness is native.Readiness.READY:
                        state = policy.Readiness.READY
                        operand = (
                            policy.PowerOperand(selector.power_id)
                            if selector.kind == 3
                            else policy.ItemOperand(
                                facts.item_key, self._item_token(facts, pub), facts.template_key
                            )
                        )
                    elif facts.readiness is not native.Readiness.UNKNOWN:
                        state = policy.Readiness.NOT_READY
                readiness.append(
                    policy.ReadinessEvidence(alternative.action.action_id, state, operand)
                )
                states.append(covered)
            # Alternatives are OR coverage: one active form satisfies its group.
            covered = (
                policy.Coverage.PRESENT
                if policy.Coverage.PRESENT in states
                else policy.Coverage.PARTIAL
                if policy.Coverage.PARTIAL in states
                else policy.Coverage.MISSING
                if all(x is policy.Coverage.MISSING for x in states)
                else policy.Coverage.UNKNOWN
            )
            coverage.append(policy.CoverageEvidence(group.group_id, covered))
            digest = self.manifest.group_digest(index)
            if any(x.group_digest == digest and x.state == 1 for x in pub.applications):
                pending.add(group.group_id)
        known_groups = {self.manifest.group_digest(i) for i in range(self.manifest.group_count)}
        if any(x.state == 1 and x.group_digest not in known_groups for x in pub.applications):
            raise native.PublicationError("unmatched pending application prevents preparation")
        self._preparation_capture_identity = pub.identity
        self._preparation_capture_sequence = pub.sequence
        self._publication = pub
        return policy.PreparationObservation(
            actor,
            pub.revision,
            pub.complete,
            tuple(coverage),
            tuple(readiness),
            pub.admission_revision,
            int(pub.admission_blocks),
            frozenset(pending),
            capture_sequence=pub.sequence,
        )

    def advance_preparation(self, proposal):
        from . import preparation as policy

        def ack(
            disposition=policy.Disposition.UNCERTAIN, entry=policy.EntryState.UNKNOWN, settled=False
        ):
            return policy.PreparationAcknowledgement(proposal, disposition, entry, settled)

        self._last_preparation_receipt = self._last_preparation_command = None
        if not isinstance(proposal, policy.PreparationProposal):
            raise ValueError("typed immutable preparation proposal required")
        if self._combat_proposal is not None or self._stop_context_command is not None:
            return ack()
        if self._preparation_proposal is not None and proposal != self._preparation_proposal:
            raise ValueError("another immutable preparation proposal is unresolved")
        if self._preparation_proposal is None:
            self._preparation_proposal = proposal
            self._preparation_publication = self._publication
            self._preparation_last_response = self.session.cleanup.clock()

        if self._preparation_command is not None:
            # Query existing ownership without requiring a coherent unrelated-world census.
            # The original command and native parent fence still validate every response.
            if self._closed or self._terminal or not self._opened:
                raise RuntimeError("pending preparation owner is not open")
            self._current_actor_identity()
            result = self._send(Verb.ACTION_STATUS, self._preparation_command)
            return self._preparation_result(result, proposal, self._preparation_command)
        try:
            opened = self._ensure_open()
        except NativeCharacterPopulationSnapshotChanged:
            # This is unavailable observation, not native refusal or local settlement.
            self._require_preparation_response()
            return ack()
        if not opened:
            self._require_preparation_response()
            return ack()
        if not self._local_ready():
            self._require_preparation_response()
            return ack()
        pub = self._preparation_publication
        expected = policy.ActorIdentity(
            self.parent.client_pid,
            self.parent.client_creation,
            self.parent.scene,
            self.parent.actor_key,
            self.actor_token,
        )
        if (
            pub is None
            or not pub.complete
            or proposal.actor != expected
            or proposal.publication_epoch != pub.revision
            or proposal.admission_revision != pub.admission_revision
            or pub.admission_blocks
        ):
            raise ValueError("preparation proposal has no exact current publication")
        group_index = next(
            (i for i, g in enumerate(self._settings.groups) if g.group_id == proposal.group_id),
            None,
        )
        choices = [
            (s, a.action)
            for s in self.manifest.selectors
            if s.group == group_index
            for a in self._settings.groups[group_index].alternatives
            if a.action == proposal.action
            and (
                (s.kind == 3 and s.power_id == a.action.power_id)
                or (s.kind == 4 and s.template_id == a.action.item_template[0])
            )
        ]
        if len(choices) != 1 or not proposal.action.matches(proposal.operand):
            raise ValueError("preparation action differs from canonical intent")
        selector, _ = choices[0]
        facts = next(x for x in pub.actions if x.selector == selector)
        from shadowbane_lab.client_extension.actor_publication import Readiness

        if facts.readiness is not Readiness.READY:
            raise ValueError("preparation action lacks native ready evidence")
        kwargs = dict(
            selector_index=selector.index,
            manifest_digest=self.manifest.digest,
            publication_revision=pub.revision,
            snapshot_id=pub.snapshot_id,
        )
        if isinstance(proposal.operand, policy.ItemOperand):
            if (
                proposal.operand.item_key != facts.item_key
                or proposal.operand.item_token != self._item_token(facts, pub)
                or proposal.operand.template_key != facts.template_key
            ):
                raise ValueError("preparation item differs from exact published instance")
            kwargs.update(
                item_key=facts.item_key,
                template_key=facts.template_key,
                item_hint=facts.item_hint,
                template_hint=facts.template_hint,
            )
        self._preparation_command = self._command(
            action=Action(selector.kind), power_id=selector.power_id, **kwargs
        )
        self._preparation_proposal = proposal
        self._local_command = self._preparation_command
        result = self._send(Verb.SUBMIT, self._preparation_command)
        return self._preparation_result(result, proposal, self._preparation_command)

    def _require_preparation_response(self):
        # This bounds unavailable status transport, not native action duration.
        # Always try this turn's original request before testing freshness.
        if self.session.cleanup.clock() - self._preparation_last_response >= 5.0:
            self._stop_owner_once("preparation_status_unavailable")
            raise RuntimeError("preparation status response deadline expired")

    def _preparation_result(self, result, proposal, command):
        from . import preparation as policy

        if (
            proposal is None
            or proposal != self._preparation_proposal
            or command is None
            or command != self._preparation_command
        ):
            raise ValueError("preparation receipt has no exact pending command owner")

        def ack(
            disposition=policy.Disposition.UNCERTAIN, entry=policy.EntryState.UNKNOWN, settled=False
        ):
            return policy.PreparationAcknowledgement(proposal, disposition, entry, settled)

        r = result.receipt
        self._last_preparation_receipt = r
        self._last_preparation_command = command
        if r is None:
            self._require_preparation_response()
            return ack()
        # _send validates this fresh transport response against the immutable
        # command and verb. Journal/publication updates cannot renew this bound.
        if self._live_local_response(command, r):
            self._preparation_last_response = self.session.cleanup.clock()
        else:
            self._require_preparation_response()
        disposition = policy.Disposition.UNCERTAIN
        if r.owner_phase is Phase.BOUND:
            if r.flags & OUTBOUND_QUEUED and r.outcome not in (
                Outcome.UNCERTAIN,
                Outcome.PENDING,
                Outcome.HISTORY_EXPIRED,
            ):
                disposition = policy.Disposition.QUEUED
            elif r.entry is Entry.NEVER_ENTERED and r.local_settlement is LocalSettlement.SETTLED:
                disposition = (
                    policy.Disposition.NOT_READY
                    if r.outcome is Outcome.POWER_REUSE_BLOCKED
                    else policy.Disposition.DEFERRED
                    if r.outcome is Outcome.DEFERRED
                    else policy.Disposition.REJECTED
                )
        entry = {
            Entry.UNKNOWN: policy.EntryState.UNKNOWN,
            Entry.ENTERED: policy.EntryState.ENTERED,
            Entry.NEVER_ENTERED: policy.EntryState.NEVER_ENTERED,
        }[r.entry]
        settled = r.local_settlement is LocalSettlement.SETTLED
        if settled:
            if self._local_command == command:
                self._local_command = self._local_receipt = None
            self._preparation_command = self._preparation_proposal = None
            self._preparation_publication = None
        return ack(disposition, entry, settled)

    def preparation_step(self, combat_proposal=None):
        """At most one new ready buff ahead of each still-unpublished combat proposal."""
        self.latest_preparation_status = None
        if self._preparation_policy is None or self._combat_proposal is not None:
            return None
        if self._terminal or self._stop_context_command is not None:
            return None
        pending = self._preparation_policy.pending_proposal
        if pending is None:
            if combat_proposal is not None and combat_proposal == self._preparation_before_combat:
                return None
            if not self._local_ready():
                return None
        observation = self.observe_preparation()
        if observation is None:
            if pending is None:
                return None
            decision = self._preparation_decision
        else:
            decision = self._preparation_policy.advance(observation)
        self._preparation_decision = decision
        if decision.proposal is None:
            if observation is not None and observation.complete and observation.admission_blocks:
                self.latest_preparation_status = NativePreparationStatus(
                    observation.publication_epoch,
                    observation.admission_revision,
                    observation.admission_blocks,
                )
            return None
        if combat_proposal is not None:
            self._preparation_before_combat = combat_proposal
        acknowledgement = self.advance_preparation(decision.proposal)
        self._preparation_policy.acknowledge(acknowledgement)
        return NativePreparationUpdate(
            decision,
            acknowledgement,
            self._last_preparation_receipt,
            self._last_preparation_command,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if not self.finish("actor_scope_closed")[0]:
            raise RuntimeError("native actor cleanup remains unconfirmed")


@dataclass(frozen=True, slots=True)
class NativePreparationUpdate:
    decision: object
    acknowledgement: object
    receipt: Receipt | None
    command: Command | None

    def as_dict(self):
        proposal = self.acknowledgement.proposal
        if self.receipt is not None:
            if self.command is None:
                raise ValueError("preparation receipt requires exact immutable command")
            self.receipt.require_command(self.command, self.receipt.verb)
        r = self.receipt
        return {
            "group": proposal.group_id,
            "action": proposal.action.action_id,
            "sequence": proposal.sequence,
            "publication_revision": proposal.publication_epoch,
            "admission_revision": proposal.admission_revision,
            "disposition": self.acknowledgement.disposition.value,
            "entry_state": self.acknowledgement.entry_state.value,
            "local_settled": self.acknowledgement.local_settled,
            "request": None if r is None else r.request.encode().hex(),
            "command_digest": None if r is None else r.command_digest.hex(),
            "outcome": None if r is None else r.outcome.name.lower(),
            "reason": None if r is None else r.reason.name.lower(),
            "application": None if r is None else r.application.name.lower(),
            "groups": [
                {
                    "group": g.group_id,
                    "coverage": g.coverage.value,
                    "application_pending": g.application_pending,
                }
                for g in self.decision.groups
            ],
        }


@dataclass(frozen=True, slots=True)
class NativePreparationStatus:
    """Trace-only current blockers; never an action acknowledgement or scheduler gate."""

    publication_revision: int
    admission_revision: int
    admission_blocks: int

    def __post_init__(self):
        if (
            any(
                type(v) is not int or not 0 < v < 2**64
                for v in (
                    self.publication_revision,
                    self.admission_revision,
                )
            )
            or type(self.admission_blocks) is not int
            or not 0 < self.admission_blocks <= 31
        ):
            raise ValueError("trace status requires positive revisions and known native blockers")

    def as_dict(self):
        from shadowbane_lab.client_extension.actor_publication import AdmissionBlock

        return {
            "action": None,
            "reason": "native_admission_blocked",
            "publication_revision": self.publication_revision,
            "admission_revision": self.admission_revision,
            "admission_blocks": self.admission_blocks,
            "blockers": [b.name.lower() for b in AdmissionBlock if b & self.admission_blocks],
        }
