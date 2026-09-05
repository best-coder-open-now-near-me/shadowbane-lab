import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.travel import (
    LearnedNavigationStateError,
    NavigationCell,
    SparseNavigationMap,
    TravelDestination,
    load_learned_navigation_map,
    save_learned_navigation_map,
)


def _save_observation(path, coordinate, ready, release):
    navigation = load_learned_navigation_map(Path(path))
    cell = NavigationCell(*coordinate)
    navigation.mark_refined_learned_blocked(NavigationCell(cell.x // 2, cell.y // 2), cell)
    ready.put(True)
    if not release.wait(15):
        raise RuntimeError("save barrier timed out")
    save_learned_navigation_map(Path(path), navigation)


def _crash_before_replace(path, ready, release):
    from shadowbane_lab import record_store

    navigation = load_learned_navigation_map(Path(path))
    navigation.mark_learned_blocked(NavigationCell(99, 99))

    def interrupted_publish(target, payload, *, temporary_label):
        def crash(temporary, target):
            ready.set()
            if not release.wait(15):
                raise RuntimeError("crash barrier timed out")
            os._exit(23)

        return record_store.publish_atomic_record(
            target, payload, temporary_label=temporary_label, replacer=crash
        )

    with patch("shadowbane_lab.travel.navigation_state.publish_atomic_record", interrupted_publish):
        save_learned_navigation_map(Path(path), navigation)


class LearnedNavigationStateTests(unittest.TestCase):
    def test_independent_processes_merge_observations_and_reload(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.json"
            ready, release = context.Queue(), context.Event()
            cells = ((8, 10), (9, 11))
            writers = [
                context.Process(target=_save_observation, args=(str(path), cell, ready, release))
                for cell in cells
            ]
            for writer in writers:
                writer.start()
            try:
                for _ in writers:
                    self.assertTrue(ready.get(timeout=15))
                release.set()
                for writer in writers:
                    writer.join(15)
                    self.assertEqual(0, writer.exitcode)
            finally:
                release.set()
                for writer in writers:
                    if writer.is_alive():
                        writer.terminate()
                    writer.join(5)
            restored = load_learned_navigation_map(path)
            self.assertEqual(
                frozenset(NavigationCell(*cell) for cell in cells), restored.refined_learned_blocked
            )
            self.assertEqual(frozenset({NavigationCell(4, 5)}), restored.learned_blocked)
            save_learned_navigation_map(path, restored)
            self.assertEqual(
                restored.refined_learned_blocked,
                load_learned_navigation_map(path).refined_learned_blocked,
            )

    def test_crashed_writer_preserves_previous_generation_and_releases_lock(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.json"
            initial = SparseNavigationMap(cell_size=20.0)
            initial.mark_learned_blocked(NavigationCell(1, 2))
            save_learned_navigation_map(path, initial)
            before = path.read_bytes()
            ready, release = context.Event(), context.Event()
            writer = context.Process(target=_crash_before_replace, args=(str(path), ready, release))
            writer.start()
            try:
                self.assertTrue(ready.wait(15))
                self.assertEqual(before, path.read_bytes())
                release.set()
                writer.join(15)
                self.assertEqual(23, writer.exitcode)
            finally:
                release.set()
                if writer.is_alive():
                    writer.terminate()
                writer.join(5)
            self.assertEqual(before, path.read_bytes())
            recovered = load_learned_navigation_map(path)
            recovered.mark_learned_blocked(NavigationCell(3, 4))
            save_learned_navigation_map(path, recovered)
            self.assertEqual(
                frozenset({NavigationCell(1, 2), NavigationCell(3, 4)}),
                load_learned_navigation_map(path).learned_blocked,
            )

    def test_round_trips_only_live_learned_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learned-navigation.json"
            navigation = SparseNavigationMap(cell_size=20.0)
            navigation.mark_blocked(NavigationCell(2, 3))
            navigation.mark_learned_blocked(NavigationCell(4, 5))

            save_learned_navigation_map(path, navigation)
            restored = load_learned_navigation_map(path)

        self.assertEqual(frozenset({NavigationCell(4, 5)}), restored.learned_blocked)
        self.assertEqual(restored.learned_blocked, restored.blocked)

    def test_round_trips_precise_live_collision_subcells(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learned-navigation.json"
            navigation = SparseNavigationMap(cell_size=20.0)
            navigation.mark_blocked_ahead(
                NativePlayerPositionObservation(88818.8828125, 45040.55859375, 0.0),
                TravelDestination(88819.0, 45122.0),
            )

            save_learned_navigation_map(path, navigation)
            payload = json.loads(path.read_text(encoding="utf-8"))
            restored = load_learned_navigation_map(path)

        self.assertEqual(2, payload["schema_version"])
        self.assertEqual(10.0, payload["refined_cell_size"])
        self.assertEqual(
            frozenset({NavigationCell(8881, 4506)}),
            restored.refined_learned_blocked,
        )

    def test_loads_legacy_coarse_blocker_conservatively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learned-navigation.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cell_size": 20.0,
                        "blocked_cells": [{"x": 4, "y": 5}],
                    }
                ),
                encoding="utf-8",
            )

            restored = load_learned_navigation_map(path)

        self.assertEqual(
            frozenset(
                {
                    NavigationCell(8, 10),
                    NavigationCell(8, 11),
                    NavigationCell(9, 10),
                    NavigationCell(9, 11),
                }
            ),
            restored.refined_learned_blocked,
        )

    def test_missing_state_starts_with_empty_navigation_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            restored = load_learned_navigation_map(Path(directory) / "missing.json")

        self.assertEqual(frozenset(), restored.learned_blocked)

    def test_rejects_state_for_a_different_cell_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "learned-navigation.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "cell_size": 10.0,
                        "blocked_cells": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                LearnedNavigationStateError,
                "different navigation cell size",
            ):
                load_learned_navigation_map(path)


if __name__ == "__main__":
    unittest.main()
