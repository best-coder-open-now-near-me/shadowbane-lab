"""Coherent PvE observation assembly over the canonical runtime dispatch loop."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input import StopSignal
from shadowbane_lab.client_observation import (
    NativeCombatEventParser,
    NativeCombatLogEntry,
    NativeTargetActionObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
    NativeTargetIdentityReadError,
    NativeTargetPositionObservation,
)
from shadowbane_lab.pve.approach import (
    PvEApproachController,
    PvEApproachStatus,
    PvEApproachUpdate,
)
from shadowbane_lab.pve.controller import PvEController as _BasePvEController
from shadowbane_lab.pve.model import PvEObservation
from shadowbane_lab.pve.runtime import (
    CharacterPopulationSource,
    CombatLogSource,
    PlayerActionSource,
    PlayerPositionSource,
    PlayerVitalsSource,
    PvEIntentDispatcher,
    TargetActionSource,
    TargetHealthSource,
    TargetIdentitySource,
    TargetPositionSource,
)
from shadowbane_lab.pve.runtime import (
    PvERunner as _BasePvERunner,
)
from shadowbane_lab.travel import TravelDecision, TravelPhase
from shadowbane_lab.travel.runtime import TravelDecisionDispatcher


class PvEObservationCoherenceError(RuntimeError):
    """Raised when native channels do not describe one stable selected target."""


@runtime_checkable
class PvEObservationSource(Protocol):
    """Build one controller-ready observation from an explicit channel request."""

    def observe(
        self,
        *,
        now_ms: int,
        target_action_active: bool,
        player_action_active: bool,
    ) -> PvEObservation: ...


class NativePvEObservationSource:
    """Assemble native channels behind one selected-target stability boundary.

    Process-backed target-health readers are sampled at the beginning and end of
    each frame. Tape and sequence readers have no process identity and are treated
    as already atomic, preserving deterministic replay and existing test fixtures.
    """

    def __init__(
        self,
        *,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        combat_log_reader: CombatLogSource,
        player_position_reader: PlayerPositionSource | None = None,
        target_position_reader: TargetPositionSource | None = None,
        target_action_reader: TargetActionSource | None = None,
        player_action_reader: PlayerActionSource | None = None,
        target_identity_reader: TargetIdentitySource | None = None,
        population_reader: CharacterPopulationSource | None = None,
    ) -> None:
        if not isinstance(health_reader, TargetHealthSource):
            raise ValueError("health_reader must implement TargetHealthSource")
        if not isinstance(player_vitals_reader, PlayerVitalsSource):
            raise ValueError("player_vitals_reader must implement PlayerVitalsSource")
        if not isinstance(combat_log_reader, CombatLogSource):
            raise ValueError("combat_log_reader must implement CombatLogSource")
        if (player_position_reader is None) != (target_position_reader is None):
            raise ValueError("player and target position readers must be provided together")
        if player_position_reader is not None and not isinstance(
            player_position_reader, PlayerPositionSource
        ):
            raise ValueError("player_position_reader must implement PlayerPositionSource")
        if target_position_reader is not None and not isinstance(
            target_position_reader, TargetPositionSource
        ):
            raise ValueError("target_position_reader must implement TargetPositionSource")
        if target_action_reader is not None and not isinstance(
            target_action_reader, TargetActionSource
        ):
            raise ValueError("target_action_reader must implement TargetActionSource")
        if player_action_reader is not None and not isinstance(
            player_action_reader, PlayerActionSource
        ):
            raise ValueError("player_action_reader must implement PlayerActionSource")
        if target_identity_reader is not None and not isinstance(
            target_identity_reader, TargetIdentitySource
        ):
            raise ValueError("target_identity_reader must implement TargetIdentitySource")
        if population_reader is not None and not isinstance(
            population_reader, CharacterPopulationSource
        ):
            raise ValueError("population_reader must implement CharacterPopulationSource")

        process_ids = {
            process_id
            for reader in (
                health_reader,
                player_vitals_reader,
                player_position_reader,
                target_position_reader,
                target_action_reader,
                player_action_reader,
                target_identity_reader,
                population_reader,
                combat_log_reader,
            )
            if (process_id := self._process_id(reader)) is not None
        }
        if len(process_ids) > 1:
            raise ValueError("native PvE observation readers resolved different processes")

        self._health_reader = health_reader
        self._player_vitals_reader = player_vitals_reader
        self._player_position_reader = player_position_reader
        self._target_position_reader = target_position_reader
        self._target_action_reader = target_action_reader
        self._player_action_reader = player_action_reader
        self._target_identity_reader = target_identity_reader
        self._population_reader = population_reader
        self._combat_log_reader = combat_log_reader
        self._parser = NativeCombatEventParser()
        self._selection_boundary_enabled = self._process_id(health_reader) is not None

    @property
    def selection_boundary_enabled(self) -> bool:
        """Whether the source performs the second process-backed target sample."""

        return self._selection_boundary_enabled

    def observe(
        self,
        *,
        now_ms: int,
        target_action_active: bool,
        player_action_active: bool,
    ) -> PvEObservation:
        if isinstance(now_ms, bool) or not isinstance(now_ms, int) or now_ms < 0:
            raise ValueError("now_ms must be a non-negative integer")
        if not isinstance(target_action_active, bool):
            raise ValueError("target_action_active must be boolean")
        if not isinstance(player_action_active, bool):
            raise ValueError("player_action_active must be boolean")

        target = self._health_reader.observe()
        population = (
            None if self._population_reader is None else self._population_reader.observe()
        )
        target_action = (
            None
            if self._target_action_reader is None or not target_action_active
            else self._target_action_reader.observe()
        )
        player_action = (
            None
            if self._player_action_reader is None or not player_action_active
            else self._player_action_reader.observe_player()
        )
        target_identity = self._observe_target_identity(target)
        target_position = (
            None
            if self._target_position_reader is None
            else self._target_position_reader.observe()
        )
        player_position = (
            None
            if self._player_position_reader is None
            else self._player_position_reader.observe()
        )
        player = self._player_vitals_reader.observe()

        if self._selection_boundary_enabled:
            boundary = self._health_reader.observe()
            if not self._same_selection(target, boundary):
                raise PvEObservationCoherenceError(
                    "selected target changed during native PvE frame assembly"
                )
            target = boundary

        if not target.target_present:
            target_position = self._absent_target_position(target_position)
            target_action = self._absent_target_action(target_action)
            target_identity = self._absent_target_identity(target_identity)

        try:
            observation = PvEObservation(
                now_ms=now_ms,
                target=target,
                player=player,
                player_position=player_position,
                target_position=target_position,
                target_action=target_action,
                player_action=player_action,
                target_identity=target_identity,
                population=population,
            )
        except ValueError as exc:
            message = str(exc)
            if "disagree" in message or "resolved different" in message:
                raise PvEObservationCoherenceError(message) from exc
            raise

        events = tuple(
            self._parser.parse(entry)
            for entry in self._combat_log_reader.read_new_entries()
        )
        if not events:
            return observation
        return replace(observation, combat_events=events)

    def _observe_target_identity(
        self,
        target: NativeTargetHealthObservation,
    ) -> NativeTargetIdentityObservation | None:
        if self._target_identity_reader is None:
            return None
        try:
            return self._target_identity_reader.observe()
        except NativeTargetIdentityReadError as exc:
            if not target.target_present:
                return NativeTargetIdentityObservation(target_present=False)
            assert target.target_token is not None
            message = " ".join(str(exc).split())
            return NativeTargetIdentityObservation.unavailable(
                target_token=target.target_token,
                error=f"{type(exc).__name__}:{message[:160]}",
            )

    @staticmethod
    def _same_selection(
        first: NativeTargetHealthObservation,
        second: NativeTargetHealthObservation,
    ) -> bool:
        return (
            first.target_present == second.target_present
            and first.target_token == second.target_token
        )

    @staticmethod
    def _absent_target_position(
        value: NativeTargetPositionObservation | None,
    ) -> NativeTargetPositionObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetPositionObservation(target_present=False)

    @staticmethod
    def _absent_target_action(
        value: NativeTargetActionObservation | None,
    ) -> NativeTargetActionObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetActionObservation(target_present=False)

    @staticmethod
    def _absent_target_identity(
        value: NativeTargetIdentityObservation | None,
    ) -> NativeTargetIdentityObservation | None:
        if value is None or not value.target_present:
            return value
        return NativeTargetIdentityObservation(target_present=False)

    @staticmethod
    def _process_id(reader: object | None) -> int | None:
        if reader is None:
            return None
        value = getattr(reader, "process_id", None)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return None
        return value


class _ObservationFrameBridge:
    """Present one fully validated observation through the legacy reader protocols."""

    def __init__(
        self,
        source: NativePvEObservationSource,
        controller: _BasePvEController,
    ) -> None:
        self._source = source
        self._controller = controller
        self._frame: PvEObservation | None = None

    def begin_frame(self) -> PvEObservation:
        self._frame = self._source.observe(
            now_ms=0,
            target_action_active=self._controller.target_action_observation_active,
            player_action_active=self._controller.player_action_observation_active,
        )
        return self._frame

    def require_frame(self) -> PvEObservation:
        if self._frame is None:
            raise RuntimeError("PvE observation frame was requested before target health")
        return self._frame

    def take_combat_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        frame = self.require_frame()
        self._frame = None
        return tuple(
            NativeCombatLogEntry(
                sequence=event.sequence,
                timestamp=event.timestamp,
                message=event.message,
            )
            for event in frame.combat_events
        )


class _FrameTargetHealthSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        return self._bridge.begin_frame().target


class _FramePlayerVitalsSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        return self._bridge.require_frame().player


class _FramePlayerPositionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().player_position
        if value is None:
            raise RuntimeError("coherent PvE frame is missing player position")
        return value


class _FrameTargetPositionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().target_position
        if value is None:
            raise RuntimeError("coherent PvE frame is missing target position")
        return value


class _FrameTargetActionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().target_action
        if value is None:
            raise RuntimeError("coherent PvE frame is missing target action")
        return value


class _FramePlayerActionSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe_player(self):
        value = self._bridge.require_frame().player_action
        if value is None:
            raise RuntimeError("coherent PvE frame is missing player action")
        return value


class _FrameTargetIdentitySource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().target_identity
        if value is None:
            raise RuntimeError("coherent PvE frame is missing target identity")
        return value


class _FrameCharacterPopulationSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def observe(self):
        value = self._bridge.require_frame().population
        if value is None:
            raise RuntimeError("coherent PvE frame is missing character population")
        return value


class _FrameCombatLogSource:
    def __init__(self, bridge: _ObservationFrameBridge) -> None:
        self._bridge = bridge

    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]:
        return self._bridge.take_combat_entries()


def _failure_reason(prefix: str, exc: Exception) -> str:
    message = " ".join(str(exc).split())
    detail = f":{message[:160]}" if message else ""
    return f"{prefix}:{type(exc).__name__}{detail}"


class _FailClosedController(_BasePvEController):
    """Translate decision/approach exceptions into terminal controller decisions."""

    def __init__(self, delegate: _BasePvEController) -> None:
        self._delegate = delegate

    @property
    def requires_target_action(self) -> bool:
        return self._delegate.requires_target_action

    @property
    def requires_target_identity(self) -> bool:
        return self._delegate.requires_target_identity

    @property
    def requires_population(self) -> bool:
        return self._delegate.requires_population

    @property
    def continuous(self) -> bool:
        return self._delegate.continuous

    @property
    def terminal(self) -> bool:
        return self._delegate.terminal

    @property
    def target_action_observation_active(self) -> bool:
        return self._delegate.target_action_observation_active

    @property
    def player_action_observation_active(self) -> bool:
        return self._delegate.player_action_observation_active

    def step(self, observation: PvEObservation):
        try:
            return self._delegate.step(observation)
        except Exception as exc:
            return self._delegate.stop(
                _failure_reason("decision_failure", exc),
                now_ms=observation.now_ms,
            )

    def stop(self, reason: str, *, now_ms: int | None = None):
        coherence_prefix = "observation_failure:PvEObservationCoherenceError"
        if reason.startswith(coherence_prefix):
            reason = reason.replace(
                "observation_failure:",
                "observation_coherence_failure:",
                1,
            )
        return self._delegate.stop(reason, now_ms=now_ms)

    def recover_from_approach_failure(
        self,
        observation: PvEObservation,
        reason: str,
    ):
        if reason.startswith("runtime_exception:"):
            return self._delegate.stop(
                f"approach_failure:{reason.removeprefix('runtime_exception:')}",
                now_ms=observation.now_ms,
            )
        return self._delegate.recover_from_approach_failure(observation, reason)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class _FailClosedApproach(PvEApproachController):
    """Represent an unexpected approach exception as a non-dispatchable failure."""

    def __init__(self, delegate: PvEApproachController) -> None:
        self._delegate = delegate

    @property
    def config(self):
        return self._delegate.config

    def step(self, observation: PvEObservation, **kwargs) -> PvEApproachUpdate:
        try:
            return self._delegate.step(observation, **kwargs)
        except Exception as exc:
            distance = observation.target_planar_distance or 0.0
            return PvEApproachUpdate(
                PvEApproachStatus.FAILED,
                TravelDecision(
                    decision_id=0,
                    now_ms=observation.now_ms,
                    phase=TravelPhase.STOPPED,
                    waypoint_index=0,
                    distance_remaining=distance,
                    click_count=0,
                    terminal_reason=_failure_reason("runtime_exception", exc),
                ),
            )

    def cancel(self, reason: str) -> PvEApproachUpdate:
        return self._delegate.cancel(reason)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class PvERunner(_BasePvERunner):
    """Use coherent frames and fail-closed stage proxies with one dispatch loop."""

    def __init__(
        self,
        *,
        controller: _BasePvEController,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        player_position_reader: PlayerPositionSource | None = None,
        target_position_reader: TargetPositionSource | None = None,
        target_action_reader: TargetActionSource | None = None,
        player_action_reader: PlayerActionSource | None = None,
        target_identity_reader: TargetIdentitySource | None = None,
        population_reader: CharacterPopulationSource | None = None,
        combat_log_reader: CombatLogSource,
        dispatcher: PvEIntentDispatcher,
        approach_controller: PvEApproachController | None = None,
        movement_dispatcher: TravelDecisionDispatcher | None = None,
        stop_signal: StopSignal,
        poll_interval_ms: int = 100,
        maximum_consecutive_observation_failures: int = 3,
        maximum_retained_trace_steps: int | None = None,
        trace_sink=None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        if not isinstance(controller, _BasePvEController):
            raise ValueError("controller must be PvEController")
        source = NativePvEObservationSource(
            health_reader=health_reader,
            player_vitals_reader=player_vitals_reader,
            player_position_reader=player_position_reader,
            target_position_reader=target_position_reader,
            target_action_reader=target_action_reader,
            player_action_reader=player_action_reader,
            target_identity_reader=target_identity_reader,
            population_reader=population_reader,
            combat_log_reader=combat_log_reader,
        )
        bridge = _ObservationFrameBridge(source, controller)
        guarded_controller = _FailClosedController(controller)
        guarded_approach = (
            None
            if approach_controller is None
            else _FailClosedApproach(approach_controller)
        )
        super().__init__(
            controller=guarded_controller,
            health_reader=_FrameTargetHealthSource(bridge),
            player_vitals_reader=_FramePlayerVitalsSource(bridge),
            player_position_reader=(
                None
                if player_position_reader is None
                else _FramePlayerPositionSource(bridge)
            ),
            target_position_reader=(
                None
                if target_position_reader is None
                else _FrameTargetPositionSource(bridge)
            ),
            target_action_reader=(
                None
                if target_action_reader is None
                else _FrameTargetActionSource(bridge)
            ),
            player_action_reader=(
                None
                if player_action_reader is None
                else _FramePlayerActionSource(bridge)
            ),
            target_identity_reader=(
                None
                if target_identity_reader is None
                else _FrameTargetIdentitySource(bridge)
            ),
            population_reader=(
                None
                if population_reader is None
                else _FrameCharacterPopulationSource(bridge)
            ),
            combat_log_reader=_FrameCombatLogSource(bridge),
            dispatcher=dispatcher,
            approach_controller=guarded_approach,
            movement_dispatcher=movement_dispatcher,
            stop_signal=stop_signal,
            poll_interval_ms=poll_interval_ms,
            maximum_consecutive_observation_failures=(
                maximum_consecutive_observation_failures
            ),
            maximum_retained_trace_steps=maximum_retained_trace_steps,
            trace_sink=trace_sink,
            clock=clock,
            sleeper=sleeper,
        )
        self._native_observation_source = source

    @property
    def observation_source(self) -> NativePvEObservationSource:
        return self._native_observation_source
