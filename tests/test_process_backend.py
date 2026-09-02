# -*- coding: utf-8 -*-
"""M7 T1：ProcessBackend 接口与 VoxelBackend（行为不变包装）。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from process_backend import (
    ProcessBackendError,
    VoxelBackend,
    create_backend,
)

GRID = 48
DEMO = "Basic Trench"


def make_backend() -> VoxelBackend:
    return create_backend("voxel", grid=GRID)


class BackendInterfaceTests(unittest.TestCase):
    def test_info_and_registry(self) -> None:
        backend = make_backend()
        info = backend.info()
        self.assertEqual(info.name, "voxel")
        self.assertEqual(info.precision, "voxel")
        self.assertIsInstance(info.version, str)

    def test_registry_unknown_backend_raises(self) -> None:
        with self.assertRaises(ProcessBackendError) as ctx:
            create_backend("__no_such_backend__")
        self.assertEqual(ctx.exception.code, "unknown_backend")

    def test_summary_matches_model(self) -> None:
        backend = make_backend()
        summary = backend.summary()
        self.assertEqual(summary.grid_shape, (GRID, GRID, GRID))
        self.assertGreater(summary.voxel_size_nm, 0.0)

    def test_snapshot_restore_round_trip(self) -> None:
        import tcad_simulator as tcad

        backend = make_backend()
        database = tcad.MaterialDatabase()
        step = tcad._webui_deserialize_step(
            tcad.load_demo_flows(database)[DEMO]["steps"][0], database,
        )
        backend.execute_step(step)
        grid_before = backend.grid().copy()
        state = backend.snapshot()

        backend.execute_step(
            tcad._webui_deserialize_step(
                tcad.load_demo_flows(database)[DEMO]["steps"][1], database,
            )
        )
        self.assertFalse(np.array_equal(backend.grid(), grid_before))

        backend.restore(state)
        np.testing.assert_array_equal(backend.grid(), grid_before)


class VoxelParityTests(unittest.TestCase):
    def test_backend_matches_direct_execution(self) -> None:
        import tcad_simulator as tcad

        # 路径 A：VoxelBackend
        backend = make_backend()
        database_a = tcad.MaterialDatabase()
        for blob in tcad.load_demo_flows(database_a)[DEMO]["steps"]:
            step = tcad._webui_deserialize_step(blob, database_a)
            self.assertIsNotNone(step)
            outcome = backend.execute_step(step)
            self.assertTrue(str(outcome.message).strip())

        # 路径 B：直接 ProcessModel（既有契约）
        database_b = tcad.MaterialDatabase()
        model = tcad.ProcessModel(
            database_b,
            grid_shape=(GRID, GRID, GRID),
            voxel_size_nm=640.0 / GRID,
            max_workers=1,
        )
        try:
            for blob in tcad.load_demo_flows(database_b)[DEMO]["steps"]:
                step = tcad._webui_deserialize_step(blob, database_b)
                step.execute(model)

            np.testing.assert_array_equal(backend.grid(), model.grid)

            surfaces_backend = backend.material_surfaces(face_limit=20000)
            surfaces_direct = model.get_material_surfaces(face_limit=20000)
            self.assertEqual(
                [mat_id for mat_id, _ in surfaces_backend],
                [mat_id for mat_id, _ in surfaces_direct],
            )
            for (_, tri_a), (_, tri_b) in zip(surfaces_backend, surfaces_direct):
                np.testing.assert_allclose(tri_a, tri_b)
        finally:
            model.parallel.shutdown()
            backend.shutdown()


if __name__ == "__main__":
    unittest.main()


class ViennaPSBackendTests(unittest.TestCase):
    """M9：几何后端注册、能力回退与双引擎标定（引擎需已安装）。"""

    def _skip_if_no_engine(self) -> None:
        from process_backend import engine_available

        if not engine_available():
            self.skipTest("viennaps 未安装（见 experiments/viennaps/README.md）")

    def test_registered_with_geometry_precision(self) -> None:
        self._skip_if_no_engine()
        from process_backend import create_backend

        backend = create_backend("viennaps", grid_nm=16.0)
        info = backend.info()
        self.assertEqual(info.name, "viennaps")
        self.assertEqual(info.precision, "geometry")
        self.assertIn("viennaps", __import__("process_backend", fromlist=["available_backends"]).available_backends())

    def test_unsupported_step_falls_back_explicitly(self) -> None:
        self._skip_if_no_engine()
        from process_backend import create_backend

        backend = create_backend("viennaps")
        class FakeStep:
            name = "Spin Resist"
            params = {}
        with self.assertRaises(ProcessBackendError) as ctx:
            backend.execute_step(FakeStep())
        self.assertEqual(ctx.exception.code, "unsupported_step")
        self.assertIn("voxel", str(ctx.exception.suggestion))

    def test_initialize_etch_and_snapshot_round_trip(self) -> None:
        self._skip_if_no_engine()
        import tcad_simulator as tcad
        from process_backend import create_backend

        backend = create_backend("viennaps", grid_nm=16.0)
        class Step:
            def __init__(self, name, params):
                self.name, self.params = name, params
        backend.execute_step(Step("Initialize Wafer", {"thickness_nm": 200.0}))
        surfaces = backend.material_surfaces(20000)
        self.assertEqual(len(surfaces), 1)
        mat_id, triangles = surfaces[0]
        self.assertGreater(triangles.shape[0], 0)
        self.assertEqual(triangles.shape[1:], (3, 3))
        surface_z_max = float(triangles[:, :, 2].max())

        state = backend.snapshot()
        backend.execute_step(Step("Etch", {"time": 10.0, "chemistry": "Dry"}))
        tri_after = backend.material_surfaces(20000)[0][1]
        depth_after = float(tri_after[:, :, 2].max() - tri_after[:, :, 2].min())

        backend.restore(state)
        tri_restored = backend.material_surfaces(20000)[0][1]
        self.assertAlmostEqual(
            float(tri_restored[:, :, 2].max()), surface_z_max, places=9,
        )
        backend.shutdown()

    def test_grid_raises_geometry_error(self) -> None:
        self._skip_if_no_engine()
        from process_backend import create_backend

        backend = create_backend("viennaps")
        class Step:
            name, params = "Initialize Wafer", {"thickness_nm": 200.0}
        backend.execute_step(Step())
        with self.assertRaises(ProcessBackendError) as ctx:
            backend.grid()
        self.assertEqual(ctx.exception.code, "geometry_backend")

    def test_calibration_etch_depth_both_engines(self) -> None:
        """双引擎标定：同目标刻蚀，报告并宽限比较刻蚀深度量级。"""
        self._skip_if_no_engine()
        import tcad_simulator as tcad
        from process_backend import create_backend

        # 体素引擎：Initialize + Etch(Dry 30s)
        voxel = create_backend("voxel", grid=64)
        database = tcad.MaterialDatabase()
        flow = tcad.load_demo_flows(database)["Basic Trench"]["steps"]
        voxel.execute_step(tcad._webui_deserialize_step(flow[0], database))
        etch = next(
            tcad._webui_deserialize_step(blob, database)
            for blob in flow
            if blob.get("name") == "Etch"
        )
        voxel.execute_step(etch)
        void_id = next(
            mid for mid, material in database.items() if material.name == "Void"
        )
        grid = voxel.grid()
        import numpy as np
        silicon_id = next(
            mid for mid, material in database.items() if material.name == "Silicon"
        )
        heights = np.nonzero(grid == silicon_id)[2]
        voxel_depth_nm = float((heights.max() - heights.min()) + 1) * voxel.summary().voxel_size_nm
        voxel.shutdown()

        # 几何引擎：Initialize(200nm) + Etch(30s)
        geometry = create_backend("viennaps", grid_nm=16.0)
        class Step:
            def __init__(self, name, params):
                self.name, self.params = name, params
        geometry.execute_step(Step("Initialize Wafer", {"thickness_nm": 200.0}))
        top_before = float(geometry.material_surfaces(40000)[0][1][:, :, 2].max())
        geometry.execute_step(Step("Etch", {"time": 30.0, "chemistry": "Dry"}))
        top_after = float(geometry.material_surfaces(40000)[0][1][:, :, 2].max())
        geo_depth_nm = (top_before - top_after) * 1000.0
        geometry.shutdown()

        print(f"\n[calibration] voxel etch depth ≈ {voxel_depth_nm:.1f} nm | "
              f"viennaps ≈ {geo_depth_nm:.1f} nm | ratio ≈ {geo_depth_nm / max(voxel_depth_nm, 1e-9):.2f}")
        # 宽容量级断言：两个物理模型都应产生明显刻蚀
        self.assertGreater(voxel_depth_nm, 0.0)
        self.assertGreater(geo_depth_nm, 0.0)
        ratio = geo_depth_nm / max(voxel_depth_nm, 1e-9)
        self.assertTrue(0.2 <= ratio <= 3.0, f"标定漂移：ratio={ratio:.2f}")
