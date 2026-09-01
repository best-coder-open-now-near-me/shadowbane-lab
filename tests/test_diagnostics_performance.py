import unittest

from shadowbane_lab.client_extension.performance import (
    PERFORMANCE_AGGREGATE_CAPABILITY,
    PERFORMANCE_FULL_CAPABILITY,
    CacheArchive,
    PerformanceRecord,
    PerformanceRecordKind,
    PerformanceTelemetryHeader,
    PerformanceTelemetrySnapshot,
)
from shadowbane_lab.diagnostics.performance import PerformanceFrameCollector
from shadowbane_lab.diagnostics.process import ProcessIdentity


class _Source:
    def __init__(self, snapshots: list[PerformanceTelemetrySnapshot]) -> None:
        self._snapshots = snapshots

    def snapshot(self) -> PerformanceTelemetrySnapshot:
        return self._snapshots.pop(0)


class PerformanceFrameCollectorTests(unittest.TestCase):
    def test_drains_only_new_frame_summaries_and_maps_qpc_to_monotonic(self) -> None:
        identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
        source = _Source(
            [
                _snapshot(10),
                _snapshot(12, _frame(11, 11_000), _frame(12, 12_000, interval=1_000)),
            ]
        )
        collector = PerformanceFrameCollector(identity, source)

        collector.poll(1_000_000_000, "2026-09-01T00:00:00.000Z")
        collector.poll(2_000_000_000, "2026-09-01T00:00:01.000Z")
        report = collector.as_report(
            started_monotonic_ns=1_000_000_000,
            started_at_utc="2026-09-01T00:00:00.000Z",
            ended_monotonic_ns=2_000_000_000,
            ended_at_utc="2026-09-01T00:00:01.000Z",
            retained_cutoff_monotonic_ns=1_000_000_000,
        )

        self.assertTrue(report["complete"])
        self.assertEqual([11, 12], [item["sequence"] for item in report["frames"]])
        self.assertEqual(
            [1_100_000_000, 1_200_000_000],
            [item["frame_monotonic_ns"] for item in report["frames"]],
        )
        self.assertEqual(100.0, report["frames"][1]["frame_time_ms"])
        self.assertEqual(4, report["frames"][0]["cache_reads"]["count"])
        self.assertEqual(8192, report["frames"][0]["texture_uploads"]["bytes"])

    def test_discard_before_releases_pretrigger_frames(self) -> None:
        identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
        source = _Source(
            [
                _snapshot(10),
                _snapshot(11, _frame(11, 11_000)),
                _snapshot(12, _frame(12, 12_000)),
            ]
        )
        collector = PerformanceFrameCollector(identity, source)
        collector.poll(1, "2026-09-01T00:00:00.000Z")
        collector.poll(2, "2026-09-01T00:00:01.000Z")
        collector.poll(3, "2026-09-01T00:00:02.000Z")

        collector.discard_before(3)
        report = collector.as_report(
            started_monotonic_ns=1,
            started_at_utc="2026-09-01T00:00:00.000Z",
            ended_monotonic_ns=3,
            ended_at_utc="2026-09-01T00:00:02.000Z",
            retained_cutoff_monotonic_ns=1,
        )

        self.assertEqual([12], [item["sequence"] for item in report["frames"]])

    def test_reports_ring_overwrite_and_capture_drop_as_incomplete(self) -> None:
        identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
        collector = PerformanceFrameCollector(
            identity,
            _Source([_snapshot(1), _snapshot(9000, _frame(9000, 20_000))]),
        )
        collector.poll(1, "2026-09-01T00:00:00.000Z")
        collector.poll(2, "2026-09-01T00:00:01.000Z")
        report = collector.as_report(
            started_monotonic_ns=1,
            started_at_utc="2026-09-01T00:00:00.000Z",
            ended_monotonic_ns=2,
            ended_at_utc="2026-09-01T00:00:01.000Z",
            retained_cutoff_monotonic_ns=1,
        )

        self.assertFalse(report["complete"])
        self.assertEqual("producer-ring-overwrite", report["gaps"][0]["reason"])

    def test_rejects_nonaggregate_profile(self) -> None:
        identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
        collector = PerformanceFrameCollector(
            identity,
            _Source([_snapshot(0, capability=PERFORMANCE_FULL_CAPABILITY)]),
        )
        with self.assertRaisesRegex(ValueError, "not using the aggregate profile"):
            collector.poll(1, "2026-09-01T00:00:00.000Z")


def _header(
    write_sequence: int,
    *,
    capability: int = PERFORMANCE_AGGREGATE_CAPABILITY,
) -> PerformanceTelemetryHeader:
    return PerformanceTelemetryHeader(
        process_id=42,
        capability_flags=capability,
        process_creation_filetime_utc=1000,
        qpc_frequency=10_000,
        started_qpc=1,
        write_sequence=write_sequence,
        overwritten_record_count=max(0, write_sequence - 8192),
        frame_count=write_sequence,
        slow_frame_count=0,
        cache_read_count=0,
        cache_read_bytes=0,
        texture_upload_count=0,
        texture_upload_bytes=0,
        producer_error=0,
        active_hook_count=20,
    )


def _frame(
    sequence: int,
    started_qpc: int,
    *,
    interval: int = 0,
) -> PerformanceRecord:
    return PerformanceRecord(
        sequence=sequence,
        kind=PerformanceRecordKind.FRAME_SUMMARY,
        flags=1,
        started_qpc=started_qpc,
        duration_qpc=10,
        thread_id=7,
        archive=CacheArchive.NONE,
        byte_count=4096,
        argument0=4,
        argument1=20,
        argument2=2,
        frame_interval_qpc=interval,
        pipeline_gap_qpc=30,
        reserved=8192,
    )


def _snapshot(
    write_sequence: int,
    *records: PerformanceRecord,
    capability: int = PERFORMANCE_AGGREGATE_CAPABILITY,
) -> PerformanceTelemetrySnapshot:
    return PerformanceTelemetrySnapshot(
        header=_header(write_sequence, capability=capability),
        records=tuple(records),
    )


if __name__ == "__main__":
    unittest.main()
