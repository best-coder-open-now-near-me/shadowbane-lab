import unittest

from shadowbane_lab.client_input import WindowBounds
from shadowbane_lab.manager.application import ManagerDashboardApplication
from shadowbane_lab.manager.dashboard import DashboardError
from shadowbane_lab.manager.manifest import ManagerManifest, parse_manager_manifest
from shadowbane_lab.manager.model import ClientInstanceSnapshot, ClientRegistrySnapshot
from shadowbane_lab.manager.operation import (
    WorkerOperationKind,
    WorkerOperationReceipt,
    WorkerOperationSnapshot,
    WorkerOperationState,
    new_worker_operation,
)
from shadowbane_lab.manager.session import (
    ManagerSessionSnapshot,
    ManagerSlotSnapshot,
    ManagerSlotState,
    SessionActionError,
)
from shadowbane_lab.manager.worker import (
    WorkerDispatchPermit,
    WorkerHealthState,
    WorkerSlotHealthSnapshot,
)

NODE_ID = "gaming-pc-east"
PROCESS_DIRECTORY = r"C:\Games\Shadowbane"


def _manifest() -> ManagerManifest:
    return parse_manager_manifest(
        {
            "schema_version": 1,
            "node_id": NODE_ID,
            "clients": [
                {
                    "client_id": client_id,
                    "launch": {
                        "executable": rf"{PROCESS_DIRECTORY}\launcher.exe",
                        "arguments": ["-windowed"],
                        "working_directory": PROCESS_DIRECTORY,
                    },
                    "expected_process_directory": PROCESS_DIRECTORY,
                    "expected_executable_names": ["sb.exe"],
                    "window_tile": {
                        "left": left,
                        "top": 0,
                        "width": 800,
                        "height": 600,
                    },
                }
                for client_id, left in (("client-01", 0), ("client-02", 800))
            ],
        }
    )


def _slot(
    client_id: str,
    *,
    instance_id: str | None = None,
    state: ManagerSlotState | None = None,
) -> ManagerSlotSnapshot:
    attached = instance_id is not None
    resolved_state = state or (
        ManagerSlotState.ATTACHED if attached else ManagerSlotState.CONFIGURED
    )
    return ManagerSlotSnapshot(
        client_id=client_id,
        state=resolved_state,
        instance_id=instance_id,
        dispatch_enabled=resolved_state is ManagerSlotState.ATTACHED,
        launched_by_manager=False,
        launcher_process_id=None,
        launcher_process_started_at_100ns=None,
        launch_provenance=None,
        attached_at=None,
        last_verified_at=None,
        window_tile=(0, 0, 800, 600),
    )


def _client(
    instance_id: str,
    process_id: int,
    *,
    directory: str = PROCESS_DIRECTORY,
) -> ClientInstanceSnapshot:
    return ClientInstanceSnapshot(
        node_id=NODE_ID,
        instance_id=instance_id,
        process_id=process_id,
        process_started_at_100ns=133_700_000_000_000_000 + process_id,
        window_handle=10_000 + process_id,
        executable_name="sb.exe",
        executable_path=rf"{directory}\sb.exe",
        title=f"Shadowbane {process_id}",
        client_bounds=WindowBounds(left=0, top=0, width=800, height=600),
        dpi_scale=1.0,
        is_foreground=False,
        is_visible=True,
    )


class _StaticRegistry:
    def __init__(self, snapshot: ClientRegistrySnapshot) -> None:
        self.snapshot = snapshot
        self.inspection_count = 0
        self.worker_supervisor: object | None = None

    def inspect(self) -> ClientRegistrySnapshot:
        self.inspection_count += 1
        return self.snapshot


class _RecordingSession:
    def __init__(self, snapshot: ManagerSessionSnapshot) -> None:
        self.snapshot_value = snapshot
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    def snapshot(self) -> ManagerSessionSnapshot:
        return self.snapshot_value

    def status(self, client_id: str) -> ManagerSlotSnapshot:
        return next(slot for slot in self.snapshot_value.slots if slot.client_id == client_id)

    def _record(self, *call: object) -> ManagerSessionSnapshot:
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        return self.snapshot_value

    def refresh(self) -> ManagerSessionSnapshot:
        return self._record("refresh")

    def start(
        self,
        client_id: str,
        *,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> ManagerSlotSnapshot:
        self._record("start", client_id, timeout_seconds, poll_seconds)
        return self.status(client_id)

    def start_all(
        self,
        *,
        timeout_seconds: float,
        poll_seconds: float,
    ) -> ManagerSessionSnapshot:
        return self._record("start-all", timeout_seconds, poll_seconds)

    def attach(self, client_id: str, *, instance_id: str) -> ManagerSlotSnapshot:
        self._record("attach", client_id, instance_id)
        return self.status(client_id)

    def tile(self, client_id: str) -> ManagerSlotSnapshot:
        self._record("tile", client_id)
        return self.status(client_id)

    def tile_all(self) -> ManagerSessionSnapshot:
        return self._record("tile-all")

    def pause(self, client_id: str) -> ManagerSlotSnapshot:
        self._record("pause", client_id)
        return self.status(client_id)

    def resume(self, client_id: str) -> ManagerSlotSnapshot:
        self._record("resume", client_id)
        return self.status(client_id)

    def detach(self, client_id: str) -> ManagerSlotSnapshot:
        self._record("detach", client_id)
        return self.status(client_id)

    def request_close(self, client_id: str) -> ManagerSlotSnapshot:
        self._record("close", client_id)
        return self.status(client_id)


class _StaticWorkerSupervisor:
    def __init__(self, state: WorkerHealthState = WorkerHealthState.HEALTHY) -> None:
        self.state = state
        self.revocations: list[tuple[str, str]] = []

    def inspect(
        self,
        client_id: str,
        *,
        instance_id: str | None,
        lifecycle_dispatch_enabled: bool,
    ) -> WorkerSlotHealthSnapshot:
        if instance_id is None:
            return WorkerSlotHealthSnapshot(
                client_id=client_id,
                state=WorkerHealthState.UNBOUND,
                dispatch_allowed=False,
                active_worker_count=0,
            )
        return WorkerSlotHealthSnapshot(
            client_id=client_id,
            state=self.state,
            dispatch_allowed=(
                lifecycle_dispatch_enabled and self.state is WorkerHealthState.HEALTHY
            ),
            active_worker_count=1,
        )

    def revoke(self, client_id: str, *, reason: str) -> None:
        self.revocations.append((client_id, reason))


class _RecordingWorkerController:
    def __init__(self) -> None:
        self.starts: list[tuple[str, str]] = []
        self.stops: list[tuple[str, str]] = []

    def ensure_started(self, client_id: str, client: ClientInstanceSnapshot) -> int:
        self.starts.append((client_id, client.instance_id))
        return 7001

    def request_stop(self, client_id: str, *, reason: str) -> int:
        self.stops.append((client_id, reason))
        return 1


class _StaticOperationStatus:
    def __init__(self, *snapshots: WorkerOperationSnapshot) -> None:
        self.snapshots = tuple(snapshots)

    def inspect_slot(self, _client_id: str) -> tuple[WorkerOperationSnapshot, ...]:
        return self.snapshots


def _application(
    session: _RecordingSession,
    *clients: ClientInstanceSnapshot,
    worker_state: WorkerHealthState = WorkerHealthState.HEALTHY,
    worker_controller: _RecordingWorkerController | None = None,
    operation_status: _StaticOperationStatus | None = None,
) -> tuple[ManagerDashboardApplication, _StaticRegistry]:
    registry = _StaticRegistry(
        ClientRegistrySnapshot(
            node_id=NODE_ID,
            clients=tuple(
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
            ),
        )
    )
    worker_supervisor = _StaticWorkerSupervisor(worker_state)
    registry.worker_supervisor = worker_supervisor
    return (
        ManagerDashboardApplication(
            _manifest(),
            session,
            registry,
            worker_supervisor,
            worker_controller=worker_controller,
            operation_status=operation_status,
            launch_timeout_seconds=12.0,
            poll_seconds=0.25,
        ),
        registry,
    )


class ManagerDashboardApplicationTests(unittest.TestCase):
    def test_status_reports_active_operation_and_latest_terminal_result(self) -> None:
        bound = _client("instance-101", 101)
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(_slot("client-01", instance_id=bound.instance_id),),
            )
        )
        permit = WorkerDispatchPermit(
            node_id=NODE_ID,
            client_id="client-01",
            instance_id=bound.instance_id,
            worker_id="worker-0123456789abcdef0123456789abcdef",
            process_id=9001,
            process_started_at_100ns=133_700_000_000_009_001,
            heartbeat_sequence=4,
            health_state=WorkerHealthState.HEALTHY,
            allowed=True,
            issued_at=100.0,
            expires_at=102.0,
            reason="exact worker is healthy",
        )
        completed = new_worker_operation(
            permit,
            WorkerOperationKind.TRAVEL,
            "/go 1 2",
            now=100.0,
            operation_id="operation-11111111111111111111111111111111",
        )
        active = new_worker_operation(
            permit,
            WorkerOperationKind.PVE,
            "/pve",
            now=101.0,
            operation_id="operation-22222222222222222222222222222222",
        )
        operation_status = _StaticOperationStatus(
            WorkerOperationSnapshot(
                completed,
                WorkerOperationReceipt.for_operation(
                    completed,
                    WorkerOperationState.SUCCEEDED,
                    observed_at=100.5,
                ),
            ),
            WorkerOperationSnapshot(
                active,
                WorkerOperationReceipt.for_operation(
                    active,
                    WorkerOperationState.ACTIVE,
                    observed_at=101.1,
                ),
            ),
        )
        application, _ = _application(
            session,
            bound,
            operation_status=operation_status,
        )

        operation = application.status()["slots"][0]["operation"]

        self.assertEqual(0, operation["queued_count"])
        self.assertEqual(
            active.operation_id,
            operation["active"]["operation"]["operation_id"],
        )
        self.assertEqual(
            "succeeded",
            operation["latest_result"]["receipt"]["state"],
        )

    def test_resume_bootstraps_exact_worker_and_detach_stops_it(self) -> None:
        bound = _client("instance-101", 101)
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(_slot("client-01", instance_id=bound.instance_id),),
            )
        )
        controller = _RecordingWorkerController()
        application, _ = _application(
            session,
            bound,
            worker_controller=controller,
        )

        application.execute(
            "resume",
            client_id="client-01",
            instance_id=bound.instance_id,
        )
        application.execute(
            "detach",
            client_id="client-01",
            instance_id=bound.instance_id,
        )

        self.assertEqual([("client-01", bound.instance_id)], controller.starts)
        self.assertEqual(1, len(controller.stops))
        self.assertEqual("client-01", controller.stops[0][0])
        self.assertIn("detach", controller.stops[0][1])

    def test_status_enriches_exact_binding_and_excludes_it_from_candidates(self) -> None:
        bound = _client("instance-101", 101)
        candidate = _client("instance-202", 202)
        unrelated = _client("instance-303", 303, directory=r"D:\Other")
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(
                    _slot("client-01", instance_id=bound.instance_id),
                    _slot("client-02"),
                ),
            )
        )
        application, registry = _application(session, unrelated, candidate, bound)

        status = application.status()

        self.assertTrue(status["ok"])
        self.assertEqual(2, status["configured_count"])
        self.assertEqual(1, status["bound_count"])
        self.assertEqual(1, status["healthy_worker_count"])
        self.assertEqual(1, status["dispatch_ready_count"])
        self.assertEqual(bound.instance_id, status["slots"][0]["binding"]["instance_id"])
        self.assertTrue(status["slots"][0]["lifecycle_dispatch_enabled"])
        self.assertTrue(status["slots"][0]["dispatch_enabled"])
        self.assertEqual("healthy", status["slots"][0]["worker"]["state"])
        self.assertEqual(
            [candidate.instance_id],
            [item["instance_id"] for item in status["slots"][0]["candidates"]],
        )
        self.assertEqual(
            [candidate.instance_id],
            [item["instance_id"] for item in status["slots"][1]["candidates"]],
        )
        self.assertEqual(1, registry.inspection_count)

    def test_status_derives_absent_remembered_binding_as_stale_and_unbound(self) -> None:
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(
                    _slot("client-01", instance_id="instance-gone"),
                    _slot("client-02"),
                ),
            )
        )
        application, _ = _application(session)

        status = application.status()

        self.assertEqual(0, status["bound_count"])
        effective = status["slots"][0]
        self.assertEqual("stale", effective["state"])
        self.assertFalse(effective["dispatch_enabled"])
        self.assertIsNone(effective["binding"])
        self.assertEqual("instance-gone", effective["instance_id"])
        self.assertIn("absent", effective["status_detail"])

    def test_status_never_substitutes_new_matching_candidate_for_absent_binding(self) -> None:
        replacement = _client("instance-replacement", 202)
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(
                    _slot(
                        "client-01",
                        instance_id="instance-gone",
                        state=ManagerSlotState.CLOSE_REQUESTED,
                    ),
                    _slot("client-02"),
                ),
            )
        )
        application, _ = _application(session, replacement)

        status = application.status()

        effective = status["slots"][0]
        self.assertEqual(0, status["bound_count"])
        self.assertEqual("stale", effective["state"])
        self.assertIsNone(effective["binding"])
        self.assertEqual(
            [replacement.instance_id],
            [candidate["instance_id"] for candidate in effective["candidates"]],
        )

    def test_stale_browser_instance_cannot_act_on_a_rebound_slot(self) -> None:
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(
                    _slot("client-01", instance_id="instance-current"),
                    _slot("client-02"),
                ),
            )
        )
        application, _ = _application(session)

        with self.assertRaisesRegex(DashboardError, "no longer owns") as context:
            application.execute(
                "pause",
                client_id="client-01",
                instance_id="instance-stale",
            )

        self.assertEqual("stale-instance-selection", context.exception.code)
        self.assertEqual([], session.calls)

    def test_worker_health_is_a_required_effective_dispatch_gate(self) -> None:
        bound = _client("instance-101", 101)
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(
                    _slot("client-01", instance_id=bound.instance_id),
                    _slot("client-02"),
                ),
            )
        )
        application, _ = _application(
            session,
            bound,
            worker_state=WorkerHealthState.MISSING,
        )

        status = application.status()

        slot = status["slots"][0]
        self.assertTrue(slot["lifecycle_dispatch_enabled"])
        self.assertFalse(slot["dispatch_enabled"])
        self.assertEqual("missing", slot["worker"]["state"])
        self.assertEqual(0, status["dispatch_ready_count"])

    def test_launch_requires_existing_candidates_to_be_attached_first(self) -> None:
        candidate = _client("instance-existing", 202)
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(_slot("client-01"), _slot("client-02")),
            )
        )
        application, _ = _application(session, candidate)

        with self.assertRaises(DashboardError) as context:
            application.execute("start-all")

        self.assertEqual("attach-selection-required", context.exception.code)
        self.assertEqual([], session.calls)

    def test_reviewed_actions_map_to_session_with_configured_launch_limits(self) -> None:
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(
                    _slot("client-01", instance_id="instance-101"),
                    _slot("client-02"),
                ),
            )
        )
        application, registry = _application(session)

        application.execute("start-all")
        application.execute("refresh")
        application.execute("tile-all")
        application.execute("start", client_id="client-02")
        application.execute(
            "attach",
            client_id="client-02",
            instance_id="instance-existing",
        )
        for action in ("tile", "pause", "resume", "detach", "close"):
            application.execute(
                action,
                client_id="client-01",
                instance_id="instance-101",
            )

        self.assertEqual(
            [
                ("start-all", 12.0, 0.25),
                ("refresh",),
                ("tile-all",),
                ("start", "client-02", 12.0, 0.25),
                ("attach", "client-02", "instance-existing"),
                ("tile", "client-01"),
                ("pause", "client-01"),
                ("resume", "client-01"),
                ("detach", "client-01"),
                ("close", "client-01"),
            ],
            session.calls,
        )
        self.assertIsInstance(registry.worker_supervisor, _StaticWorkerSupervisor)
        worker_supervisor = registry.worker_supervisor
        assert isinstance(worker_supervisor, _StaticWorkerSupervisor)
        self.assertEqual(
            [
                "client-02",
                "client-02",
                "client-02",
                "client-01",
                "client-01",
                "client-01",
            ],
            [client_id for client_id, _reason in worker_supervisor.revocations],
        )

    def test_session_failures_become_structured_dashboard_conflicts(self) -> None:
        session = _RecordingSession(
            ManagerSessionSnapshot(
                node_id=NODE_ID,
                slots=(_slot("client-01"), _slot("client-02")),
            )
        )
        session.error = SessionActionError("start failed safely")
        application, _ = _application(session)

        with self.assertRaises(DashboardError) as context:
            application.execute("start", client_id="client-01")

        self.assertEqual("manager-action-failed", context.exception.code)
        self.assertIn("start failed safely", context.exception.message)


if __name__ == "__main__":
    unittest.main()
