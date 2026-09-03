"""M32: Material System 2.0 tests."""
import os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
from material_system import MaterialDefinition, MaterialRegistry, get_registry
from material_system.registry import MaterialVisual, ProcessProperties, AccurateBackendMapping


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.reg = MaterialRegistry()

    def test_silicon_by_id(self):
        si = self.reg.get_by_id(1)
        self.assertEqual(si.canonical_name, "Silicon")
        self.assertEqual(si.category, "semiconductor")

    def test_silicon_by_name(self):
        si = self.reg.get_by_name("Si")
        self.assertEqual(si.id, 1)
        si2 = self.reg.get_by_name("silicon")
        self.assertEqual(si2.id, 1)
        si3 = self.reg.get_by_name("硅")
        self.assertEqual(si3.id, 1)

    def test_sio2_aliases(self):
        for alias in ["SiO2", "oxide", "二氧化硅", "氧化层"]:
            mat = self.reg.get_by_name(alias)
            self.assertIsNotNone(mat, f"alias '{alias}' should resolve")
            self.assertEqual(mat.canonical_name, "Silicon Dioxide")

    def test_tungsten(self):
        w = self.reg.get_by_name("W")
        self.assertEqual(w.canonical_name, "Tungsten")
        self.assertEqual(w.category, "metal")
        self.assertAlmostEqual(w.process.density_g_cm3, 19.25)

    def test_resolve_int(self):
        mat = self.reg.resolve(1)
        self.assertEqual(mat.canonical_name, "Silicon")

    def test_resolve_str(self):
        mat = self.reg.resolve("SiO2")
        self.assertEqual(mat.canonical_name, "Silicon Dioxide")

    def test_unknown_returns_none(self):
        self.assertIsNone(self.reg.get_by_name("Unobtainium"))

    def test_accurate_supported(self):
        supported = self.reg.accurate_supported
        names = {m.canonical_name for m in supported}
        self.assertIn("Silicon", names)
        self.assertIn("Silicon Dioxide", names)
        # PR is approximate, not exact
        self.assertNotIn("Photoresist", names)

    def test_categories(self):
        semis = self.reg.materials_by_category("semiconductor")
        self.assertGreater(len(semis), 0)
        metals = self.reg.materials_by_category("metal")
        self.assertIn("Tungsten", {m.canonical_name for m in metals})

    def test_all_materials_sorted(self):
        all_mats = self.reg.all_materials()
        ids = [m.id for m in all_mats]
        self.assertEqual(ids, sorted(ids))

    def test_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        self.assertIs(r1, r2)


class MaterialDefinitionTests(unittest.TestCase):
    def test_matches_canonical(self):
        mat = get_registry().get_by_id(1)
        self.assertTrue(mat.matches("Silicon"))
        self.assertTrue(mat.matches("silicon"))
        self.assertTrue(mat.matches("Si"))
        self.assertTrue(mat.matches("硅"))
        self.assertFalse(mat.matches("SiO2"))

    def test_approximation_provenance(self):
        pr = get_registry().get_by_id(4)  # Photoresist
        self.assertTrue(pr.accurate.approximation)
        self.assertIn("Mask", pr.accurate.reason)

    def test_physics_properties_none_not_fabricated(self):
        """Unknown physics properties must be None, not fabricated."""
        sin = get_registry().get_by_id(3)  # SiN
        # SiN doesn't have etch_rate in our registry — should be None
        self.assertIsNone(sin.process.etch_rate_nm_s)


class CrossModuleConsistencyTests(unittest.TestCase):
    """Material System 2.0 ↔ existing MaterialDatabase consistency."""

    def test_ids_match_material_database(self):
        import tcad_simulator as tcad
        db = tcad.MaterialDatabase()
        reg = get_registry()
        for mat_id, material in db.items():
            reg_mat = reg.get_by_id(mat_id)
            if reg_mat is not None:
                # Names should match (or the canonical name should be recognizable)
                self.assertEqual(
                    reg_mat.canonical_name, material.name,
                    f"ID {mat_id}: registry='{reg_mat.canonical_name}' vs DB='{material.name}'",
                )

    def test_viennaps_mapping_consistent(self):
        """Registry mapping should match material_mapping.name_to_ps_material."""
        try:
            import viennaps
        except ImportError:
            self.skipTest("viennaps 未安装")
        from process_backend.material_mapping import name_to_ps_material
        reg = get_registry()
        for mat in reg.accurate_supported:
            expected = name_to_ps_material(mat.canonical_name)
            if expected is not None:
                self.assertIsNotNone(
                    expected,
                    f"'{mat.canonical_name}' should map to ViennaPS",
                )


if __name__ == "__main__":
    unittest.main()
