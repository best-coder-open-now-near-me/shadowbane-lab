"""Bounded cleanup obligations shared by an exact native owner and its clients.

Expiration never confirms cleanup. Normal encounter cleanup releases its obligation;
terminal cancellation additionally prohibits all later input under that same Grant.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

CLEANUP_TIMEOUT_SECONDS = 3.0
CLEANUP_POLL_SECONDS = 0.1


@dataclass(eq=False)
class CleanupObligation:
    grant: Any
    deadline: float | None = None
    released: bool = False


class CleanupSettlement:
    def __init__(self, *, clock=time.monotonic, sleeper=time.sleep):
        self.clock, self.sleeper = clock, sleeper
        self._condition = threading.Condition()
        self._owners = {}
        self._terminal = {}
        self._aborted = set()

    def register(self, grant) -> CleanupObligation:
        with self._condition:
            if grant in self._terminal or grant in self._aborted:
                raise RuntimeError("native owner is terminal; new cleanup ownership denied")
            if grant in self._owners:
                raise RuntimeError("native owner already has a cleanup obligation")
            obligation = CleanupObligation(grant)
            self._owners[grant] = obligation
            return obligation

    def begin(self, obligation: CleanupObligation) -> float:
        with self._condition:
            if obligation.deadline is None:
                obligation.deadline = self.clock() + CLEANUP_TIMEOUT_SECONDS
            terminal = self._terminal.get(obligation.grant)
            if terminal is not None:
                obligation.deadline = min(obligation.deadline, terminal)
            return obligation.deadline

    def release(self, obligation: CleanupObligation) -> None:
        """Called only after the owning client establishes its exact closure proof."""
        with self._condition:
            obligation.released = True
            if self._owners.get(obligation.grant) is obligation:
                del self._owners[obligation.grant]
            self._condition.notify_all()

    def request_terminal(self, grant) -> None:
        with self._condition:
            if grant not in self._terminal:
                self._terminal[grant] = self.clock() + CLEANUP_TIMEOUT_SECONDS
            obligation = self._owners.get(grant)
            if obligation is not None:
                self._terminal[grant] = min(self._terminal[grant], self.begin(obligation))
            self._condition.notify_all()

    def blocked(self, grant) -> bool:
        with self._condition:
            return grant in self._terminal or grant in self._aborted

    def abort(self, grant) -> None:
        """Actual safety/owner failure ends heartbeat permission, never ownership proof."""
        with self._condition:
            self._aborted.add(grant)
            self._condition.notify_all()

    def maintain(self, grant) -> bool:
        with self._condition:
            obligation = self._owners.get(grant)
            return bool(obligation is not None and not obligation.released
                        and grant not in self._aborted and grant in self._terminal
                        and self.clock() < self.begin(obligation))

    def wait_for_terminal(self, grant) -> None:
        with self._condition:
            while self.maintain(grant):
                self._condition.wait(timeout=min(CLEANUP_POLL_SECONDS,
                    self._terminal[grant] - self.clock()))

    def timeout_ms(self, grant, maximum: int) -> int:
        """Clamp an already-bounded cleanup call to this owner's remaining budget."""
        with self._condition:
            owner = self._owners.get(grant)
            deadline = None if owner is None else owner.deadline
            terminal = self._terminal.get(grant)
            if terminal is not None:
                deadline = terminal if deadline is None else min(deadline, terminal)
            if deadline is None:
                return maximum
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise TimeoutError("native cleanup settlement deadline expired")
            return min(maximum, max(1, int(remaining * 1000)))

    def settle(self, obligation, attempt, previous):
        """Poll immutable cleanup only; all callers share the original deadline."""
        deadline = self.begin(obligation)
        result = previous
        while self.clock() < deadline and not obligation.released:
            result = attempt()
            if result[0]:
                return result
            remaining = deadline - self.clock()
            if remaining > 0:
                self.sleeper(min(CLEANUP_POLL_SECONDS, remaining))
        return result
