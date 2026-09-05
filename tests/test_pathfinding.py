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

    def test_blocked_ahead_uses_first_boundary_crossed_by_nearly_cardinal_route(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)
        navigation.set_cost(NavigationCell(4440, 2253), 8.0)

        blocked = navigation.mark_blocked_ahead(
            NativePlayerPositionObservation(88818.8828125, 45040.55859375, 0.0),
            TravelDestination(88819.0, 45122.0),
        )

        self.assertEqual(NavigationCell(4440, 2253), blocked)

    def test_blocked_ahead_keeps_true_diagonal_fallback(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)

        blocked = navigation.mark_blocked_ahead(
            NativePlayerPositionObservation(5.0, 5.0, 0.0),
            TravelDestination(35.0, 35.0),
        )

        self.assertEqual(NavigationCell(1, 1), blocked)

    def test_live_collision_marks_only_the_entered_refined_child(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)
        navigation.set_cost(NavigationCell(4440, 2253), 8.0)

        blocked = navigation.mark_blocked_ahead(
            NativePlayerPositionObservation(88818.8828125, 45040.55859375, 0.0),
            TravelDestination(88819.0, 45122.0),
        )
        refined = navigation.refined_navigation_map()

        self.assertEqual(NavigationCell(4440, 2253), blocked)
        self.assertEqual(
            frozenset({NavigationCell(8881, 4506)}),
            navigation.refined_learned_blocked,
        )
        self.assertIn(NavigationCell(8881, 4506), refined.blocked)
        self.assertNotIn(NavigationCell(8880, 4506), refined.blocked)
        self.assertNotIn(NavigationCell(8881, 4507), refined.blocked)
        grid = refined.local_grid(
            NavigationCell(8880, 4506),
            NavigationCell(8881, 4507),
            WeightedAStarConfig(obstacle_clearance_cells=0),
        )
        self.assertEqual(8.0, grid.traversal_cost(NavigationCell(8880, 4506)))
        self.assertEqual(8.0, grid.traversal_cost(NavigationCell(8881, 4507)))

    def test_refinement_keeps_structural_walls_solid_and_foliage_traversable(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)
        navigation.mark_blocked(NavigationCell(0, 0))
        navigation.set_cost(NavigationCell(1, 0), 8.0)

        refined = navigation.refined_navigation_map()
        grid = refined.local_grid(
            NavigationCell(2, 0),
            NavigationCell(5, 0),
            WeightedAStarConfig(
                planning_margin_cells=2,
                obstacle_clearance_cells=0,
            ),
        )

        self.assertTrue(
            {
                NavigationCell(0, 0),
                NavigationCell(0, 1),
                NavigationCell(1, 0),
                NavigationCell(1, 1),
            }.issubset(refined.blocked)
        )
        for child in (
            NavigationCell(2, 0),
            NavigationCell(2, 1),
            NavigationCell(3, 0),
            NavigationCell(3, 1),
        ):
            self.assertNotIn(child, refined.blocked)
            self.assertEqual(8.0, grid.traversal_cost(child))

    def test_refined_plan_is_bounded_to_one_local_route_slice(self) -> None:
        navigation = SparseNavigationMap(cell_size=20.0)
        navigation.mark_blocked_ahead(
            NativePlayerPositionObservation(10.0, 10.0, 0.0),
            TravelDestination(200.0, 10.0),
        )
        planner = WeightedAStarPlanner(
            WeightedAStarConfig(obstacle_clearance_cells=0)
        )

        route = planner.plan_refined(
            navigation,
            start_lt=10.0,
            start_lg=10.0,
            destination=TravelDestination(200.0, 10.0),
            maximum_distance=120.0,
        )

        self.assertEqual((130.0, 10.0), (route.destinations[-1].lt, route.destinations[-1].lg))
        self.assertTrue(any(cell.y != 1 for cell in route.cells))

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

    def test_smoothing_preserves_astar_detour_around_weighted_terrain(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        navigation.set_cost(NavigationCell(2, 0), 8.0)
        planner = WeightedAStarPlanner(
            WeightedAStarConfig(
                planning_margin_cells=4,
                obstacle_clearance_cells=0,
            )
        )

        route = planner.plan(
            navigation,
            start_lt=5.0,
            start_lg=5.0,
            destination=TravelDestination(45.0, 5.0, 5.0),
        )

        self.assertGreater(len(route.cells), 2)
        self.assertNotIn(NavigationCell(2, 0), route.cells)
        self.assertGreater(len(route.destinations), 1)

    def test_partial_route_uses_reachable_window_edge_beside_complete_barrier(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        for y in range(-2, 3):
            navigation.mark_blocked(NavigationCell(3, y))
        planner = WeightedAStarPlanner(
            WeightedAStarConfig(
                planning_margin_cells=2,
                obstacle_clearance_cells=0,
            )
        )

        route = planner.plan_reachable_frontier(
            navigation,
            start_lt=5.0,
            start_lg=5.0,
            destination=TravelDestination(65.0, 5.0, 5.0),
        )

        self.assertEqual(2, route.cells[-1].x)
        self.assertEqual(2, abs(route.cells[-1].y))
        self.assertEqual(25.0, route.destinations[-1].lt)
        self.assertEqual(15.0, abs(route.destinations[-1].lg))
        self.assertTrue(all(cell.x < 3 for cell in route.cells))


if __name__ == "__main__":
    unittest.main()
