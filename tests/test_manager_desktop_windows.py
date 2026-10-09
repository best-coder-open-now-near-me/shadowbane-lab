"""Actual Windows process/lock/HTTP handshake with only gameplay application substituted."""

import json
import os
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import shadowbane_lab
from shadowbane_lab.manager import desktop_launcher as desktop
from shadowbane_lab.manager.startup import StartupStore
from shadowbane_lab.manager.supervisor import Win32ProcessLifetimeInspector


@pytest.mark.skipif(os.name != "nt", reason="exact Windows process lifetime required")
def test_real_desktop_entrypoint_reuses_startup_across_timeout(tmp_path, monkeypatch):
    manifest = tmp_path / "manager.json"
    game = tmp_path / "unused-game"
    game.mkdir()
    executable = game / "launcher.exe"
    executable.write_bytes(b"not executed")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "node_id": "desktop-test",
                "clients": [
                    {
                        "client_id": "test-client",
                        "launch": {
                            "executable": str(executable),
                            "arguments": [],
                            "working_directory": str(game),
                        },
                        "expected_process_directory": str(game),
                        "expected_executable_names": ["sb.exe"],
                        "window_tile": {"left": 0, "top": 0, "width": 800, "height": 600},
                    }
                ],
            }
        )
    )
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    args = [
        str(manifest),
        "--port",
        str(port),
        "--worker-state-directory",
        str(tmp_path / "workers"),
        "--authorization-token-file",
        str(tmp_path / "dashboard.token"),
        "--pid-file",
        str(tmp_path / "manager.pid"),
    ]
    fixture = Path(__file__).parent / "fixtures" / "manager_desktop_child.py"
    package_root = str(Path(shadowbane_lab.__file__).parent.parent)
    real_popen = subprocess.Popen
    children, opened, errors = [], [], []

    def fixture_popen(command, **kwargs):
        assert Path(command[0]).name.lower() == "python.exe"
        assert command[1:3] == ["-m", "shadowbane_lab.cli"]
        assert "PYTHONHOME" not in kwargs["env"] and "PYTHONPATH" not in kwargs["env"]
        child = real_popen([command[0], str(fixture), package_root, *command[3:]], **kwargs)
        children.append(child)
        return child

    original_open = desktop.open_dashboard

    def open_test(*a, **kw):
        return original_open(*a, browser=lambda url, **unused: opened.append(url) or True, **kw)

    monkeypatch.setattr(desktop.subprocess, "Popen", fixture_popen)
    monkeypatch.setattr(desktop, "open_dashboard", open_test)
    monkeypatch.setattr(desktop, "show_error", errors.append)
    monkeypatch.setenv("PYTHONHOME", "must-not-reach-manager")
    monkeypatch.setenv("PYTHONPATH", "must-not-reach-manager")
    store = StartupStore(tmp_path, Win32ProcessLifetimeInspector())
    try:
        assert desktop.main([*args, "--startup-timeout-seconds", "1"]) == 1
        assert len(children) == 1 and children[0].poll() is None
        assert errors and "not restarted" in errors[0]
        generation = store.read()["generation"]
        (tmp_path / "allow-listener").touch()
        assert desktop.main([*args, "--startup-timeout-seconds", "20"]) == 0
        with ThreadPoolExecutor(4) as pool:
            assert list(pool.map(lambda _: desktop.main(args), range(4))) == [0] * 4
        record = store.read()
        assert record["generation"] == generation and len(children) == 1
        assert record["manager"] is not None and store.live(record)
        assert len(opened) == 5
        token = (tmp_path / "dashboard.token").read_text().strip()
        for log in (tmp_path / "desktop-start.stdout.log", tmp_path / "desktop-start.stderr.log"):
            assert token not in log.read_text()
        assert token not in " ".join(errors)
    finally:
        (tmp_path / "stop-test").touch()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)
    assert all(child.returncode == 0 for child in children)
