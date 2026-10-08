"""Start a locally pinned mod pack on the PC's normal graphics driver."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from shadowbane_lab.client_extension.package import verify_runtime_patched_client_copy


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(config: dict) -> Path:
    root = Path(config["client_directory"]).resolve(strict=True)
    evidence = root / ".wonderbane-extension" / "package.json"
    if digest(evidence) != config["package_sha256"]:
        raise ValueError(
            "Mod pack inventory changed; revalidate this installation before launching."
        )
    package = verify_runtime_patched_client_copy(root)
    if package.extension_sha256 != config["extension_sha256"]:
        raise ValueError("Mod pack extension does not match the selected build.")
    if package.result_executable_sha256 != config["executable_sha256"]:
        raise ValueError("Mod pack client does not match the selected build.")
    for entry in config.get("panel_files", []):
        if digest(Path(entry["path"])) != entry["sha256"]:
            raise ValueError(
                "The installed panel changed; install the matching panel and extension."
            )
    return root


def panel(pid: int | None) -> None:
    import tkinter as tk
    from tkinter import ttk

    from shadowbane_lab.graphics_lab.app import GraphicsLabApp

    root = tk.Tk()
    app = GraphicsLabApp(root)
    if pid is not None:
        for index, target in enumerate(app.targets):
            if target.process_id == pid:
                app.target_combo.current(index)
                app._connect_target(target)
                break

    def select_katana(widget):
        if isinstance(widget, ttk.Notebook):
            for tab in widget.tabs():
                if widget.tab(tab, "text") == "Katana":
                    widget.select(tab)
        for child in widget.winfo_children():
            select_katana(child)

    select_katana(root)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--panel-only", action="store_true")
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    if args.panel_only:
        panel(args.pid)
        return 0
    root = verify(config)
    if args.check:
        print("Mod pack verified: " + str(root))
        return 0
    env = os.environ.copy()
    for name in (
        "LIBGL_ALWAYS_SOFTWARE",
        "GALLIUM_DRIVER",
        "LP_NUM_THREADS",
        "MESA_EXTENSION_MAX_YEAR",
        "MESA_GL_VERSION_OVERRIDE",
        "MESA_GLSL_VERSION_OVERRIDE",
    ):
        env.pop(name, None)
    game = subprocess.Popen([str(root / "sb.exe")], cwd=root, env=env)
    record = {
        "process_id": game.pid,
        "client_directory": str(root),
        "source_commit": config["source_commit"],
    }
    args.config.with_name("last-launch.json").write_text(json.dumps(record, indent=2))
    print("Started modded Wonderbane, PID " + str(game.pid), flush=True)
    from shadowbane_lab.client_extension.graphics_status_wait import (
        GraphicsRuntimeStatusExpectation,
        wait_for_graphics_runtime_status,
    )
    from shadowbane_lab.manager.supervisor import Win32ProcessLifetimeInspector

    lifetime = Win32ProcessLifetimeInspector().inspect(game.pid)
    if lifetime is None:
        raise RuntimeError("The game exited during startup.")
    status = wait_for_graphics_runtime_status(
        GraphicsRuntimeStatusExpectation(
            status_directory=Path(os.environ["LOCALAPPDATA"]) / "ShadowbaneLab/client-extension",
            process_id=game.pid,
            process_creation_filetime_utc=lifetime.process_started_at_100ns,
            executable_path=root / "sb.exe",
            executable_sha256=config["executable_sha256"],
            runtime_profile="full-renderer",
        ),
        timeout_seconds=30,
    )
    args.config.with_name("last-graphics-status.json").write_text(json.dumps(status, indent=2))
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen(
        [
            str(pythonw),
            str(Path(__file__).resolve()),
            "--config",
            str(args.config.resolve()),
            "--panel-only",
            "--pid",
            str(game.pid),
        ],
        cwd=root,
        env=env,
    )
    print("Full graphics extension verified; Katana panel opened.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print("Mod pack could not start: " + str(error), file=sys.stderr)
        raise SystemExit(1) from error
