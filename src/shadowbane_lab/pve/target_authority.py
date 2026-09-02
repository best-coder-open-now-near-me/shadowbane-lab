"""Bounded target validation for native-population PvE acquisition."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.pve.controller import PvEController as _BasePvEController
from shadowbane_lab.pve.model import (
    PvEControllerConfig,
    PvEControllerDecision,
    PvEIntent,
    PvEObservation,
    PvEPhase,
)


class PvETargetRejectionReason(StrEnum):
    """Stable reasons why a native-population candidate was quarantined."""

    TARGET_CYCLE_WRAPPED = "target_cycle_wrapped"
    TARGET_SNAPSHOT_UNAVAILABLE = "target_snapshot_unavailable"
    TARGET_IDENTITY_UNAVAILABLE = "target_identity_unavailable"
    TARGET_DEAD = "target_dead"
    TARGET_OUTSIDE_CAMP = "target_outside_camp"
    TARGET_NOT_ATTACK_ELIGIBLE = "target_not_attack_eligible"


@dataclass(frozen=True, slots=True)
class PvETargetRejection:
    """One bounded native-population candidate rejection."""

    target_token: str
    reason: PvETargetRejectionReason
    at_ms: int
    validation_wait_ms: int
    population_generation: int
    selected_target_token: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.target_token, str) or not self.target_token.strip():
            raise ValueError("target rejection requires a non-empty target token")
        if not isinstance(self.reason, PvETargetRejectionReason):
            raise ValueError("target rejection reason must be PvETargetRejectionReason")
        for value, field_name in (
            (self.at_ms, "at_ms"),
            (self.validation_wait_ms, "validation_wait_ms"),
            (self.population_generation, "population_generation"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.selected_target_token is not None and not self.selected_target_token.strip():
            raise ValueError("selected_target_token must be non-empty when present")


class PvEController(_BasePvEController):
    """Adds bounded selected-candidate validation to the core PvE state machine."""

    _MAXIMUM_RETAINED_TARGET_REJECTIONS = 256

    def __init__(self, config: PvEControllerConfig) -> None:
        super().__init__(config)
        self._population_candidate_selected_at: int | None = None
        self._target_rejections: deque[PvETargetRejection] = deque(
            maxlen=self._MAXIMUM_RETAINED_TARGET_REJECTIONS
        )

    @property
    def candidate_validation_timeout_ms(self) -> int:
        """Maximum time a selected population token may lack a usable target snapshot."""

        return min(
            self._config.acquisition_timeout_ms,
            max(
                self._config.acquisition_retry_ms,
                self._config.target_sample_interval_ms * 3,
            ),
        )

    @property
    def target_rejections(self) -> tuple[PvETargetRejection, ...]:
        """Return the bounded ordered tail of candidate rejections."""

        return tuple(self._target_rejections)

    def _enter(self, phase: PvEPhase, now_ms: int) -> None:
        super()._enter(phase, now_ms)
        self._population_candidate_selected_at = None

    def _seek_population(self, observation: PvEObservation) -> PvEControllerDecision:
        """Rank population candidates while bounding validation of the selected token."""

        now = observation.now_ms
        population = observation.population
        player_position = observation.player_position
        if population is None or player_position is None:
            return self.stop("native_population_unavailable", now_ms=now)

        while True:
            self._expire_failed_targets(now)
            ranked = sorted(
                (
                    (
                        ((character.lt - player_position.lt) ** 2)
                        + ((character.lg - player_position.lg) ** 2),
                        character.token,
                    )
                    for character in population.characters
                    if character.attack_eligible
                    and character.token not in self._failed_target_tokens
                    and (
                        self._camp is None
                        or self._camp.contains(character.lt, character.lg)
                    )
                ),
                key=lambda item: (item[0], item[1]),
            )
            candidate_tokens = {token for _, token in ranked}
            if self._population_desired_target_token not in candidate_tokens:
                self._population_desired_target_token = ranked[0][1] if ranked else None
                self._population_cycle_seen.clear()
                self._population_candidate_selected_at = None

            desired = self._population_desired_target_token
            if desired is None:
                if self._config.continuous:
                    return self._begin_camp_idle(observation)
                if self._phase_elapsed(now) >= self._config.acquisition_timeout_ms:
                    return self.stop("mob_acquisition_timeout", now_ms=now)
                return self._emit(now)

            selected = population.selected_target_token
            if selected == desired:
                if self._population_candidate_selected_at is None:
                    self._population_candidate_selected_at = now
                immediate_rejection = self._selected_candidate_rejection_reason(
                    observation,
                    desired,
                )
                if immediate_rejection is not None:
                    self._quarantine_population_candidate(
                        observation,
                        desired,
                        immediate_rejection,
                    )
                    continue
                if self._target_attack_eligible(observation):
                    self._require_different_target = False
                    return self._begin_engagement(observation)
                selected_at = self._population_candidate_selected_at
                assert selected_at is not None
                if now - selected_at >= self.candidate_validation_timeout_ms:
                    timeout_reason = (
                        PvETargetRejectionReason.TARGET_SNAPSHOT_UNAVAILABLE
                        if not observation.target.target_present
                        else PvETargetRejectionReason.TARGET_IDENTITY_UNAVAILABLE
                    )
                    self._quarantine_population_candidate(
                        observation,
                        desired,
                        timeout_reason,
                    )
                    continue
                return self._emit(now)

            self._population_candidate_selected_at = None
            if selected in self._population_cycle_seen:
                self._quarantine_population_candidate(
                    observation,
                    desired,
                    PvETargetRejectionReason.TARGET_CYCLE_WRAPPED,
                )
                continue
            self._population_cycle_seen.add(selected)
            if self._target_sample_ready(now):
                return self._emit(now, PvEIntent.ACQUIRE_NEXT_MOB)
            return self._emit(now)

    def _selected_candidate_rejection_reason(
        self,
        observation: PvEObservation,
        desired: str,
    ) -> PvETargetRejectionReason | None:
        target = observation.target
        if not target.target_present:
            return None
        if target.target_token != desired:
            return PvETargetRejectionReason.TARGET_SNAPSHOT_UNAVAILABLE
        if target.current_health == 0.0:
            return PvETargetRejectionReason.TARGET_DEAD
        if self._target_inside_camp(observation) is False:
            return PvETargetRejectionReason.TARGET_OUTSIDE_CAMP
        identity = observation.target_identity
        if identity is None:
            return None
        if not identity.classification_available:
            return PvETargetRejectionReason.TARGET_IDENTITY_UNAVAILABLE
        if not identity.attack_eligible:
            return PvETargetRejectionReason.TARGET_NOT_ATTACK_ELIGIBLE
        return None

    def _quarantine_population_candidate(
        self,
        observation: PvEObservation,
        target_token: str,
        reason: PvETargetRejectionReason,
    ) -> None:
        population = observation.population
        assert population is not None
        selected_at = self._population_candidate_selected_at
        validation_wait_ms = (
            0 if selected_at is None else max(0, observation.now_ms - selected_at)
        )
        self._target_rejections.append(
            PvETargetRejection(
                target_token=target_token,
                reason=reason,
                at_ms=observation.now_ms,
                validation_wait_ms=validation_wait_ms,
                population_generation=population.scan_generation,
                selected_target_token=population.selected_target_token,
            )
        )
        self._failed_target_tokens[target_token] = observation.now_ms
        self._population_desired_target_token = None
        self._population_cycle_seen.clear()
        self._population_candidate_selected_at = None
