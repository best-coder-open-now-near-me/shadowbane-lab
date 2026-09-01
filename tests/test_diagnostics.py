from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from client_alignment_fixture import build_pe

from shadowbane_lab.cli import main
from shadowbane_lab.client_extension.performance import (
    PERFORMANCE_AGGREGATE_CAPABILITY,
    CacheArchive,
    PerformanceRecord,
    PerformanceRecordKind,
    PerformanceTelemetryHeader,
    PerformanceTelemetrySnapshot,
)
from shadowbane_lab.client_observation.native_position import (
    NativePlayerPositionObservation,
)
from shadowbane_lab.diagnostics import (
    DiagnosticError,
    DiagnosticProfile,
    DiagnosticRequest,
    FileCaptureMode,
    FileChannel,
    ProcessIdentity,
    ProcessSample,
    TriggerOperator,
    TriggerRule,
    analyze_diagnostic_capture,
    compare_diagnostic_captures,
    run_diagnostic_capture,
)
from shadowbane_lab.diagnostics.collectors import ScreenshotCapture
from shadowbane_lab.evidence import (
    ArtifactKind,
    ManifestTerminalState,
    RedactionState,
    VerificationStatus,
    verify_manifest,
)


class _FakeClock:
    def __init__(self, on_sleep=None) -> None:
        self.value_ns = 1_000_000_000
        self._base = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
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
    def __init__(
        self,
        executable: Path,
        *,
        change_identity_at: int | None = None,
        private_growth: int = 10,
    ) -> None:
        self.executable = executable
        self.samples = 0
        self.change_identity_at = change_identity_at
        self.private_growth = private_growth

    def sample(self, process_id: int) -> ProcessSample:
        self.samples += 1
        creation = 123_456
        if self.change_identity_at is not None and self.samples >= self.change_identity_at:
            creation += 1
        identity = ProcessIdentity(process_id, creation, str(self.executable))
        metrics = {
            "cpu_kernel_seconds": float(self.samples),
            "cpu_user_seconds": float(self.samples * 2),
            "process_handle_count": float(50 + self.samples),
            "process_private_bytes": float(100 + (self.samples - 1) * self.private_growth),
            "process_working_set_bytes": float(80 + self.samples),
        }
        return ProcessSample(identity, tuple(sorted(metrics.items())))


class _FakeNativePositionSource:
    def __init__(
        self,
        executable: Path,
        *,
        process_id: int,
        process_creation_filetime_utc: int = 123_456,
    ) -> None:
        self.process_id = process_id
        self.process_creation_filetime_utc = process_creation_filetime_utc
        self.executable_path = executable
        self.executable_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
        self.profile_id = "fixture-native-position-v1"
        self.samples = 0
        self.closed = False

    def observe(self) -> NativePlayerPositionObservation:
        self.samples += 1
        return NativePlayerPositionObservation(
            lt=100.0 + self.samples,
            lg=200.0 + self.samples,
            altitude=25.0,
        )

    def close(self) -> None:
        self.closed = True


class _FakePerformanceSource:
    def __init__(self, identity: ProcessIdentity) -> None:
        self.identity = identity
        self.calls = 0

    def snapshot(self) -> PerformanceTelemetrySnapshot:
        sequence = self.calls
        self.calls += 1
        header = PerformanceTelemetryHeader(
            process_id=self.identity.process_id,
            capability_flags=PERFORMANCE_AGGREGATE_CAPABILITY,
            process_creation_filetime_utc=(
                self.identity.process_creation_filetime_utc
            ),
            qpc_frequency=10_000,
            started_qpc=1,
            write_sequence=sequence,
            overwritten_record_count=0,
            frame_count=sequence,
            slow_frame_count=sequence,
            cache_read_count=0,
            cache_read_bytes=0,
            texture_upload_count=0,
            texture_upload_bytes=0,
            producer_error=0,
            active_hook_count=20,
        )
        records = (
            (
                PerformanceRecord(
                    sequence=sequence,
                    kind=PerformanceRecordKind.FRAME_SUMMARY,
                    flags=1,
                    started_qpc=10_000 + sequence * 1_000,
                    duration_qpc=10,
                    thread_id=7,
                    archive=CacheArchive.NONE,
                    byte_count=0,
                    argument0=0,
                    argument1=0,
                    argument2=0,
                    frame_interval_qpc=1_000,
                    pipeline_gap_qpc=0,
                    reserved=0,
                ),
            )
            if sequence
            else ()
        )
        return PerformanceTelemetrySnapshot(
            header=header,
            records=records,
        )


class _FakeScreenshotCollector:
    def __init__(self, payloads: tuple[bytes, ...]) -> None:
        self._payloads = iter(payloads)

    def poll(self, monotonic_ns: int) -> tuple[ScreenshotCapture, ...]:
        try:
            payload = next(self._payloads)
        except StopIteration:
            return ()
        return (ScreenshotCapture(monotonic_ns, payload, 1, 1),)


def _artifact_payload(result, channel_id: str) -> bytes:
    descriptors = [
        item
        for item in result.manifest.artifacts
        if dict(item.metadata).get("channel_id") == channel_id
    ]
    if len(descriptors) != 1:
        raise AssertionError(f"expected one {channel_id} artifact, found {len(descriptors)}")
    with result.store.open_artifact(descriptors[0].artifact_id or "") as stream:
        return stream.read()


def _write_client_executable(root: Path) -> Path:
    executable = root / "sb.exe"
    executable.write_bytes(build_pe())
    return executable


class DiagnosticSessionTests(unittest.TestCase):
    def test_aggregate_performance_capture_seals_one_correlated_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            source_instances: list[_FakePerformanceSource] = []

            def source_factory(identity: ProcessIdentity) -> _FakePerformanceSource:
                source = _FakePerformanceSource(identity)
                source_instances.append(source)
                return source

            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=41,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    capture_performance_telemetry=True,
                ),
                process_probe=_FakeProbe(executable),
                performance_source_factory=source_factory,
                clock=_FakeClock(),
            )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertIsNotNone(result.timeline_path)
            self.assertTrue(result.timeline_path.is_file())
            self.assertEqual(1, len(source_instances))
            timeline = json.loads(result.timeline_path.read_bytes())
            sealed_timeline = json.loads(_artifact_payload(result, "diagnostic-timeline"))
            self.assertEqual(timeline, sealed_timeline)
            self.assertGreaterEqual(timeline["summary"]["frame_count"], 2)
            self.assertEqual(41, timeline["process_identity"]["process_id"])
            self.assertFalse(timeline["summary"]["phase_protocol_complete"])
            self.assertIn("diagnostic-timeline", result.manifest.completed_channels)
            self.assertIn("observation-markers", result.manifest.completed_channels)
            self.assertFalse(
                (root / "capture" / "control" / "active-marker-session.json").exists()
            )

    def test_requested_graphics_present_channel_seals_exact_import_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sb.exe"
            executable.write_bytes(build_pe())
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=41,
                    duration_seconds=0.1,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    capture_graphics_present=True,
                ),
                process_probe=_FakeProbe(executable),
                clock=_FakeClock(),
            )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertIn("graphics-present", result.manifest.completed_channels)
            graphics = json.loads(_artifact_payload(result, "graphics-present"))
            self.assertEqual(
                "exact-live-executable-bytes", graphics["assessment"]["static_import_authority"]
            )
            self.assertEqual("none", graphics["assessment"]["candidate_status"])
            self.assertEqual("unresolved", graphics["assessment"]["active_route_authority"])
            self.assertIn(
                "frame-timing omitted: no identity-bound runtime producer was supplied; "
                "graphics-present contains static import evidence only",
                result.summary["warnings"],
            )

    def test_standard_capture_seals_reusable_metrics_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=42,
                    profile=DiagnosticProfile.STANDARD,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    repository_directory=Path(__file__).parents[1],
                ),
                process_probe=_FakeProbe(executable),
                clock=_FakeClock(),
            )
            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertEqual(
                VerificationStatus.PASS,
                verify_manifest(result.store, result.manifest).status,
            )
            self.assertTrue(
                all(
                    item.redaction.state is RedactionState.PENDING
                    for item in result.manifest.artifacts
                )
            )
            stream = json.loads(_artifact_payload(result, "capture-stream"))
            metrics = [
                record for record in stream["records"] if record["channel_id"] == "process-metrics"
            ]
            self.assertEqual(3, len(metrics))
            self.assertEqual(
                110.0,
                metrics[0]["payload"]["process_private_bytes"],
            )
            self.assertEqual(
                123_456, result.summary["process_identity"]["process_creation_filetime_utc"]
            )

    def test_native_position_uses_process_metric_clock_and_exact_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            source: _FakeNativePositionSource | None = None

            def factory(process_id: int) -> _FakeNativePositionSource:
                nonlocal source
                source = _FakeNativePositionSource(executable, process_id=process_id)
                return source

            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=142,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    capture_native_position=True,
                ),
                process_probe=_FakeProbe(executable),
                native_position_factory=factory,
                clock=_FakeClock(),
            )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertIn("native-position", result.manifest.completed_channels)
            self.assertEqual(3, result.summary["native_position_sample_count"])
            self.assertEqual(0, result.summary["native_position_failure_count"])
            self.assertIsNotNone(source)
            self.assertTrue(source.closed)
            stream = json.loads(_artifact_payload(result, "capture-stream"))
            process_rows = [
                item for item in stream["records"] if item["channel_id"] == "process-metrics"
            ]
            position_rows = [
                item for item in stream["records"] if item["channel_id"] == "native-position"
            ]
            self.assertEqual(
                [item["monotonic_ns"] for item in process_rows],
                [item["monotonic_ns"] for item in position_rows],
            )
            self.assertEqual(101.0, position_rows[0]["payload"]["lt"])
            self.assertEqual(201.0, position_rows[0]["payload"]["lg"])
            self.assertEqual(25.0, position_rows[0]["payload"]["altitude"])
            analysis = analyze_diagnostic_capture(result.store, result.manifest)
            position_summary = analysis["spatial"]["native_position"]
            self.assertEqual(3, position_summary["sample_count"])
            self.assertEqual(101.0, position_summary["first"]["lt"])
            self.assertEqual(103.0, position_summary["last"]["lt"])
            self.assertGreater(position_summary["total_sampled_distance"], 0.0)

    def test_native_position_identity_mismatch_is_sealed_as_omission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            source = _FakeNativePositionSource(
                executable,
                process_id=143,
                process_creation_filetime_utc=123_457,
            )
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=143,
                    duration_seconds=0.1,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    capture_native_position=True,
                ),
                process_probe=_FakeProbe(executable),
                native_position_factory=lambda _: source,
                clock=_FakeClock(),
            )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.INCOMPLETE)
            self.assertTrue(source.closed)
            self.assertTrue(
                any(
                    omission.startswith("native-position:")
                    and "creation identity" in omission
                    for omission in result.manifest.omissions
                )
            )

    def test_triggered_capture_retains_only_configured_binary_pre_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            log = root / "client.log"
            log.write_bytes(b"a")
            appended = iter((b"b", b"c", b"d", b"e"))

            def append_log() -> None:
                with log.open("ab") as stream:
                    stream.write(next(appended))

            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=43,
                    profile=DiagnosticProfile.TRIGGERED,
                    duration_seconds=1.0,
                    sample_interval_seconds=0.1,
                    pre_trigger_seconds=0.1,
                    post_trigger_seconds=0.1,
                    client_executable=executable,
                    file_channels=(
                        FileChannel(
                            "client-log",
                            log,
                            FileCaptureMode.TAIL,
                            ArtifactKind.CLIENT_LOG,
                            "text/plain",
                        ),
                    ),
                    trigger_rules=(
                        TriggerRule(
                            "process_private_bytes",
                            TriggerOperator.GE,
                            20,
                            compare_to_baseline=True,
                        ),
                    ),
                ),
                process_probe=_FakeProbe(executable),
                clock=_FakeClock(append_log),
            )
            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertTrue(result.summary["triggered"])
            self.assertEqual(b"bcd", _artifact_payload(result, "client-log"))

    def test_screenshot_buffer_accepts_payload_at_exact_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            collector = _FakeScreenshotCollector((b"1234",))
            with patch(
                "shadowbane_lab.diagnostics.session._MAX_SCREENSHOT_BUFFER_BYTES",
                4,
            ):
                result = run_diagnostic_capture(
                    DiagnosticRequest(
                        output_directory=root / "capture",
                        process_id=143,
                        duration_seconds=0.1,
                        sample_interval_seconds=0.1,
                        client_executable=executable,
                        screenshot_region=(0, 0, 1, 1),
                        screenshot_interval_seconds=0.1,
                    ),
                    process_probe=_FakeProbe(executable),
                    screenshot_factory=lambda _region, _interval: collector,
                    clock=_FakeClock(),
                )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertEqual(4, result.summary["retained_screenshot_bytes"])
            self.assertEqual(4, result.summary["peak_screenshot_bytes"])
            screenshots = [
                item
                for item in result.manifest.artifacts
                if dict(item.metadata).get("channel_id") == "screenshots"
            ]
            self.assertEqual(1, len(screenshots))

    def test_screenshot_buffer_rejects_crossing_cap_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            collector = _FakeScreenshotCollector((b"1234", b"5"))
            with patch(
                "shadowbane_lab.diagnostics.session._MAX_SCREENSHOT_BUFFER_BYTES",
                4,
            ):
                result = run_diagnostic_capture(
                    DiagnosticRequest(
                        output_directory=root / "capture",
                        process_id=144,
                        duration_seconds=0.1,
                        sample_interval_seconds=0.1,
                        client_executable=executable,
                        screenshot_region=(0, 0, 1, 1),
                        screenshot_interval_seconds=0.1,
                    ),
                    process_probe=_FakeProbe(executable),
                    screenshot_factory=lambda _region, _interval: collector,
                    clock=_FakeClock(),
                )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.INCOMPLETE)
            self.assertEqual(4, result.summary["retained_screenshot_bytes"])
            self.assertIn(
                "would exceed 4 bytes",
                result.summary["channel_failures"]["screenshots"],
            )

    def test_screenshot_buffer_rejects_single_payload_larger_than_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            collector = _FakeScreenshotCollector((b"12345",))
            with patch(
                "shadowbane_lab.diagnostics.session._MAX_SCREENSHOT_BUFFER_BYTES",
                4,
            ):
                result = run_diagnostic_capture(
                    DiagnosticRequest(
                        output_directory=root / "capture",
                        process_id=145,
                        duration_seconds=0.1,
                        sample_interval_seconds=0.1,
                        client_executable=executable,
                        screenshot_region=(0, 0, 1, 1),
                        screenshot_interval_seconds=0.1,
                    ),
                    process_probe=_FakeProbe(executable),
                    screenshot_factory=lambda _region, _interval: collector,
                    clock=_FakeClock(),
                )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.INCOMPLETE)
            self.assertEqual(0, result.summary["retained_screenshot_bytes"])
            screenshots = [
                item
                for item in result.manifest.artifacts
                if dict(item.metadata).get("channel_id") == "screenshots"
            ]
            self.assertEqual([], screenshots)

    def test_triggered_capture_prunes_long_pretrigger_history_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            payloads = tuple(bytes((index, 0, 0)) for index in range(20))
            collector = _FakeScreenshotCollector(payloads)
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=146,
                    profile=DiagnosticProfile.TRIGGERED,
                    duration_seconds=2.0,
                    sample_interval_seconds=0.1,
                    pre_trigger_seconds=0.1,
                    post_trigger_seconds=0.1,
                    client_executable=executable,
                    screenshot_region=(0, 0, 1, 1),
                    screenshot_interval_seconds=0.1,
                    trigger_rules=(
                        TriggerRule(
                            "process_private_bytes",
                            TriggerOperator.GE,
                            50,
                            compare_to_baseline=True,
                        ),
                    ),
                ),
                process_probe=_FakeProbe(executable),
                screenshot_factory=lambda _region, _interval: collector,
                clock=_FakeClock(),
            )

            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.COMPLETE)
            self.assertEqual(9, result.summary["retained_screenshot_bytes"])
            self.assertEqual(9, result.summary["peak_screenshot_bytes"])
            screenshots = [
                item
                for item in result.manifest.artifacts
                if dict(item.metadata).get("channel_id") == "screenshots"
            ]
            self.assertEqual(3, len(screenshots))
            stream = json.loads(_artifact_payload(result, "capture-stream"))
            cutoff = result.summary["retained_pre_trigger_cutoff_monotonic_ns"]
            process_rows = [
                item for item in stream["records"] if item["channel_id"] == "process-metrics"
            ]
            self.assertTrue(process_rows)
            self.assertTrue(all(item["monotonic_ns"] >= cutoff for item in process_rows))

    def test_requested_missing_channel_is_explicitly_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=44,
                    duration_seconds=0.1,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                    file_channels=(
                        FileChannel(
                            "network-summary",
                            root / "missing.json",
                            FileCaptureMode.SNAPSHOT,
                            ArtifactKind.PACKET_SUMMARY,
                            "application/json",
                        ),
                    ),
                ),
                process_probe=_FakeProbe(executable),
                clock=_FakeClock(),
            )
            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.INCOMPLETE)
            self.assertTrue(
                any(item.startswith("network-summary:") for item in result.manifest.omissions)
            )

    def test_pid_reuse_fails_closed_but_preserves_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=45,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                ),
                process_probe=_FakeProbe(executable, change_identity_at=3),
                clock=_FakeClock(),
            )
            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.FAILED)
            self.assertEqual("process-identity-changed", result.summary["stop_reason"])
            self.assertEqual(
                VerificationStatus.PASS,
                verify_manifest(result.store, result.manifest).status,
            )

    def test_identity_change_during_fingerprinting_blocks_capture_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            with self.assertRaisesRegex(
                DiagnosticError,
                "between fingerprinting and capture start",
            ):
                run_diagnostic_capture(
                    DiagnosticRequest(
                        output_directory=root / "capture",
                        process_id=46,
                        duration_seconds=0.1,
                        sample_interval_seconds=0.1,
                        client_executable=executable,
                    ),
                    process_probe=_FakeProbe(executable, change_identity_at=2),
                    clock=_FakeClock(),
                )

    def test_build_drift_is_evidence_only_and_never_auto_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.exe"
            candidate = root / "candidate.exe"
            reference.write_bytes(build_pe(text_byte=0x90))
            candidate.write_bytes(build_pe(text_byte=0xCC))
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=46,
                    duration_seconds=0.1,
                    sample_interval_seconds=0.1,
                    client_executable=candidate,
                    reference_executable=reference,
                ),
                process_probe=_FakeProbe(candidate),
                clock=_FakeClock(),
            )
            alignment = json.loads(_artifact_payload(result, "client-alignment"))
            interpretation = alignment["diagnostic_interpretation"]
            self.assertEqual("candidate-evidence-only", interpretation["address_mapping_authority"])
            self.assertFalse(interpretation["automatic_compatibility_promotion"])
            self.assertTrue(interpretation["unresolved_mapping_blocks_dependent_decoders"])

    def test_analysis_is_stable_and_reuses_sealed_raw_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=47,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                ),
                process_probe=_FakeProbe(executable),
                clock=_FakeClock(),
            )
            first = analyze_diagnostic_capture(result.store, result.manifest)
            second = analyze_diagnostic_capture(result.store, result.manifest)
            self.assertEqual(first, second)
            self.assertEqual(
                20.0,
                first["metrics"]["process_private_bytes"]["delta"],
            )
            self.assertEqual(result.manifest.manifest_id, first["source_manifest_id"])

    def test_comparison_uses_raw_samples_from_both_captures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = _write_client_executable(root)
            request = dict(
                process_id=48,
                duration_seconds=0.2,
                sample_interval_seconds=0.1,
                client_executable=executable,
            )
            baseline = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "baseline",
                    **request,
                ),
                process_probe=_FakeProbe(executable, private_growth=10),
                clock=_FakeClock(),
            )
            candidate = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "candidate",
                    **request,
                ),
                process_probe=_FakeProbe(executable, private_growth=20),
                clock=_FakeClock(),
            )
            comparison = compare_diagnostic_captures(
                baseline.store,
                baseline.manifest,
                candidate.store,
                candidate.manifest,
            )
            private = comparison["metrics"]["process_private_bytes"]
            self.assertEqual(20.0, private["mean_delta"])
            self.assertEqual(20.0, private["net_change_delta"])
            self.assertFalse(comparison["review_required"])

            analysis_output = root / "analysis.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "diagnose",
                        "analyze",
                        str(baseline.store.root),
                        str(baseline.manifest_path),
                        "--output",
                        str(analysis_output),
                        "--json",
                    ]
                )
            self.assertEqual(0, exit_code)
            self.assertEqual(
                json.loads(analysis_output.read_text(encoding="utf-8")),
                json.loads(stdout.getvalue()),
            )

            comparison_output = root / "comparison.json"
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "diagnose",
                        "compare",
                        str(baseline.store.root),
                        str(baseline.manifest_path),
                        str(candidate.store.root),
                        str(candidate.manifest_path),
                        "--output",
                        str(comparison_output),
                        "--json",
                    ]
                )
            self.assertEqual(0, exit_code)
            self.assertIn(
                "comparison_id",
                json.loads(comparison_output.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()
