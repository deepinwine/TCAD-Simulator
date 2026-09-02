# -*- coding: utf-8 -*-
"""M10：GeometryScene 双后端统一与 VTK/STL 导出。"""
from __future__ import annotations

import os
import struct
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from geometry_scene import GeometryScene, MaterialMesh


def make_rect_triangles(x0, y0, z0, x1, y1, z1):
    """生成长方体的 12 个三角面（简化测试用）。"""
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


class GeometrySceneTests(unittest.TestCase):
    def test_from_surfaces_and_bounds(self):
        tri = make_rect_triangles(0, 0, 0, 100, 200, 50)
        scene = GeometryScene.from_surfaces([(1, tri)], {1: "Silicon"})
        self.assertEqual(len(scene.meshes), 1)
        self.assertEqual(scene.meshes[0].name, "Silicon")
        self.assertEqual(scene.total_triangles, 12)
        b = scene.bounds()
        self.assertAlmostEqual(b[0], 0)
        self.assertAlmostEqual(b[3], 100)

    def test_merge_same_material(self):
        tri = make_rect_triangles(0, 0, 0, 10, 10, 10)
        scene = GeometryScene()
        scene.add(1, tri)
        scene.add(1, tri)
        self.assertEqual(scene.total_triangles, 24)

    def test_stl_export_binary(self):
        tri = make_rect_triangles(0, 0, 0, 50, 50, 20)
        scene = GeometryScene.from_surfaces([(2, tri)])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.stl"
            written = scene.export_stl(out)
            self.assertTrue(written[0].exists())
            data = written[0].read_bytes()
            count = struct.unpack("<I", data[80:84])[0]
            self.assertEqual(count, 12)
            self.assertEqual(len(data), 84 + 50 * count)

    def test_vtp_export_xml(self):
        tri1 = make_rect_triangles(0, 0, 0, 50, 50, 20)
        tri2 = make_rect_triangles(60, 0, 0, 100, 50, 20)
        scene = GeometryScene.from_surfaces([(1, tri1), (2, tri2)])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scene.vtp"
            scene.export_vtp(out)
            content = out.read_text()
            self.assertIn("<VTKFile", content)
            self.assertIn("MaterialId", content)
            self.assertIn('NumberOfPolys="24"', content)

    def test_empty_scene_raises_on_export(self):
        scene = GeometryScene()
        with self.assertRaises(ValueError):
            scene.export_vtp(Path("/tmp/_never.vtp"))


class DualBackendSceneTests(unittest.TestCase):
    """双后端产出统一 GeometryScene。"""

    def test_voxel_backend_produces_scene(self):
        import tcad_simulator as tcad
        from geometry_scene import GeometryScene
        from process_backend import create_backend

        backend = create_backend("voxel", grid=32)
        database = backend.database
        flow = tcad.load_demo_flows(database)["Basic Trench"]["steps"]
        for blob in flow:
            step = tcad._webui_deserialize_step(blob, database)
            backend.execute_step(step)

        names = {mid: mat.name for mid, mat in database.items()}
        scene = GeometryScene.from_surfaces(
            backend.material_surfaces(10000), names,
        )
        self.assertGreater(scene.total_triangles, 0)
        mat_names = [m.name for m in scene.meshes]
        self.assertIn("Silicon", mat_names)
        with tempfile.TemporaryDirectory() as tmp:
            scene.export_vtp(Path(tmp) / "voxel.vtp")
        backend.shutdown()

    def test_viennaps_backend_produces_scene(self):
        from process_backend import engine_available

        if not engine_available():
            self.skipTest("viennaps 未安装")
        from process_backend import create_backend

        class S:
            def __init__(self, n, p):
                self.name, self.params = n, p

        backend = create_backend("viennaps", grid_nm=32.0)
        backend.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        scene = GeometryScene.from_surfaces(backend.material_surfaces(10000))
        self.assertGreater(scene.total_triangles, 0)
        with tempfile.TemporaryDirectory() as tmp:
            scene.export_vtp(Path(tmp) / "vps.vtp")
        backend.shutdown()


if __name__ == "__main__":
    unittest.main()
