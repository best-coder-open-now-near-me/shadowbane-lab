import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shadowbane_lab.client_observation import (
    NativePlayerPositionObservation,
    NativePlayerVitalsObservation,
)
from shadowbane_lab.travel import (
    ActiveZoneTerrainNavigation,
    ActiveZoneTerrainNavigationSource,
    AStarRouteNotFound,
    AStarTravelController,
    NavigationCell,
    NavigationMapSnapshot,
    NavigationPlanningWindow,
    SparseNavigationMap,
    TerrainNavigationConfig,
    TravelControllerConfig,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
    TravelPhase,
    WeightedAStarConfig,
    WeightedAStarPlanner,
)


def _position(lt: float, lg: float) -> NativePlayerPositionObservation:
    return NativePlayerPositionObservation(lt, lg, 0.0)


def _observation(now_ms: int, lt: float, lg: float) -> TravelObservation:
    return TravelObservation(
        now_ms,
        _position(lt, lg),
        NativePlayerVitalsObservation(100, 100, 100, 100, 100, 100),
    )


class StaticNavigationSource:
    def __init__(
        self,
        navigation_map: SparseNavigationMap,
        planning_window: NavigationPlanningWindow | None = None,
    ) -> None:
        self.snapshot = NavigationMapSnapshot(
            "static:1",
            navigation_map,
            planning_window,
        )

    def observe(self, _position) -> NavigationMapSnapshot:
        return self.snapshot


class AStarTravelControllerTests(unittest.TestCase):
    def test_initial_route_uses_known_obstacle_waypoints(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        navigation.mark_blocked_ahead(
            _position(5.0, 5.0),
            TravelDestination(95.0, 5.0, 5.0),
        )
        controller = AStarTravelController(
            TravelDestination(95.0, 5.0, 5.0),
            TravelControllerConfig(click_interval_ms=100),
            StaticNavigationSource(navigation),
        )

        decision = controller.step(_observation(0, 5.0, 5.0))

        self.assertEqual(TravelManeuver.DIRECT, decision.maneuver)
        self.assertIsNotNone(decision.minimap_direction)
        assert decision.minimap_direction is not None
        self.assertLess(decision.minimap_direction.x, 0.0)
        assert controller.active_plan is not None
        self.assertGreater(len(controller.active_plan.destinations), 1)

    def test_stall_marks_obstacle_and_replans_without_counting_hidden_escape(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        controller = AStarTravelController(
            TravelDestination(95.0, 5.0, 5.0),
            TravelControllerConfig(
                click_interval_ms=100,
                minimum_progress=5.0,
                maximum_no_progress_clicks=1,
            ),
            StaticNavigationSource(navigation),
        )

        first = controller.step(_observation(0, 5.0, 5.0))
        second = controller.step(_observation(100, 5.0, 5.0))

        self.assertEqual(1, first.click_count)
        self.assertEqual(2, second.click_count)
        self.assertEqual(TravelManeuver.DIRECT, second.maneuver)
        self.assertEqual(1, controller.replan_count)
        self.assertTrue(navigation.blocked)
        assert second.minimap_direction is not None
        self.assertLess(second.minimap_direction.x, 0.0)

    def test_far_destination_plans_to_receding_terrain_horizon(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        controller = AStarTravelController(
            TravelDestination(500.0, 5.0, 5.0),
            TravelControllerConfig(click_interval_ms=100),
            StaticNavigationSource(
                navigation,
                NavigationPlanningWindow(5.0, 5.0, 100.0, 50.0),
            ),
        )

        decision = controller.step(_observation(0, 5.0, 5.0))

        self.assertEqual(TravelPhase.TRAVELING, decision.phase)
        self.assertEqual("astar_horizon", controller.route_mode)
        self.assertEqual(0, controller.direct_fallback_count)
        assert controller.active_plan is not None
        horizon = controller.active_plan.destinations[-1]
        self.assertGreater(horizon.lt, 55.0)
        self.assertLess(horizon.lt, 500.0)

    def test_far_destination_uses_reachable_frontier_when_local_horizon_has_no_route(self) -> None:
        class NoRoutePlanner(WeightedAStarPlanner):
            def plan(self, *_args, **_kwargs):
                raise AStarRouteNotFound("local terrain is disconnected")

        navigation = SparseNavigationMap(cell_size=10.0)
        controller = AStarTravelController(
            TravelDestination(500.0, 5.0, 5.0),
            TravelControllerConfig(click_interval_ms=100),
            StaticNavigationSource(
                navigation,
                NavigationPlanningWindow(5.0, 5.0, 100.0, 50.0),
            ),
            planner=NoRoutePlanner(),
        )

        decision = controller.step(_observation(0, 5.0, 5.0))

        self.assertEqual(TravelPhase.TRAVELING, decision.phase)
        self.assertEqual(TravelManeuver.DIRECT, decision.maneuver)
        self.assertEqual("astar_partial", controller.route_mode)
        self.assertEqual(0, controller.direct_fallback_count)
        self.assertEqual(1, controller.partial_route_count)
        assert controller.active_plan is not None
        self.assertLess(controller.active_plan.destinations[-1].lt, 500.0)

    def test_far_destination_stops_when_no_safe_frontier_exists(self) -> None:
        class NoRoutePlanner(WeightedAStarPlanner):
            def plan(self, *_args, **_kwargs):
                raise AStarRouteNotFound("local terrain is disconnected")

            def plan_reachable_frontier(self, *_args, **_kwargs):
                raise AStarRouteNotFound("no safe reachable frontier")

        controller = AStarTravelController(
            TravelDestination(500.0, 5.0, 5.0),
            TravelControllerConfig(click_interval_ms=100),
            StaticNavigationSource(
                SparseNavigationMap(cell_size=10.0),
                NavigationPlanningWindow(5.0, 5.0, 100.0, 50.0),
            ),
            planner=NoRoutePlanner(),
        )

        decision = controller.step(_observation(0, 5.0, 5.0))

        self.assertEqual(TravelPhase.STOPPED, decision.phase)
        self.assertEqual(0, decision.click_count)
        self.assertIn("no safe reachable frontier", decision.terminal_reason)

    def test_partial_frontier_slides_window_and_continues_around_large_barrier(self) -> None:
        navigation = SparseNavigationMap(cell_size=10.0)
        for y in range(-12, 13):
            navigation.mark_blocked(NavigationCell(3, y))
        controller = AStarTravelController(
            TravelDestination(500.0, 5.0, 5.0),
            TravelControllerConfig(click_interval_ms=100),
            StaticNavigationSource(
                navigation,
                NavigationPlanningWindow(5.0, 5.0, 100.0, 50.0),
            ),
            planner=WeightedAStarPlanner(
                WeightedAStarConfig(
                    planning_margin_cells=8,
                    obstacle_clearance_cells=0,
                )
            ),
        )

        first = controller.step(_observation(0, 5.0, 5.0))
        assert controller.active_plan is not None
        frontier = controller.active_plan.destinations[-1]
        continued = controller.step(_observation(100, frontier.lt, frontier.lg))

        self.assertEqual(TravelPhase.TRAVELING, first.phase)
        self.assertEqual(TravelPhase.TRAVELING, continued.phase)
        self.assertEqual(2, continued.click_count)
        self.assertEqual(1, controller.replan_count)
        self.assertNotEqual("astar_partial", controller.route_mode)
        assert controller.active_plan is not None
        self.assertTrue(
            any(
                destination.lt > 35.0 and abs(destination.lg) >= 125.0
                for destination in controller.active_plan.destinations
            )
        )

    def test_local_no_route_remains_terminal_instead_of_crossing_known_terrain(self) -> None:
        class NoRoutePlanner(WeightedAStarPlanner):
            def plan(self, *_args, **_kwargs):
                raise AStarRouteNotFound("local terrain is disconnected")

        controller = AStarTravelController(
            TravelDestination(50.0, 5.0, 5.0),
            TravelControllerConfig(click_interval_ms=100),
            StaticNavigationSource(
                SparseNavigationMap(cell_size=10.0),
                NavigationPlanningWindow(5.0, 5.0, 100.0, 50.0),
            ),
            planner=NoRoutePlanner(),
        )

        decision = controller.step(_observation(0, 5.0, 5.0))

        self.assertEqual(TravelPhase.STOPPED, decision.phase)
        self.assertIn("astar_route_not_found", decision.terminal_reason)
        self.assertEqual(0, controller.direct_fallback_count)


class ActiveZoneTerrainNavigationSourceTests(unittest.TestCase):
    def test_uses_injected_map_so_learned_obstacles_survive_route_instances(self) -> None:
        zone = SimpleNamespace(name="Camp", zone_token="zone-a")
        reader = SimpleNamespace(observe=lambda: zone)
        navigation = SparseNavigationMap(cell_size=10.0)
        navigation.mark_blocked_ahead(
            _position(5.0, 5.0),
            TravelDestination(95.0, 5.0, 5.0),
        )
        source = ActiveZoneTerrainNavigationSource(
            "cache",
            reader,
            TerrainNavigationConfig(cell_size=10.0),
            navigation_map=navigation,
        )

        with patch(
            "shadowbane_lab.travel.terrain.load_active_zone_terrain_navigation",
            return_value=ActiveZoneTerrainNavigation(navigation, None),
        ):
            snapshot = source.observe(_position(5.0, 5.0))

        self.assertIs(navigation, snapshot.navigation_map)
        self.assertTrue(snapshot.navigation_map.learned_blocked)

    def test_refreshes_on_window_distance_and_zone_change_while_reusing_map(self) -> None:
        zone = SimpleNamespace(name="Camp", zone_token="zone-a")
        reader = SimpleNamespace(observe=lambda: zone)
        config = TerrainNavigationConfig(cell_size=10.0, seed_radius=100.0)
        source = ActiveZoneTerrainNavigationSource("cache", reader, config)
        seen_maps = []

        def load(_cache, _zone, _position, _config, *, navigation_map):
            seen_maps.append(navigation_map)
            return ActiveZoneTerrainNavigation(navigation_map, None)

        with patch(
            "shadowbane_lab.travel.terrain.load_active_zone_terrain_navigation",
            side_effect=load,
        ):
            first = source.observe(_position(0.0, 0.0))
            same = source.observe(_position(20.0, 0.0))
            moved = source.observe(_position(60.0, 0.0))
            zone.zone_token = "zone-b"
            changed = source.observe(_position(65.0, 0.0))

        self.assertIs(first, same)
        self.assertNotEqual(first.token, moved.token)
        self.assertNotEqual(moved.token, changed.token)
        self.assertEqual(3, source.refresh_count)
        self.assertTrue(all(item is seen_maps[0] for item in seen_maps))


if __name__ == "__main__":
    unittest.main()
