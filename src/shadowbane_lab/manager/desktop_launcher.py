"""Packaged desktop entrypoint: open one exact manager, never infer death from HTTP delay."""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from .manifest import load_manager_manifest
from .startup import StartupConfig, StartupError, StartupStore
from .supervisor import Win32ProcessLifetimeInspector


class StartupPending(StartupError):
    """The owned process may still be starting. A later click resumes the same attempt."""


def manager_interpreter() -> Path:
    """A pythonw shortcut still starts the manager through its exact console interpreter."""
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    if not executable.is_file():
        raise StartupError("The installed manager interpreter is missing")
    return executable


def _message_box(message):
    import ctypes
    from ctypes import wintypes

    show = ctypes.WinDLL("user32", use_last_error=True).MessageBoxW
    show.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
    show.restype = ctypes.c_int
    show(None, message, "WonderBane Control Center", 0x10)


def show_error(message):
    # No authorization token, browser URL, or arbitrary exception text is displayed.
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    if os.name == "nt" and (sys.stderr is None or Path(sys.executable).stem.lower() == "pythonw"):
        _message_box(message)


def listener_present(port):
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def read_startup(port, token, timeout):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/startup", headers={"Authorization": "Bearer " + token}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(16385)
            if len(raw) > 16384:
                raise StartupError("Dashboard startup response is oversized")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Busy request slots are unknown, not proof of a foreign or dead process.
        if exc.code == 503:
            return None
        raise StartupError("Dashboard startup identity was not authenticated") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None
    except (ValueError, UnicodeError):
        raise StartupError("Dashboard startup response is invalid") from None


def wait_for_startup(
    store,
    config,
    record,
    token,
    *,
    deadline,
    clock=time.monotonic,
    sleep=time.sleep,
    request=read_startup,
):
    generation = record["generation"]
    while clock() < deadline:
        current = store.read()
        if current is None or current["generation"] != generation:
            raise StartupError("Manager startup ownership changed while waiting")
        if not store.live(current):
            raise StartupError("The manager exited during startup; inspect its startup log")
        response = request(config.port, token, min(1.0, max(0.001, deadline - clock())))
        if response is not None:
            return store.verify_listener(config, generation, response)
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(0.1, remaining))
    raise StartupPending(
        "The manager is still starting or unavailable. "
        "Its owned process was not restarted; try opening again."
    )


def open_dashboard(
    manifest_path: Path,
    *,
    port=52740,
    worker_state_directory: Path,
    token_file: Path,
    pid_file: Path,
    timeout_seconds=60.0,
    inspector=None,
    spawn=None,
    browser=webbrowser.open,
    clock=time.monotonic,
    sleep=time.sleep,
    request=read_startup,
    port_probe=listener_present,
):
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 1 <= timeout_seconds <= 600
    ):
        raise ValueError("Startup wait must be between 1 and 600 seconds")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Desktop manager requires a fixed loopback port")
    # Import lazily to keep CLI/package ownership free of a circular dependency.
    from shadowbane_lab.cli_commands.manager import _load_or_create_dashboard_token

    manifest = load_manager_manifest(manifest_path)
    token = _load_or_create_dashboard_token(token_file)
    config = StartupConfig.create(
        manifest_path,
        manifest.node_id,
        port,
        worker_state_directory,
        token_file,
        pid_file,
        manager_interpreter(),
    )
    store = StartupStore(
        worker_state_directory.parent, inspector or Win32ProcessLifetimeInspector()
    )
    deadline = clock() + timeout_seconds

    def start(generation):
        args = [
            config.interpreter,
            "-m",
            "shadowbane_lab.cli",
            "manager",
            "app",
            config.manifest,
            "--live",
            "--port",
            str(port),
            "--worker-state-directory",
            config.worker_directory,
            "--authorization-token-file",
            config.token_file,
            "--pid-file",
            config.pid_file,
            "--startup-generation",
            generation,
            "--no-browser",
        ]
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        directory = worker_state_directory.parent
        with (
            (directory / "desktop-start.stdout.log").open("ab") as out,
            (directory / "desktop-start.stderr.log").open("ab") as err,
        ):
            return subprocess.Popen(
                args,
                cwd=manifest_path.resolve().parent,
                env=environment,
                stdout=out,
                stderr=err,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

    record = store.launch_or_reuse(
        config,
        spawn or start,
        listener_present=lambda: port_probe(port),
        timeout_seconds=min(5.0, max(0.001, deadline - clock())),
    )
    wait_for_startup(
        store, config, record, token, deadline=deadline, clock=clock, sleep=sleep, request=request
    )
    # Browser receives a fragment token; neither process arguments nor stdout/logs do.
    try:
        opened = browser(f"http://127.0.0.1:{port}/#token={token}", new=1)
    except (OSError, webbrowser.Error):
        raise StartupError("The manager is ready, but the browser could not be opened") from None
    if not opened:
        raise StartupError("The manager is ready, but the browser could not be opened")
    return record["generation"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--port", type=int, default=52740)
    parser.add_argument("--worker-state-directory", type=Path, required=True)
    parser.add_argument("--authorization-token-file", type=Path, required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--startup-timeout-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        open_dashboard(
            args.manifest,
            port=args.port,
            worker_state_directory=args.worker_state_directory,
            token_file=args.authorization_token_file,
            pid_file=args.pid_file,
            timeout_seconds=args.startup_timeout_seconds,
        )
    except StartupError as exc:
        show_error(str(exc))
        return 1
    except (OSError, RuntimeError, ValueError):
        show_error("The dashboard could not be opened. Check its configuration and startup logs.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
