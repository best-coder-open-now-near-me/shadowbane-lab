import unittest

from shadowbane_lab.client_action import (
    ClientActionBoundary,
    ClientActionCheckpoint,
    ClientActionEffectObservation,
    ClientActionRunner,
    ClientActionSpec,
    ClientActionVerification,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class RecordingAction:
    action_id = "action-1"
    spec = ClientActionSpec(
        key="client.test.recording",
        verification=ClientActionVerification.NATIVE_VERIFIED,
        timeout_ms=100,
        poll_interval_ms=25,
    )

    def __init__(self, *, observe_after: int = 1, fail_at: str | None = None) -> None:
        self.observe_after = observe_after
        self.fail_at = fail_at
        self.observations = 0
        self.cleanup_calls = 0

    def prepare(self) -> ClientActionCheckpoint:
        if self.fail_at == "prepare":
            raise RuntimeError("unsafe precondition")
        return ClientActionCheckpoint("precondition is exact", {"process_id": 42})

    def dispatch(self) -> ClientActionCheckpoint:
        if self.fail_at == "dispatch":
            raise RuntimeError("input rejected")
        return ClientActionCheckpoint("one input was dispatched", {"commands": 1})

    def observe_effect(self) -> ClientActionEffectObservation:
        self.observations += 1
        if self.fail_at == "observe":
            raise RuntimeError("observer incoherent")
        return ClientActionEffectObservation(
            observed=self.observations >= self.observe_after,
            checkpoint=ClientActionCheckpoint(
                "effect observed" if self.observations >= self.observe_after else "effect pending",
                {"poll": self.observations},
            ),
        )

    def cleanup(self) -> ClientActionCheckpoint:
        self.cleanup_calls += 1
        if self.fail_at == "cleanup":
            raise RuntimeError("cleanup rejected")
        return ClientActionCheckpoint("cleanup completed", {"cleanup_calls": self.cleanup_calls})


class ClientActionRunnerTests(unittest.TestCase):
    def test_records_clear_success_boundaries(self) -> None:
        clock = FakeClock()
        action = RecordingAction(observe_after=2)

        result = ClientActionRunner(clock=clock, sleeper=clock.sleep).run(action)

        self.assertTrue(result.succeeded)
        self.assertEqual("effect_observed", result.terminal_reason)
        self.assertEqual(
            (
                ClientActionBoundary.STARTED,
                ClientActionBoundary.PRECONDITION_PASSED,
                ClientActionBoundary.INPUT_DISPATCHED,
                ClientActionBoundary.EFFECT_OBSERVED,
                ClientActionBoundary.CLEANUP_COMPLETED,
                ClientActionBoundary.SUCCEEDED,
            ),
            tuple(item.boundary for item in result.boundaries),
        )
        self.assertEqual(1, action.cleanup_calls)
        self.assertEqual("native_verified", result.to_dict()["verification"])

    def test_precondition_failure_never_dispatches_or_cleans_up(self) -> None:
        action = RecordingAction(fail_at="prepare")

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("precondition_failed", result.terminal_reason)
        self.assertEqual(0, action.cleanup_calls)
        self.assertEqual(ClientActionBoundary.FAILED, result.boundaries[-1].boundary)

    def test_dispatch_failure_still_runs_cleanup(self) -> None:
        action = RecordingAction(fail_at="dispatch")

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("dispatch_failed", result.terminal_reason)
        self.assertEqual(1, action.cleanup_calls)
        self.assertIn(
            ClientActionBoundary.CLEANUP_COMPLETED,
            tuple(item.boundary for item in result.boundaries),
        )

    def test_times_out_with_last_pending_observation(self) -> None:
        clock = FakeClock()
        action = RecordingAction(observe_after=100)

        result = ClientActionRunner(clock=clock, sleeper=clock.sleep).run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("effect_timeout", result.terminal_reason)
        self.assertEqual(100, result.duration_ms)
        self.assertIn("effect pending", result.boundaries[-1].detail)
        self.assertEqual(1, action.cleanup_calls)

    def test_cleanup_failure_overrides_an_observed_effect(self) -> None:
        action = RecordingAction(fail_at="cleanup")

        result = ClientActionRunner().run(action)

        self.assertFalse(result.succeeded)
        self.assertEqual("cleanup_failed", result.terminal_reason)
        self.assertEqual(ClientActionBoundary.EFFECT_OBSERVED, result.boundaries[-2].boundary)
        self.assertEqual(ClientActionBoundary.FAILED, result.boundaries[-1].boundary)


if __name__ == "__main__":
    unittest.main()
