import re
import unittest
from types import SimpleNamespace
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


class FillTests(unittest.TestCase):
    def _make_side_open_cavity_model(self, direction, *, remote_column=False, at_domain_edge=False):
        db, model = make_model((12, 12, 12))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        x_start = 0 if at_domain_edge else 3
        if direction == "top":
            model.grid[x_start : x_start + 5, 3:7, 0:6] = np.uint16(silicon_id)
            cavity_z = slice(2, 4)
            remote_z = slice(0, 6)
        else:
            model.grid[x_start : x_start + 5, 3:7, 4:10] = np.uint16(silicon_id)
            cavity_z = slice(6, 8)
            remote_z = slice(4, 10)
        model.grid[x_start : x_start + 2, 4:6, cavity_z] = np.uint16(0)
        if remote_column:
            model.grid[1, 3, remote_z] = np.uint16(silicon_id)
        model._rebuild_height_map()
        return db, model, (slice(x_start, x_start + 2), slice(4, 6), cavity_z)

    def test_side_open_capped_cavity_is_exterior_connected(self):
        for direction in ("top", "bottom"):
            with self.subTest(direction=direction):
                db, model, cavity = self._make_side_open_cavity_model(direction)
                copper_id = db.id_for("Copper")

                filled = model.fill_voids("Copper", 40.0, direction=direction)

                self.assertEqual(filled, 2 * 2 * 2)
                self.assertTrue(np.all(model.grid[cavity] == copper_id))

    def test_remote_unrelated_column_does_not_change_side_open_fill(self):
        scipy_backend = tcad._scipy_ndimage
        for direction in ("top", "bottom"):
            for fallback in (False, True):
                with self.subTest(direction=direction, fallback=fallback):
                    grids = []
                    counts = []
                    backend = None if fallback else scipy_backend
                    for remote_column in (False, True):
                        db, model, cavity = self._make_side_open_cavity_model(
                            direction,
                            remote_column=remote_column,
                        )
                        with mock.patch.object(tcad, "_scipy_ndimage", backend):
                            counts.append(model.fill_voids("Copper", 40.0, direction=direction))
                        grids.append(model.grid[cavity].copy())

                    self.assertEqual(counts, [2 * 2 * 2, 2 * 2 * 2])
                    self.assertTrue(np.array_equal(grids[0], grids[1]))
                    self.assertTrue(np.all(grids[0] == db.id_for("Copper")))

    def test_side_open_cavity_at_model_boundary_is_seeded_as_exterior(self):
        for direction in ("top", "bottom"):
            with self.subTest(direction=direction):
                db, model, cavity = self._make_side_open_cavity_model(direction, at_domain_edge=True)
                copper_id = db.id_for("Copper")

                filled = model.fill_voids("Copper", 40.0, direction=direction)

                self.assertEqual(filled, 2 * 2 * 2)
                self.assertTrue(np.all(model.grid[cavity] == copper_id))

    def test_through_hole_is_part_of_wafer_footprint_from_top_and_bottom(self):
        for direction, expected_z in (("top", slice(3, 6)), ("bottom", slice(0, 3))):
            with self.subTest(direction=direction):
                db, model = make_model((10, 10, 10))
                self.addCleanup(model.parallel.shutdown)
                silicon_id = db.id_for("Silicon")
                copper_id = db.id_for("Copper")
                model.grid[1:9, 1:9, :6] = np.uint16(silicon_id)
                model.grid[4:6, 4:6, :6] = np.uint16(0)
                model._rebuild_height_map()

                filled = model.fill_voids("Copper", 30.0, direction=direction)

                self.assertEqual(filled, 2 * 2 * 3)
                self.assertTrue(np.all(model.grid[4:6, 4:6, expected_z] == copper_id))
                outside_wafer = np.ones(model.grid.shape[:2], dtype=bool)
                outside_wafer[1:9, 1:9] = False
                self.assertFalse(np.any(model.grid[outside_wafer, :] == copper_id))

    def test_through_hole_footprint_has_a_no_scipy_fallback(self):
        db, model = make_model((9, 9, 9))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[1:8, 1:8, :6] = np.uint16(silicon_id)
        model.grid[3:5, 3:5, :6] = np.uint16(0)
        model._rebuild_height_map()

        with mock.patch.object(tcad, "_scipy_ndimage", None):
            filled = model.fill_voids("Copper", 20.0, direction="top")

        self.assertEqual(filled, 2 * 2 * 2)
        self.assertTrue(np.all(model.grid[3:5, 3:5, 4:6] == copper_id))

    def test_open_xy_concavity_and_bbox_exterior_are_not_promoted_to_footprint(self):
        db, model = make_model((12, 12, 10))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[2:10, 2:10, :6] = np.uint16(silicon_id)
        model.grid[2:6, 5:7, :6] = np.uint16(0)
        model._rebuild_height_map()

        filled = model.fill_voids("Copper", 30.0, direction="top")

        self.assertEqual(filled, 0)
        self.assertFalse(np.any(model.grid[2:6, 5:7, :] == copper_id))
        self.assertFalse(np.any(model.grid[:2, :, :] == copper_id))
        self.assertFalse(np.any(model.grid[10:, :, :] == copper_id))

    def test_fill_open_trench_without_filling_sealed_or_external_void(self):
        db, model = make_model((12, 12, 18))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, :10] = np.uint16(silicon_id)
        model.grid[2:5, 2:5, 5:10] = np.uint16(0)
        model.grid[8:10, 8:10, 3:5] = np.uint16(0)
        model._rebuild_height_map()

        filled = model.fill_voids("Copper", 60.0, direction="top", include_sealed=False)

        self.assertEqual(filled, 3 * 3 * 5)
        self.assertTrue(np.all(model.grid[2:5, 2:5, 5:10] == copper_id))
        self.assertFalse(np.any(model.grid[8:10, 8:10, 3:5] == copper_id))
        self.assertFalse(np.any(model.grid[:, :, 10:] == copper_id))
        self.assertTrue(np.all(model.height_map == 10))
        self.assertTrue(np.all(model.open_mask))

    def test_fill_depth_uses_ceil_and_never_crosses_the_depth_window(self):
        cases = ((20.0, 2), (20.01, 3))
        for depth_nm, expected_layers in cases:
            with self.subTest(depth_nm=depth_nm):
                db, model = make_model((6, 6, 12))
                self.addCleanup(model.parallel.shutdown)
                silicon_id = db.id_for("Silicon")
                copper_id = db.id_for("Copper")
                model.grid[:, :, :8] = np.uint16(silicon_id)
                model.grid[2:4, 2:4, 1:8] = np.uint16(0)
                model._rebuild_height_map()

                filled = model.fill_voids("Copper", depth_nm, direction="top")

                first_filled_z = 8 - expected_layers
                self.assertEqual(filled, 2 * 2 * expected_layers)
                self.assertTrue(np.all(model.grid[2:4, 2:4, first_filled_z:8] == copper_id))
                self.assertFalse(np.any(model.grid[2:4, 2:4, :first_filled_z] == copper_id))

    def test_fill_from_bottom_is_directionally_symmetric(self):
        db, model = make_model((7, 7, 14))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, 4:12] = np.uint16(silicon_id)
        model.grid[2:5, 2:5, 4:10] = np.uint16(0)
        model._rebuild_height_map()

        filled = model.fill_voids("Copper", 30.0, direction="bottom")

        self.assertEqual(filled, 3 * 3 * 3)
        self.assertTrue(np.all(model.grid[2:5, 2:5, 4:7] == copper_id))
        self.assertFalse(np.any(model.grid[2:5, 2:5, 7:10] == copper_id))
        self.assertFalse(np.any(model.grid[:, :, :4] == copper_id))

    def test_include_sealed_fills_only_cavities_inside_the_depth_window(self):
        db, model = make_model((10, 10, 15))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, :10] = np.uint16(silicon_id)
        model.grid[2:4, 2:4, 5:7] = np.uint16(0)
        model.grid[6:8, 6:8, 2:4] = np.uint16(0)
        model._rebuild_height_map()

        filled = model.fill_voids("Copper", 60.0, direction="top", include_sealed=True)

        self.assertEqual(filled, 2 * 2 * 2)
        self.assertTrue(np.all(model.grid[2:4, 2:4, 5:7] == copper_id))
        self.assertFalse(np.any(model.grid[6:8, 6:8, 2:4] == copper_id))
        self.assertFalse(np.any(model.grid[:, :, 10:] == copper_id))

    def test_empty_model_returns_zero_and_validation_is_explicit(self):
        db, model = make_model((4, 4, 6))
        self.addCleanup(model.parallel.shutdown)

        self.assertEqual(model.fill_voids("Copper", 10.0), 0)
        for material in ("Void", "Missingium", True):
            with self.subTest(material=material):
                with self.assertRaises(ValueError):
                    model.fill_voids(material, 10.0)
        for depth in (float("nan"), float("inf"), float("-inf"), 0.0, -1.0, True):
            with self.subTest(depth=depth):
                with self.assertRaises(ValueError):
                    model.fill_voids("Copper", depth)
        with self.assertRaises(ValueError):
            model.fill_voids("Copper", 10.0, direction="side")
        for include_sealed in (1, "yes", None):
            with self.subTest(include_sealed=include_sealed):
                with self.assertRaises(ValueError):
                    model.fill_voids("Copper", 10.0, include_sealed=include_sealed)

    def test_fill_accepts_integer_and_zero_dimensional_material_ids(self):
        for as_zero_dimensional in (False, True):
            with self.subTest(as_zero_dimensional=as_zero_dimensional):
                db, model = make_model((4, 4, 6))
                self.addCleanup(model.parallel.shutdown)
                silicon_id = db.id_for("Silicon")
                copper_id = db.id_for("Copper")
                model.grid[:, :, :4] = np.uint16(silicon_id)
                model.grid[1, 1, 2:4] = np.uint16(0)
                model._rebuild_height_map()
                selector = np.array(copper_id, dtype=np.int64) if as_zero_dimensional else copper_id

                filled = model.fill_voids(selector, 10.0)

                self.assertEqual(filled, 1)
                self.assertEqual(int(model.grid[1, 1, 3]), copper_id)
                self.assertEqual(int(model.grid[1, 1, 2]), 0)

    def test_fill_clears_ghost_state_without_breaking_field_aliases(self):
        db, model = make_model((4, 4, 6))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :4] = np.uint16(silicon_id)
        model.grid[1, 1, 3] = np.uint16(0)
        model._rebuild_height_map()
        canonical_fields = (
            "doping",
            "active_dopants",
            "interstitials",
            "vacancies",
            "cluster_interstitial",
            "cluster_bic",
            "damage_concentration",
            "temperature",
        )
        for field_name in canonical_fields:
            setattr(model, field_name, np.full(model.grid.shape, 321.5, dtype=np.float32))
        model.defects_interstitial = model.interstitials
        model.defects_vacancy = model.vacancies
        species = np.full(model.grid.shape, 654.0, dtype=np.float32)
        model.dopant_species_fields = {"B": species}
        resist_acid = np.full(model.grid.shape, 987.0, dtype=np.float32)
        model._resist_state = SimpleNamespace(acid=resist_acid)

        filled = model.fill_voids("Copper", 10.0)

        self.assertEqual(filled, 1)
        self.assertIs(model.defects_interstitial, model.interstitials)
        self.assertIs(model.defects_vacancy, model.vacancies)
        for field_name in model._spatial_volume_field_names():
            field = getattr(model, field_name)
            with self.subTest(field_name=field_name):
                self.assertEqual(float(field[1, 1, 3]), 0.0)
                self.assertEqual(float(field[0, 0, 3]), 321.5)
        self.assertEqual(float(species[1, 1, 3]), 0.0)
        self.assertEqual(float(species[0, 0, 3]), 654.0)
        self.assertEqual(float(resist_acid[1, 1, 3]), 0.0)
        self.assertEqual(float(resist_acid[0, 0, 3]), 987.0)

    def test_fill_step_factory_specs_execution_roundtrip_and_default_recipe(self):
        db, model = make_model((5, 5, 7))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, :5] = np.uint16(silicon_id)
        model.grid[2, 2, 3:5] = np.uint16(0)
        model._rebuild_height_map()
        step = tcad.PROCESS_STEP_FACTORIES["Fill"](db)
        step.params.update(
            {
                "material": "Copper",
                "max_depth_nm": 20.0,
                "direction": "top",
                "include_sealed": False,
            }
        )

        result = step.execute(model)
        blob = tcad._webui_serialize_step(step)
        restored = tcad._webui_deserialize_step(blob, db)

        self.assertIsInstance(step, tcad.FillStep)
        self.assertEqual(int(model.grid[2, 2, 3]), copper_id)
        self.assertEqual(int(model.grid[2, 2, 4]), copper_id)
        self.assertIn("2", result)
        self.assertIn("Copper", result)
        self.assertIsInstance(restored, tcad.FillStep)
        self.assertEqual(restored.params, step.params)
        specs = {spec.key: spec for spec in restored.parameter_specs()}
        self.assertEqual(specs["material"].type, "enum")
        self.assertNotIn("Void", [choice[0] for choice in specs["material"].choices])
        self.assertEqual(specs["max_depth_nm"].type, "float")
        self.assertEqual([choice[0] for choice in specs["direction"].choices], ["top", "bottom"])
        self.assertEqual(specs["include_sealed"].type, "bool")
        self.assertNotIn("Fill", [item.name for item in tcad._webui_default_recipe(db)])
