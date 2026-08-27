import time
import tempfile
import unittest
from pathlib import Path

import numpy as np

import tcad_simulator as tcad


DEMO_NAMES = ("Basic Trench", "Spacer Formation", "Bonding + Thinning")


def execute_demo(name):
    database = tcad.MaterialDatabase()
    recipe = tcad._webui_demo_recipes(database)[name]
    model = tcad.ProcessModel(
        database,
        grid_shape=(64, 64, 96),
        voxel_size_nm=10.0,
        max_workers=1,
    )
    started = time.perf_counter()
    try:
        for index, blob in enumerate(recipe["steps"]):
            if not blob.get("enabled", True):
                continue
            step = tcad._webui_deserialize_step(blob, database)
            if step is None:
                raise AssertionError(f"{name} step {index + 1} could not be deserialized: {blob!r}")
            try:
                step.execute(model)
            except Exception as exc:
                raise AssertionError(
                    f"{name} step {index + 1} ({blob.get('name')}) failed: {exc}"
                ) from exc
        return database, model, time.perf_counter() - started
    except Exception:
        model.parallel.shutdown()
        raise


class DemoRecipeRegistryTests(unittest.TestCase):
    def test_registry_returns_three_canonical_portable_recipes(self):
        database = tcad.MaterialDatabase()

        demos = tcad._webui_demo_recipes(database)

        self.assertEqual(tuple(demos), DEMO_NAMES)
        for name, recipe in demos.items():
            with self.subTest(demo=name):
                self.assertEqual(recipe["name"], name)
                self.assertTrue(recipe["description"].strip())
                self.assertTrue(recipe["steps"])
                for blob in recipe["steps"]:
                    self.assertIn(blob["name"], tcad.PROCESS_STEP_FACTORIES)
                    self.assertNotIn("runtime_status", blob)
                    self.assertIsInstance(blob.get("params"), dict)
                    step = tcad._webui_deserialize_step(blob, database)
                    self.assertIsNotNone(step)
                    self.assertTrue(step.instance_name.strip())
                    self.assertLessEqual(len(step.instance_name), 80)

    def test_registry_returns_fresh_mutable_blobs(self):
        database = tcad.MaterialDatabase()
        first = tcad._webui_demo_recipes(database)
        first["Basic Trench"]["steps"][0]["params"]["thickness_nm"] = -1

        second = tcad._webui_demo_recipes(database)

        self.assertGreater(
            second["Basic Trench"]["steps"][0]["params"]["thickness_nm"],
            0,
        )

    def test_demo_sequences_express_the_designed_process_order(self):
        database = tcad.MaterialDatabase()
        demos = tcad._webui_demo_recipes(database)

        self.assertEqual(
            [step["name"] for step in demos["Basic Trench"]["steps"]],
            [
                "Initialize Wafer",
                "Oxidation/Nitridation",
                "Spin Resist",
                "Mask Exposure",
                "Resist Develop",
                "Etch",
                "Strip",
            ],
        )
        spacer_names = [step["name"] for step in demos["Spacer Formation"]["steps"]]
        self.assertEqual(spacer_names[0], "Initialize Wafer")
        self.assertIn("Deposition", spacer_names)
        self.assertIn("Mask Exposure", spacer_names)
        self.assertGreaterEqual(spacer_names.count("Etch"), 2)
        self.assertEqual(spacer_names[-2:], ["Etch", "Strip"])
        self.assertEqual(
            [step["name"] for step in demos["Bonding + Thinning"]["steps"]][-3:],
            ["Wafer Flip", "Bonding", "Thinning"],
        )

    def test_worker_init_exposes_the_canonical_demo_recipes(self):
        manager = None
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                manager = tcad.WebUIServerManager(
                    host="127.0.0.1",
                    port=0,
                    max_users=1,
                    storage_root=Path(temp_dir),
                    enable_ai_agent=False,
                    default_domain={
                        "grid_shape": [32, 32, 32],
                        "voxel_size_nm": 10.0,
                        "threads": 1,
                    },
                )
                manager.start()
                session, _cookie = manager.create_session()
                self.assertIsNotNone(session)

                init_result = session.rpc("init", {}, timeout_s=30.0)["result"]

                self.assertEqual(tuple(init_result["demo_recipes"]), DEMO_NAMES)
                self.assertEqual(
                    init_result["demo_recipes"],
                    tcad._webui_demo_recipes(tcad.MaterialDatabase()),
                )
            finally:
                if manager is not None:
                    manager.stop()

    def test_webui_builds_safe_selector_options_from_init_payload(self):
        self.assertIn("state.demoRecipes = init.result.demo_recipes || {};", tcad._WEBUI_SCRIPT_JS)
        self.assertIn("renderDemoRecipes();", tcad._WEBUI_SCRIPT_JS)
        self.assertNotIn("demo_trench_lpcvd", tcad._WEBUI_INDEX_HTML)
        self.assertNotIn("demo_trench_ald", tcad._WEBUI_INDEX_HTML)
        self.assertIn("option.textContent", tcad._WEBUI_SCRIPT_JS)


class DemoHeadlessAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        try:
            for name in DEMO_NAMES:
                cls.runs[name] = execute_demo(name)
        except Exception:
            for _database, model, _elapsed in cls.runs.values():
                model.parallel.shutdown()
            raise

    @classmethod
    def tearDownClass(cls):
        for _database, model, _elapsed in cls.runs.values():
            model.parallel.shutdown()

    def test_all_demos_finish_with_visible_bounded_geometry_in_reasonable_time(self):
        total_elapsed = 0.0
        for name, (database, model, elapsed) in self.runs.items():
            with self.subTest(demo=name):
                total_elapsed += elapsed
                occupied = np.argwhere(model.grid != 0)
                material_ids = np.unique(model.grid[model.grid != 0])
                self.assertGreaterEqual(len(material_ids), 2)
                self.assertGreater(occupied.size, 0)
                bbox_min = occupied.min(axis=0)
                bbox_max = occupied.max(axis=0)
                self.assertTrue(np.all(bbox_max >= bbox_min))
                for material_id in material_ids:
                    self.assertNotEqual(database.material(int(material_id)).name, "Void")
        self.assertLess(total_elapsed, 90.0)

    def test_basic_trench_strips_resist_and_leaves_patterned_oxide_on_silicon(self):
        database, model, _elapsed = self.runs["Basic Trench"]
        resist_id = database.id_for("Photoresist")
        silicon_id = database.id_for("Silicon")
        oxide_id = database.id_for("Silicon Dioxide")

        self.assertFalse(np.any(model.grid == resist_id))
        self.assertGreater(np.count_nonzero(model.grid == silicon_id), 0)
        self.assertGreater(np.count_nonzero(model.grid == oxide_id), 0)
        oxide_columns = np.any(model.grid == oxide_id, axis=2)
        self.assertTrue(np.any(oxide_columns))
        self.assertTrue(np.any(~oxide_columns))
        self.assertGreater(np.unique(model.height_map).size, 1)

    def test_spacer_demo_leaves_two_multilayer_sidewalls_after_core_strip(self):
        database, model, _elapsed = self.runs["Spacer Formation"]
        spacer_id = database.id_for("Silicon Nitride")
        core_id = database.id_for("Polysilicon")
        spacer = model.grid == spacer_id
        nx = model.grid.shape[0]

        self.assertFalse(np.any(model.grid == core_id))
        self.assertGreater(np.count_nonzero(spacer), 0)
        spacer_coords = np.argwhere(spacer)
        self.assertGreaterEqual(np.unique(spacer_coords[:, 2]).size, 3)
        self.assertTrue(np.any(spacer_coords[:, 0] < nx // 2))
        self.assertTrue(np.any(spacer_coords[:, 0] > nx // 2))
        self.assertEqual(np.count_nonzero(spacer[nx // 2, :, :]), 0)
        self.assertFalse(np.any(np.all(spacer, axis=(0, 1))))

    def test_bonding_demo_preserves_handle_bond_layer_and_thinned_device(self):
        database, model, _elapsed = self.runs["Bonding + Thinning"]
        silicon_id = database.id_for("Silicon")
        oxide_id = database.id_for("Silicon Dioxide")

        self.assertEqual(model.active_side, "bottom")
        silicon_planes = np.all(model.grid == silicon_id, axis=(0, 1))
        oxide_planes = np.all(model.grid == oxide_id, axis=(0, 1))
        silicon_z = np.flatnonzero(silicon_planes)
        oxide_z = np.flatnonzero(oxide_planes)
        self.assertGreaterEqual(oxide_z.size, 1)
        self.assertTrue(np.any(silicon_z < oxide_z.min()))
        self.assertTrue(np.any(silicon_z > oxide_z.max()))

        segments = []
        for run in np.split(silicon_z, np.where(np.diff(silicon_z) != 1)[0] + 1):
            if run.size:
                segments.append(run)
        self.assertEqual(len(segments), 2)
        handle, device = segments
        self.assertGreater(handle.size, device.size)
        self.assertEqual(device.size, 8)
        self.assertTrue(np.all(oxide_planes[handle[-1] + 1 : device[0]]))


if __name__ == "__main__":
    unittest.main()
