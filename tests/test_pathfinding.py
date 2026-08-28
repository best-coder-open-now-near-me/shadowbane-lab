import unittest

from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.travel import (
    NavigationCell,
    SparseNavigationMap,
    TravelDestination,
    WeightedAStarConfig,
    WeightedAStarPlanner,
)


class WeightedAStarTests(unittest.TestCase):
    def test_direct_route_smooths_to_exact_destination(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        route = WeightedAStarPlanner().plan(
            navigation,
            start_lt=5.0,
            start_lg=5.0,
            destination=TravelDestination(95.0, 5.0, 6.0),
        )

        self.assertEqual(2, len(route.cells))
        self.assertEqual((95.0, 5.0), (route.destinations[-1].lt, route.destinations[-1].lg))

    def test_blocked_corridor_routes_around_clearance_instead_of_corner_cutting(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        for y in (-1, 0, 1):
            position = NativePlayerPositionObservation(15.0, y * 10.0 + 5.0, 0.0)
            navigation.mark_blocked_ahead(
                position,
                TravelDestination(25.0, y * 10.0 + 5.0),
            )
        planner = WeightedAStarPlanner(
            WeightedAStarConfig(
                planning_margin_cells=6,
                obstacle_clearance_cells=0,
            )
        )

        route = planner.plan(
            navigation,
            start_lt=5.0,
            start_lg=5.0,
            destination=TravelDestination(55.0, 5.0, 5.0),
        )

        blocked = navigation.blocked
        self.assertTrue(all(cell not in blocked for cell in route.cells))
        self.assertGreater(len(route.cells), 2)
        self.assertTrue(any(cell.y not in (-1, 0, 1) for cell in route.cells))

    def test_learned_obstacle_grid_is_global_and_bounded_per_plan(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)
        blocked = navigation.mark_blocked_ahead(
            NativePlayerPositionObservation(10.0, 10.0, 0.0),
            TravelDestination(100.0, 10.0),
        )
        planner = WeightedAStarPlanner(
            WeightedAStarConfig(
                planning_margin_cells=3,
                obstacle_clearance_cells=1,
            )
        )
        start = NavigationCell(0, 0)
        goal = NavigationCell(5, 0)

        grid = navigation.local_grid(start, goal, planner.config)

        self.assertEqual(NavigationCell(1, 0), blocked)
        self.assertIn(blocked, grid.blocked)
        self.assertEqual(NavigationCell(-3, -3), grid.minimum)
        self.assertEqual(NavigationCell(8, 3), grid.maximum)

    def test_zero_clearance_keeps_single_obstacle_detour_local(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)
        navigation.mark_blocked_ahead(
            NativePlayerPositionObservation(10.0, 10.0, 0.0),
            TravelDestination(200.0, 10.0),
        )
        planner = WeightedAStarPlanner(
            WeightedAStarConfig(
                obstacle_clearance_cells=0,
                waypoint_radius_fraction=0.5,
            )
        )

        route = planner.plan(
            navigation,
            start_lt=10.0,
            start_lg=10.0,
            destination=TravelDestination(200.0, 10.0),
        )

        self.assertEqual(2, len(route.destinations))
        detour = route.destinations[0]
        self.assertEqual((10.0, -10.0), (detour.lt, detour.lg))
        self.assertEqual(10.0, detour.arrival_radius)


if __name__ == "__main__":
    unittest.main()
