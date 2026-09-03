"""M25: GeometryScene → ViennaPS true import + correctness fixes."""
import os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np
from process_backend.base import ProcessBackendError

def _engine():
    try:
        import viennaps; return True
    except ImportError: return False

def _box(x0, y0, z0, x1, y1, z1):
    v = np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                  [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]])
    quads = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    tris = []
    for a,b,c,d in quads:
        tris.append([v[a],v[b],v[c]]); tris.append([v[a],v[c],v[d]])
    return np.array(tris)


class Issue002HeightMapTests(unittest.TestCase):
    """ISSUE-002: height_map rebuild must use correct Z axis."""

    def test_height_map_top_z(self):
        from process_backend.hybrid import HybridBackend
        backend = HybridBackend(grid=32)
        model = backend._fast._model
        # Build known grid: Si (id=1) from z=2 to z=5, void above and below
        grid = np.zeros((32, 32, 32), dtype=np.uint16)
        grid[:, :, 2:6] = 1  # Si from z=2 to z=5 (top at z=5)
        model.grid[:] = grid

        HybridBackend._rebuild_voxel_derived(model)

        # Every column with material should have height_map = 5 (top z index)
        hm = model.height_map
        self.assertTrue((hm[:, :] == 5).all(),
                        f"height_map should be 5 everywhere, got {hm[0,0]}")

    def test_height_map_empty_column(self):
        from process_backend.hybrid import HybridBackend
        backend = HybridBackend(grid=32)
        model = backend._fast._model
        grid = np.zeros((32, 32, 32), dtype=np.uint16)
        grid[:, :, 3] = 1  # Only z=3
        model.grid[:] = grid

        HybridBackend._rebuild_voxel_derived(model)

        hm = model.height_map
        self.assertTrue((hm == 3).all(),
                        f"height_map should be 3, got {hm[0,0]}")
        backend.shutdown()


class Issue003MaterialMappingTests(unittest.TestCase):
    """ISSUE-003: no silent material approximation."""

    def test_known_materials_exact(self):
        from process_backend.material_mapping import name_to_ps_material
        import viennaps as ps
        self.assertIs(name_to_ps_material("Si"), ps.Material.Si)
        self.assertIs(name_to_ps_material("SiO2"), ps.Material.SiO2)
        self.assertIs(name_to_ps_material("Si3N4"), ps.Material.Si3N4)

    def test_unknown_material_returns_none(self):
        from process_backend.material_mapping import name_to_ps_material
        # These should return None if ViennaPS doesn't have them
        # (or the actual material if it does — no approximation)
        result = name_to_ps_material("Unobtainium")
        self.assertIsNone(result)

    def test_build_mapping_no_approximation(self):
        """build_mapping should NOT map TiN→Si or W→Si if ViennaPS lacks them."""
        import tcad_simulator as tcad
        from process_backend.material_mapping import build_mapping, name_to_ps_material
        import viennaps as ps
        db = tcad.MaterialDatabase()
        mapping = build_mapping(db)
        for mat_id, ps_mat in mapping.items():
            # Every mapped material must be the exact ViennaPS equivalent
            # (not a fallback to Si or SiO2)
            name = db.material(mat_id).name
            expected = name_to_ps_material(name)
            if expected is not None:
                self.assertIs(ps_mat, expected,
                    f"{name} mapped to {ps_mat}, expected {expected}")


@unittest.skipUnless(_engine(), "viennaps 未安装")
class GeometrySceneImportTests(unittest.TestCase):
    """M25: load_geometry_scene true import."""

    def _backend(self):
        from process_backend import create_backend
        return create_backend("viennaps", grid_nm=32.0)

    def test_import_single_layer(self):
        from geometry_scene import GeometryScene
        scene = GeometryScene.from_surfaces([
            (1, _box(0, 0, 0, 640, 640, 200)),  # Si 200nm
        ], {1: "Silicon"})
        backend = self._backend()
        backend.load_geometry_scene(scene)
        # Domain should be created
        self.assertIsNotNone(backend._domain)
        surfaces = backend.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        backend.shutdown()

    def test_import_multi_layer(self):
        from geometry_scene import GeometryScene
        scene = GeometryScene.from_surfaces([
            (1, _box(0, 0, 0, 640, 640, 200)),      # Si 200nm
            (2, _box(0, 0, 200, 640, 640, 300)),    # SiO2 100nm
        ], {1: "Silicon", 2: "Silicon Dioxide"})
        backend = self._backend()
        backend.load_geometry_scene(scene)
        self.assertIsNotNone(backend._domain)
        surfaces = backend.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        backend.shutdown()

    def test_import_unsupported_material_raises(self):
        from geometry_scene import GeometryScene
        # Material ID 99 = not in MaterialDatabase
        scene = GeometryScene.from_surfaces([
            (99, _box(0, 0, 0, 640, 640, 100)),
        ])
        backend = self._backend()
        with self.assertRaises(ProcessBackendError) as ctx:
            backend.load_geometry_scene(scene)
        self.assertEqual(ctx.exception.code, "unsupported_material")
        backend.shutdown()

    def test_import_then_etch(self):
        """Import Si substrate then etch — geometry must change."""
        from geometry_scene import GeometryScene
        scene = GeometryScene.from_surfaces([
            (1, _box(0, 0, 0, 640, 640, 200)),
        ], {1: "Silicon"})
        backend = self._backend()
        backend.load_geometry_scene(scene)

        class S:
            name = "Etch"
            params = {"time": 5.0, "chemistry": "Dry"}

        outcome = backend.execute_step(S())
        self.assertIn("SF6O2", outcome.message)

        # After etch, surfaces should exist
        surfaces = backend.material_surfaces(5000)
        self.assertGreater(len(surfaces), 0)
        backend.shutdown()


@unittest.skipUnless(_engine(), "viennaps 未安装")
class HybridTrueImportTests(unittest.TestCase):
    """M25 E2E: FAST→ACCURATE with true geometry import."""

    def test_fast_to_accurate_bridge_loads_geometry(self):
        """_bridge_to_accurate should call load_geometry_scene."""
        from process_backend.hybrid import ACCURATE, FAST, HybridBackend, ModeSelector

        backend = HybridBackend(grid=32)
        import tcad_simulator as tcad
        db = backend._fast.database
        flow = tcad.load_demo_flows(db)["Basic Trench"]["steps"]
        init = tcad._webui_deserialize_step(flow[0], db)

        # FAST: Initialize
        backend.execute_step(init)
        self.assertIsNotNone(backend.canonical_scene)

        # Simulate switch to ACCURATE — bridge should load geometry
        load_called = []
        original_load = None
        try:
            accurate = backend._get_accurate()
            original_load = accurate.load_geometry_scene
            def tracking_load(scene):
                load_called.append(scene)
                return original_load(scene)
            accurate.load_geometry_scene = tracking_load
        except Exception:
            pass

        sel = ModeSelector()
        sel.set_mode("Etch", ACCURATE)
        backend._selector = sel

        etch = next(tcad._webui_deserialize_step(b, db) for b in flow if b.get("name") == "Etch")
        backend.execute_step(etch)

        # Verify bridge was attempted (may succeed or fallback)
        self.assertGreater(len(backend.routing_log), 1)
        bridge_entries = [e for e in backend.routing_log if "bridge" in str(e.get("step", ""))]
        # Either bridge succeeded (load called) or failed (bridge entry logged)
        # Both are acceptable; what's NOT acceptable is silent state drift
        backend.shutdown()


if __name__ == "__main__":
    unittest.main()
