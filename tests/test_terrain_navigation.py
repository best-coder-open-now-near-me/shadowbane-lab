import unittest

from shadowbane_lab.client_observation import NativeZoneGeometry
from shadowbane_lab.travel import (
    NavigationCell,
    SparseNavigationMap,
    TerrainNavigationConfig,
    seed_height_raster_navigation,
)
from shadowbane_lab.world_data import TerrainAlphaRaster


def _geometry() -> NativeZoneGeometry:
    return NativeZoneGeometry(
        minimum_local_x=-20.0,
        minimum_local_z=-20.0,
        maximum_local_x=20.0,
        maximum_local_z=20.0,
        rotation_w=1.0,
        rotation_x=0.0,
        rotation_y=0.0,
        rotation_z=0.0,
        absolute_center_x=0.0,
        absolute_center_z=0.0,
        local_center_x=0.0,
        local_center_z=0.0,
        radius_x=20.0,
        radius_z=20.0,
    )


class TerrainNavigationTests(unittest.TestCase):
    def test_steep_height_transition_seeds_global_blocked_cells(self) -> None:
        rows = [bytes((20, 20, 255, 255, 255)) for _ in range(5)]
        raster = TerrainAlphaRaster(7, 1, 5, 5, b"".join(rows))
        navigation = SparseNavigationMap(cell_size=10.0)

        seed = seed_height_raster_navigation(
            navigation,
            geometry=_geometry(),
            raster=raster,
            zone_depth=0,
            template_group_id=0,
            template_id=10400,
            config=TerrainNavigationConfig(
                cell_size=10.0,
                blocked_sample_delta=64,
            ),
        )

        self.assertEqual(16, seed.sampled_cells)
        self.assertTrue(seed.blocked_cells)
        self.assertEqual(seed.blocked_cells, navigation.blocked)
        self.assertTrue(
            any(cell.x in (-1, 0) for cell in seed.blocked_cells)
        )

    def test_gentle_height_changes_become_costs_without_blocking(self) -> None:
        rows = [bytes((0, 10, 20, 30, 40)) for _ in range(5)]
        raster = TerrainAlphaRaster(7, 1, 5, 5, b"".join(rows))
        navigation = SparseNavigationMap(cell_size=10.0)

        seed = seed_height_raster_navigation(
            navigation,
            geometry=_geometry(),
            raster=raster,
            zone_depth=0,
            template_group_id=0,
            template_id=10400,
            config=TerrainNavigationConfig(
                cell_size=10.0,
                blocked_sample_delta=100,
                maximum_traversal_cost=3.0,
            ),
        )

        self.assertFalse(seed.blocked_cells)
        self.assertTrue(seed.costs)
        first_cell, first_cost = seed.costs[0]
        self.assertIsInstance(first_cell, NavigationCell)
        self.assertGreater(first_cost, 1.0)

    def test_optional_floor_blocks_only_when_explicitly_calibrated(self) -> None:
        raster = TerrainAlphaRaster(7, 1, 5, 5, bytes(25))
        uncalibrated = SparseNavigationMap(cell_size=10.0)
        calibrated = SparseNavigationMap(cell_size=10.0)

        seed_height_raster_navigation(
            uncalibrated,
            geometry=_geometry(),
            raster=raster,
            zone_depth=0,
            template_group_id=0,
            template_id=10400,
            config=TerrainNavigationConfig(cell_size=10.0),
        )
        seed_height_raster_navigation(
            calibrated,
            geometry=_geometry(),
            raster=raster,
            zone_depth=0,
            template_group_id=0,
            template_id=10400,
            config=TerrainNavigationConfig(
                cell_size=10.0,
                minimum_traversable_sample=1,
            ),
        )

        self.assertFalse(uncalibrated.blocked)
        self.assertTrue(calibrated.blocked)

    def test_explicit_zone_water_becomes_a_high_cost_traversable_region(self) -> None:
        rows = [bytes((0, 0, 100, 100, 100)) for _ in range(5)]
        navigation = SparseNavigationMap(cell_size=10.0)

        seed = seed_height_raster_navigation(
            navigation,
            geometry=_geometry(),
            raster=TerrainAlphaRaster(7, 1, 5, 5, b"".join(rows)),
            zone_depth=0,
            template_group_id=0,
            template_id=3033,
            water_sample_threshold=50.0,
            config=TerrainNavigationConfig(
                cell_size=10.0,
                blocked_sample_delta=255,
                water_traversal_cost=9.0,
            ),
        )

        self.assertTrue(seed.water_cells)
        self.assertFalse(seed.blocked_cells)
        self.assertEqual(50.0, seed.water_sample_threshold)
        water_costs = dict(seed.costs)
        self.assertTrue(all(water_costs[cell] >= 9.0 for cell in seed.water_cells))

    def test_nonzero_local_center_projects_around_absolute_world_center(self) -> None:
        geometry = NativeZoneGeometry(
            minimum_local_x=80.0,
            minimum_local_z=-70.0,
            maximum_local_x=120.0,
            maximum_local_z=-30.0,
            rotation_w=1.0,
            rotation_x=0.0,
            rotation_y=0.0,
            rotation_z=0.0,
            absolute_center_x=1000.0,
            absolute_center_z=-2000.0,
            local_center_x=100.0,
            local_center_z=-50.0,
            radius_x=20.0,
            radius_z=20.0,
        )
        navigation = SparseNavigationMap(cell_size=10.0)

        seed = seed_height_raster_navigation(
            navigation,
            geometry=geometry,
            raster=TerrainAlphaRaster(7, 1, 5, 5, bytes(25)),
            zone_depth=0,
            template_group_id=0,
            template_id=10400,
            config=TerrainNavigationConfig(
                cell_size=10.0,
                minimum_traversable_sample=1,
            ),
        )

        self.assertEqual(16, seed.sampled_cells)
        self.assertTrue(all(98 <= cell.x <= 101 for cell in seed.blocked_cells))
        self.assertTrue(all(198 <= cell.y <= 201 for cell in seed.blocked_cells))

    def test_large_zone_is_bounded_to_the_local_seed_window(self) -> None:
        geometry = NativeZoneGeometry(
            minimum_local_x=-50_000.0,
            minimum_local_z=-50_000.0,
            maximum_local_x=50_000.0,
            maximum_local_z=50_000.0,
            rotation_w=1.0,
            rotation_x=0.0,
            rotation_y=0.0,
            rotation_z=0.0,
            absolute_center_x=71_834.0,
            absolute_center_z=-46_390.0,
            local_center_x=0.0,
            local_center_z=0.0,
            radius_x=50_000.0,
            radius_z=50_000.0,
        )

        seed = seed_height_raster_navigation(
            SparseNavigationMap(cell_size=20.0),
            geometry=geometry,
            raster=TerrainAlphaRaster(7, 1, 5, 5, bytes(25)),
            zone_depth=0,
            template_group_id=0,
            template_id=230,
            window_center_lt=71_834.0,
            window_center_lg=46_390.0,
            config=TerrainNavigationConfig(
                cell_size=20.0,
                seed_radius=1_200.0,
                maximum_seed_cells=20_000,
            ),
        )

        self.assertLessEqual(seed.sampled_cells, 121 * 121)
        self.assertEqual(71_834.0, seed.window_center_lt)
        self.assertEqual(1_200.0, seed.window_radius)


if __name__ == "__main__":
    unittest.main()
