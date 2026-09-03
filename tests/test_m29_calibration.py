"""M29: Dry Etch Calibration Benchmark — Si trench SF6O2 depth/CD/sidewall."""
import os, json, tempfile, unittest
from pathlib import Path
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np

from calibration import (
    CalibrationProfile, CalibrationRunner, ReferenceTarget,
)
from calibration.cross_section import CrossSectionEngine
from calibration.metrology import MeasurementROI, MetrologyEngine


def _engine():
    try:
        import viennaps; return True
    except ImportError: return False


class SiTrenchBenchmarkTests(unittest.TestCase):
    """M29: Si trench SF6O2 etch benchmark with MetrologyEngine."""

    def _build_trench_grid(self, nx=32, ny=32, nz=32, voxel_nm=20.0,
                           trench_center=16, trench_half=3, trench_depth_voxels=10,
                           mat_id=1):
        """Synthetic Si trench grid for metrology validation."""
        grid = np.zeros((nx, ny, nz), dtype=np.uint16)
        substrate_top = nz - 4
        grid[:, :, :substrate_top] = mat_id
        x0 = max(0, trench_center - trench_half)
        x1 = min(nx, trench_center + trench_half + 1)
        grid[x0:x1, :, substrate_top - trench_depth_voxels:substrate_top] = 0
        return grid

    def test_etch_depth_benchmark(self):
        """Synthetic trench: depth = 10 voxels × 20nm = 200nm."""
        grid_before = self._build_trench_grid(trench_depth_voxels=0)
        grid_after = self._build_trench_grid(trench_depth_voxels=10)

        profiles_before = CrossSectionEngine.trench_profile(grid_before, 20.0, 16)
        profiles_after = CrossSectionEngine.trench_profile(grid_after, 20.0, 16)

        depth = CrossSectionEngine.etch_depth(profiles_before, profiles_after, material_id=1)
        self.assertAlmostEqual(depth, 200.0, delta=10.0)

    def test_top_cd_benchmark(self):
        """Synthetic trench: CD = 7 voxels × 20nm = 140nm."""
        grid = self._build_trench_grid(trench_half=3)
        profiles = CrossSectionEngine.trench_profile(grid, 20.0, 16)
        substrate_top_voxel = 32 - 4  # 28
        cd_voxels = CrossSectionEngine.critical_dimension(
            profiles, z_level=27 * 20.0, void_id=0,
        )
        cd_nm = cd_voxels * 20.0
        expected = 7 * 20.0  # 7 voxels
        self.assertAlmostEqual(cd_nm, expected, delta=2 * 20.0)

    def test_sidewall_angle_benchmark(self):
        """Vertical trench → angle ≥ 80°."""
        grid = self._build_trench_grid()
        profiles = CrossSectionEngine.trench_profile(grid, 20.0, 16)
        angle = CrossSectionEngine.sidewall_angle(profiles, material_id=1)
        self.assertGreater(angle, 80.0)

    def test_calibration_profile_si_trench(self):
        """M29: CalibrationProfile for Si trench dry etch."""
        profile = CalibrationProfile(
            name="si_sf6o2_trench_v1",
            process="dry_etch",
            engine="viennaps",
            engine_version="4.7.0",
            material="Silicon",
            parameter_grid={"time": [30.0], "flux": [100.0]},
            reference=ReferenceTarget(
                source_type="synthetic",
                source="voxel baseline 300nm depth",
                target_depth_nm=300.0,
                top_cd_nm=100.0,
                sidewall_angle_deg=88.0,
            ),
        )
        d = profile.to_dict()
        self.assertEqual(d["name"], "si_sf6o2_trench_v1")
        self.assertEqual(d["reference"]["source_type"], "synthetic")
        self.assertEqual(d["reference"]["target_depth_nm"], 300.0)

    def test_calibration_runner_with_cross_section(self):
        """Runner using CrossSectionEngine for metrology."""
        def simulate(params):
            depth_voxels = int(params.get("depth_voxels", 10))
            grid = self._build_trench_grid(trench_depth_voxels=depth_voxels)
            # Return profiles as "surfaces" substitute
            return grid

        def measure(grid):
            # Convert grid to cross-section profiles, then measure depth
            profiles = CrossSectionEngine.trench_profile(grid, 20.0, 16)
            # Use max material top z as depth reference
            mat_tops = []
            for cs in profiles:
                si_segs = [s for s in cs.segments if s.mat_id == 1]
                if si_segs:
                    mat_tops.append(max(s.z_end for s in si_segs))
            if not mat_tops:
                from calibration.metrics import MeasurementResult
                return MeasurementResult()
            from calibration.metrics import MeasurementResult
            return MeasurementResult(depth_nm=min(mat_tops) - 0)  # Top descent

        profile = CalibrationProfile(
            name="synthetic_trench_test",
            process="dry_etch",
            engine="synthetic",
            parameter_grid={"depth_voxels": [5, 10, 15]},
            reference=ReferenceTarget(
                source_type="synthetic",
                source="test target 200nm",
                target_depth_nm=200.0,
            ),
        )
        runner = CalibrationRunner(simulate, measure)
        report = runner.run(profile, git_commit="test")
        self.assertEqual(len(report.results), 3)
        self.assertIsNotNone(report.best)


@unittest.skipUnless(_engine(), "viennaps 未安装")
class ViennaPSCalibrationBenchmarkTests(unittest.TestCase):
    """M29: Real ViennaPS Si trench etch calibration E2E."""

    def test_full_calibration_pipeline(self):
        """完整的 ViennaPS Si trench → metrology → calibration pipeline。"""
        from process_backend import create_backend
        from geometry_scene.bridge import surfaces_um_to_scene, scene_to_voxel_grid

        def simulate(params):
            backend = create_backend("viennaps", grid_nm=32.0)

            class S:
                def __init__(self, n, p):
                    self.name, self.params = n, p

            backend.execute_step(S("Initialize Wafer", {"thickness_nm": 300.0}))
            surfaces_before = backend.material_surfaces(5000)

            backend.execute_step(S("Etch", {
                "time": params.get("time", 30.0),
                "chemistry": "Dry",
            }))
            surfaces_after = backend.material_surfaces(5000)
            backend.shutdown()
            return (surfaces_before, surfaces_after)

        def measure(data):
            before, after = data
            from calibration.metrics import MeasurementResult
            etch_result = MetrologyEngine.etch_depth(
                [before[0]] if before else [],
                [after[0]] if after else [],
            )
            return MeasurementResult(depth_nm=etch_result.depth_nm)

        profile = CalibrationProfile(
            name="si_sf6o2_full_v1",
            process="dry_etch",
            engine="viennaps",
            engine_version="4.7.0",
            material="Silicon",
            parameter_grid={"time": [10.0]},
            reference=ReferenceTarget(
                source_type="synthetic",
                source="M9 baseline calibration",
                target_depth_nm=300.0,
            ),
        )
        runner = CalibrationRunner(simulate, measure)
        report = runner.run(profile, git_commit="m29")
        self.assertEqual(len(report.results), 1)
        self.assertIsNotNone(report.best)
        # Verify metrics exist (even if error is large)
        self.assertIn("depth_error_pct", report.best.metrics.to_dict())


if __name__ == "__main__":
    unittest.main()
