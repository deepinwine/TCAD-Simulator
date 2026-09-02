# -*- coding: utf-8 -*-
"""M15：标定框架测试。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

from calibration import (
    CalibrationMetrics,
    CalibrationProfile,
    CalibrationRunner,
    MeasurementResult,
    ReferenceTarget,
    compare_to_reference,
)
from calibration.metrics import measure_etch_depth


class MetricsTests(unittest.TestCase):
    def test_depth_error_pct(self):
        measured = MeasurementResult(depth_nm=486.0)
        ref = ReferenceTarget(
            source_type="literature",
            source="Doyle et al. 2015 Fig.3",
            target_depth_nm=500.0,
        )
        metrics = compare_to_reference(measured, ref)
        self.assertEqual(metrics.depth_error_pct, -2.8)

    def test_multiple_metrics(self):
        measured = MeasurementResult(
            depth_nm=490, top_cd_nm=105, bottom_cd_nm=65,
            film_thickness_nm=22,
        )
        ref = ReferenceTarget(
            source_type="synthetic",
            source="internal reference",
            target_depth_nm=500, top_cd_nm=100, bottom_cd_nm=70,
            film_thickness_nm=20,
        )
        metrics = compare_to_reference(measured, ref)
        self.assertEqual(metrics.depth_error_pct, -2.0)
        self.assertEqual(metrics.top_cd_error_pct, 5.0)
        self.assertEqual(metrics.film_thickness_error_pct, 10.0)
        self.assertEqual(metrics.max_error_pct(), 10.0)

    def test_reference_type_labels(self):
        ref = ReferenceTarget(source_type="measured", source="SEM CD-SEM #1234")
        self.assertEqual(ref.source_type, "measured")
        ref2 = ReferenceTarget(source_type="literature", source="patent US123")
        self.assertEqual(ref2.source_type, "literature")

    def test_no_crash_on_missing_data(self):
        measured = MeasurementResult()  # 全空
        ref = ReferenceTarget(source_type="synthetic", source="test")
        metrics = compare_to_reference(measured, ref)
        self.assertIsNone(metrics.depth_error_pct)
        self.assertEqual(metrics.max_error_pct(), 0.0)


class RunnerTests(unittest.TestCase):
    def test_grid_search_finds_best(self):
        """网格搜索：模拟 depth = rate × time，目标 500nm。"""
        def simulate(params):
            depth = params["rate"] * params["time"]
            import numpy as np
            z = depth / 1000.0
            # 两个三角形：顶面 z=z、底面 z=0 → z 范围 = depth
            tri = np.array([[[0,0,z],[1,0,z],[0.5,1,z]], [[0,0,0],[1,0,0],[0.5,1,0]]])
            return [(1, tri)]

        def measure(surfaces):
            from calibration.metrics import MeasurementResult
            tri = surfaces[0][1]
            z_range = tri[:,:,2].max() - tri[:,:,2].min()
            return MeasurementResult(depth_nm=z_range * 1000.0)

        profile = CalibrationProfile(
            name="test_rate_scan",
            process="dry_etch",
            engine="mock",
            parameter_grid={"rate": [5.0, 10.0, 16.7], "time": [30.0]},
            reference=ReferenceTarget(
                source_type="synthetic",
                source="mock target",
                target_depth_nm=500.0,
            ),
        )
        runner = CalibrationRunner(simulate, measure)
        report = runner.run(profile, git_commit="test123")

        self.assertEqual(len(report.results), 3)
        self.assertIsNotNone(report.best)
        # rate=16.7 × 30 = 501 ≈ 500 → 最优
        self.assertAlmostEqual(report.best.parameters["rate"], 16.7, places=0)
        self.assertLess(report.best.score, 5.0)  # <5% 误差

    def test_report_reproducibility(self):
        """报告包含引擎版本/git commit/时间戳。"""
        def simulate(params):
            import numpy as np
            return [(1, np.array([[[0,0,0.5],[1,0,0.5],[0.5,1,0.5]]]))]

        def measure(surfaces):
            return MeasurementResult(depth_nm=500.0)

        profile = CalibrationProfile(
            name="repro_test",
            process="dry_etch",
            engine="mock",
            engine_version="0.1",
            parameter_grid={"x": [1.0]},
            reference=ReferenceTarget(
                source_type="synthetic", source="test", target_depth_nm=500.0,
            ),
        )
        report = CalibrationRunner(simulate, measure).run(
            profile, git_commit="abc1234", grid_resolution="64³@5nm",
        )
        d = report.to_dict()
        self.assertEqual(d["git_commit"], "abc1234")
        self.assertEqual(d["grid_resolution"], "64³@5nm")
        self.assertIn("timestamp", d)
        self.assertIn("engine_version", d)


class ViennaPSCalibrationIntegration(unittest.TestCase):
    """ViennaPS 刻蚀深度标定集成（引擎可用时运行）。"""

    def test_etch_depth_calibration(self):
        try:
            import viennaps  # noqa: F401
        except ImportError:
            self.skipTest("viennaps 未安装")

        from process_backend import create_backend

        def simulate(params):
            backend = create_backend("viennaps", grid_nm=32.0)

            class S:
                def __init__(self, n, p):
                    self.name, self.params = n, p

            backend.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
            backend.execute_step(S("Etch", {
                "time": params.get("time", 30.0),
                "chemistry": "Dry",
            }))
            surfaces = backend.material_surfaces(5000)
            backend.shutdown()
            return surfaces

        profile = CalibrationProfile(
            name="sf6o2_si_etch_v1",
            process="dry_etch",
            engine="viennaps",
            engine_version="4.7.0",
            material="Si",
            parameter_grid={"time": [10.0]},
            reference=ReferenceTarget(
                source_type="synthetic",
                source="voxel baseline Basic Trench",
                target_depth_nm=300.0,
            ),
        )
        runner = CalibrationRunner(simulate, measure_etch_depth)
        report = runner.run(profile)
        self.assertEqual(len(report.results), 1)
        # 不设误差阈值——只验证管道跑通且产出结构化结果
        self.assertIsNotNone(report.best)
        self.assertIn("depth_error_pct", report.best.metrics.to_dict())


if __name__ == "__main__":
    unittest.main()
