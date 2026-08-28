import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from shadowbane_lab.cli import _listen_for_go_commands, _run_pve, _run_travel, main
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
from shadowbane_lab.travel import SparseNavigationMap, TravelPhase
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
        self.assertEqual(4, payload["action_count"])
        self.assertFalse(payload["live_input_enabled"])

        profile = load_calibration(template)
        mappings = {mapping.action_key: mapping for mapping in profile.actions}
        self.assertEqual(";", mappings["client.pve.target_next_mobile"].activation.key)
        self.assertEqual(
            "'",
            mappings["client.pve.target_previous_mobile"].activation.key,
        )
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

    def test_pve_recovery_health_cannot_undercut_safety_threshold(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "client",
                    "run-pve",
                    "--client-profile",
                    "pve.json",
                    "--recovery-health-fraction",
                    "0.4",
                    "--live",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertIn("safety threshold", payload["error"])

    def test_continuous_pve_requires_a_durable_evidence_destination(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                (
                    "client",
                    "run-pve",
                    "--client-profile",
                    "pve.json",
                    "--continuous",
                    "--live",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertIn("evidence-output", payload["error"])

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

    def test_chat_pve_command_runs_on_the_guarded_client_and_stays_stoppable(self) -> None:
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
        service_stop = EventEmergencyStop()
        captured: dict[str, object] = {}

        class OneCommandListener:
            def __init__(self, _guard, *, on_command, on_interaction) -> None:
                self.on_command = on_command
                self.on_interaction = on_interaction

            def __enter__(self):
                self.on_command("/pve")
                return self

            def __exit__(self, *_args) -> None:
                return None

        def run_pve(**kwargs) -> int:
            captured.update(kwargs)
            service_stop.trip()
            return 0

        emergency_stop = MagicMock()
        emergency_stop.__enter__.return_value = service_stop
        output = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("shadowbane_lab.cli.load_calibration", return_value=profile),
            patch(
                "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                return_value=StaticWindowInspector(snapshot),
            ),
            patch(
                "shadowbane_lab.cli.WindowsHotkeyEmergencyStop",
                return_value=emergency_stop,
            ),
            patch(
                "shadowbane_lab.cli.WindowsGoChatCommandListener",
                OneCommandListener,
            ),
            patch("shadowbane_lab.cli._verify_hotbar_power_mapping"),
            patch("shadowbane_lab.cli._run_pve", side_effect=run_pve),
            patch(
                "shadowbane_lab.cli.PyAutoGuiBackend",
                return_value=RecordingInputBackend(),
            ),
            redirect_stdout(output),
        ):
            evidence_directory = Path(directory) / "evidence"
            result = _listen_for_go_commands(
                destination_state_path=Path(directory) / "travel.json",
                client_profile_path=template,
                native_position_profile_path=None,
                native_vitals_profile_path=None,
                native_runegate_profile_path=None,
                world_def_path=None,
                named_destination_overrides_path=None,
                pve_client_profile_path=Path(directory) / "pve.json",
                pve_hotbar_config_path=Path(directory) / "hotbar.cfg",
                pve_evidence_directory=evidence_directory,
                pve_navigation_cache_directory=Path(directory) / "cache",
                pve_max_kills=3,
                pve_max_seconds=300,
                pve_max_encounter_seconds=120,
                pve_recovery_timeout_seconds=30,
                pve_poll_ms=100,
                max_seconds=300,
                wait_for_client_seconds=0,
                poll_ms=200,
                click_interval_ms=4_000,
                live=True,
                as_json=True,
                pve_continuous=True,
                pve_camp_radius=140.0,
                pve_retained_trace_steps=1_500,
            )

        self.assertEqual(0, result)
        self.assertEqual(4320, captured["client_process_id"])
        self.assertEqual(3, captured["max_kills"])
        self.assertEqual("proc-assassin", captured["policy"])
        self.assertEqual("state", captured["combat_source"])
        self.assertTrue(captured["continuous"])
        self.assertEqual(140.0, captured["camp_radius"])
        self.assertEqual(1_500, captured["retained_trace_steps"])
        self.assertEqual(Path(directory) / "cache", captured["navigation_cache_directory"])
        self.assertTrue(captured["stop_signal"].is_set())
        evidence_path = captured["evidence_output_path"]
        self.assertIsInstance(evidence_path, Path)
        self.assertEqual(evidence_directory, evidence_path.parent)

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
            for index in range(9)
        )
        readers = tuple(MagicMock() for _ in range(9))
        for reader in readers:
            reader.process_id = 4320
            reader.__enter__.return_value = reader
        zone_observation = SimpleNamespace(name="Sea Dog's Rest", zone_token="zone-1")
        readers[8].observe.return_value = zone_observation
        terrain_origin = NativePlayerPositionObservation(88908, 45112, 28)
        readers[2].observe.return_value = terrain_origin
        navigation_map = SparseNavigationMap()
        terrain_navigation = SimpleNamespace(
            navigation_map=navigation_map,
            seed=SimpleNamespace(
                zone_depth=0,
                template_group_id=0,
                template_id=10400,
                terrain_group_id=13936188,
                terrain_map_id=1,
                raster_width=384,
                raster_height=384,
                window_center_lt=88908,
                window_center_lg=45112,
                window_radius=1200,
                sampled_cells=1600,
                blocked_cells=frozenset({(1, 2)}),
                water_cells=frozenset({(3, 4)}),
                object_density_cells=frozenset({(5, 6), (7, 8)}),
                object_density_layers=(
                    SimpleNamespace(
                        layer_index=1,
                        terrain_group_id=1173,
                        terrain_map_id=214,
                        object_count=4,
                        population_capacity=70,
                        maximum_horizontal_radius=13.4,
                    ),
                ),
                water_sample_threshold=194.56,
                costs=(((2, 3), 1.5),),
            ),
        )
        completed_run = SimpleNamespace(
            final_phase=PvEPhase.COMPLETE,
            terminal_reason="kill_limit_reached",
            kills=1,
            trace=(),
        )
        injected_stop = EventEmergencyStop()
        output = io.StringIO()
        open_health = MagicMock(return_value=readers[0])
        open_vitals = MagicMock(return_value=readers[1])
        open_position = MagicMock(return_value=readers[2])
        open_target_position = MagicMock(return_value=readers[3])
        open_message_hud = MagicMock(return_value=readers[4])
        open_target_action = MagicMock(return_value=readers[5])
        open_target_identity = MagicMock(return_value=readers[6])
        open_population = MagicMock(return_value=readers[7])
        open_zone = MagicMock(return_value=readers[8])
        load_terrain = MagicMock(return_value=terrain_navigation)
        with tempfile.TemporaryDirectory() as directory:
            evidence_output = Path(directory) / "evidence" / "pve.json"
            navigation_cache = Path(directory) / "cache"
            navigation_cache.mkdir()
            with (
                patch("shadowbane_lab.cli.load_calibration", return_value=profile),
                patch(
                    "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                    return_value=StaticWindowInspector(snapshot),
                ),
                patch.multiple(
                    "shadowbane_lab.cli",
                    load_bundled_native_health_profile=MagicMock(
                        return_value=native_profiles[0]
                    ),
                    load_bundled_native_vitals_profile=MagicMock(
                        return_value=native_profiles[1]
                    ),
                    load_bundled_native_position_profile=MagicMock(
                        return_value=native_profiles[2]
                    ),
                    load_bundled_native_target_position_profile=MagicMock(
                        return_value=native_profiles[3]
                    ),
                    load_bundled_native_message_hud_profile=MagicMock(
                        return_value=native_profiles[4]
                    ),
                    load_bundled_native_target_action_profile=MagicMock(
                        return_value=native_profiles[5]
                    ),
                    load_bundled_native_target_identity_profile=MagicMock(
                        return_value=native_profiles[6]
                    ),
                    load_bundled_native_character_population_profile=MagicMock(
                        return_value=native_profiles[7]
                    ),
                    load_bundled_native_zone_profile=MagicMock(
                        return_value=native_profiles[8]
                    ),
                ),
                patch.multiple(
                    "shadowbane_lab.cli",
                    open_windows_native_target_health_reader=open_health,
                    open_windows_native_player_vitals_reader=open_vitals,
                    open_windows_native_player_position_reader=open_position,
                    open_windows_native_target_position_reader=open_target_position,
                    open_windows_native_message_hud_reader=open_message_hud,
                    open_windows_native_target_action_reader=open_target_action,
                    open_windows_native_target_identity_reader=open_target_identity,
                    open_windows_native_character_population_reader=open_population,
                    open_windows_native_current_zone_reader=open_zone,
                    load_active_zone_terrain_navigation=load_terrain,
                ),
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
                    native_target_action_profile_path=None,
                    navigation_cache_directory=navigation_cache,
                    max_kills=1,
                    max_seconds=30,
                    wait_for_client_seconds=0,
                    poll_ms=100,
                    policy="basic",
                    live=True,
                    as_json=True,
                    evidence_output_path=evidence_output,
                    stop_signal=injected_stop,
                    client_process_id=4320,
                )
                saved_evidence = json.loads(evidence_output.read_text(encoding="utf-8"))

        self.assertEqual(0, result)
        self.assertEqual(1, saved_evidence["trace_schema_version"])
        self.assertEqual(4320, saved_evidence["native_observation"]["process_id"])
        self.assertEqual(120.0, saved_evidence["farm_limits"]["maximum_encounter_seconds"])
        self.assertEqual(0.75, saved_evidence["farm_limits"]["recovery_health_fraction"])
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
        open_target_action.assert_called_once_with(
            native_profiles[5],
            process_id=4320,
        )
        open_target_identity.assert_called_once_with(
            native_profiles[6],
            process_id=4320,
        )
        open_population.assert_called_once_with(
            native_profiles[7],
            process_id=4320,
        )
        open_zone.assert_called_once_with(native_profiles[8], process_id=4320)
        load_terrain.assert_called_once_with(
            navigation_cache,
            zone_observation,
            terrain_origin,
        )
        self.assertIs(
            navigation_map,
            pve_runner.call_args.kwargs["approach_controller"]._navigation_map,
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
        self.assertEqual(
            "profile-5",
            saved_evidence["native_observation"]["target_action_profile_id"],
        )
        self.assertEqual(
            "profile-6",
            saved_evidence["native_observation"]["target_identity_profile_id"],
        )
        self.assertEqual(
            "profile-7",
            saved_evidence["native_observation"]["character_population_profile_id"],
        )
        self.assertEqual("seeded", saved_evidence["terrain_navigation"]["status"])
        self.assertEqual(
            10400,
            saved_evidence["terrain_navigation"]["seed"]["template_id"],
        )
        self.assertEqual(
            1600,
            saved_evidence["terrain_navigation"]["seed"]["sampled_cells"],
        )
        self.assertEqual(
            1,
            saved_evidence["terrain_navigation"]["seed"]["water_cells"],
        )
        self.assertEqual(
            2,
            saved_evidence["terrain_navigation"]["seed"]["object_density_cells"],
        )
        self.assertEqual(
            70,
            saved_evidence["terrain_navigation"]["seed"]["object_density_layers"][0][
                "population_capacity"
            ],
        )
        emergency_stop.assert_not_called()

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
