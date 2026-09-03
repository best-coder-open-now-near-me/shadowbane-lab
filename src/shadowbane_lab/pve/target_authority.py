"""Bound target validation and optional positive hostile-NPC authority."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, fields
from enum import StrEnum

from shadowbane_lab.pve.authority import (
    PvETargetAuthorityDecision,
    PvETargetAuthorityEvaluator,
)
from shadowbane_lab.pve.controller import PvEController as _BasePvEController
from shadowbane_lab.pve.model import (
    PvEControllerConfig,
    PvEControllerDecision,
    PvEIntent,
    PvEKillConfirmation,
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
    TARGET_AUTHORITY_UNAVAILABLE = "target_authority_unavailable"
    TARGET_AUTHORITY_REJECTED = "target_authority_rejected"


@dataclass(frozen=True, slots=True)
class PvETargetRejection:
    """One bounded native-population candidate rejection."""

    target_token: str
    reason: PvETargetRejectionReason
    at_ms: int
    validation_wait_ms: int
    population_generation: int
    selected_target_token: str | None
    authority_exclusions: tuple[str, ...] = ()

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
        if not isinstance(self.authority_exclusions, tuple):
            raise ValueError("authority_exclusions must be a tuple")
        if len(self.authority_exclusions) != len(set(self.authority_exclusions)):
            raise ValueError("authority_exclusions must not contain duplicates")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in self.authority_exclusions
        ):
            raise ValueError("authority_exclusions must contain non-empty strings")

    def as_dict(self) -> dict[str, object]:
        return {
            "target_token": self.target_token,
            "reason": self.reason.value,
            "at_ms": self.at_ms,
            "validation_wait_ms": self.validation_wait_ms,
            "population_generation": self.population_generation,
            "selected_target_token": self.selected_target_token,
            "authority_exclusions": list(self.authority_exclusions),
        }


@dataclass(frozen=True, slots=True)
class PvETargetAuthorityControllerDecision(PvEControllerDecision):
    """Controller decision carrying authority evidence from the same observation."""

    target_authority: PvETargetAuthorityDecision | None = None
    target_rejections: tuple[PvETargetRejection, ...] = ()

    def __post_init__(self) -> None:
        PvEControllerDecision.__post_init__(self)
        if self.target_authority is not None:
            if not isinstance(self.target_authority, PvETargetAuthorityDecision):
                raise ValueError("target_authority must be PvETargetAuthorityDecision")
            if self.target_authority.observed_at_ms != self.now_ms:
                raise ValueError("target authority time must match controller decision time")
        if not isinstance(self.target_rejections, tuple):
            raise ValueError("target_rejections must be a tuple")
        if any(
            not isinstance(value, PvETargetRejection)
            for value in self.target_rejections
        ):
            raise ValueError("target_rejections must contain PvETargetRejection values")
        if any(value.at_ms != self.now_ms for value in self.target_rejections):
            raise ValueError("target rejection time must match controller decision time")

    @classmethod
    def from_decision(
        cls,
        decision: PvEControllerDecision,
        *,
        target_authority: PvETargetAuthorityDecision | None,
        target_rejections: tuple[PvETargetRejection, ...],
    ) -> PvETargetAuthorityControllerDecision:
        if not isinstance(decision, PvEControllerDecision):
            raise ValueError("decision must be PvEControllerDecision")
        values = {
            field.name: getattr(decision, field.name)
            for field in fields(PvEControllerDecision)
        }
        return cls(
            **values,
            target_authority=target_authority,
            target_rejections=target_rejections,
        )


class PvEController(_BasePvEController):
    """Bounds candidate validation and can require verified hostile-NPC proof."""

    _MAXIMUM_RETAINED_TARGET_REJECTIONS = 256
    _MAXIMUM_RETAINED_AUTHORITY_DECISIONS = 256

    def __init__(
        self,
        config: PvEControllerConfig,
        *,
        target_authority_evaluator: PvETargetAuthorityEvaluator | None = None,
        require_verified_target_authority: bool = False,
    ) -> None:
        if not isinstance(require_verified_target_authority, bool):
            raise ValueError("require_verified_target_authority must be boolean")
        if target_authority_evaluator is not None and not isinstance(
            target_authority_evaluator,
            PvETargetAuthorityEvaluator,
        ):
            raise ValueError(
                "target_authority_evaluator must implement PvETargetAuthorityEvaluator"
            )
        if require_verified_target_authority and target_authority_evaluator is None:
            raise ValueError(
                "verified target authority requires a target_authority_evaluator"
            )
        super().__init__(config)
        self._population_candidate_selected_at: int | None = None
        self._target_rejections: deque[PvETargetRejection] = deque(
            maxlen=self._MAXIMUM_RETAINED_TARGET_REJECTIONS
        )
        self._target_authority_evaluator = target_authority_evaluator
        self._require_verified_target_authority = require_verified_target_authority
        self._active_target_authority: PvETargetAuthorityDecision | None = None
        self._active_step_target_rejections: list[PvETargetRejection] = []
        self._target_authority_history: deque[PvETargetAuthorityDecision] = deque(
            maxlen=self._MAXIMUM_RETAINED_AUTHORITY_DECISIONS
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

    @property
    def require_verified_target_authority(self) -> bool:
        return self._require_verified_target_authority

    @property
    def target_authority_history(self) -> tuple[PvETargetAuthorityDecision, ...]:
        """Return the bounded ordered authority decisions evaluated by this controller."""

        return tuple(self._target_authority_history)

    @property
    def latest_target_authority(self) -> PvETargetAuthorityDecision | None:
        return (
            None
            if not self._target_authority_history
            else self._target_authority_history[-1]
        )

    def step(self, observation: PvEObservation) -> PvEControllerDecision:
        if not isinstance(observation, PvEObservation):
            raise ValueError("observation must be PvEObservation")
        self._active_step_target_rejections.clear()
        authority = None
        if self._target_authority_evaluator is not None:
            authority = self._target_authority_evaluator.evaluate(observation)
            if not isinstance(authority, PvETargetAuthorityDecision):
                raise ValueError(
                    "target authority evaluator must return PvETargetAuthorityDecision"
                )
            if authority.observed_at_ms != observation.now_ms:
                raise ValueError("target authority decision time does not match observation")
            if authority.target_token != observation.target.target_token:
                raise ValueError("target authority decision token does not match observation")
            self._target_authority_history.append(authority)
        self._active_target_authority = authority
        try:
            return super().step(observation)
        finally:
            self._active_target_authority = None
            self._active_step_target_rejections.clear()

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
        if identity is not None:
            if not identity.classification_available:
                return PvETargetRejectionReason.TARGET_IDENTITY_UNAVAILABLE
            if not identity.attack_eligible:
                return PvETargetRejectionReason.TARGET_NOT_ATTACK_ELIGIBLE
        if self._require_verified_target_authority:
            authority = self._active_target_authority
            if authority is None:
                return PvETargetRejectionReason.TARGET_AUTHORITY_UNAVAILABLE
            if not authority.accepted:
                return PvETargetRejectionReason.TARGET_AUTHORITY_REJECTED
        return None

    def _target_attack_eligible(self, observation: PvEObservation) -> bool:
        if not super()._target_attack_eligible(observation):
            return False
        if not self._require_verified_target_authority:
            return True
        authority = self._active_target_authority
        return authority is not None and authority.accepted

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
        authority = self._active_target_authority
        authority_exclusions = (
            ()
            if authority is None or authority.target_token != target_token
            else tuple(value.value for value in authority.exclusions)
        )
        rejection = PvETargetRejection(
            target_token=target_token,
            reason=reason,
            at_ms=observation.now_ms,
            validation_wait_ms=validation_wait_ms,
            population_generation=population.scan_generation,
            selected_target_token=population.selected_target_token,
            authority_exclusions=authority_exclusions,
        )
        self._target_rejections.append(rejection)
        self._active_step_target_rejections.append(rejection)
        self._failed_target_tokens[target_token] = observation.now_ms
        self._population_desired_target_token = None
        self._population_cycle_seen.clear()
        self._population_candidate_selected_at = None

    def _emit(
        self,
        now_ms: int,
        intent: PvEIntent | None = None,
        *,
        terminal_reason: str | None = None,
        kill_confirmation: PvEKillConfirmation | None = None,
        reposition_requested: bool = False,
        return_to_camp: bool = False,
    ) -> PvEControllerDecision:
        decision = super()._emit(
            now_ms,
            intent,
            terminal_reason=terminal_reason,
            kill_confirmation=kill_confirmation,
            reposition_requested=reposition_requested,
            return_to_camp=return_to_camp,
        )
        return PvETargetAuthorityControllerDecision.from_decision(
            decision,
            target_authority=self._active_target_authority,
            target_rejections=tuple(self._active_step_target_rejections),
        )
