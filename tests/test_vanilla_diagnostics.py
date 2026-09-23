from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from shadowbane_vanilla_diagnostics.capture import (
    assert_required_output_root,
    calculate_cpu_rates,
    mark_active_capture,
)
from shadowbane_vanilla_diagnostics.model import ProcessIdentity, ProcessSample
from shadowbane_vanilla_diagnostics.package import (
    PackageVerificationError,
    verify_package,
)
from shadowbane_vanilla_diagnostics.residue import build_vanilla_preflight
from shadowbane_vanilla_diagnostics.windows import (
    WindowsModuleProbe,
    WindowsNetworkProbe,
    WindowsProcessProbe,
    WindowsWindowInputProbe,
    select_primary_window,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_package(root: Path) -> Path:
    package = root / "package"
    module = package / "shadowbane_vanilla_diagnostics"
    module.mkdir(parents=True)
    runner = package / "run_vanilla_diagnostics.py"
    source = module / "__init__.py"
    runner.write_text("print('runner')\n", encoding="utf-8")
    source.write_text('"""package"""\n', encoding="utf-8")
    files = [runner, source]
    manifest = {
        "schema_version": 1,
        "package_id": "shadowbane-vanilla-diagnostics",
        "package_version": "1.0.0",
        "source_revision": "a" * 40,
        "created_at_utc": "2026-09-02T12:00:00Z",
        "required_output_root": r"\\VBOXSVR\codexdiag\vanilla-diagnostics",
        "allowed_executable_sha256": ["b" * 64],
        "files": [
            {
                "path": path.relative_to(package).as_posix(),
                "length": path.stat().st_size,
                "sha256": _digest(path),
            }
            for path in files
        ],
        "channels": ["process"],
    }
    (package / "package-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return package


class PackageVerificationTests(unittest.TestCase):
    def test_manifested_package_verifies_and_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = _write_package(Path(directory))
            self.assertEqual("1.0.0", verify_package(package)["package_version"])

            (package / "run_vanilla_diagnostics.py").write_text(
                "print('tampered')\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PackageVerificationError, "mismatch"):
                verify_package(package)

    def test_unmanifested_executable_code_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = _write_package(Path(directory))
            (package / "extra.py").write_text("pass\n", encoding="utf-8")
            with self.assertRaisesRegex(PackageVerificationError, "unmanifested"):
                verify_package(package)


class VanillaPreflightTests(unittest.TestCase):
    def test_exact_reviewed_process_without_residue_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "sb.exe"
            executable.write_bytes(b"vanilla")
            digest = _digest(executable)
            identity = ProcessIdentity(4100, 134325668008358961, str(executable))

            report = build_vanilla_preflight(
                requested_executable=executable,
                identity=identity,
                allowed_executable_sha256=[digest],
                modules=[{"name": "sb.exe", "path": str(executable), "image_size": 7}],
                runtime_status_directory=None,
            )

        self.assertTrue(report["accepted"])
        self.assertFalse(report["extension_telemetry_loaded"])

    def test_client_loaded_module_and_identity_status_residue_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "client"
            client.mkdir()
            executable = client / "sb.exe"
            executable.write_bytes(b"vanilla")
            (client / "wonderbane-extension.dll").write_bytes(b"extension")
            status = Path(directory) / "status"
            status.mkdir()
            identity = ProcessIdentity(4100, 134325668008358961, str(executable))
            (status / "heartbeat-4100-134325668008358961.json").write_text(
                "{}",
                encoding="utf-8",
            )

            report = build_vanilla_preflight(
                requested_executable=executable,
                identity=identity,
                allowed_executable_sha256=[_digest(executable)],
                modules=[
                    {"name": "sb.exe", "path": str(executable), "image_size": 7},
                    {
                        "name": "wonderbane-extension.dll",
                        "path": str(client / "wonderbane-extension.dll"),
                        "image_size": 9,
                    },
                ],
                runtime_status_directory=status,
            )

        self.assertFalse(report["accepted"])
        self.assertEqual(3, len(report["failures"]))


class CaptureContractTests(unittest.TestCase):
    def test_output_is_pinned_to_the_isolated_share(self) -> None:
        required = r"\\VBOXSVR\codexdiag\vanilla-diagnostics"
        assert_required_output_root(Path(required), required)
        with self.assertRaisesRegex(Exception, "exactly"):
            assert_required_output_root(Path(r"\\VBOXSVR\codexrepo"), required)


    def test_portable_output_is_pinned_beneath_verified_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            evidence = package_root / "evidence"
            assert_required_output_root(
                evidence,
                r"{PACKAGE_ROOT}\evidence",
                package_root=package_root,
            )
            with self.assertRaisesRegex(Exception, "portable evidence"):
                assert_required_output_root(
                    package_root / "elsewhere",
                    r"{PACKAGE_ROOT}\evidence",
                    package_root=package_root,
                )
    def test_cpu_rates_keep_one_core_and_capacity_interpretations_separate(self) -> None:
        identity = ProcessIdentity(10, 20, r"C:\game\sb.exe")
        previous = ProcessSample(
            identity,
            {"cpu_kernel_seconds": 2.0, "cpu_user_seconds": 3.0},
        )
        current = ProcessSample(
            identity,
            {"cpu_kernel_seconds": 2.25, "cpu_user_seconds": 3.25},
        )

        rates = calculate_cpu_rates(previous, current, 1.0, 4)

        self.assertEqual(50.0, rates["cpu_percent_one_core"])
        self.assertEqual(12.5, rates["cpu_percent_system_capacity"])

    def test_marker_is_create_only_and_bound_to_the_one_active_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run = output / "shadowbane-vanilla-test"
            markers = run / "markers"
            markers.mkdir(parents=True)
            (run / "capture-active.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "active",
                        "run_id": "shadowbane-vanilla-test",
                        "collector_process_id": 900,
                        "collector_process_creation_filetime_utc": 901,
                    }
                ),
                encoding="utf-8",
            )

            class ExactCollectorProbe:
                def sample(self, process_id: int) -> ProcessSample:
                    return ProcessSample(
                        ProcessIdentity(process_id, 901, r"C:\Python\python.exe"),
                        {},
                    )

            marker_path = mark_active_capture(
                output,
                "At Turtles",
                "stutter visible",
                process_probe=ExactCollectorProbe(),
            )
            marker = json.loads(marker_path.read_text(encoding="utf-8"))

        self.assertEqual("at_turtles", marker["label"])
        self.assertEqual("stutter visible", marker["note"])

    def test_primary_window_prefers_largest_visible_non_minimized_window(self) -> None:
        sample = {
            "windows": [
                {"handle": 1, "visible": True, "minimized": False, "rect": [0, 0, 10, 10]},
                {"handle": 2, "visible": True, "minimized": False, "rect": [0, 0, 20, 20]},
                {"handle": 3, "visible": True, "minimized": True, "rect": [0, 0, 30, 30]},
            ]
        }
        self.assertEqual(2, select_primary_window(sample))


@unittest.skipUnless(os.name == "nt", "Windows probe smoke test")
class WindowsProbeSmokeTests(unittest.TestCase):
    def test_current_process_can_be_sampled_without_mutation(self) -> None:
        process_id = os.getpid()
        process = WindowsProcessProbe().sample(process_id)
        modules = WindowsModuleProbe().list_modules(process_id)
        window_input = WindowsWindowInputProbe().sample(process_id)
        network = WindowsNetworkProbe().sample(process_id)

        self.assertEqual(process_id, process.identity.process_id)
        self.assertGreater(process.metrics["process_working_set_bytes"], 0)
        self.assertTrue(any(Path(item["path"]).name == "python.exe" for item in modules))
        self.assertFalse(window_input["input_content_captured"])
        self.assertFalse(network["payload_captured"])


if __name__ == "__main__":
    unittest.main()
