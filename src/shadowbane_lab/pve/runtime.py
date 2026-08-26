"""Runtime wiring for native observations and guarded semantic PvE input."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from shadowbane_lab.client_input import ClientInputAdapter, StopSignal
from shadowbane_lab.client_observation import (
    NativeCombatEventParser,
    NativeCombatLogEntry,
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
)
from shadowbane_lab.protocol import ActionBinding, DecisionMessage, DispatchResult
from shadowbane_lab.pve.controller import PvEController
from shadowbane_lab.pve.model import (
    PvEIntent,
    PvEObservation,
    PvERunResult,
    PvERunTraceStep,
)


@runtime_checkable
class PvEIntentDispatcher(Protocol):
    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult: ...


@runtime_checkable
class TargetHealthSource(Protocol):
    def observe(self) -> NativeTargetHealthObservation: ...


@runtime_checkable
class PlayerVitalsSource(Protocol):
    def observe(self) -> NativePlayerVitalsObservation: ...


@runtime_checkable
class CombatLogSource(Protocol):
    def read_new_entries(self) -> tuple[NativeCombatLogEntry, ...]: ...


class ClientPvEIntentDispatcher:
    """Wraps PvE intents in the shared semantic decision contract."""

    def __init__(self, adapter: ClientInputAdapter, *, agent_id: str = "client-self") -> None:
        if not isinstance(adapter, ClientInputAdapter):
            raise ValueError("adapter must be ClientInputAdapter")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self._adapter = adapter
        self._agent_id = agent_id

    def dispatch(self, intent: PvEIntent, *, sequence: int) -> DispatchResult:
        if not isinstance(intent, PvEIntent):
            raise ValueError("intent must be PvEIntent")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        correlation_id = f"pve:{sequence}:{intent.value}"
        return self._adapter.dispatch(
            DecisionMessage(
                message_id=f"message:{correlation_id}",
                correlation_id=correlation_id,
                observation_id=f"observation:pve:{sequence}",
                agent_id=self._agent_id,
                tick=sequence,
                affordance_id=f"affordance:pve:{sequence}:{intent.value}",
                action_key=intent.value,
                binding=ActionBinding(actor_id=self._agent_id),
            )
        )


class PvERunner:
    """Polls exact observations and stops on every read, input, or safety failure."""

    def __init__(
        self,
        *,
        controller: PvEController,
        health_reader: TargetHealthSource,
        player_vitals_reader: PlayerVitalsSource,
        combat_log_reader: CombatLogSource,
        dispatcher: PvEIntentDispatcher,
        stop_signal: StopSignal,
        poll_interval_ms: int = 100,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(controller, PvEController):
            raise ValueError("controller must be PvEController")
        if not isinstance(health_reader, TargetHealthSource):
            raise ValueError("health_reader must implement TargetHealthSource")
        if not isinstance(player_vitals_reader, PlayerVitalsSource):
            raise ValueError("player_vitals_reader must implement PlayerVitalsSource")
        if not isinstance(combat_log_reader, CombatLogSource):
            raise ValueError("combat_log_reader must implement CombatLogSource")
        if not isinstance(dispatcher, PvEIntentDispatcher):
            raise ValueError("dispatcher must implement PvEIntentDispatcher")
        if not isinstance(stop_signal, StopSignal):
            raise ValueError("stop_signal must implement StopSignal")
        if (
            isinstance(poll_interval_ms, bool)
            or not isinstance(poll_interval_ms, int)
            or poll_interval_ms <= 0
        ):
            raise ValueError("poll_interval_ms must be a positive integer")
        self._controller = controller
        self._health_reader = health_reader
        self._player_vitals_reader = player_vitals_reader
        self._combat_log_reader = combat_log_reader
        self._dispatcher = dispatcher
        self._stop_signal = stop_signal
        self._poll_interval_seconds = poll_interval_ms / 1000.0
        self._clock = clock
        self._sleeper = sleeper
        self._parser = NativeCombatEventParser()

    def run(self) -> PvERunResult:
        trace: list[PvERunTraceStep] = []
        started_at = self._clock()
        terminal = None
        while terminal is None:
            now_ms = round((self._clock() - started_at) * 1000)
            if self._stop_signal.is_set():
                terminal = self._controller.stop("emergency_stop", now_ms=now_ms)
                trace.append(self._trace(terminal, target=None, player=None))
                break
            try:
                target = self._health_reader.observe()
                player = self._player_vitals_reader.observe()
                events = tuple(
                    self._parser.parse(entry)
                    for entry in self._combat_log_reader.read_new_entries()
                )
                decision = self._controller.step(
                    PvEObservation(
                        now_ms=now_ms,
                        target=target,
                        player=player,
                        combat_events=events,
                    )
                )
            except Exception as exc:
                terminal = self._controller.stop(
                    f"observation_failure:{type(exc).__name__}",
                    now_ms=now_ms,
                )
                trace.append(self._trace(terminal, target=None, player=None))
                break

            accepted = None
            reason = None
            if decision.intent is not None:
                try:
                    result = self._dispatcher.dispatch(
                        decision.intent,
                        sequence=decision.decision_id,
                    )
                except Exception as exc:
                    reason = f"input_failure:{type(exc).__name__}"
                    trace.append(
                        self._trace(
                            decision,
                            target=target,
                            player=player,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop(reason, now_ms=now_ms)
                    trace.append(self._trace(terminal, target=target, player=player))
                    break
                accepted = result.accepted
                reason = result.reason
                if not result.accepted:
                    trace.append(
                        self._trace(
                            decision,
                            target=target,
                            player=player,
                            input_accepted=False,
                            input_reason=reason,
                        )
                    )
                    terminal = self._controller.stop(
                        "guarded_input_rejected",
                        now_ms=now_ms,
                    )
                    trace.append(self._trace(terminal, target=target, player=player))
                    break
            trace.append(
                self._trace(
                    decision,
                    target=target,
                    player=player,
                    input_accepted=accepted,
                    input_reason=reason,
                )
            )
            if decision.terminal:
                terminal = decision
                break
            self._sleeper(self._poll_interval_seconds)

        assert terminal is not None
        assert terminal.terminal_reason is not None
        return PvERunResult(
            final_phase=terminal.phase,
            terminal_reason=terminal.terminal_reason,
            kills=terminal.kills,
            trace=tuple(trace),
        )

    @staticmethod
    def _trace(
        decision,
        *,
        target,
        player,
        input_accepted: bool | None = None,
        input_reason: str | None = None,
    ) -> PvERunTraceStep:
        return PvERunTraceStep(
            decision=decision,
            target_present=False if target is None else target.target_present,
            current_health=None if target is None else target.current_health,
            maximum_health=None if target is None else target.maximum_health,
            player_current_health=None if player is None else player.current_health,
            player_maximum_health=None if player is None else player.maximum_health,
            input_accepted=input_accepted,
            input_reason=input_reason,
        )
