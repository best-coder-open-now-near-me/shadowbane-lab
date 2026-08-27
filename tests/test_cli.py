import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shadowbane_lab.cli import _run_pve, _run_travel, main
from shadowbane_lab.client_input import (
    EventEmergencyStop,
    RecordingInputBackend,
    StaticVisibleWindowInspector,
    StaticWindowInspector,
    WindowBounds,
    WindowSnapshot,
    load_calibration,
)
from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.pve import PvEIntent, PvEPhase
from shadowbane_lab.travel import TravelPhase
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

    def test_pve_template_has_verified_target_power_and_attack_mappings(self) -> None:
        output = io.StringIO()
        template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"

        with redirect_stdout(output):
            result = main(("client", "validate-profile", str(template), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(3, payload["action_count"])
        self.assertFalse(payload["live_input_enabled"])

        profile = load_calibration(template)
        mappings = {mapping.action_key: mapping for mapping in profile.actions}
        self.assertEqual(";", mappings["client.pve.target_next_mobile"].activation.key)
        self.assertEqual(
            "f2",
            mappings[PvEIntent.CAST_SHADOW_TOUCH.value].activation.key,
        )
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

    def test_explicit_file_log_source_requires_a_log_path(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "client",
                    "run-pve",
                    "--client-profile",
                    "pve.json",
                    "--combat-source",
                    "log",
                    "--live",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertIn("requires --combat-log", payload["error"])

    def test_chat_travel_command_requires_explicit_live_flag(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "client",
                    "listen-go",
                    "--client-profile",
                    "travel.json",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertFalse(payload["ok"])
        self.assertIn("--live", payload["error"])

    def test_travel_binds_native_readers_to_the_guarded_client_process(self) -> None:
        template = Path(__file__).parents[1] / "configs" / "wonderbane-travel.template.json"
        profile = replace(load_calibration(template), live_input_enabled=True)
        snapshot = WindowSnapshot(
            executable_name=profile.target.executable_names[0],
            title="Shadowbane",
            client_bounds=WindowBounds(
                left=0,
                top=0,
                width=profile.target.reference_width,
                height=profile.target.reference_height,
            ),
            dpi_scale=profile.target.dpi_scale,
            is_foreground=True,
            is_visible=True,
            process_id=4320,
        )
        position_profile = SimpleNamespace(executable_sha256="ab" * 32)
        vitals_profile = SimpleNamespace(executable_sha256="ab" * 32)
        position_reader = MagicMock()
        position_reader.process_id = 4320
        position_reader.__enter__.return_value = position_reader
        vitals_reader = MagicMock()
        vitals_reader.process_id = 4320
        vitals_reader.__enter__.return_value = vitals_reader
        completed_run = SimpleNamespace(
            final_phase=TravelPhase.COMPLETE,
            terminal_reason="arrived",
            final_position=NativePlayerPositionObservation(1000, 2000, 10),
            trace=(),
            clicks=1,
            stop_input_accepted=None,
            stop_input_reason=None,
        )
        output = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("shadowbane_lab.cli.load_calibration", return_value=profile),
            patch(
                "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                return_value=StaticWindowInspector(snapshot),
            ),
            patch(
                "shadowbane_lab.cli.load_bundled_native_position_profile",
                return_value=position_profile,
            ),
            patch(
                "shadowbane_lab.cli.load_bundled_native_vitals_profile",
                return_value=vitals_profile,
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_position_reader",
                return_value=position_reader,
            ) as open_position,
            patch(
                "shadowbane_lab.cli.open_windows_native_player_vitals_reader",
                return_value=vitals_reader,
            ) as open_vitals,
            patch(
                "shadowbane_lab.cli.PyAutoGuiBackend",
                return_value=RecordingInputBackend(),
            ),
            patch("shadowbane_lab.cli.TravelRunner") as travel_runner,
            redirect_stdout(output),
        ):
            travel_runner.return_value.run.return_value = completed_run
            result = _run_travel(
                lt=1000,
                lg=2000,
                radius=75,
                destination_state_path=Path(directory) / "travel.json",
                client_profile_path=template,
                native_position_profile_path=None,
                native_vitals_profile_path=None,
                max_seconds=30,
                wait_for_client_seconds=0,
                poll_ms=200,
                click_interval_ms=4000,
                live=True,
                as_json=True,
                stop_signal=EventEmergencyStop(),
                client_process_id=4320,
            )

        self.assertEqual(0, result)
        open_position.assert_called_once_with(position_profile, process_id=4320)
        open_vitals.assert_called_once_with(vitals_profile, process_id=4320)

    def test_pve_binds_every_native_reader_to_the_guarded_client_process(self) -> None:
        template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"
        profile = replace(load_calibration(template), live_input_enabled=True)
        snapshot = WindowSnapshot(
            executable_name=profile.target.executable_names[0],
            title="Shadowbane",
            client_bounds=WindowBounds(
                left=0,
                top=0,
                width=profile.target.reference_width,
                height=profile.target.reference_height,
            ),
            dpi_scale=profile.target.dpi_scale,
            is_foreground=True,
            is_visible=True,
            process_id=4320,
        )
        native_profiles = tuple(
            SimpleNamespace(executable_sha256="ab" * 32, profile_id=f"profile-{index}")
            for index in range(5)
        )
        readers = tuple(MagicMock() for _ in range(5))
        for reader in readers:
            reader.process_id = 4320
            reader.__enter__.return_value = reader
        completed_run = SimpleNamespace(
            final_phase=PvEPhase.COMPLETE,
            terminal_reason="kill_limit_reached",
            kills=1,
            trace=(),
        )
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            evidence_output = Path(directory) / "evidence" / "pve.json"
            with (
                patch("shadowbane_lab.cli.load_calibration", return_value=profile),
                patch(
                    "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                    return_value=StaticWindowInspector(snapshot),
                ),
                patch(
                    "shadowbane_lab.cli.load_bundled_native_health_profile",
                    return_value=native_profiles[0],
                ),
                patch(
                    "shadowbane_lab.cli.load_bundled_native_vitals_profile",
                    return_value=native_profiles[1],
                ),
                patch(
                    "shadowbane_lab.cli.load_bundled_native_position_profile",
                    return_value=native_profiles[2],
                ),
                patch(
                    "shadowbane_lab.cli.load_bundled_native_target_position_profile",
                    return_value=native_profiles[3],
                ),
                patch(
                    "shadowbane_lab.cli.load_bundled_native_message_hud_profile",
                    return_value=native_profiles[4],
                ),
                patch(
                    "shadowbane_lab.cli.open_windows_native_target_health_reader",
                    return_value=readers[0],
                ) as open_health,
                patch(
                    "shadowbane_lab.cli.open_windows_native_player_vitals_reader",
                    return_value=readers[1],
                ) as open_vitals,
                patch(
                    "shadowbane_lab.cli.open_windows_native_player_position_reader",
                    return_value=readers[2],
                ) as open_position,
                patch(
                    "shadowbane_lab.cli.open_windows_native_target_position_reader",
                    return_value=readers[3],
                ) as open_target_position,
                patch(
                    "shadowbane_lab.cli.open_windows_native_message_hud_reader",
                    return_value=readers[4],
                ) as open_message_hud,
                patch("shadowbane_lab.cli.WindowsHotkeyEmergencyStop") as emergency_stop,
                patch(
                    "shadowbane_lab.cli.PyAutoGuiBackend",
                    return_value=RecordingInputBackend(),
                ),
                patch("shadowbane_lab.cli.PvERunner") as pve_runner,
                redirect_stdout(output),
            ):
                emergency_stop.return_value.__enter__.return_value = EventEmergencyStop()
                pve_runner.return_value.run.return_value = completed_run
                result = _run_pve(
                    client_profile_path=template,
                    combat_log_path=None,
                    hotbar_config_path=None,
                    native_health_profile_path=None,
                    native_vitals_profile_path=None,
                    native_position_profile_path=None,
                    native_target_position_profile_path=None,
                    max_kills=1,
                    max_seconds=30,
                    wait_for_client_seconds=0,
                    poll_ms=100,
                    policy="basic",
                    live=True,
                    as_json=True,
                    evidence_output_path=evidence_output,
                )
                saved_evidence = json.loads(evidence_output.read_text(encoding="utf-8"))

        self.assertEqual(0, result)
        self.assertEqual(1, saved_evidence["trace_schema_version"])
        self.assertEqual(4320, saved_evidence["native_observation"]["process_id"])
        open_health.assert_called_once_with(native_profiles[0], process_id=4320)
        open_vitals.assert_called_once_with(native_profiles[1], process_id=4320)
        open_position.assert_called_once_with(native_profiles[2], process_id=4320)
        open_target_position.assert_called_once_with(
            native_profiles[3],
            process_id=4320,
        )
        open_message_hud.assert_called_once_with(
            native_profiles[4],
            process_id=4320,
            start_at_end=True,
        )
        readers[4].attach.assert_called_once_with()
        self.assertEqual(
            "hud",
            saved_evidence["native_observation"]["combat_source"],
        )
        self.assertEqual(
            "profile-4",
            saved_evidence["native_observation"]["message_hud_profile_id"],
        )

    def test_proc_assassin_policy_fails_before_input_without_shadow_touch_mapping(self) -> None:
        template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"
        profile_data = json.loads(template.read_text(encoding="utf-8"))
        profile_data["live_input_enabled"] = True
        profile_data["actions"] = [
            item
            for item in profile_data["actions"]
            if item["action_key"] != PvEIntent.CAST_SHADOW_TOUCH.value
        ]
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

    def test_proc_assassin_policy_requires_verified_current_hotbar(self) -> None:
        template = Path(__file__).parents[1] / "configs" / "wonderbane-pve.template.json"
        profile_data = json.loads(template.read_text(encoding="utf-8"))
        profile_data["live_input_enabled"] = True
        hotbar_slots = []
        for slot_index in range(12):
            if slot_index == 2:
                hotbar_slots.extend(
                    (
                        f"BEGINHBI {slot_index} PowerHotButtonInfo",
                        'POWERNAME= "ASS-013"',
                        "ENDHBI",
                    )
                )
            else:
                hotbar_slots.extend((f"BEGINHBI {slot_index} EMPTY", "ENDHBI"))
        hotbar_text = (
            "BEGINHOTBAR\nCURRENTSET= 0\nBEGINSET\n"
            + "\n".join(hotbar_slots)
            + "\nENDSET\nENDHOTBAR\n"
        )
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "pve.local.json"
            combat_log = Path(directory) / "combat.log.txt"
            hotbar = Path(directory) / "SCREEN_GAME_character.cfg"
            profile.write_text(json.dumps(profile_data), encoding="utf-8")
            combat_log.write_text("", encoding="utf-8")
            hotbar.write_text(hotbar_text, encoding="utf-8")
            with redirect_stdout(output):
                result = main(
                    (
                        "client",
                        "run-pve",
                        "--client-profile",
                        str(profile),
                        "--combat-log",
                        str(combat_log),
                        "--hotbar-config",
                        str(hotbar),
                        "--policy",
                        "proc-assassin",
                        "--live",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertIn("maps ASS-013", payload["error"])
        self.assertIn("f3", payload["error"])


if __name__ == "__main__":
    unittest.main()
