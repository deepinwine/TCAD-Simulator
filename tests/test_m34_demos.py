"""M34: Advanced semiconductor demo suite tests."""
import os, unittest
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np

from demos import DEMO_FLOWS
from demos.flows import (
    ALD_LINER_W_FILL_FLOW, BEOL_VIA_FLOW, BOND_THIN_FLOW,
    CONTACT_PLUG_FLOW, HAR_TRENCH_FLOW, SPACER_FLOW, STI_FLOW,
)


class DemoFlowDefinitionTests(unittest.TestCase):
    """验证每个 demo flow 的结构完整性和步骤有效性。"""

    def _get_factory_names(self):
        import tcad_simulator as tcad
        return set(tcad.PROCESS_STEP_FACTORIES.keys())

    def _validate_flow(self, flow):
        self.assertIn("domain", flow)
        domain = flow["domain"]
        self.assertLess(flow["steps"][0]["params"]["thickness_nm"],
                        domain["grid_shape"][2] * domain["voxel_size_nm"])
        self.assertIn("name", flow)
        self.assertIn("description", flow)
        self.assertIn("steps", flow)
        self.assertGreater(len(flow["steps"]), 0)

        factories = self._get_factory_names()
        for i, step in enumerate(flow["steps"]):
            self.assertIn("name", step, f"step {i} missing name in {flow['name']}")
            self.assertIn(step["name"], factories,
                          f"step {i} '{step['name']}' not in PROCESS_STEP_FACTORIES")
            self.assertIn("params", step)
            self.assertIn("enabled", step)

    def test_sti_flow(self):
        self._validate_flow(STI_FLOW)
        self.assertGreater(len(STI_FLOW["steps"]), 5)

    def test_contact_plug_flow(self):
        self._validate_flow(CONTACT_PLUG_FLOW)
        # Should have TiN + W + CMP
        step_names = [s["name"] for s in CONTACT_PLUG_FLOW["steps"]]
        self.assertIn("CMP", step_names)
        materials = [s.get("params", {}).get("material") for s in CONTACT_PLUG_FLOW["steps"]]
        self.assertIn("TiN", materials)
        self.assertIn("Tungsten", materials)

    def test_beol_via_flow(self):
        self._validate_flow(BEOL_VIA_FLOW)
        materials = [s.get("params", {}).get("material") for s in BEOL_VIA_FLOW["steps"]]
        self.assertIn("Copper", materials)
        self.assertIn("TaN", materials)

    def test_spacer_flow(self):
        self._validate_flow(SPACER_FLOW)
        # Should have conformal SiN + anisotropic etchback
        materials = [s.get("params", {}).get("material") for s in SPACER_FLOW["steps"]]
        self.assertIn("Silicon Nitride", materials)
        self.assertIn("Polysilicon", materials)

    def test_har_trench_flow(self):
        self._validate_flow(HAR_TRENCH_FLOW)
        # HAR should have deep etch
        etch_steps = [s for s in HAR_TRENCH_FLOW["steps"] if s["name"] == "Etch"]
        self.assertGreater(len(etch_steps), 0)
        self.assertTrue(any(s["params"].get("material") == "Silicon" for s in etch_steps))

    def test_ald_liner_flow(self):
        self._validate_flow(ALD_LINER_W_FILL_FLOW)
        materials = [s.get("params", {}).get("material") for s in ALD_LINER_W_FILL_FLOW["steps"]]
        self.assertIn("Silicon Nitride", materials)
        self.assertIn("TiN", materials)
        self.assertIn("Tungsten", materials)

    def test_bond_thin_flow(self):
        self._validate_flow(BOND_THIN_FLOW)
        step_names = [s["name"] for s in BOND_THIN_FLOW["steps"]]
        self.assertIn("Wafer Flip", step_names)
        self.assertIn("Bonding", step_names)
        self.assertIn("Thinning", step_names)

    def test_all_registered(self):
        """All M34 flows are in DEMO_FLOWS."""
        expected = [
            "STI (Shallow Trench Isolation)",
            "Contact Plug (W Fill + CMP)",
            "BEOL Via (Dual Damascene)",
            "Spacer Formation (SADP-like)",
            "HAR Trench (DRIE)",
            "ALD Liner + W Fill",
            "Bond + Flip + Thin",
        ]
        for name in expected:
            self.assertIn(name, DEMO_FLOWS)
            self.assertIsNotNone(DEMO_FLOWS[name], f"{name} should have a flow definition")


    def test_advanced_flows_share_public_registry_and_are_copied(self):
        import tcad_simulator as tcad
        db = tcad.MaterialDatabase()
        registered = tcad.load_demo_flows(db)
        for name, flow in DEMO_FLOWS.items():
            if flow is not None:
                self.assertIn(name, registered)
                self.assertEqual(registered[name], flow)
                self.assertEqual(flow["name"], name)
        registered[STI_FLOW["name"]]["steps"][0]["params"]["thickness_nm"] = -1
        registered[STI_FLOW["name"]]["domain"]["grid_shape"][2] = 1
        self.assertEqual(tcad.load_demo_flows(db)[STI_FLOW["name"]], STI_FLOW)

    def test_advanced_parameters_pass_the_executable_import_contract(self):
        import tcad_simulator as tcad
        from recipe_planner.schema import validate_import
        db = tcad.MaterialDatabase()
        for name, flow in DEMO_FLOWS.items():
            with self.subTest(demo=name):
                validate_import(flow, db)
                for blob in flow["steps"]:
                    if blob["name"] == "Deposition":
                        self.assertIn("thickness", blob["params"])
                        self.assertNotIn("thickness_nm", blob["params"])
                    if blob["name"] == "Mask Exposure":
                        self.assertEqual(blob["params"]["advanced_enable"], 1)
                        mask = np.asarray(blob["custom_mask"])
                        self.assertTrue(np.any(mask == 1))
                        self.assertTrue(np.any(mask == 0))


class DemoExecutionTests(unittest.TestCase):
    """M34 demos 可在 VoxelBackend 上真实执行。"""

    def _run_flow(self, flow):
        import tcad_simulator as tcad
        db = tcad.MaterialDatabase()
        domain = flow["domain"]
        model = tcad.ProcessModel(db, grid_shape=tuple(domain["grid_shape"]),
                                  voxel_size_nm=domain["voxel_size_nm"], max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        trace = []
        for index, blob in enumerate(flow["steps"]):
            step = tcad._webui_deserialize_step(blob, db)
            self.assertIsNotNone(step, f"{flow['name']} step {index + 1}")
            before = model.grid.copy()
            try:
                step.execute(model)
            except Exception as exc:
                self.fail(f"{flow['name']} step {index + 1} ({step.name}): {exc}")
            trace.append((blob, before, model.grid.copy()))
        self.assertEqual(len(trace), len(flow["steps"]))
        self.assertFalse(np.any(model.grid == db.id_for("Photoresist")))
        return db, model, trace

    def assert_pattern_opened(self, db, trace):
        develops = [after for blob, before, after in trace if blob["name"] == "Resist Develop"]
        self.assertTrue(develops)
        for after in develops:
            resist_xy = np.any(after == db.id_for("Photoresist"), axis=2)
            self.assertTrue(np.any(resist_xy))
            self.assertTrue(np.any(~resist_xy))

    def test_executor_reports_a_failed_step_instead_of_accepting_substrate(self):
        from copy import deepcopy
        flow = deepcopy(STI_FLOW)
        flow["steps"] = [flow["steps"][0],
                         {"name": "Fill", "enabled": True, "params": {"max_depth_nm": -1}}]
        with self.assertRaisesRegex(AssertionError, r"step 2 \(Fill\)"):
            self._run_flow(flow)

    def test_executor_reports_an_unknown_step_instead_of_skipping_it(self):
        from copy import deepcopy
        flow = deepcopy(STI_FLOW)
        flow["steps"] = [flow["steps"][0], {"name": "Not a process", "params": {}}]
        with self.assertRaisesRegex(AssertionError, "step 2"):
            self._run_flow(flow)

    def test_sti_fills_etched_silicon_with_oxide(self):
        db, model, trace = self._run_flow(STI_FLOW)
        self.assert_pattern_opened(db, trace)
        silicon, oxide = db.id_for("Silicon"), db.id_for("Silicon Dioxide")
        before, after = next((before, after) for blob, before, after in trace
                             if blob["name"] == "Etch" and blob["params"]["material"] == "Silicon")
        removed = (before == silicon) & (after == 0)
        self.assertGreater(np.count_nonzero(removed), 0)
        self.assertTrue(np.all(model.grid[removed] == oxide))
        self.assertTrue(np.all(model.grid[:8, :, :20] == silicon))
        self.assertLessEqual(np.ptp(model.height_map), 1)

    def assert_filled_contacts(self, flow, metal_name, liner_names):
        from tests.test_process_cad_demos import xy_component_count
        db, model, trace = self._run_flow(flow)
        self.assert_pattern_opened(db, trace)
        metal = model.grid == db.id_for(metal_name)
        self.assertEqual(xy_component_count(np.any(metal, axis=2)), 4)
        self.assertGreater(np.unique(np.argwhere(metal)[:, 2]).size, 2)
        self.assertFalse(np.any(np.all(metal, axis=(0, 1))))
        before, after = next((before, after) for blob, before, after in trace
                             if blob["name"] == "Etch" and blob["params"]["material"] == "Silicon Dioxide")
        opened = (before == db.id_for("Silicon Dioxide")) & (after == 0)
        self.assertTrue(np.all(opened[metal]))
        for name in liner_names:
            liner = model.grid == db.id_for(name)
            self.assertTrue(np.any(liner), name)
            self.assertFalse(np.any(np.all(liner, axis=(0, 1))), name)
        self.assertTrue(np.any(model.grid == db.id_for("Silicon Dioxide")))
        self.assertLessEqual(np.ptp(model.height_map), 1)
        for blob, before, after in trace:
            if blob["name"] == "Fill":
                self.assertGreater(np.count_nonzero(after == db.id_for(metal_name)),
                                   np.count_nonzero(before == db.id_for(metal_name)))

    def test_contact_plug_retains_four_tin_lined_tungsten_contacts(self):
        self.assert_filled_contacts(CONTACT_PLUG_FLOW, "Tungsten", ("TiN",))

    def test_beol_via_retains_four_tan_lined_copper_vias(self):
        self.assert_filled_contacts(BEOL_VIA_FLOW, "Copper", ("TaN",))

    def test_ald_liner_fill_retains_liner_and_barrier(self):
        self.assert_filled_contacts(ALD_LINER_W_FILL_FLOW, "Tungsten", ("Silicon Nitride", "TiN"))

    def test_spacer_retains_two_multilayer_sidewalls_without_mandrel(self):
        from tests.test_process_cad_demos import xy_component_count
        db, model, trace = self._run_flow(SPACER_FLOW)
        self.assert_pattern_opened(db, trace)
        self.assertFalse(np.any(model.grid == db.id_for("Polysilicon")))
        spacer = model.grid == db.id_for("Silicon Nitride")
        self.assertEqual(xy_component_count(np.any(spacer, axis=2)), 2)
        self.assertGreaterEqual(np.unique(np.argwhere(spacer)[:, 2]).size, 3)
        self.assertFalse(np.any(spacer[model.grid.shape[0] // 2]))
        self.assertFalse(np.any(np.all(spacer, axis=(0, 1))))

    def test_har_has_open_oxide_window_and_deep_silicon_trench(self):
        db, model, trace = self._run_flow(HAR_TRENCH_FLOW)
        self.assert_pattern_opened(db, trace)
        oxide_xy = np.any(model.grid == db.id_for("Silicon Dioxide"), axis=2)
        self.assertTrue(np.any(oxide_xy))
        self.assertTrue(np.any(~oxide_xy))
        center = model.grid.shape[0] // 2
        silicon = model.grid == db.id_for("Silicon")
        field_top = np.flatnonzero(silicon[4, center])[-1]
        trench_top = np.flatnonzero(silicon[center, center])[-1]
        self.assertGreaterEqual(field_top - trench_top, 30)
        self.assertTrue(np.all(model.grid[center, center, trench_top + 1:] == 0))

    def test_bond_flip_thin_preserves_handle_and_eight_layer_device(self):
        db, model, trace = self._run_flow(BOND_THIN_FLOW)
        self.assertEqual(model.active_side, "bottom")
        silicon_z = np.flatnonzero(np.all(model.grid == db.id_for("Silicon"), axis=(0, 1)))
        segments = np.split(silicon_z, np.where(np.diff(silicon_z) != 1)[0] + 1)
        self.assertEqual(len(segments), 2)
        self.assertEqual([len(s) for s in segments], [20, 8])
        self.assertTrue(np.all(model.grid[:, :, segments[0][-1]+1:segments[1][0]]
                               == db.id_for("Silicon Dioxide")))


if __name__ == "__main__":
    unittest.main()
