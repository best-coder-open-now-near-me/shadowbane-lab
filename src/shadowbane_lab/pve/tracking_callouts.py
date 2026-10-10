"""Complete Hunt Foe appearances for group callouts; no sending or attack authority."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .tracking import TrackingActor, TrackingStatus

_NAME = re.compile(r"[A-Za-z][A-Za-z'-]{0,31}\Z")
_MAX_MESSAGE = 88


@dataclass(frozen=True, slots=True)
class GroupCallout:
    actor: TrackingActor
    group_generation: int
    response_generation: int
    first_names: tuple[str, ...]
    message: str


def _message(names: tuple[str, ...]) -> str:
    """One bounded ASCII message; excess arrivals are counted, never queued."""
    prefix = "Hunt Foe: "
    shown: list[str] = []
    for name in names:
        candidate = shown + [name]
        left = len(names) - len(candidate)
        suffix = f" (+{left} more)" if left else ""
        if len(prefix + ", ".join(candidate) + suffix) > _MAX_MESSAGE:
            break
        shown = candidate
    left = len(names) - len(shown)
    return prefix + ", ".join(shown) + (f" (+{left} more)" if left else "")


def coalesce(pending: GroupCallout | None, decision: GroupCallout | None,
             status: TrackingStatus, *, group_generation: int) -> GroupCallout | None:
    """One fresh pending message; prune departures before merging new arrivals."""
    if not status.current or status.response_age_seconds is None:
        return pending
    if status.response_age_seconds > status.freshness_seconds:
        return None
    present = {c.name.split(" ", 1)[0].casefold() for c in status.contacts}
    names: dict[str, str] = {}
    for value in (pending, decision):
        if (value is None or value.actor != status.actor
                or value.group_generation != group_generation):
            continue
        for name in value.first_names:
            if name.casefold() in present:
                names.setdefault(name.casefold(), name)
    if not names:
        return None
    arrivals = tuple(names[key] for key in sorted(names))
    return GroupCallout(status.actor, group_generation, status.generation,
                        arrivals, _message(arrivals))


class TrackingAppearances:
    """Consume copied complete responses once within a qualified group lifetime.

    ``group_generation`` identifies the observed current group context. The
    integration advances it on known roster/ownership changes; it is not a
    server group nonce. Sending still requires a current native roster check.
    Missing group authority or unavailable tracking preserves previous presence.
    A new actor/group seeds its first complete response without retrospective
    callouts. Reset on explicit disable/ownership release, not a failed scan.

    Returned callouts are consumed decisions, not retry queues. Native sending
    must revalidate the same actor/group and retain its own uncertain entry;
    a later tracking read must never replay an uncertain chat submission.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._scope: tuple[TrackingActor, int] | None = None
        self._generation = 0
        self._present: frozenset[str] = frozenset()

    def observe(
        self, status: TrackingStatus, *, group_generation: int | None
    ) -> GroupCallout | None:
        if not isinstance(status, TrackingStatus):
            raise ValueError("tracking status required")
        if group_generation is None:
            return None
        if type(group_generation) is not int or not 0 < group_generation < 2**64:
            raise ValueError("qualified group generation required")
        if not status.enabled or not status.current or status.actor is None:
            return None
        if (
            status.response_age_seconds is None
            or status.response_age_seconds > status.freshness_seconds
        ):
            return None
        assert status.generation is not None
        scope = (status.actor, group_generation)
        if scope == self._scope and status.generation <= self._generation:
            return None
        names: dict[str, str] = {}
        for contact in status.contacts:
            if contact.object_key == status.actor.object_key:
                continue
            # Hunt Foe can display a surname. The server-unique first name is
            # sufficient and avoids sending arbitrary markup/control content.
            first = contact.name.split(" ", 1)[0]
            # Unsupported names still participate in presence. Withhold only
            # their text; never rename them or stall other valid arrivals.
            key = first.casefold()
            names.setdefault(key, first)
        present = frozenset(names)
        arrivals = tuple(names[key] for key in sorted(present - self._present)
                         if _NAME.fullmatch(names[key]))
        changed_scope = scope != self._scope
        self._scope, self._generation, self._present = scope, status.generation, present
        if changed_scope or not arrivals:
            return None
        return GroupCallout(
            status.actor, group_generation, status.generation, arrivals, _message(arrivals)
        )
