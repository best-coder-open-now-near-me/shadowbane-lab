"""Byte-accounted rolling retention for diagnostic payloads."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

T = TypeVar("T")


class ByteRetentionBuffer(Generic[T]):
    """Retain accepted items without ever crossing a configured byte ceiling."""

    def __init__(
        self,
        maximum_bytes: int,
        *,
        monotonic_ns: Callable[[T], int],
        size_bytes: Callable[[T], int],
    ) -> None:
        if (
            isinstance(maximum_bytes, bool)
            or not isinstance(maximum_bytes, int)
            or maximum_bytes <= 0
        ):
            raise ValueError("maximum_bytes must be a positive integer")
        if not callable(monotonic_ns) or not callable(size_bytes):
            raise ValueError("retention accessors must be callable")
        self.maximum_bytes = maximum_bytes
        self._monotonic_ns = monotonic_ns
        self._size_bytes = size_bytes
        self._items: deque[tuple[T, int]] = deque()
        self._retained_bytes = 0
        self._peak_retained_bytes = 0

    @property
    def retained_bytes(self) -> int:
        return self._retained_bytes

    @property
    def peak_retained_bytes(self) -> int:
        return self._peak_retained_bytes

    def append(self, item: T) -> bool:
        """Accept one item only when its prospective total remains within budget."""

        size = self._size_bytes(item)
        timestamp = self._monotonic_ns(item)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("retained item size must be a non-negative integer")
        if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
            raise ValueError("retained item timestamp must be a non-negative integer")
        if size > self.maximum_bytes - self._retained_bytes:
            return False
        self._items.append((item, size))
        self._retained_bytes += size
        self._peak_retained_bytes = max(
            self._peak_retained_bytes,
            self._retained_bytes,
        )
        return True

    def discard_before(self, cutoff_monotonic_ns: int) -> tuple[T, ...]:
        if (
            isinstance(cutoff_monotonic_ns, bool)
            or not isinstance(cutoff_monotonic_ns, int)
            or cutoff_monotonic_ns < 0
        ):
            raise ValueError("retention cutoff must be a non-negative integer")
        discarded = []
        while self._items and self._monotonic_ns(self._items[0][0]) < cutoff_monotonic_ns:
            item, size = self._items.popleft()
            self._retained_bytes -= size
            discarded.append(item)
        return tuple(discarded)

    def __iter__(self) -> Iterator[T]:
        return (item for item, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)


__all__ = ["ByteRetentionBuffer"]
