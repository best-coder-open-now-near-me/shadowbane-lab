from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

from client_alignment_fixture import build_pe

from shadowbane_lab.cli import main
from shadowbane_lab.diagnostics import (
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
            "process_private_bytes": float(
                100 + (self.samples - 1) * self.private_growth
            ),
            "process_working_set_bytes": float(80 + self.samples),
        }
        return ProcessSample(identity, tuple(sorted(metrics.items())))


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


class DiagnosticSessionTests(unittest.TestCase):
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
            self.assertEqual("exact-live-executable-bytes", graphics["assessment"][
                "static_import_authority"
            ])
            self.assertEqual("none", graphics["assessment"]["candidate_status"])
            self.assertEqual("unresolved", graphics["assessment"]["active_route_authority"])

    def test_standard_capture_seals_reusable_metrics_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = Path(sys.executable)
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
                record
                for record in stream["records"]
                if record["channel_id"] == "process-metrics"
            ]
            self.assertEqual(3, len(metrics))
            self.assertEqual(123_456, result.summary["process_identity"][
                "process_creation_filetime_utc"
            ])

    def test_triggered_capture_retains_only_configured_binary_pre_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = Path(sys.executable)
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

    def test_requested_missing_channel_is_explicitly_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = Path(sys.executable)
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
            executable = Path(sys.executable)
            result = run_diagnostic_capture(
                DiagnosticRequest(
                    output_directory=root / "capture",
                    process_id=45,
                    duration_seconds=0.2,
                    sample_interval_seconds=0.1,
                    client_executable=executable,
                ),
                process_probe=_FakeProbe(executable, change_identity_at=2),
                clock=_FakeClock(),
            )
            self.assertIs(result.manifest.terminal_state, ManifestTerminalState.FAILED)
            self.assertEqual("process-identity-changed", result.summary["stop_reason"])
            self.assertEqual(
                VerificationStatus.PASS,
                verify_manifest(result.store, result.manifest).status,
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
            self.assertEqual("candidate-evidence-only", interpretation[
                "address_mapping_authority"
            ])
            self.assertFalse(interpretation["automatic_compatibility_promotion"])
            self.assertTrue(
                interpretation["unresolved_mapping_blocks_dependent_decoders"]
            )

    def test_analysis_is_stable_and_reuses_sealed_raw_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = Path(sys.executable)
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
            executable = Path(sys.executable)
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
            self.assertEqual(10.0, private["mean_delta"])
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
