import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import (
    StaticVisibleWindowInspector,
    WindowBounds,
    WindowSnapshot,
)


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


def _manifest_client(
    game_directory: Path,
    *,
    client_id: str = "client-01",
    left: int = 0,
) -> dict[str, object]:
    return {
        "client_id": client_id,
        "launch": {
            "executable": str(game_directory / "launcher.exe"),
            "arguments": ["-windowed"],
            "working_directory": str(game_directory),
        },
        "expected_process_directory": str(game_directory),
        "expected_executable_names": ["sb.exe"],
        "window_tile": {"left": left, "top": 0, "width": 800, "height": 600},
    }


class ManagerCliTests(unittest.TestCase):
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
            result = main(
                ("manager", "inspect", "--node-id", "gaming-pc-east", "--json")
            )

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
            result = main(
                ("manager", "inspect", "--node-id", "gaming-pc-east", "--json")
            )

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
                        executable_path=str(game_directory / "sb.exe"),
                    ),
                )
            )
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
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
        self.assertEqual([101], [
            item["process_id"]
            for item in payload["clients"][0]["matching_instances"]
        ])
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
                (_snapshot(executable_path=str(game_directory / "sb.exe")),)
            )
            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
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

    def test_inspection_failure_is_structured(self) -> None:
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                side_effect=RuntimeError("Windows only"),
            ),
            redirect_stdout(output),
        ):
            result = main(
                ("manager", "inspect", "--node-id", "gaming-pc-east", "--json")
            )

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
