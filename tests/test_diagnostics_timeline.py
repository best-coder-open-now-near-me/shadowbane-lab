import unittest

from shadowbane_lab.diagnostics.markers import ObservationMarker, ObservationPhase
from shadowbane_lab.diagnostics.process import ProcessIdentity
from shadowbane_lab.diagnostics.timeline import build_diagnostic_timeline


class DiagnosticTimelineTests(unittest.TestCase):
    def test_correlates_phases_samples_and_followup_recommendations(self) -> None:
        report = build_diagnostic_timeline(
            run_id="diag-test",
            identity=ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe"),
            started_monotonic_ns=1_000_000_000,
            started_at_utc="2026-09-01T00:00:00.000Z",
            ended_monotonic_ns=2_000_000_000,
            ended_at_utc="2026-09-01T00:00:01.000Z",
            performance_report={
                "complete": True,
                "frames": [
                    _frame(1, 1_100_000_000, None),
                    _frame(2, 1_200_000_000, 50.0),
                    _frame(3, 1_300_000_000, 51.0),
                    _frame(4, 1_400_000_000, 52.0),
                    _frame(5, 1_600_000_000, 60.0, texture_count=2),
                ],
            },
            player_samples=[
                {
                    "monotonic_ns": 1_180_000_000,
                    "captured_at_utc": "2026-09-01T00:00:00.180Z",
                    "sample_index": 1,
                    "lt": 10.0,
                    "lg": 20.0,
                    "altitude": 30.0,
                }
            ],
            camera_report={
                "clock": {"counter_frequency_hz": 10_000},
                "samples": [
                    {
                        "sequence": 7,
                        "counter": 12_100,
                        "position": [1.0, 2.0, 3.0],
                    }
                ],
            },
            observation_markers=[
                _marker("cold", 1_050_000_000, ObservationPhase.COLD_APPROACH),
                _marker("still", 1_150_000_000, ObservationPhase.STATIONARY),
                _marker("warm", 1_500_000_000, ObservationPhase.WARM_RETURN),
            ],
        )

        self.assertTrue(report["complete"])
        self.assertTrue(report["summary"]["phase_protocol_complete"])
        self.assertTrue(report["summary"]["cpu_stack_capture_recommended"])
        self.assertTrue(report["summary"]["texture_identity_followup_recommended"])
        self.assertEqual("resident-unexplained", report["frames"][1]["classification"])
        self.assertEqual("stationary", report["frames"][1]["phase"])
        self.assertEqual(1, report["frames"][1]["correlation"]["player"]["sample_index"])
        self.assertEqual(7, report["frames"][1]["correlation"]["camera"]["sequence"])
        self.assertEqual("2026-09-01T00:00:00.200Z", report["frames"][1]["frame_at_utc"])

    def test_missing_manual_phases_are_reported_without_inventing_them(self) -> None:
        report = build_diagnostic_timeline(
            run_id="diag-test",
            identity=ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe"),
            started_monotonic_ns=1_000_000_000,
            started_at_utc="2026-09-01T00:00:00.000Z",
            ended_monotonic_ns=2_000_000_000,
            ended_at_utc="2026-09-01T00:00:01.000Z",
            performance_report={"complete": True, "frames": [_frame(1, 1_100_000_000, None)]},
            player_samples=[],
            camera_report=None,
            observation_markers=[],
        )

        self.assertTrue(report["complete"])
        self.assertFalse(report["summary"]["phase_protocol_complete"])
        self.assertEqual(
            ["cold-approach", "stationary", "warm-return"],
            report["summary"]["missing_protocol_phases"],
        )
        self.assertEqual("unmarked", report["frames"][0]["phase"])


def _frame(
    sequence: int,
    monotonic_ns: int,
    frame_time_ms: float | None,
    *,
    texture_count: int = 0,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "started_qpc": monotonic_ns // 100_000,
        "frame_monotonic_ns": monotonic_ns,
        "frame_time_ms": frame_time_ms,
        "present_ms": 1.0,
        "cache_reads": {"count": 0, "bytes": 0, "total_time_ms": 0.0},
        "texture_uploads": {
            "count": texture_count,
            "bytes": texture_count * 4096,
            "total_time_ms": float(texture_count),
        },
    }


def _marker(
    marker_id: str,
    monotonic_ns: int,
    phase: ObservationPhase,
) -> ObservationMarker:
    return ObservationMarker(
        marker_id=marker_id,
        run_id="diag-test",
        monotonic_ns=monotonic_ns,
        captured_at_utc="2026-09-01T00:00:00.000Z",
        label=marker_id,
        phase=phase,
        finish=False,
    )


if __name__ == "__main__":
    unittest.main()
