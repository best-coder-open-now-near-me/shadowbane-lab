import json
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.travel import (
    LearnedNavigationStateError,
    NavigationCell,
    SparseNavigationMap,
    TravelDestination,
    load_learned_navigation_map,
    save_learned_navigation_map,
)


class LearnedNavigationStateTests(unittest.TestCase):
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
