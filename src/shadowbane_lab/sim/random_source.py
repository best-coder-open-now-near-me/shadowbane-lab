"""Explicitly specified deterministic random source for reproducible simulations."""

from __future__ import annotations

from dataclasses import dataclass

_MASK_32 = (1 << 32) - 1
_MASK_64 = (1 << 64) - 1
_MULTIPLIER = 6_364_136_223_846_793_005


@dataclass(frozen=True, slots=True)
class RandomSnapshot:
    state: int
    increment: int

    def __post_init__(self) -> None:
        if not 0 <= self.state <= _MASK_64:
            raise ValueError("state must be an unsigned 64-bit integer")
        if not 0 <= self.increment <= _MASK_64 or self.increment % 2 == 0:
            raise ValueError("increment must be an odd unsigned 64-bit integer")


class DeterministicRandom:
    """PCG-XSH-RR 32 with explicit state and stream selection.

    Using a small specified generator avoids dependence on Python's implementation-specific
    random state and makes snapshots portable across reference and optimized backends.
    """

    def __init__(self, seed: int, stream: int = 54) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(stream, bool) or not isinstance(stream, int):
            raise ValueError("stream must be an integer")
        self._state = 0
        self._increment = ((stream & _MASK_64) << 1 | 1) & _MASK_64
        self.next_uint32()
        self._state = (self._state + (seed & _MASK_64)) & _MASK_64
        self.next_uint32()

    def next_uint32(self) -> int:
        old_state = self._state
        self._state = (old_state * _MULTIPLIER + self._increment) & _MASK_64
        xor_shifted = (((old_state >> 18) ^ old_state) >> 27) & _MASK_32
        rotation = old_state >> 59
        return ((xor_shifted >> rotation) | (xor_shifted << ((-rotation) & 31))) & _MASK_32

    def random(self) -> float:
        """Return a value in the half-open interval [0, 1)."""

        return self.next_uint32() / (1 << 32)

    def uniform(self, minimum: float, maximum: float) -> float:
        if maximum < minimum:
            raise ValueError("maximum must be at least minimum")
        return minimum + (maximum - minimum) * self.random()

    def chance(self, probability: float) -> bool:
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be between zero and one")
        return self.random() < probability

    def randbelow(self, bound: int) -> int:
        """Return an unbiased integer in ``range(bound)``."""

        if isinstance(bound, bool) or not isinstance(bound, int) or bound <= 0:
            raise ValueError("bound must be a positive integer")
        if bound > 1 << 32:
            raise ValueError("bound must fit in an unsigned 32-bit range")
        threshold = (1 << 32) % bound
        while True:
            candidate = self.next_uint32()
            if candidate >= threshold:
                return candidate % bound

    def snapshot(self) -> RandomSnapshot:
        return RandomSnapshot(state=self._state, increment=self._increment)

    def restore(self, snapshot: RandomSnapshot) -> None:
        self._state = snapshot.state
        self._increment = snapshot.increment
