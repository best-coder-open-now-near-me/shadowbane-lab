import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_extension import (
    GraphicsRuntimeStatusExpectation,
    GraphicsRuntimeStatusWaitError,
    wait_for_graphics_runtime_status,
)
from shadowbane_lab.client_extension.__main__ import main

PROCESS_ID = 4321
CREATION_FILETIME = 133_700_000_000_004_321
EXECUTABLE_SHA256 = "ab" * 32


@dataclass(frozen=True)
class _Lifetime:
    process_id: int = PROCESS_ID
    process_started_at_100ns: int = CREATION_FILETIME


_LIVE_LIFETIME = _Lifetime()


class _Inspector:
    def __init__(self, lifetime: _Lifetime | None = _LIVE_LIFETIME) -> None:
        self.lifetime = lifetime
        self.calls: list[int] = []

    def inspect(self, process_id: int) -> _Lifetime | None:
        self.calls.append(process_id)
        return self.lifetime


def _expectation(root: Path) -> GraphicsRuntimeStatusExpectation:
    return GraphicsRuntimeStatusExpectation(
        status_directory=root / "status",
        process_id=PROCESS_ID,
        process_creation_filetime_utc=CREATION_FILETIME,
        executable_path=root / "client" / "sb.exe",
        executable_sha256=EXECUTABLE_SHA256,
        runtime_profile="diagnostics-only",
    )


def _payload(expectation: GraphicsRuntimeStatusExpectation) -> dict[str, object]:
    return {
        "schema_version": 2,
        "producer_id": "wonderbane-extension.graphics",
        "runtime_profile": expectation.runtime_profile,
        "process_identity": {
            "process_id": expectation.process_id,
            "process_creation_filetime_utc": (
                expectation.process_creation_filetime_utc
            ),
            "executable_path": str(expectation.executable_path),
        },
        "executable_sha256": expectation.executable_sha256,
    }


class GraphicsRuntimeStatusWaitTests(unittest.TestCase):
    def test_accepts_only_the_derived_exact_identity_status_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expectation = _expectation(Path(directory))
            expectation.status_path.parent.mkdir(parents=True)
            expectation.status_path.write_text(
                json.dumps(_payload(expectation)),
                encoding="utf-8",
            )
            inspector = _Inspector()

            result = wait_for_graphics_runtime_status(
                expectation,
                process_inspector=inspector,
                clock=lambda: 0.0,
                sleeper=lambda _seconds: None,
            )

        self.assertEqual("diagnostics-only", result["runtime_profile"])
        self.assertEqual([PROCESS_ID], inspector.calls)
        self.assertEqual(
            f"graphics-status-{PROCESS_ID}-{CREATION_FILETIME}.json",
            expectation.status_path.name,
        )

    def test_retries_partial_status_then_accepts_atomic_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expectation = _expectation(Path(directory))
            expectation.status_path.parent.mkdir(parents=True)
            expectation.status_path.write_text("{", encoding="utf-8")
            sleeps: list[float] = []

            def publish_after_first_poll(seconds: float) -> None:
                sleeps.append(seconds)
                expectation.status_path.write_text(
                    json.dumps(_payload(expectation)),
                    encoding="utf-8",
                )

            result = wait_for_graphics_runtime_status(
                expectation,
                process_inspector=_Inspector(),
                clock=lambda: 0.0,
                sleeper=publish_after_first_poll,
            )

        self.assertEqual("wonderbane-extension.graphics", result["producer_id"])
        self.assertEqual([0.1], sleeps)

    def test_wrong_identity_status_times_out_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expectation = _expectation(Path(directory))
            expectation.status_path.parent.mkdir(parents=True)
            payload = _payload(expectation)
            payload["process_identity"]["process_id"] = 9999  # type: ignore[index]
            expectation.status_path.write_text(json.dumps(payload), encoding="utf-8")
            ticks = iter((0.0, 1.0))

            with self.assertRaisesRegex(
                GraphicsRuntimeStatusWaitError,
                "last status was invalid.*process ID",
            ):
                wait_for_graphics_runtime_status(
                    expectation,
                    timeout_seconds=0.5,
                    process_inspector=_Inspector(),
                    clock=lambda: next(ticks),
                    sleeper=lambda _seconds: None,
                )

    def test_exit_or_pid_reuse_aborts_before_status_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expectation = _expectation(Path(directory))
            cases = (
                (_Inspector(None), "exited"),
                (
                    _Inspector(
                        _Lifetime(process_started_at_100ns=CREATION_FILETIME + 1)
                    ),
                    "reused",
                ),
            )
            for inspector, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(
                    GraphicsRuntimeStatusWaitError,
                    message,
                ):
                    wait_for_graphics_runtime_status(
                        expectation,
                        process_inspector=inspector,
                        clock=lambda: 0.0,
                        sleeper=lambda _seconds: None,
                    )

    def test_client_extension_cli_routes_exact_status_expectation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status_directory = root / "status"
            executable = root / "client" / "sb.exe"
            payload = {"runtime_profile": "diagnostics-only"}
            output = StringIO()
            with (
                patch(
                    "shadowbane_lab.client_extension.__main__.wait_for_graphics_runtime_status",
                    return_value=payload,
                ) as wait,
                redirect_stdout(output),
            ):
                result = main(
                    (
                        "wait-graphics-status",
                        str(status_directory),
                        "--process-id",
                        str(PROCESS_ID),
                        "--process-creation-filetime-utc",
                        str(CREATION_FILETIME),
                        "--executable",
                        str(executable),
                        "--executable-sha256",
                        EXECUTABLE_SHA256,
                        "--runtime-profile",
                        "diagnostics-only",
                        "--timeout-seconds",
                        "12.5",
                    )
                )

        self.assertEqual(0, result)
        self.assertEqual(payload, json.loads(output.getvalue()))
        expectation = wait.call_args.args[0]
        self.assertEqual(status_directory, expectation.status_directory)
        self.assertEqual(executable, expectation.executable_path)
        self.assertEqual(12.5, wait.call_args.kwargs["timeout_seconds"])


if __name__ == "__main__":
    unittest.main()
