"""M28: CrossSectionEngine + profile metrology tests."""
import os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np
from calibration.cross_section import CrossSectionEngine, MaterialSegment


def _make_grid_with_trench(nx=32, ny=32, nz=32, voxel=5.0,
                            trench_x_center=16, trench_half_width=4, trench_depth_voxels=8):
    """体素网格：Si 衬底（底部）+ 顶部挖 trench。"""
    grid = np.zeros((nx, ny, nz), dtype=np.uint16)
    substrate_top = nz - 4  # Leave 4 void voxels on top
    grid[:, :, :substrate_top] = 1  # Si
    # Cut trench: void in x range around center, from top of Si downward
    x0 = max(0, trench_x_center - trench_half_width)
    x1 = min(nx, trench_x_center + trench_half_width + 1)
    grid[x0:x1, :, substrate_top - trench_depth_voxels:substrate_top] = 0  # void
    return grid


class CrossSectionTests(unittest.TestCase):
    def test_from_voxel_grid_basic(self):
        grid = _make_grid_with_trench()
        cs = CrossSectionEngine.from_voxel_grid(grid, 5.0, x_index=16, y_index=16)
        # At trench center: void from top to trench bottom, then Si
        self.assertGreater(len(cs.segments), 0)
        # segments[0] is BOTTOM (lowest z), segments[-1] is TOP
        # At trench center: bottom = Si (1), top = void (0)
        bottom_seg = cs.segments[0]
        self.assertEqual(bottom_seg.mat_id, 1)
        top_seg = cs.segments[-1]
        self.assertEqual(top_seg.mat_id, 0)

    def test_from_voxel_grid_outside_trench(self):
        grid = _make_grid_with_trench()
        cs = CrossSectionEngine.from_voxel_grid(grid, 5.0, x_index=2, y_index=16)
        # Outside trench: should be Si with void cap
        mat_ids = [s.mat_id for s in cs.segments]
        self.assertIn(1, mat_ids)

    def test_trench_profile(self):
        grid = _make_grid_with_trench()
        profiles = CrossSectionEngine.trench_profile(grid, 5.0, y_index=16)
        self.assertEqual(len(profiles), 32)
        # Center profile should have void (trench)
        center = profiles[16]
        mat_ids = [s.mat_id for s in center.segments]
        self.assertIn(0, mat_ids)


class FeatureMetrologyTests(unittest.TestCase):
    def test_etch_depth(self):
        """Before: flat Si surface; After: trench → depth = trench_depth × voxel."""
        grid_before = _make_grid_with_trench(trench_depth_voxels=0)  # No trench
        grid_after = _make_grid_with_trench(trench_depth_voxels=8)

        profile_before = CrossSectionEngine.trench_profile(grid_before, 5.0, 16)
        profile_after = CrossSectionEngine.trench_profile(grid_after, 5.0, 16)

        depth = CrossSectionEngine.etch_depth(profile_before, profile_after, material_id=1)
        expected = 8 * 5.0  # 8 voxels × 5nm
        self.assertAlmostEqual(depth, expected, delta=2.0)

    def test_critical_dimension(self):
        """Trench opening width = (2*half_width+1) voxels."""
        grid = _make_grid_with_trench(trench_half_width=4)
        profiles = CrossSectionEngine.trench_profile(grid, 5.0, 16)
        # CD at z just above substrate bottom (in the trench void region)
        # Si substrate top is at z_voxel = 28 (nz-4=28)
        cd_voxels = CrossSectionEngine.critical_dimension(
            profiles, z_level=27 * 5.0, void_id=0,
        )
        expected_voxels = 4 * 2 + 1  # half_width*2 + 1
        self.assertAlmostEqual(cd_voxels, expected_voxels, delta=2)

    def test_sidewall_angle_vertical(self):
        """Vertical trench sidewalls → angle ≈ 90°."""
        grid = _make_grid_with_trench()
        profiles = CrossSectionEngine.trench_profile(grid, 5.0, 16)
        angle = CrossSectionEngine.sidewall_angle(profiles, material_id=1)
        # Perfectly vertical → 90°
        self.assertGreater(angle, 80.0)  # Allow some tolerance


class IntegrationWithBridgeTests(unittest.TestCase):
    """Cross-section from actual voxelization round-trip."""

    def test_box_trench_cross_section(self):
        from geometry_scene import GeometryScene
        from geometry_scene.bridge import scene_to_voxel_grid

        def box(x0, y0, z0, x1, y1, z1):
            v = np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                          [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]])
            quads = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
            tris = []
            for a,b,c,d in quads:
                tris.append([v[a],v[b],v[c]]); tris.append([v[a],v[c],v[d]])
            return np.array(tris)

        # Si substrate 200nm
        scene = GeometryScene.from_surfaces([
            (1, box(0, 0, 0, 640, 640, 200)),
        ])
        grid = scene_to_voxel_grid(scene, (32, 32, 32), 20.0)
        cs = CrossSectionEngine.from_voxel_grid(grid, 20.0, 20, 10)
        # Should have Si segment
        mat_ids = [s.mat_id for s in cs.segments]
        self.assertIn(1, mat_ids)
        # Si should occupy lower portion
        si_seg = next(s for s in cs.segments if s.mat_id == 1)
        self.assertGreater(si_seg.z_end, 100)  # At least 100nm thick
        self.assertLess(si_seg.z_start, 50)    # Starts near z=0


if __name__ == "__main__":
    unittest.main()
