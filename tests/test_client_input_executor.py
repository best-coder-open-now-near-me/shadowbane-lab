import unittest
from dataclasses import replace

from shadowbane_lab.client_input import (
    AbsolutePoint,
    ClickInvocation,
    ClientInputAdapter,
    DecisionInputCompiler,
    DragInvocation,
    EventEmergencyStop,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    HotkeyInvocation,
    InputExecutionError,
    KeyPressInvocation,
    MouseButton,
    NormalizedPoint,
    PyAutoGuiBackend,
    RecordingInputBackend,
    StaticBindingPointResolver,
    StaticWindowInspector,
    WindowBounds,
    WindowGuardError,
    WindowSnapshot,
)
from shadowbane_lab.protocol import DecisionAdapter
from tests.fixtures import protocol_exchange
from tests.test_client_input_compiler import _load_profile


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleep_calls: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.sleep_calls.append(duration)
        self.now += duration


class TripAfterClickBackend(RecordingInputBackend):
    def __init__(self, stop: EventEmergencyStop) -> None:
        super().__init__()
        self._stop = stop

    def click(self, invocation: ClickInvocation) -> None:
        super().click(invocation)
        self._stop.trip()


class FakePyAutoGui:
    def __init__(self) -> None:
        self.FAILSAFE = False
        self.calls: list[tuple[object, ...]] = []

    def click(self, **kwargs: object) -> None:
        self.calls.append(("click", kwargs))

    def moveTo(self, x: int, y: int) -> None:
        self.calls.append(("moveTo", x, y))

    def dragTo(self, x: int, y: int, **kwargs: object) -> None:
        self.calls.append(("dragTo", x, y, kwargs))

    def press(self, key: str) -> None:
        self.calls.append(("press", key))

    def hotkey(self, *keys: str) -> None:
        self.calls.append(("hotkey", *keys))


def _valid_snapshot() -> WindowSnapshot:
    return WindowSnapshot(
        executable_name="Shadowbane.exe",
        title="WonderBane - Character Select",
        client_bounds=WindowBounds(left=100, top=50, width=1280, height=720),
        dpi_scale=1.0,
        is_foreground=True,
        is_visible=True,
        process_id=4320,
    )


def _client_adapter(
    *,
    snapshot: WindowSnapshot | None = None,
    backend: RecordingInputBackend | None = None,
    stop: EventEmergencyStop | None = None,
    clock: ManualClock | None = None,
) -> tuple[ClientInputAdapter, RecordingInputBackend, StaticWindowInspector, ManualClock]:
    profile = _load_profile()
    resolved_backend = backend or RecordingInputBackend()
    resolved_stop = stop or EventEmergencyStop()
    resolved_clock = clock or ManualClock()
    inspector = StaticWindowInspector(snapshot if snapshot is not None else _valid_snapshot())
    compiler = DecisionInputCompiler(
        profile,
        StaticBindingPointResolver({"enemy-7": NormalizedPoint(0.62, 0.43)}),
    )
    executor = GuardedInputExecutor(
        guard=ForegroundWindowGuard(profile, inspector),
        backend=resolved_backend,
        stop_signal=resolved_stop,
        minimum_input_interval_ms=25,
        clock=resolved_clock,
        sleeper=resolved_clock.sleep,
    )
    return ClientInputAdapter(compiler, executor), resolved_backend, inspector, resolved_clock


class GuardedInputAdapterTests(unittest.TestCase):
    def test_character_precondition_runs_before_each_input_and_preserves_rejection(self) -> None:
        adapter, backend, inspector, clock = _client_adapter()
        checks = []

        def precondition():
            checks.append(True)
            if len(checks) == 2:
                raise RuntimeError("active character changed")

        adapter._executor._input_precondition = precondition
        result = adapter.dispatch(protocol_exchange()[2])
        self.assertFalse(result.accepted)
        self.assertIn("active character changed", result.reason)
        self.assertEqual(2, len(checks))
        self.assertEqual(1, len(backend.invocations))

    def test_semantic_decision_executes_resolved_recording_plan(self) -> None:
        adapter, backend, inspector, clock = _client_adapter()
        decision = protocol_exchange()[2]
        bounds = _valid_snapshot().client_bounds

        result = adapter.dispatch(decision)

        self.assertIsInstance(adapter, DecisionAdapter)
        self.assertTrue(result.accepted)
        self.assertEqual(
            (
                ClickInvocation(
                    point=bounds.resolve(NormalizedPoint(0.62, 0.43)),
                    button=MouseButton.LEFT,
                ),
                KeyPressInvocation("3"),
            ),
            backend.invocations,
        )
        self.assertEqual(2, inspector.inspection_count)
        self.assertAlmostEqual(0.15, clock.now)
        self.assertEqual(3, adapter.audits[0].commands_completed)

    def test_guard_rejects_mismatched_windows_before_any_input(self) -> None:
        invalid_snapshots = {
            "background": replace(_valid_snapshot(), is_foreground=False),
            "hidden": replace(_valid_snapshot(), is_visible=False),
            "executable": replace(_valid_snapshot(), executable_name="notepad.exe"),
            "title": replace(_valid_snapshot(), title="Unrelated Game"),
            "width": replace(
                _valid_snapshot(),
                client_bounds=WindowBounds(left=100, top=50, width=1200, height=720),
            ),
            "dpi": replace(_valid_snapshot(), dpi_scale=1.25),
        }
        for name, snapshot in invalid_snapshots.items():
            with self.subTest(name=name):
                adapter, backend, _, _ = _client_adapter(snapshot=snapshot)

                result = adapter.dispatch(protocol_exchange()[2])

                self.assertFalse(result.accepted)
                self.assertEqual((), backend.invocations)
                self.assertEqual(0, adapter.audits[0].commands_completed)

    def test_guard_rejects_when_no_foreground_window_can_be_inspected(self) -> None:
        profile = _load_profile()
        backend = RecordingInputBackend()
        inspector = StaticWindowInspector(None)
        compiler = DecisionInputCompiler(
            profile,
            StaticBindingPointResolver({"enemy-7": NormalizedPoint(0.62, 0.43)}),
        )
        executor = GuardedInputExecutor(
            guard=ForegroundWindowGuard(profile, inspector),
            backend=backend,
            stop_signal=EventEmergencyStop(),
        )
        adapter = ClientInputAdapter(compiler, executor)

        result = adapter.dispatch(protocol_exchange()[2])

        self.assertFalse(result.accepted)
        self.assertIn("no foreground window", result.reason or "")
        self.assertEqual((), backend.invocations)

    def test_guard_rejects_a_different_foreground_client_process(self) -> None:
        profile = _load_profile()
        guard = ForegroundWindowGuard(
            profile,
            StaticWindowInspector(_valid_snapshot()),
            expected_process_id=9376,
        )

        with self.assertRaisesRegex(WindowGuardError, "different client process"):
            guard.require_target()

    def test_guard_can_bind_the_complete_immutable_client_identity(self) -> None:
        profile = _load_profile()
        snapshot = replace(
            _valid_snapshot(),
            process_started_at_100ns=133_700_000_000_000_000,
            window_handle=91234,
        )
        guard = ForegroundWindowGuard(
            profile,
            StaticWindowInspector(snapshot),
            expected_process_id=snapshot.process_id,
            expected_process_started_at_100ns=snapshot.process_started_at_100ns,
            expected_window_handle=snapshot.window_handle,
        )

        self.assertEqual(snapshot, guard.require_target())

        replacements = (
            ("process_started_at_100ns", 133_700_000_000_000_001, "replaced client process"),
            ("window_handle", 91235, "different client window"),
        )
        for field_name, value, message in replacements:
            with self.subTest(field_name=field_name):
                replaced_snapshot = replace(snapshot, **{field_name: value})
                replaced_guard = ForegroundWindowGuard(
                    profile,
                    StaticWindowInspector(replaced_snapshot),
                    expected_process_id=snapshot.process_id,
                    expected_process_started_at_100ns=snapshot.process_started_at_100ns,
                    expected_window_handle=snapshot.window_handle,
                )
                with self.assertRaisesRegex(WindowGuardError, message):
                    replaced_guard.require_target()

    def test_emergency_stop_rejects_before_any_input(self) -> None:
        stop = EventEmergencyStop()
        stop.trip()
        adapter, backend, inspector, _ = _client_adapter(stop=stop)

        result = adapter.dispatch(protocol_exchange()[2])

        self.assertFalse(result.accepted)
        self.assertIn("emergency stop", result.reason or "")
        self.assertEqual((), backend.invocations)
        self.assertEqual(0, inspector.inspection_count)

    def test_emergency_stop_interrupts_plan_and_audits_partial_execution(self) -> None:
        stop = EventEmergencyStop()
        backend = TripAfterClickBackend(stop)
        adapter, _, inspector, _ = _client_adapter(backend=backend, stop=stop)

        result = adapter.dispatch(protocol_exchange()[2])

        self.assertFalse(result.accepted)
        self.assertEqual(1, len(backend.invocations))
        self.assertEqual(1, inspector.inspection_count)
        self.assertEqual(1, adapter.audits[0].commands_completed)

    def test_camera_drag_uses_same_guarded_executor(self) -> None:
        adapter, backend, inspector, _ = _client_adapter()
        bounds = _valid_snapshot().client_bounds

        result = adapter.dispatch_camera_drag(
            correlation_id="camera-1",
            horizontal=0.5,
            vertical=-1.0,
        )

        self.assertTrue(result.accepted)
        self.assertEqual(
            (
                DragInvocation(
                    start=bounds.resolve(NormalizedPoint(0.5, 0.5)),
                    end=bounds.resolve(NormalizedPoint(0.6, 0.35)),
                    duration_ms=1000,
                    button=MouseButton.LEFT,
                ),
            ),
            backend.invocations,
        )
        self.assertEqual(1, inspector.inspection_count)

    def test_movement_stop_uses_guarded_calibrated_center_click(self) -> None:
        adapter, backend, inspector, _ = _client_adapter()
        bounds = _valid_snapshot().client_bounds

        result = adapter.dispatch_movement_stop(correlation_id="travel:7:stop")

        self.assertTrue(result.accepted)
        self.assertEqual(
            (
                ClickInvocation(
                    point=bounds.resolve(NormalizedPoint(0.5, 0.5)),
                    button=MouseButton.LEFT,
                ),
            ),
            backend.invocations,
        )
        self.assertEqual(1, inspector.inspection_count)


class PyAutoGuiBackendTests(unittest.TestCase):
    def test_translates_typed_invocations_to_pyautogui_calls(self) -> None:
        fake = FakePyAutoGui()
        backend = PyAutoGuiBackend(fake)

        backend.click(ClickInvocation(AbsolutePoint(500, 500), MouseButton.LEFT, clicks=2))
        backend.drag(
            DragInvocation(
                start=AbsolutePoint(400, 400),
                end=AbsolutePoint(600, 400),
                duration_ms=1000,
                button=MouseButton.LEFT,
            )
        )
        backend.key_press(KeyPressInvocation("3"))
        backend.hotkey(HotkeyInvocation(("ctrl", "1")))

        self.assertTrue(fake.FAILSAFE)
        self.assertEqual(
            [
                ("click", {"x": 500, "y": 500, "clicks": 2, "button": "left"}),
                ("moveTo", 400, 400),
                ("dragTo", 600, 400, {"duration": 1.0, "button": "left"}),
                ("press", "3"),
                ("hotkey", "ctrl", "1"),
            ],
            fake.calls,
        )

    def test_unconfirmed_profile_cannot_dispatch_through_live_backend(self) -> None:
        fake = FakePyAutoGui()
        profile = _load_profile()
        inspector = StaticWindowInspector(_valid_snapshot())
        compiler = DecisionInputCompiler(
            profile,
            StaticBindingPointResolver({"enemy-7": NormalizedPoint(0.62, 0.43)}),
        )
        executor = GuardedInputExecutor(
            guard=ForegroundWindowGuard(profile, inspector),
            backend=PyAutoGuiBackend(fake),
            stop_signal=EventEmergencyStop(),
        )
        adapter = ClientInputAdapter(compiler, executor)
        plan = compiler.compile(protocol_exchange()[2])

        with self.assertRaisesRegex(InputExecutionError, "not enabled for live input"):
            executor.execute(plan)

        result = adapter.dispatch(protocol_exchange()[2])

        self.assertFalse(result.accepted)
        self.assertIn("not enabled for live input", result.reason or "")
        self.assertEqual([], fake.calls)
        self.assertEqual(0, inspector.inspection_count)


if __name__ == "__main__":
    unittest.main()
