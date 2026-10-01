"""Typed contracts for the bounded PvE controller and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import hypot, isfinite
from typing import TYPE_CHECKING

from shadowbane_lab.client_observation import (
    NativeCharacterObservation,
    NativeCharacterPopulationObservation,
    NativeCombatEvent,
    NativePlayerActionObservation,
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
    NativeTargetActionObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetPositionObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.travel.model import TravelDecision, TravelDestination

if TYPE_CHECKING:
    from shadowbane_lab.pve.authority_snapshot import PvETargetAuthoritySnapshot
    from shadowbane_lab.pve.listed_combat import ListedCombatUpdate
    from shadowbane_lab.pve.native_actor import NativePreparationUpdate
    from shadowbane_lab.pve.native_combat import NativeCombatUpdate


def _positive_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _non_negative_integer(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


class PvEIntent(StrEnum):
    ACQUIRE_NEXT_MOB = "client.pve.target_next_mobile"
    ACQUIRE_PREVIOUS_MOB = "client.pve.target_previous_mobile"
    CAST_SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"
    ATTACK_SELECTED_TARGET = "shadowbane.basic_attack"


class PvECombatKind(StrEnum):
    BIND = "bind"
    ATTACK = "attack"
    CAST = "cast"
    SELF_POWER = "self_power"


class PvEAbilityRecipient(StrEnum):
    ACTOR = "actor"
    ENGAGEMENT_TARGET = "engagement_target"


@dataclass(frozen=True, slots=True)
class PvEAbility:
    """Configured native power identity and recipient, independent of class/hotbar."""

    power_id: int
    recipient: PvEAbilityRecipient

    def __post_init__(self) -> None:
        if type(self.power_id) is not int or not 0 < self.power_id < 2**32:
            raise ValueError("ability power_id must be a positive uint32")
        if not isinstance(self.recipient, PvEAbilityRecipient):
            raise ValueError("ability recipient must be typed")

    @property
    def kind(self) -> PvECombatKind:
        return (PvECombatKind.SELF_POWER if self.recipient is PvEAbilityRecipient.ACTOR
                else PvECombatKind.CAST)

    def as_dict(self) -> dict[str, object]:
        return {"power_id": self.power_id, "recipient": self.recipient.value}


# Compatibility is confined to configuration; native proposals always carry IDs.
_LEGACY_ABILITIES = {
    PvEIntent.CAST_SHADOW_TOUCH: PvEAbility(428918601, PvEAbilityRecipient.ENGAGEMENT_TARGET),
}


class PvECombatDisposition(StrEnum):
    BOUND = "bound"
    QUEUED = "queued"
    DEFERRED = "deferred"
    NOT_READY = "not_ready"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class PvECombatNotReadyReason(StrEnum):
    POWER_REUSE = "power_reuse"


@dataclass(frozen=True, slots=True)
class PvECombatProposal:
    """Immutable policy request; the coordinator owns native IDs and authority."""

    proposal_id: int
    target_token: str
    target_key: NativeObjectKey
    kind: PvECombatKind
    power_id: int = 0
    adopted_existing_action: bool = False
    interrupt_sequence: int | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.proposal_id, "proposal_id")
        if not isinstance(self.target_token, str) or not self.target_token.strip():
            raise ValueError("combat proposal requires an opaque target token")
        if not isinstance(self.target_key, NativeObjectKey) or self.target_key.is_null:
            raise ValueError("combat proposal requires an exact native object key")
        if not isinstance(self.kind, PvECombatKind):
            raise ValueError("combat proposal requires a semantic kind")
        if type(self.power_id) is not int or not 0 <= self.power_id < 2**32:
            raise ValueError("power_id must be uint32")
        if (self.kind in (PvECombatKind.CAST, PvECombatKind.SELF_POWER)) != (self.power_id != 0):
            raise ValueError("only power actions require a numeric power ID")
        if type(self.adopted_existing_action) is not bool:
            raise ValueError("adopted_existing_action must be boolean")
        if self.adopted_existing_action and self.kind is not PvECombatKind.BIND:
            raise ValueError("existing action adoption requires BIND")
        if self.interrupt_sequence is not None:
            _non_negative_integer(self.interrupt_sequence, "interrupt_sequence")
            if self.kind is not PvECombatKind.CAST:
                raise ValueError("interrupt metadata requires CAST")

    def as_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id, "target_token": self.target_token,
            "target_key": [self.target_key.object_type, self.target_key.object_uuid],
            "kind": self.kind.value, "power_id": self.power_id,
            "adopted_existing_action": self.adopted_existing_action,
            "interrupt_sequence": self.interrupt_sequence,
        }


@dataclass(frozen=True, slots=True)
class PvECombatAcknowledgement:
    """Policy projection of an already correlated native receipt, never text."""

    disposition: PvECombatDisposition
    native_entered: bool | None
    cleanup_required: bool
    not_ready_reason: PvECombatNotReadyReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PvECombatDisposition):
            raise ValueError("combat acknowledgment requires a typed disposition")
        if self.native_entered is not None and type(self.native_entered) is not bool:
            raise ValueError("native entry must remain tri-state")
        if type(self.cleanup_required) is not bool:
            raise ValueError("cleanup_required must be boolean")
        if self.disposition is PvECombatDisposition.NOT_READY:
            if (self.not_ready_reason is not PvECombatNotReadyReason.POWER_REUSE
                    or self.native_entered is not False or not self.cleanup_required):
                raise ValueError("not-ready power requires no entry and retained ownership")
        elif self.not_ready_reason is not None:
            raise ValueError("readiness reason requires not-ready disposition")
        if self.disposition is PvECombatDisposition.QUEUED and self.native_entered is not True:
            raise ValueError("queued action must positively prove native entry")
        if self.disposition is PvECombatDisposition.DEFERRED and self.native_entered is True:
            raise ValueError("deferred acknowledgment cannot claim entry")


class PvEPhase(StrEnum):
    INITIALIZING = "initializing"
    OBSERVING_ACTION = "observing_action"
    SEEKING = "seeking"
    OPENING = "opening"
    ENGAGED = "engaged"
    DISENGAGING = "disengaging"
    POST_KILL = "post_kill"
    RECOVERING = "recovering"
    CAMP_IDLE = "camp_idle"
    COMPLETE = "complete"
    STOPPED = "stopped"


class PvEKillConfirmation(StrEnum):
    NATIVE_COMBAT_EVENT = "native_combat_event"
    NATIVE_HEALTH_ZERO = "native_health_zero"


@dataclass(frozen=True, slots=True)
class PvETrackedTarget:
    """A retained object binding; selection is a separate input channel."""

    token: str
    object_key: NativeObjectKey
    character: NativeCharacterObservation | None

    def __post_init__(self) -> None:
        if (not self.token or not isinstance(self.object_key, NativeObjectKey)
                or self.object_key.is_null):
            raise ValueError("tracked target requires an exact token and object key")
        if self.character is not None and (
            self.character.token != self.token or self.character.object_key != self.object_key
        ):
            raise ValueError("tracked character must match both retained identity fields")

    @property
    def available(self) -> bool:
        return self.character is not None

    def planar_distance(self, observation: PvEObservation) -> float | None:
        player = observation.player_position
        if self.character is None or player is None:
            return None
        return hypot(self.character.lt - player.lt, self.character.lg - player.lg)

    def as_dict(self) -> dict[str, object]:
        character = self.character
        return {
            "token": self.token,
            "object_key": [self.object_key.object_type, self.object_key.object_uuid],
            "available": self.available,
            "current_health": None if character is None else character.current_health,
            "maximum_health": None if character is None else character.maximum_health,
            "lt": None if character is None else character.lt,
            "lg": None if character is None else character.lg,
            "altitude": None if character is None else character.altitude,
        }


@dataclass(frozen=True, slots=True)
class PvETrackedTargetAction:
    """Action detail attributed to an exact retained native object identity."""

    token: str
    object_key: NativeObjectKey
    action: NativeTargetActionObservation

    def __post_init__(self) -> None:
        if (not self.token or not isinstance(self.object_key, NativeObjectKey)
                or self.object_key.is_null
                or not isinstance(self.action, NativeTargetActionObservation)
                or not self.action.target_present or self.action.target_token != self.token):
            raise ValueError("tracked action requires matching native object identity")

    def as_dict(self) -> dict[str, object]:
        return {"token": self.token,
                "object_key": [self.object_key.object_type, self.object_key.object_uuid],
                "initiation_state": self.action.initiation_state,
                "power_protocol_ids": self.action.power_protocol_ids,
                "motion_id": self.action.motion_id,
                "animation_event_index": self.action.animation_event_index,
                "targeting_player": self.action.targeting_player,
                "animation_frame": self.action.animation_frame}


@dataclass(frozen=True, slots=True)
class PvECombatCleanupRequest:
    sequence: int
    target_token: str
    object_key: NativeObjectKey
    reason: str

    def __post_init__(self) -> None:
        _non_negative_integer(self.sequence, "cleanup sequence")
        if not self.target_token or not self.reason:
            raise ValueError("cleanup requires retained target and reason")
        if not isinstance(self.object_key, NativeObjectKey) or self.object_key.is_null:
            raise ValueError("cleanup requires retained object key")

    def as_dict(self) -> dict[str, object]:
        return {"sequence": self.sequence, "target_token": self.target_token,
                "object_key": [self.object_key.object_type, self.object_key.object_uuid],
                "reason": self.reason}


@dataclass(frozen=True, slots=True)
class PvECombatCleanupResult:
    request: PvECombatCleanupRequest
    confirmed: bool
    request_key: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (not isinstance(self.request, PvECombatCleanupRequest)
                or type(self.confirmed) is not bool):
            raise ValueError("invalid cleanup result")
        if self.confirmed and (not self.request_key or self.error is not None):
            raise ValueError("confirmed cleanup requires correlated native acknowledgment")
        if not self.confirmed and not self.error:
            raise ValueError("unconfirmed cleanup requires a diagnostic")

    def as_dict(self) -> dict[str, object]:
        return {**self.request.as_dict(), "confirmed": self.confirmed,
                "request_key": self.request_key, "error": self.error}


@dataclass(frozen=True, slots=True)
class PvECampLease:
    """The spatial operating boundary captured where a continuous run starts."""

    anchor_lt: float
    anchor_lg: float
    radius: float
    return_radius: float
    return_trigger_radius: float | None = None

    def __post_init__(self) -> None:
        if self.return_trigger_radius is None:
            object.__setattr__(
                self,
                "return_trigger_radius",
                self.return_radius + min(18.0, (self.radius - self.return_radius) / 2.0),
            )
        assert self.return_trigger_radius is not None
        for value, field_name in (
            (self.anchor_lt, "anchor_lt"),
            (self.anchor_lg, "anchor_lg"),
            (self.radius, "radius"),
            (self.return_radius, "return_radius"),
            (self.return_trigger_radius, "return_trigger_radius"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"camp {field_name} must be finite")
        if self.radius <= 0:
            raise ValueError("camp radius must be positive")
        if self.return_radius <= 0 or self.return_radius >= self.radius:
            raise ValueError("camp return_radius must be positive and below radius")
        if not self.return_radius < self.return_trigger_radius < self.radius:
            raise ValueError(
                "camp return_trigger_radius must be above return_radius and below radius"
            )

    def contains(self, lt: float, lg: float) -> bool:
        return hypot(lt - self.anchor_lt, lg - self.anchor_lg) <= self.radius

    def distance_from_anchor(self, lt: float, lg: float) -> float:
        return hypot(lt - self.anchor_lt, lg - self.anchor_lg)

    @property
    def return_destination(self) -> TravelDestination:
        return TravelDestination(
            lt=self.anchor_lt,
            lg=self.anchor_lg,
            arrival_radius=self.return_radius,
        )


@dataclass(frozen=True, slots=True)
class PvEControllerConfig:
    maximum_kills: int = 1
    maximum_session_ms: int = 120_000
    acquisition_retry_ms: int = 1_000
    acquisition_timeout_ms: int = 15_000
    stale_selection_cycle_delay_ms: int = 1_000
    nearest_target_sample_count: int = 1
    target_sample_interval_ms: int = 350
    engagement_timeout_ms: int = 30_000
    stalled_progress_ms: int = 5_000
    quiet_melee_timeout_ms: int = 2_500
    incoming_reposition_grace_ms: int = 1_500
    incoming_reposition_window_ms: int = 3_000
    selection_loss_grace_ms: int = 750
    post_kill_delay_ms: int = 1_000
    recovery_timeout_ms: int = 30_000
    maximum_reengage_attempts: int = 2
    maximum_stalled_retargets: int = 0
    maximum_combat_repositions: int = 2
    minimum_player_health_fraction: float = 0.5
    minimum_recovery_health_fraction: float = 0.0
    minimum_recovery_mana_fraction: float = 0.0
    minimum_recovery_stamina_fraction: float = 0.0
    accept_automatic_targets: bool = False
    opening_intent: PvEIntent | None = None
    opening_ability: PvEAbility | None = None
    opening_mana_cost: float = 0.0
    opening_followup_delay_ms: int = 0
    interrupt_intent: PvEIntent | None = None
    interrupt_ability: PvEAbility | None = None
    interrupt_mana_cost: float = 0.0
    interrupt_cooldown_ms: int = 0
    maximum_interrupts_per_target: int = 0
    automatic_attack_expected: bool = False
    automatic_target_requires_active_action: bool = False
    require_target_identity: bool = False
    melee_approach_radius: float = 20.0
    minimum_approach_progress: float = 8.0
    continuous: bool = False
    camp_radius: float | None = None
    camp_return_radius: float = 12.0
    camp_return_trigger_radius: float | None = None
    camp_idle_ms: int = 5_000
    camp_return_retry_ms: int = 5_000
    failed_target_cooldown_ms: int = 30_000

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.maximum_kills, "maximum_kills"),
            (self.maximum_session_ms, "maximum_session_ms"),
            (self.acquisition_retry_ms, "acquisition_retry_ms"),
            (self.acquisition_timeout_ms, "acquisition_timeout_ms"),
            (self.stale_selection_cycle_delay_ms, "stale_selection_cycle_delay_ms"),
            (self.nearest_target_sample_count, "nearest_target_sample_count"),
            (self.target_sample_interval_ms, "target_sample_interval_ms"),
            (self.engagement_timeout_ms, "engagement_timeout_ms"),
            (self.stalled_progress_ms, "stalled_progress_ms"),
            (self.quiet_melee_timeout_ms, "quiet_melee_timeout_ms"),
            (self.incoming_reposition_grace_ms, "incoming_reposition_grace_ms"),
            (self.incoming_reposition_window_ms, "incoming_reposition_window_ms"),
            (self.selection_loss_grace_ms, "selection_loss_grace_ms"),
            (self.post_kill_delay_ms, "post_kill_delay_ms"),
            (self.recovery_timeout_ms, "recovery_timeout_ms"),
            (self.camp_idle_ms, "camp_idle_ms"),
            (self.camp_return_retry_ms, "camp_return_retry_ms"),
            (self.failed_target_cooldown_ms, "failed_target_cooldown_ms"),
        ):
            _positive_integer(value, field_name)
        _non_negative_integer(self.maximum_reengage_attempts, "maximum_reengage_attempts")
        _non_negative_integer(self.maximum_stalled_retargets, "maximum_stalled_retargets")
        _non_negative_integer(
            self.maximum_combat_repositions,
            "maximum_combat_repositions",
        )
        _non_negative_integer(self.opening_followup_delay_ms, "opening_followup_delay_ms")
        _non_negative_integer(self.interrupt_cooldown_ms, "interrupt_cooldown_ms")
        _non_negative_integer(
            self.maximum_interrupts_per_target,
            "maximum_interrupts_per_target",
        )
        if (
            isinstance(self.minimum_player_health_fraction, bool)
            or not isinstance(self.minimum_player_health_fraction, (int, float))
            or not 0.0 < self.minimum_player_health_fraction <= 1.0
        ):
            raise ValueError("minimum_player_health_fraction must be in (0, 1]")
        if self.acquisition_retry_ms > self.acquisition_timeout_ms:
            raise ValueError("acquisition retry cannot exceed acquisition timeout")
        if self.stale_selection_cycle_delay_ms > self.acquisition_timeout_ms:
            raise ValueError("stale selection cycle delay cannot exceed acquisition timeout")
        if self.target_sample_interval_ms > self.acquisition_timeout_ms:
            raise ValueError("target sample interval cannot exceed acquisition timeout")
        if self.stalled_progress_ms > self.engagement_timeout_ms:
            raise ValueError("stalled progress timeout cannot exceed engagement timeout")
        if self.selection_loss_grace_ms > self.engagement_timeout_ms:
            raise ValueError("selection loss grace cannot exceed engagement timeout")
        if self.post_kill_delay_ms > self.recovery_timeout_ms:
            raise ValueError("post-kill delay cannot exceed recovery timeout")
        for value, field_name in (
            (self.minimum_recovery_health_fraction, "minimum_recovery_health_fraction"),
            (self.minimum_recovery_mana_fraction, "minimum_recovery_mana_fraction"),
            (
                self.minimum_recovery_stamina_fraction,
                "minimum_recovery_stamina_fraction",
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise ValueError(f"{field_name} must be in [0, 1]")
        if (
            self.minimum_recovery_health_fraction != 0
            and self.minimum_recovery_health_fraction < self.minimum_player_health_fraction
        ):
            raise ValueError("minimum recovery health cannot be below the player safety threshold")
        for value, field_name in (
            (self.accept_automatic_targets, "accept_automatic_targets"),
            (self.automatic_attack_expected, "automatic_attack_expected"),
            (
                self.automatic_target_requires_active_action,
                "automatic_target_requires_active_action",
            ),
            (self.require_target_identity, "require_target_identity"),
            (self.continuous, "continuous"),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field_name} must be a boolean")
        if self.camp_radius is not None and (
            isinstance(self.camp_radius, bool)
            or not isinstance(self.camp_radius, (int, float))
            or not isfinite(self.camp_radius)
            or self.camp_radius <= 0
        ):
            raise ValueError("camp_radius must be positive when present")
        if (
            isinstance(self.camp_return_radius, bool)
            or not isinstance(self.camp_return_radius, (int, float))
            or not isfinite(self.camp_return_radius)
            or self.camp_return_radius <= 0
        ):
            raise ValueError("camp_return_radius must be positive")
        if self.camp_return_trigger_radius is not None and (
            isinstance(self.camp_return_trigger_radius, bool)
            or not isinstance(self.camp_return_trigger_radius, (int, float))
            or not isfinite(self.camp_return_trigger_radius)
            or self.camp_return_trigger_radius <= 0
        ):
            raise ValueError("camp_return_trigger_radius must be positive when present")
        if self.continuous and self.camp_radius is None:
            raise ValueError("continuous PvE requires a camp_radius")
        if self.camp_radius is not None and self.camp_return_radius >= self.camp_radius:
            raise ValueError("camp_return_radius must be below camp_radius")
        if self.camp_return_trigger_radius is not None and (
            self.camp_return_trigger_radius <= self.camp_return_radius
            or (
                self.camp_radius is not None and self.camp_return_trigger_radius >= self.camp_radius
            )
        ):
            raise ValueError(
                "camp_return_trigger_radius must be above camp_return_radius and below camp_radius"
            )
        for role in ("opening", "interrupt"):
            ability, intent = getattr(self, role + "_ability"), getattr(self, role + "_intent")
            if ability is not None and not isinstance(ability, PvEAbility):
                raise ValueError(f"{role}_ability must be PvEAbility")
            if ability is not None and intent is not None:
                raise ValueError(f"{role} requires ability or legacy intent, not both")
        if (self.interrupt_ability is not None
                and self.interrupt_ability.recipient is not PvEAbilityRecipient.ENGAGEMENT_TARGET):
            raise ValueError("interrupt ability must target the engagement")
        if self.opening_intent is not None and not isinstance(self.opening_intent, PvEIntent):
            raise ValueError("opening_intent must be PvEIntent when present")
        if self.opening_intent in (
            PvEIntent.ACQUIRE_NEXT_MOB,
            PvEIntent.ACQUIRE_PREVIOUS_MOB,
            PvEIntent.ATTACK_SELECTED_TARGET,
        ):
            raise ValueError("opening_intent must be a power activation")
        if (
            isinstance(self.opening_mana_cost, bool)
            or not isinstance(self.opening_mana_cost, (int, float))
            or not isfinite(self.opening_mana_cost)
            or self.opening_mana_cost < 0
        ):
            raise ValueError("opening_mana_cost must be a non-negative number")
        if self.resolved_opening_ability is None and self.opening_mana_cost != 0:
            raise ValueError("opening_mana_cost requires an opening_intent")
        if self.interrupt_intent is not None and not isinstance(self.interrupt_intent, PvEIntent):
            raise ValueError("interrupt_intent must be PvEIntent when present")
        if self.interrupt_intent in (
            PvEIntent.ACQUIRE_NEXT_MOB,
            PvEIntent.ACQUIRE_PREVIOUS_MOB,
            PvEIntent.ATTACK_SELECTED_TARGET,
        ):
            raise ValueError("interrupt_intent must be a power activation")
        if (
            isinstance(self.interrupt_mana_cost, bool)
            or not isinstance(self.interrupt_mana_cost, (int, float))
            or not isfinite(self.interrupt_mana_cost)
            or self.interrupt_mana_cost < 0
        ):
            raise ValueError("interrupt_mana_cost must be a non-negative number")
        if self.resolved_interrupt_ability is None and any(
            (
                self.interrupt_mana_cost != 0,
                self.interrupt_cooldown_ms != 0,
                self.maximum_interrupts_per_target != 0,
            )
        ):
            raise ValueError("interrupt limits require an interrupt_intent")
        if self.resolved_interrupt_ability is not None and self.maximum_interrupts_per_target == 0:
            raise ValueError("interrupt_intent requires a positive per-target limit")
        for value, field_name in (
            (self.melee_approach_radius, "melee_approach_radius"),
            (self.minimum_approach_progress, "minimum_approach_progress"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{field_name} must be positive")


    @property
    def resolved_opening_ability(self) -> PvEAbility | None:
        return self.opening_ability or _LEGACY_ABILITIES.get(self.opening_intent)

    @property
    def resolved_interrupt_ability(self) -> PvEAbility | None:
        return self.interrupt_ability or _LEGACY_ABILITIES.get(self.interrupt_intent)


@dataclass(frozen=True, slots=True)
class PvEObservation:
    now_ms: int
    target: NativeTargetHealthObservation
    player: NativePlayerVitalsObservation
    combat_events: tuple[NativeCombatEvent, ...] = ()
    player_position: NativePlayerPositionObservation | None = None
    target_position: NativeTargetPositionObservation | None = None
    target_action: NativeTargetActionObservation | None = None
    tracked_target_action: PvETrackedTargetAction | None = None
    selection_observed: bool = True
    player_action: NativePlayerActionObservation | None = None
    target_identity: NativeTargetIdentityObservation | None = None
    population: NativeCharacterPopulationObservation | None = None
    authority_snapshot: PvETargetAuthoritySnapshot | None = None

    def __post_init__(self) -> None:
        _non_negative_integer(self.now_ms, "now_ms")
        if not isinstance(self.selection_observed, bool):
            raise ValueError("selection_observed must be boolean")
        if not self.selection_observed and self.target.target_present:
            raise ValueError("unavailable selection cannot contain selected health")
        if self.tracked_target_action is not None:
            bound = self.tracked_target_action
            if (not isinstance(bound, PvETrackedTargetAction) or self.population is None
                    or not any(c.token == bound.token and c.object_key == bound.object_key
                               for c in self.population.characters)):
                raise ValueError("tracked action and population resolved different identities")
        if self.authority_snapshot is not None:
            from shadowbane_lab.pve.authority_snapshot import PvETargetAuthoritySnapshot

            if not isinstance(self.authority_snapshot, PvETargetAuthoritySnapshot):
                raise ValueError("authority_snapshot must be PvETargetAuthoritySnapshot")
            if self.population is None:
                raise ValueError("authority snapshot requires the sampled population")
            if (
                self.authority_snapshot.local_player_object_key
                != self.population.local_player_object_key
                or {(c.target_token, c.object_key) for c in self.authority_snapshot.characters}
                != {(c.token, c.object_key) for c in self.population.characters}
            ):
                raise ValueError("authority snapshot and population resolved different identities")
        if not isinstance(self.target, NativeTargetHealthObservation):
            raise ValueError("target must be NativeTargetHealthObservation")
        if not isinstance(self.player, NativePlayerVitalsObservation):
            raise ValueError("player must be NativePlayerVitalsObservation")
        if any(not isinstance(event, NativeCombatEvent) for event in self.combat_events):
            raise ValueError("combat_events must contain NativeCombatEvent values")
        sequences = tuple(event.sequence for event in self.combat_events)
        if sequences != tuple(sorted(sequences)) or len(sequences) != len(set(sequences)):
            raise ValueError("combat events must have unique ascending sequences")
        if self.target_action is not None:
            if not isinstance(self.target_action, NativeTargetActionObservation):
                raise ValueError("target_action must be NativeTargetActionObservation")
            if self.target.target_present != self.target_action.target_present:
                raise ValueError("target health and action disagree about target presence")
            if (
                self.target.target_present
                and self.target.target_token != self.target_action.target_token
            ):
                raise ValueError("target health and action resolved different targets")
        if self.player_action is not None and not isinstance(
            self.player_action,
            NativePlayerActionObservation,
        ):
            raise ValueError("player_action must be NativePlayerActionObservation")
        if self.player_action is not None:
            if (self.population is not None and self.player_action.action_target_token
                    != self.population.player_action_target_token):
                raise ValueError("population and player action resolved different action targets")
        if self.target_identity is not None:
            if not isinstance(self.target_identity, NativeTargetIdentityObservation):
                raise ValueError("target_identity must be NativeTargetIdentityObservation")
            if self.target.target_present != self.target_identity.target_present:
                raise ValueError("target health and identity disagree about target presence")
            if (
                self.target.target_present
                and self.target.target_token != self.target_identity.target_token
            ):
                raise ValueError("target health and identity resolved different targets")
        if self.population is not None:
            if not isinstance(self.population, NativeCharacterPopulationObservation):
                raise ValueError("population must be NativeCharacterPopulationObservation")
            if (
                self.target.target_present
                and self.target.target_token != self.population.selected_target_token
            ):
                raise ValueError("target health and population resolved different selections")
        if (self.player_position is None) != (self.target_position is None):
            raise ValueError("player and target positions must be observed together")
        if self.player_position is None:
            return
        if not isinstance(self.player_position, NativePlayerPositionObservation):
            raise ValueError("player_position must be NativePlayerPositionObservation")
        if not isinstance(self.target_position, NativeTargetPositionObservation):
            raise ValueError("target_position must be NativeTargetPositionObservation")
        if self.target.target_present != self.target_position.target_present:
            raise ValueError("target health and position disagree about target presence")
        if (
            self.target.target_present
            and self.target.target_token != self.target_position.target_token
        ):
            raise ValueError("target health and position resolved different targets")

    @property
    def target_planar_distance(self) -> float | None:
        if self.player_position is None or self.target_position is None:
            return None
        if not self.target_position.target_present:
            return None
        assert self.target_position.lt is not None
        assert self.target_position.lg is not None
        return hypot(
            self.target_position.lt - self.player_position.lt,
            self.target_position.lg - self.player_position.lg,
        )

    @property
    def target_altitude_delta(self) -> float | None:
        if self.player_position is None or self.target_position is None:
            return None
        if not self.target_position.target_present:
            return None
        assert self.target_position.altitude is not None
        return self.target_position.altitude - self.player_position.altitude

    @property
    def target_spatial_distance(self) -> float | None:
        planar = self.target_planar_distance
        altitude = self.target_altitude_delta
        if planar is None or altitude is None:
            return None
        return hypot(planar, altitude)

    @property
    def target_attack_eligible(self) -> bool | None:
        if self.target_identity is None:
            return None
        return self.target_identity.attack_eligible


@dataclass(frozen=True, slots=True)
class PvEControllerDecision:
    decision_id: int
    now_ms: int
    phase: PvEPhase
    kills: int
    intent: PvEIntent | None = None
    reposition_requested: bool = False
    camp: PvECampLease | None = None
    target_inside_camp: bool | None = None
    return_to_camp: bool = False
    terminal_reason: str | None = None
    kill_confirmation: PvEKillConfirmation | None = None
    acquisition_target_token: str | None = None
    cleanup_request: PvECombatCleanupRequest | None = None
    tracked_target: PvETrackedTarget | None = None
    native_action_pending: bool = False
    opening_skill_skipped: bool = False
    opening_skill_skip_reason: PvECombatNotReadyReason | None = None
    combat_proposal: PvECombatProposal | None = None

    def __post_init__(self) -> None:
        if (type(self.opening_skill_skipped) is not bool
                or (self.opening_skill_skipped
                    and self.opening_skill_skip_reason is not PvECombatNotReadyReason.POWER_REUSE)
                or (not self.opening_skill_skipped and self.opening_skill_skip_reason is not None)):
            raise ValueError("opening skip requires typed power reuse proof")

        _non_negative_integer(self.decision_id, "decision_id")
        _non_negative_integer(self.now_ms, "now_ms")
        _non_negative_integer(self.kills, "kills")
        proposal = self.combat_proposal
        if proposal is not None:
            if not isinstance(proposal, PvECombatProposal):
                raise ValueError("combat_proposal must be typed")
            if proposal.proposal_id != self.decision_id:
                raise ValueError("combat proposal must belong to this decision")
            if self.cleanup_request is not None or self.terminal_reason is not None:
                raise ValueError("cleanup/terminal decisions cannot submit combat")
            if self.native_action_pending and proposal.kind is not PvECombatKind.BIND:
                raise ValueError("busy native action cannot submit a conflicting action")
        if not isinstance(self.phase, PvEPhase):
            raise ValueError("phase must be PvEPhase")
        if self.intent is not None and not isinstance(self.intent, PvEIntent):
            raise ValueError("intent must be PvEIntent when present")
        if not isinstance(self.reposition_requested, bool):
            raise ValueError("reposition_requested must be boolean")
        if self.camp is not None and not isinstance(self.camp, PvECampLease):
            raise ValueError("camp must be PvECampLease when present")
        if self.target_inside_camp is not None and not isinstance(
            self.target_inside_camp,
            bool,
        ):
            raise ValueError("target_inside_camp must be boolean when present")
        if self.target_inside_camp is not None and self.camp is None:
            raise ValueError("target_inside_camp requires a camp lease")
        if not isinstance(self.return_to_camp, bool):
            raise ValueError("return_to_camp must be boolean")
        if self.return_to_camp and self.camp is None:
            raise ValueError("return_to_camp requires a camp lease")
        if self.return_to_camp and self.phase not in (PvEPhase.CAMP_IDLE, PvEPhase.RECOVERING):
            raise ValueError("return_to_camp is valid only while camp-idle or recovering")
        if self.kill_confirmation is not None and not isinstance(
            self.kill_confirmation, PvEKillConfirmation
        ):
            raise ValueError("kill_confirmation must be PvEKillConfirmation when present")
        if self.kill_confirmation is not None and self.intent is not None:
            raise ValueError("kill-confirmation decisions cannot dispatch input")
        if self.kill_confirmation is not None and self.reposition_requested:
            raise ValueError("kill-confirmation decisions cannot request repositioning")
        if self.acquisition_target_token is not None and not self.acquisition_target_token.strip():
            raise ValueError("acquisition_target_token must be non-empty when present")
        if self.acquisition_target_token is not None and self.phase is not PvEPhase.SEEKING:
            raise ValueError("acquisition_target_token is valid only while seeking")
        if self.native_action_pending and (self.intent is not None or self.reposition_requested):
            raise ValueError("uncompleted native action cannot dispatch conflicting input")
        if self.cleanup_request is not None and (
            self.intent is not None or self.reposition_requested or self.return_to_camp
        ):
            raise ValueError("pending cleanup cannot dispatch input or movement")
        terminal = self.phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)
        if terminal != (self.terminal_reason is not None):
            raise ValueError("terminal phases require exactly one terminal reason")
        if terminal and self.intent is not None:
            raise ValueError("terminal decisions cannot dispatch an intent")
        if terminal and self.reposition_requested:
            raise ValueError("terminal decisions cannot request repositioning")
        if terminal and self.return_to_camp:
            raise ValueError("terminal decisions cannot return to camp")

    @property
    def terminal(self) -> bool:
        return self.phase in (PvEPhase.COMPLETE, PvEPhase.STOPPED)


@dataclass(frozen=True, slots=True)
class PvERunTraceStep:
    decision: PvEControllerDecision
    target_present: bool
    current_health: float | None
    maximum_health: float | None
    player_current_health: float | None = None
    player_maximum_health: float | None = None
    player_current_mana: float | None = None
    player_maximum_mana: float | None = None
    player_current_stamina: float | None = None
    player_maximum_stamina: float | None = None
    target_token: str | None = None
    player_position: NativePlayerPositionObservation | None = None
    target_position: NativeTargetPositionObservation | None = None
    target_action: NativeTargetActionObservation | None = None
    tracked_target_action: PvETrackedTargetAction | None = None
    selection_observed: bool = True
    player_action: NativePlayerActionObservation | None = None
    target_identity: NativeTargetIdentityObservation | None = None
    target_planar_distance: float | None = None
    target_altitude_delta: float | None = None
    target_spatial_distance: float | None = None
    combat_events: tuple[NativeCombatEvent, ...] = ()
    input_accepted: bool | None = None
    input_reason: str | None = None
    approach_status: str | None = None
    approach_decision: TravelDecision | None = None
    approach_input_accepted: bool | None = None
    approach_input_reason: str | None = None
    movement_stop_accepted: bool | None = None
    movement_stop_reason: str | None = None
    movement_arrival_confirmed: bool | None = None
    population_character_count: int | None = None
    population_attack_eligible_count: int | None = None
    population_selected_target_token: str | None = None
    population_player_action_target_token: str | None = None
    population_scan_generation: int | None = None
    native_combat: NativeCombatUpdate | None = None
    preparation: NativePreparationUpdate | None = None
    listed_combat: ListedCombatUpdate | None = None
    combat_cleanup: PvECombatCleanupResult | None = None

    def __post_init__(self) -> None:
        if self.movement_arrival_confirmed is not None:
            if type(self.movement_arrival_confirmed) is not bool:
                raise ValueError("movement_arrival_confirmed must be boolean when present")
            if self.approach_decision is None or not self.approach_decision.terminal:
                raise ValueError("arrival confirmation requires a terminal approach decision")
        if not isinstance(self.decision, PvEControllerDecision):
            raise ValueError("decision must be PvEControllerDecision")
        if not isinstance(self.target_present, bool):
            raise ValueError("target_present must be a boolean")
        if self.input_accepted is not None and not isinstance(self.input_accepted, bool):
            raise ValueError("input_accepted must be a boolean when present")
        if self.preparation is not None:
            from shadowbane_lab.pve.native_actor import NativePreparationUpdate

            if not isinstance(self.preparation, NativePreparationUpdate):
                raise ValueError("preparation trace requires a typed correlated update")
        if self.native_combat is not None:
            from shadowbane_lab.pve.native_combat import NativeCombatUpdate

            if not isinstance(self.native_combat, NativeCombatUpdate):
                raise ValueError("native combat trace requires a typed correlated update")
        if (self.decision.intent is None and self.decision.combat_proposal is None
                and self.native_combat is None and self.input_accepted is not None):
            raise ValueError("input outcome requires an intent, proposal or native combat update")
        if self.input_reason is not None and self.input_accepted is not False:
            raise ValueError("input_reason is valid only for rejected input")
        if self.approach_status is not None and (
            not isinstance(self.approach_status, str) or not self.approach_status.strip()
        ):
            raise ValueError("approach_status must be a non-empty string when present")
        if self.approach_decision is not None and not isinstance(
            self.approach_decision, TravelDecision
        ):
            raise ValueError("approach_decision must be TravelDecision when present")
        if self.approach_input_accepted is not None and not isinstance(
            self.approach_input_accepted, bool
        ):
            raise ValueError("approach_input_accepted must be a boolean when present")
        if self.approach_input_accepted is not None and (
            self.approach_decision is None or self.approach_decision.minimap_direction is None
        ):
            raise ValueError("approach input outcome requires a movement decision")
        if self.approach_input_reason is not None and self.approach_input_accepted is not False:
            raise ValueError("approach_input_reason is valid only for rejected input")
        if self.movement_stop_accepted is not None and not isinstance(
            self.movement_stop_accepted, bool
        ):
            raise ValueError("movement_stop_accepted must be a boolean when present")
        if self.movement_stop_accepted is not None and (
            self.approach_decision is None or not self.approach_decision.terminal
        ):
            raise ValueError("movement stop outcome requires a terminal approach decision")
        if self.movement_stop_reason is not None and self.movement_stop_accepted is not False:
            raise ValueError("movement_stop_reason is valid only for rejected movement stop")
        if self.player_position is not None and not isinstance(
            self.player_position, NativePlayerPositionObservation
        ):
            raise ValueError("player_position must be NativePlayerPositionObservation")
        if self.target_position is not None and not isinstance(
            self.target_position, NativeTargetPositionObservation
        ):
            raise ValueError("target_position must be NativeTargetPositionObservation")
        if self.target_action is not None and not isinstance(
            self.target_action, NativeTargetActionObservation
        ):
            raise ValueError("target_action must be NativeTargetActionObservation")
        if self.player_action is not None and not isinstance(
            self.player_action,
            NativePlayerActionObservation,
        ):
            raise ValueError("player_action must be NativePlayerActionObservation")
        if self.target_identity is not None and not isinstance(
            self.target_identity, NativeTargetIdentityObservation
        ):
            raise ValueError("target_identity must be NativeTargetIdentityObservation")
        if any(not isinstance(event, NativeCombatEvent) for event in self.combat_events):
            raise ValueError("combat_events must contain NativeCombatEvent values")
        for value, field_name in (
            (self.population_character_count, "population_character_count"),
            (self.population_attack_eligible_count, "population_attack_eligible_count"),
            (self.population_scan_generation, "population_scan_generation"),
        ):
            if value is not None:
                _non_negative_integer(value, field_name)

    def as_dict(self) -> dict[str, object]:
        return {
            "native_combat": None if self.native_combat is None else self.native_combat.as_dict(),
            "preparation": None if self.preparation is None else self.preparation.as_dict(),
            "listed_combat": None if self.listed_combat is None else self.listed_combat.as_dict(),
            "decision_id": self.decision.decision_id,
            "at_ms": self.decision.now_ms,
            "phase": self.decision.phase.value,
            "kills": self.decision.kills,
            "kill_confirmation": (
                None
                if self.decision.kill_confirmation is None
                else self.decision.kill_confirmation.value
            ),
            "selection_observed": self.selection_observed,
            "tracked_target_action": (None if self.tracked_target_action is None
                                      else self.tracked_target_action.as_dict()),
            "tracked_target": (None if self.decision.tracked_target is None
                               else self.decision.tracked_target.as_dict()),
            "combat_proposal": (None if self.decision.combat_proposal is None
                                else self.decision.combat_proposal.as_dict()),
            "combat_cleanup": (None if self.combat_cleanup is None
                               else self.combat_cleanup.as_dict()),
            "native_action_pending": self.decision.native_action_pending,
            "opening_skill_skipped": self.decision.opening_skill_skipped,
            "opening_skill_skip_reason": (None if self.decision.opening_skill_skip_reason is None
                                          else self.decision.opening_skill_skip_reason.value),
            "cleanup_request": (None if self.decision.cleanup_request is None
                                else self.decision.cleanup_request.as_dict()),
            "intent": None if self.decision.intent is None else self.decision.intent.value,
            "acquisition_target_token": self.decision.acquisition_target_token,
            "reposition_requested": self.decision.reposition_requested,
            "camp": (
                None
                if self.decision.camp is None
                else {
                    "anchor_lt": self.decision.camp.anchor_lt,
                    "anchor_lg": self.decision.camp.anchor_lg,
                    "radius": self.decision.camp.radius,
                    "return_radius": self.decision.camp.return_radius,
                    "return_trigger_radius": (self.decision.camp.return_trigger_radius),
                    "target_inside": self.decision.target_inside_camp,
                    "return_requested": self.decision.return_to_camp,
                }
            ),
            "target": {
                "present": self.target_present,
                "token": self.target_token,
                "current_health": self.current_health,
                "maximum_health": self.maximum_health,
                "lt": None if self.target_position is None else self.target_position.lt,
                "lg": None if self.target_position is None else self.target_position.lg,
                "altitude": (
                    None if self.target_position is None else self.target_position.altitude
                ),
                "planar_distance": self.target_planar_distance,
                "altitude_delta": self.target_altitude_delta,
                "spatial_distance": self.target_spatial_distance,
                "action": (
                    None
                    if self.target_action is None
                    else {
                        "targeting_player": self.target_action.targeting_player,
                        "motion_id": self.target_action.motion_id,
                        "animation_event_index": self.target_action.animation_event_index,
                        "animation_frame": self.target_action.animation_frame,
                        "initiation_state": self.target_action.initiation_state,
                        "power_protocol_ids": self.target_action.power_protocol_ids,
                        "initiation_pending": self.target_action.initiation_pending,
                    }
                ),
                "identity": (
                    None
                    if self.target_identity is None
                    else {
                        "classification_available": (self.target_identity.classification_available),
                        "classification_error": self.target_identity.classification_error,
                        "merchant": self.target_identity.merchant,
                        "shopkeeper": self.target_identity.shopkeeper,
                        "arc_character": self.target_identity.arc_character,
                        "banker": self.target_identity.banker,
                        "trainer": self.target_identity.trainer,
                        "minion": self.target_identity.minion,
                        "protected_roles": list(self.target_identity.protected_roles),
                        "attack_eligible": self.target_identity.attack_eligible,
                    }
                ),
            },
            "player": {
                "current_health": self.player_current_health,
                "maximum_health": self.player_maximum_health,
                "current_mana": self.player_current_mana,
                "maximum_mana": self.player_maximum_mana,
                "current_stamina": self.player_current_stamina,
                "maximum_stamina": self.player_maximum_stamina,
                "lt": None if self.player_position is None else self.player_position.lt,
                "lg": None if self.player_position is None else self.player_position.lg,
                "altitude": (
                    None if self.player_position is None else self.player_position.altitude
                ),
                "action": (
                    None
                    if self.player_action is None
                    else {
                        "targeting_selected": self.player_action.targeting_selected,
                        "selection_observed": self.player_action.selection_observed,
                        "selected_target_token": self.player_action.selected_target_token,
                        "action_target_token": self.player_action.action_target_token,
                        "motion_id": self.player_action.motion_id,
                        "animation_event_index": self.player_action.animation_event_index,
                        "animation_frame": self.player_action.animation_frame,
                        "initiation_state": self.player_action.initiation_state,
                        "power_protocol_ids": self.player_action.power_protocol_ids,
                        "initiation_pending": self.player_action.initiation_pending,
                        "mode": self.player_action.mode,
                        "action_state": self.player_action.action_state,
                        "initiation_clear": self.player_action.initiation_clear,
                    }
                ),
            },
            "population": (
                None
                if self.population_character_count is None
                else {
                    "character_count": self.population_character_count,
                    "attack_eligible_count": self.population_attack_eligible_count,
                    "selected_target_token": self.population_selected_target_token,
                    "player_action_target_token": (self.population_player_action_target_token),
                    "scan_generation": self.population_scan_generation,
                }
            ),
            "combat_events": [
                {
                    "sequence": event.sequence,
                    "timestamp": event.timestamp,
                    "kind": event.kind.value,
                    "message": event.message,
                    "target_name": event.target_name,
                    "amount": event.amount,
                }
                for event in self.combat_events
            ],
            "input_accepted": self.input_accepted,
            "input_reason": self.input_reason,
            "approach": (
                None
                if self.approach_status is None
                else {
                    "status": self.approach_status,
                    "phase": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.phase.value
                    ),
                    "maneuver": (
                        None
                        if self.approach_decision is None or self.approach_decision.maneuver is None
                        else self.approach_decision.maneuver.value
                    ),
                    "direction": (
                        None
                        if self.approach_decision is None
                        or self.approach_decision.minimap_direction is None
                        else {
                            "x": self.approach_decision.minimap_direction.x,
                            "y": self.approach_decision.minimap_direction.y,
                        }
                    ),
                    "distance_remaining": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.distance_remaining
                    ),
                    "click_count": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.click_count
                    ),
                    "terminal_reason": (
                        None
                        if self.approach_decision is None
                        else self.approach_decision.terminal_reason
                    ),
                    "input_accepted": self.approach_input_accepted,
                    "input_reason": self.approach_input_reason,
                    "movement_arrival_confirmed": self.movement_arrival_confirmed,
                    "movement_stop_accepted": self.movement_stop_accepted,
                    "movement_stop_reason": self.movement_stop_reason,
                }
            ),
        }


@dataclass(frozen=True, slots=True)
class PvERunResult:
    final_phase: PvEPhase
    terminal_reason: str
    kills: int
    trace: tuple[PvERunTraceStep, ...]
    total_steps: int
    trace_truncated: bool

    def __post_init__(self) -> None:
        if self.final_phase not in (PvEPhase.COMPLETE, PvEPhase.STOPPED):
            raise ValueError("PvE run result must be terminal")
        if not isinstance(self.terminal_reason, str) or not self.terminal_reason.strip():
            raise ValueError("terminal_reason must be a non-empty string")
        _non_negative_integer(self.kills, "kills")
        if any(not isinstance(step, PvERunTraceStep) for step in self.trace):
            raise ValueError("trace must contain PvERunTraceStep values")
        _non_negative_integer(self.total_steps, "total_steps")
        if self.total_steps < len(self.trace):
            raise ValueError("total_steps cannot be below retained trace length")
        if not isinstance(self.trace_truncated, bool):
            raise ValueError("trace_truncated must be boolean")
        if self.trace_truncated != (self.total_steps > len(self.trace)):
            raise ValueError("trace_truncated must match the retained trace length")
