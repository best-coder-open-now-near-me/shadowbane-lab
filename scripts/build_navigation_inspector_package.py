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
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()



DIAGNOSTIC_TRANSPARENCY_FAILURES = frozenset({
    "wonderbane_extension_selected_cue_native_transparency",
    "wonderbane_extension_effects_native_transparency",
})


def validate_native_results(path: Path, required: set[str], *, diagnostic: bool,
                            exit_code: int) -> list[dict[str, str]]:
    """Retain known diagnostic failures without granting acceptance or hiding skips."""
    cases = ET.parse(path).getroot().findall(".//testcase")
    failures = []
    for case in cases:
        name = case.get("name", "")
        if case.find("error") is not None:
            raise RuntimeError(f"native gate error: {name}")
        if case.find("failure") is not None or case.get("status") == "fail":
            if not diagnostic or name not in DIAGNOSTIC_TRANSPARENCY_FAILURES:
                raise RuntimeError(f"native gate failed: {name}")
            failures.append({"test": name, "status": "failed",
                             "detail": case.findtext("system-out", "")})
    for name in required:
        matches = [case for case in cases if case.get("name") == name]
        if len(matches) != 1 or matches[0].find("skipped") is not None:
            raise RuntimeError(f"native gate missing, duplicated or skipped: {name}")
        allowed_failure = any(failure["test"] == name for failure in failures)
        if matches[0].get("status") != "run" and not allowed_failure:
            raise RuntimeError(f"native gate did not execute: {name}")
    if bool(exit_code) != bool(failures):
        raise RuntimeError("native command exit does not match recorded gate failures")
    return failures

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cmake", default=shutil.which("cmake"))
    parser.add_argument(
        "--output-root", type=Path, help="Local artifact root; use a short Windows path"
    )
    parser.add_argument(
        "--reviewed-client", type=Path, help="Private executable for read-only binding verification"
    )
    parser.add_argument(
        "--diagnostic-observation", action="store_true",
        help="Prepare a non-acceptance trace artifact; retain known transparency failures",
    )
    arguments = parser.parse_args()
    if arguments.diagnostic_observation and not arguments.reviewed_client:
        parser.error("diagnostic observation requires an exact reviewed client")
    if os.name != "nt" or not arguments.cmake:
        parser.error("Windows and CMake are required")
    repo = Path(__file__).resolve().parents[1]

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    if git("status", "--porcelain"):
        parser.error("Commit the reviewed source first; the package must match a clean Git tree")
    revision = git("rev-parse", "HEAD")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_root = arguments.output_root or repo / "artifacts" / "navigation-inspector"
    output = output_root.resolve() / uuid4().hex[:8]
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
    environment.pop("WONDERBANE_MOVEMENT_RUNTIME_TEST", None)
    environment["PYTHONUTF8"] = "1"
    steps = []
    diagnostic_failures = []

    def run(name, command, cwd=source, *, retain_failure=False):
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
        # Preserve executed gates even when a required gate stops packaging.
        # This progress record is not a successful package receipt.
        (output / "validation-progress.json").write_text(
            json.dumps({"source_revision": revision, "steps": steps}, indent=2) + "\n",
            encoding="utf-8",
        )
        if result.returncode:
            print(log.read_text(encoding="utf-8")[-6000:], flush=True)
            if not retain_failure:
                raise RuntimeError(f"{name} failed; see {log}")
            print(f"{name}: FAILED; retained for diagnostic-only validation", flush=True)
            return result.returncode
        print(f"{name}: passed", flush=True)
        return 0

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
        "scene_context.cpp",
        "navigation_protocol.cpp",
        "navigation_channel.cpp",
        "navigation_draw.cpp",
        "navigation_viewer.cpp",
        "effects.cpp",
        "effects_runtime.cpp",
        "effects_draw.cpp",
        "sky.cpp",
        "sky_draw.cpp",
        "sky_runtime.cpp",
        "sky_asset.rc",
    ]
    sky_folder = source / "assets/sky-horizon"
    sky_manifest = json.loads((sky_folder / "manifest.json").read_text(encoding="utf-8"))
    sky_content = (sky_folder / "clear-day.sky").read_bytes()
    if hashlib.sha256(sky_content).hexdigest() != sky_manifest["sha256"]:
        raise RuntimeError("sky asset identity mismatch")
    artifacts = [source_archive, *sorted(sky_folder.iterdir())]
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
        project_root = ET.parse(project).getroot()
        included_sources = [
            Path(item.attrib["Include"]).name
            for tag in ("ClCompile", "ResourceCompile")
            for item in project_root.findall(f".//{{*}}{tag}")
            if "Include" in item.attrib
        ]
        # The native consumer registers after successful startup and defaults disabled.
        # Membership does not certify complete settings/transport capability.
        for movement_source in (
            "movement_boundary_trace.cpp",
            "movement_controls.cpp",
            "movement_native_image.cpp",
            "movement_lifetime.cpp",
            "movement_native_stop.cpp",
            "movement_native_ui.cpp",
            "movement_windows_input.cpp",
            "movement_runtime.cpp",
            "movement_settings.cpp",
        ):
            if included_sources.count(movement_source) != 1:
                raise RuntimeError(
                    f"{profile}: movement source must have one owner: {movement_source}"
                )
        for developer_source in ("movement_tree_probe.cpp",):
            if included_sources.count(developer_source) != 0:
                raise RuntimeError(
                    f"{profile}: developer-only source entered runtime: {developer_source}"
                )
        for name in contracts:
            expected_count = 1 if profile == "full" else 0
            if included_sources.count(name) != expected_count:
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
        native_results = logs / f"{profile}-tests.xml"
        native_exit = run(
            f"{profile}-tests",
            [
                ctest,
                "--test-dir",
                build,
                "-C",
                "Release",
                "--output-on-failure",
                "--output-junit",
                native_results,
            ],
            retain_failure=arguments.diagnostic_observation,
        )
        required_native_tests = {
            "wonderbane_extension_combined_render",
            "wonderbane_extension_selected_cue_gpu",
            "wonderbane_extension_scene_pipeline_guard",
            "wonderbane_extension_scene_query_guard",
            "wonderbane_extension_terrain_trace_enabled",
            "wonderbane_extension_terrain_trace_disabled",
            "wonderbane_extension_selected_cue_native_transparency",
            "wonderbane_extension_effects_native_transparency",
            "wonderbane_extension_movement_runtime_keyboard",
            "wonderbane_extension_movement_runtime_controller",
            "wonderbane_extension_movement_runtime_drag",
            "wonderbane_extension_movement_runtime_focus",
            "wonderbane_extension_movement_runtime_nested-stop",
            "wonderbane_extension_movement_runtime_nested-camera",
            "wonderbane_extension_movement_runtime_nested-move",
            "wonderbane_extension_movement_runtime_chat",
            "wonderbane_extension_movement_runtime_settings-stale",
            "wonderbane_extension_movement_settings",
            "wonderbane_extension_movement_wire",
            "wonderbane_extension_movement_channel",
            "wonderbane_extension_movement_runtime_commands",
        }
        profile_failures = validate_native_results(
            native_results, required_native_tests,
            diagnostic=arguments.diagnostic_observation, exit_code=native_exit,
        )
        diagnostic_failures.extend({"profile": profile, **failure} for failure in profile_failures)
        ipc_results = logs / f"{profile}-movement-ipc.xml"
        environment["WONDERBANE_MOVEMENT_RUNTIME_TEST"] = str(
            build / "Release/wonderbane_extension_movement_runtime_test.exe"
        )
        try:
            run(
                f"{profile}-movement-ipc",
                [sys.executable, "-m", "pytest", "tests/test_native_movement_session.py",
                 "tests/test_manager_movement.py", "tests/test_native_movement_operation.py",
                 "-q", f"--junitxml={ipc_results}"],
            )
        finally:
            environment.pop("WONDERBANE_MOVEMENT_RUNTIME_TEST", None)
        ipc_cases = ET.parse(ipc_results).getroot().findall(".//testcase")
        required_ipc = {
            "test_real_producer_mutex_native_owner_completion_and_readonly_snapshot",
            "test_operation_context_uses_real_native_interprocess_movement",
            "test_standalone_context_real_native_process_renews_across_slow_planner",
        }
        if not required_ipc <= {case.get("name") for case in ipc_cases} or any(
            case.find("skipped") is not None or case.find("failure") is not None
            or case.find("error") is not None for case in ipc_cases
        ):
            raise RuntimeError(f"{profile}: required native movement IPC did not execute and pass")
        if arguments.reviewed_client:
            run(
                f"{profile}-selected-binding",
                [
                    build / "Release/wonderbane_extension_selected_cue_binding_test.exe",
                    arguments.reviewed_client.resolve(),
                ],
            )
        if arguments.reviewed_client:
            for test in ("sky_binding", "sky_render"):
                run(
                    f"{profile}-{test}",
                    [
                        build / f"Release/wonderbane_extension_{test}_test.exe",
                        arguments.reviewed_client.resolve(),
                    ],
                )
        destination = output / profile / "wonderbane-extension.dll"
        destination.parent.mkdir()
        shutil.copy2(build / "Release/wonderbane-extension.dll", destination)
        # PE machine check is independent of the directory/profile label.
        dll = destination.read_bytes()
        if (sky_content in dll) != (profile == "full"):
            raise RuntimeError(f"{profile}: incorrect packaged sky resource ownership")
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
        for name in ("effects.py", "effects_panel.py", "sky.py", "sky_panel.py"):
            if f"shadowbane_lab/graphics_lab/{name}" not in package.namelist():
                raise RuntimeError(f"wheel missing effects control module {name}")
        if "shadowbane_lab/client_extension/movement_settings.py" not in package.namelist():
            raise RuntimeError("wheel missing native movement settings entry")
        if "shadowbane_lab/client_extension/movement_wire.py" not in package.namelist():
            raise RuntimeError("wheel missing native movement codec")
        if "shadowbane_lab/client_extension/movement_session.py" not in package.namelist():
            raise RuntimeError("wheel missing native movement session")
        if "shadowbane_lab/client_extension/movement_dispatcher.py" not in package.namelist():
            raise RuntimeError("wheel missing native movement dispatcher")
        if "shadowbane_lab/manager/movement.py" not in package.namelist():
            raise RuntimeError("wheel missing manager native operation ownership")
        if "shadowbane_lab/client_extension/movement_operation.py" not in package.namelist():
            raise RuntimeError("wheel missing standalone native operation ownership")
        sky_names = [
            name
            for name in package.namelist()
            if name.endswith("/share/shadowbane-lab/sky-horizon/clear-day.sky")
        ]
        if len(sky_names) != 1 or package.read(sky_names[0]) != sky_content:
            raise RuntimeError("wheel missing exact sky content")
    with tarfile.open(sdist) as package:
        names = package.getnames()
        for relative in (
            "assets/sky-horizon/clear-day.sky",
            "native/wonderbane_extension/sky_runtime.cpp",
            "src/shadowbane_lab/graphics_lab/sky_panel.py",
            "native/wonderbane_extension/selected_cue_runtime.cpp",
            "src/shadowbane_lab/graphics_lab/selected_cue.py",
            "native/wonderbane_extension/navigation_draw.cpp",
            "native/wonderbane_extension/effects_runtime.cpp",
            "native/wonderbane_extension/effects_test.cpp",
            "native/wonderbane_extension/movement_runtime.cpp",
            "native/wonderbane_extension/movement_settings.cpp",
            "src/shadowbane_lab/client_extension/movement_settings.py",
            "docs/native-movement-controls.md",
            "native/wonderbane_extension/movement_wire.h",
            "src/shadowbane_lab/client_extension/movement_wire.py",
            "tests/fixtures/native_movement_wire_v2.hex",
            "src/shadowbane_lab/client_extension/movement_session.py",
            "src/shadowbane_lab/client_extension/movement_dispatcher.py",
            "src/shadowbane_lab/manager/movement.py",
            "src/shadowbane_lab/client_extension/movement_operation.py",
            "tests/test_native_movement_operation.py",
            "tests/test_native_movement_session.py",
            "tests/test_native_movement_dispatcher.py",
            "tests/test_manager_movement.py",
            "native/wonderbane_extension/movement_command_queue.h",
            "native/wonderbane_extension/movement_channel_test.cpp",
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
    effects_smoke = (
        "import tkinter as tk; import shadowbane_lab.graphics_lab.app as module; "
        "module.discover_graphics_targets=lambda: (); "
        "root=tk.Tk(); root.withdraw(); app=module.GraphicsLabApp(root); "
        "assert app.effects_panel is not None; app.close()"
    )
    run("installed-effects-panel", [python, "-c", effects_smoke], cwd=output)
    cue_smoke = (
        "import tkinter as tk; import shadowbane_lab.graphics_lab.app as module; "
        "module.discover_graphics_targets=lambda: (); "
        "root=tk.Tk(); root.withdraw(); app=module.GraphicsLabApp(root); "
        "assert app.cue_panel.settings().enabled is False; app.close()"
    )
    run("installed-selection-panel", [python, "-c", cue_smoke], cwd=output)
    sky_smoke = (
        "import tkinter as tk; import shadowbane_lab.graphics_lab.app as module; "
        "module.discover_graphics_targets=lambda: (); "
        "root=tk.Tk(); root.withdraw(); app=module.GraphicsLabApp(root); "
        "assert app.sky_panel.get().enabled == 0; app.close()"
    )
    run("installed-sky-panel", [python, "-c", sky_smoke], cwd=output)
    movement_smoke = """
import pathlib, sys, tkinter as tk
import shadowbane_lab.graphics_lab.app as module
import shadowbane_lab.client_extension.movement_settings as settings
assert pathlib.Path(settings.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
module.discover_graphics_targets = lambda: ()
root = tk.Tk()
root.withdraw()
app = module.GraphicsLabApp(root)
def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)
buttons = [child for child in descendants(root)
           if child.winfo_class() == "TButton" and child.cget("text") == "Movement controls"]
assert len(buttons) == 1
buttons[0].invoke()
assert app.status_var.get() == "Select a connected client first"
app.close()
"""
    run("installed-movement-panel", [python, "-c", movement_smoke], cwd=output)
    run("installed-trace-reader", [python, "-c", """
import json, pathlib, sys, tempfile
from shadowbane_lab.diagnostics import terrain_trace
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(terrain_trace.__file__).resolve().is_relative_to(installed_root)
payload = {"transmission_state": {"program": 0, "framebuffer": 0},
           "quad_support": {"program_pipeline": 0}}
with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory) / "trace.json"
    path.write_text(json.dumps(payload))
    assert terrain_trace.read_local_trace(path) == payload
"""], cwd=output)
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
    artifacts.extend(sorted(logs.glob("*.xml")))
    sky_handoff = output / "sky-horizon.md"
    shutil.copy2(source / "docs/handoffs/sky-horizon.md", sky_handoff)
    artifacts.append(sky_handoff)
    diagnostic = arguments.diagnostic_observation
    if diagnostic:
        diagnostic_note = output / "DIAGNOSTIC-ONLY.txt"
        diagnostic_note.write_text(
            "DIAGNOSTIC OBSERVATION ONLY - NOT AN ACCEPTANCE CANDIDATE\n"
            f"Exact source: {revision}\n"
            "Known full transparency gate failures remain recorded in diagnostic-manifest.json.\n"
            "No VM installation, deployment or activation is authorized by this artifact.\n"
            "Only the full-profile DLL contains the opt-in terrain observer.\n"
            "Both profiles are retained for verification; their capabilities differ.\n"
            "Existing capture-wonderbane-terrain-trace.ps1 requests one bounded frame.\n"
            "Activation requires an exact isolated runtime, disabled visual/movement settings,\n"
            "verified restoration and separate owner authorization. No current client overwrite.\n"
            "A frame identifies observed submissions/state, not opaque completeness.\n",
            encoding="utf-8",
        )
        artifacts.append(diagnostic_note)
    receipt = {
        "purpose": "diagnostic_observation" if diagnostic else "acceptance_candidate",
        "acceptance_eligible": not diagnostic,
        "known_failed_gates": diagnostic_failures,
        "source_revision": revision,
        "source_branch": git("branch", "--show-current"),
        "built_utc": stamp,
        "platform": "Visual Studio 2022 / Win32 / Release",
        "terrain_material_repair_included": False,
        "actor_root_effects_included": True,
        "sky_horizon_included": True,
        "sky_asset": sky_manifest,
        "sky_binding_and_runtime_verified": bool(arguments.reviewed_client),
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
    receipt_path = output / ("diagnostic-manifest.json" if diagnostic else "receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    handoff = output / "navigation-inspector.md"
    shutil.copy2(source / "docs/handoffs/navigation-inspector.md", handoff)
    effects_handoff = output / "particles-trails.md"
    shutil.copy2(source / "docs/handoffs/particles-trails.md", effects_handoff)
    artifacts.append(effects_handoff)
    package_stem = (
        "navigation-inspector-diagnostic" if diagnostic else "navigation-inspector-acceptance"
    )
    package_path = output / f"{package_stem}.zip"
    with zipfile.ZipFile(package_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [
            receipt_path,
            handoff,
            source / "docs/handoffs/selected-character-cue.md",
            *artifacts,
        ]:
            archive.write(path, path.relative_to(output))
    digest_path = output / f"{package_stem}.sha256"
    digest_path.write_text(sha256(package_path) + "  " + package_path.name + "\n", encoding="ascii")
    print(
        json.dumps(
            {
                "purpose": receipt["purpose"],
                "acceptance_eligible": not diagnostic,
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
