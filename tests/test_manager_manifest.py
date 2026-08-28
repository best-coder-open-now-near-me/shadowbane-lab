import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path, PureWindowsPath

from shadowbane_lab.manager.manifest import (
    MANAGER_MANIFEST_SCHEMA_VERSION,
    ClientLaunchConfig,
    ManagedClientConfig,
    ManagerManifest,
    ManagerManifestError,
    WindowTile,
    load_manager_manifest,
    loads_manager_manifest,
    parse_manager_manifest,
)


def _client(client_id: str = "client-01", *, left: int = 0) -> dict[str, object]:
    return {
        "client_id": client_id,
        "launch": {
            "executable": r"C:\Games\Shadowbane\Shadowbane.exe",
            "arguments": ["-windowed", "-resolution", "1280x720"],
            "working_directory": r"C:\Games\Shadowbane",
        },
        "expected_process_directory": r"C:\Games\Shadowbane\bin",
        "expected_executable_names": ["Shadowbane.exe", "sb.exe"],
        "window_tile": {"left": left, "top": 0, "width": 1280, "height": 720},
    }


def _payload(*clients: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "node_id": "gaming-pc-east",
        "clients": list(clients or (_client(),)),
    }


class ManagerManifestTests(unittest.TestCase):
    def test_parses_operational_topology_into_immutable_values(self) -> None:
        manifest = parse_manager_manifest(
            _payload(_client("client-01"), _client("client-02", left=1280))
        )

        self.assertEqual(MANAGER_MANIFEST_SCHEMA_VERSION, manifest.schema_version)
        self.assertEqual("gaming-pc-east", manifest.node_id)
        self.assertIsInstance(manifest.clients, tuple)
        self.assertEqual(("client-01", "client-02"), tuple(c.client_id for c in manifest.clients))
        first = manifest.clients[0]
        self.assertIsInstance(first.launch.executable, PureWindowsPath)
        self.assertEqual(
            (
                r"C:\Games\Shadowbane\Shadowbane.exe",
                "-windowed",
                "-resolution",
                "1280x720",
            ),
            first.launch.command,
        )
        self.assertEqual(
            (0, 0, 1280, 720),
            first.window_tile.assignment if first.window_tile else None,
        )
        with self.assertRaises(FrozenInstanceError):
            manifest.node_id = "another-node"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            first.launch.arguments = ()  # type: ignore[misc]

    def test_round_trips_to_plain_json_data_without_exposing_mutability(self) -> None:
        manifest = parse_manager_manifest(_payload())
        encoded = json.dumps(manifest.to_dict(), sort_keys=True)
        decoded = loads_manager_manifest(encoded)

        self.assertEqual(manifest, decoded)
        mutable_payload = manifest.to_dict()
        mutable_payload["clients"][0]["launch"]["arguments"].append("changed")
        self.assertEqual(
            ("-windowed", "-resolution", "1280x720"),
            manifest.clients[0].launch.arguments,
        )

    def test_loads_utf8_json_from_a_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manager.json"
            path.write_text(json.dumps(_payload()), encoding="utf-8")

            manifest = load_manager_manifest(path)

        self.assertEqual("gaming-pc-east", manifest.node_id)

    def test_rejects_unknown_fields_at_every_level(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        root = _payload()
        root["region"] = "east"
        cases.append(("manifest", root))
        client = _client()
        client["character"] = "Commander"
        cases.append(("client", _payload(client)))
        client = _client()
        client["launch"]["shell"] = True
        cases.append(("launch", _payload(client)))
        client = _client()
        client["window_tile"]["monitor"] = 1
        cases.append(("window_tile", _payload(client)))

        for label, payload in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ManagerManifestError, "unknown fields"):
                    parse_manager_manifest(payload)

    def test_rejects_credentials_character_identity_and_tactical_roles(self) -> None:
        forbidden_fields = {
            "account": "account@example.com",
            "password": "secret",
            "character_id": "character-1",
            "tactical_role": "caller",
        }
        for field, value in forbidden_fields.items():
            client = _client()
            client[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ManagerManifestError, "unknown fields"):
                    parse_manager_manifest(_payload(client))

        for argument in (
            "--password=secret",
            "/account:someone",
            "--character",
            "--role=caller",
            "tactical-role=healer",
        ):
            client = _client()
            client["launch"]["arguments"] = [argument]
            with self.subTest(argument=argument):
                with self.assertRaisesRegex(ManagerManifestError, "operational launch data"):
                    parse_manager_manifest(_payload(client))

    def test_requires_schema_version_one_and_all_required_fields(self) -> None:
        for version in (0, 2, True, "1"):
            payload = _payload()
            payload["schema_version"] = version
            with self.subTest(version=version):
                with self.assertRaisesRegex(ManagerManifestError, "schema_version"):
                    parse_manager_manifest(payload)

        for field in ("schema_version", "node_id", "clients"):
            payload = _payload()
            del payload[field]
            with self.subTest(field=field):
                with self.assertRaisesRegex(ManagerManifestError, "missing required"):
                    parse_manager_manifest(payload)

    def test_requires_safe_canonical_identifiers(self) -> None:
        for node_id in ("", " node", "node name", "node/one", "a" * 129):
            payload = _payload()
            payload["node_id"] = node_id
            with self.subTest(node_id=node_id):
                with self.assertRaisesRegex(ManagerManifestError, "node_id"):
                    parse_manager_manifest(payload)

        for client_id in ("", " client", "client one", "client/one"):
            with self.subTest(client_id=client_id):
                with self.assertRaisesRegex(ManagerManifestError, "client_id"):
                    parse_manager_manifest(_payload(_client(client_id)))

    def test_requires_absolute_canonical_windows_paths(self) -> None:
        fields = (
            ("launch", "executable"),
            ("launch", "working_directory"),
            (None, "expected_process_directory"),
        )
        for parent, field in fields:
            for value in (r"relative\game", r"C:drive-relative", r"C:\Games\..\Other"):
                client = _client()
                target = client[parent] if parent else client
                target[field] = value
                with self.subTest(parent=parent, field=field, value=value):
                    with self.assertRaisesRegex(ManagerManifestError, field):
                        parse_manager_manifest(_payload(client))

    def test_launch_arguments_must_be_separate_safe_tokens(self) -> None:
        for arguments in ("-windowed -resolution 1280x720", [""], ["bad\0value"], ["bad\nvalue"]):
            client = _client()
            client["launch"]["arguments"] = arguments
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ManagerManifestError, "arguments"):
                    parse_manager_manifest(_payload(client))

    def test_expected_executable_names_are_nonempty_basenames_and_unique(self) -> None:
        for names in ([], [r"bin\sb.exe"], ["sb.exe", "SB.EXE"], [" sb.exe"]):
            client = _client()
            client["expected_executable_names"] = names
            with self.subTest(names=names):
                with self.assertRaisesRegex(ManagerManifestError, "expected_executable_names"):
                    parse_manager_manifest(_payload(client))

    def test_rejects_duplicate_client_ids_and_tile_assignments(self) -> None:
        with self.assertRaisesRegex(ManagerManifestError, "client_id values"):
            parse_manager_manifest(_payload(_client("client-01"), _client("CLIENT-01", left=1280)))

        with self.assertRaisesRegex(ManagerManifestError, "window_tile assignments"):
            parse_manager_manifest(_payload(_client("client-01"), _client("client-02")))

    def test_window_tiles_allow_virtual_screen_offsets_but_require_positive_size(self) -> None:
        client = _client()
        client["window_tile"] = {"left": -1920, "top": -100, "width": 1920, "height": 1080}
        manifest = parse_manager_manifest(_payload(client))
        self.assertEqual((-1920, -100, 1920, 1080), manifest.clients[0].window_tile.assignment)

        for field, value in (
            ("width", 0),
            ("height", -1),
            ("left", True),
            ("top", 2**31),
        ):
            client = _client()
            client["window_tile"][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ManagerManifestError, field):
                    parse_manager_manifest(_payload(client))

    def test_rejects_duplicate_json_fields_and_nonstandard_constants(self) -> None:
        with self.assertRaisesRegex(ManagerManifestError, "duplicate field"):
            loads_manager_manifest(
                '{"schema_version":1,"schema_version":1,"node_id":"node","clients":[]}'
            )
        with self.assertRaisesRegex(ManagerManifestError, "not permitted"):
            loads_manager_manifest('{"schema_version":1,"node_id":"node","clients":NaN}')

    def test_direct_construction_preserves_the_same_immutable_contract(self) -> None:
        launch = ClientLaunchConfig(
            executable=PureWindowsPath(r"C:\Games\Shadowbane\Shadowbane.exe"),
            arguments=("-windowed",),
            working_directory=PureWindowsPath(r"C:\Games\Shadowbane"),
        )
        client = ManagedClientConfig(
            client_id="client-01",
            launch=launch,
            expected_process_directory=PureWindowsPath(r"C:\Games\Shadowbane\bin"),
            expected_executable_names=("sb.exe",),
            window_tile=WindowTile(left=0, top=0, width=800, height=600),
        )

        manifest = ManagerManifest(node_id="node-a", clients=(client,))

        self.assertEqual((client,), manifest.clients)
        with self.assertRaisesRegex(ManagerManifestError, "immutable tuple"):
            ManagerManifest(node_id="node-a", clients=[client])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
