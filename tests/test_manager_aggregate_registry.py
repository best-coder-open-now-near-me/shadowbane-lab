import unittest
from pathlib import PureWindowsPath
from unittest.mock import MagicMock, patch

from shadowbane_lab.client_input import WindowBounds, WindowSnapshot
from shadowbane_lab.manager.aggregate_registry import (
    AggregateRegistryConflictError,
    AggregateRegistryError,
    ManifestClientRegistryProvider,
)
from shadowbane_lab.manager.manifest import (
    ClientLaunchConfig,
    ManagedClientConfig,
    ManagerManifest,
)
from shadowbane_lab.manager.model import ClientRegistrySnapshot
from shadowbane_lab.manager.window_control import ClientRegistrySnapshotProvider

NODE_ID = "gaming-pc-east"
DIRECTORY_A = r"C:\Games\WonderBane-A"
DIRECTORY_B = r"D:\Games\WonderBane-B"


def _config(
    client_id: str,
    *,
    directory: str,
    executable_names: tuple[str, ...],
) -> ManagedClientConfig:
    return ManagedClientConfig(
        client_id=client_id,
        launch=ClientLaunchConfig(
            executable=PureWindowsPath(directory) / "launcher.exe",
            arguments=("--windowed",),
            working_directory=PureWindowsPath(directory),
        ),
        expected_process_directory=PureWindowsPath(directory),
        expected_executable_names=executable_names,
    )


def _manifest(*configs: ManagedClientConfig, node_id: str = NODE_ID) -> ManagerManifest:
    return ManagerManifest(node_id=node_id, clients=configs)


def _window(
    process_id: int,
    *,
    directory: str = DIRECTORY_A,
    executable_name: str = "sb.exe",
    window_handle: int | None = None,
    process_started_at_100ns: int | None = None,
    title: str | None = None,
) -> WindowSnapshot:
    return WindowSnapshot(
        executable_name=executable_name,
        executable_path=rf"{directory}\{executable_name}",
        title=title or f"Shadowbane {process_id}",
        client_bounds=WindowBounds(
            left=process_id,
            top=process_id + 1,
            width=1280,
            height=720,
        ),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
        process_id=process_id,
        window_handle=window_handle if window_handle is not None else process_id * 10,
        process_started_at_100ns=(
            process_started_at_100ns if process_started_at_100ns is not None else process_id * 1000
        ),
    )


class CountingInspector:
    def __init__(self, windows: tuple[WindowSnapshot, ...]) -> None:
        self.windows = windows
        self.inspection_count = 0

    def inspect_all(self) -> tuple[WindowSnapshot, ...]:
        self.inspection_count += 1
        return self.windows


class MalformedInspector:
    def inspect_all(self) -> object:
        return []


class ManifestClientRegistryProviderTests(unittest.TestCase):
    def test_unions_multiple_directories_and_names_from_one_underlying_scan(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe", "Shadowbane.exe"),
            ),
            _config(
                "slot-b",
                directory=DIRECTORY_B,
                executable_names=("sb.exe",),
            ),
        )
        first = _window(101, directory=DIRECTORY_A, executable_name="sb.exe")
        second = _window(
            202,
            directory=DIRECTORY_A,
            executable_name="Shadowbane.exe",
        )
        third = _window(303, directory=DIRECTORY_B, executable_name="sb.exe")
        unrelated = (
            _window(404, directory=DIRECTORY_A, executable_name="patcher.exe"),
            _window(505, directory=r"E:\Other", executable_name="sb.exe"),
        )
        inspector = CountingInspector((third, unrelated[0], first, unrelated[1], second))
        provider = ManifestClientRegistryProvider(inspector, manifest)

        result = provider.inspect()

        self.assertEqual(1, inspector.inspection_count)
        self.assertEqual(NODE_ID, result.node_id)
        self.assertEqual({101, 202, 303}, {client.process_id for client in result.clients})
        self.assertEqual((), result.rejected)
        self.assertNotIn(404, {client.process_id for client in result.clients})
        self.assertNotIn(505, {client.process_id for client in result.clients})
        self.assertIsInstance(provider, ClientRegistrySnapshotProvider)

    def test_overlapping_manifest_filters_do_not_duplicate_one_window(self) -> None:
        manifest = _manifest(
            _config(
                "wide-slot",
                directory=DIRECTORY_A,
                executable_names=("sb.exe", "Shadowbane.exe"),
            ),
            _config(
                "same-name-different-case",
                directory=r"c:\games\wonderbane-a",
                executable_names=("SB.EXE",),
            ),
            _config(
                "same-selector",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            ),
        )
        inspector = CountingInspector((_window(101),))

        result = ManifestClientRegistryProvider(inspector, manifest).inspect()

        self.assertEqual(1, inspector.inspection_count)
        self.assertEqual(1, len(result.clients))
        self.assertEqual(101, result.clients[0].process_id)

    def test_rejected_identities_are_preserved_in_the_union(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            )
        )
        accepted = _window(101)
        missing_handle = WindowSnapshot(
            executable_name="sb.exe",
            executable_path=rf"{DIRECTORY_A}\sb.exe",
            title="Missing HWND",
            client_bounds=WindowBounds(left=0, top=0, width=1280, height=720),
            dpi_scale=1.0,
            is_foreground=False,
            is_visible=True,
            process_id=202,
            process_started_at_100ns=202000,
        )
        result = ManifestClientRegistryProvider(
            CountingInspector((missing_handle, accepted)),
            manifest,
        ).inspect()

        self.assertEqual((101,), tuple(client.process_id for client in result.clients))
        self.assertEqual(1, len(result.rejected))
        self.assertEqual(202, result.rejected[0].process_id)
        self.assertIn("missing_window_handle", result.rejected[0].to_dict()["reasons"])

    def test_conflicting_process_or_window_identity_across_selectors_fails_closed(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            ),
            _config(
                "slot-b",
                directory=DIRECTORY_B,
                executable_names=("Shadowbane.exe",),
            ),
        )
        duplicate_process = (
            _window(101, directory=DIRECTORY_A, window_handle=1001),
            _window(
                101,
                directory=DIRECTORY_B,
                executable_name="Shadowbane.exe",
                window_handle=2002,
                process_started_at_100ns=999000,
            ),
        )
        duplicate_window = (
            _window(101, directory=DIRECTORY_A, window_handle=1001),
            _window(
                202,
                directory=DIRECTORY_B,
                executable_name="Shadowbane.exe",
                window_handle=1001,
            ),
        )

        for windows, message in (
            (duplicate_process, "process ID 101"),
            (duplicate_window, "window handle 1001"),
        ):
            with self.subTest(message=message):
                provider = ManifestClientRegistryProvider(CountingInspector(windows), manifest)
                with self.assertRaisesRegex(AggregateRegistryConflictError, message):
                    provider.inspect()

    def test_conflicting_instance_ids_across_selectors_fail_closed(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            ),
            _config(
                "slot-b",
                directory=DIRECTORY_B,
                executable_names=("Shadowbane.exe",),
            ),
        )
        windows = (
            _window(101, directory=DIRECTORY_A),
            _window(202, directory=DIRECTORY_B, executable_name="Shadowbane.exe"),
        )
        with patch(
            "shadowbane_lab.manager.registry.derive_client_instance_id",
            return_value="client-forced-collision",
        ):
            provider = ManifestClientRegistryProvider(CountingInspector(windows), manifest)
            with self.assertRaisesRegex(AggregateRegistryConflictError, "instance ID"):
                provider.inspect()

    def test_rejected_and_attachable_records_cannot_claim_the_same_process(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            ),
            _config(
                "slot-b",
                directory=DIRECTORY_B,
                executable_names=("Shadowbane.exe",),
            ),
        )
        accepted = _window(101, directory=DIRECTORY_A)
        rejected = WindowSnapshot(
            executable_name="Shadowbane.exe",
            executable_path=rf"{DIRECTORY_B}\Shadowbane.exe",
            title="Incomplete duplicate process",
            client_bounds=WindowBounds(left=0, top=0, width=1280, height=720),
            dpi_scale=1.0,
            is_foreground=False,
            is_visible=True,
            process_id=101,
            process_started_at_100ns=999000,
        )
        provider = ManifestClientRegistryProvider(
            CountingInspector((accepted, rejected)),
            manifest,
        )

        with self.assertRaisesRegex(AggregateRegistryConflictError, "process ID 101"):
            provider.inspect()

    def test_result_is_canonically_sorted_independent_of_manifest_and_scan_order(self) -> None:
        manifest = _manifest(
            _config(
                "slot-b",
                directory=DIRECTORY_B,
                executable_names=("Shadowbane.exe",),
            ),
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            ),
        )
        windows = (
            _window(303, directory=DIRECTORY_A),
            _window(101, directory=DIRECTORY_A),
            _window(202, directory=DIRECTORY_B, executable_name="Shadowbane.exe"),
        )

        result = ManifestClientRegistryProvider(CountingInspector(windows), manifest).inspect()

        self.assertEqual(
            (("sb.exe", 101), ("sb.exe", 303), ("Shadowbane.exe", 202)),
            tuple((client.executable_name, client.process_id) for client in result.clients),
        )
        self.assertEqual(
            result,
            ClientRegistrySnapshot(
                node_id=result.node_id,
                clients=result.clients,
                rejected=result.rejected,
            ),
        )

    def test_inconsistent_filtered_registry_node_fails_closed(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            )
        )
        filtered_registry = MagicMock()
        filtered_registry.inspect.return_value = ClientRegistrySnapshot(
            node_id="gaming-pc-west",
            clients=(),
        )
        with patch(
            "shadowbane_lab.manager.aggregate_registry.ClientWindowRegistry",
            return_value=filtered_registry,
        ):
            provider = ManifestClientRegistryProvider(CountingInspector(()), manifest)
            with self.assertRaisesRegex(AggregateRegistryError, "gaming-pc-west"):
                provider.inspect()

    def test_malformed_underlying_inspection_fails_closed(self) -> None:
        manifest = _manifest(
            _config(
                "slot-a",
                directory=DIRECTORY_A,
                executable_names=("sb.exe",),
            )
        )
        provider = ManifestClientRegistryProvider(MalformedInspector(), manifest)

        with self.assertRaisesRegex(AggregateRegistryError, "tuple"):
            provider.inspect()


if __name__ == "__main__":
    unittest.main()
