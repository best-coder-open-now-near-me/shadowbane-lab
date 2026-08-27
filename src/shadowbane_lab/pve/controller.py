"""Deterministic, fail-closed PvE state machine."""

from __future__ import annotations

from shadowbane_lab.client_observation import NativeCombatEvent, NativeCombatEventKind
from shadowbane_lab.pve.model import (
    PvEControllerConfig,
    PvEControllerDecision,
    PvEIntent,
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
                return self._record_kill(observation)

        if self._phase is PvEPhase.INITIALIZING:
            if (
                self._config.accept_automatic_targets
                and observation.target.target_present
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
        if target.target_present:
            explicitly_acquired = (
                self._last_acquire_at is not None
                and target.target_token != self._baseline_target_token
            )
            if explicitly_acquired:
                self._require_different_target = False
                return self._begin_engagement(observation)
            if not self._require_different_target and (
                self._config.accept_automatic_targets and self._automatic_target_confirmed(events)
            ):
                return self._begin_engagement(observation)
        if self._phase_elapsed(now) >= self._config.acquisition_timeout_ms:
            return self.stop("mob_acquisition_timeout", now_ms=now)
        if target.target_present and self._config.accept_automatic_targets:
            if self._phase_elapsed(now) >= self._config.stale_selection_cycle_delay_ms and (
                self._last_acquire_at is None
                or now - self._last_acquire_at >= self._config.acquisition_retry_ms
            ):
                return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
            return self._emit(now)
        if (
            self._last_acquire_at is None
            or now - self._last_acquire_at >= self._config.acquisition_retry_ms
        ):
            return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
        return self._emit(now)

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
        if target.target_token != self._engaged_target_token:
            return self.stop("selected_target_changed_during_engagement", now_ms=now)
        assert target.current_health is not None
        if self._last_health is None or target.current_health < self._last_health - 0.0001:
            self._last_progress_at = now
        if any(event.kind is NativeCombatEventKind.PLAYER_HIT_TARGET for event in events):
            self._last_progress_at = now
        self._last_health = target.current_health

        interrupt = self._interrupt(observation)
        if interrupt is not None:
            return interrupt

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
        if self._phase_elapsed(now) < self._config.post_kill_delay_ms:
            return self._emit(now)
        previous_target_token = self._engaged_target_token
        if (
            self._config.accept_automatic_targets
            and observation.target.target_present
            and observation.target.target_token != previous_target_token
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

    def _record_kill(self, observation: PvEObservation) -> PvEControllerDecision:
        now = observation.now_ms
        self._kills += 1
        if self._kills >= self._config.maximum_kills:
            self._enter(PvEPhase.COMPLETE, now)
            return self._emit(now, terminal_reason="kill_limit_reached")
        self._baseline_target_token = observation.target.target_token
        self._enter(PvEPhase.POST_KILL, now)
        return self._emit(now)

    def _automatic_target_confirmed(
        self,
        events: tuple[NativeCombatEvent, ...],
    ) -> bool:
        return not self._config.automatic_target_requires_combat_event or any(
            event.kind is NativeCombatEventKind.PLAYER_HIT_TARGET for event in events
        )

    def _clear_engagement(self) -> None:
        self._engaged_target_token = None
        self._last_health = None
        self._last_progress_at = None
        self._selection_lost_at = None
        self._reengage_attempts = 0
        self._last_interrupt_action_sequence = None
        self._interrupts_for_target = 0

    def _enter(self, phase: PvEPhase, now_ms: int) -> None:
        self._phase = phase
        self._phase_entered_at = now_ms

    def _phase_elapsed(self, now_ms: int) -> int:
        assert self._phase_entered_at is not None
        return now_ms - self._phase_entered_at

    def _emit(
        self,
        now_ms: int,
        intent: PvEIntent | None = None,
        *,
        terminal_reason: str | None = None,
    ) -> PvEControllerDecision:
        decision = PvEControllerDecision(
            decision_id=self._decision_id,
            now_ms=now_ms,
            phase=self._phase,
            kills=self._kills,
            intent=intent,
            terminal_reason=terminal_reason,
        )
        self._decision_id += 1
        if intent is PvEIntent.ACQUIRE_NEXT_MOB:
            self._last_acquire_at = now_ms
        elif intent not in (None, PvEIntent.ATTACK_SELECTED_TARGET):
            self._last_power_at[intent] = now_ms
        return decision
