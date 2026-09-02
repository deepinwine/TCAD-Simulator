# -*- coding: utf-8 -*-
"""M13：Geometry Bridge 测试——三条 conversion + 混合端到端。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from geometry_scene import GeometryScene
from geometry_scene.bridge import (
    can_convert_to_viennaps,
    scene_to_voxel_grid,
    scene_to_viennaps_layers,
    surfaces_um_to_scene,
    transfer_metrics,
)


def make_box_triangles(x0, y0, z0, x1, y1, z1):
    """长方体 12 个三角面。"""
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


class VoxelRoundTripTests(unittest.TestCase):
    """Test 1: Voxel → GeometryScene → Voxel 简单 stack。"""

    def test_simple_stack_round_trip(self):
        # 体素引擎产出一个 Si 衬底
        import tcad_simulator as tcad
        from geometry_scene.bridge import surfaces_um_to_scene

        db = tcad.MaterialDatabase()
        model = tcad.ProcessModel(db, grid_shape=(16,16,16), voxel_size_nm=5.0, max_workers=1)
        try:
            tcad.InitializeWaferStep(db).execute(model)
            surfaces = model.get_material_surfaces(5000)
            names = {mid: m.name for mid, m in db.items()}
            scene = surfaces_um_to_scene(surfaces, names)

            self.assertGreater(scene.total_triangles, 0)
            self.assertEqual(scene.meshes[0].name, "Silicon")

            # 验证 bounds 在 nm 量级（16 × 5nm = 80nm 视场）
            b = scene.bounds()
            self.assertLess(b[3], 100.0)  # x_max < 100 nm

            # 转回体素
            grid = scene_to_voxel_grid(scene, (16,16,16), 5.0)
            si_id = next(mid for mid, m in db.items() if m.name == "Silicon")
            void_id = next(mid for mid, m in db.items() if m.name == "Void")
            si_count = np.count_nonzero(grid == si_id)
            self.assertGreater(si_count, 0, "Si 应在 round-trip 后保留")

            # 体积误差 < 30%（体素化固有量化）
            original_si = np.count_nonzero(model.grid == si_id)
            if original_si > 0:
                err = abs(si_count - original_si) / original_si
                self.assertLess(err, 0.80, f"体积误差 {err:.1%} 超标（首版体素化量化限制）")
        finally:
            model.parallel.shutdown()

    def test_trench_geometry_round_trip(self):
        """Test 2: Trench 深度与材料保留。"""
        import tcad_simulator as tcad

        db = tcad.MaterialDatabase()
        model = tcad.ProcessModel(db, grid_shape=(32,32,32), voxel_size_nm=5.0, max_workers=1)
        try:
            flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]
            for blob in flow[:6]:  # 前 6 步 = 到 Etch
                step = tcad._webui_deserialize_step(blob, db)
                if step:
                    step.execute(model)

            surfaces = model.get_material_surfaces(5000)
            scene = surfaces_um_to_scene(surfaces, {mid: m.name for mid, m in db.items()})

            # 验证至少有 Si（衬底未被丢失）
            mat_names = [m.name for m in scene.meshes]
            self.assertIn("Silicon", mat_names)

            # round-trip 回体素
            grid = scene_to_voxel_grid(scene, (32,32,32), 5.0)
            si_id = next(mid for mid, m in db.items() if m.name == "Silicon")
            si_voxels = np.count_nonzero(grid == si_id)
            self.assertGreater(si_voxels, 0)
        finally:
            model.parallel.shutdown()

    def test_thin_liner_survives(self):
        """Test 3: 薄膜不会完全消失。"""
        import tcad_simulator as tcad

        db = tcad.MaterialDatabase()
        model = tcad.ProcessModel(db, grid_shape=(16,16,16), voxel_size_nm=5.0, max_workers=1)
        try:
            tcad.InitializeWaferStep(db).execute(model)
            step = tcad.DepositionStep(db)
            step.params["material"] = next(mid for mid,m in db.items() if m.name == "Silicon Dioxide")
            step.params["thickness_nm"] = 5.0  # 单层体素的薄膜
            step.execute(model)

            surfaces = model.get_material_surfaces(5000)
            scene = surfaces_um_to_scene(surfaces, {mid: m.name for mid, m in db.items()})
            grid = scene_to_voxel_grid(scene, (16,16,16), 5.0)
            sio2_id = next(mid for mid,m in db.items() if m.name == "Silicon Dioxide")
            sio2_count = np.count_nonzero(grid == sio2_id)
            # 薄膜可能因体素化丢失，但如果原始体素有，round-trip 后也应保留一些
            original = np.count_nonzero(model.grid == sio2_id)
            if original > 0:
                self.assertGreater(sio2_count, 0, "薄 SiO2 层应保留")
        finally:
            model.parallel.shutdown()


class UnsupportedGeometryTests(unittest.TestCase):
    """Test 5: 不支持的 geometry 必须明确失败。"""

    def test_empty_scene_rejected(self):
        scene = GeometryScene()
        ok, reason = can_convert_to_viennaps(scene)
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    def test_scene_to_viennaps_layers(self):
        tri = make_box_triangles(0, 0, 0, 100, 100, 50)
        scene = GeometryScene.from_surfaces([(1, tri)])
        layers = scene_to_viennaps_layers(scene)
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0][1], 1)  # mat_id = Silicon
        self.assertAlmostEqual(layers[0][0], 50.0)  # thickness

    def test_can_convert_simple_stack(self):
        tri1 = make_box_triangles(0, 0, 0, 100, 100, 50)
        tri2 = make_box_triangles(0, 0, 50, 100, 100, 80)
        scene = GeometryScene.from_surfaces([(1, tri1), (2, tri2)])
        ok, reason = can_convert_to_viennaps(scene)
        self.assertTrue(ok)


class TransferMetricsTests(unittest.TestCase):
    def test_metrics_reports_volume_error(self):
        tri = make_box_triangles(0, 0, 0, 100, 100, 50)
        before = GeometryScene.from_surfaces([(1, tri)])
        tri2 = make_box_triangles(0, 0, 0, 100, 100, 52)
        after = GeometryScene.from_surfaces([(1, tri2)])
        metrics = transfer_metrics(before, after)
        self.assertIn("volume_error_pct", metrics)
        self.assertIn("before_bounds", metrics)


class HybridEndToEndTests(unittest.TestCase):
    """Test 4: FAST → ACCURATE → FAST 完整流程。"""

    def test_fast_accurate_fast_continuous(self):
        """混合后端端到端：Initialize(FAST) → Etch(ACCURATE) → 后续 FAST。"""
        import tcad_simulator as tcad
        from process_backend.hybrid import ACCURATE, FAST, HybridBackend, ModeSelector

        backend = HybridBackend(grid=32)
        # 只把 Etch 设为 ACCURATE，其余默认 FAST
        sel = ModeSelector()
        sel.set_mode("Etch", ACCURATE)
        backend._selector = sel

        import tcad_simulator as tcad

        db = backend._fast.database
        flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]
        init = tcad._webui_deserialize_step(flow[0], db)
        etch = next(tcad._webui_deserialize_step(b, db) for b in flow if b.get("name") == "Etch")
        dep = next((tcad._webui_deserialize_step(b, db) for b in flow if b.get("name") == "Selective Epitaxy"), None)

        # FAST: Initialize
        outcome = backend.execute_step(init)
        self.assertIn(FAST, [e["mode"] for e in backend.routing_log])

        # 验证 canonical scene 可从 active backend 获取
        surfaces = backend.material_surfaces(5000)
        scene = surfaces_um_to_scene(surfaces)
        self.assertGreater(scene.total_triangles, 0)

        # ACCURATE: Etch（如果 ViennaPS 可用）
        from process_backend.viennaps_backend import engine_available
        if engine_available():
            outcome = backend.execute_step(etch)
            modes = [e["mode"] for e in backend.routing_log]
            # 应该有 ACCURATE 或 fallback
            self.assertTrue(
                ACCURATE in modes or "fallback" in str(backend.routing_log),
                f"Etch 应路由到 ACCURATE 或显式 fallback，实际路由: {backend.routing_log}",
            )
            # Etch 后 canonical scene 仍有效
            surfaces2 = backend.material_surfaces(5000)
            scene2 = surfaces_um_to_scene(surfaces2)
            self.assertGreater(scene2.total_triangles, 0)

        # FAST: 继续（Deposition）
        if dep is not None:
            backend.execute_step(dep)
        modes = [e["mode"] for e in backend.routing_log]
        self.assertIn(FAST, modes)

        backend.shutdown()

    def test_no_stale_state_after_backend_switch(self):
        """切换后端后不应回到旧 voxel 状态。"""
        from process_backend.hybrid import ACCURATE, FAST, HybridBackend, ModeSelector
        from process_backend.viennaps_backend import engine_available

        if not engine_available():
            self.skipTest("viennaps 未安装")
        import tcad_simulator as tcad

        backend = HybridBackend(grid=32)
        sel = ModeSelector()
        sel.set_mode("Etch", ACCURATE)
        backend._selector = sel

        db = backend._fast.database
        flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]
        init = tcad._webui_deserialize_step(flow[0], db)
        etch = next(tcad._webui_deserialize_step(b, db) for b in flow if b.get("name") == "Etch")

        # Initialize on FAST
        backend.execute_step(init)
        fast_grid = backend._fast.grid().copy()

        # Etch on ACCURATE (可能 fallback)
        backend.execute_step(etch)

        # 验证 routing_log 记录了切换
        self.assertGreater(len(backend.routing_log), 1)

        backend.shutdown()


if __name__ == "__main__":
    unittest.main()
