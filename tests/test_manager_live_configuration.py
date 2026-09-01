import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from shadowbane_lab.manager.dashboard import DashboardError
from shadowbane_lab.manager.live_configuration import (
    LiveConfiguredManagerApplication,
    replace_manager_manifest,
)
from shadowbane_lab.manager.manifest import load_manager_manifest, parse_manager_manifest


def _manifest_payload(*, node_id: str = "gaming-pc-east") -> dict[str, object]:
    return {
        "schema_version": 1,
        "node_id": node_id,
        "clients": [
            {
                "client_id": "client-01",
                "launch": {
                    "executable": r"C:\Games\Shadowbane\sb.exe",
                    "arguments": [],
                    "working_directory": r"C:\Games\Shadowbane",
                },
                "expected_process_directory": r"C:\Games\Shadowbane",
                "expected_executable_names": ["sb.exe"],
                "window_tile": {
                    "left": 0,
                    "top": 0,
                    "width": 1920,
                    "height": 955,
                },
            }
        ],
    }


class _FakeApplication:
    def __init__(self, manifest, open_instances: list[str]) -> None:
        self.manifest = manifest
        self.open_instances = open_instances
        self.bindings: dict[str, str] = {}
        self.execute_calls: list[tuple[str, str | None, str | None]] = []
        self.revocations: list[str] = []

    def status(self) -> dict[str, object]:
        bound_ids = set(self.bindings.values())
        candidates = [
            {"instance_id": instance_id}
            for instance_id in self.open_instances
            if instance_id not in bound_ids
        ]
        return {
            "ok": True,
            "node_id": self.manifest.node_id,
            "configured_count": len(self.manifest.clients),
            "bound_count": len(self.bindings),
            "slots": [
                {
                    "client_id": client.client_id,
                    "instance_id": self.bindings.get(client.client_id),
                    "binding": (
                        None
                        if client.client_id not in self.bindings
                        else {"instance_id": self.bindings[client.client_id]}
                    ),
                    "candidates": candidates,
                    "rejected_windows": [],
                }
                for client in self.manifest.clients
            ],
        }

    def reconcile_instances(self) -> dict[str, object]:
        bound_ids = set(self.bindings.values())
        free_ids = [
            client.client_id
            for client in self.manifest.clients
            if client.client_id not in self.bindings
        ]
        adopted: list[str] = []
        for instance_id in self.open_instances:
            if instance_id in bound_ids or not free_ids:
                continue
            client_id = free_ids.pop(0)
            self.bindings[client_id] = instance_id
            bound_ids.add(instance_id)
            adopted.append(client_id)
        return {
            "adopted_client_ids": adopted,
            "archived_client_ids": [],
            "issues": [],
        }

    def execute(
        self,
        action: str,
        *,
        client_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, object]:
        self.execute_calls.append((action, client_id, instance_id))
        if action == "attach":
            assert client_id is not None and instance_id is not None
            self.bindings[client_id] = instance_id
        elif action == "start":
            assert client_id is not None
            launched_id = f"launched-{len(self.open_instances) + 1}"
            self.open_instances.append(launched_id)
            self.bindings[client_id] = launched_id
        return {"ok": True, "action": action}

    def revoke_all_workers(self, *, reason: str) -> None:
        self.revocations.append(reason)


class _Factory:
    def __init__(self, *open_instances: str) -> None:
        self.open_instances = list(open_instances)
        self.applications: list[_FakeApplication] = []

    def __call__(self, manifest):
        application = _FakeApplication(manifest, self.open_instances)
        self.applications.append(application)
        return application


class _PreparedCapacity:
    def __init__(self, manifest, client_id: str) -> None:
        self.manifest = manifest
        self.client_id = client_id
        self.discarded = False

    def discard(self) -> None:
        self.discarded = True


class _CapacityProvisioner:
    def __init__(self) -> None:
        self.prepared: _PreparedCapacity | None = None

    def prepare(self, manifest):
        payload = manifest.to_dict()
        client = deepcopy(payload["clients"][0])
        client["client_id"] = "client-02"
        client["launch"]["executable"] = r"C:\Games\Shadowbane-02\sb.exe"
        client["launch"]["working_directory"] = r"C:\Games\Shadowbane-02"
        client["expected_process_directory"] = r"C:\Games\Shadowbane-02"
        payload["clients"].append(client)
        self.prepared = _PreparedCapacity(parse_manager_manifest(payload), "client-02")
        return self.prepared


class _InvalidCapacityProvisioner(_CapacityProvisioner):
    def prepare(self, manifest):
        prepared = super().prepare(manifest)
        prepared.client_id = "wrong-client"
        return prepared


class LiveConfiguredManagerApplicationTests(unittest.TestCase):
    def _application(self, directory: str, factory: _Factory):
        manifest_path = Path(directory) / "manager.json"
        manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
        application = LiveConfiguredManagerApplication(
            manifest_path,
            load_manager_manifest(manifest_path),
            factory,
        )
        return manifest_path, application

    def test_status_lists_only_open_instances_and_adopts_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = _Factory("existing-client")
            _, application = self._application(directory, factory)

            status = application.status()

            self.assertEqual(1, status["open_count"])
            self.assertEqual("existing-client", status["slots"][0]["instance_id"])
            self.assertEqual(["client-01"], status["reconciliation"]["adopted_client_ids"])

    def test_add_client_uses_free_internal_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = _Factory()
            manifest_path, application = self._application(directory, factory)

            result = application.execute("add-client")
            status = application.status()

            self.assertFalse(result["capacity_expanded"])
            self.assertEqual("client-01", result["client_id"])
            self.assertEqual(1, status["open_count"])
            self.assertEqual(1, len(load_manager_manifest(manifest_path).clients))

    def test_add_client_expands_capacity_and_preserves_live_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = _Factory("existing-client")
            manifest_path, application = self._application(directory, factory)
            application.status()

            result = application.execute("add-client")
            status = application.status()

            self.assertTrue(result["capacity_expanded"])
            self.assertEqual(2, status["open_count"])
            self.assertEqual(2, len(load_manager_manifest(manifest_path).clients))
            self.assertEqual("existing-client", factory.applications[1].bindings["client-01"])
            self.assertEqual([], factory.applications[0].revocations)
            self.assertEqual(1, len(tuple(Path(directory).glob("manager.before-slots-*.json"))))

    def test_status_grows_internal_capacity_for_manually_opened_clients(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = _Factory("client-a", "client-b")
            manifest_path, application = self._application(directory, factory)

            status = application.status()

            self.assertEqual(2, status["open_count"])
            self.assertEqual(2, len(load_manager_manifest(manifest_path).clients))
            self.assertEqual(
                {"client-a", "client-b"},
                {slot["instance_id"] for slot in status["slots"]},
            )

    def test_tileless_manifest_without_provisioner_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manager.json"
            payload = _manifest_payload()
            del payload["clients"][0]["window_tile"]
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            factory = _Factory("existing-client")
            application = LiveConfiguredManagerApplication(
                manifest_path,
                load_manager_manifest(manifest_path),
                factory,
            )

            status = application.status()

            self.assertFalse(status["can_add_client"])
            with self.assertRaisesRegex(DashboardError, "no live runtime provisioner"):
                application.execute("add-client")
            self.assertEqual(1, len(load_manager_manifest(manifest_path).clients))

    def test_add_client_provisions_isolated_capacity_and_preserves_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manager.json"
            payload = _manifest_payload()
            del payload["clients"][0]["window_tile"]
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            factory = _Factory("existing-client")
            provisioner = _CapacityProvisioner()
            application = LiveConfiguredManagerApplication(
                manifest_path,
                load_manager_manifest(manifest_path),
                factory,
                capacity_provisioner=provisioner,
            )

            self.assertTrue(application.status()["can_add_client"])
            result = application.execute("add-client")
            status = application.status()

            self.assertTrue(result["capacity_expanded"])
            self.assertTrue(result["runtime_provisioned"])
            self.assertEqual("client-02", result["client_id"])
            self.assertEqual(2, status["open_count"])
            self.assertEqual(2, len(load_manager_manifest(manifest_path).clients))
            self.assertEqual("existing-client", factory.applications[1].bindings["client-01"])
            self.assertIsNotNone(provisioner.prepared)
            self.assertFalse(provisioner.prepared.discarded)

    def test_failed_isolated_capacity_migration_discards_prepared_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manager.json"
            payload = _manifest_payload()
            del payload["clients"][0]["window_tile"]
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            provisioner = _InvalidCapacityProvisioner()
            application = LiveConfiguredManagerApplication(
                manifest_path,
                load_manager_manifest(manifest_path),
                _Factory("existing-client"),
                capacity_provisioner=provisioner,
            )

            with self.assertRaisesRegex(DashboardError, "could not be committed"):
                application.execute("add-client")

            self.assertIsNotNone(provisioner.prepared)
            self.assertTrue(provisioner.prepared.discarded)
            self.assertEqual(1, len(load_manager_manifest(manifest_path).clients))

    def test_delegates_normal_actions_to_current_immutable_application(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = _Factory()
            _, application = self._application(directory, factory)

            result = application.execute(
                "tile",
                client_id="client-01",
                instance_id="exact-client",
            )

            self.assertEqual("tile", result["action"])
            self.assertEqual(
                [("tile", "client-01", "exact-client")],
                factory.applications[0].execute_calls,
            )

    def test_manifest_replace_is_compare_and_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manager.json"
            manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
            expected = load_manager_manifest(manifest_path)
            manifest_path.write_text(
                json.dumps(_manifest_payload(node_id="changed-node")),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "changed after"):
                replace_manager_manifest(
                    manifest_path,
                    expected=expected,
                    replacement=expected,
                )

            self.assertEqual("changed-node", load_manager_manifest(manifest_path).node_id)


if __name__ == "__main__":
    unittest.main()
