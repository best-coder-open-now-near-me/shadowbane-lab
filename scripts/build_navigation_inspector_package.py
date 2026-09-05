"""Build and validate an exact committed Windows inspector acceptance package.

Run with Python 3.11+ containing build, setuptools>=77 and the project test
dependencies. Requires CMake and Visual Studio 2022 C++ Win32. This creates
only local artifacts; it never installs into a game or publishes binaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cmake", default=shutil.which("cmake"))
    parser.add_argument(
        "--output-root", type=Path, help="Local artifact root; use a short Windows path"
    )
    parser.add_argument(
        "--reviewed-client", type=Path, help="Private executable for read-only binding verification"
    )
    arguments = parser.parse_args()
    if os.name != "nt" or not arguments.cmake:
        parser.error("Windows and CMake are required")
    repo = Path(__file__).resolve().parents[1]

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    if git("status", "--porcelain"):
        parser.error("Commit the reviewed source first; the package must match a clean Git tree")
    revision = git("rev-parse", "HEAD")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = (
        arguments.output_root or repo / "artifacts" / "navigation-inspector"
    ).resolve() / uuid4().hex[:8]
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    logs = output / "logs"
    logs.mkdir()
    source_archive = output / "source.zip"
    subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=zip", f"--output={source_archive}", revision],
        check=True,
    )
    with zipfile.ZipFile(source_archive) as archive:
        archive.extractall(source)
    metadata = {"source_revision": revision}
    identity = source / "src/shadowbane_lab/navigation_inspector/build_identity.json"
    identity.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    steps = []

    def run(name, command, cwd=source):
        command = [str(value) for value in command]
        print(f"{name}: running", flush=True)
        log = logs / f"{name}.log"
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                command, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT
            )
        steps.append(
            {
                "name": name,
                "command": command,
                "exit_code": result.returncode,
                "log": str(log.relative_to(output)),
            }
        )
        if result.returncode:
            print(log.read_text(encoding="utf-8")[-6000:], flush=True)
            raise RuntimeError(f"{name} failed; see {log}")
        print(f"{name}: passed", flush=True)

    run("python-tests", [sys.executable, "-m", "pytest", "-q"])
    run(
        "ruff",
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "scripts/build_navigation_inspector_package.py",
        ],
    )
    cmake = Path(arguments.cmake).resolve()
    ctest = cmake.with_name("ctest.exe")
    contracts = [
        "selected_cue.cpp",
        "selected_cue_gpu.cpp",
        "selected_cue_runtime.cpp",
        "effects_attachment.cpp",
        "scene_draw.cpp",
        "navigation_protocol.cpp",
        "navigation_channel.cpp",
        "navigation_draw.cpp",
        "navigation_viewer.cpp",
    ]
    artifacts = [source_archive]
    for profile in ("full", "diagnostics-only"):
        # MSBuild still imposes MAX_PATH on its long generated test tlog names.
        build = output / ("nf" if profile == "full" else "nd")
        run(
            f"{profile}-configure",
            [
                cmake,
                "-S",
                source / "native/wonderbane_extension",
                "-B",
                build,
                "-G",
                "Visual Studio 17 2022",
                "-A",
                "Win32",
                f"-DWONDERBANE_EXTENSION_PROFILE={profile}",
            ],
        )
        project = build / "wonderbane_extension.vcxproj"
        project_text = project.read_text(encoding="utf-8-sig")
        for name in contracts:
            if (name in project_text) != (profile == "full"):
                raise RuntimeError(f"{profile}: incorrect runtime source ownership for {name}")
        run(
            f"{profile}-build",
            [
                cmake,
                "--build",
                build,
                "--config",
                "Release",
                "--parallel",
                "4",
                "--",
                "/verbosity:quiet",
            ],
        )
        run(
            f"{profile}-tests", [ctest, "--test-dir", build, "-C", "Release", "--output-on-failure"]
        )
        if arguments.reviewed_client:
            run(
                f"{profile}-selected-binding",
                [
                    build / "Release/wonderbane_extension_selected_cue_binding_test.exe",
                    arguments.reviewed_client.resolve(),
                ],
            )
        destination = output / profile / "wonderbane-extension.dll"
        destination.parent.mkdir()
        shutil.copy2(build / "Release/wonderbane-extension.dll", destination)
        # PE machine check is independent of the directory/profile label.
        dll = destination.read_bytes()
        pe = int.from_bytes(dll[60:64], "little")
        if dll[pe : pe + 4] != (b"PE" + bytes(2)):
            raise RuntimeError("invalid DLL PE signature")
        if int.from_bytes(dll[pe + 4 : pe + 6], "little") != 0x14C:
            raise RuntimeError("DLL is not Win32/x86")
        artifacts.extend([destination, project, build / "Testing/Temporary/LastTest.log"])
    # build produces the wheel from its own freshly built source distribution.
    run(
        "python-packages",
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", output / "dist"],
    )
    (wheel,) = (output / "dist").glob("*.whl")
    (sdist,) = (output / "dist").glob("*.tar.gz")
    with zipfile.ZipFile(wheel) as package:
        identity_name = "shadowbane_lab/navigation_inspector/build_identity.json"
        if json.loads(package.read(identity_name)) != metadata:
            raise RuntimeError("wheel source identity does not match")
        (entry,) = [name for name in package.namelist() if name.endswith("entry_points.txt")]
        if "shadowbane-navigation-inspector" not in package.read(entry).decode():
            raise RuntimeError("wheel is missing the inspector entry point")
    with tarfile.open(sdist) as package:
        names = package.getnames()
        for relative in (
            "native/wonderbane_extension/selected_cue_runtime.cpp",
            "src/shadowbane_lab/graphics_lab/selected_cue.py",
            "native/wonderbane_extension/navigation_draw.cpp",
            "tests/fixtures/navigation-inspector-v1.hex",
            "tests/fixtures/navigation-inspector-controls-v1.hex",
            "src/shadowbane_lab/navigation_inspector/build_identity.json",
            "scripts/build_navigation_inspector_package.py",
        ):
            if not any(name.endswith("/" + relative) for name in names):
                raise RuntimeError(f"source distribution missing {relative}")
        if any("/artifacts/" in name or "/.git/" in name for name in names):
            raise RuntimeError("source distribution includes private/generated artifacts")
    installed = output / "installed-wheel"
    run("wheel-environment", [sys.executable, "-m", "venv", installed])
    python = installed / "Scripts/python.exe"
    run("wheel-install", [python, "-m", "pip", "install", "--no-index", "--no-deps", wheel])
    run(
        "installed-entry-point",
        [installed / "Scripts/shadowbane-navigation-inspector.exe", "--help"],
        cwd=output,
    )
    smoke = (
        "import json, pathlib, tkinter as tk; "
        "import shadowbane_lab.navigation_inspector.app as module; "
        f"assert json.loads(pathlib.Path(module.__file__).with_name('build_identity.json')"
        f".read_text())['source_revision'] == '{revision}'; "
        "root=tk.Tk(); root.withdraw(); app=module.InspectorApp(root,discover=lambda:()); "
        "assert app.current_snapshot is None; app.close()"
    )
    run("installed-panel", [python, "-c", smoke], cwd=output)
    cue_smoke = (
        "import tkinter as tk; from shadowbane_lab.graphics_lab.app import GraphicsLabApp; "
        "root=tk.Tk(); root.withdraw(); app=GraphicsLabApp(root); "
        "assert app.cue_panel.settings().enabled is False; app.close()"
    )
    run("installed-selection-panel", [python, "-c", cue_smoke], cwd=output)
    artifacts.extend(
        [
            wheel,
            sdist,
            identity,
            source / "src/shadowbane_lab/navigation_inspector/protocol.py",
            source / "native/wonderbane_extension/navigation_protocol.h",
            source / "tests/fixtures/navigation-inspector-v1.hex",
            source / "tests/fixtures/navigation-inspector-controls-v1.hex",
        ]
    )
    artifacts.extend(sorted(logs.glob("*.log")))
    receipt = {
        "source_revision": revision,
        "source_branch": git("branch", "--show-current"),
        "built_utc": stamp,
        "platform": "Visual Studio 2022 / Win32 / Release",
        "terrain_material_repair_included": False,
        "live_acceptance": "pending; no deployment performed",
        "selected_cue_binding_verified": bool(arguments.reviewed_client),
        "source_identity": metadata,
        "steps": steps,
        "files": [
            {
                "path": str(path.relative_to(output)).replace(chr(92), "/"),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in artifacts
        ],
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    handoff = output / "navigation-inspector.md"
    shutil.copy2(source / "docs/handoffs/navigation-inspector.md", handoff)
    package_path = output / "navigation-inspector-acceptance.zip"
    with zipfile.ZipFile(package_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [
            receipt_path,
            handoff,
            source / "docs/handoffs/selected-character-cue.md",
            *artifacts,
        ]:
            archive.write(path, path.relative_to(output))
    digest_path = output / "navigation-inspector-acceptance.sha256"
    digest_path.write_text(sha256(package_path) + "  " + package_path.name + "\n", encoding="ascii")
    print(
        json.dumps(
            {
                "package": str(package_path),
                "sha256": sha256(package_path),
                "receipt": str(receipt_path),
                "source_revision": revision,
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
