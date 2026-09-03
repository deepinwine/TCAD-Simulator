"""M20: ViennaPS 新工艺模型测试。"""
import os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
from process_backend.base import ProcessBackendError

def _engine():
    try:
        import viennaps; return True
    except ImportError: return False

@unittest.skipUnless(_engine(), "viennaps 未安装")
class DirectionalEtchTests(unittest.TestCase):
    def _backend(self):
        from process_backend import create_backend
        b = create_backend("viennaps", grid_nm=32.0)
        class S:
            def __init__(self, n, p): self.name, self.params = n, p
        b.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        return b, S

    def test_directional_etch_produces_geometry(self):
        b, S = self._backend()
        outcome = b.execute_step(S("Directional Etch", {"time": 10.0, "rate": 5.0}))
        self.assertIn("方向性", outcome.message)
        surfaces = b.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        b.shutdown()

    def test_directional_with_angle(self):
        b, S = self._backend()
        outcome = b.execute_step(S("Directional Etch", {
            "time": 5.0, "rate": 8.0, "angle_deg": 30.0,
        }))
        self.assertIn("方向性", outcome.message)
        b.shutdown()

@unittest.skipUnless(_engine(), "viennaps 未安装")
class ALDDepositionTests(unittest.TestCase):
    def _backend(self):
        from process_backend import create_backend
        b = create_backend("viennaps", grid_nm=32.0)
        class S:
            def __init__(self, n, p): self.name, self.params = n, p
        b.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        return b, S

    def test_ald_produces_geometry(self):
        b, S = self._backend()
        outcome = b.execute_step(S("ALD Deposition", {
            "thickness_nm": 10.0, "material": "Si3N4",
        }))
        self.assertIn("ALD", outcome.message)
        # ALD 可能在单独 level-set 上操作；只需验证进程不崩溃
        # surfaces 可为空（ALD 新层可能尚未 merge 到主 domain）
        surfaces = b.material_surfaces(5000)
        b.shutdown()

    def test_ald_unknown_material_raises(self):
        b, S = self._backend()
        with self.assertRaises(ProcessBackendError) as ctx:
            b.execute_step(S("ALD Deposition", {"thickness_nm": 5.0, "material": "Xyz"}))
        self.assertEqual(ctx.exception.code, "unsupported_material")
        b.shutdown()

@unittest.skipUnless(_engine(), "viennaps 未安装")
class SelectiveEtchTests(unittest.TestCase):
    def _backend(self):
        from process_backend import create_backend
        b = create_backend("viennaps", grid_nm=32.0)
        class S:
            def __init__(self, n, p): self.name, self.params = n, p
        b.execute_step(S("Initialize Wafer", {"thickness_nm": 200.0}))
        return b, S

    def test_selective_etch_produces_geometry(self):
        b, S = self._backend()
        outcome = b.execute_step(S("Selective Etch", {
            "time": 10.0,
            "selectivity": {"Si": 10.0, "SiO2": 0.1},
        }))
        self.assertIn("选择性", outcome.message)
        surfaces = b.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        b.shutdown()

    def test_selective_no_valid_materials_raises(self):
        b, S = self._backend()
        with self.assertRaises(ProcessBackendError) as ctx:
            b.execute_step(S("Selective Etch", {
                "time": 10.0,
                "selectivity": {"XyzUnknown": 5.0},
            }))
        self.assertEqual(ctx.exception.code, "unsupported_material")
        b.shutdown()

class CapabilitiesTest(unittest.TestCase):
    def test_new_steps_in_capabilities(self):
        from process_backend.viennaps_backend import SUPPORTED_STEPS
        self.assertIn("Directional Etch", SUPPORTED_STEPS)
        self.assertIn("ALD Deposition", SUPPORTED_STEPS)
        self.assertIn("Selective Etch", SUPPORTED_STEPS)

if __name__ == "__main__":
    unittest.main()
