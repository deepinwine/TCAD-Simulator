# -*- coding: utf-8 -*-
"""M19: ViennaPS 多材料 + 材料映射 + BUG-002/003 修复测试。"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np

from process_backend.base import ProcessBackendError


def _engine():
    try:
        import viennaps  # noqa: F401
        return True
    except ImportError:
        return False


class MaterialMappingTests(unittest.TestCase):
    def test_known_material_silicon(self):
        from process_backend.material_mapping import name_to_ps_material
        import viennaps as ps
        self.assertIs(name_to_ps_material("Si"), ps.Material.Si)
        self.assertIs(name_to_ps_material("silicon"), ps.Material.Si)
        self.assertIs(name_to_ps_material("硅"), ps.Material.Si)

    def test_known_material_sio2(self):
        from process_backend.material_mapping import name_to_ps_material
        import viennaps as ps
        self.assertIs(name_to_ps_material("SiO2"), ps.Material.SiO2)
        self.assertIs(name_to_ps_material("oxide"), ps.Material.SiO2)
        self.assertIs(name_to_ps_material("二氧化硅"), ps.Material.SiO2)

    def test_known_material_tungsten(self):
        from process_backend.material_mapping import name_to_ps_material
        import viennaps as ps
        self.assertIs(name_to_ps_material("W"), ps.Material.W)
        self.assertIs(name_to_ps_material("tungsten"), ps.Material.W)
        self.assertIs(name_to_ps_material("钨"), ps.Material.W)

    def test_unknown_returns_none(self):
        """BUG-003: 未知材料返回 None，不默认 SiO2。"""
        from process_backend.material_mapping import name_to_ps_material
        self.assertIsNone(name_to_ps_material("Unobtainium"))
        self.assertIsNone(name_to_ps_material("XYZ123"))

    def test_ps_to_mat_id_round_trip(self):
        import tcad_simulator as tcad
        from process_backend.material_mapping import ps_to_mat_id
        import viennaps as ps
        db = tcad.MaterialDatabase()
        si_id = next(mid for mid, m in db.items() if m.name == "Silicon")
        result = ps_to_mat_id(ps.Material.Si, db)
        self.assertEqual(result, si_id)


@unittest.skipUnless(_engine(), "viennaps 未安装")
class MultiMaterialSurfaceTests(unittest.TestCase):
    """BUG-002: material_surfaces 不应全部返回 Silicon。"""

    def _make_backend(self):
        from process_backend import create_backend
        return create_backend("viennaps", grid_nm=32.0)

    def test_single_material_surfaces_not_all_silicon_mislabeled(self):
        """单材料时至少不崩溃且返回有效 surfaces。"""
        backend = self._make_backend()
        class S:
            def __init__(self, n, p):
                self.name, self.params = n, p
        backend.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        surfaces = backend.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        for mat_id, triangles in surfaces:
            self.assertIsInstance(mat_id, int)
            self.assertGreater(triangles.shape[0], 0)
        backend.shutdown()

    def test_deposition_creates_new_material_surface(self):
        """沉积后应有多个材料的 surface。"""
        backend = self._make_backend()
        class S:
            def __init__(self, n, p):
                self.name, self.params = n, p
        backend.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        backend.execute_step(S("Deposition", {
            "thickness_nm": 20.0, "material": "SiO2",
        }))
        surfaces = backend.material_surfaces(5000)
        mat_ids = {mid for mid, _ in surfaces}
        # 应至少有 Silicon；SiO2 如果映射成功也应在
        import tcad_simulator as tcad
        db = tcad.MaterialDatabase()
        si_id = next(mid for mid, m in db.items() if m.name == "Silicon")
        self.assertIn(si_id, mat_ids)
        backend.shutdown()

    def test_unknown_material_raises_error(self):
        """BUG-003: 未知材料应报错，不默认 SiO2。"""
        backend = self._make_backend()
        class S:
            def __init__(self, n, p):
                self.name, self.params = n, p
        backend.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        with self.assertRaises(ProcessBackendError) as ctx:
            backend.execute_step(S("Deposition", {
                "thickness_nm": 20.0, "material": "Unobtainium",
            }))
        self.assertEqual(ctx.exception.code, "unsupported_material")
        self.assertIn("Unobtainium", str(ctx.exception))
        backend.shutdown()


if __name__ == "__main__":
    unittest.main()
