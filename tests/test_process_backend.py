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
