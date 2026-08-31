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
    expand_manager_slots,
    load_manager_manifest,
    loads_manager_manifest,
    parse_manager_manifest,
    retarget_manager_client_directories,
    retarget_manager_clients,
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
    def test_retargets_every_slot_to_a_unique_full_size_runtime(self) -> None:
        original = parse_manager_manifest(
            _payload(_client("client-01"), _client("client-02", left=1280))
        )

        retargeted = retarget_manager_client_directories(
            original,
            {
                "client-01": PureWindowsPath(r"C:\Runtimes\deployment-01\client-01"),
                "client-02": PureWindowsPath(r"C:\Runtimes\deployment-01\client-02"),
            },
            resolution_width=1920,
            resolution_height=955,
        )

        self.assertEqual((None, None), tuple(client.window_tile for client in retargeted.clients))
        self.assertEqual(
            (
                PureWindowsPath(r"C:\Runtimes\deployment-01\client-01"),
                PureWindowsPath(r"C:\Runtimes\deployment-01\client-02"),
            ),
            tuple(client.launch.working_directory for client in retargeted.clients),
        )
        self.assertTrue(
            all(
                client.launch.arguments == ("-windowed", "-resolution", "1920x955")
                for client in retargeted.clients
            )
        )

    def test_isolated_runtime_retarget_rejects_missing_or_shared_directories(self) -> None:
        original = parse_manager_manifest(
            _payload(_client("client-01"), _client("client-02", left=1280))
        )

        with self.assertRaisesRegex(ManagerManifestError, "cover every manager slot"):
            retarget_manager_client_directories(
                original,
                {"client-01": PureWindowsPath(r"C:\Runtimes\client-01")},
            )
        with self.assertRaisesRegex(ManagerManifestError, "must be unique"):
            retarget_manager_client_directories(
                original,
                {
                    "client-01": PureWindowsPath(r"C:\Runtimes\shared"),
                    "client-02": PureWindowsPath(r"C:\Runtimes\SHARED"),
                },
            )

    def test_retargets_every_slot_without_changing_operational_ownership(self) -> None:
        original = parse_manager_manifest(
            _payload(_client("client-01"), _client("client-02", left=1280))
        )

        retargeted = retarget_manager_clients(
            original,
            PureWindowsPath(r"C:\Reviewed\WonderBane-1.0.5"),
            executable_name="sb.exe",
        )

        self.assertEqual(original.node_id, retargeted.node_id)
        self.assertEqual(
            tuple(client.client_id for client in original.clients),
            tuple(client.client_id for client in retargeted.clients),
        )
        self.assertEqual(
            tuple(client.window_tile for client in original.clients),
            tuple(client.window_tile for client in retargeted.clients),
        )
        for before, after in zip(original.clients, retargeted.clients, strict=True):
            self.assertEqual(before.launch.arguments, after.launch.arguments)
            self.assertEqual(before.launch.environment, after.launch.environment)
            self.assertEqual(
                PureWindowsPath(r"C:\Reviewed\WonderBane-1.0.5\sb.exe"),
                after.launch.executable,
            )
            self.assertEqual(("sb.exe",), after.expected_executable_names)

    def test_expands_reviewed_slots_and_retiles_without_mutating_launch_config(self) -> None:
        original = parse_manager_manifest(_payload())

        expanded = expand_manager_slots(
            original,
            4,
            display_width=1920,
            display_height=955,
        )

        self.assertEqual(1, len(original.clients))
        self.assertEqual(
            ("client-01", "client-02", "client-03", "client-04"),
            tuple(client.client_id for client in expanded.clients),
        )
        self.assertTrue(
            all(client.launch == original.clients[0].launch for client in expanded.clients)
        )
        self.assertEqual(
            (
                (0, 0, 960, 477),
                (960, 0, 960, 477),
                (0, 477, 960, 478),
                (960, 477, 960, 478),
            ),
            tuple(client.window_tile.assignment for client in expanded.clients),
        )

    def test_slot_expansion_preserves_existing_ids_and_rejects_shrink(self) -> None:
        manifest = parse_manager_manifest(_payload(_client("primary")))

        expanded = expand_manager_slots(manifest, 3)

        self.assertEqual(
            ("primary", "client-01", "client-02"),
            tuple(client.client_id for client in expanded.clients),
        )
        with self.assertRaisesRegex(ManagerManifestError, "cannot shrink"):
            expand_manager_slots(expanded, 2)

    def test_slot_expansion_preserves_virtual_display_origin(self) -> None:
        manifest = parse_manager_manifest(_payload())

        expanded = expand_manager_slots(
            manifest,
            2,
            display_left=-1920,
            display_top=-40,
            display_width=1920,
            display_height=1000,
        )

        self.assertEqual(
            ((-1920, -40, 960, 1000), (-960, -40, 960, 1000)),
            tuple(client.window_tile.assignment for client in expanded.clients),
        )

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
            "plaintext-password",
            "--password=secret",
            "--auth-token=secret",
            "--pass-word",
            "/account:someone",
            "--character",
            "--role=caller",
            "tactical-role=healer",
        ):
            client = _client()
            client["launch"]["arguments"] = [argument]
            with self.subTest(argument=argument):
                with self.assertRaisesRegex(ManagerManifestError, "not an allowed operational"):
                    parse_manager_manifest(_payload(client))

    def test_accepts_only_the_documented_operational_launch_grammar(self) -> None:
        accepted = (
            [],
            ["-windowed"],
            ["--windowed"],
            ["--client"],
            ["--client", "-windowed", "-resolution", "1920x1080"],
            ["-resolution", "1x16384", "--windowed", "--client"],
        )
        for arguments in accepted:
            client = _client()
            client["launch"]["arguments"] = arguments
            with self.subTest(arguments=arguments):
                parsed = parse_manager_manifest(_payload(client))
                self.assertEqual(tuple(arguments), parsed.clients[0].launch.arguments)

    def test_accepts_only_reviewed_legacy_renderer_environment(self) -> None:
        client = _client()
        client["launch"]["environment"] = {
            "LIBGL_ALWAYS_SOFTWARE": "true",
            "GALLIUM_DRIVER": "llvmpipe",
            "MESA_EXTENSION_MAX_YEAR": "2001",
            "MESA_GL_VERSION_OVERRIDE": None,
            "MESA_GLSL_VERSION_OVERRIDE": None,
        }

        manifest = parse_manager_manifest(_payload(client))

        self.assertEqual(
            (
                ("GALLIUM_DRIVER", "llvmpipe"),
                ("LIBGL_ALWAYS_SOFTWARE", "true"),
                ("MESA_EXTENSION_MAX_YEAR", "2001"),
                ("MESA_GLSL_VERSION_OVERRIDE", None),
                ("MESA_GL_VERSION_OVERRIDE", None),
            ),
            manifest.clients[0].launch.environment,
        )
        self.assertEqual(
            client["launch"]["environment"],
            manifest.to_dict()["clients"][0]["launch"]["environment"],
        )

        rejected = (
            {"PATH": r"C:\unreviewed"},
            {"ACCOUNT_TOKEN": "secret"},
            {"GALLIUM_DRIVER": "hardware"},
            {"LIBGL_ALWAYS_SOFTWARE": True},
            {"MESA_EXTENSION_MAX_YEAR": "2026"},
            {"MESA_GL_VERSION_OVERRIDE": "4.6"},
        )
        for environment in rejected:
            client = _client()
            client["launch"]["environment"] = environment
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(
                    ManagerManifestError,
                    "unsupported variable|must be one of",
                ):
                    parse_manager_manifest(_payload(client))

    def test_rejects_unknown_launch_flags_aliases_and_positional_values(self) -> None:
        rejected = (
            ["--fullscreen"],
            ["-Windowed"],
            ["/windowed"],
            ["windowed"],
            ["--resolution", "1920x1080"],
            ["-resolution=1920x1080"],
            ["--client-mode"],
            ["launcher-profile.json"],
        )
        for arguments in rejected:
            client = _client()
            client["launch"]["arguments"] = arguments
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ManagerManifestError, "not an allowed operational"):
                    parse_manager_manifest(_payload(client))

    def test_resolution_argument_is_canonical_bounded_and_complete(self) -> None:
        rejected = (
            ["-resolution"],
            ["-resolution", "0x720"],
            ["-resolution", "001x720"],
            ["-resolution", "1920X1080"],
            ["-resolution", "1920*1080"],
            ["-resolution", "16385x720"],
            ["-resolution", 1080],
        )
        for arguments in rejected:
            client = _client()
            client["launch"]["arguments"] = arguments
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(
                    ManagerManifestError,
                    "following WIDTHxHEIGHT|display resolution|dimensions|non-empty string",
                ):
                    parse_manager_manifest(_payload(client))

    def test_launch_options_cannot_be_repeated_or_aliased_twice(self) -> None:
        for arguments in (
            ["-windowed", "-windowed"],
            ["-windowed", "--windowed"],
            ["--client", "--client"],
            ["-resolution", "1280x720", "-resolution", "1920x1080"],
        ):
            client = _client()
            client["launch"]["arguments"] = arguments
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ManagerManifestError, "duplicates launch option"):
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
        with self.assertRaisesRegex(ManagerManifestError, "name/value pairs"):
            ClientLaunchConfig(
                executable=launch.executable,
                arguments=(),
                working_directory=launch.working_directory,
                environment=(("GALLIUM_DRIVER",),),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ManagerManifestError, "must be unique"):
            ClientLaunchConfig(
                executable=launch.executable,
                arguments=(),
                working_directory=launch.working_directory,
                environment=(
                    ("GALLIUM_DRIVER", "llvmpipe"),
                    ("GALLIUM_DRIVER", "llvmpipe"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
