"""Actual Windows process/lock/HTTP handshake with only gameplay application substituted."""

import json
import os
import socket
import subprocess
import sys
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


@pytest.mark.skipif(os.name != "nt", reason="actual Windows CreateProcess required")
def test_windows_rejected_process_creation_can_retry_without_erasing_unknown(tmp_path, monkeypatch):
    import _winapi

    from shadowbane_lab.manager.startup import SpawnNotCreated, StartupConfig

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    config = StartupConfig.create(
        manifest,
        "test",
        52740,
        tmp_path / "workers",
        tmp_path / "token",
        tmp_path / "pid",
        Path(sys.executable),
    )
    store = StartupStore(tmp_path, Win32ProcessLifetimeInspector())
    invalid = tmp_path / "invalid.exe"
    invalid.write_bytes(b"not an executable")

    def spawn(executable, arguments=()):
        return lambda generation: desktop.spawn_manager_process(
            [str(executable), *arguments],
            directory=tmp_path,
            manifest_directory=tmp_path,
            environment=os.environ.copy(),
        )

    with pytest.raises(SpawnNotCreated):
        store.launch_or_reuse(config, spawn(invalid), listener_present=lambda: False)
    assert store.read() is None
    real_create = _winapi.CreateProcess

    def denied(*args, **kwargs):
        import ctypes

        raise ctypes.WinError(5)

    with monkeypatch.context() as patch:
        patch.setattr(_winapi, "CreateProcess", denied)
        with pytest.raises(SpawnNotCreated):
            store.launch_or_reuse(config, spawn(sys.executable), listener_present=lambda: False)
    assert store.read() is None and _winapi.CreateProcess is real_create
    child = None

    def corrected(generation):
        nonlocal child
        child = spawn(sys.executable, ["-c", "import time; time.sleep(30)"])(generation)
        return child

    try:
        record = store.launch_or_reuse(config, corrected, listener_present=lambda: False)
        assert child is not None and store.live(record)
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=5)


def test_log_open_failure_is_known_before_spawn(tmp_path, monkeypatch):
    from shadowbane_lab.manager.startup import SpawnNotCreated

    calls = []
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda *a, **kw: calls.append(a))
    with pytest.raises(SpawnNotCreated):
        desktop.spawn_manager_process(
            [sys.executable],
            directory=tmp_path / "missing",
            manifest_directory=tmp_path,
            environment={},
        )
    assert calls == []


def test_log_close_failure_after_spawn_is_not_no_child(monkeypatch):
    from shadowbane_lab.manager.startup import SpawnNotCreated

    calls = []

    class Log:
        def open(self, mode):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *unused):
            error = OSError("close failed after creation")
            error.winerror = 5
            raise error

    class Directory:
        def __truediv__(self, name):
            return Log()

    monkeypatch.setattr(desktop.subprocess, "Popen", lambda *a, **kw: calls.append(a) or object())
    with pytest.raises(OSError) as failure:
        desktop.spawn_manager_process(
            [sys.executable], directory=Directory(), manifest_directory=Path.cwd(), environment={}
        )
    assert not isinstance(failure.value, SpawnNotCreated) and len(calls) == 1


@pytest.mark.skipif(os.name != "nt", reason="actual Windows process required")
def test_post_creation_popen_error_retains_intent_and_never_duplicates(tmp_path, monkeypatch):
    import ctypes

    from shadowbane_lab.manager.startup import StartupConfig

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    config = StartupConfig.create(
        manifest,
        "test",
        52740,
        tmp_path / "workers",
        tmp_path / "token",
        tmp_path / "pid",
        Path(sys.executable),
    )
    store = StartupStore(tmp_path, Win32ProcessLifetimeInspector())
    actual = subprocess.Popen
    children = []

    def created_then_error(*args, **kwargs):
        children.append(actual(*args, **kwargs))
        raise ctypes.WinError(5)

    monkeypatch.setattr(desktop.subprocess, "Popen", created_then_error)

    def spawn(generation):
        return desktop.spawn_manager_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            directory=tmp_path,
            manifest_directory=tmp_path,
            environment=os.environ.copy(),
        )

    try:
        with pytest.raises(OSError):
            store.launch_or_reuse(config, spawn, listener_present=lambda: False)
        record = store.read()
        assert record["launcher"] is None and len(children) == 1
        assert children[0].poll() is None
        assert store.launch_or_reuse(config, spawn, listener_present=lambda: False) == record
        assert len(children) == 1
    finally:
        for child in children:
            child.terminate()
            child.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="actual Windows process required")
def test_post_create_handle_cleanup_error_is_unknown(tmp_path, monkeypatch):
    import _winapi
    import ctypes

    from shadowbane_lab.manager.startup import StartupConfig

    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    config = StartupConfig.create(
        manifest,
        "test",
        52740,
        tmp_path / "workers",
        tmp_path / "token",
        tmp_path / "pid",
        Path(sys.executable),
    )
    store = StartupStore(tmp_path, Win32ProcessLifetimeInspector())
    original_close = subprocess.Popen._close_pipe_fds

    def fail_after_close(self, *args):
        original_close(self, *args)
        raise ctypes.WinError(5)

    monkeypatch.setattr(subprocess.Popen, "_close_pipe_fds", fail_after_close)

    def spawn(generation):
        return desktop.spawn_manager_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            directory=tmp_path,
            manifest_directory=tmp_path,
            environment=os.environ.copy(),
        )

    handles = None
    try:
        with pytest.raises(OSError) as failure:
            store.launch_or_reuse(config, spawn, listener_present=lambda: False)
        trace = failure.value.__traceback__
        while trace is not None:
            if trace.tb_frame.f_code is desktop._WINDOWS_EXECUTE_CHILD:
                handles = trace.tb_frame.f_locals
                break
            trace = trace.tb_next
        assert handles is not None and handles["pid"] > 0
        assert not desktop._creation_rejected_before_handles(failure.value)
        record = store.read()
        assert record["launcher"] is None
        assert store.launch_or_reuse(config, spawn, listener_present=lambda: False) == record
    finally:
        if handles is not None:
            # These are the actual handles returned by our single test CreateProcess.
            _winapi.TerminateProcess(handles["hp"], 0)
            _winapi.WaitForSingleObject(handles["hp"], 5000)
            _winapi.CloseHandle(handles["hp"])
            _winapi.CloseHandle(handles["ht"])
