"""M21: MetrologyEngine 测试——BUG-004 修复。"""
import os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np
from calibration.metrology import MeasurementROI, MetrologyEngine


def _box(x0, y0, z0, x1, y1, z1):
    v = np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                  [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]])
    quads = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    tris = []
    for a,b,c,d in quads:
        tris.append([v[a],v[b],v[c]]); tris.append([v[a],v[c],v[d]])
    return np.array(tris)


class EtchDepthTests(unittest.TestCase):
    def test_simple_etch_depth(self):
        """刻蚀前 z=[0,0.2]，刻蚀后 z=[0,0.15] → 深度 50nm。"""
        before = [(1, _box(0, 0, 0, 0.1, 0.1, 0.2))]   # 200nm thick
        after = [(1, _box(0, 0, 0, 0.1, 0.1, 0.15))]   # 150nm → 50nm etched
        result = MetrologyEngine.etch_depth(before, after)
        self.assertAlmostEqual(result.depth_nm, 50.0, delta=1.0)

    def test_etch_depth_with_roi(self):
        """ROI 限制后只测量指定区域。"""
        before = [(1, _box(0, 0, 0, 0.1, 0.1, 0.2))]
        after = [(1, _box(0, 0, 0, 0.1, 0.1, 0.15))]
        roi = MeasurementROI(x_min=-1, x_max=1, y_min=-1, y_max=1, z_min=-1, z_max=1)
        result = MetrologyEngine.etch_depth(before, after, roi)
        self.assertAlmostEqual(result.depth_nm, 50.0, delta=1.0)

    def test_no_etch_returns_zero(self):
        before = [(1, _box(0, 0, 0, 0.1, 0.1, 0.2))]
        after = before  # Same geometry
        result = MetrologyEngine.etch_depth(before, after)
        self.assertAlmostEqual(result.depth_nm, 0.0, places=0)

    def test_empty_before(self):
        result = MetrologyEngine.etch_depth([], [])
        self.assertEqual(result.method, "no_before")


class CriticalDimensionTests(unittest.TestCase):
    def test_cd_at_top(self):
        tri = _box(0.02, 0, 0, 0.08, 0.1, 0.2)  # 60nm wide
        cd = MetrologyEngine.critical_dimension(tri, z_plane=0.2)
        self.assertAlmostEqual(cd, 60.0, delta=5.0)

    def test_cd_empty(self):
        tri = _box(0, 0, 0, 0.1, 0.1, 0.1)
        cd = MetrologyEngine.critical_dimension(tri, z_plane=0.5)
        self.assertEqual(cd, 0.0)


class FilmThicknessTests(unittest.TestCase):
    def test_film_thickness(self):
        from geometry_scene import GeometryScene
        scene = GeometryScene.from_surfaces(
            [(2, _box(0, 0, 0.1, 0.1, 0.1, 0.12))],
            {2: "Silicon Dioxide"},
        )
        thickness = MetrologyEngine.film_thickness(scene, "Silicon Dioxide")
        self.assertAlmostEqual(thickness, 0.02, places=6)

    def test_missing_material(self):
        from geometry_scene import GeometryScene
        scene = GeometryScene.from_surfaces([(1, _box(0, 0, 0, 1, 1, 1))])
        self.assertEqual(MetrologyEngine.film_thickness(scene, "Nonexistent"), 0.0)


class StepCoverageTests(unittest.TestCase):
    def test_step_coverage(self):
        from geometry_scene import GeometryScene
        scene = GeometryScene.from_surfaces([
            (2, _box(0, 0, 0.1, 0.1, 0.1, 0.12)),
            (3, _box(0, 0, 0.005, 0.1, 0.1, 0.007)),
        ])
        sc = MetrologyEngine.step_coverage(scene, "mat_2", "mat_3")
        # Just verify it computes without crash
        self.assertIsInstance(sc, float)


if __name__ == "__main__":
    unittest.main()
