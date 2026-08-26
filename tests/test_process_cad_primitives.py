import re
import unittest
from unittest import mock

import numpy as np
import tcad_simulator as tcad


def make_model(shape=(10, 10, 16)):
    db = tcad.MaterialDatabase()
    model = tcad.ProcessModel(
        db,
        grid_shape=shape,
        voxel_size_nm=10.0,
        max_workers=1,
    )
    model.grid.fill(np.uint16(0))
    model._rebuild_height_map()
    return db, model


class PrimitiveFixtureTests(unittest.TestCase):
    def test_make_model_builds_empty_default_grid(self):
        db, model = make_model()
        self.addCleanup(model.parallel.shutdown)

        self.assertIsInstance(db, tcad.MaterialDatabase)
        self.assertEqual(model.grid.shape, (10, 10, 16))
        self.assertEqual(model.voxel_size_nm, 10.0)
        self.assertFalse(np.any(model.grid))
        self.assertFalse(np.any(model.height_map))


class StripTests(unittest.TestCase):
    def test_webui_bool_params_use_checkbox_and_write_boolean(self):
        bool_branch = re.compile(
            r"else if \(spec\.type === 'bool'\).*?"
            r"input\.type = 'checkbox'.*?"
            r"input\.checked = .*?"
            r"step\.params\[spec\.key\] = Boolean\(input\.checked\)",
            re.DOTALL,
        )

        self.assertRegex(tcad._WEBUI_SCRIPT_JS, bool_branch)

    def test_global_strip_removes_only_requested_materials(self):
        db, model = make_model((6, 6, 6))
        self.addCleanup(model.parallel.shutdown)
        oxide_id = db.id_for("Silicon Dioxide")
        resist_id = db.id_for("Photoresist")
        model.grid[:, :, 0] = np.uint16(oxide_id)
        model.grid[:, :, 1:3] = np.uint16(resist_id)
        model._rebuild_height_map()

        removed = model.strip_materials(["Photoresist"], exposed_only=False, direction="top")

        self.assertEqual(removed, 6 * 6 * 2)
        self.assertFalse(np.any(model.grid == resist_id))
        self.assertEqual(np.count_nonzero(model.grid == oxide_id), 6 * 6)
        self.assertTrue(np.all(model.height_map == 1))
        self.assertTrue(np.all(model.open_mask))

    def test_exposed_only_top_preserves_sealed_target_pocket(self):
        db, model = make_model((7, 7, 7))
        self.addCleanup(model.parallel.shutdown)
        oxide_id = db.id_for("Silicon Dioxide")
        resist_id = db.id_for("Photoresist")
        model.grid[1:6, 1:6, 1:6] = np.uint16(oxide_id)
        model.grid[3, 3, 3] = np.uint16(resist_id)
        model.grid[1, 1, 4:6] = np.uint16(resist_id)
        model._rebuild_height_map()

        removed = model.strip_materials("Photoresist", exposed_only=True, direction="top")

        self.assertEqual(removed, 2)
        self.assertEqual(int(model.grid[3, 3, 3]), resist_id)
        self.assertEqual(int(model.grid[1, 1, 4]), 0)
        self.assertEqual(int(model.grid[1, 1, 5]), 0)

    def test_exposed_only_top_seeds_target_on_fully_covered_boundary(self):
        db, model = make_model((4, 4, 4))
        self.addCleanup(model.parallel.shutdown)
        resist_id = db.id_for("Photoresist")
        model.grid[:, :, :] = np.uint16(resist_id)
        model._rebuild_height_map()

        removed = model.strip_materials([resist_id], exposed_only=True, direction="top")

        self.assertEqual(removed, 4 * 4 * 4)
        self.assertFalse(np.any(model.grid))

    def test_exposed_only_bottom_is_directionally_symmetric(self):
        db, model = make_model((5, 5, 5))
        self.addCleanup(model.parallel.shutdown)
        oxide_id = db.id_for("Silicon Dioxide")
        resist_id = db.id_for("Photoresist")
        model.grid[:, :, :] = np.uint16(oxide_id)
        model.grid[2, 2, 0:2] = np.uint16(resist_id)
        model.grid[2, 2, 3] = np.uint16(resist_id)
        model._rebuild_height_map()

        removed = model.strip_materials(resist_id, exposed_only=True, direction="bottom")

        self.assertEqual(removed, 2)
        self.assertEqual(int(model.grid[2, 2, 0]), 0)
        self.assertEqual(int(model.grid[2, 2, 1]), 0)
        self.assertEqual(int(model.grid[2, 2, 3]), resist_id)

    def test_model_rejects_empty_unknown_void_bool_and_bad_direction(self):
        db, model = make_model((3, 3, 3))
        self.addCleanup(model.parallel.shutdown)

        for materials in ([], "", "Missingium", "Void", 0, True):
            with self.subTest(materials=materials):
                with self.assertRaises(ValueError):
                    model.strip_materials(materials)
        with self.assertRaises(ValueError):
            model.strip_materials("Photoresist", direction="side")

    def test_material_normalizer_accepts_zero_dim_id_and_rejects_negative_ids(self):
        db, model = make_model((3, 3, 3))
        self.addCleanup(model.parallel.shutdown)
        resist_id = db.id_for("Photoresist")
        model.grid[1, 1, 1] = np.uint16(resist_id)
        model._rebuild_height_map()

        removed = model.strip_materials(np.array(resist_id, dtype=np.int64))

        self.assertEqual(removed, 1)
        for value in (-1, "-1", np.array(-1, dtype=np.int64)):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "material ID"):
                    model.strip_materials(value)

    def test_strip_clears_all_spatial_volume_fields_at_removed_voxels(self):
        db, model = make_model((3, 3, 3))
        self.addCleanup(model.parallel.shutdown)
        resist_id = db.id_for("Photoresist")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[0, 0, 1] = np.uint16(resist_id)
        model.grid[1, 1, 1] = np.uint16(oxide_id)
        expected_fields = {
            "doping",
            "active_dopants",
            "interstitials",
            "vacancies",
            "cluster_interstitial",
            "cluster_bic",
            "damage_concentration",
            "temperature",
            "defects_interstitial",
            "defects_vacancy",
        }
        self.assertEqual(set(model._spatial_volume_field_names()), expected_fields)
        for field_name in expected_fields:
            setattr(model, field_name, np.full(model.grid.shape, 321.5, dtype=np.float32))
        model._rebuild_height_map()

        model.strip_materials("Photoresist")

        for field_name in expected_fields:
            field = getattr(model, field_name)
            with self.subTest(field_name=field_name):
                self.assertEqual(float(field[0, 0, 1]), 0.0)
                self.assertEqual(float(field[1, 1, 1]), 321.5)

    def test_exposed_strip_uses_one_seed_array_and_crops_target_propagation(self):
        db, model = make_model((32, 32, 32))
        self.addCleanup(model.parallel.shutdown)
        resist_id = db.id_for("Photoresist")
        model.grid[10:12, 10:12, 28:30] = np.uint16(resist_id)
        model._rebuild_height_map()
        target = model.grid == np.uint16(resist_id)
        accessible = model.grid == 0
        original_zeros_like = np.zeros_like
        with mock.patch.object(tcad.np, "zeros_like", wraps=original_zeros_like) as zeros_like:
            seeds = tcad._strip_target_seeds(target, accessible, boundary_z=-1)
        full_shape_allocations = [
            call for call in zeros_like.call_args_list if call.args and call.args[0].shape == model.grid.shape
        ]
        self.assertEqual(len(full_shape_allocations), 1)
        self.assertEqual(seeds.dtype, np.bool_)

        propagation_shapes = []
        original_propagate = tcad._propagate_binary_3d

        def recording_propagate(seed_mask, allowed_mask):
            propagation_shapes.append((seed_mask.shape, allowed_mask.shape))
            return original_propagate(seed_mask, allowed_mask)

        with mock.patch.object(tcad, "_propagate_binary_3d", side_effect=recording_propagate):
            removed = model.strip_materials("Photoresist", exposed_only=True, direction="top")

        self.assertEqual(removed, 2 * 2 * 2)
        self.assertEqual(propagation_shapes[0], (model.grid.shape, model.grid.shape))
        self.assertEqual(propagation_shapes[1], ((2, 2, 2), (2, 2, 2)))

    def test_strip_step_parses_materials_executes_and_validates_like_model(self):
        db, model = make_model((3, 3, 4))
        self.addCleanup(model.parallel.shutdown)
        resist_id = db.id_for("Photoresist")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[0, 0, 3] = np.uint16(resist_id)
        model.grid[1, 1, 3] = np.uint16(oxide_id)
        model._rebuild_height_map()
        step = tcad.StripStep(db)
        step.params.update(
            {
                "materials": "Photoresist; Silicon Dioxide",
                "exposed_only": True,
                "direction": "top",
            }
        )

        result = step.execute(model)

        self.assertEqual(np.count_nonzero(model.grid), 0)
        self.assertIn("2", result)
        self.assertIn("Photoresist", result)
        self.assertIn("Silicon Dioxide", result)

        for materials in ("", "Void", "Missingium"):
            with self.subTest(materials=materials):
                step.params["materials"] = materials
                with self.assertRaises(ValueError):
                    step.execute(model)
        step.params["materials"] = "Photoresist"
        step.params["direction"] = "side"
        with self.assertRaises(ValueError):
            step.execute(model)

    def test_strip_step_accepts_comma_delimiters_and_recipe_roundtrips(self):
        db, model = make_model((3, 3, 3))
        self.addCleanup(model.parallel.shutdown)
        resist_id = db.id_for("Photoresist")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[0, 0, 2] = np.uint16(resist_id)
        model.grid[1, 1, 2] = np.uint16(oxide_id)
        model._rebuild_height_map()
        step = tcad.PROCESS_STEP_FACTORIES["Strip"](db)
        step.params.update(
            {
                "materials": "Photoresist, Silicon Dioxide",
                "exposed_only": False,
                "direction": "bottom",
            }
        )

        step.execute(model)
        blob = tcad._webui_serialize_step(step)
        restored = tcad._webui_deserialize_step(blob, db)

        self.assertIsInstance(restored, tcad.StripStep)
        self.assertEqual(restored.params["materials"], "Photoresist, Silicon Dioxide")
        self.assertIs(restored.params["exposed_only"], False)
        self.assertEqual(restored.params["direction"], "bottom")
        specs = {spec.key: spec for spec in restored.parameter_specs()}
        self.assertEqual(specs["materials"].type, "text")
        self.assertEqual(specs["exposed_only"].type, "bool")
        self.assertEqual([choice[0] for choice in specs["direction"].choices], ["top", "bottom"])
