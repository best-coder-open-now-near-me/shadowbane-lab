import unittest
from unittest.mock import MagicMock, patch

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager.manifest import parse_manager_manifest
from shadowbane_lab.manager.model import (
    ClientInstanceSnapshot,
    ClientRegistrySnapshot,
    RejectedWindowSnapshot,
    WindowRejectionReason,
)
from shadowbane_lab.manager.supervisor import (
    AmbiguousClientError,
    ClientInstanceSelector,
    ClientLifecycleSupervisor,
    DuplicateManagedClientError,
    InvalidLifecycleTransitionError,
    LaunchReceipt,
    LaunchTimeoutError,
    ManagedClientState,
    NoMatchingClientError,
    RegistryContractError,
    ReviewedLaunchCommand,
    StaleManagedClientError,
    SubprocessLauncher,
    SupervisorError,
    UnknownManagedClientError,
    UnsafeClientIdentityError,
    WindowControllerUnavailableError,
    launch_command_from_config,
    selector_from_config,
    window_rectangle_from_config,
)
from shadowbane_lab.manager.window_control import WindowRectangle

NODE_ID = "gaming-pc-east"
PROCESS_DIRECTORY = r"C:\Games\WonderBane"


def _selector(**changes: object) -> ClientInstanceSelector:
    values: dict[str, object] = {
        "node_id": NODE_ID,
        "executable_names": ("sb.exe",),
        "process_directory": PROCESS_DIRECTORY,
    }
    values.update(changes)
    return ClientInstanceSelector(**values)


def _client(
    process_id: int,
    *,
    instance_id: str | None = None,
    process_started_at_100ns: int | None = None,
    window_handle: int | None = None,
    node_id: str = NODE_ID,
    executable_name: str = "sb.exe",
    executable_path: str | None = None,
) -> ClientInstanceSnapshot:
    started_at = process_started_at_100ns or process_id * 1000
    handle = window_handle or process_id * 10
    return ClientInstanceSnapshot(
        node_id=node_id,
        instance_id=instance_id or f"client-{process_id}",
        process_id=process_id,
        process_started_at_100ns=started_at,
        window_handle=handle,
        executable_name=executable_name,
        executable_path=executable_path or rf"{PROCESS_DIRECTORY}\{executable_name}",
        title=f"Shadowbane {process_id}",
        client_bounds=WindowBounds(left=0, top=0, width=1280, height=720),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
    )


def _rejected() -> RejectedWindowSnapshot:
    return RejectedWindowSnapshot(
        node_id=NODE_ID,
        executable_name="sb.exe",
        executable_path=rf"{PROCESS_DIRECTORY}\sb.exe",
        title="Shadowbane unknown",
        client_bounds=WindowBounds(left=0, top=0, width=1280, height=720),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
        reasons=(WindowRejectionReason.MISSING_WINDOW_HANDLE,),
        process_id=777,
        process_started_at_100ns=777000,
    )


def _snapshot(
    *clients: ClientInstanceSnapshot,
    rejected: tuple[RejectedWindowSnapshot, ...] = (),
    node_id: str = NODE_ID,
) -> ClientRegistrySnapshot:
    ordered_clients = tuple(
        sorted(
            clients,
            key=lambda client: (
                client.node_id,
                client.executable_name.casefold(),
                client.process_id,
                client.process_started_at_100ns,
                client.window_handle,
                client.instance_id,
            ),
        )
    )
    return ClientRegistrySnapshot(
        node_id=node_id,
        clients=ordered_clients,
        rejected=rejected,
    )


class FakeRegistry:
    def __init__(self, snapshots: list[ClientRegistrySnapshot]) -> None:
        if not snapshots:
            raise ValueError("snapshots must not be empty")
        self.snapshots = list(snapshots)
        self.selectors: list[ClientInstanceSelector] = []

    def inspect(self, selector: ClientInstanceSelector) -> ClientRegistrySnapshot:
        self.selectors.append(selector)
        if len(self.snapshots) > 1:
            return self.snapshots.pop(0)
        return self.snapshots[0]


class FakeClock:
    def __init__(self, current: float = 10.0) -> None:
        self.current = current

    def now(self) -> float:
        return self.current


class AdvancingSleeper:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.current += seconds


class FakeLauncher:
    def __init__(self, process_id: int = 9000) -> None:
        self.receipt = LaunchReceipt(process_id=process_id)
        self.commands: list[ReviewedLaunchCommand] = []

    def launch(self, command: ReviewedLaunchCommand) -> LaunchReceipt:
        self.commands.append(command)
        return self.receipt


class FakeWindowController:
    def __init__(self, *, close_error: Exception | None = None) -> None:
        self.close_error = close_error
        self.close_requests: list[ClientInstanceSnapshot] = []
        self.tile_requests: list[tuple[ClientInstanceSnapshot, WindowRectangle]] = []

    def request_graceful_close(
        self,
        expected: ClientInstanceSnapshot,
    ) -> ClientInstanceSnapshot:
        self.close_requests.append(expected)
        if self.close_error is not None:
            raise self.close_error
        return expected

    def tile(
        self,
        expected: ClientInstanceSnapshot,
        rectangle: WindowRectangle,
    ) -> ClientInstanceSnapshot:
        self.tile_requests.append((expected, rectangle))
        return expected


def _supervisor(
    registry: FakeRegistry,
    *,
    launcher: FakeLauncher | None = None,
    clock: FakeClock | None = None,
    sleeper: AdvancingSleeper | None = None,
    controller: FakeWindowController | None = None,
) -> ClientLifecycleSupervisor:
    resolved_clock = clock or FakeClock()
    return ClientLifecycleSupervisor(
        registry,
        launcher=launcher or FakeLauncher(),
        clock=resolved_clock,
        sleeper=sleeper or AdvancingSleeper(resolved_clock),
        window_controller=controller,
    )


class SupervisorValueTests(unittest.TestCase):
    def test_selector_requires_exact_absolute_directory_and_file_name(self) -> None:
        invalid_changes = (
            {"node_id": " east"},
            {"executable_names": (r"bin\sb.exe",)},
            {"executable_names": ("sb.exe", "SB.EXE")},
            {"process_directory": "WonderBane"},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    _selector(**changes)

    def test_reviewed_command_requires_separate_nonempty_argv_tokens(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty tuple"):
            ReviewedLaunchCommand(())
        with self.assertRaisesRegex(ValueError, "without NUL"):
            ReviewedLaunchCommand((rf"{PROCESS_DIRECTORY}\sb.exe", "bad\0argument"))
        with self.assertRaisesRegex(ValueError, "absolute Windows path"):
            ReviewedLaunchCommand(("launcher.exe",))
        with self.assertRaisesRegex(ValueError, "working_directory"):
            ReviewedLaunchCommand(
                (rf"{PROCESS_DIRECTORY}\launcher.exe",),
                working_directory="relative",
            )

    def test_subprocess_launcher_never_uses_a_shell(self) -> None:
        process = MagicMock(pid=2468)
        process.poll.return_value = None
        command = ReviewedLaunchCommand(
            (r"C:\Games\WonderBane\sb.exe", "--windowed"),
            working_directory=PROCESS_DIRECTORY,
        )
        with patch(
            "shadowbane_lab.manager.supervisor.subprocess.Popen",
            return_value=process,
        ) as popen:
            receipt = SubprocessLauncher().launch(command)

        self.assertEqual(2468, receipt.process_id)
        popen.assert_called_once_with(
            command.argv,
            cwd=PROCESS_DIRECTORY,
            shell=False,
        )

    def test_manifest_slot_translates_without_tactical_or_machine_role_state(self) -> None:
        manifest = parse_manager_manifest(
            {
                "schema_version": 1,
                "node_id": NODE_ID,
                "clients": [
                    {
                        "client_id": "client-01",
                        "launch": {
                            "executable": rf"{PROCESS_DIRECTORY}\launcher.exe",
                            "arguments": ["-windowed"],
                            "working_directory": PROCESS_DIRECTORY,
                        },
                        "expected_process_directory": PROCESS_DIRECTORY,
                        "expected_executable_names": ["sb.exe", "Shadowbane.exe"],
                        "window_tile": {
                            "left": -960,
                            "top": 0,
                            "width": 960,
                            "height": 540,
                        },
                    }
                ],
            }
        )
        config = manifest.clients[0]

        selector = selector_from_config(manifest.node_id, config)
        command = launch_command_from_config(config)
        rectangle = window_rectangle_from_config(config)

        self.assertEqual(("sb.exe", "Shadowbane.exe"), selector.executable_names)
        self.assertEqual(
            (rf"{PROCESS_DIRECTORY}\launcher.exe", "-windowed"),
            command.argv,
        )
        self.assertEqual(
            WindowRectangle(left=-960, top=0, width=960, height=540),
            rectangle,
        )


class ClientLifecycleSupervisorTests(unittest.TestCase):
    def test_attach_binds_exactly_one_preexisting_client(self) -> None:
        client = _client(101)
        registry = FakeRegistry([_snapshot(client)])
        supervisor = _supervisor(registry)

        result = supervisor.attach(_selector())

        self.assertEqual(client, result.client)
        self.assertEqual(ManagedClientState.ATTACHED, result.state)
        self.assertTrue(result.dispatch_enabled)
        self.assertFalse(result.launched_by_manager)
        self.assertEqual([_selector()], registry.selectors)
        self.assertEqual((result,), supervisor.snapshots())

    def test_attach_fails_closed_on_zero_ambiguous_or_rejected_matches(self) -> None:
        cases = (
            (_snapshot(), NoMatchingClientError),
            (_snapshot(_client(101), _client(102)), AmbiguousClientError),
            (_snapshot(rejected=(_rejected(),)), UnsafeClientIdentityError),
        )
        for snapshot, error_type in cases:
            with self.subTest(error_type=error_type):
                supervisor = _supervisor(FakeRegistry([snapshot]))
                with self.assertRaises(error_type):
                    supervisor.attach(_selector())
                self.assertEqual((), supervisor.snapshots())

    def test_attach_can_select_an_exact_instance_from_identical_clients(self) -> None:
        first = _client(101)
        second = _client(202)
        supervisor = _supervisor(FakeRegistry([_snapshot(first, second)]))

        result = supervisor.attach(_selector(), instance_id=second.instance_id)

        self.assertEqual(second, result.client)
        self.assertEqual((result,), supervisor.snapshots())

    def test_attach_rejects_an_instance_outside_the_exact_selector(self) -> None:
        client = _client(101)
        supervisor = _supervisor(FakeRegistry([_snapshot(client)]))

        with self.assertRaises(NoMatchingClientError):
            supervisor.attach(_selector(), instance_id="client-elsewhere")

    def test_attach_defends_against_registry_filter_violations(self) -> None:
        wrong_executable = _client(101, executable_name="patcher.exe")
        supervisor = _supervisor(FakeRegistry([_snapshot(wrong_executable)]))

        with self.assertRaisesRegex(RegistryContractError, "executable filter"):
            supervisor.attach(_selector())

        wrong_directory = _client(
            102,
            executable_path=r"D:\Other\sb.exe",
        )
        supervisor = _supervisor(FakeRegistry([_snapshot(wrong_directory)]))
        with self.assertRaisesRegex(RegistryContractError, "directory filter"):
            supervisor.attach(_selector())

    def test_same_immutable_client_cannot_be_managed_twice(self) -> None:
        client = _client(101)
        supervisor = _supervisor(FakeRegistry([_snapshot(client)]))
        supervisor.attach(_selector())

        with self.assertRaises(DuplicateManagedClientError):
            supervisor.attach(_selector())

    def test_launch_attaches_only_the_single_new_identity(self) -> None:
        old_client = _client(101)
        new_client = _client(202)
        registry = FakeRegistry(
            [
                _snapshot(old_client),
                _snapshot(old_client),
                _snapshot(old_client, new_client),
            ]
        )
        clock = FakeClock()
        sleeper = AdvancingSleeper(clock)
        launcher = FakeLauncher(process_id=8080)
        supervisor = _supervisor(
            registry,
            launcher=launcher,
            clock=clock,
            sleeper=sleeper,
        )
        command = ReviewedLaunchCommand((r"C:\Games\WonderBane\launcher.exe", "--client"))

        result = supervisor.launch_and_attach(
            _selector(),
            command,
            timeout_seconds=2.0,
            poll_seconds=0.25,
        )

        self.assertEqual(new_client, result.client)
        self.assertTrue(result.launched_by_manager)
        self.assertEqual(8080, result.launcher_process_id)
        self.assertEqual([command], launcher.commands)
        self.assertEqual([0.25], sleeper.calls)

    def test_launch_fails_on_multiple_new_clients(self) -> None:
        old_client = _client(101)
        registry = FakeRegistry(
            [
                _snapshot(old_client),
                _snapshot(old_client, _client(202), _client(303)),
            ]
        )
        supervisor = _supervisor(registry)

        with self.assertRaisesRegex(AmbiguousClientError, "2 new"):
            supervisor.launch_and_attach(
                _selector(),
                ReviewedLaunchCommand((rf"{PROCESS_DIRECTORY}\launcher.exe",)),
                timeout_seconds=1.0,
            )
        self.assertEqual((), supervisor.snapshots())

    def test_launch_fails_when_a_baseline_identity_disappears(self) -> None:
        old_client = _client(101)
        registry = FakeRegistry([_snapshot(old_client), _snapshot(_client(202))])
        supervisor = _supervisor(registry)

        with self.assertRaisesRegex(StaleManagedClientError, "disappeared"):
            supervisor.launch_and_attach(
                _selector(),
                ReviewedLaunchCommand((rf"{PROCESS_DIRECTORY}\launcher.exe",)),
                timeout_seconds=1.0,
            )

    def test_launch_times_out_without_a_new_identity(self) -> None:
        baseline = _snapshot(_client(101))
        clock = FakeClock()
        sleeper = AdvancingSleeper(clock)
        supervisor = _supervisor(
            FakeRegistry([baseline]),
            clock=clock,
            sleeper=sleeper,
        )

        with self.assertRaises(LaunchTimeoutError):
            supervisor.launch_and_attach(
                _selector(),
                ReviewedLaunchCommand((rf"{PROCESS_DIRECTORY}\launcher.exe",)),
                timeout_seconds=0.5,
                poll_seconds=0.2,
            )

        self.assertEqual(3, len(sleeper.calls))
        self.assertAlmostEqual(0.2, sleeper.calls[0])
        self.assertAlmostEqual(0.2, sleeper.calls[1])
        self.assertAlmostEqual(0.1, sleeper.calls[2])

    def test_launch_refuses_incomplete_identity_before_starting_process(self) -> None:
        launcher = FakeLauncher()
        supervisor = _supervisor(
            FakeRegistry([_snapshot(rejected=(_rejected(),))]),
            launcher=launcher,
        )

        with self.assertRaises(UnsafeClientIdentityError):
            supervisor.launch_and_attach(
                _selector(),
                ReviewedLaunchCommand((rf"{PROCESS_DIRECTORY}\launcher.exe",)),
                timeout_seconds=1.0,
            )
        self.assertEqual([], launcher.commands)

    def test_pause_and_resume_only_gate_manager_dispatch(self) -> None:
        client = _client(101)
        launcher = FakeLauncher()
        controller = FakeWindowController()
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client)]),
            launcher=launcher,
            controller=controller,
        )
        attached = supervisor.attach(_selector())

        paused = supervisor.pause(attached.instance_id)
        resumed = supervisor.resume(attached.instance_id)

        self.assertEqual(ManagedClientState.PAUSED, paused.state)
        self.assertFalse(paused.dispatch_enabled)
        self.assertEqual(ManagedClientState.ATTACHED, resumed.state)
        self.assertTrue(resumed.dispatch_enabled)
        self.assertEqual([], launcher.commands)
        self.assertEqual([], controller.close_requests)

    def test_stale_refresh_permanently_disables_dispatch(self) -> None:
        client = _client(101)
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client), _snapshot()]),
        )
        attached = supervisor.attach(_selector())

        refreshed = supervisor.refresh(attached.instance_id)

        self.assertEqual(ManagedClientState.STALE, refreshed.state)
        self.assertFalse(refreshed.dispatch_enabled)
        with self.assertRaises(StaleManagedClientError):
            supervisor.resume(attached.instance_id)

    def test_dispatch_check_reverifies_and_fails_closed(self) -> None:
        client = _client(101)
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client), _snapshot()]),
        )
        attached = supervisor.attach(_selector())

        self.assertFalse(supervisor.dispatch_is_enabled(attached.instance_id))
        self.assertEqual(ManagedClientState.STALE, supervisor.status(attached.instance_id).state)

    def test_detach_forgets_binding_without_window_or_process_action(self) -> None:
        client = _client(101)
        launcher = FakeLauncher()
        controller = FakeWindowController()
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client)]),
            launcher=launcher,
            controller=controller,
        )
        attached = supervisor.attach(_selector())

        detached = supervisor.detach(attached.instance_id)

        self.assertEqual(ManagedClientState.DETACHED, detached.state)
        self.assertFalse(detached.dispatch_enabled)
        self.assertEqual([], launcher.commands)
        self.assertEqual([], controller.close_requests)
        self.assertEqual((), supervisor.snapshots())
        with self.assertRaises(UnknownManagedClientError):
            supervisor.status(attached.instance_id)

    def test_request_close_uses_graceful_window_controller_and_disables_dispatch(self) -> None:
        client = _client(101)
        controller = FakeWindowController()
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client)]),
            controller=controller,
        )
        attached = supervisor.attach(_selector())

        result = supervisor.request_close(attached.instance_id)

        self.assertEqual([client], controller.close_requests)
        self.assertEqual(ManagedClientState.CLOSE_REQUESTED, result.state)
        self.assertFalse(result.dispatch_enabled)
        with self.assertRaises(InvalidLifecycleTransitionError):
            supervisor.resume(attached.instance_id)

    def test_failed_close_request_leaves_dispatch_paused(self) -> None:
        client = _client(101)
        controller = FakeWindowController(close_error=OSError("window rejected close"))
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client)]),
            controller=controller,
        )
        attached = supervisor.attach(_selector())

        with self.assertRaisesRegex(SupervisorError, "close request failed"):
            supervisor.request_close(attached.instance_id)

        status = supervisor.status(attached.instance_id)
        self.assertEqual(ManagedClientState.PAUSED, status.state)
        self.assertFalse(status.dispatch_enabled)

    def test_window_operations_require_a_controller(self) -> None:
        client = _client(101)
        supervisor = _supervisor(FakeRegistry([_snapshot(client)]))
        attached = supervisor.attach(_selector())

        with self.assertRaises(WindowControllerUnavailableError):
            supervisor.request_close(attached.instance_id)
        with self.assertRaises(WindowControllerUnavailableError):
            supervisor.tile(
                attached.instance_id,
                WindowRectangle(left=0, top=0, width=800, height=600),
            )

    def test_tile_passes_verified_identity_and_explicit_rectangle(self) -> None:
        client = _client(101)
        controller = FakeWindowController()
        registry = FakeRegistry([_snapshot(client)])
        supervisor = _supervisor(registry, controller=controller)
        binding = supervisor.attach(_selector())
        rectangle = WindowRectangle(left=-960, top=0, width=960, height=540)

        result = supervisor.tile(binding.instance_id, rectangle)

        self.assertEqual([(client, rectangle)], controller.tile_requests)
        self.assertEqual(binding.instance_id, result.instance_id)

    def test_close_request_cannot_be_repeated(self) -> None:
        client = _client(101)
        controller = FakeWindowController()
        supervisor = _supervisor(
            FakeRegistry([_snapshot(client)]),
            controller=controller,
        )
        attached = supervisor.attach(_selector())
        supervisor.request_close(attached.instance_id)

        with self.assertRaises(InvalidLifecycleTransitionError):
            supervisor.request_close(attached.instance_id)


if __name__ == "__main__":
    unittest.main()
