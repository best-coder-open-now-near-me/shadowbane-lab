import unittest

from shadowbane_lab.client_extension.performance_reader import (
    PerformanceTelemetryReader,
    PerformanceTelemetryReadError,
)
from tests.test_client_extension_performance import PerformanceTelemetryContractTests


class SequencedMemory:
    def __init__(self, payloads: list[bytes | Exception]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, int]] = []

    def read(self, name: str, size: int) -> bytes:
        self.calls.append((name, size))
        value = self.payloads.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class PerformanceTelemetryReaderTests(unittest.TestCase):
    def test_retries_a_concurrent_partial_commit(self) -> None:
        incoherent = PerformanceTelemetryContractTests._mapping(write_sequence=1)
        coherent = PerformanceTelemetryContractTests._mapping(write_sequence=1)
        PerformanceTelemetryContractTests._slot(
            coherent,
            1,
            kind=1,
            flags=1,
            interval=50_000,
        )
        memory = SequencedMemory([bytes(incoherent), bytes(coherent)])

        snapshot = PerformanceTelemetryReader(42, 1000, memory).snapshot()

        self.assertEqual(1, len(snapshot.records))
        self.assertEqual(2, len(memory.calls))

    def test_wraps_mapping_open_failure(self) -> None:
        reader = PerformanceTelemetryReader(42, 1000, SequencedMemory([OSError("missing")]))
        with self.assertRaisesRegex(
            PerformanceTelemetryReadError,
            "could not read the exact performance mapping: OSError",
        ):
            reader.snapshot()


if __name__ == "__main__":
    unittest.main()
