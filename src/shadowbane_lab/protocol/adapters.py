"""Adapter contracts and side-effect-free test implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from shadowbane_lab.protocol.model import DecisionMessage


@dataclass(frozen=True, slots=True)
class DispatchResult:
    adapter_name: str
    correlation_id: str
    accepted: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ValueError("accepted must be a boolean")
        if not self.adapter_name.strip():
            raise ValueError("adapter_name must be a non-empty string")
        if not self.correlation_id.strip():
            raise ValueError("correlation_id must be a non-empty string")
        if not self.accepted and not self.reason:
            raise ValueError("rejected dispatches require a reason")


@runtime_checkable
class DecisionAdapter(Protocol):
    """Consumes semantic decisions without exposing transport details to policies."""

    @property
    def name(self) -> str: ...

    def dispatch(self, decision: DecisionMessage) -> DispatchResult: ...


class RecordingDecisionAdapter:
    """Records decisions without producing simulator, network, or desktop side effects."""

    def __init__(self, name: str = "recording") -> None:
        if not name.strip():
            raise ValueError("name must be a non-empty string")
        self._name = name
        self._decisions: list[DecisionMessage] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def decisions(self) -> tuple[DecisionMessage, ...]:
        return tuple(self._decisions)

    def dispatch(self, decision: DecisionMessage) -> DispatchResult:
        self._decisions.append(decision)
        return DispatchResult(
            adapter_name=self.name,
            correlation_id=decision.correlation_id,
            accepted=True,
        )
