import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.client_extension.manifest import (
    ExtensionArtifact,
    MaskedSignature,
    PatchManifest,
    PatchSite,
    SourceExecutable,
)
from shadowbane_lab.manager import load_manager_manifest
from shadowbane_lab.manager.runtime_deployment import (
    RuntimeDeploymentError,
    provision_isolated_client_runtimes,
)


def _manager_payload() -> dict[str, object]:
    clients = []
    for index in range(4):
        clients.append(
            {
                "client_id": f"client-{index + 1:02d}",
                "launch": {
                    "executable": r"C:\OldShared\sb.exe",
                    "arguments": [],
                    "working_directory": r"C:\OldShared",
                },
                "expected_process_directory": r"C:\OldShared",
                "expected_executable_names": ["sb.exe"],
                "window_tile": {
                    "left": (index % 2) * 960,
                    "top": (index // 2) * 477,
                    "width": 960,
                    "height": 477 + (index // 2),
                },
            }
        )
    return {"schema_version": 1, "node_id": "wonderbane-vm", "clients": clients}


def _patch_manifest() -> PatchManifest:
    return PatchManifest(
        patch_id="fixture.bootstrap-v1",
        source=SourceExecutable(
            file_name="sb.exe",
            sha256="1" * 64,
            length=1024,
            machine=0x14C,
            pointer_size=4,
        ),
        patched_executable_sha256="2" * 64,
        extension=ExtensionArtifact(
            file_name="wonderbane-extension.dll",
            sha256="3" * 64,
            version="1.3.0",
            machine=0x14C,
            bootstrap_export="WonderBaneExtensionInitialize",
        ),
        sites=(
            PatchSite(
                site_id="entry",
                section=".text",
                reviewed_rva=0x1000,
                expected_original=b"\x01",
                replacement=b"\x02",
                signature=MaskedSignature(value=b"\x00\x7f", mask=b"\x00\xff"),
                signature_site_offset=0,
                search_radius=16,
            ),
        ),
    )


class ManagerRuntimeDeploymentTests(unittest.TestCase):
    def test_publishes_two_unique_runtimes_then_atomically_retargets_manager(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "client-manager.json"
            manifest_path.write_text(json.dumps(_manager_payload()), encoding="utf-8")
            frozen = root / "frozen"
            frozen.mkdir()
            extension = root / "wonderbane-extension.dll"
            extension.write_bytes(b"extension")
            deployment = root / "vanilla-20260831"
            baseline = SimpleNamespace(
                directory=str(frozen),
                tree_sha256="4" * 64,
                repository_revision="abc123",
            )

            def prepare(_baseline, destination, _manifest, _extension, **_kwargs):
                destination = Path(destination)
                destination.mkdir()
                (destination / "sb.exe").write_bytes(b"patched")
                evidence = SimpleNamespace(
                    destination_directory=str(destination.resolve()),
                    working_tree_sha256="5" * 64,
                    result_executable_sha256="2" * 64,
                    extension_sha256="3" * 64,
                )
                return SimpleNamespace(destination_published=True, evidence=evidence)

            with (
                patch(
                    "shadowbane_lab.manager.runtime_deployment.verify_frozen_client_baseline",
                    return_value=baseline,
                ),
                patch(
                    "shadowbane_lab.manager.runtime_deployment.prepare_patched_client_copy",
                    side_effect=prepare,
                ) as prepare_copy,
            ):
                result = provision_isolated_client_runtimes(
                    manifest_path,
                    frozen,
                    deployment,
                    _patch_manifest(),
                    extension,
                    deployment_id="vanilla-20260831",
                    slot_count=2,
                )

            configured = load_manager_manifest(manifest_path)
            self.assertEqual(2, prepare_copy.call_count)
            self.assertEqual(2, len(configured.clients))
            self.assertEqual(
                (None, None), tuple(client.window_tile for client in configured.clients)
            )
            self.assertEqual(
                2,
                len({str(client.launch.working_directory) for client in configured.clients}),
            )
            self.assertTrue(
                all(
                    client.launch.arguments == ("-windowed", "-resolution", "1920x955")
                    for client in configured.clients
                )
            )
            self.assertTrue(Path(result.manager_backup_path).is_file())
            evidence = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
            self.assertEqual(2, evidence["slot_count"])
            self.assertEqual("4" * 64, evidence["baseline_tree_sha256"])

    def test_failed_second_copy_removes_new_deployment_and_preserves_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "client-manager.json"
            manifest_path.write_text(json.dumps(_manager_payload()), encoding="utf-8")
            original = manifest_path.read_bytes()
            frozen = root / "frozen"
            frozen.mkdir()
            extension = root / "wonderbane-extension.dll"
            extension.write_bytes(b"extension")
            deployment = root / "vanilla-failed"
            baseline = SimpleNamespace(
                directory=str(frozen),
                tree_sha256="4" * 64,
                repository_revision="abc123",
            )
            calls = 0

            def prepare(_baseline, destination, _manifest, _extension, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("disk full")
                destination = Path(destination)
                destination.mkdir()
                (destination / "sb.exe").write_bytes(b"patched")
                evidence = SimpleNamespace(
                    destination_directory=str(destination.resolve()),
                    working_tree_sha256="5" * 64,
                    result_executable_sha256="2" * 64,
                    extension_sha256="3" * 64,
                )
                return SimpleNamespace(destination_published=True, evidence=evidence)

            with (
                patch(
                    "shadowbane_lab.manager.runtime_deployment.verify_frozen_client_baseline",
                    return_value=baseline,
                ),
                patch(
                    "shadowbane_lab.manager.runtime_deployment.prepare_patched_client_copy",
                    side_effect=prepare,
                ),
            ):
                with self.assertRaisesRegex(RuntimeDeploymentError, "disk full"):
                    provision_isolated_client_runtimes(
                        manifest_path,
                        frozen,
                        deployment,
                        _patch_manifest(),
                        extension,
                        deployment_id="vanilla-failed",
                        slot_count=2,
                    )

            self.assertFalse(deployment.exists())
            self.assertEqual(original, manifest_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
