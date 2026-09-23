import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import _test_world_map_click, main


class ClientActionCliTests(unittest.TestCase):
    def test_routes_world_map_click_arguments_to_the_live_handler(self) -> None:
        with patch("shadowbane_lab.cli._test_world_map_click", return_value=7) as run:
            result = main(
                [
                    "client",
                    "test-world-map-click",
                    "--client-profile",
                    "client.json",
                    "--native-world-map-profile",
                    "map.json",
                    "--map-x-fraction",
                    "0.6",
                    "--map-y-fraction",
                    "0.4",
                    "--wait-for-client-seconds",
                    "10",
                    "--timeout-seconds",
                    "3",
                    "--evidence-output",
                    "action.json",
                    "--live",
                    "--json",
                ]
            )

        self.assertEqual(7, result)
        run.assert_called_once_with(
            client_profile_path=Path("client.json"),
            native_world_map_profile_path=Path("map.json"),
            map_x_fraction=0.6,
            map_y_fraction=0.4,
            wait_for_client_seconds=10.0,
            timeout_seconds=3.0,
            evidence_output_path=Path("action.json"),
            live=True,
            as_json=True,
        )

    def test_live_flag_is_required_before_any_client_setup(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = _test_world_map_click(
                client_profile_path=Path("missing.json"),
                native_world_map_profile_path=None,
                map_x_fraction=0.5,
                map_y_fraction=0.5,
                wait_for_client_seconds=0.0,
                timeout_seconds=2.0,
                evidence_output_path=None,
                live=False,
                as_json=True,
            )

        self.assertEqual(2, result)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertIn("explicit --live", payload["error"])

    def test_invalid_map_fraction_fails_before_loading_the_profile(self) -> None:
        output = io.StringIO()
        with (
            patch("shadowbane_lab.cli.load_calibration") as load,
            redirect_stdout(output),
        ):
            result = _test_world_map_click(
                client_profile_path=Path("missing.json"),
                native_world_map_profile_path=None,
                map_x_fraction=1.1,
                map_y_fraction=0.5,
                wait_for_client_seconds=0.0,
                timeout_seconds=2.0,
                evidence_output_path=None,
                live=True,
                as_json=True,
            )

        self.assertEqual(2, result)
        load.assert_not_called()
        self.assertIn("map fractions", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
