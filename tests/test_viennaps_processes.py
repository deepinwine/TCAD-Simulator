# -*- coding: utf-8 -*-
"""M14：ViennaPS Accurate 工艺扩展测试。"""
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


@unittest.skipUnless(_engine(), "viennaps 未安装")
class ExpandedProcessTests(unittest.TestCase):
    def setUp(self):
        from process_backend import create_backend

        self.backend = create_backend("viennaps", grid_nm=32.0)

    def tearDown(self):
        self.backend.shutdown()

    def _init(self):
        from tcad_simulator import MaterialDatabase
        from process_backend import create_backend

        class S:
            def __init__(self, n, p):
                self.name, self.params = n, p

        self.backend.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))

    def _run_step(self, name, params):
        class S:
            def __init__(self, n, p):
                self.name, self.params = n, p

        return self.backend.execute_step(S(name, params))

    def test_capabilities_list(self):
        caps = self.backend.capabilities()
        self.assertIn("accurate_support", caps)
        self.assertTrue(caps["accurate_support"]["Wet Etch (isotropic)"])
        self.assertTrue(caps["accurate_support"]["Deposition (conformal)"])
        self.assertFalse(caps["accurate_support"]["CMP"])

    def test_isotropic_etch_produces_geometry(self):
        """P1 各向同性刻蚀。"""
        self._init()
        outcome = self._run_step("Wet Etch", {"time": 10.0, "rate": 5.0})
        self.assertIn("刻蚀", outcome.message)
        surfaces = self.backend.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        self.assertGreater(surfaces[0][1].shape[0], 0)

    def test_conformal_deposition_produces_geometry(self):
        """P4 共形沉积。"""
        self._init()
        outcome = self._run_step("Deposition", {"thickness_nm": 20.0, "material": "SiO2"})
        self.assertIn("沉积", outcome.message)
        surfaces = self.backend.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)

    def test_dry_etch_still_works(self):
        """P3 已有 SF6O2 Dry Etch 仍正常。"""
        self._init()
        outcome = self._run_step("Etch", {"time": 5.0, "chemistry": "Dry"})
        self.assertIn("SF6O2", outcome.message)

    def test_unsupported_chemistry_explicit_error(self):
        self._init()
        with self.assertRaises(ProcessBackendError) as ctx:
            self._run_step("Etch", {"time": 5.0, "chemistry": "PlasmaReactiveIonWhatever"})
        self.assertEqual(ctx.exception.code, "unsupported_step")

    def test_unsupported_step_explicit_fallback_hint(self):
        with self.assertRaises(ProcessBackendError) as ctx:
            self._run_step("CMP", {"target": 300})
        self.assertEqual(ctx.exception.code, "unsupported_step")
        self.assertIn("voxel", str(ctx.exception.suggestion))


if __name__ == "__main__":
    unittest.main()
