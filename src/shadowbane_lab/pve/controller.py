"""Deterministic, fail-closed PvE state machine."""

from __future__ import annotations

from math import hypot

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import NativeCharacterKind
from shadowbane_lab.pve.model import (
    PvEAbility,
    PvEAbilityRecipient,
    PvECampLease,
    PvECombatAcknowledgement,
    PvECombatCleanupRequest,
    PvECombatCleanupResult,
    PvECombatDisposition,
    PvECombatKind,
    PvECombatNotReadyReason,
    PvECombatProposal,
    PvEControllerConfig,
    PvEControllerDecision,
    PvEIntent,
    PvEKillConfirmation,
    PvEObservation,
    PvEPhase,
    PvETrackedTarget,
)


class PvEController:
    """Chooses mob acquisition and attack intents from exact native observations."""

    def __init__(self, config: PvEControllerConfig) -> None:
        if not isinstance(config, PvEControllerConfig):
            raise ValueError("config must be PvEControllerConfig")
        self._config = config
        self._phase = PvEPhase.INITIALIZING
        self._kills = 0
        self._decision_id = 0
        self._started_at: int | None = None
        self._phase_entered_at: int | None = None
        self._last_now: int | None = None
        self._last_acquire_at: int | None = None
        self._baseline_target_token: str | None = None
        self._engaged_target_token: str | None = None
        self._engaged_object_key = None
        self._pending_cleanup: PvECombatCleanupRequest | None = None
        self._cleanup_sequence = 0
        self._last_observation: PvEObservation | None = None
        self._last_health: float | None = None
        self._last_player_health: float | None = None
        self._last_progress_at: int | None = None
        self._last_attack_at: int | None = None
        self._last_target_health_progress_at: int | None = None
        self._last_player_health_loss_at: int | None = None
        self._melee_entered_at: int | None = None
        self._last_reposition_at: int | None = None
        self._combat_repositions = 0
        self._selection_lost_at: int | None = None
        self._reengage_attempts = 0
        self._stalled_retargets = 0
        self._failed_targets: dict[tuple[str, NativeObjectKey], int] = {}
        self._require_different_target = False
        self._last_power_at: dict[int, int] = {}
        self._interrupts_for_target = 0
        self._best_approach_distance: float | None = None
        self._outside_melee = False
        self._target_candidates: dict[str, float] = {}
        self._observed_target_tokens: set[str] = set()
        self._last_sampled_target_token: str | None = None
        self._target_sampling_complete = False
        self._target_sample_cycle_at: int | None = None
        self._empty_target_cycles = 0
        self._camp: PvECampLease | None = None
        self._camp_return_retry_at: int | None = None
        self._last_target_inside_camp: bool | None = None
        self._population_desired_target_token: str | None = None
        self._population_cycle_seen: set[str | None] = set()
        self._attack_already_active = False
        self._external_return_pending = False
        self._pending_combat: PvECombatProposal | None = None
        self._last_combat_ack = None
        self._queued_self_followup = None
        self._retry_proposal: PvECombatProposal | None = None
        self._combat_ack_at: int | None = None
        self._adoption_bind_pending = False
        self._proposal_interrupt_sequence: int | None = None
        self._proposal_reengage = False
        self._opening_queued_at: int | None = None
        self._opening_skipped = False

    @property
    def phase(self) -> PvEPhase:
        return self._phase

    @property
    def kills(self) -> int:
        return self._kills

    @property
    def terminal(self) -> bool:
        return self._phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)

    @property
    def requires_target_action(self) -> bool:
        return self._config.resolved_interrupt_ability is not None

    @property
    def requires_target_identity(self) -> bool:
        return self._config.require_target_identity

    @property
    def requires_population(self) -> bool:
        return True

    @property
    def continuous(self) -> bool:
        return self._config.continuous

    @property
    def camp(self) -> PvECampLease | None:
        return self._camp

    @property
    def target_action_observation_active(self) -> bool:
        return self._phase is PvEPhase.ENGAGED

    @property
    def player_action_observation_active(self) -> bool:
        # Recovery/camp movement also must not interrupt an uncompleted native cast.
        return not self.terminal

    @property
    def required_intents(self) -> frozenset[PvEIntent]:
        intents = {PvEIntent.ATTACK_SELECTED_TARGET}
        if self._config.opening_intent is not None:
            intents.add(self._config.opening_intent)
        if self._config.interrupt_intent is not None:
            intents.add(self._config.interrupt_intent)
        return frozenset(intents)

    @property
    def pending_combat_proposal(self) -> PvECombatProposal | None:
        return self._pending_combat

    def acknowledge_combat(
        self, proposal: PvECombatProposal, result: PvECombatAcknowledgement, *, now_ms: int,
    ) -> None:
        """Apply one correlated result; uncertainty keeps the exact proposal pinned."""
        if not isinstance(result, PvECombatAcknowledgement):
            raise ValueError("combat acknowledgment must be typed")
        if self._pending_combat != proposal:
            if self._last_combat_ack == (proposal, result):
                return
            raise ValueError("combat acknowledgment does not match the pending proposal")
        if type(now_ms) is not int or now_ms < (self._last_now or 0):
            raise ValueError("combat acknowledgment time must be monotonic")
        disposition = result.disposition
        if (disposition is PvECombatDisposition.BOUND) != (proposal.kind is PvECombatKind.BIND):
            if disposition in (PvECombatDisposition.BOUND, PvECombatDisposition.QUEUED):
                raise ValueError("combat acknowledgment kind does not match proposal")
        if (disposition is PvECombatDisposition.DEFERRED
                and proposal.kind is not PvECombatKind.BIND and result.native_entered is not False):
            raise ValueError("deferred action must positively prove no entry")
        self._last_now = now_ms
        self._last_combat_ack = (proposal, result)
        self._combat_ack_at = now_ms
        if disposition is PvECombatDisposition.UNCERTAIN:
            return
        if disposition is PvECombatDisposition.NOT_READY:
            opener = self._config.resolved_opening_ability
            if (self._phase is not PvEPhase.OPENING or opener is None
                    or proposal.kind is not opener.kind or proposal.power_id != opener.power_id
                    or proposal.interrupt_sequence is not None or proposal.adopted_existing_action
                    or result.not_ready_reason is not PvECombatNotReadyReason.POWER_REUSE):
                self._request_cleanup("native_power_not_ready", now_ms)
                return
            self._pending_combat = self._retry_proposal = None
            self._opening_skipped = True
            self._opening_queued_at = None
            self._queued_self_followup = None
            return
        if disposition is PvECombatDisposition.REJECTED:
            # Even an unentered action may have bound an engagement. Only the
            # coordinator's exact closure proof can release that obligation.
            self._request_cleanup("native_combat_rejected", now_ms)
            return
        self._pending_combat = None
        if disposition is PvECombatDisposition.DEFERRED:
            self._retry_proposal = proposal
            return
        self._retry_proposal = None
        if not result.cleanup_required:
            self._request_cleanup("native_engagement_closed", now_ms)
        if disposition is PvECombatDisposition.QUEUED:
            if proposal.kind is PvECombatKind.ATTACK:
                self._last_attack_at = now_ms
                self._queued_self_followup = None
            else:
                self._last_power_at[proposal.power_id] = now_ms
                if (proposal.kind is PvECombatKind.SELF_POWER
                        and self._pending_cleanup is None and result.cleanup_required):
                    self._queued_self_followup = (
                        proposal.target_token, proposal.target_key, proposal.power_id)
                if self._phase is PvEPhase.OPENING and self._pending_cleanup is None:
                    self._opening_queued_at = now_ms
                    self._phase_entered_at = now_ms
            if self._proposal_reengage:
                self._reengage_attempts += 1
                self._last_progress_at = now_ms
            self._proposal_reengage = False

    def candidate_camp(self, observation: PvEObservation) -> PvECampLease | None:
        """Establish the same original camp before ranking an external interruption."""
        if self._started_at is None and self._camp is None:
            self._capture_camp(observation)
        return self._camp

    def resume_after_external_combat(self, observation: PvEObservation) -> None:
        """Discard interrupted engagement only after exact native cleanup proof."""
        if self.terminal:
            raise RuntimeError("terminal PvE controller cannot resume")
        self._clear_engagement()
        self._baseline_target_token = observation.target.target_token
        self._require_different_target = True
        self._external_return_pending = self._should_return_to_camp(observation)
        self._camp_return_retry_at = None
        self._enter(PvEPhase.RECOVERING, observation.now_ms)

    def can_start_external_combat(self, observation: PvEObservation) -> bool:
        action = observation.player_action
        if self._engaged_target_token is None and (
            action is None or not action.initiation_clear
            or action.action_target_token is not None
        ):
            return False
        return (not self.terminal
                and self._pending_cleanup is None
                and self._pending_combat is None
                and self._phase not in (
                    PvEPhase.RECOVERING, PvEPhase.POST_KILL, PvEPhase.DISENGAGING
                )
                and self._resources_recovered(observation)
                and not self._should_return_to_camp(observation))

    def _recover_external_combat(self, observation: PvEObservation) -> PvEControllerDecision:
        now = observation.now_ms
        if (not self._config.continuous
                and self._phase_elapsed(now) >= self._config.recovery_timeout_ms):
            return self.stop("combat_recovery_timeout", now_ms=now)
        if not self._resources_recovered(observation):
            return self._emit(now)
        self._external_return_pending |= self._should_return_to_camp(observation)
        if self._external_return_pending and self._camp is not None:
            position = observation.player_position
            assert position is not None
            if self._camp.distance_from_anchor(position.lt, position.lg) > self._camp.return_radius:
                retry = self._camp_return_retry_at
                return self._emit(now, return_to_camp=retry is None or now >= retry)
        self._external_return_pending = False
        self._camp_return_retry_at = None
        self._enter(PvEPhase.SEEKING, now)
        return self._emit(now)

    def step(
        self, observation: PvEObservation, *, external_combat: bool = False,
    ) -> PvEControllerDecision:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        if self.terminal:
            raise RuntimeError("terminal PvE controller cannot accept another observation")
        now = observation.now_ms
        if self._last_now is not None and now < self._last_now:
            raise ValueError("PvE observation time must be monotonic")
        self._last_now = now
        self._last_observation = observation
        if self._started_at is None:
            self._started_at = now
            self._phase_entered_at = now
            self._capture_camp(observation)
        if self._camp is not None and observation.player_position is None:
            return self.stop("camp_position_unavailable", now_ms=now)
        self._last_target_inside_camp = self._target_inside_camp(observation)

        if observation.player.current_health == 0:
            return self.stop("player_death_observed", now_ms=now)
        if observation.player.health_fraction <= self._config.minimum_player_health_fraction:
            return self.stop("player_health_safety_threshold", now_ms=now)
        assert self._started_at is not None
        if (
            not self._config.continuous
            and now - self._started_at >= self._config.maximum_session_ms
        ):
            return self.stop("maximum_session_elapsed", now_ms=now)

        if external_combat:
            # Keep safety/session accounting current without
            # crediting listed kills or consuming ordinary PvE input/cooldowns.
            return self._emit(now)

        if self._pending_cleanup is not None:
            return self._emit(now)
        tracked = self.tracked_target(observation)
        if self._phase in (PvEPhase.OPENING, PvEPhase.ENGAGED):
            if (tracked is not None and tracked.character is not None
                    and tracked.character.current_health == 0):
                return self._record_kill(observation, PvEKillConfirmation.NATIVE_HEALTH_ZERO)

        if self._engaged_target_token is None and self._phase in (
            PvEPhase.INITIALIZING, PvEPhase.SEEKING, PvEPhase.OBSERVING_ACTION,
        ):
            current = self.observed_action_target(observation)
            if current is not None and self._tracked_target_attack_eligible(observation, current):
                return self._bind_engagement(observation, current.character,
                                            attack_already_active=True, adopt_existing_action=True)
            action = observation.player_action
            if (action is None or not action.initiation_clear
                    or action.action_target_token is not None):
                self._enter(PvEPhase.OBSERVING_ACTION, now)
                return self._emit(now)
            if self._phase is PvEPhase.OBSERVING_ACTION:
                self._baseline_target_token = observation.target.target_token
                self._enter(PvEPhase.SEEKING, now)
                return self._emit(now)

        if self._pending_combat is not None:
            if tracked is None or not self._tracked_target_attack_eligible(observation, tracked):
                return self._recover_invalid_engagement(observation)
            if self._phase_elapsed(now) >= self._config.engagement_timeout_ms:
                return self.stop("combat_acknowledgment_timeout", now_ms=now)
            return self._emit(now)
        if self._phase is PvEPhase.INITIALIZING:
            self._enter(PvEPhase.SEEKING, now)
            return self._seek_population(observation)
        if self._phase is PvEPhase.SEEKING:
            return self._seek_population(observation)
        if self._retry_proposal is not None:
            if tracked is None or not self._tracked_target_attack_eligible(observation, tracked):
                return self._recover_invalid_engagement(observation)
            if self._combat_ack_at is not None and now <= self._combat_ack_at:
                return self._emit(now)
            action = observation.player_action
            retry = self._retry_proposal
            if retry.kind is not PvECombatKind.BIND and (
                action is None or (not action.initiation_clear and not (
                    retry.kind is PvECombatKind.ATTACK
                    and self._self_followup_matches(observation)))
            ):
                return self._emit(now)
            self._retry_proposal = None
            if retry.interrupt_sequence is not None:
                # Re-evaluate the current target action; never replay a stale opportunity.
                interrupt = self._interrupt(observation)
                return interrupt if interrupt is not None else self._emit(now)
            self._proposal_interrupt_sequence = retry.interrupt_sequence
            self._adoption_bind_pending = retry.kind is PvECombatKind.BIND
            if retry.kind in (PvECombatKind.CAST, PvECombatKind.SELF_POWER):
                recipient = (PvEAbilityRecipient.ACTOR
                    if retry.kind is PvECombatKind.SELF_POWER
                    else PvEAbilityRecipient.ENGAGEMENT_TARGET)
                ability = PvEAbility(retry.power_id, recipient)
                return self._emit(now, self._config.opening_intent, ability=ability)
            intent = None if retry.kind is PvECombatKind.BIND else PvEIntent.ATTACK_SELECTED_TARGET
            return self._emit(now, intent)
        if self._phase is PvEPhase.OPENING:
            return self._open(observation)
        if self._phase is PvEPhase.ENGAGED:
            return self._engage(observation)
        if self._phase is PvEPhase.POST_KILL:
            return self._post_kill(observation)
        if self._phase is PvEPhase.RECOVERING:
            return self._recover_external_combat(observation)
        if self._phase is PvEPhase.CAMP_IDLE:
            return self._camp_idle(observation)
        raise RuntimeError("unreachable PvE phase")

    def stop(self, reason: str, *, now_ms: int | None = None) -> PvEControllerDecision:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("stop reason must be a non-empty string")
        if self.terminal:
            raise RuntimeError("PvE controller is already terminal")
        now = self._last_now if now_ms is None else now_ms
        if now is None:
            now = 0
        if self._last_now is not None and now < self._last_now:
            raise ValueError("stop time must be monotonic")
        self._last_now = now
        self._enter(PvEPhase.STOPPED, now)
        self._request_cleanup(reason, now)
        return self._emit(now, terminal_reason=reason)

    def _seek_population(self, observation: PvEObservation) -> PvEControllerDecision:
        now = observation.now_ms
        population, position = observation.population, observation.player_position
        if population is None or position is None:
            return self.stop("native_population_unavailable", now_ms=now)
        self._expire_failed_targets(now)
        ranked = sorted(
            (character for character in population.characters
             if character.object_key is not None
             and (character.token, character.object_key) not in self._failed_targets),
            key=lambda item: (hypot(item.lt - position.lt, item.lg - position.lg), item.token),
        )
        for character in ranked:
            tracked = PvETrackedTarget(character.token, character.object_key, character)
            if self._tracked_target_attack_eligible(observation, tracked):
                return self._bind_engagement(observation, character)
        if self._config.continuous:
            return self._begin_camp_idle(observation)
        if self._phase_elapsed(now) >= self._config.acquisition_timeout_ms:
            return self.stop("mob_acquisition_timeout", now_ms=now)
        return self._emit(now)

    def _engage(
        self,
        observation: PvEObservation,
    ) -> PvEControllerDecision:
        now = observation.now_ms
        tracked = self.tracked_target(observation)
        assert tracked is not None
        target = tracked.character
        if target is None:
            if self._selection_lost_at is None:
                self._selection_lost_at = now
            if now - self._selection_lost_at >= self._config.selection_loss_grace_ms:
                return self._recover_invalid_engagement(observation)
            return self._emit(now)
        self._selection_lost_at = None
        if not self._tracked_target_attack_eligible(observation, tracked):
            return self._recover_invalid_engagement(observation)
        assert target.current_health is not None
        approach_arrived = False
        distance = tracked.planar_distance(observation)
        inside_melee = bool(distance is not None and distance <= self._config.melee_approach_radius)
        if distance is not None:
            if (
                self._best_approach_distance is None
                or distance <= self._best_approach_distance - self._config.minimum_approach_progress
            ):
                self._best_approach_distance = distance
                self._last_progress_at = now
            if distance > self._config.melee_approach_radius:
                self._outside_melee = True
            elif self._outside_melee:
                self._outside_melee = False
                self._melee_entered_at = now
                approach_arrived = True
            elif self._melee_entered_at is None:
                self._melee_entered_at = now
        target_health_progress = bool(
            self._last_health is None
            or target.current_health < self._last_health - 0.0001
        )
        player_health_loss = bool(
            self._last_player_health is not None
            and observation.player.current_health < self._last_player_health - 0.0001
        )
        if target_health_progress:
            self._last_progress_at = now
            self._last_target_health_progress_at = now
        if player_health_loss:
            self._last_player_health_loss_at = now
        self._last_health = target.current_health
        self._last_player_health = observation.player.current_health
        player_action = observation.player_action
        if player_action is None or not player_action.initiation_clear:
            if self._phase_elapsed(now) >= self._config.engagement_timeout_ms:
                return self.stop("engagement_timeout", now_ms=now)
            return self._emit(now)

        interrupt = self._interrupt(observation)
        if interrupt is not None:
            return interrupt
        if (approach_arrived and (self._last_target_health_progress_at is None
                or now - self._last_target_health_progress_at >= self._config.stalled_progress_ms)):
            self._last_progress_at = now
            return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)

        if (
            inside_melee
            and self._last_attack_at is not None
            and (
                self._last_target_health_progress_at is None
                or self._last_target_health_progress_at < self._last_attack_at
            )
            and (
                self._last_player_health_loss_at is None
                or self._last_player_health_loss_at < self._last_attack_at
            )
        ):
            quiet_timeout = self._config.quiet_melee_timeout_ms
            if now - self._last_attack_at >= quiet_timeout:
                return self._abandon_stalled_target(observation)

        if (
            inside_melee
            and self._last_attack_at is not None
            and self._last_player_health_loss_at is not None
            and (
                self._last_target_health_progress_at is None
                or self._last_player_health_loss_at > self._last_target_health_progress_at
            )
            and (
                self._last_reposition_at is None
                or self._last_player_health_loss_at > self._last_reposition_at
            )
            and now - self._last_attack_at >= self._config.incoming_reposition_grace_ms
            and now - self._last_player_health_loss_at <= self._config.incoming_reposition_window_ms
            and self._combat_repositions < self._config.maximum_combat_repositions
        ):
            self._combat_repositions += 1
            self._last_reposition_at = now
            return self._emit(now, reposition_requested=True)

        if self._phase_elapsed(now) >= self._config.engagement_timeout_ms:
            if self._config.continuous:
                return self._abandon_stalled_target(observation)
            return self.stop("engagement_timeout", now_ms=now)
        assert self._last_progress_at is not None
        if now - self._last_progress_at >= self._config.stalled_progress_ms:
            if self._reengage_attempts >= self._config.maximum_reengage_attempts:
                return self._abandon_stalled_target(observation)
            self._proposal_reengage = True
            return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)
        return self._emit(now)

    def _post_kill(self, observation: PvEObservation) -> PvEControllerDecision:
        if self._phase_elapsed(observation.now_ms) < self._config.post_kill_delay_ms:
            return self._emit(observation.now_ms)
        self._request_cleanup("target_killed", observation.now_ms)
        return self._emit(observation.now_ms)

    def _bind_engagement(self, observation: PvEObservation, character, *,
                         attack_already_active: bool = False,
                         adopt_existing_action: bool = False) -> PvEControllerDecision:
        now = observation.now_ms
        if self._engaged_target_token is not None or self._pending_cleanup is not None:
            raise RuntimeError("new engagement requires acknowledged cleanup")
        self._baseline_target_token = character.token
        self._engaged_target_token = character.token
        self._engaged_object_key = character.object_key
        self._last_health = character.current_health
        self._last_player_health = observation.player.current_health
        self._last_progress_at = now
        self._last_attack_at = None
        self._last_target_health_progress_at = None
        self._last_player_health_loss_at = None
        self._melee_entered_at = None
        self._last_reposition_at = None
        self._combat_repositions = 0
        self._last_acquire_at = None
        self._reengage_attempts = 0
        self._selection_lost_at = None
        self._require_different_target = False
        self._interrupts_for_target = 0
        self._best_approach_distance = self.tracked_target(observation).planar_distance(observation)
        self._outside_melee = bool(
            self._best_approach_distance is not None
            and self._best_approach_distance > self._config.melee_approach_radius
        )
        self._attack_already_active = attack_already_active
        self._population_desired_target_token = None
        self._population_cycle_seen.clear()
        self._opening_queued_at = None
        self._opening_skipped = False
        if not self._outside_melee and self._best_approach_distance is not None:
            self._melee_entered_at = now
        if adopt_existing_action:
            self._adoption_bind_pending = True
            self._enter(PvEPhase.ENGAGED, now)
            return self._emit(now)
        opener = self._config.resolved_opening_ability
        if opener is not None and observation.player.current_mana >= self._config.opening_mana_cost:
            self._enter(PvEPhase.OPENING, now)
            return self._emit(now, self._config.opening_intent, ability=opener)
        self._enter(PvEPhase.ENGAGED, now)
        if attack_already_active and (self._outside_melee or self._best_approach_distance is None):
            return self._emit(now)
        return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)

    def _interrupt(self, observation: PvEObservation) -> PvEControllerDecision | None:
        # AF8 and animation telemetry do not identify a cast or its target.
        # No interrupt request is authorized without that missing provenance.
        return None

    def _self_followup_matches(self, observation: PvEObservation) -> bool:
        queued = self._queued_self_followup
        action = observation.player_action
        tracked = self.tracked_target(observation)
        return bool(queued is not None and action is not None
                    and action.initiation_pending is not None
                    and tracked is not None and tracked.available
                    and queued[:2] == (tracked.token, tracked.object_key))

    def _open(
        self,
        observation: PvEObservation,
    ) -> PvEControllerDecision:
        now = observation.now_ms
        tracked = self.tracked_target(observation)
        assert tracked is not None
        target = tracked.character
        if target is None:
            if self._selection_lost_at is None:
                self._selection_lost_at = now
            if now - self._selection_lost_at >= self._config.selection_loss_grace_ms:
                return self._recover_invalid_engagement(observation)
            return self._emit(now)
        self._selection_lost_at = None
        if not self._tracked_target_attack_eligible(observation, tracked):
            return self._recover_invalid_engagement(observation)
        assert target.current_health is not None
        target_health_progress = bool(
            self._last_health is None
            or target.current_health < self._last_health - 0.0001
        )
        player_health_loss = bool(
            self._last_player_health is not None
            and observation.player.current_health < self._last_player_health - 0.0001
        )
        if target_health_progress:
            self._last_progress_at = now
            self._last_target_health_progress_at = now
        if player_health_loss:
            self._last_player_health_loss_at = now
        self._last_health = target.current_health
        self._last_player_health = observation.player.current_health
        if (observation.player_action is None or (
                not observation.player_action.initiation_clear
                and not self._self_followup_matches(observation))):
            if self._phase_elapsed(now) >= self._config.engagement_timeout_ms:
                return self.stop("engagement_timeout", now_ms=now)
            return self._emit(now)
        if self._opening_skipped:
            if self._combat_ack_at is None or now <= self._combat_ack_at:
                return self._emit(now)
        elif (self._opening_queued_at is None
                or now - self._opening_queued_at < self._config.opening_followup_delay_ms):
            return self._emit(now)
        self._enter(PvEPhase.ENGAGED, now)
        distance = tracked.planar_distance(observation)
        if distance is not None:
            self._best_approach_distance = distance
            self._outside_melee = distance > self._config.melee_approach_radius
            if not self._outside_melee:
                self._melee_entered_at = now
        if self._attack_already_active and (
            distance is None or distance > self._config.melee_approach_radius
        ):
            return self._emit(now)
        return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)

    def _record_kill(
        self,
        observation: PvEObservation,
        confirmation: PvEKillConfirmation,
    ) -> PvEControllerDecision:
        now = observation.now_ms
        self._kills += 1
        if not self._config.continuous and self._kills >= self._config.maximum_kills:
            self._enter(PvEPhase.COMPLETE, now)
            self._request_cleanup("kill_limit_reached", now)
            return self._emit(
                now,
                terminal_reason="kill_limit_reached",
                kill_confirmation=confirmation,
            )
        self._baseline_target_token = observation.target.target_token
        self._enter(PvEPhase.POST_KILL, now)
        return self._emit(now, kill_confirmation=confirmation)

    def _resources_recovered(self, observation: PvEObservation) -> bool:
        player = observation.player
        return (
            player.health_fraction >= self._config.minimum_recovery_health_fraction
            and player.mana_fraction >= self._config.minimum_recovery_mana_fraction
            and player.stamina_fraction >= self._config.minimum_recovery_stamina_fraction
        )

    def observed_action_target(self, observation: PvEObservation) -> PvETrackedTarget | None:
        action, population = observation.player_action, observation.population
        if action is None or population is None or action.action_target_token is None:
            return None
        character = next((item for item in population.characters
                          if item.token == action.action_target_token), None)
        if (character is None or character.object_key is None
                or character.character_kind is not NativeCharacterKind.NPC):
            return None
        return PvETrackedTarget(character.token, character.object_key, character)

    def tracked_target(self, observation: PvEObservation) -> PvETrackedTarget | None:
        if self._engaged_target_token is None or self._engaged_object_key is None:
            return None
        population = observation.population
        character = None if population is None else next((
            item for item in population.characters
            if (item.token == self._engaged_target_token
                and item.object_key == self._engaged_object_key)
        ), None)
        return PvETrackedTarget(self._engaged_target_token, self._engaged_object_key, character)

    def _tracked_target_attack_eligible(
        self, observation: PvEObservation, tracked: PvETrackedTarget,
    ) -> bool:
        character = tracked.character
        return bool(character is not None and character.attack_eligible
                    and character.character_kind is NativeCharacterKind.NPC and (
            self._camp is None or self._camp.contains(character.lt, character.lg)
        ))

    @property
    def input_target(self) -> PvETrackedTarget | None:
        observation = self._last_observation
        return None if observation is None else self.tracked_target(observation)

    @property
    def pending_cleanup(self) -> PvECombatCleanupRequest | None:
        return self._pending_cleanup

    def _request_cleanup(self, reason: str, now_ms: int) -> None:
        self._queued_self_followup = None
        if self._engaged_target_token is None:
            return
        assert self._engaged_object_key is not None
        if self._pending_cleanup is None:
            self._pending_cleanup = PvECombatCleanupRequest(
                self._cleanup_sequence, self._engaged_target_token, self._engaged_object_key, reason
            )
            self._cleanup_sequence += 1
        if not self.terminal:
            self._enter(PvEPhase.DISENGAGING, now_ms)

    def request_final_cleanup(self) -> PvECombatCleanupRequest | None:
        self._request_cleanup("pve_run_unwound", self._last_now or 0)
        return self._pending_cleanup

    def acknowledge_cleanup(self, result: PvECombatCleanupResult) -> None:
        if not result.confirmed or result.request != self._pending_cleanup:
            raise ValueError("cleanup acknowledgment must match the pending engagement")
        self._pending_cleanup = None
        self._clear_engagement()
        self._require_different_target = True
        if not self.terminal:
            self._external_return_pending = False
            self._camp_return_retry_at = None
            self._enter(PvEPhase.RECOVERING, self._last_now or 0)

    def _target_attack_eligible(self, observation: PvEObservation) -> bool:
        population = observation.population
        character = None if population is None else next((
            item for item in population.characters if item.token == observation.target.target_token
        ), None)
        if (character is None or character.object_key is None
                or character.character_kind is not NativeCharacterKind.NPC):
            return False
        inside_camp = self._target_inside_camp(observation)
        if inside_camp is False:
            return False
        eligible = observation.target_attack_eligible
        if eligible is None:
            return not self._config.require_target_identity
        return eligible

    def _abandon_stalled_target(self, observation: PvEObservation) -> PvEControllerDecision:
        now = observation.now_ms
        if (not self._config.continuous
                and self._stalled_retargets >= self._config.maximum_stalled_retargets):
            return self.stop("engagement_stalled", now_ms=now)
        self._stalled_retargets += 1
        return self._recover_invalid_engagement(observation, reason="engagement_stalled")

    def recover_from_approach_failure(
        self,
        observation: PvEObservation,
        reason: str,
    ) -> PvEControllerDecision:
        """Turns a recoverable movement failure into a bounded camp retry."""

        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("approach failure reason must be non-empty")
        if self.terminal:
            raise RuntimeError("terminal PvE controller cannot recover movement")
        if self._last_now is not None and observation.now_ms < self._last_now:
            raise ValueError("PvE observation time must be monotonic")
        self._last_now = observation.now_ms
        if not self._config.continuous:
            return self.stop(f"approach_{reason}", now_ms=observation.now_ms)
        if self._phase in (PvEPhase.OPENING, PvEPhase.ENGAGED):
            tracked = self.tracked_target(observation)
            if tracked is not None and tracked.available:
                return self._abandon_stalled_target(observation)
            return self._recover_invalid_engagement(observation)
        if self._phase in (PvEPhase.CAMP_IDLE, PvEPhase.RECOVERING):
            self._camp_return_retry_at = observation.now_ms + self._config.camp_return_retry_ms
            return self._emit(observation.now_ms)
        return self.stop(f"approach_{reason}", now_ms=observation.now_ms)

    def _recover_invalid_engagement(
        self, observation: PvEObservation, *,
        reason: str = "engaged_object_unavailable_or_ineligible",
    ) -> PvEControllerDecision:
        now = observation.now_ms
        if self._engaged_target_token is not None:
            assert self._engaged_object_key is not None
            self._failed_targets[(self._engaged_target_token, self._engaged_object_key)] = now
        self._baseline_target_token = observation.target.target_token
        self._request_cleanup(reason, now)
        return self._emit(now)

    def _capture_camp(self, observation: PvEObservation) -> None:
        if self._config.camp_radius is None:
            return
        if observation.player_position is None:
            raise ValueError("camp-scoped PvE requires native player position")
        self._camp = PvECampLease(
            anchor_lt=observation.player_position.lt,
            anchor_lg=observation.player_position.lg,
            radius=float(self._config.camp_radius),
            return_radius=float(self._config.camp_return_radius),
            return_trigger_radius=(
                None
                if self._config.camp_return_trigger_radius is None
                else float(self._config.camp_return_trigger_radius)
            ),
        )

    def _target_inside_camp(self, observation: PvEObservation) -> bool | None:
        if self._camp is None:
            return None
        target_position = observation.target_position
        if target_position is None or not target_position.target_present:
            return None
        assert target_position.lt is not None
        assert target_position.lg is not None
        return self._camp.contains(target_position.lt, target_position.lg)

    def _begin_camp_idle(
        self,
        observation: PvEObservation,
    ) -> PvEControllerDecision:
        self._baseline_target_token = observation.target.target_token
        self._clear_engagement()
        self._require_different_target = False
        self._enter(PvEPhase.CAMP_IDLE, observation.now_ms)
        return self._emit(
            observation.now_ms,
            return_to_camp=self._should_return_to_camp(observation),
        )

    def _camp_idle(self, observation: PvEObservation) -> PvEControllerDecision:
        now = observation.now_ms
        self._expire_failed_targets(now)
        if self._should_return_to_camp(observation):
            retry_at = self._camp_return_retry_at
            return self._emit(
                now,
                return_to_camp=retry_at is None or now >= retry_at,
            )
        self._camp_return_retry_at = None
        if self._phase_elapsed(now) < self._config.camp_idle_ms:
            return self._emit(now)
        self._baseline_target_token = observation.target.target_token
        self._enter(PvEPhase.SEEKING, now)
        return self._seek_population(observation)

    def _should_return_to_camp(self, observation: PvEObservation) -> bool:
        if self._camp is None or observation.player_position is None:
            return False
        return (
            self._camp.distance_from_anchor(
                observation.player_position.lt,
                observation.player_position.lg,
            )
            > self._camp.return_trigger_radius
        )

    def _expire_failed_targets(self, now_ms: int) -> None:
        cutoff = now_ms - self._config.failed_target_cooldown_ms
        self._failed_targets = {
            identity: failed_at
            for identity, failed_at in self._failed_targets.items()
            if failed_at > cutoff
        }

    def _clear_engagement(self) -> None:
        self._queued_self_followup = None
        self._engaged_target_token = None
        self._engaged_object_key = None
        self._pending_combat = None
        self._retry_proposal = None
        self._adoption_bind_pending = False
        self._proposal_interrupt_sequence = None
        self._proposal_reengage = False
        self._opening_queued_at = None
        self._opening_skipped = False
        self._last_health = None
        self._last_player_health = None
        self._last_progress_at = None
        self._last_attack_at = None
        self._last_target_health_progress_at = None
        self._last_player_health_loss_at = None
        self._melee_entered_at = None
        self._last_reposition_at = None
        self._combat_repositions = 0
        self._selection_lost_at = None
        self._reengage_attempts = 0
        self._interrupts_for_target = 0
        self._best_approach_distance = None
        self._outside_melee = False
        self._attack_already_active = False

    def _enter(self, phase: PvEPhase, now_ms: int) -> None:
        self._phase = phase
        self._phase_entered_at = now_ms
        if phase is PvEPhase.SEEKING:
            self._empty_target_cycles = 0
            self._target_candidates.clear()
            self._observed_target_tokens.clear()
            self._last_sampled_target_token = None
            self._target_sampling_complete = False
            self._target_sample_cycle_at = None
            self._population_desired_target_token = None
            self._population_cycle_seen.clear()

    def _phase_elapsed(self, now_ms: int) -> int:
        assert self._phase_entered_at is not None
        return now_ms - self._phase_entered_at

    def _emit(
        self,
        now_ms: int,
        intent: PvEIntent | None = None,
        *,
        ability: PvEAbility | None = None,
        terminal_reason: str | None = None,
        kill_confirmation: PvEKillConfirmation | None = None,
        reposition_requested: bool = False,
        return_to_camp: bool = False,
    ) -> PvEControllerDecision:
        observation = self._last_observation
        tracked = None if observation is None else self.tracked_target(observation)
        action = None if observation is None else observation.player_action
        native_action_pending = bool(
            self._phase is PvEPhase.OBSERVING_ACTION
            or (not self.terminal and (action is None or (not action.initiation_clear
                and not (intent is PvEIntent.ATTACK_SELECTED_TARGET
                         and observation is not None
                         and self._self_followup_matches(observation)))))
        )
        proposal = None
        if self._pending_combat is not None:
            native_action_pending = True
        if native_action_pending:
            ability = None
            intent, reposition_requested, return_to_camp = None, False, False
        if self._pending_cleanup is not None:
            intent, reposition_requested, return_to_camp = None, False, False
        elif (self._pending_combat is None and not self.terminal
              and tracked is not None and tracked.available):
            kind = (PvECombatKind.BIND if self._adoption_bind_pending else
                    PvECombatKind.ATTACK if intent is PvEIntent.ATTACK_SELECTED_TARGET else
                    ability.kind if ability is not None else None)
            if kind is not None:
                proposal = PvECombatProposal(
                    self._decision_id, tracked.token, tracked.object_key, kind,
                    power_id=ability.power_id if ability is not None else 0,
                    adopted_existing_action=kind is PvECombatKind.BIND,
                    interrupt_sequence=self._proposal_interrupt_sequence,
                )
                self._pending_combat = proposal
                self._adoption_bind_pending = False
                self._proposal_interrupt_sequence = None
        if proposal is None:
            intent = None
        decision = PvEControllerDecision(
            decision_id=self._decision_id,
            now_ms=now_ms,
            phase=self._phase,
            kills=self._kills,
            cleanup_request=self._pending_cleanup,
            tracked_target=tracked,
            target_health_progress_at_ms=(
                self._last_target_health_progress_at
                if self._phase in (PvEPhase.OPENING, PvEPhase.ENGAGED)
                and tracked is not None and tracked.available and self._pending_cleanup is None
                else None
            ),
            native_action_pending=native_action_pending,
            opening_skill_skipped=self._opening_skipped,
            opening_skill_skip_reason=(
                PvECombatNotReadyReason.POWER_REUSE if self._opening_skipped else None),
            combat_proposal=proposal,
            intent=intent,
            reposition_requested=reposition_requested,
            camp=self._camp,
            target_inside_camp=self._last_target_inside_camp,
            return_to_camp=return_to_camp,
            terminal_reason=terminal_reason,
            kill_confirmation=kill_confirmation,
            acquisition_target_token=(
                self._population_desired_target_token if self._phase is PvEPhase.SEEKING else None
            ),
        )
        self._decision_id += 1
        return decision
