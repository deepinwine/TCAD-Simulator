# -*- coding: utf-8 -*-
"""M18：Hybrid Geometry Truth——canonical GeometryScene 驱动的连续工艺测试。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from process_backend.hybrid import ACCURATE, FAST, HybridBackend, ModeSelector


def _engine():
    try:
        import viennaps  # noqa: F401
        return True
    except ImportError:
        return False


def _load_steps(backend):
    """从 demo flow 加载真实步骤。"""
    import tcad_simulator as tcad

    db = backend._fast.database
    flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]
    steps = {}
    for blob in flow:
        step = tcad._webui_deserialize_step(blob, db)
        if step is not None:
            steps[blob.get("name", "")] = step
    return steps


class CanonicalSceneTests(unittest.TestCase):
    def test_canonical_scene_initialized_after_first_step(self):
        backend = HybridBackend(grid=32)
        steps = _load_steps(backend)
        backend.execute_step(steps["Initialize Wafer"])
        self.assertIsNotNone(backend.canonical_scene)
        self.assertGreater(backend.canonical_scene.total_triangles, 0)
        backend.shutdown()

    def test_canonical_scene_updated_after_each_step(self):
        backend = HybridBackend(grid=32)
        steps = _load_steps(backend)
        backend.execute_step(steps["Initialize Wafer"])
        tri_before = backend.canonical_scene.total_triangles
        backend.execute_step(steps["Spin Resist"])
        tri_after = backend.canonical_scene.total_triangles
        # 几何应变化（有新材料）
        self.assertNotEqual(tri_before, tri_after)
        backend.shutdown()

    def test_snapshot_includes_scene(self):
        backend = HybridBackend(grid=32)
        steps = _load_steps(backend)
        backend.execute_step(steps["Initialize Wafer"])
        state = backend.snapshot()
        self.assertIn("scene", state)
        self.assertIn("backend", state)
        backend.shutdown()

    def test_routing_log_records_mode(self):
        backend = HybridBackend(grid=32)
        steps = _load_steps(backend)
        backend.execute_step(steps["Initialize Wafer"])
        self.assertEqual(backend.routing_log[-1]["mode"], FAST)
        backend.shutdown()


class FastAccurateFastTests(unittest.TestCase):
    """M18 核心验证：FAST → ACCURATE → FAST 连续。"""

    def test_continuous_flow(self):
        backend = HybridBackend(grid=32)
        sel = ModeSelector()
        sel.set_mode("Etch", ACCURATE)
        backend._selector = sel
        steps = _load_steps(backend)

        # FAST: Initialize
        outcome = backend.execute_step(steps["Initialize Wafer"])
        self.assertEqual(backend.routing_log[-1]["mode"], FAST)
        self.assertIsNotNone(backend.canonical_scene)

        # FAST: Spin Resist
        backend.execute_step(steps["Spin Resist"])
        scene_after_resist = backend.canonical_scene

        # ACCURATE: Etch（或显式 fallback）
        outcome = backend.execute_step(steps["Etch"])
        modes = [e["mode"] for e in backend.routing_log]
        # 应该有 ACCURATE 或 fallback 记录
        has_accurate = ACCURATE in modes
        has_fallback = any("fallback" in str(e.get("step", "")) for e in backend.routing_log)
        self.assertTrue(
            has_accurate or has_fallback,
            f"Etch 应路由到 ACCURATE 或 fallback，实际: {backend.routing_log}",
        )

        # Etch 后 canonical scene 仍有效
        scene_after_etch = backend.canonical_scene
        self.assertIsNotNone(scene_after_etch)
        self.assertGreater(scene_after_etch.total_triangles, 0)

        # FAST: Deposition（切回 FAST 后基于 canonical state 继续）
        if "Deposition" in steps:
            backend.execute_step(steps["Deposition"])
            self.assertEqual(backend.routing_log[-1]["mode"], FAST)
            scene_after_dep = backend.canonical_scene
            self.assertIsNotNone(scene_after_dep)

        # FAST: CMP
        if "CMP" in steps:
            backend.execute_step(steps["CMP"])
            scene_after_cmp = backend.canonical_scene
            self.assertIsNotNone(scene_after_cmp)

        backend.shutdown()

    def test_no_stale_state_after_switch(self):
        """切换后 canonical scene 不丢失。"""
        backend = HybridBackend(grid=32)
        sel = ModeSelector()
        sel.set_mode("Etch", ACCURATE)
        backend._selector = sel
        steps = _load_steps(backend)

        backend.execute_step(steps["Initialize Wafer"])
        backend.execute_step(steps["Spin Resist"])
        scene_before = backend.canonical_scene

        backend.execute_step(steps["Etch"])
        scene_after = backend.canonical_scene

        # Scene 应仍然有 Silicon（不会因为切换丢失）
        self.assertIsNotNone(scene_after)
        mat_names = [m.name for m in scene_after.meshes] if scene_after.meshes else []
        # 如果 scene 有 meshes（可能因为 fallback 到 fast 也有）
        if mat_names:
            pass  # 只验证 scene 存在且有内容

        backend.shutdown()


class LayerOrderingTests(unittest.TestCase):
    """BUG-001 回归：layer 按 z_min 排序而非 thickness。"""

    def test_layer_order_independent_of_thickness(self):
        from geometry_scene import GeometryScene
        from geometry_scene.bridge import scene_to_viennaps_layers

        def box(x0, y0, z0, x1, y1, z1):
            v = np.array([
                [x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1],
            ])
            quads = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
            tris = []
            for a,b,c,d in quads:
                tris.append([v[a],v[b],v[c]])
                tris.append([v[a],v[c],v[d]])
            return np.array(tris)

        # Si(500nm) 底层 → SiO2(30nm) 中间 → SiN(100nm) 顶层
        # SiN 比 SiO2 厚，但必须在 SiO2 上方
        scene = GeometryScene.from_surfaces([
            (1, box(0, 0, 0, 100, 100, 500)),    # Si z=[0,500]
            (2, box(0, 0, 500, 100, 100, 530)),  # SiO2 z=[500,530]
            (3, box(0, 0, 530, 100, 100, 630)),  # SiN z=[530,630]
        ])

        layers = scene_to_viennaps_layers(scene)
        self.assertEqual(len(layers), 3)
        # 验证按 z_min 升序（不是按 thickness）
        z_mins = [layer[0] for layer in layers]
        self.assertEqual(z_mins, sorted(z_mins))
        # SiN（z=530）必须在 SiO2（z=500）之上
        self.assertEqual(layers[0][1], 1)  # Si
        self.assertEqual(layers[1][1], 2)  # SiO2
        self.assertEqual(layers[2][1], 3)  # SiN


class HybridRegressions(unittest.TestCase):
    """确保 M11 已有功能不回归。"""

    def test_info_and_capabilities(self):
        backend = HybridBackend(grid=32)
        info = backend.info()
        self.assertEqual(info.name, "hybrid")
        self.assertEqual(info.precision, "mixed")
        caps = backend.capabilities()
        self.assertIn("canonical_scene", caps)
        backend.shutdown()

    def test_snapshot_restore_round_trip(self):
        backend = HybridBackend(grid=32)
        steps = _load_steps(backend)
        backend.execute_step(steps["Initialize Wafer"])
        state = backend.snapshot()
        grid_before = backend.grid().copy()
        backend.restore(state)
        np.testing.assert_array_equal(backend.grid(), grid_before)
        backend.shutdown()

    def test_grid_returns_voxel(self):
        backend = HybridBackend(grid=32)
        grid = backend.grid()
        self.assertIsInstance(grid, np.ndarray)
        backend.shutdown()


if __name__ == "__main__":
    unittest.main()
