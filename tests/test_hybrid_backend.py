# -*- coding: utf-8 -*-
"""M11：混合 Fast/Accurate 后端测试。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

from process_backend.base import ProcessBackendError
from process_backend.hybrid import ACCURATE, FAST, HybridBackend, ModeSelector


class FakeStep:
    def __init__(self, name, params=None):
        self.name = name
        self.params = params or {}


class ModeSelectorTests(unittest.TestCase):
    def test_default_map_routes_etch_accurate(self):
        sel = ModeSelector()
        self.assertEqual(sel.select("Etch"), ACCURATE if _engine() else FAST)
        self.assertEqual(sel.select("Deposition"), FAST)
        self.assertEqual(sel.select("CMP"), FAST)

    def test_unknown_step_defaults_fast(self):
        sel = ModeSelector()
        self.assertEqual(sel.select("My Custom Step"), FAST)

    def test_set_mode_overrides(self):
        sel = ModeSelector()
        sel.set_mode("Etch", FAST)
        self.assertEqual(sel.select("Etch"), FAST)

    def test_invalid_mode_rejected(self):
        sel = ModeSelector()
        with self.assertRaises(ValueError):
            sel.set_mode("Etch", "turbo")


def _engine():
    try:
        import viennaps  # noqa: F401

        return True
    except ImportError:
        return False


class HybridBackendTests(unittest.TestCase):
    def test_info_and_registry(self):
        backend = HybridBackend(grid=32)
        info = backend.info()
        self.assertEqual(info.name, "hybrid")
        self.assertEqual(info.precision, "mixed")
        backend.shutdown()

    def test_fast_steps_run_on_voxel(self):
        import tcad_simulator as tcad

        backend = HybridBackend(grid=32)
        database = backend._fast.database
        step = tcad._webui_deserialize_step(
            tcad.load_demo_flows(database)["Basic Trench"]["steps"][0],
            database,
        )
        outcome = backend.execute_step(step)
        self.assertIn("Wafer", outcome.message)
        log = backend.routing_log
        self.assertEqual(log[-1]["mode"], FAST)
        backend.shutdown()

    def test_etch_routes_to_accurate_when_available(self):
        if not _engine():
            self.skipTest("viennaps 未安装")
        import tcad_simulator as tcad

        backend = HybridBackend(grid=32)
        database = backend._fast.database
        flow = tcad.load_demo_flows(database)["Basic Trench"]["steps"]
        init = tcad._webui_deserialize_step(flow[0], database)
        etch = next(
            tcad._webui_deserialize_step(blob, database)
            for blob in flow if blob.get("name") == "Etch"
        )
        backend.execute_step(init)
        outcome = backend.execute_step(etch)
        log = backend.routing_log
        modes = [entry["mode"] for entry in log]
        self.assertIn(ACCURATE, modes)
        backend.shutdown()

    def test_accurate_unsupported_falls_back_to_fast(self):
        if not _engine():
            self.skipTest("viennaps 未安装")
        import tcad_simulator as tcad

        backend = HybridBackend(grid=32)
        database = backend._fast.database
        sel = ModeSelector()
        sel.set_mode("Spin Resist", ACCURATE)
        backend._selector = sel
        flow = tcad.load_demo_flows(database)["Basic Trench"]["steps"]
        step = next(
            tcad._webui_deserialize_step(blob, database)
            for blob in flow if blob.get("name") == "Spin Resist"
        )
        backend.execute_step(
            tcad._webui_deserialize_step(flow[0], database)
        )
        outcome = backend.execute_step(step)
        log = backend.routing_log
        self.assertIn("fallback", log[-1]["step"])
        backend.shutdown()

    def test_grid_returns_voxel_grid(self):
        import numpy as np

        backend = HybridBackend(grid=32)
        grid = backend.grid()
        self.assertIsInstance(grid, np.ndarray)
        backend.shutdown()

    def test_snapshot_restore_round_trip(self):
        import tcad_simulator as tcad

        backend = HybridBackend(grid=32)
        database = backend._fast.database
        step = tcad._webui_deserialize_step(
            tcad.load_demo_flows(database)["Basic Trench"]["steps"][0],
            database,
        )
        backend.execute_step(step)
        state = backend.snapshot()
        grid_before = backend.grid().copy()
        backend.restore(state)
        np.testing.assert_array_equal(backend.grid(), grid_before)
        backend.shutdown()


import numpy as np  # noqa: E402

if __name__ == "__main__":
    unittest.main()
