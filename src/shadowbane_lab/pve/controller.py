"""Deterministic, fail-closed PvE state machine."""

from __future__ import annotations

from shadowbane_lab.client_observation import NativeCombatEvent, NativeCombatEventKind
from shadowbane_lab.pve.model import (
    PvEControllerConfig,
    PvEControllerDecision,
    PvEIntent,
    PvEKillConfirmation,
    PvEObservation,
    PvEPhase,
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
        self._last_event_sequence = -1
        self._last_acquire_at: int | None = None
        self._baseline_target_token: str | None = None
        self._engaged_target_token: str | None = None
        self._last_health: float | None = None
        self._last_progress_at: int | None = None
        self._selection_lost_at: int | None = None
        self._reengage_attempts = 0
        self._stalled_retargets = 0
        self._require_different_target = False
        self._last_power_at: dict[PvEIntent, int] = {}
        self._last_interrupt_action_sequence: int | None = None
        self._interrupts_for_target = 0
        self._best_approach_distance: float | None = None
        self._outside_melee = False
        self._target_candidates: dict[str, float] = {}
        self._observed_target_tokens: set[str] = set()
        self._last_sampled_target_token: str | None = None
        self._target_sampling_complete = False
        self._target_sample_cycle_at: int | None = None

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
        return self._config.interrupt_intent is not None

    @property
    def requires_target_identity(self) -> bool:
        return self._config.require_target_identity

    @property
    def target_action_observation_active(self) -> bool:
        return self._phase is PvEPhase.ENGAGED

    @property
    def required_intents(self) -> frozenset[PvEIntent]:
        intents = {
            PvEIntent.ACQUIRE_NEXT_MOB,
            PvEIntent.ATTACK_SELECTED_TARGET,
        }
        if self._config.opening_intent is not None:
            intents.add(self._config.opening_intent)
        if self._config.interrupt_intent is not None:
            intents.add(self._config.interrupt_intent)
        return frozenset(intents)

    def step(self, observation: PvEObservation) -> PvEControllerDecision:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        if self.terminal:
            raise RuntimeError("terminal PvE controller cannot accept another observation")
        now = observation.now_ms
        if self._last_now is not None and now < self._last_now:
            raise ValueError("PvE observation time must be monotonic")
        self._last_now = now
        if self._started_at is None:
            self._started_at = now
            self._phase_entered_at = now

        events = tuple(
            event
            for event in observation.combat_events
            if event.sequence > self._last_event_sequence
        )
        if events:
            self._last_event_sequence = events[-1].sequence
        if any(event.kind is NativeCombatEventKind.PLAYER_KILLED for event in events):
            return self.stop("player_death_observed", now_ms=now)
        if observation.player.health_fraction <= self._config.minimum_player_health_fraction:
            return self.stop("player_health_safety_threshold", now_ms=now)
        assert self._started_at is not None
        if now - self._started_at >= self._config.maximum_session_ms:
            return self.stop("maximum_session_elapsed", now_ms=now)

        if self._phase in (PvEPhase.OPENING, PvEPhase.ENGAGED):
            kills = tuple(
                event for event in events if event.kind is NativeCombatEventKind.TARGET_KILLED
            )
            if len(kills) > 1:
                return self.stop("ambiguous_multiple_kill_records", now_ms=now)
            if kills:
                return self._record_kill(
                    observation,
                    PvEKillConfirmation.NATIVE_COMBAT_EVENT,
                )
            if (
                observation.target.target_present
                and observation.target.current_health == 0.0
            ):
                return self._record_kill(
                    observation,
                    PvEKillConfirmation.NATIVE_HEALTH_ZERO,
                )

        if self._phase is PvEPhase.INITIALIZING:
            if (
                self._config.accept_automatic_targets
                and observation.target.target_present
                and observation.target.current_health != 0.0
                and self._target_attack_eligible(observation)
                and self._automatic_target_confirmed(events)
            ):
                return self._begin_engagement(observation)
            self._baseline_target_token = observation.target.target_token
            self._enter(PvEPhase.SEEKING, now)
            if self._config.accept_automatic_targets and observation.target.target_present:
                return self._emit(now)
            return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
        if self._phase is PvEPhase.SEEKING:
            return self._seek(observation, events)
        if self._phase is PvEPhase.OPENING:
            return self._open(observation)
        if self._phase is PvEPhase.ENGAGED:
            return self._engage(observation, events)
        if self._phase is PvEPhase.POST_KILL:
            return self._post_kill(observation, events)
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
        return self._emit(now, terminal_reason=reason)

    def _seek(
        self,
        observation: PvEObservation,
        events: tuple[NativeCombatEvent, ...],
    ) -> PvEControllerDecision:
        now = observation.now_ms
        target = observation.target
        if target.target_present and target.current_health != 0.0:
            if not self._target_attack_eligible(observation):
                return self._reject_target(observation)
            sampled = self._sample_nearest_target(observation)
            if sampled is not None:
                return sampled
            explicitly_acquired = (
                self._last_acquire_at is not None
                and target.target_token != self._baseline_target_token
            )
            if explicitly_acquired:
                self._require_different_target = False
                return self._begin_engagement(observation)
            if not self._require_different_target and (
                self._config.accept_automatic_targets
                and self._automatic_target_confirmed(events)
            ):
                return self._begin_engagement(observation)
        if self._phase_elapsed(now) >= self._config.acquisition_timeout_ms:
            return self.stop("mob_acquisition_timeout", now_ms=now)
        if self._config.nearest_target_sample_count > 1 and (
            not target.target_present or target.current_health == 0.0
        ):
            if self._target_sample_ready(now):
                return self._cycle_target_sample(now)
            return self._emit(now)
        if target.target_present and self._config.accept_automatic_targets:
            if (
                self._phase_elapsed(now) >= self._config.stale_selection_cycle_delay_ms
                and (
                    self._last_acquire_at is None
                    or now - self._last_acquire_at >= self._config.acquisition_retry_ms
                )
            ):
                return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
            return self._emit(now)
        if (
            self._last_acquire_at is None
            or now - self._last_acquire_at >= self._config.acquisition_retry_ms
        ):
            return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
        return self._emit(now)

    def _sample_nearest_target(
        self,
        observation: PvEObservation,
    ) -> PvEControllerDecision | None:
        if self._config.nearest_target_sample_count == 1:
            return None
        target = observation.target
        distance = observation.target_planar_distance
        if distance is None:
            return None
        assert target.target_token is not None
        token = target.target_token
        now = observation.now_ms
        if self._require_different_target and token == self._baseline_target_token:
            if self._target_sample_ready(now):
                return self._cycle_target_sample(now)
            return self._emit(now)

        if token != self._last_sampled_target_token:
            self._target_sample_cycle_at = None
            if token in self._observed_target_tokens:
                self._target_sampling_complete = True
            else:
                self._observed_target_tokens.add(token)
                self._target_candidates[token] = distance
                if (
                    len(self._observed_target_tokens)
                    >= self._config.nearest_target_sample_count
                ):
                    self._target_sampling_complete = True
            self._last_sampled_target_token = token
        elif (
            self._target_sample_cycle_at is not None
            and now - self._target_sample_cycle_at
            >= self._config.target_sample_interval_ms
        ):
            self._target_sampling_complete = True

        if self._target_sampling_complete:
            nearest_token = min(
                self._target_candidates,
                key=lambda candidate: (self._target_candidates[candidate], candidate),
            )
            if token == nearest_token:
                self._require_different_target = False
                return self._begin_engagement(observation)
        if self._target_sample_ready(now):
            return self._cycle_target_sample(now)
        return self._emit(now)

    def _reject_target(self, observation: PvEObservation) -> PvEControllerDecision:
        target = observation.target
        assert target.target_present
        assert target.target_token is not None
        now = observation.now_ms
        token = target.target_token
        if token != self._last_sampled_target_token:
            self._target_sample_cycle_at = None
            if token in self._observed_target_tokens:
                self._target_sampling_complete = True
            else:
                self._observed_target_tokens.add(token)
                if (
                    len(self._observed_target_tokens)
                    >= self._config.nearest_target_sample_count
                ):
                    self._target_sampling_complete = True
            self._last_sampled_target_token = token
        elif (
            self._target_sample_cycle_at is not None
            and now - self._target_sample_cycle_at
            >= self._config.target_sample_interval_ms
        ):
            self._target_sampling_complete = True
        if self._phase_elapsed(now) >= self._config.acquisition_timeout_ms:
            return self.stop("mob_acquisition_timeout", now_ms=now)
        if self._target_sample_ready(now):
            return self._cycle_target_sample(now)
        return self._emit(now)

    def _cycle_target_sample(self, now_ms: int) -> PvEControllerDecision:
        self._target_sample_cycle_at = now_ms
        return self._emit(now_ms, PvEIntent.ACQUIRE_NEXT_MOB)

    def _target_sample_ready(self, now_ms: int) -> bool:
        return (
            self._last_acquire_at is None
            or now_ms - self._last_acquire_at >= self._config.target_sample_interval_ms
        )

    def _engage(
        self,
        observation: PvEObservation,
        events: tuple[NativeCombatEvent, ...],
    ) -> PvEControllerDecision:
        now = observation.now_ms
        target = observation.target
        if not target.target_present:
            if self._selection_lost_at is None:
                self._selection_lost_at = now
            if now - self._selection_lost_at >= self._config.selection_loss_grace_ms:
                self._baseline_target_token = None
                self._enter(PvEPhase.SEEKING, now)
                return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
            return self._emit(now)
        self._selection_lost_at = None
        if not self._target_attack_eligible(observation):
            return self.stop("engaged_target_became_attack_ineligible", now_ms=now)
        if target.target_token != self._engaged_target_token:
            return self.stop("selected_target_changed_during_engagement", now_ms=now)
        assert target.current_health is not None
        approach_arrived = False
        distance = observation.target_planar_distance
        if distance is not None:
            if (
                self._best_approach_distance is None
                or distance
                <= self._best_approach_distance - self._config.minimum_approach_progress
            ):
                self._best_approach_distance = distance
                self._last_progress_at = now
            if distance > self._config.melee_approach_radius:
                self._outside_melee = True
            elif self._outside_melee:
                self._outside_melee = False
                approach_arrived = True
        if self._last_health is None or target.current_health < self._last_health - 0.0001:
            self._last_progress_at = now
        if any(event.kind is NativeCombatEventKind.PLAYER_HIT_TARGET for event in events):
            self._last_progress_at = now
        self._last_health = target.current_health

        interrupt = self._interrupt(observation)
        if interrupt is not None:
            return interrupt
        if approach_arrived:
            self._last_progress_at = now
            return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)

        if self._phase_elapsed(now) >= self._config.engagement_timeout_ms:
            return self.stop("engagement_timeout", now_ms=now)
        assert self._last_progress_at is not None
        if now - self._last_progress_at >= self._config.stalled_progress_ms:
            if self._reengage_attempts >= self._config.maximum_reengage_attempts:
                if self._stalled_retargets < self._config.maximum_stalled_retargets:
                    self._stalled_retargets += 1
                    self._baseline_target_token = target.target_token
                    self._clear_engagement()
                    self._require_different_target = True
                    self._enter(PvEPhase.SEEKING, now)
                    return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
                return self.stop("engagement_stalled", now_ms=now)
            self._reengage_attempts += 1
            self._last_progress_at = now
            return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)
        return self._emit(now)

    def _post_kill(
        self,
        observation: PvEObservation,
        events: tuple[NativeCombatEvent, ...],
    ) -> PvEControllerDecision:
        now = observation.now_ms
        elapsed = self._phase_elapsed(now)
        if elapsed < self._config.post_kill_delay_ms:
            return self._emit(now)
        if not self._resources_recovered(observation):
            if elapsed >= self._config.recovery_timeout_ms:
                return self.stop("post_kill_recovery_timeout", now_ms=now)
            return self._emit(now)
        previous_target_token = self._engaged_target_token
        if (
            self._config.accept_automatic_targets
            and observation.target.target_present
            and observation.target.current_health != 0.0
            and observation.target.target_token != previous_target_token
            and self._target_attack_eligible(observation)
        ):
            if self._automatic_target_confirmed(events):
                return self._begin_engagement(observation)
            self._baseline_target_token = observation.target.target_token
            self._clear_engagement()
            self._enter(PvEPhase.SEEKING, now)
            return self._emit(now)
        self._baseline_target_token = observation.target.target_token
        self._clear_engagement()
        self._enter(PvEPhase.SEEKING, now)
        return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)

    def _begin_engagement(self, observation: PvEObservation) -> PvEControllerDecision:
        target = observation.target
        assert target.target_present
        assert target.target_token is not None
        assert target.current_health is not None
        assert target.current_health > 0.0
        assert self._target_attack_eligible(observation)
        now = observation.now_ms
        self._baseline_target_token = target.target_token
        self._engaged_target_token = target.target_token
        self._last_health = target.current_health
        self._last_progress_at = now
        self._last_acquire_at = None
        self._reengage_attempts = 0
        self._selection_lost_at = None
        self._require_different_target = False
        self._last_interrupt_action_sequence = None
        self._interrupts_for_target = 0
        self._best_approach_distance = observation.target_planar_distance
        self._outside_melee = bool(
            self._best_approach_distance is not None
            and self._best_approach_distance > self._config.melee_approach_radius
        )
        opener = self._config.opening_intent
        if opener is not None and observation.player.current_mana >= self._config.opening_mana_cost:
            self._enter(PvEPhase.OPENING, now)
            return self._emit(now, opener)
        self._enter(PvEPhase.ENGAGED, now)
        if self._config.automatic_attack_expected:
            return self._emit(now)
        return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)

    def _interrupt(self, observation: PvEObservation) -> PvEControllerDecision | None:
        intent = self._config.interrupt_intent
        action = observation.target_action
        if intent is None or action is None or not action.interrupt_opportunity:
            return None
        assert action.action_sequence is not None
        if action.action_sequence == self._last_interrupt_action_sequence:
            return None
        if self._interrupts_for_target >= self._config.maximum_interrupts_per_target:
            return None
        if observation.player.current_mana < self._config.interrupt_mana_cost:
            return None
        last_power_at = self._last_power_at.get(intent)
        if (
            last_power_at is not None
            and observation.now_ms - last_power_at < self._config.interrupt_cooldown_ms
        ):
            return None
        self._last_interrupt_action_sequence = action.action_sequence
        self._interrupts_for_target += 1
        return self._emit(observation.now_ms, intent)

    def _open(self, observation: PvEObservation) -> PvEControllerDecision:
        now = observation.now_ms
        target = observation.target
        if not target.target_present:
            return self.stop("selection_lost_during_opener", now_ms=now)
        if not self._target_attack_eligible(observation):
            return self.stop("opening_target_became_attack_ineligible", now_ms=now)
        if target.target_token != self._engaged_target_token:
            return self.stop("selected_target_changed_during_opener", now_ms=now)
        assert target.current_health is not None
        if self._last_health is None or target.current_health < self._last_health - 0.0001:
            self._last_progress_at = now
        self._last_health = target.current_health
        if self._phase_elapsed(now) < self._config.opening_followup_delay_ms:
            return self._emit(now)
        self._enter(PvEPhase.ENGAGED, now)
        if self._config.automatic_attack_expected:
            return self._emit(now)
        return self._emit(now, PvEIntent.ATTACK_SELECTED_TARGET)

    def _record_kill(
        self,
        observation: PvEObservation,
        confirmation: PvEKillConfirmation,
    ) -> PvEControllerDecision:
        now = observation.now_ms
        self._kills += 1
        if self._kills >= self._config.maximum_kills:
            self._enter(PvEPhase.COMPLETE, now)
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

    def _automatic_target_confirmed(
        self,
        events: tuple[NativeCombatEvent, ...],
    ) -> bool:
        return (
            not self._config.automatic_target_requires_combat_event
            or any(event.kind is NativeCombatEventKind.PLAYER_HIT_TARGET for event in events)
        )

    def _target_attack_eligible(self, observation: PvEObservation) -> bool:
        eligible = observation.target_attack_eligible
        if eligible is None:
            return not self._config.require_target_identity
        return eligible

    def _clear_engagement(self) -> None:
        self._engaged_target_token = None
        self._last_health = None
        self._last_progress_at = None
        self._selection_lost_at = None
        self._reengage_attempts = 0
        self._last_interrupt_action_sequence = None
        self._interrupts_for_target = 0
        self._best_approach_distance = None
        self._outside_melee = False

    def _enter(self, phase: PvEPhase, now_ms: int) -> None:
        self._phase = phase
        self._phase_entered_at = now_ms
        if phase is PvEPhase.SEEKING:
            self._target_candidates.clear()
            self._observed_target_tokens.clear()
            self._last_sampled_target_token = None
            self._target_sampling_complete = False
            self._target_sample_cycle_at = None

    def _phase_elapsed(self, now_ms: int) -> int:
        assert self._phase_entered_at is not None
        return now_ms - self._phase_entered_at

    def _emit(
        self,
        now_ms: int,
        intent: PvEIntent | None = None,
        *,
        terminal_reason: str | None = None,
        kill_confirmation: PvEKillConfirmation | None = None,
    ) -> PvEControllerDecision:
        decision = PvEControllerDecision(
            decision_id=self._decision_id,
            now_ms=now_ms,
            phase=self._phase,
            kills=self._kills,
            intent=intent,
            terminal_reason=terminal_reason,
            kill_confirmation=kill_confirmation,
        )
        self._decision_id += 1
        if intent is PvEIntent.ACQUIRE_NEXT_MOB:
            self._last_acquire_at = now_ms
        elif intent not in (None, PvEIntent.ATTACK_SELECTED_TARGET):
            self._last_power_at[intent] = now_ms
        return decision
