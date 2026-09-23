from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.client_observation.native_health import NativeMemoryRegion
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogDebugHit,
    NativeVendorDialogDetachError,
)
from shadowbane_lab.diagnostics.terrain_branch_hits import (
    TERRAIN_OBJECT_SIZE,
    TerrainBranchCompatibilityError,
    TerrainBranchProfile,
    TerrainEdgeBranch,
    _supervised_capture,
    capture_terrain_branch_hits,
)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _profile(extension: bytes) -> TerrainBranchProfile:
    return TerrainBranchProfile(
        profile_id="terrain-test",
        executable_sha256="ab" * 32,
        extension_sha256=_sha256(extension),
        branches=(
            TerrainEdgeBranch("inbound_entry", "edge_0", 0x1000, b"\xeb\x68", 1),
            TerrainEdgeBranch("inbound_complete", "edge_1", 0x1100, b"\xe9\x7a", 2),
            TerrainEdgeBranch("outbound_entry", "edge_2", 0x1200, b"\xe9\x0f", 4),
            TerrainEdgeBranch("outbound_complete", "edge_3", 0x1300, b"\xe9\x84", 8),
        ),
    )


class FakeBackend:
    pid = 77
    executable_name = "sb.exe"
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4
    process_creation_filetime_utc = 123456

    def __init__(self, root: Path, profile: TerrainBranchProfile, clock: Clock) -> None:
        self.executable_path = root / "sb.exe"
        self.memory: dict[int, bytes] = {
            self.base_address + branch.rva: branch.signature for branch in profile.branches
        }
        self.clock = clock
        self.hits: list[NativeVendorDialogDebugHit] = []
        self.attached: dict[str, int] | None = None
        self.continued: list[tuple[str, bool]] = []
        self.closed = False
        self.detach_error = False

    def read_block(self, address: int, size: int) -> bytes:
        for start, value in self.memory.items():
            if start <= address and address + size <= start + len(value):
                offset = address - start
                return value[offset : offset + size]
        raise OSError(f"unmapped test read at {address:#x}")

    def query_region(self, address: int) -> NativeMemoryRegion:
        return NativeMemoryRegion(address, TERRAIN_OBJECT_SIZE, 4, 0x20000)

    def attach(self, breakpoints: dict[str, int]) -> None:
        self.attached = dict(breakpoints)

    def wait_for_hit(self, timeout_ms: int) -> NativeVendorDialogDebugHit | None:
        if self.hits:
            self.clock.value += 0.001
            return self.hits.pop(0)
        self.clock.value += timeout_ms / 1000
        return None

    def continue_hit(
        self,
        hit: NativeVendorDialogDebugHit,
        *,
        disable_role: bool = False,
    ) -> None:
        self.continued.append((hit.role, disable_role))

    def close(self) -> None:
        self.closed = True
        if self.detach_error:
            raise NativeVendorDialogDetachError(
                "DebugActiveProcessStop failed: access denied"
            )


def _hit(
    role: str,
    address: int,
    object_address: int,
    *,
    thread_id: int = 9,
) -> NativeVendorDialogDebugHit:
    return NativeVendorDialogDebugHit(
        role=role,
        process_id=77,
        thread_id=thread_id,
        instruction_address=address,
        registers={"ebx": object_address, "eip": address},
    )


def _terrain_object() -> bytes:
    raw = bytearray(TERRAIN_OBJECT_SIZE)
    for offset, begin, count in (
        (0x150, 0x200000, 2),
        (0x15C, 0x210000, 2),
        (0x168, 0x220000, 2),
    ):
        struct.pack_into("<II", raw, offset, begin, begin + count * 4)
    struct.pack_into("<I", raw, 0x1A4, 0x230000)
    raw[0x1AC] = 5
    raw[0x1AD] = 0
    return bytes(raw)


class TerrainBranchHitTests(unittest.TestCase):
    def test_retains_one_bounded_snapshot_per_branch_and_writes_one_json(self) -> None:
        extension = b"reviewed extension"
        profile = _profile(extension)
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "wonderbane-extension.dll").write_bytes(extension)
            backend = FakeBackend(root, profile, clock)
            object_address = 0x600000
            backend.memory[object_address] = _terrain_object()
            backend.hits = [
                _hit(branch.role, backend.base_address + branch.rva, object_address)
                for branch in profile.branches
            ]
            output = root / "capture.json"

            result = capture_terrain_branch_hits(
                backend,
                output,
                expected_creation_filetime=backend.process_creation_filetime_utc,
                timeout_seconds=2,
                profile=profile,
                monotonic=clock,
            )

            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("captured", result["status"])
        self.assertEqual(4, saved["unique_branch_count"])
        self.assertEqual(4, saved["hit_event_count"])
        self.assertEqual(
            [("inbound_entry", True), ("inbound_complete", True),
             ("outbound_entry", True), ("outbound_complete", True)],
            backend.continued,
        )
        self.assertEqual(2, saved["observations"][0]["terrain_object"]["color_textures"]["count"])
        self.assertEqual(5, saved["observations"][0]["terrain_object"]["direction_completion_bits"])
        self.assertEqual(
            0,
            saved["observations"][0]["terrain_object"]["dirty_flag_before_repaired_jump"],
        )
        self.assertEqual(
            saved["repaired_signatures_before"],
            saved["repaired_signatures_while_attached"],
        )
        self.assertFalse(saved["scope"]["client_code_writes"])
        self.assertTrue(backend.closed)

    def test_stationary_timeout_is_explicitly_no_branch_activity(self) -> None:
        extension = b"reviewed extension"
        profile = _profile(extension)
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "wonderbane-extension.dll").write_bytes(extension)
            backend = FakeBackend(root, profile, clock)
            output = root / "capture.json"

            result = capture_terrain_branch_hits(
                backend,
                output,
                expected_creation_filetime=backend.process_creation_filetime_utc,
                timeout_seconds=1,
                profile=profile,
                monotonic=clock,
            )

        self.assertEqual("captured_no_branch_activity", result["status"])
        self.assertEqual(0, result["unique_branch_count"])
        self.assertTrue(backend.closed)

    def test_executable_mismatch_fails_before_attach(self) -> None:
        extension = b"reviewed extension"
        profile = _profile(extension)
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "wonderbane-extension.dll").write_bytes(extension)
            backend = FakeBackend(root, profile, clock)
            backend.executable_sha256 = "cd" * 32

            with self.assertRaisesRegex(TerrainBranchCompatibilityError, "executable SHA-256"):
                capture_terrain_branch_hits(
                    backend,
                    root / "capture.json",
                    expected_creation_filetime=backend.process_creation_filetime_utc,
                    timeout_seconds=1,
                    profile=profile,
                    monotonic=clock,
                )

        self.assertIsNone(backend.attached)
        self.assertFalse(backend.closed)

    def test_existing_output_fails_before_target_validation_or_attach(self) -> None:
        extension = b"reviewed extension"
        profile = _profile(extension)
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "wonderbane-extension.dll").write_bytes(extension)
            output = root / "capture.json"
            output.write_text("preserve", encoding="utf-8")
            backend = FakeBackend(root, profile, clock)

            with self.assertRaises(FileExistsError):
                capture_terrain_branch_hits(
                    backend,
                    output,
                    expected_creation_filetime=backend.process_creation_filetime_utc,
                    timeout_seconds=1,
                    profile=profile,
                    monotonic=clock,
                )

            self.assertEqual("preserve", output.read_text(encoding="utf-8"))
        self.assertIsNone(backend.attached)

    def test_worker_can_defer_only_explicit_detach_verification_to_parent(self) -> None:
        extension = b"reviewed extension"
        profile = _profile(extension)
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "wonderbane-extension.dll").write_bytes(extension)
            backend = FakeBackend(root, profile, clock)
            backend.detach_error = True
            output = root / "worker.json"

            result = capture_terrain_branch_hits(
                backend,
                output,
                expected_creation_filetime=backend.process_creation_filetime_utc,
                timeout_seconds=1,
                profile=profile,
                monotonic=clock,
                allow_process_exit_detach=True,
            )

        self.assertFalse(result["cleanup"]["explicit_detach_succeeded"])
        self.assertTrue(result["cleanup"]["process_exit_detach_required"])
        self.assertTrue(result["cleanup"]["debug_register_clear_completed"])

    def test_supervisor_publishes_only_after_post_exit_verification(self) -> None:
        extension = b"reviewed extension"
        profile = _profile(extension)
        clock = Clock()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "wonderbane-extension.dll").write_bytes(extension)
            process = FakeBackend(root, profile, clock)
            output = root / "final.json"

            def run_worker(command: list[str], **_kwargs: object) -> SimpleNamespace:
                pending = Path(command[command.index("--output") + 1])
                pending.write_text(
                    json.dumps({
                        "schema_version": 1,
                        "status": "captured_no_branch_activity",
                        "process_id": process.pid,
                        "process_creation_filetime_utc": (
                            process.process_creation_filetime_utc
                        ),
                        "unique_branch_count": 0,
                        "hit_event_count": 0,
                        "cleanup": {
                            "debug_register_clear_completed": True,
                            "explicit_detach_succeeded": False,
                            "process_exit_detach_required": True,
                        },
                    }),
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                patch(
                    "shadowbane_lab.diagnostics.terrain_branch_hits.PROFILE",
                    profile,
                ),
                patch(
                    "shadowbane_lab.diagnostics.terrain_branch_hits.subprocess.run",
                    side_effect=run_worker,
                ),
                patch(
                    "shadowbane_lab.diagnostics.terrain_branch_hits."
                    "WindowsReadOnlyProcessMemory.open_for_process",
                    return_value=process,
                ),
                patch(
                    "shadowbane_lab.diagnostics.terrain_branch_hits."
                    "_remote_debugger_present",
                    return_value=False,
                ),
            ):
                result = _supervised_capture(
                    process_id=process.pid,
                    creation_filetime=process.process_creation_filetime_utc,
                    output_path=output,
                    timeout_seconds=1,
                    input_mode="none",
                )

            saved = json.loads(output.read_text(encoding="utf-8"))
            pending_files = tuple(root.glob("*.debugger-worker"))

        self.assertTrue(result["cleanup"]["debugger_worker_exited"])
        self.assertFalse(saved["cleanup"]["post_exit_debugger_present"])
        self.assertEqual({}, {path.name: path for path in pending_files})
