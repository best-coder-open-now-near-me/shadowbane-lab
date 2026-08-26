import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import (
    StaticVisibleWindowInspector,
    StaticWindowInspector,
    load_calibration,
)
from shadowbane_lab.pve import PvEIntent
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

    def test_discover_finds_game_by_directory_without_foreground_focus(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            game_directory = Path(temporary_directory) / "Wonderbane"
            game_directory.mkdir()
            terminal = replace(
                _valid_snapshot(),
                executable_name="powershell.exe",
                title="Administrator: Windows PowerShell",
                is_foreground=True,
                executable_path=r"C:\Windows\System32\WindowsPowerShell\powershell.exe",
            )
            game = replace(
                _valid_snapshot(),
                executable_name="sb.exe",
                title="Shadowbane",
                is_foreground=False,
                executable_path=str(game_directory / "sb.exe"),
            )
            inspector = StaticVisibleWindowInspector((terminal, game))
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
                ),
                redirect_stdout(output),
            ):
                result = main(
                    (
                        "client",
                        "discover",
                        "--process-directory",
                        str(game_directory),
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual("sb.exe", payload["executable_name"])
        self.assertFalse(payload["is_foreground"])
        self.assertEqual(str(game_directory / "sb.exe"), payload["executable_path"])

    def test_discover_fails_closed_when_directory_match_is_ambiguous(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory:
            game_directory = Path(temporary_directory) / "Wonderbane"
            game_directory.mkdir()
            first = replace(
                _valid_snapshot(),
                executable_name="sb.exe",
                title="Shadowbane",
                executable_path=str(game_directory / "sb.exe"),
            )
            second = replace(
                _valid_snapshot(),
                executable_name="WonderBanePatcher.exe",
                title="WonderBane Patcher",
                executable_path=str(game_directory / "WonderBanePatcher.exe"),
            )
            inspector = StaticVisibleWindowInspector((first, second))
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
                ),
                redirect_stderr(output),
            ):
                result = main(
                    (
                        "client",
                        "discover",
                        "--process-directory",
                        str(game_directory),
                    )
                )

        self.assertEqual(2, result)
        self.assertIn("multiple visible client windows", output.getvalue())

    def test_bundled_template_validates_and_remains_live_locked(self) -> None:
        output = io.StringIO()
        template = Path(__file__).parents[1] / "configs" / "wonderbane.template.json"

        with redirect_stdout(output):
            result = main(("client", "validate-profile", str(template), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["live_input_enabled"])

    def test_pve_template_has_mob_target_and_basic_attack_mappings(self) -> None:
        output = io.StringIO()
        template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"

        with redirect_stdout(output):
            result = main(("client", "validate-profile", str(template), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(2, payload["action_count"])
        self.assertFalse(payload["live_input_enabled"])

        profile = load_calibration(template)
        mappings = {mapping.action_key: mapping for mapping in profile.actions}
        self.assertEqual(";", mappings["client.pve.target_next_mobile"].activation.key)
        self.assertEqual(
            ("ctrl", "a"),
            mappings["shadowbane.basic_attack"].activation.keys,
        )

    def test_pve_command_requires_explicit_live_flag(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "client",
                    "run-pve",
                    "--client-profile",
                    "pve.json",
                    "--combat-log",
                    "combat.log.txt",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertFalse(payload["ok"])
        self.assertIn("--live", payload["error"])

    def test_proc_assassin_policy_fails_before_input_without_shadow_touch_mapping(self) -> None:
        template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"
        profile_data = json.loads(template.read_text(encoding="utf-8"))
        profile_data["live_input_enabled"] = True
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "pve.local.json"
            combat_log = Path(directory) / "combat.log.txt"
            profile.write_text(json.dumps(profile_data), encoding="utf-8")
            combat_log.write_text("", encoding="utf-8")
            with redirect_stdout(output):
                result = main(
                    (
                        "client",
                        "run-pve",
                        "--client-profile",
                        str(profile),
                        "--combat-log",
                        str(combat_log),
                        "--policy",
                        "proc-assassin",
                        "--live",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertIn(PvEIntent.CAST_SHADOW_TOUCH.value, payload["error"])


if __name__ == "__main__":
    unittest.main()
