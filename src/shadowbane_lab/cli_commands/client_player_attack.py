"""Finite operation-scoped player attack through the existing native actor owner."""
from __future__ import annotations

import hashlib
import json
import math
import time
from contextlib import ExitStack
from dataclasses import dataclass

from shadowbane_lab.client_extension.actor_action_fence import (
    Authority,
    ContextBinding,
    Ticket,
)
from shadowbane_lab.client_extension.actor_action_wire import Phase
from shadowbane_lab.client_extension.combat_wire_v2 import identity_digest
from shadowbane_lab.client_input.stop import observed_stop_cause
from shadowbane_lab.client_observation.native_character_session import open_native_character_session
from shadowbane_lab.client_observation.native_group import (
    load_bundled_native_group_profile,
    open_windows_native_group_reader,
)
from shadowbane_lab.client_observation.native_health import NativeTargetHealthObservation
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterKind,
    load_bundled_native_character_population_profile,
    open_windows_native_character_population_reader,
)
from shadowbane_lab.client_observation.native_vitals import (
    load_bundled_native_vitals_profile,
    open_windows_native_player_vitals_reader,
)
from shadowbane_lab.manager.operation import (
    WorkerOperationExecution,
    WorkerOperationKind,
    WorkerOperationState,
    WorkerPlayerAttackTarget,
)
from shadowbane_lab.pve.attack_list import AttackListOwner
from shadowbane_lab.pve.model import (
    PvECombatDisposition,
    PvECombatKind,
    PvECombatProposal,
    PvEObservation,
)
from shadowbane_lab.pve.native_actor import NativeActorCoordinator
from shadowbane_lab.pve.native_combat import NativeCombatCoordinator
from shadowbane_lab.pve.settings import load_pve_settings


def _key(value):
    return None if value is None else (value.object_type, value.object_uuid)


def _group_keys(group):
    return frozenset((member.object_type, member.object_uuid) for member in group.observe().members)


def resolve_player_attack_target(character_session, population, group, name):
    """Resolve one current loaded first name, never selection or tracking guesses."""
    if (not isinstance(name, str) or not name or name != name.strip()
            or len(name) > 64 or any(c.isspace() or ord(c) < 32 for c in name)):
        raise ValueError("attack requires one player first name")
    character_session.require_current()
    binding = character_session.binding
    protected = _group_keys(group)
    frame = population.observe()
    if frame.local_player_object_key != binding.object_key:
        raise ValueError("player attack local identity changed")
    candidates = []
    for character in frame.characters:
        if (character.character_kind is not NativeCharacterKind.PLAYER
                or character.object_key == binding.object_key):
            continue
        identity = population.observe_player_identity(
            character.token, character.object_key, character_session.reader)
        if identity.character_name.split()[0].casefold() == name.casefold():
            candidates.append((character, identity))
    if len(candidates) != 1:
        raise ValueError("attack player name is missing or ambiguous in current native population")
    character, identity = candidates[0]
    if (not character.attack_eligible or _key(character.object_key) in protected
            or identity.server_name != binding.identity.server_name):
        raise ValueError("attack target is protected, dead, or from another server")
    target = WorkerPlayerAttackTarget(_key(identity.object_key), identity.character_name,
                                     identity.server_name, _key(binding.object_key))
    if _group_keys(group) != protected:
        raise ValueError("group membership changed during player resolution")
    # A second exact-key read closes replacement/disappearance during name discovery.
    _target_frame(character_session, population, group, target, require_alive=True)
    return target


def _target_frame(character_session, population, group, target, *, require_alive=False):
    character_session.require_current()
    binding = character_session.binding
    if (_key(binding.object_key) != target.local_key
            or binding.identity.server_name != target.server):
        raise ValueError("player attack belongs to another native character")
    protected = _group_keys(group)
    if target.object_key in protected:
        raise ValueError("player attack target is now in the current group")
    frame = population.observe()
    if frame.local_player_object_key != binding.object_key:
        raise ValueError("player attack actor identity changed")
    matches = [c for c in frame.characters if _key(c.object_key) == target.object_key]
    if len(matches) != 1:
        raise ValueError("exact player attack target is no longer loaded")
    character = matches[0]
    if (character.character_kind is not NativeCharacterKind.PLAYER or character.protected_roles
            or (require_alive and not character.alive)):
        raise ValueError("exact player attack target is not eligible")
    identity = population.observe_player_identity(
        character.token, character.object_key, character_session.reader)
    if (_key(identity.object_key), identity.character_name, identity.server_name) != (
            target.object_key, target.name, target.server):
        raise ValueError("player attack target name/key/server changed")
    if _group_keys(group) != protected:
        raise ValueError("group membership changed during player observation")
    character_session.require_current()
    return frame, character


@dataclass(frozen=True, slots=True)
class _Entry:
    entry_id: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    entry: _Entry
    revision: int
    character: object


class _OperationPlayerIntent:
    """Immutable finite intent; no saved attack-list file or global membership."""

    def __init__(self, operation, binding):
        self.target = operation.player_target
        self.owner = AttackListOwner(binding.identity.server_name, binding.identity.character_name)
        encoded = json.dumps(operation.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        self.digest = hashlib.sha256(encoded).digest()
        self.entry = _Entry(self.digest.hex())

    def register_actor_context(self, entry_id, *, expected_revision, parent,
                               context_id, target_hint):
        if (entry_id != self.entry.entry_id or expected_revision != 1
                or parent.actor_key != self.target.local_key
                or parent.owner != bytes.fromhex(self.owner.storage_key)
                or parent.local_name != identity_digest(self.owner.character)
                or parent.server != identity_digest(self.target.server)):
            raise ValueError("player attack context differs from immutable operation")
        context = ContextBinding(parent.digest, context_id, Authority.MANUAL_PLAYER,
                                 target_hint, self.target.object_key, 1, self.digest,
                                 self.digest, identity_digest(self.target.name))
        context.require_parent(parent)
        ticket = Ticket(context, parent=parent, create=True)
        try:
            ticket.arm()
        except BaseException:
            ticket.close()
            raise
        return ticket, context


def _finish_owner(owner, primary=None):
    prefix = "" if primary is None else " ".join(str(primary).split())[:200] + "; "
    try:
        confirmed = owner.finish("finite_player_attack_finished")[0]
    except Exception as cleanup:
        raise RuntimeError(prefix + "native player attack cleanup failed: "
                           + type(cleanup).__name__) from (primary or cleanup)
    if not confirmed:
        raise RuntimeError(prefix + "native player attack cleanup remains unconfirmed") from primary


def _run_finite(*, operation, character_session, population, group, vitals, owner,
                combat, intent, stop_signal, max_seconds, progress_sink,
                clock=time.monotonic, sleeper=time.sleep):
    started = clock()
    proposal = None
    state, detail = WorkerOperationState.FAILED, "player attack timed out"
    primary = None
    try:
        while max_seconds is None or clock() - started < max_seconds:
            if stop_signal.is_set():
                cause = observed_stop_cause(stop_signal)
                state = (WorkerOperationState.CANCELLED if cause.kind == "requested"
                         else WorkerOperationState.FAILED)
                detail = cause.reason
                break
            frame, character = _target_frame(character_session, population, group,
                                             operation.player_target)
            if proposal is not None and proposal.target_token != character.token:
                raise ValueError("player target object instance changed")
            if not character.alive:
                state = WorkerOperationState.SUCCEEDED
                detail = "exact player target native health zero"
                break
            player = vitals.observe()
            if player.current_health <= 0:
                detail = "local native health zero"
                break
            observation = PvEObservation(
                round((clock() - started) * 1000), NativeTargetHealthObservation(False),
                player, selection_observed=False, population=frame)
            if proposal is None:
                proposal = PvECombatProposal(1, character.token, character.object_key,
                                             PvECombatKind.ATTACK)
            if combat.pending is not None or not combat.active:
                update = combat.advance(proposal, observation,
                                        listed=_Candidate(intent.entry, 1, character))
                if progress_sink is not None:
                    progress_sink({"state": "attacking",
                                   "target": operation.player_target.to_dict(),
                                   "native": update.as_dict()})
                if update.terminal_reason or update.acknowledgement.disposition in (
                        PvECombatDisposition.REJECTED, PvECombatDisposition.DEFERRED):
                    detail = update.terminal_reason or "native player attack refused"
                    break
            else:
                receipt, native_detail = combat.observe()
                if receipt is None or receipt.context_phase is not Phase.BOUND:
                    detail = "native player context unavailable: " + (native_detail or "no receipt")
                    break
            # Same actor owner arbitrates buffs and tracking; never a second producer.
            owner.preparation_step(allow_new=combat.pending is None)
            owner.tracking_step()
            sleeper(0.2)
        return WorkerOperationExecution(state, " ".join(detail.split())[:512])
    except Exception as exc:
        primary = exc
        raise
    finally:
        # Finite outcome never substitutes for positively closing the native owner.
        _finish_owner(owner, primary)


def execute_player_attack(*, binding, operation, movement_acquirer, stop_signal,
                          settings=None, progress_sink=None, max_seconds=None):
    """Initialize readers, revalidate intent, then acquire the worker's one owner.

    Outer OperationMovement owns final movement cleanup and reports aggregate
    cleanup proof. This function never reacquires, selects a UI target, or writes
    the saved attack list. Native ATTACK supplies the existing attack/pursuit path.
    Normal execution has no arbitrary fight timeout: this one target ends on
    death, cancellation, lost identity/protection, or native failure. An optional
    duration is available only for explicitly bounded acceptance/tests.
    """
    if (operation.kind is not WorkerOperationKind.PLAYER_ATTACK
            or not isinstance(operation.player_target, WorkerPlayerAttackTarget)):
        raise ValueError("finite player attack requires its typed operation")
    if max_seconds is not None and (
            isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not math.isfinite(max_seconds) or max_seconds <= 0):
        raise ValueError("optional acceptance duration must be finite and positive")
    pid = binding.game_process_id
    with ExitStack() as stack:
        character = stack.enter_context(open_native_character_session(process_id=pid))
        native = character.binding
        if (native.process_id != pid
                or native.process_creation_filetime_utc != binding.game_process_started_at_100ns
                or _key(native.object_key) != operation.player_target.local_key
                or native.identity.server_name != operation.player_target.server):
            raise ValueError("player attack game/character lifetime changed")
        population = stack.enter_context(open_windows_native_character_population_reader(
            load_bundled_native_character_population_profile(), process_id=pid))
        group = stack.enter_context(open_windows_native_group_reader(
            load_bundled_native_group_profile(), process_id=pid))
        vitals = stack.enter_context(open_windows_native_player_vitals_reader(
            load_bundled_native_vitals_profile(), process_id=pid))
        saved = settings if settings is not None else load_pve_settings(native.identity)
        _target_frame(character, population, group, operation.player_target, require_alive=True)
        if stop_signal.is_set():
            cause = observed_stop_cause(stop_signal)
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED if cause.kind == "requested"
                else WorkerOperationState.FAILED, cause.reason)
        movement = movement_acquirer()
        if movement is None:
            cause = observed_stop_cause(stop_signal)
            return WorkerOperationExecution(
                WorkerOperationState.CANCELLED if cause.kind == "requested"
                else WorkerOperationState.FAILED, cause.reason)
        intent = _OperationPlayerIntent(operation, native)
        owner = NativeActorCoordinator(session=movement.session, grant=movement.grant,
                                       population=population, character_session=character,
                                       store=intent)
        try:
            if saved.buffs.enabled:
                owner.configure_preparation(saved.buffs)
            if saved.tracking.enabled:
                owner.configure_tracking(saved.tracking)
        except Exception as exc:
            _finish_owner(owner, exc)
            raise
        return _run_finite(operation=operation, character_session=character,
                           population=population, group=group, vitals=vitals,
                           owner=owner, combat=NativeCombatCoordinator(owner=owner),
                           intent=intent, stop_signal=stop_signal, max_seconds=max_seconds,
                           progress_sink=progress_sink)
