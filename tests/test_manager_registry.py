import json
import unittest
from dataclasses import replace

from shadowbane_lab.client_input import (
    StaticVisibleWindowInspector,
    WindowBounds,
    WindowSnapshot,
)
from shadowbane_lab.manager import (
    ClientWindowRegistry,
    DuplicateClientIdentityError,
    WindowRejectionReason,
    derive_client_instance_id,
)


def _snapshot(
    *,
    process_id: int | None = 101,
    window_handle: int | None = 1001,
    process_started_at_100ns: int | None = 133_700_000_000_000_000,
    executable_name: str = "sb.exe",
    executable_path: str | None = r"C:\Games\Shadowbane\sb.exe",
    title: str = "Shadowbane",
    left: int = 10,
) -> WindowSnapshot:
    return WindowSnapshot(
        executable_name=executable_name,
        executable_path=executable_path,
        title=title,
        client_bounds=WindowBounds(left=left, top=20, width=1280, height=720),
        dpi_scale=1.25,
        is_foreground=False,
        is_visible=True,
        process_id=process_id,
        window_handle=window_handle,
        process_started_at_100ns=process_started_at_100ns,
    )


class ClientWindowRegistryTests(unittest.TestCase):
    def test_requires_an_explicit_discovery_filter(self) -> None:
        inspector = StaticVisibleWindowInspector(())

        with self.assertRaisesRegex(ValueError, "at least one"):
            ClientWindowRegistry(inspector, node_id="gaming-pc-east")

    def test_requires_a_canonical_node_id(self) -> None:
        inspector = StaticVisibleWindowInspector(())

        for node_id in ("", "  ", " gaming-pc-east", "gaming-pc-east\0spoof"):
            with self.subTest(node_id=node_id):
                with self.assertRaisesRegex(ValueError, "node_id"):
                    ClientWindowRegistry(
                        inspector,
                        node_id=node_id,
                        executable_names=("sb.exe",),
                    )

    def test_validates_filter_values(self) -> None:
        inspector = StaticVisibleWindowInspector(())

        for executable_names in ("sb.exe", (" sb.exe",), (r"bin\sb.exe",)):
            with self.subTest(executable_names=executable_names):
                with self.assertRaisesRegex(ValueError, "executable_names"):
                    ClientWindowRegistry(
                        inspector,
                        node_id="gaming-pc-east",
                        executable_names=executable_names,
                    )
        with self.assertRaisesRegex(ValueError, "process_directory"):
            ClientWindowRegistry(
                inspector,
                node_id="gaming-pc-east",
                process_directory=42,
            )

    def test_filters_names_case_insensitively(self) -> None:
        client = _snapshot(executable_name="SB.EXE")
        other = _snapshot(
            process_id=202,
            window_handle=2002,
            process_started_at_100ns=133_700_000_000_000_001,
            executable_name="patcher.exe",
            executable_path=r"C:\Games\Shadowbane\patcher.exe",
        )
        inspector = StaticVisibleWindowInspector((other, client))

        result = ClientWindowRegistry(
            inspector,
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        ).inspect()

        self.assertEqual((101,), tuple(item.process_id for item in result.clients))
        self.assertEqual(1, inspector.inspection_count)

    def test_process_directory_is_exact_and_both_filters_must_match(self) -> None:
        exact = _snapshot(executable_name="SB.EXE")
        nested = _snapshot(
            process_id=202,
            window_handle=2002,
            process_started_at_100ns=133_700_000_000_000_001,
            executable_path=r"C:\Games\Shadowbane\Copy\sb.exe",
        )
        wrong_name = _snapshot(
            process_id=303,
            window_handle=3003,
            process_started_at_100ns=133_700_000_000_000_002,
            executable_name="patcher.exe",
            executable_path=r"c:/games/shadowbane/patcher.exe",
        )
        inspector = StaticVisibleWindowInspector((nested, wrong_name, exact))

        result = ClientWindowRegistry(
            inspector,
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
            process_directory=r"c:/GAMES/shadowbane/.",
        ).inspect()

        self.assertEqual((101,), tuple(item.process_id for item in result.clients))
        self.assertEqual((), result.rejected)

    def test_directory_filter_rejects_windows_without_an_executable_path(self) -> None:
        inspector = StaticVisibleWindowInspector((_snapshot(executable_path=None),))

        result = ClientWindowRegistry(
            inspector,
            node_id="gaming-pc-east",
            process_directory=r"C:\Games\Shadowbane",
        ).inspect()

        self.assertEqual((), result.clients)
        self.assertEqual((), result.rejected)

    def test_missing_lifetime_identity_is_reported_but_not_attachable(self) -> None:
        missing_pid = _snapshot(process_id=None)
        missing_window = _snapshot(
            process_id=202,
            window_handle=None,
            process_started_at_100ns=133_700_000_000_000_001,
            left=30,
        )
        missing_start = _snapshot(
            process_id=303,
            window_handle=3003,
            process_started_at_100ns=None,
            left=50,
        )
        inspector = StaticVisibleWindowInspector((missing_start, missing_window, missing_pid))

        result = ClientWindowRegistry(
            inspector,
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        ).inspect()

        self.assertEqual((), result.clients)
        rejected_by_pid = {window.process_id: window for window in result.rejected}
        self.assertEqual(
            (WindowRejectionReason.MISSING_PROCESS_ID,),
            rejected_by_pid[None].reasons,
        )
        self.assertEqual(
            (WindowRejectionReason.MISSING_WINDOW_HANDLE,),
            rejected_by_pid[202].reasons,
        )
        self.assertEqual(
            (WindowRejectionReason.MISSING_PROCESS_START_TIME,),
            rejected_by_pid[303].reasons,
        )
        self.assertEqual(
            {"gaming-pc-east"},
            {window.node_id for window in result.rejected},
        )

    def test_instance_id_is_stable_and_globally_scoped_to_node_and_window(self) -> None:
        original = _snapshot(title="First title", left=10)
        moved_and_renamed = replace(
            original,
            title="Renamed title",
            client_bounds=WindowBounds(left=900, top=300, width=1280, height=720),
        )
        recreated_window = replace(original, window_handle=9999)
        reused_pid = replace(
            original,
            process_started_at_100ns=original.process_started_at_100ns + 1,
        )

        original_id = ClientWindowRegistry(
            StaticVisibleWindowInspector((original,)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        ).inspect().clients[0].instance_id
        renamed_id = ClientWindowRegistry(
            StaticVisibleWindowInspector((moved_and_renamed,)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        ).inspect().clients[0].instance_id
        recreated_window_id = ClientWindowRegistry(
            StaticVisibleWindowInspector((recreated_window,)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        ).inspect().clients[0].instance_id
        reused_id = ClientWindowRegistry(
            StaticVisibleWindowInspector((reused_pid,)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        ).inspect().clients[0].instance_id
        other_node_id = ClientWindowRegistry(
            StaticVisibleWindowInspector((original,)),
            node_id="gaming-pc-west",
            executable_names=("sb.exe",),
        ).inspect().clients[0].instance_id

        self.assertEqual(original_id, renamed_id)
        self.assertNotEqual(original_id, recreated_window_id)
        self.assertNotEqual(original_id, reused_id)
        self.assertNotEqual(original_id, other_node_id)
        self.assertEqual(
            original_id,
            derive_client_instance_id(
                "gaming-pc-east",
                original.process_id,
                original.process_started_at_100ns,
                original.window_handle,
            ),
        )

    def test_duplicate_process_id_is_rejected(self) -> None:
        first = _snapshot()
        second = replace(
            first,
            window_handle=2002,
            process_started_at_100ns=first.process_started_at_100ns + 1,
        )
        registry = ClientWindowRegistry(
            StaticVisibleWindowInspector((first, second)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        )

        with self.assertRaisesRegex(DuplicateClientIdentityError, "process ID 101"):
            registry.inspect()

    def test_duplicate_window_handle_is_rejected(self) -> None:
        first = _snapshot()
        second = replace(
            first,
            process_id=202,
            process_started_at_100ns=first.process_started_at_100ns + 1,
        )
        registry = ClientWindowRegistry(
            StaticVisibleWindowInspector((first, second)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        )

        with self.assertRaisesRegex(DuplicateClientIdentityError, "window handle 1001"):
            registry.inspect()

    def test_duplicate_identity_is_rejected_even_if_one_window_is_unattachable(self) -> None:
        attachable = _snapshot()
        unattachable = replace(attachable, window_handle=None)
        registry = ClientWindowRegistry(
            StaticVisibleWindowInspector((attachable, unattachable)),
            node_id="gaming-pc-east",
            executable_names=("sb.exe",),
        )

        with self.assertRaisesRegex(DuplicateClientIdentityError, "process ID 101"):
            registry.inspect()

    def test_snapshot_and_payload_are_canonically_sorted(self) -> None:
        later = _snapshot(
            process_id=400,
            window_handle=4000,
            process_started_at_100ns=133_700_000_000_000_004,
            executable_name="z-client.exe",
            executable_path=r"C:\Games\Shadowbane\z-client.exe",
        )
        second = _snapshot(
            process_id=200,
            window_handle=2000,
            process_started_at_100ns=133_700_000_000_000_002,
        )
        first = _snapshot(
            process_id=100,
            window_handle=1000,
            process_started_at_100ns=133_700_000_000_000_001,
        )
        registry = ClientWindowRegistry(
            StaticVisibleWindowInspector((later, second, first)),
            node_id="gaming-pc-east",
            executable_names=("z-client.exe", "sb.exe"),
        )

        result = registry.inspect()
        payload = result.as_dict()

        self.assertEqual((100, 200, 400), tuple(client.process_id for client in result.clients))
        self.assertEqual([100, 200, 400], [client["process_id"] for client in payload["clients"]])
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("gaming-pc-east", payload["node_id"])
        self.assertEqual(
            {"gaming-pc-east"},
            {client["node_id"] for client in payload["clients"]},
        )
        self.assertEqual([], payload["rejected"])
        self.assertEqual(payload, json.loads(json.dumps(payload, sort_keys=True)))
        self.assertEqual(payload, result.to_dict())


if __name__ == "__main__":
    unittest.main()
