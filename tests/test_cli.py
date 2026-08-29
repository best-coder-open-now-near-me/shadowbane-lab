import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import StaticWindowInspector
from tests.test_client_input_executor import _valid_snapshot


class ClientCliTests(unittest.TestCase):
    def test_inspect_emits_machine_readable_window_identity(self) -> None:
        output = io.StringIO()
        inspector = StaticWindowInspector(_valid_snapshot())
        with (
            patch(
                "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                return_value=inspector,
            ),
            redirect_stdout(output),
        ):
            result = main(("client", "inspect", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertEqual("Shadowbane.exe", payload["executable_name"])
        self.assertEqual(1280, payload["client_bounds"]["width"])

    def test_inspect_fails_closed_when_no_window_is_available(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                return_value=StaticWindowInspector(None),
            ),
            redirect_stderr(output),
        ):
            result = main(("client", "inspect"))

        self.assertEqual(2, result)
        self.assertIn("focus WonderBane", output.getvalue())

    def test_bundled_template_validates_and_remains_live_locked(self) -> None:
        output = io.StringIO()
        template = Path(__file__).parents[1] / "configs" / "wonderbane.template.json"

        with redirect_stdout(output):
            result = main(("client", "validate-profile", str(template), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["live_input_enabled"])

    def test_character_layout_template_validates_and_remains_live_locked(self) -> None:
        output = io.StringIO()
        template = (
            Path(__file__).parents[1] / "configs" / "wonderbane-character-layout.template.json"
        )

        with redirect_stdout(output):
            result = main(("character", "validate-layout", str(template), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertEqual(4, payload["pointer_size"])
        self.assertFalse(payload["live_capture_enabled"])
        self.assertEqual(1, payload["collection_count"])


if __name__ == "__main__":
    unittest.main()
