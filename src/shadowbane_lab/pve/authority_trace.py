"""Authority-enriched PvE trace steps over the coherent canonical runner."""

from __future__ import annotations

from dataclasses import dataclass, fields

from shadowbane_lab.pve.authority import PvETargetAuthorityDecision
from shadowbane_lab.pve.guarded_runtime import PvERunner as _GuardedPvERunner
from shadowbane_lab.pve.model import PvERunTraceStep
from shadowbane_lab.pve.target_authority import (
    PvETargetAuthorityControllerDecision,
    PvETargetRejection,
)


@dataclass(frozen=True, slots=True)
class PvEAuthorityRunTraceStep(PvERunTraceStep):
    """One ordinary trace step plus authority evaluated for the same decision."""

    target_authority: PvETargetAuthorityDecision | None = None
    target_rejections: tuple[PvETargetRejection, ...] = ()

    def __post_init__(self) -> None:
        PvERunTraceStep.__post_init__(self)
        if self.target_authority is not None:
            if not isinstance(self.target_authority, PvETargetAuthorityDecision):
                raise ValueError("target_authority must be PvETargetAuthorityDecision")
            if self.target_authority.observed_at_ms != self.decision.now_ms:
                raise ValueError("trace target authority time must match its decision")
        if not isinstance(self.target_rejections, tuple):
            raise ValueError("target_rejections must be a tuple")
        if any(
            not isinstance(value, PvETargetRejection)
            for value in self.target_rejections
        ):
            raise ValueError("target_rejections must contain PvETargetRejection values")
        if any(value.at_ms != self.decision.now_ms for value in self.target_rejections):
            raise ValueError("trace target rejection time must match its decision")

    @classmethod
    def from_trace_step(
        cls,
        step: PvERunTraceStep,
        *,
        target_authority: PvETargetAuthorityDecision | None,
        target_rejections: tuple[PvETargetRejection, ...],
    ) -> PvEAuthorityRunTraceStep:
        if not isinstance(step, PvERunTraceStep):
            raise ValueError("step must be PvERunTraceStep")
        values = {
            field.name: getattr(step, field.name)
            for field in fields(PvERunTraceStep)
        }
        return cls(
            **values,
            target_authority=target_authority,
            target_rejections=target_rejections,
        )

    def as_dict(self) -> dict[str, object]:
        payload = PvERunTraceStep.as_dict(self)
        payload["target_authority"] = (
            None if self.target_authority is None else self.target_authority.as_dict()
        )
        payload["target_rejections"] = [
            value.as_dict() for value in self.target_rejections
        ]
        return payload


class PvERunner(_GuardedPvERunner):
    """Enrich coherent runtime traces without duplicating the dispatch loop."""

    def _trace(self, decision, **kwargs) -> PvERunTraceStep:
        step = super()._trace(decision, **kwargs)
        if not isinstance(decision, PvETargetAuthorityControllerDecision):
            return step
        if decision.target_authority is None and not decision.target_rejections:
            return step
        return PvEAuthorityRunTraceStep.from_trace_step(
            step,
            target_authority=decision.target_authority,
            target_rejections=decision.target_rejections,
        )
