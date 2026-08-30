from pathlib import Path


def replace_exact(path: Path, old: str, new: str, *, expected: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrence(s), found {count}: {old[:80]!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


cli_tests = Path("tests/test_cli.py")
replace_exact(
    cli_tests,
    '''            patch("shadowbane_lab.cli.load_calibration", return_value=profile),
            patch(
                "shadowbane_lab.cli.WindowsHotkeyEmergencyStop",
''',
    '''            patch("shadowbane_lab.cli.load_calibration", return_value=profile),
            patch(
                "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                return_value=StaticWindowInspector(_valid_snapshot()),
            ),
            patch(
                "shadowbane_lab.cli.PyAutoGuiBackend",
                return_value=RecordingInputBackend(),
            ),
            patch(
                "shadowbane_lab.cli.WindowsHotkeyEmergencyStop",
''',
    expected=2,
)
replace_exact(
    cli_tests,
    '''            patch("shadowbane_lab.cli.load_manager_manifest", return_value=MagicMock()),
            patch("shadowbane_lab.cli.ManifestClientRegistryProvider"),
''',
    '''            patch("shadowbane_lab.cli.load_manager_manifest", return_value=MagicMock()),
            patch(
                "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                return_value=StaticVisibleWindowInspector(()),
            ),
            patch(
                "shadowbane_lab.cli.PyAutoGuiBackend",
                return_value=RecordingInputBackend(),
            ),
            patch("shadowbane_lab.cli.ManifestClientRegistryProvider"),
''',
)

manager_tests = Path("tests/test_manager_cli.py")
replace_exact(
    manager_tests,
    "from pathlib import Path\n",
    "from pathlib import Path, PureWindowsPath\n",
)
replace_exact(
    manager_tests,
    '''def _manifest_client(
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
''',
    '''def _windows_game_directory(game_directory: Path) -> PureWindowsPath:
    return PureWindowsPath(r"C:\\Tests") / game_directory.name


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
''',
)
replace_exact(
    manager_tests,
    '''            inspector = StaticVisibleWindowInspector(
                (
                    _snapshot(
                        executable_path=str(game_directory / "sb.exe"),
                    ),
                )
            )
''',
    '''            inspector = StaticVisibleWindowInspector(
                (
                    _snapshot(
                        executable_path=str(
                            _windows_game_directory(game_directory) / "sb.exe"
                        ),
                    ),
                )
            )
''',
)
replace_exact(
    manager_tests,
    '''            inspector = StaticVisibleWindowInspector(
                (_snapshot(executable_path=str(game_directory / "sb.exe")),)
            )
''',
    '''            inspector = StaticVisibleWindowInspector(
                (
                    _snapshot(
                        executable_path=str(
                            _windows_game_directory(game_directory) / "sb.exe"
                        )
                    ),
                )
            )
''',
)
replace_exact(
    manager_tests,
    '''            with (
                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=inspector,
                ),
                redirect_stdout(output),
            ):
                result = main(("manager", "preflight", str(manifest_path), "--json"))
''',
    '''            with (
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
''',
    expected=2,
)
replace_exact(
    manager_tests,
    '''                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=StaticVisibleWindowInspector(()),
                ),
                patch(
                    "shadowbane_lab.cli.Win32WindowApi",
''',
    '''                patch(
                    "shadowbane_lab.cli.WindowsVisibleWindowInspector",
                    return_value=StaticVisibleWindowInspector(()),
                ),
                patch(
                    "shadowbane_lab.cli._manager_path_status",
                    side_effect=_ready_manager_path_status,
                ),
                patch(
                    "shadowbane_lab.cli.Win32WindowApi",
''',
)
