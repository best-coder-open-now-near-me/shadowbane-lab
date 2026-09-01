import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.diagnostics.markers import (
    ObservationMarkerInbox,
    ObservationPhase,
    submit_observation_marker,
)
from shadowbane_lab.diagnostics.process import ProcessIdentity


class ObservationMarkerTests(unittest.TestCase):
    def test_cli_submits_marker_to_the_authenticated_active_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            inbox = ObservationMarkerInbox(
                output,
                "diag-test",
                ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe"),
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    (
                        "diagnose",
                        "mark",
                        str(output),
                        "stationary at camp center",
                        "--phase",
                        "stationary",
                        "--json",
                    )
                )

            payload = json.loads(stdout.getvalue())
            retained = inbox.poll()
            self.assertEqual(0, exit_code)
            self.assertTrue(payload["ok"])
            self.assertEqual("stationary", payload["phase"])
            self.assertEqual(payload["marker_id"], retained[0].marker_id)

    def test_submits_multiple_timestamped_markers_without_game_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
            inbox = ObservationMarkerInbox(output, "diag-test", identity)

            first = submit_observation_marker(
                output,
                "cross turtle center cold",
                phase=ObservationPhase.COLD_APPROACH,
                monotonic_ns=100,
                captured_at_utc="2026-09-01T00:00:00.000Z",
            )
            second = submit_observation_marker(
                output,
                "stationary twenty seconds begins",
                phase=ObservationPhase.STATIONARY,
                monotonic_ns=200,
                captured_at_utc="2026-09-01T00:00:01.000Z",
            )

            self.assertEqual((first, second), inbox.poll())
            self.assertEqual((), inbox.poll())
            self.assertTrue(inbox.active_path.exists())
            inbox.close()
            self.assertFalse(inbox.active_path.exists())

    def test_rejects_forged_token_and_wrong_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            identity = ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe")
            inbox = ObservationMarkerInbox(output, "diag-test", identity)
            marker = submit_observation_marker(
                output,
                "warm crossing",
                phase=ObservationPhase.WARM_RETURN,
                monotonic_ns=300,
                captured_at_utc="2026-09-01T00:00:02.000Z",
            )
            path = output / "control" / "marker-inbox" / f"{marker.marker_id}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["token"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "token is invalid"):
                inbox.poll()

    def test_finish_marker_is_explicit_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            inbox = ObservationMarkerInbox(
                output,
                "diag-test",
                ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe"),
            )
            submitted = submit_observation_marker(
                output,
                "warm return complete",
                phase=ObservationPhase.COMPLETE,
                finish=True,
                monotonic_ns=400,
                captured_at_utc="2026-09-01T00:00:03.000Z",
            )

            retained = inbox.poll()

            self.assertEqual(submitted, retained[0])
            self.assertTrue(retained[0].finish)
            self.assertEqual("complete", retained[0].as_dict()["phase"])

    def test_rejects_control_characters_in_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            ObservationMarkerInbox(
                output,
                "diag-test",
                ProcessIdentity(42, 1000, "C:/Wonderbane/sb.exe"),
            )
            with self.assertRaisesRegex(ValueError, "control character"):
                submit_observation_marker(output, "bad\nlabel")


if __name__ == "__main__":
    unittest.main()
