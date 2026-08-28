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
    AStarTravelController,
    NavigationMapSnapshot,
    SparseNavigationMap,
    TerrainNavigationConfig,
    TravelControllerConfig,
    TravelDestination,
    TravelManeuver,
    TravelObservation,
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
    def __init__(self, navigation_map: SparseNavigationMap) -> None:
        self.snapshot = NavigationMapSnapshot("static:1", navigation_map)

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


class ActiveZoneTerrainNavigationSourceTests(unittest.TestCase):
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
