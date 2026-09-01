from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from client_alignment_fixture import build_pe

from shadowbane_lab.diagnostics import (
    DiagnosticRequest,
    ProcessIdentity,
    ProcessSample,
    analyze_diagnostic_capture,
    collect_graphics_present_evidence,
    compare_diagnostic_captures,
    run_diagnostic_capture,
)
from shadowbane_lab.diagnostics.frame_timing import FrameTimingCollector
from shadowbane_lab.evidence import ManifestTerminalState


def _present_pe() -> bytes:
    result = bytearray(build_pe())
    optional_offset = 0x80 + 24
    struct.pack_into("<I", result, optional_offset + 92, 16)
    struct.pack_into("<II", result, optional_offset + 96 + 8, 0x2000, 0x80)
    data_offset = 0x400
    struct.pack_into("<IIIII", result, data_offset, 0x2040, 0, 0, 0x2030, 0x2050)
    result[data_offset + 0x30 : data_offset + 0x30 + 10] = b"GDI32.dll\0"
    struct.pack_into("<I", result, data_offset + 0x40, 0x2080)
    struct.pack_into("<I", result, data_offset + 0x44, 0)
    struct.pack_into("<I", result, data_offset + 0x50, 0x2080)
    struct.pack_into("<I", result, data_offset + 0x54, 0)
    struct.pack_into("<H", result, data_offset + 0x80, 0)
    result[data_offset + 0x82 : data_offset + 0x82 + 12] = b"SwapBuffers\0"
    return bytes(result)


def _status(
    executable: Path,
    identity: ProcessIdentity,
    *,
    latest_sequence: int = 12,
    sample_capacity: int = 1024,
) -> dict[str, object]:
    entry = {
        "library": "GDI32.dll",
        "symbol": "SwapBuffers",
        "iat_rva": 0x2050,
    }
    return {
        "schema_version": 2,
        "producer_id": "wonderbane-extension.graphics",
        "extension_version": "1.5.5",
        "process_identity": identity.as_dict(),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "present_entries": [{**entry, "call_count": latest_sequence}],
        "active_present_entry": entry,
        "graphics_context": {
            "context_observed": True,
            "gl_version": "1.4 fixture",
            "glsl_version": "1.20 fixture",
            "depth_bits": 24,
            "depth_texture_supported": True,
            "framebuffer_object_supported": False,
            "viewport": [0, 0, 800, 600],
        },
        "frame_timing": {
            "clock": "windows-query-performance-counter",
            "counter_frequency_hz": 1_000_000,
            "snapshot_counter": 10_000_000 + latest_sequence * 16_667,
            "snapshot_filetime_utc": (134_326_944_408_808_988 + latest_sequence * 166_670),
            "latest_present_sequence": latest_sequence,
            "oldest_available_sequence": (
                max(1, latest_sequence - sample_capacity + 1) if latest_sequence else 0
            ),
            "sample_capacity": sample_capacity,
            "sample_count": min(latest_sequence, sample_capacity),
            "timing_query_failure_count": 0,
            "samples": [
                [sequence, 10_000_000 + sequence * 16_667]
                for sequence in range(
                    max(1, latest_sequence - sample_capacity + 1),
                    latest_sequence + 1,
                )
            ],
        },
        "depth_edge_pass": {"state": "disabled", "reason": "diagnostic fixture"},
    }


class _FakeClock:
    def __init__(self, on_sleep=None) -> None:
        self.value_ns = 1_000_000_000
        self._base = datetime(2026, 9, 1, 3, 30, tzinfo=UTC)
        self._on_sleep = on_sleep

    def monotonic_ns(self) -> int:
        return self.value_ns

    def utc_timestamp(self) -> str:
        elapsed = (self.value_ns - 1_000_000_000) / 1_000_000_000
        value = self._base + timedelta(seconds=elapsed)
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def sleep(self, seconds: float) -> None:
        self.value_ns += int(seconds * 1_000_000_000)
        if self._on_sleep is not None:
            self._on_sleep()


class _FakeProbe:
    def __init__(self, identity: ProcessIdentity) -> None:
        self.identity = identity
        self.samples = 0

    def sample(self, process_id: int) -> ProcessSample:
        self.samples += 1
        return ProcessSample(
            self.identity,
            (
                ("cpu_user_seconds", float(self.samples)),
                ("process_private_bytes", float(100 + self.samples)),
            ),
        )


def _artifact_payload(result, channel_id: str) -> bytes:
    descriptors = [
        item
        for item in result.manifest.artifacts
        if dict(item.metadata).get("channel_id") == channel_id
    ]
    if len(descriptors) != 1:
        raise AssertionError(f"expected one {channel_id} artifact")
    with result.store.open_artifact(descriptors[0].artifact_id or "") as stream:
        return stream.read()


class GraphicsPresentEvidenceTests(unittest.TestCase):
    def test_capture_launcher_auto_discovers_identity_bound_runtime_status(self) -> None:
        launcher = (
            Path(__file__).resolve().parents[1] / "scripts" / "capture-shadowbane-diagnostics.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "$clientProcess.StartTime.ToUniversalTime().ToFileTimeUtc()",
            launcher,
        )
        self.assertIn(
            '"graphics-status-$($clientProcess.Id)-$processCreationFiletimeUtc.json"',
            launcher,
        )
        self.assertIn(
            "Test-Path -LiteralPath $expectedGraphicsRuntimeStatus -PathType Leaf",
            launcher,
        )

    def test_static_import_is_exact_but_active_route_remains_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(42, 123456, str(executable))

            result = collect_graphics_present_evidence(executable, identity)

            self.assertTrue(result.complete)
            self.assertEqual(1, result.report["assessment"]["candidate_count"])
            self.assertEqual(
                "unresolved",
                result.report["assessment"]["active_route_authority"],
            )
            self.assertTrue(
                result.report["assessment"]["unresolved_mapping_blocks_dependent_renderer_work"]
            )

    def test_identity_bound_runtime_status_proves_present_and_depth_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(43, 123456, str(executable))
            status = root / "graphics-status.json"
            status.write_text(json.dumps(_status(executable, identity)), encoding="utf-8")

            result = collect_graphics_present_evidence(
                executable,
                identity,
                runtime_status_path=status,
            )

            self.assertTrue(result.complete)
            self.assertEqual("accepted", result.report["runtime_status"]["state"])
            self.assertEqual(
                "runtime-observed-exact-process",
                result.report["assessment"]["active_route_authority"],
            )
            self.assertTrue(result.report["assessment"]["depth_edge_prerequisites_observed"])

    def test_continuous_collector_reports_ring_overwrite_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(46, 123456, str(executable))
            status = root / "graphics-status.json"
            status.write_text(
                json.dumps(_status(executable, identity, latest_sequence=10)),
                encoding="utf-8",
            )
            collector = FrameTimingCollector(
                status,
                identity,
                hashlib.sha256(executable.read_bytes()).hexdigest(),
                (
                    {
                        "candidate_id": "gdi32-swap-buffers",
                        "library": "GDI32.dll",
                        "symbol": "SwapBuffers",
                        "iat_rva": 0x2050,
                        "ordinal": None,
                    },
                ),
            )
            collector.poll(1_000_000_000, "2026-09-01T03:30:00.000Z")
            status.write_text(
                json.dumps(
                    _status(
                        executable,
                        identity,
                        latest_sequence=1100,
                        sample_capacity=1024,
                    )
                ),
                encoding="utf-8",
            )
            collector.poll(2_000_000_000, "2026-09-01T03:30:01.000Z")
            report = collector.as_report(
                started_monotonic_ns=1_000_000_000,
                started_at_utc="2026-09-01T03:30:00.000Z",
                ended_monotonic_ns=2_000_000_000,
                ended_at_utc="2026-09-01T03:30:01.000Z",
                retained_cutoff_monotonic_ns=1_000_000_000,
            )

            self.assertFalse(report["complete"])
            self.assertEqual(1024, report["sample_count"])
            self.assertEqual("producer-ring-overwrite", report["gaps"][0]["reason"])
            self.assertEqual(66, report["gaps"][0]["missing_count"])

    def test_capture_continuously_drains_and_analyzes_exact_present_timing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(45, 123456, str(executable))
            status = root / "graphics-status.json"
            latest = 10

            def publish() -> None:
                nonlocal latest
                latest += 2
                status.write_text(
                    json.dumps(
                        _status(
                            executable,
                            identity,
                            latest_sequence=latest,
                        )
                    ),
                    encoding="utf-8",
                )

            status.write_text(
                json.dumps(
                    _status(
                        executable,
                        identity,
                        latest_sequence=latest,
                    )
                ),
                encoding="utf-8",
            )
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=identity.process_id,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    capture_graphics_present=True,
                    graphics_runtime_status=status,
                ),
                process_probe=_FakeProbe(identity),
                clock=_FakeClock(publish),
            )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            timing = json.loads(_artifact_payload(result, "frame-timing"))
            self.assertTrue(timing["complete"])
            self.assertEqual([11, 12, 13, 14], [item[0] for item in timing["samples"]])
            analysis = analyze_diagnostic_capture(result.store, result.manifest)
            self.assertEqual(4, analysis["frame_timing"]["sample_count"])
            self.assertAlmostEqual(16.667, analysis["frame_timing"]["frame_time_ms"]["median"])
            self.assertEqual(
                0,
                analysis["frame_timing"]["hitches"]["at_least_33_3_ms"]["count"],
            )
            comparison = compare_diagnostic_captures(
                result.store,
                result.manifest,
                result.store,
                result.manifest,
            )
            self.assertEqual("comparable", comparison["frame_timing"]["state"])
            self.assertEqual(
                1.0,
                comparison["frame_timing"]["metrics"]["average_fps"]["ratio"],
            )

    def test_runtime_status_with_wrong_creation_identity_is_retained_as_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(_present_pe())
            identity = ProcessIdentity(44, 123456, str(executable))
            wrong_identity = ProcessIdentity(44, 123457, str(executable))
            status = root / "graphics-status.json"
            status.write_text(json.dumps(_status(executable, wrong_identity)), encoding="utf-8")

            result = collect_graphics_present_evidence(
                executable,
                identity,
                runtime_status_path=status,
            )

            self.assertFalse(result.complete)
            self.assertIn("creation identity", result.failure or "")
            self.assertEqual("rejected", result.report["runtime_status"]["state"])


if __name__ == "__main__":
    unittest.main()
