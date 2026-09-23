import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.diagnostics.markers import ObservationMarker, ObservationPhase
from shadowbane_lab.diagnostics.process import ProcessIdentity
from shadowbane_lab.diagnostics.stack_capture import plan_stationary_cpu_stack_capture
from shadowbane_lab.diagnostics.timeline import build_diagnostic_timeline
from shadowbane_lab.evidence import (
    ArtifactKind,
    ArtifactStore,
    EvidenceManifest,
    ManifestTerminalState,
    save_contract,
)
from shadowbane_lab.integrity import canonical_json_bytes, create_only_json


class StationaryStackCapturePlanTests(unittest.TestCase):
    def test_launcher_is_short_identity_bound_and_does_not_claim_pid_only_collection(self) -> None:
        launcher = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "capture-shadowbane-stationary-cpu-stacks.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("[ValidateRange(1, 30)]", launcher)
        self.assertIn("[switch]$ConfirmStationary", launcher)
        self.assertIn("diagnose `\n        stack-plan `", launcher)
        self.assertIn("$process.StartTime.ToUniversalTime().ToFileTimeUtc()", launcher)
        self.assertIn("[StringComparison]::OrdinalIgnoreCase", launcher)
        self.assertIn("WPR is not recording", launcher)
        self.assertIn("& $wprPath -start CPU -filemode", launcher)
        self.assertIn("& $wprPath -stop $etlPath", launcher)
        self.assertIn("& $wprPath -cancel", launcher)
        self.assertIn(
            "system-wide-cpu-sampling-targeted-during-analysis",
            launcher,
        )
        self.assertIn("game_input_injected = $false", launcher)
        self.assertIn("process_memory_written = $false", launcher)
        self.assertNotIn("SendKeys", launcher)

    def test_verifies_sealed_timeline_and_returns_exact_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = _sealed_capture(Path(temporary), stationary_slow_frames=3)

            plan = plan_stationary_cpu_stack_capture(capture)

            self.assertEqual("recommended", plan["status"])
            self.assertEqual(42, plan["process_identity"]["process_id"])
            self.assertEqual(1000, plan["process_identity"]["process_creation_filetime_utc"])
            self.assertEqual(3, plan["stationary_resident_unexplained_slow_frame_count"])
            self.assertEqual(
                "system-wide-cpu-sampling-targeted-during-analysis",
                plan["collection_scope"],
            )

    def test_cli_rejects_stack_capture_when_timeline_does_not_recommend_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = _sealed_capture(Path(temporary), stationary_slow_frames=2)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(("diagnose", "stack-plan", str(capture), "--json"))

            payload = json.loads(stdout.getvalue())
            self.assertEqual(2, exit_code)
            self.assertFalse(payload["ok"])
            self.assertIn("not recommended", payload["error"])

    def test_rejects_convenience_timeline_that_differs_from_sealed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            capture = _sealed_capture(Path(temporary), stationary_slow_frames=3)
            timeline_path = next(capture.glob("*.timeline.json"))
            payload = json.loads(timeline_path.read_text(encoding="utf-8"))
            payload["run_id"] = "diag-tampered"
            timeline_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "differs from its sealed artifact"):
                plan_stationary_cpu_stack_capture(capture)


def _sealed_capture(root: Path, *, stationary_slow_frames: int) -> Path:
    capture = root / "capture"
    capture.mkdir()
    store = ArtifactStore.initialize(capture / "store", store_id="stack-test-store")
    identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
    frames = [_frame(1, 1_100_000_000, None)]
    frames.extend(
        _frame(index + 2, 1_200_000_000 + index * 100_000_000, 50.0)
        for index in range(stationary_slow_frames)
    )
    timeline = build_diagnostic_timeline(
        run_id="diag-stack-test",
        identity=identity,
        started_monotonic_ns=1_000_000_000,
        started_at_utc="2026-09-01T00:00:00.000Z",
        ended_monotonic_ns=2_000_000_000,
        ended_at_utc="2026-09-01T00:00:01.000Z",
        performance_report={"complete": True, "frames": frames},
        player_samples=[],
        camera_report=None,
        observation_markers=[
            _marker("cold", 1_010_000_000, ObservationPhase.COLD_APPROACH),
            _marker("still", 1_050_000_000, ObservationPhase.STATIONARY),
            _marker("warm", 1_900_000_000, ObservationPhase.WARM_RETURN),
        ],
    )
    timeline_path = capture / "diag-stack-test.timeline.json"
    create_only_json(timeline_path, timeline)
    descriptor = store.ingest_bytes(
        canonical_json_bytes(timeline),
        artifact_kind=ArtifactKind.SEMANTIC_TRACE,
        media_type="application/json",
        logical_name="diag-stack-test.diagnostic-timeline.json",
        producer_id="shadowbane-lab.diagnostics",
        producer_version="1",
        captured_at_utc="2026-09-01T00:00:01.000Z",
        metadata=(("channel_id", "diagnostic-timeline"),),
    )
    manifest = EvidenceManifest(
        created_at_utc="2026-09-01T00:00:01.000Z",
        fingerprint_id="fingerprint-stack-test",
        run_id="diag-stack-test",
        artifacts=(descriptor,),
        terminal_state=ManifestTerminalState.COMPLETE,
        required_channels=("diagnostic-timeline",),
        completed_channels=("diagnostic-timeline",),
    )
    save_contract(capture / "manifests" / "diag-stack-test.manifest.json", manifest)
    return capture


def _frame(
    sequence: int,
    frame_monotonic_ns: int,
    frame_time_ms: float | None,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "started_qpc": frame_monotonic_ns // 100_000,
        "frame_monotonic_ns": frame_monotonic_ns,
        "frame_time_ms": frame_time_ms,
        "present_ms": 1.0,
        "cache_reads": {"count": 0, "bytes": 0, "total_time_ms": 0.0},
        "texture_uploads": {"count": 0, "bytes": 0, "total_time_ms": 0.0},
    }


def _marker(
    marker_id: str,
    monotonic_ns: int,
    phase: ObservationPhase,
) -> ObservationMarker:
    return ObservationMarker(
        marker_id=marker_id,
        run_id="diag-stack-test",
        monotonic_ns=monotonic_ns,
        captured_at_utc="2026-09-01T00:00:00.000Z",
        label=marker_id,
        phase=phase,
        finish=False,
    )


if __name__ == "__main__":
    unittest.main()
