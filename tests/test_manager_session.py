import json
import unittest
from dataclasses import FrozenInstanceError, replace

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager.manifest import ManagerManifest, parse_manager_manifest
from shadowbane_lab.manager.model import ClientInstanceSnapshot
from shadowbane_lab.manager.session import (
    ManagerSession,
    ManagerSessionSnapshot,
    ManagerSlotSnapshot,
    ManagerSlotState,
    SessionActionError,
    SessionSlotBoundError,
    SessionSlotUnboundError,
)
from shadowbane_lab.manager.supervisor import (
    ClientInstanceSelector,
    LaunchProvenance,
    ManagedClientSnapshot,
    ManagedClientState,
    ReviewedLaunchCommand,
    selector_from_config,
)
from shadowbane_lab.manager.window_control import WindowRectangle

NODE_ID = "gaming-pc-east"
PROCESS_DIRECTORY = r"C:\Games\Shadowbane\bin"


def _client_config(
    client_id: str,
    *,
    left: int | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "client_id": client_id,
        "launch": {
            "executable": r"C:\Games\Shadowbane\launcher.exe",
            "arguments": ["-windowed"],
            "working_directory": r"C:\Games\Shadowbane",
        },
        "expected_process_directory": PROCESS_DIRECTORY,
        "expected_executable_names": ["sb.exe"],
    }
    if left is not None:
        payload["window_tile"] = {
            "left": left,
            "top": 0,
            "width": 800,
            "height": 600,
        }
    return payload


def _manifest() -> ManagerManifest:
    return parse_manager_manifest(
        {
            "schema_version": 1,
            "node_id": NODE_ID,
            "clients": [
                _client_config("client-01", left=0),
                _client_config("client-02", left=800),
                _client_config("client-03", left=None),
            ],
        }
    )


def _instance(instance_id: str, process_id: int) -> ClientInstanceSnapshot:
    return ClientInstanceSnapshot(
        node_id=NODE_ID,
        instance_id=instance_id,
        process_id=process_id,
        process_started_at_100ns=133_700_000_000_000_000 + process_id,
        window_handle=10_000 + process_id,
        executable_name="sb.exe",
        executable_path=rf"{PROCESS_DIRECTORY}\sb.exe",
        title=f"Shadowbane {process_id}",
        client_bounds=WindowBounds(left=0, top=0, width=800, height=600),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
    )


def _managed(
    selector: ClientInstanceSelector,
    instance_id: str,
    process_id: int,
    *,
    state: ManagedClientState = ManagedClientState.ATTACHED,
    launched: bool = True,
    detail: str | None = None,
) -> ManagedClientSnapshot:
    return ManagedClientSnapshot(
        selector=selector,
        client=_instance(instance_id, process_id),
        state=state,
        dispatch_enabled=state is ManagedClientState.ATTACHED,
        launched_by_manager=launched,
        launcher_process_id=9000 + process_id if launched else None,
        launcher_process_started_at_100ns=(
            133_700_000_000_000_000 + process_id - 1 if launched else None
        ),
        launch_provenance=(LaunchProvenance.DESCENDANT_PROCESS if launched else None),
        attached_at=10.0,
        last_verified_at=11.0,
        status_detail=detail,
    )


class FakeSupervisor:
    def __init__(self) -> None:
        self.start_outcomes: list[ManagedClientSnapshot | Exception] = []
        self.attach_results: dict[str, ManagedClientSnapshot] = {}
        self.refresh_outcomes: dict[str, list[ManagedClientSnapshot | Exception]] = {}
        self.statuses: dict[str, ManagedClientSnapshot] = {}
        self.close_error: Exception | None = None
        self.start_calls: list[
            tuple[ClientInstanceSelector, ReviewedLaunchCommand, float, float]
        ] = []
        self.attach_calls: list[tuple[ClientInstanceSelector, str | None]] = []
        self.refresh_calls: list[str] = []
        self.pause_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.detach_calls: list[str] = []
        self.close_calls: list[str] = []
        self.tile_calls: list[tuple[str, WindowRectangle]] = []

    def launch_and_attach(
        self,
        selector: ClientInstanceSelector,
        command: ReviewedLaunchCommand,
        *,
        timeout_seconds: float,
        poll_seconds: float = 0.5,
    ) -> ManagedClientSnapshot:
        self.start_calls.append((selector, command, timeout_seconds, poll_seconds))
        if not self.start_outcomes:
            raise AssertionError("no fake start outcome")
        outcome = self.start_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        self.statuses[outcome.instance_id] = outcome
        return outcome

    def attach(
        self,
        selector: ClientInstanceSelector,
        *,
        instance_id: str | None = None,
    ) -> ManagedClientSnapshot:
        self.attach_calls.append((selector, instance_id))
        if instance_id is None or instance_id not in self.attach_results:
            raise RuntimeError("selected instance was not registered")
        result = self.attach_results[instance_id]
        self.statuses[result.instance_id] = result
        return result

    def refresh(self, instance_id: str) -> ManagedClientSnapshot:
        self.refresh_calls.append(instance_id)
        outcomes = self.refresh_outcomes.get(instance_id)
        if outcomes:
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            self.statuses[instance_id] = outcome
            return outcome
        return self.status(instance_id)

    def status(self, instance_id: str) -> ManagedClientSnapshot:
        try:
            return self.statuses[instance_id]
        except KeyError as exc:
            raise RuntimeError(f"instance {instance_id} is not managed") from exc

    def pause(self, instance_id: str) -> ManagedClientSnapshot:
        self.pause_calls.append(instance_id)
        result = replace(
            self.status(instance_id),
            state=ManagedClientState.PAUSED,
            dispatch_enabled=False,
            status_detail=None,
        )
        self.statuses[instance_id] = result
        return result

    def resume(self, instance_id: str) -> ManagedClientSnapshot:
        self.resume_calls.append(instance_id)
        result = replace(
            self.status(instance_id),
            state=ManagedClientState.ATTACHED,
            dispatch_enabled=True,
            status_detail=None,
        )
        self.statuses[instance_id] = result
        return result

    def detach(self, instance_id: str) -> ManagedClientSnapshot:
        self.detach_calls.append(instance_id)
        current = self.status(instance_id)
        result = replace(
            current,
            state=ManagedClientState.DETACHED,
            dispatch_enabled=False,
            status_detail="detached by manager",
        )
        del self.statuses[instance_id]
        return result

    def request_close(self, instance_id: str) -> ManagedClientSnapshot:
        self.close_calls.append(instance_id)
        if self.close_error is not None:
            self.statuses[instance_id] = replace(
                self.status(instance_id),
                state=ManagedClientState.PAUSED,
                dispatch_enabled=False,
                status_detail="graceful close request failed",
            )
            raise self.close_error
        result = replace(
            self.status(instance_id),
            state=ManagedClientState.CLOSE_REQUESTED,
            dispatch_enabled=False,
            status_detail="graceful close requested",
        )
        self.statuses[instance_id] = result
        return result

    def tile(
        self,
        instance_id: str,
        rectangle: WindowRectangle,
    ) -> ManagedClientSnapshot:
        self.tile_calls.append((instance_id, rectangle))
        return self.status(instance_id)


def _selector(manifest: ManagerManifest, client_id: str) -> ClientInstanceSelector:
    config = next(client for client in manifest.clients if client.client_id == client_id)
    return selector_from_config(manifest.node_id, config)


class ManagerSessionTests(unittest.TestCase):
    def test_initial_status_is_immutable_serializable_local_topology(self) -> None:
        manifest = _manifest()
        session = ManagerSession(manifest, FakeSupervisor())

        snapshot = session.status()

        self.assertIsInstance(snapshot, ManagerSessionSnapshot)
        self.assertEqual(NODE_ID, snapshot.node_id)
        self.assertEqual(1, snapshot.schema_version)
        self.assertEqual(
            (ManagerSlotState.CONFIGURED,) * 3,
            tuple(slot.state for slot in snapshot.slots),
        )
        self.assertEqual(
            (0, 0, 800, 600),
            snapshot.slots[0].window_tile,
        )
        self.assertIsNone(snapshot.slots[2].window_tile)
        self.assertEqual(snapshot.to_dict(), json.loads(json.dumps(snapshot.to_dict())))
        with self.assertRaises(FrozenInstanceError):
            snapshot.node_id = "other"  # type: ignore[misc]

    def test_start_translates_manifest_and_never_silently_rebinds_slot(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        expected = _managed(_selector(manifest, "client-01"), "instance-101", 101)
        supervisor.start_outcomes.append(expected)
        session = ManagerSession(manifest, supervisor)

        result = session.start(
            "client-01",
            timeout_seconds=8.0,
            poll_seconds=0.25,
        )

        self.assertEqual("instance-101", result.instance_id)
        self.assertEqual(ManagerSlotState.ATTACHED, result.state)
        self.assertTrue(result.dispatch_enabled)
        selector, command, timeout, poll = supervisor.start_calls[0]
        self.assertEqual(_selector(manifest, "client-01"), selector)
        self.assertEqual(
            (r"C:\Games\Shadowbane\launcher.exe", "-windowed"),
            command.argv,
        )
        self.assertEqual((8.0, 0.25), (timeout, poll))

        with self.assertRaises(SessionSlotBoundError):
            session.start("client-01")
        self.assertEqual(1, len(supervisor.start_calls))
        self.assertEqual("instance-101", session.status("client-01").instance_id)

    def test_new_binding_must_begin_attached_and_dispatch_authorized(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        supervisor.start_outcomes.append(
            _managed(
                _selector(manifest, "client-01"),
                "instance-101",
                101,
                state=ManagedClientState.PAUSED,
            )
        )
        session = ManagerSession(manifest, supervisor)

        with self.assertRaisesRegex(SessionActionError, "must begin.*attached"):
            session.start("client-01")

        status = session.status("client-01")
        self.assertIsNone(status.instance_id)
        self.assertFalse(status.dispatch_enabled)

    def test_start_all_is_sequential_and_stops_on_first_overlapping_filter_failure(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        supervisor.start_outcomes.extend(
            [
                _managed(_selector(manifest, "client-01"), "instance-101", 101),
                RuntimeError("ambiguous new matching clients"),
                _managed(_selector(manifest, "client-03"), "instance-303", 303),
            ]
        )
        session = ManagerSession(manifest, supervisor)

        with self.assertRaisesRegex(SessionActionError, "ambiguous"):
            session.start_all(timeout_seconds=3.0)

        self.assertEqual(2, len(supervisor.start_calls))
        self.assertEqual(supervisor.start_calls[0][0], supervisor.start_calls[1][0])
        status = session.snapshot()
        self.assertEqual(ManagerSlotState.ATTACHED, status.slots[0].state)
        self.assertEqual(ManagerSlotState.CONFIGURED, status.slots[1].state)
        self.assertIn("start failed", status.slots[1].failure_detail)
        self.assertEqual(ManagerSlotState.CONFIGURED, status.slots[2].state)

    def test_exact_attach_prevents_one_instance_from_owning_two_slots(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        selected = _managed(
            _selector(manifest, "client-01"),
            "instance-existing",
            404,
            launched=False,
        )
        supervisor.attach_results[selected.instance_id] = selected
        session = ManagerSession(manifest, supervisor)

        attached = session.attach("client-01", instance_id=selected.instance_id)

        self.assertEqual(selected.instance_id, attached.instance_id)
        self.assertFalse(attached.launched_by_manager)
        self.assertEqual(
            [(_selector(manifest, "client-01"), selected.instance_id)],
            supervisor.attach_calls,
        )
        with self.assertRaisesRegex(SessionSlotBoundError, "already bound"):
            session.attach("client-02", instance_id=selected.instance_id)
        self.assertEqual(1, len(supervisor.attach_calls))
        self.assertIn("already bound", session.status("client-02").failure_detail)

    def test_refresh_rejects_a_supervisor_attempt_to_rebind_exact_identity(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        original = _managed(_selector(manifest, "client-01"), "instance-101", 101)
        replacement = _managed(_selector(manifest, "client-01"), "instance-202", 202)
        supervisor.start_outcomes.append(original)
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")
        supervisor.refresh_outcomes[original.instance_id] = [replacement]

        with self.assertRaisesRegex(SessionActionError, "exact instance"):
            session.refresh("client-01")

        status = session.status("client-01")
        self.assertEqual(original.instance_id, status.instance_id)
        self.assertIn("refresh failed", status.failure_detail)

    def test_tile_one_and_all_use_only_configured_rectangles(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        supervisor.start_outcomes.extend(
            [
                _managed(_selector(manifest, "client-01"), "instance-101", 101),
                _managed(_selector(manifest, "client-02"), "instance-202", 202),
                _managed(_selector(manifest, "client-03"), "instance-303", 303),
            ]
        )
        session = ManagerSession(manifest, supervisor)
        session.start_all()

        session.tile_all()

        self.assertEqual(
            [
                ("instance-101", WindowRectangle(left=0, top=0, width=800, height=600)),
                ("instance-202", WindowRectangle(left=800, top=0, width=800, height=600)),
            ],
            supervisor.tile_calls,
        )
        with self.assertRaisesRegex(SessionActionError, "no window_tile"):
            session.tile("client-03")

    def test_pause_resume_and_detach_preserve_process_ownership_boundary(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        supervisor.start_outcomes.append(
            _managed(_selector(manifest, "client-01"), "instance-101", 101)
        )
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")

        paused = session.pause("client-01")
        resumed = session.resume("client-01")
        detached = session.detach("client-01")

        self.assertEqual(ManagerSlotState.PAUSED, paused.state)
        self.assertFalse(paused.dispatch_enabled)
        self.assertEqual(ManagerSlotState.ATTACHED, resumed.state)
        self.assertTrue(resumed.dispatch_enabled)
        self.assertEqual(ManagerSlotState.DETACHED, detached.state)
        self.assertIsNone(detached.instance_id)
        self.assertEqual(["instance-101"], supervisor.detach_calls)
        self.assertEqual([], supervisor.close_calls)
        with self.assertRaises(SessionSlotUnboundError):
            session.pause("client-01")

    def test_generic_stale_close_refresh_retains_exact_binding_dispatch_off(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        attached = _managed(_selector(manifest, "client-01"), "instance-101", 101)
        supervisor.start_outcomes.append(attached)
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")

        closing = session.graceful_close("client-01")
        stale = replace(
            supervisor.statuses[attached.instance_id],
            state=ManagedClientState.STALE,
            dispatch_enabled=False,
            status_detail="immutable client identity is no longer present exactly once",
        )
        supervisor.refresh_outcomes[attached.instance_id] = [stale]
        stale_status = session.refresh("client-01")

        self.assertEqual(ManagerSlotState.CLOSE_REQUESTED, closing.state)
        self.assertFalse(closing.dispatch_enabled)
        self.assertEqual(ManagerSlotState.STALE, stale_status.state)
        self.assertFalse(stale_status.dispatch_enabled)
        self.assertEqual(attached.instance_id, stale_status.instance_id)
        self.assertEqual([], supervisor.detach_calls)

    def test_verified_process_exit_completes_close_and_releases_slot(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        attached = _managed(_selector(manifest, "client-01"), "instance-101", 101)
        supervisor.start_outcomes.append(attached)
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")
        session.graceful_close("client-01")
        exited = replace(
            supervisor.statuses[attached.instance_id],
            state=ManagedClientState.EXITED,
            dispatch_enabled=False,
            status_detail="verified exact process lifetime exited",
        )
        supervisor.refresh_outcomes[attached.instance_id] = [exited]

        closed = session.refresh("client-01")

        self.assertEqual(ManagerSlotState.CLOSED, closed.state)
        self.assertIsNone(closed.instance_id)
        self.assertEqual([attached.instance_id], supervisor.detach_calls)
        self.assertIn("process exit was verified", closed.status_detail)

    def test_verified_exit_can_recover_after_intermediate_generic_stale_status(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        attached = _managed(_selector(manifest, "client-01"), "instance-101", 101)
        supervisor.start_outcomes.append(attached)
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")
        session.graceful_close("client-01")
        closing = supervisor.statuses[attached.instance_id]
        supervisor.refresh_outcomes[attached.instance_id] = [
            replace(
                closing,
                state=ManagedClientState.STALE,
                dispatch_enabled=False,
                status_detail="window identity temporarily absent",
            ),
            replace(
                closing,
                state=ManagedClientState.EXITED,
                dispatch_enabled=False,
                status_detail="verified exact process lifetime exited",
            ),
        ]

        stale = session.refresh("client-01")
        closed = session.refresh("client-01")

        self.assertEqual(ManagerSlotState.STALE, stale.state)
        self.assertEqual(attached.instance_id, stale.instance_id)
        self.assertEqual(ManagerSlotState.CLOSED, closed.state)
        self.assertIsNone(closed.instance_id)

    def test_close_failure_records_detail_and_reconciles_dispatch_paused(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        supervisor.start_outcomes.append(
            _managed(_selector(manifest, "client-01"), "instance-101", 101)
        )
        supervisor.close_error = OSError("window rejected graceful close")
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")

        with self.assertRaisesRegex(SessionActionError, "window rejected"):
            session.request_close("client-01")

        status = session.status("client-01")
        self.assertEqual(ManagerSlotState.PAUSED, status.state)
        self.assertFalse(status.dispatch_enabled)
        self.assertIn("close failed", status.failure_detail)
        self.assertEqual("instance-101", status.instance_id)

    def test_successful_refresh_clears_prior_failure_and_updates_status(self) -> None:
        manifest = _manifest()
        supervisor = FakeSupervisor()
        attached = _managed(_selector(manifest, "client-01"), "instance-101", 101)
        supervisor.start_outcomes.append(attached)
        session = ManagerSession(manifest, supervisor)
        session.start("client-01")
        with self.assertRaises(SessionSlotBoundError):
            session.start("client-01")
        self.assertIsNotNone(session.status("client-01").failure_detail)

        refreshed = session.refresh("client-01")

        self.assertIsInstance(refreshed, ManagerSlotSnapshot)
        self.assertIsNone(refreshed.failure_detail)
        self.assertEqual(["instance-101"], supervisor.refresh_calls)


if __name__ == "__main__":
    unittest.main()
