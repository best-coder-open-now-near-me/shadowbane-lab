from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation import (
    NATIVE_PLAYER_SNAPSHOT_SCHEMA_VERSION,
    NativePlayerProgressionCoreObservation,
    NativePlayerProgressionCoreProfile,
    NativePlayerSnapshot,
    NativePlayerSnapshotCompatibilityError,
    NativePlayerSnapshotProfiles,
    NativePlayerSnapshotReader,
    NativePlayerTrainingObservation,
    NativePlayerTrainingProfile,
    NativePlayerVitalsObservation,
    NativePlayerVitalsProfile,
)


def _progression_profile() -> NativePlayerProgressionCoreProfile:
    return NativePlayerProgressionCoreProfile(
        profile_id="native-progression-core-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        training_points_offset=0xC20,
        ability_points_offset=0xCAC,
        level_offset=0xCC0,
        left_attack_rating_offset=0xCFC,
        right_attack_rating_offset=0xD00,
        defense_offset=0xD04,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_level=75,
        maximum_plausible_points=10_000,
        maximum_plausible_rating=100_000,
    )


def _training_profile() -> NativePlayerTrainingProfile:
    return NativePlayerTrainingProfile(
        profile_id="native-training-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        skill_vector_offset=0xC24,
        power_vector_offset=0x670,
        vector_entry_size=16,
        maximum_skill_count=16,
        maximum_power_count=32,
        maximum_plausible_rank=1_000,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        skill_tokens=(),
        power_tokens=(),
    )


def _vitals_profile() -> NativePlayerVitalsProfile:
    return NativePlayerVitalsProfile(
        profile_id="native-vitals-test",
        executable_name="sb.exe",
        executable_sha256="ab" * 32,
        pointer_size=4,
        player_pointer_rva=0x200,
        current_health_offset=0x5CC,
        maximum_health_offset=0x5D0,
        current_mana_offset=0xCD4,
        maximum_mana_offset=0xCD0,
        current_stamina_offset=0xCDC,
        maximum_stamina_offset=0xCD8,
        minimum_user_address=0x10000,
        maximum_user_address=0x7FFEFFFF,
        maximum_plausible_vital=1_000_000,
    )


def _profiles() -> NativePlayerSnapshotProfiles:
    return NativePlayerSnapshotProfiles(
        progression=_progression_profile(),
        training=_training_profile(),
        vitals=_vitals_profile(),
    )


def _progression() -> NativePlayerProgressionCoreObservation:
    return NativePlayerProgressionCoreObservation(59, 168, 113, 366, 366, 150)


def _training() -> NativePlayerTrainingObservation:
    return NativePlayerTrainingObservation(skills=(), powers=())


def _vitals() -> NativePlayerVitalsObservation:
    return NativePlayerVitalsObservation(1075.375, 1075.375, 53.75, 63.75, 324.0, 324.0)


class _FakeProcessMemory:
    pid = 52
    process_creation_filetime_utc = 133_000_000_000_000_000
    executable_name = "sb.exe"
    executable_path = Path("C:/Wonderbane/sb.exe")
    executable_sha256 = "ab" * 32
    base_address = 0x400000
    pointer_size = 4

    def __init__(self) -> None:
        self.close_count = 0

    def read(self, address: int, size: int) -> bytes:
        raise AssertionError(f"unexpected direct read at 0x{address:X} for {size} bytes")

    def close(self) -> None:
        self.close_count += 1


class _ObservationReader:
    def __init__(self, observation: object) -> None:
        self._observation = observation

    def observe(self) -> object:
        return self._observation


class NativePlayerSnapshotReaderTests(unittest.TestCase):
    def test_composes_all_observations_through_one_exact_process(self) -> None:
        profiles = _profiles()
        process = _FakeProcessMemory()
        times = iter(
            (
                process.process_creation_filetime_utc + 100,
                process.process_creation_filetime_utc + 200,
            )
        )
        progression_reader = _ObservationReader(_progression())
        training_reader = _ObservationReader(_training())
        vitals_reader = _ObservationReader(_vitals())
        with (
            patch(
                "shadowbane_lab.client_observation.native_snapshot."
                "NativePlayerProgressionCoreReader",
                return_value=progression_reader,
            ) as open_progression,
            patch(
                "shadowbane_lab.client_observation.native_snapshot.NativePlayerTrainingReader",
                return_value=training_reader,
            ) as open_training,
            patch(
                "shadowbane_lab.client_observation.native_snapshot.NativePlayerVitalsReader",
                return_value=vitals_reader,
            ) as open_vitals,
        ):
            reader = NativePlayerSnapshotReader(
                profiles,
                process,
                filetime_clock=lambda: next(times),
            )
            snapshot = reader.observe()
            reader.close()

        self.assertIs(open_progression.call_args.args[1], process)
        self.assertIs(open_training.call_args.args[1], process)
        self.assertIs(open_vitals.call_args.args[1], process)
        self.assertEqual(
            (52, process.process_creation_filetime_utc), snapshot.exact_process_identity
        )
        self.assertEqual(16, len(snapshot.snapshot_token))
        self.assertEqual(1, process.close_count)
        payload = snapshot.as_dict()
        self.assertEqual(NATIVE_PLAYER_SNAPSHOT_SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual(snapshot.snapshot_token, payload["snapshot_token"])
        self.assertEqual(59, payload["progression"]["level"])
        self.assertEqual(53.75, payload["vitals"]["current_mana"])
        self.assertEqual(52, payload["training"]["process_id"])

    def test_rejects_profiles_from_different_executable_layouts(self) -> None:
        training = replace(_training_profile(), executable_sha256="cd" * 32)

        with self.assertRaisesRegex(
            NativePlayerSnapshotCompatibilityError,
            "one executable hash",
        ):
            NativePlayerSnapshotProfiles(
                progression=_progression_profile(),
                training=training,
                vitals=_vitals_profile(),
            )


class _FakeSnapshotReader:
    def __init__(self, snapshot: NativePlayerSnapshot) -> None:
        self.snapshot = snapshot

    def __enter__(self) -> _FakeSnapshotReader:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def observe(self) -> NativePlayerSnapshot:
        return self.snapshot


def _snapshot() -> NativePlayerSnapshot:
    creation = 133_000_000_000_000_000
    return NativePlayerSnapshot(
        process_id=52,
        process_creation_filetime_utc=creation,
        executable_path=Path("C:/Wonderbane/sb.exe"),
        executable_sha256="ab" * 32,
        capture_started_at_filetime_utc=creation + 100,
        captured_at_filetime_utc=creation + 200,
        progression_profile_id="native-progression-core-test",
        training_profile_id="native-training-test",
        vitals_profile_id="native-vitals-test",
        progression=_progression(),
        training=_training(),
        vitals=_vitals(),
        snapshot_token="0123456789abcdef",
    )


class NativePlayerSnapshotCliTests(unittest.TestCase):
    def test_command_emits_identity_bound_composite_payload(self) -> None:
        profiles = _profiles()
        output = io.StringIO()
        with (
            patch(
                "shadowbane_lab.cli.load_bundled_native_player_snapshot_profiles",
                return_value=profiles,
            ),
            patch(
                "shadowbane_lab.cli.open_windows_native_player_snapshot_reader",
                return_value=_FakeSnapshotReader(_snapshot()),
            ) as open_snapshot,
            redirect_stdout(output),
        ):
            result = main(
                (
                    "client",
                    "observe-native-snapshot",
                    "--process-id",
                    "4320",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertEqual("0123456789abcdef", payload["snapshot_token"])
        self.assertEqual(52, payload["process_identity"]["process_id"])
        self.assertEqual(59, payload["progression"]["level"])
        open_snapshot.assert_called_once_with(profiles, process_id=4320)


class NativePlayerSnapshotExporterTests(unittest.TestCase):
    def test_exporter_invokes_only_the_composite_snapshot(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "export-wonderbane-sim-observation.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("observe-native-snapshot --json", script)
        self.assertNotIn("observe-native-progression --json", script)
        self.assertNotIn("observe-native-training --json", script)
        self.assertNotIn("observe-native-player --json", script)
        self.assertIn("snapshot_token", script)
        self.assertIn("process_identity", script)


if __name__ == "__main__":
    unittest.main()
