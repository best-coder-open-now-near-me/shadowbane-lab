from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from client_alignment_fixture import build_pe
from shadowbane_lab.diagnostics import (
    DiagnosticProfile,
    DiagnosticRequest,
    FileCaptureMode,
    FileChannel,
    ProcessIdentity,
    ProcessSample,
    TriggerOperator,
    TriggerRule,
    run_diagnostic_capture,
)
from shadowbane_lab.evidence import (
    ArtifactKind,
    ManifestTerminalState,
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
    ) -> None:
        self.executable = executable
        self.samples = 0
        self.change_identity_at = change_identity_at

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
            "process_private_bytes": float(100 + (self.samples - 1) * 10),
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


if __name__ == "__main__":
    unittest.main()
