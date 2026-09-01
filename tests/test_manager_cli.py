import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import (
    StaticVisibleWindowInspector,
    WindowBounds,
    WindowSnapshot,
)
from shadowbane_lab.manager import load_manager_manifest


def _snapshot(
    *,
    process_id: int = 101,
    window_handle: int | None = 1001,
    process_started_at_100ns: int | None = 133_700_000_000_000_000,
    executable_name: str = "sb.exe",
    executable_path: str = r"C:\Games\Shadowbane\sb.exe",
) -> WindowSnapshot:
    return WindowSnapshot(
        executable_name=executable_name,
        executable_path=executable_path,
        title="Shadowbane",
        client_bounds=WindowBounds(left=10, top=20, width=1280, height=720),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
        process_id=process_id,
        window_handle=window_handle,
        process_started_at_100ns=process_started_at_100ns,
    )


def _windows_game_directory(game_directory: Path) -> PureWindowsPath:
    return PureWindowsPath(r"C:\Tests") / game_directory.name


def _ready_manager_path_status(path: Path, *, kind: str) -> dict[str, object]:
    return {
        "path": str(path),
        "expected_kind": kind,
        "exists": True,
        "correct_kind": True,
        "ready": True,
    }


def _manifest_client(
    game_directory: Path,
    *,
    client_id: str = "client-01",
    left: int = 0,
) -> dict[str, object]:
    windows_game_directory = _windows_game_directory(game_directory)
    return {
        "client_id": client_id,
        "launch": {
            "executable": str(windows_game_directory / "launcher.exe"),
            "arguments": ["-windowed"],
            "working_directory": str(windows_game_directory),
        },
        "expected_process_directory": str(windows_game_directory),
        "expected_executable_names": ["sb.exe"],
        "window_tile": {"left": left, "top": 0, "width": 800, "height": 600},
    }


class ManagerCliTests(unittest.TestCase):
    def test_configure_build_is_explicit_atomic_and_preserves_slots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "client-manager.json"
            original = {
                "schema_version": 1,
                "node_id": "gaming-pc-east",
                "clients": [
                    _manifest_client(root / "old", client_id="client-01"),
                ],
            }
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            original_bytes = manifest_path.read_bytes()

            with redirect_stderr(io.StringIO()):
                refused = main(
                    (
                        "manager",
                        "configure-build",
                        str(manifest_path),
                        r"C:\Reviewed\WonderBane-1.0.5",
                    )
                )
            self.assertEqual(2, refused)
            self.assertEqual(original_bytes, manifest_path.read_bytes())

            output = io.StringIO()
            with (
                patch("shadowbane_lab.cli.Path.is_file", return_value=True),
                redirect_stdout(output),
            ):
                configured = main(
                    (
                        "manager",
                        "configure-build",
                        str(manifest_path),
                        r"C:\Reviewed\WonderBane-1.0.5",
                        "--apply",
                        "--json",
                    )
                )

            payload = json.loads(output.getvalue())
            manifest = load_manager_manifest(manifest_path)
            self.assertEqual(0, configured)
            self.assertEqual(1, payload["slot_count"])
            self.assertEqual(
                ("client-01",),
                tuple(client.client_id for client in manifest.clients),
            )
            self.assertTrue(Path(payload["backup"]).is_file())
            self.assertEqual(original_bytes, Path(payload["backup"]).read_bytes())

    def test_configure_build_refuses_a_shared_runtime_for_multiple_slots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "client-manager.json"
            original = {
                "schema_version": 1,
                "node_id": "gaming-pc-east",
                "clients": [
                    _manifest_client(root / "old", client_id="client-01"),
                    _manifest_client(root / "old", client_id="client-02", left=800),
                ],
            }
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            original_bytes = manifest_path.read_bytes()

            with (
                patch("shadowbane_lab.cli.Path.is_file", return_value=True),
                redirect_stderr(io.StringIO()),
            ):
                result = main(
                    (
                        "manager",
                        "configure-build",
                        str(manifest_path),
                        r"C:\Reviewed\WonderBane-1.0.5",
                        "--apply",
                    )
                )

            self.assertEqual(2, result)
            self.assertEqual(original_bytes, manifest_path.read_bytes())

    def test_configure_slots_is_explicit_atomic_and_preserves_a_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game_directory = root / "Wonderbane"
            manifest_path = root / "client-manager.json"
            original = {
                "schema_version": 1,
                "node_id": "gaming-pc-east",
                "clients": [_manifest_client(game_directory)],
            }
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            original_bytes = manifest_path.read_bytes()

            error = io.StringIO()
            with redirect_stderr(error):
                refused = main(
                    (
                        "manager",
                        "configure-slots",
                        str(manifest_path),
                        "--count",
                        "3",
                    )
                )
            self.assertEqual(2, refused)
            self.assertEqual(original_bytes, manifest_path.read_bytes())

            output = io.StringIO()
            with redirect_stdout(output):
                configured = main(
                    (
                        "manager",
                        "configure-slots",
                        str(manifest_path),
                        "--count",
                        "3",
                        "--display-width",
                        "1920",
                        "--display-height",
                        "955",
                        "--apply",
                        "--json",
                    )
                )

            payload = json.loads(output.getvalue())
            manifest = load_manager_manifest(manifest_path)
            backup_path = Path(payload["backup"])

            self.assertEqual(0, configured)
            self.assertEqual(3, payload["slot_count"])
            self.assertTrue(payload["restart_required"])
            self.assertEqual(
                ("client-01", "client-02", "client-03"),
                tuple(client.client_id for client in manifest.clients),
            )
            self.assertTrue(backup_path.is_file())
            self.assertEqual(original_bytes, backup_path.read_bytes())

    def test_configure_slots_refuses_to_clone_an_isolated_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "client-manager.json"
            client = _manifest_client(root / "runtime")
            del client["window_tile"]
            original = {
                "schema_version": 1,
                "node_id": "gaming-pc-east",
                "clients": [client],
            }
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            original_bytes = manifest_path.read_bytes()

            with redirect_stderr(io.StringIO()):
                result = main(
                    (
                        "manager",
                        "configure-slots",
                        str(manifest_path),
                        "--count",
                        "2",
                        "--apply",
                    )
                )

            self.assertEqual(2, result)
            self.assertEqual(original_bytes, manifest_path.read_bytes())

    def test_manager_worker_requires_explicit_live_authority(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error):
            result = main(
                (
                    "manager",
                    "worker",
                    "manager.json",
                    "--worker-state-directory",
                    "workers",
                    "--client-id",
                    "client-01",
                    "--instance-id",
                    "client-012345",
                    "--game-process-id",
                    "101",
                    "--game-process-started-at-100ns",
                    "133700000000000101",
                    "--game-window-handle",
                    "1001",
                )
            )

        self.assertEqual(2, result)
        self.assertIn("pass --live", error.getvalue())

    def test_inspect_emits_attachable_and_rejected_clients_for_node(self) -> None:
        attachable = _snapshot()
        rejected = _snapshot(
            process_id=202,
            window_handle=None,
            process_started_at_100ns=133_700_000_000_000_001,
        )
        unrelated = _snapshot(
            process_id=303,
            window_handle=3003,
            process_started_at_100ns=133_700_000_000_000_002,
            executable_name="powershell.exe",
            executable_path=r"C:\Windows\System32\WindowsPowerShell\powershell.exe",
        )
        inspector = StaticVisibleWindowInspector((unrelated, rejected, attachable))
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                return_value=inspector,
            ),
            redirect_stdout(output),
        ):
            result = main(("manager", "inspect", "--node-id", "gaming-pc-east", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertEqual("gaming-pc-east", payload["node_id"])
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual([101], [item["process_id"] for item in payload["clients"]])
        self.assertEqual(
            ["missing_window_handle"],
            payload["rejected"][0]["reasons"],
        )
        self.assertEqual(1, inspector.inspection_count)

    def test_explicit_names_replace_default_and_directory_narrows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory) / "Wonderbane"
            game_directory.mkdir()
            first = replace(
                _snapshot(),
                executable_name="Shadowbane.exe",
                executable_path=str(game_directory / "Shadowbane.exe"),
            )
            second = replace(
                _snapshot(
                    process_id=202,
                    window_handle=2002,
                    process_started_at_100ns=133_700_000_000_000_001,
                ),
                executable_name="sb-test.exe",
                executable_path=str(game_directory / "sb-test.exe"),
            )
            default = replace(
                _snapshot(
                    process_id=303,
                    window_handle=3003,
                    process_started_at_100ns=133_700_000_000_000_002,
                ),
                executable_path=str(game_directory / "sb.exe"),
            )
            elsewhere = replace(
                first,
                process_id=404,
                window_handle=4004,
                process_started_at_100ns=133_700_000_000_000_003,
                executable_path=r"C:\Other\Shadowbane.exe",
            )
            inspector = StaticVisibleWindowInspector((default, elsewhere, second, first))
            output = io.StringIO()
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
                ),
                redirect_stdout(output),
            ):
                result = main(
                    (
                        "manager",
                        "inspect",
                        "--node-id",
                        "gaming-pc-east",
                        "--process-directory",
                        str(game_directory),
                        "--executable-name",
                        "Shadowbane.exe",
                        "--executable-name",
                        "sb-test.exe",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual([202, 101], [item["process_id"] for item in payload["clients"]])

    def test_empty_registry_is_a_successful_snapshot(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                return_value=StaticVisibleWindowInspector(()),
            ),
            redirect_stdout(output),
        ):
            result = main(("manager", "inspect", "--node-id", "gaming-pc-east", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual([], payload["clients"])
        self.assertEqual([], payload["rejected"])

    def test_preflight_validates_environment_and_reports_attachable_instance(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory) / "Wonderbane"
            game_directory.mkdir()
            (game_directory / "launcher.exe").touch()
            manifest_path = Path(directory) / "manager.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "node_id": "gaming-pc-east",
                        "clients": [_manifest_client(game_directory)],
                    }
                ),
                encoding="utf-8",
            )
            inspector = StaticVisibleWindowInspector(
                (
                    _snapshot(
                        executable_path=str(_windows_game_directory(game_directory) / "sb.exe"),
                    ),
                )
            )
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
                ),
                patch(
                    "shadowbane_lab.cli._manager_path_status",
                    side_effect=_ready_manager_path_status,
                ),
                redirect_stdout(output),
            ):
                result = main(("manager", "preflight", str(manifest_path), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["ready"])
        self.assertEqual("attachable", payload["clients"][0]["binding_status"])
        self.assertTrue(payload["clients"][0]["environment_ready"])
        self.assertEqual(
            [101], [item["process_id"] for item in payload["clients"][0]["matching_instances"]]
        )
        self.assertEqual(1, inspector.inspection_count)

    def test_preflight_groups_identical_filters_and_requires_exact_selection(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory) / "Wonderbane"
            game_directory.mkdir()
            (game_directory / "launcher.exe").touch()
            manifest_path = Path(directory) / "manager.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "node_id": "gaming-pc-east",
                        "clients": [
                            _manifest_client(game_directory, client_id="client-01"),
                            _manifest_client(
                                game_directory,
                                client_id="client-02",
                                left=800,
                            ),
                        ],
                    }
                ),
                encoding="utf-8",
            )
            inspector = StaticVisibleWindowInspector(
                (
                    _snapshot(
                        executable_path=str(_windows_game_directory(game_directory) / "sb.exe")
                    ),
                )
            )
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
                ),
                patch(
                    "shadowbane_lab.cli._manager_path_status",
                    side_effect=_ready_manager_path_status,
                ),
                redirect_stdout(output),
            ):
                result = main(("manager", "preflight", str(manifest_path), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual(
            ["selection_required", "selection_required"],
            [client["binding_status"] for client in payload["clients"]],
        )
        self.assertEqual(1, inspector.inspection_count)

    def test_preflight_manifest_failure_is_structured(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manager.json"
            manifest_path.write_text(
                '{"schema_version":2,"node_id":"node","clients":[]}',
                encoding="utf-8",
            )
            with redirect_stdout(output):
                result = main(("manager", "preflight", str(manifest_path), "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertFalse(payload["ok"])
        self.assertIn("manager preflight failed", payload["error"])

    def test_manager_app_requires_explicit_live_authority(self) -> None:
        error = io.StringIO()

        with redirect_stderr(error):
            result = main(("manager", "app", "missing.json", "--no-browser"))

        self.assertEqual(2, result)
        self.assertIn("pass --live", error.getvalue())

    def test_manager_app_refuses_an_incomplete_local_environment(self) -> None:
        error = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory) / "Wonderbane"
            manifest_path = Path(directory) / "manager.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "node_id": "gaming-pc-east",
                        "clients": [_manifest_client(game_directory)],
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stderr(error):
                result = main(
                    (
                        "manager",
                        "app",
                        str(manifest_path),
                        "--live",
                        "--no-browser",
                    )
                )

        self.assertEqual(2, result)
        self.assertIn("environment is not ready", error.getvalue())

    def test_manager_app_wires_local_session_and_stops_without_closing_clients(self) -> None:
        class FakeNativeWindowApi:
            def set_window_pos(self, *_: object) -> None:
                raise AssertionError("no window action expected")

            def post_message(self, *_: object) -> None:
                raise AssertionError("no window action expected")

        class FakeProcessLifetimeInspector:
            def inspect(self, _process_id: int) -> object:
                raise AssertionError("no process inspection expected")

        created_servers: list[object] = []

        class FakeDashboardServer:
            def __init__(self, service: object, *, port: int) -> None:
                self.service = service
                self.port = port
                self.suggested_url = "http://127.0.0.1:12345/#token=test"
                self.is_running = True
                self.exited = False
                created_servers.append(self)

            def __enter__(self) -> object:
                return self

            def __exit__(self, *_: object) -> None:
                self.exited = True

        output = io.StringIO()
        permit_payload: dict[str, object] | None = None
        with tempfile.TemporaryDirectory() as directory:
            game_directory = Path(directory) / "Wonderbane"
            game_directory.mkdir()
            (game_directory / "launcher.exe").touch()
            manifest_path = Path(directory) / "manager.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "node_id": "gaming-pc-east",
                        "clients": [_manifest_client(game_directory)],
                    }
                ),
                encoding="utf-8",
            )
            worker_state_directory = Path(directory) / "workers"
            manager_pid_path = Path(directory) / "manager.pid"

            def interrupt_after_pid_claim(_seconds: float) -> None:
                self.assertEqual(
                    str(os.getpid()),
                    manager_pid_path.read_text(encoding="ascii").strip(),
                )
                raise KeyboardInterrupt

            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=StaticVisibleWindowInspector(()),
                ),
                patch(
                    "shadowbane_lab.cli._manager_path_status",
                    side_effect=_ready_manager_path_status,
                ),
                patch(
                    "shadowbane_lab.cli.Win32WindowApi",
                    return_value=FakeNativeWindowApi(),
                ),
                patch(
                    "shadowbane_lab.cli.Win32ProcessLifetimeInspector",
                    return_value=FakeProcessLifetimeInspector(),
                ),
                patch(
                    "shadowbane_lab.cli.DashboardServer",
                    FakeDashboardServer,
                ),
                patch(
                    "shadowbane_lab.cli.time.sleep",
                    side_effect=interrupt_after_pid_claim,
                ),
                redirect_stdout(output),
            ):
                result = main(
                    (
                        "manager",
                        "app",
                        str(manifest_path),
                        "--worker-state-directory",
                        str(worker_state_directory),
                        "--pid-file",
                        str(manager_pid_path),
                        "--live",
                        "--no-browser",
                    )
                )
            permit_payload = json.loads(
                (
                    worker_state_directory / "gaming-pc-east" / "client-01" / "dispatch.permit"
                ).read_text(encoding="utf-8")
            )
            self.assertFalse(manager_pid_path.exists())

        self.assertEqual(0, result)
        self.assertEqual(1, len(created_servers))
        server = created_servers[0]
        self.assertTrue(server.exited)
        self.assertEqual("gaming-pc-east", server.service.status()["node_id"])
        self.assertIn("managed clients will remain open", output.getvalue())
        self.assertIsNotNone(permit_payload)
        assert permit_payload is not None
        self.assertFalse(permit_payload["allowed"])
        self.assertIn("shutdown", permit_payload["reason"])

    def test_inspection_failure_is_structured(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                side_effect=RuntimeError("Windows only"),
            ),
            redirect_stdout(output),
        ):
            result = main(("manager", "inspect", "--node-id", "gaming-pc-east", "--json"))

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertFalse(payload["ok"])
        self.assertIn("manager inspection failed", payload["error"])

    def test_missing_process_directory_is_rejected(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with redirect_stdout(output):
                result = main(
                    (
                        "manager",
                        "inspect",
                        "--node-id",
                        "gaming-pc-east",
                        "--process-directory",
                        str(missing),
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(2, result)
        self.assertIn("process directory does not exist", payload["error"])


if __name__ == "__main__":
    unittest.main()
