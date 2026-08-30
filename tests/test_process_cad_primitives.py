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

    def test_fill_rejects_readonly_colocated_state_before_writing_grid(self):
        db, model = make_model((3, 3, 5))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :4] = np.uint16(silicon_id)
        model.grid[1, 1, 3] = np.uint16(0)
        readonly = np.full(model.grid.shape, 42.0, dtype=np.float32)
        readonly.flags.writeable = False
        model.doping = readonly
        model._rebuild_height_map()
        before_grid = model.grid.copy()
        before_doping = model.doping.copy()

        with self.assertRaisesRegex(ValueError, r"Fill.*writable"):
            model.fill_voids("Copper", 10.0)

        np.testing.assert_array_equal(model.grid, before_grid)
        np.testing.assert_array_equal(model.doping, before_doping)

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


class WaferFlipTests(unittest.TestCase):
    @staticmethod
    def _resist_state(shape, shared):
        def volume(offset):
            return np.arange(np.prod(shape), dtype=np.float32).reshape(shape) + offset

        return tcad.ResistChemistryState(
            pac_fraction=volume(100.0),
            acid_conc=shared,
            base_conc=volume(200.0),
            polymer_fraction=volume(300.0),
            pag_fraction=volume(400.0),
            dill_A=1.6,
            dill_B=0.1,
            dill_C=0.015,
            acid_yield=0.85,
            base_power_mw=150.0,
            mack_rmax_nm_s=2.5,
            mack_rmin_nm_s=0.05,
            mack_n=4.0,
            mack_mth=0.3,
            resist_kind="positive",
            intensity_profile=np.arange(shape[0] * shape[1], dtype=np.float32).reshape(shape[:2]),
            exposure_time_s=12.0,
            dose_map_mj_cm2=np.full(shape[:2], 42.0, dtype=np.float32),
        )

    def test_flip_reverses_all_volume_fields_and_preserves_cross_container_aliases(self):
        db, model = make_model((2, 3, 4))
        self.addCleanup(model.parallel.shutdown)
        shape = model.grid.shape
        model.grid[:] = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
        shared = np.arange(np.prod(shape), dtype=np.float32).reshape(shape) + 10.0
        model.doping = shared
        model.active_dopants = shared
        for offset, field_name in enumerate(
            (
                "interstitials",
                "vacancies",
                "cluster_interstitial",
                "cluster_bic",
                "damage_concentration",
                "temperature",
            ),
            start=1,
        ):
            setattr(
                model,
                field_name,
                np.arange(np.prod(shape), dtype=np.float32).reshape(shape) + 1000.0 * offset,
            )
        model.defects_interstitial = model.interstitials
        model.defects_vacancy = model.vacancies
        species_b = np.arange(np.prod(shape), dtype=np.float32).reshape(shape) + 8000.0
        model.dopant_species_fields = {"Shared": shared, "B": species_b, "metadata": "keep"}
        model._resist_state = self._resist_state(shape, shared)
        resist_intensity_before = model._resist_state.intensity_profile.copy()
        resist_dose_before = model._resist_state.dose_map_mj_cm2.copy()

        spatial_before = {
            name: getattr(model, name)
            for name in model._spatial_volume_field_names()
        }
        resist_before = {
            name: getattr(model._resist_state, name)
            for name in ("pac_fraction", "acid_conc", "base_conc", "polymer_fraction", "pag_fraction")
        }
        volume_bindings = [model.grid, *spatial_before.values(), shared, species_b, *resist_before.values()]
        expected_by_identity = {
            id(array): np.flip(array, axis=2).copy()
            for array in volume_bindings
            if isinstance(array, np.ndarray) and array.shape == shape
        }

        original_flip = np.flip
        with mock.patch.object(tcad.np, "flip", wraps=original_flip) as flip:
            model.flip_wafer()

        np.testing.assert_array_equal(model.grid, expected_by_identity[id(volume_bindings[0])])
        for field_name in model._spatial_volume_field_names():
            field = getattr(model, field_name)
            with self.subTest(field_name=field_name):
                np.testing.assert_array_equal(field, expected_by_identity[id(spatial_before[field_name])])
        np.testing.assert_array_equal(model.dopant_species_fields["B"], expected_by_identity[id(species_b)])
        self.assertEqual(model.dopant_species_fields["metadata"], "keep")
        for field_name in ("pac_fraction", "acid_conc", "base_conc", "polymer_fraction", "pag_fraction"):
            with self.subTest(resist_field=field_name):
                np.testing.assert_array_equal(
                    getattr(model._resist_state, field_name),
                    expected_by_identity[id(resist_before[field_name])],
                )
        np.testing.assert_array_equal(model._resist_state.intensity_profile, resist_intensity_before)
        np.testing.assert_array_equal(model._resist_state.dose_map_mj_cm2, resist_dose_before)
        self.assertIs(model.doping, model.active_dopants)
        self.assertIs(model.doping, model.dopant_species_fields["Shared"])
        self.assertIs(model.doping, model._resist_state.acid_conc)
        self.assertIs(model.defects_interstitial, model.interstitials)
        self.assertIs(model.defects_vacancy, model.vacancies)
        self.assertEqual(sum(call.args[0] is shared for call in flip.call_args_list), 1)
        self.assertEqual(model.active_side, "bottom")

    def test_flip_preserves_2d_state_and_rebuilds_height_and_open_mask_from_grid(self):
        db, model = make_model((3, 3, 5))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        resist_id = db.id_for("Photoresist")
        model.grid.fill(np.uint16(0))
        model.grid[:, :, 0] = np.uint16(silicon_id)
        model.grid[1, 1, 0] = np.uint16(resist_id)
        model.grid[1, 1, 1] = np.uint16(silicon_id)
        model._rebuild_height_map()
        self.assertTrue(model.open_mask[1, 1])

        exposure = np.arange(9, dtype=np.float64).reshape(3, 3)
        intensity = exposure + 100.0
        fraction = exposure.astype(np.float32) + 200.0
        pending = exposure + 300.0
        model.resist_exposure = exposure
        model.last_intensity = intensity
        model._column_fraction = {"deposition": fraction}
        model._pending_interstitial_injection = pending

        model.flip_wafer()

        np.testing.assert_array_equal(model.resist_exposure, exposure)
        np.testing.assert_array_equal(model.last_intensity, intensity)
        np.testing.assert_array_equal(model._column_fraction["deposition"], fraction)
        np.testing.assert_array_equal(model._pending_interstitial_injection, pending)
        self.assertEqual(int(model.height_map[1, 1]), 5)
        self.assertFalse(model.open_mask[1, 1])
        other_columns = np.ones((3, 3), dtype=bool)
        other_columns[1, 1] = False
        self.assertTrue(np.all(model.open_mask[other_columns]))

    def test_double_flip_restores_volumes_side_and_reset_restores_top(self):
        _db, model = make_model((2, 2, 5))
        self.addCleanup(model.parallel.shutdown)
        model.grid[:] = np.arange(model.grid.size, dtype=np.uint16).reshape(model.grid.shape)
        model.interstitials = np.arange(model.grid.size, dtype=np.float32).reshape(model.grid.shape)
        model.defects_interstitial = model.interstitials
        before_grid = model.grid.copy()
        before_interstitials = model.interstitials.copy()

        model.flip_wafer()
        model.flip_wafer()

        np.testing.assert_array_equal(model.grid, before_grid)
        np.testing.assert_array_equal(model.interstitials, before_interstitials)
        self.assertIs(model.defects_interstitial, model.interstitials)
        self.assertEqual(model.active_side, "top")
        model.flip_wafer()
        model.reset_state()
        self.assertEqual(model.active_side, "top")

    def test_snapshot_restore_legacy_and_transaction_preserve_active_side(self):
        _db, model = make_model((2, 2, 4))
        self.addCleanup(model.parallel.shutdown)
        model.interstitials = np.arange(model.grid.size, dtype=np.float32).reshape(model.grid.shape)
        model.vacancies = model.interstitials + 100.0
        model.defects_interstitial = model.interstitials
        model.defects_vacancy = model.vacancies
        model.flip_wafer()
        snapshot = model.snapshot_state(compression="dense")
        self.assertEqual(snapshot["active_side"], "bottom")
        model.active_side = "top"
        model.restore_state(snapshot)
        self.assertEqual(model.active_side, "bottom")
        self.assertIsNotNone(model.interstitials)
        self.assertIsNotNone(model.vacancies)
        self.assertIs(model.defects_interstitial, model.interstitials)
        self.assertIs(model.defects_vacancy, model.vacancies)

        legacy = model.snapshot_state(compression="dense")
        legacy.pop("active_side")
        model.active_side = "bottom"
        model.restore_state(legacy)
        self.assertEqual(model.active_side, "top")
        legacy["active_side"] = "sideways"
        model.active_side = "bottom"
        model.restore_state(legacy)
        self.assertEqual(model.active_side, "top")

        model.flip_wafer()

        def flip_then_fail():
            model.flip_wafer()
            raise ValueError("controlled flip failure")

        result = tcad._run_model_transaction(model, flip_then_fail)
        self.assertTrue(result["rolled_back"])
        self.assertEqual(model.active_side, "bottom")

    def test_slots_resist_state_is_flipped_without_requiring_vars(self):
        class SlotsState:
            __slots__ = ("volume", "surface")

        _db, model = make_model((2, 2, 3))
        self.addCleanup(model.parallel.shutdown)
        state = SlotsState()
        state.volume = np.arange(model.grid.size, dtype=np.float32).reshape(model.grid.shape)
        state.surface = np.arange(4, dtype=np.float32).reshape(model.grid.shape[:2])
        before_volume = state.volume.copy()
        before_surface = state.surface.copy()
        model._resist_state = state

        model.flip_wafer()

        np.testing.assert_array_equal(state.volume, np.flip(before_volume, axis=2))
        np.testing.assert_array_equal(state.surface, before_surface)

    def test_step_factory_execute_roundtrip_and_default_recipe_exclusion(self):
        db, model = make_model((2, 2, 4))
        self.addCleanup(model.parallel.shutdown)
        step = tcad.PROCESS_STEP_FACTORIES["Wafer Flip"](db)

        result = step.execute(model)
        blob = tcad._webui_serialize_step(step)
        restored = tcad._webui_deserialize_step(blob, db)

        self.assertIsInstance(step, tcad.WaferFlipStep)
        self.assertEqual(step.params, {})
        self.assertIn("bottom", result.lower())
        self.assertIsInstance(restored, tcad.WaferFlipStep)
        self.assertEqual(restored.params, {})
        self.assertNotIn("Wafer Flip", [item.name for item in tcad._webui_default_recipe(db)])


class BondingTests(unittest.TestCase):
    def test_top_bonding_adds_interface_then_handle_without_changing_wafer(self):
        db, model = make_model((6, 6, 20))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[:, :, :4] = np.uint16(silicon_id)
        before = model.grid[:, :, :4].copy()
        model._rebuild_height_map()

        result = model.bond_wafer(
            handle_material="Silicon",
            handle_thickness_nm=40.0,
            bonding_material="Silicon Dioxide",
            bonding_layer_nm=10.0,
        )

        self.assertEqual(result["bond_voxels"], 1)
        self.assertEqual(result["handle_voxels"], 4)
        self.assertEqual(result["bond_cells"], 6 * 6)
        self.assertEqual(result["handle_cells"], 6 * 6 * 4)
        self.assertEqual(result["active_side"], "top")
        np.testing.assert_array_equal(model.grid[:, :, :4], before)
        self.assertTrue(np.all(model.grid[:, :, 4] == oxide_id))
        self.assertTrue(np.all(model.grid[:, :, 5:9] == silicon_id))
        self.assertFalse(np.any(model.grid[:, :, 9:]))

    def test_bottom_bonding_follows_flipped_active_side_in_physical_order(self):
        db, model = make_model((6, 6, 20))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[:, :, :4] = np.uint16(silicon_id)
        model._rebuild_height_map()
        model.flip_wafer()
        flipped_before = model.grid[:, :, 16:20].copy()

        result = model.bond_wafer("Silicon", 40.0, "Silicon Dioxide", 10.0)

        self.assertEqual(result["active_side"], "bottom")
        np.testing.assert_array_equal(model.grid[:, :, 16:20], flipped_before)
        self.assertTrue(np.all(model.grid[:, :, 15] == oxide_id))
        self.assertTrue(np.all(model.grid[:, :, 11:15] == silicon_id))
        self.assertFalse(np.any(model.grid[:, :, :11]))

    def test_zero_bond_layer_allows_direct_handle_and_thickness_uses_ceiling(self):
        db, model = make_model((3, 3, 10))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, :2] = np.uint16(silicon_id)
        model._rebuild_height_map()

        result = model.bond_wafer("Copper", 10.01, "Silicon Dioxide", 0.0)

        self.assertEqual(result["bond_voxels"], 0)
        self.assertEqual(result["handle_voxels"], 2)
        self.assertEqual(result["bond_cells"], 0)
        self.assertEqual(result["handle_cells"], 3 * 3 * 2)
        self.assertTrue(np.all(model.grid[:, :, 2:4] == copper_id))

    def test_insufficient_space_reports_required_available_and_is_atomic(self):
        db, model = make_model((4, 4, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :4] = np.uint16(silicon_id)
        model.doping = np.arange(model.grid.size, dtype=np.float32).reshape(model.grid.shape)
        model._rebuild_height_map()
        before_grid = model.grid.copy()
        before_doping = model.doping.copy()

        with self.assertRaisesRegex(ValueError, r"required.*5.*available.*4"):
            model.bond_wafer("Silicon", 40.0, "Silicon Dioxide", 10.0)

        np.testing.assert_array_equal(model.grid, before_grid)
        np.testing.assert_array_equal(model.doping, before_doping)

    def test_readonly_colocated_state_is_rejected_before_any_bonding_mutation(self):
        for readonly_location in ("grid", "doping", "resist"):
            with self.subTest(readonly_location=readonly_location):
                db, model = make_model((3, 3, 10))
                self.addCleanup(model.parallel.shutdown)
                silicon_id = db.id_for("Silicon")
                model.grid[:, :, :2] = np.uint16(silicon_id)
                writable = np.full(model.grid.shape, 23.0, dtype=np.float32)
                readonly = np.full(model.grid.shape, 47.0, dtype=np.float32)
                readonly.flags.writeable = False
                model.doping = readonly if readonly_location == "doping" else writable
                model._resist_state = SimpleNamespace(
                    volume=readonly if readonly_location == "resist" else writable,
                    surface=np.full(model.grid.shape[:2], 3.0, dtype=np.float32),
                )
                model.active_side = "sideways"
                model._rebuild_height_map()
                if readonly_location == "grid":
                    model.grid.flags.writeable = False
                before_grid = model.grid.copy()
                before_doping = model.doping.copy()
                before_resist = model._resist_state.volume.copy()
                before_surface = model._resist_state.surface.copy()
                before_side = model.active_side

                with self.assertRaisesRegex(ValueError, r"Bonding.*writable"):
                    model.bond_wafer("Silicon", 10.0, "Silicon Dioxide", 10.0)

                np.testing.assert_array_equal(model.grid, before_grid)
                np.testing.assert_array_equal(model.doping, before_doping)
                np.testing.assert_array_equal(model._resist_state.volume, before_resist)
                np.testing.assert_array_equal(model._resist_state.surface, before_surface)
                self.assertEqual(model.active_side, before_side)

    def test_empty_model_and_invalid_materials_and_thicknesses_are_rejected(self):
        _db, model = make_model((3, 3, 10))
        self.addCleanup(model.parallel.shutdown)
        with self.assertRaisesRegex(ValueError, "empty"):
            model.bond_wafer("Silicon", 10.0, "Silicon Dioxide", 0.0)

        model.grid[:, :, :2] = np.uint16(model.material_db.id_for("Silicon"))
        model._rebuild_height_map()
        invalid_materials = ("Void", 0, "Missingium", True, None)
        for value in invalid_materials:
            with self.subTest(handle_material=value):
                with self.assertRaises(ValueError):
                    model.bond_wafer(value, 10.0, "Silicon Dioxide", 0.0)
            with self.subTest(bonding_material=value):
                with self.assertRaises(ValueError):
                    model.bond_wafer("Silicon", 10.0, value, 0.0)

        for value in (0.0, -1.0, float("nan"), float("inf"), True):
            with self.subTest(handle_thickness_nm=value):
                with self.assertRaises(ValueError):
                    model.bond_wafer("Silicon", value, "Silicon Dioxide", 0.0)
        for value in (-1.0, float("nan"), float("inf"), True):
            with self.subTest(bonding_layer_nm=value):
                with self.assertRaises(ValueError):
                    model.bond_wafer("Silicon", 10.0, "Silicon Dioxide", value)

    def test_target_volume_precheck_never_overwrites_non_void_anomaly(self):
        db, model = make_model((3, 3, 12))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[:, :, :4] = np.uint16(silicon_id)
        model.grid[1, 1, 6] = np.uint16(oxide_id)
        model._rebuild_height_map()
        before = model.grid.copy()

        # Simulate stale/corrupt occupied-Z metadata so the proposed target range
        # intersects an anomalous occupied cell. The explicit target precheck must
        # still refuse the write rather than relying only on the global boundary.
        with mock.patch.object(tcad.np, "flatnonzero", return_value=np.arange(4)):
            with self.assertRaisesRegex(ValueError, "non-Void"):
                model.bond_wafer("Silicon", 40.0, "Silicon Dioxide", 10.0)

        np.testing.assert_array_equal(model.grid, before)

    def test_invalid_active_side_is_safely_normalized_to_top(self):
        db, model = make_model((2, 2, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[:, :, :2] = np.uint16(silicon_id)
        model.active_side = "sideways"
        model._rebuild_height_map()

        result = model.bond_wafer("Silicon", 10.0, "Silicon Dioxide", 10.0)

        self.assertEqual(result["active_side"], "top")
        self.assertEqual(model.active_side, "top")
        self.assertTrue(np.all(model.grid[:, :, 2] == oxide_id))
        self.assertTrue(np.all(model.grid[:, :, 3] == silicon_id))

    def test_new_material_clears_all_colocated_volume_state_and_preserves_aliases(self):
        db, model = make_model((2, 2, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :2] = np.uint16(silicon_id)
        shape = model.grid.shape
        shared = np.full(shape, 7.0, dtype=np.float32)
        model.doping = shared
        model.active_dopants = shared
        for field_name in model._spatial_volume_field_names():
            if field_name not in {"doping", "active_dopants"}:
                setattr(model, field_name, np.full(shape, 11.0, dtype=np.float32))
        model.defects_interstitial = model.interstitials
        model.defects_vacancy = model.vacancies
        species = np.full(shape, 13.0, dtype=np.float32)
        model.dopant_species_fields = {"Shared": shared, "B": species, "metadata": "keep"}
        resist_volume = np.full(shape, 17.0, dtype=np.float32)
        model._resist_state = SimpleNamespace(shared=shared, volume=resist_volume, surface=np.ones(shape[:2]))
        model._rebuild_height_map()

        model.bond_wafer("Silicon", 10.0, "Silicon Dioxide", 10.0)

        added = (slice(None), slice(None), slice(2, 4))
        original = (slice(None), slice(None), slice(0, 2))
        arrays = [
            *(getattr(model, name) for name in model._spatial_volume_field_names()),
            model.dopant_species_fields["Shared"],
            model.dopant_species_fields["B"],
            model._resist_state.shared,
            model._resist_state.volume,
        ]
        for array in arrays:
            with self.subTest(array_id=id(array)):
                self.assertTrue(np.all(array[added] == 0.0))
                self.assertTrue(np.all(array[original] != 0.0))
        self.assertIs(model.doping, model.active_dopants)
        self.assertIs(model.doping, model.dopant_species_fields["Shared"])
        self.assertIs(model.doping, model._resist_state.shared)
        self.assertIs(model.interstitials, model.defects_interstitial)
        self.assertIs(model.vacancies, model.defects_vacancy)
        self.assertEqual(model.dopant_species_fields["metadata"], "keep")
        self.assertTrue(np.all(model._resist_state.surface == 1.0))

    def test_step_factory_execute_roundtrip_and_default_recipe_exclusion(self):
        db, model = make_model((2, 2, 12))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :2] = np.uint16(silicon_id)
        model._rebuild_height_map()
        step = tcad.PROCESS_STEP_FACTORIES["Bonding"](db)
        step.params.update(
            {
                "handle_material": "Silicon",
                "handle_thickness_nm": 20.01,
                "bonding_material": "Silicon Dioxide",
                "bonding_layer_nm": 10.0,
            }
        )

        result = step.execute(model)
        blob = tcad._webui_serialize_step(step)
        restored = tcad._webui_deserialize_step(blob, db)

        self.assertIsInstance(step, tcad.BondingStep)
        self.assertEqual(step.name, "Bonding")
        self.assertEqual(step.group, "Wafer")
        self.assertEqual(set(step.params), {
            "handle_material",
            "handle_thickness_nm",
            "bonding_material",
            "bonding_layer_nm",
        })
        self.assertIn("Bonding", result)
        self.assertIn("3", result)
        self.assertIsInstance(restored, tcad.BondingStep)
        self.assertEqual(restored.params, step.params)
        self.assertNotIn("Bonding", [item.name for item in tcad._webui_default_recipe(db)])


class ThinningTests(unittest.TestCase):
    def test_flipped_wafer_thins_from_high_z_backside(self):
        db, model = make_model((5, 5, 16))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :10] = np.uint16(silicon_id)
        model._rebuild_height_map()
        model.flip_wafer()

        removed = model.thin_wafer(50.0, "Silicon")

        self.assertEqual(model.active_side, "bottom")
        self.assertEqual(removed, 5 * 5 * 5)
        self.assertTrue(np.all(model.grid[:, :, 6:11] == silicon_id))
        self.assertFalse(np.any(model.grid[:, :, :6]))
        self.assertFalse(np.any(model.grid[:, :, 11:]))

    def test_unflipped_wafer_thins_from_low_z_backside_and_preserves_outer_cap(self):
        db, model = make_model((4, 4, 14))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, 0] = np.uint16(copper_id)
        model.grid[:, :, 2:10] = np.uint16(silicon_id)
        model._rebuild_height_map()

        removed = model.thin_wafer(30.0, silicon_id)

        self.assertEqual(model.active_side, "top")
        self.assertEqual(removed, 4 * 4 * 5)
        self.assertTrue(np.all(model.grid[:, :, 0] == copper_id))
        self.assertFalse(np.any(model.grid[:, :, 2:7]))
        self.assertTrue(np.all(model.grid[:, :, 7:10] == silicon_id))

    def test_target_at_or_above_segment_thickness_is_a_zero_copy_noop(self):
        db, model = make_model((3, 3, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, 1:5] = np.uint16(silicon_id)
        model._rebuild_height_map()
        before_grid = model.grid.copy()
        before_history = list(model.history)

        self.assertEqual(model.thin_wafer(40.0, "Silicon"), 0)
        self.assertEqual(model.thin_wafer(50.0, "Silicon"), 0)

        np.testing.assert_array_equal(model.grid, before_grid)
        self.assertEqual(model.history, before_history)

    def test_non_integer_target_thickness_uses_ceiling(self):
        db, model = make_model((2, 2, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :5] = np.uint16(silicon_id)
        model._rebuild_height_map()

        removed = model.thin_wafer(20.01, "Silicon")

        self.assertEqual(removed, 2 * 2 * 2)
        self.assertFalse(np.any(model.grid[:, :, :2]))
        self.assertTrue(np.all(model.grid[:, :, 2:5] == silicon_id))

    def test_scanning_and_removal_reuse_only_one_two_dimensional_compare_buffer(self):
        db, model = make_model((7, 8, 96))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, 8:88] = np.uint16(silicon_id)
        model._rebuild_height_map()
        original_equal = np.equal
        out_shapes = []
        out_ids = []

        def recording_equal(left, right, *, out=None, **kwargs):
            self.assertIsNotNone(out)
            out_shapes.append(out.shape)
            out_ids.append(id(out))
            return original_equal(left, right, out=out, **kwargs)

        with mock.patch.object(tcad.np, "equal", side_effect=recording_equal):
            removed = model.thin_wafer(20.0, "Silicon")

        self.assertEqual(removed, 7 * 8 * 78)
        self.assertGreater(len(out_shapes), model.grid.shape[2])
        self.assertEqual(set(out_shapes), {model.grid.shape[:2]})
        self.assertEqual(len(set(out_ids)), 1)

    def test_invalid_active_side_is_normalized_after_successful_commit(self):
        db, model = make_model((3, 3, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, 1:5] = np.uint16(silicon_id)
        model.active_side = "sideways"
        model._rebuild_height_map()

        removed = model.thin_wafer(20.0, "Silicon")

        self.assertEqual(removed, 3 * 3 * 2)
        self.assertEqual(model.active_side, "top")

    def test_noop_does_not_normalize_invalid_active_side(self):
        db, model = make_model((3, 3, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, 1:5] = np.uint16(silicon_id)
        model.active_side = "sideways"
        model._rebuild_height_map()

        removed = model.thin_wafer(40.0, "Silicon")

        self.assertEqual(removed, 0)
        self.assertEqual(model.active_side, "sideways")

    def test_invalid_target_and_material_values_are_rejected(self):
        _db, model = make_model((3, 3, 8))
        self.addCleanup(model.parallel.shutdown)
        model.grid[:, :, :4] = np.uint16(model.material_db.id_for("Silicon"))
        model._rebuild_height_map()

        for thickness in (0.0, -1.0, float("nan"), float("inf"), True, None):
            with self.subTest(target_thickness_nm=thickness):
                with self.assertRaisesRegex(ValueError, "Thinning"):
                    model.thin_wafer(thickness, "Silicon")
        for material in ("Void", 0, "Missingium", True, None, ["Silicon"]):
            with self.subTest(material=material):
                with self.assertRaisesRegex(ValueError, "Thinning"):
                    model.thin_wafer(10.0, material)

    def test_empty_or_target_absent_model_returns_zero(self):
        db, model = make_model((3, 3, 8))
        self.addCleanup(model.parallel.shutdown)

        self.assertEqual(model.thin_wafer(10.0, "Silicon"), 0)
        model.grid[:, :, :4] = np.uint16(db.id_for("Copper"))
        model._rebuild_height_map()
        before = model.grid.copy()

        self.assertEqual(model.thin_wafer(10.0, "Silicon"), 0)
        np.testing.assert_array_equal(model.grid, before)

    def test_only_target_cells_in_removed_z_layers_are_cleared(self):
        db, model = make_model((3, 3, 7))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, 1:5] = np.uint16(silicon_id)
        model.grid[1, 1, 1:3] = np.uint16(copper_id)
        model._rebuild_height_map()

        removed = model.thin_wafer(20.0, "Silicon")

        self.assertEqual(removed, 3 * 3 * 2 - 2)
        self.assertEqual(int(model.grid[1, 1, 1]), copper_id)
        self.assertEqual(int(model.grid[1, 1, 2]), copper_id)
        self.assertFalse(np.any(model.grid[:, :, 1:3] == silicon_id))
        self.assertTrue(np.all(model.grid[:, :, 3:5] == silicon_id))

    def test_removed_cells_clear_all_colocated_state_once_and_preserve_aliases(self):
        db, model = make_model((2, 2, 6))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        copper_id = db.id_for("Copper")
        model.grid[:, :, 1:5] = np.uint16(silicon_id)
        model.grid[0, 0, 1] = np.uint16(copper_id)
        shape = model.grid.shape
        shared = np.full(shape, 7.0, dtype=np.float32)
        model.doping = shared
        model.active_dopants = shared
        for field_name in model._spatial_volume_field_names():
            if field_name not in {"doping", "active_dopants"}:
                setattr(model, field_name, np.full(shape, 11.0, dtype=np.float32))
        model.defects_interstitial = model.interstitials
        model.defects_vacancy = model.vacancies
        species = np.full(shape, 13.0, dtype=np.float32)
        model.dopant_species_fields = {"Shared": shared, "B": species, "metadata": "keep"}
        resist_volume = np.full(shape, 17.0, dtype=np.float32)
        model._resist_state = SimpleNamespace(
            shared=shared,
            volume=resist_volume,
            surface=np.ones(shape[:2], dtype=np.float32),
        )
        model._rebuild_height_map()

        removed = model.thin_wafer(20.0, "Silicon")

        removal_mask = np.zeros(shape, dtype=bool)
        removal_mask[:, :, 1:3] = True
        removal_mask[0, 0, 1] = False
        kept_mask = (model.grid != 0)
        self.assertEqual(removed, int(np.count_nonzero(removal_mask)))
        arrays = [
            *(getattr(model, name) for name in model._spatial_volume_field_names()),
            model.dopant_species_fields["Shared"],
            model.dopant_species_fields["B"],
            model._resist_state.shared,
            model._resist_state.volume,
        ]
        for array in arrays:
            with self.subTest(array_id=id(array)):
                self.assertTrue(np.all(array[removal_mask] == 0.0))
                self.assertTrue(np.all(array[kept_mask] != 0.0))
        self.assertIs(model.doping, model.active_dopants)
        self.assertIs(model.doping, model.dopant_species_fields["Shared"])
        self.assertIs(model.doping, model._resist_state.shared)
        self.assertIs(model.interstitials, model.defects_interstitial)
        self.assertIs(model.vacancies, model.defects_vacancy)
        self.assertEqual(model.dopant_species_fields["metadata"], "keep")
        self.assertTrue(np.all(model._resist_state.surface == 1.0))

    def test_readonly_colocated_state_is_rejected_before_any_thinning_mutation(self):
        for readonly_location in ("grid", "doping", "resist"):
            with self.subTest(readonly_location=readonly_location):
                db, model = make_model((3, 3, 8))
                self.addCleanup(model.parallel.shutdown)
                silicon_id = db.id_for("Silicon")
                model.grid[:, :, :4] = np.uint16(silicon_id)
                writable = np.full(model.grid.shape, 23.0, dtype=np.float32)
                readonly = np.full(model.grid.shape, 47.0, dtype=np.float32)
                readonly.flags.writeable = False
                model.doping = readonly if readonly_location == "doping" else writable
                model._resist_state = SimpleNamespace(
                    volume=readonly if readonly_location == "resist" else writable,
                    surface=np.full(model.grid.shape[:2], 3.0, dtype=np.float32),
                )
                model._rebuild_height_map()
                if readonly_location == "grid":
                    model.grid.flags.writeable = False
                before_grid = model.grid.copy()
                before_doping = model.doping.copy()
                before_resist = model._resist_state.volume.copy()

                with self.assertRaisesRegex(ValueError, r"Thinning.*writable"):
                    model.thin_wafer(20.0, "Silicon")

                np.testing.assert_array_equal(model.grid, before_grid)
                np.testing.assert_array_equal(model.doping, before_doping)
                np.testing.assert_array_equal(model._resist_state.volume, before_resist)

    def test_bonding_layer_separates_same_material_segments(self):
        db, model = make_model((3, 3, 16))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        oxide_id = db.id_for("Silicon Dioxide")
        model.grid[:, :, :6] = np.uint16(silicon_id)
        model._rebuild_height_map()
        model.bond_wafer("Silicon", 40.0, "Silicon Dioxide", 10.0)

        removed = model.thin_wafer(30.0, "Silicon")

        self.assertEqual(removed, 3 * 3 * 3)
        self.assertFalse(np.any(model.grid[:, :, :3]))
        self.assertTrue(np.all(model.grid[:, :, 3:6] == silicon_id))
        self.assertTrue(np.all(model.grid[:, :, 6] == oxide_id))
        self.assertTrue(np.all(model.grid[:, :, 7:11] == silicon_id))

    def test_step_factory_execute_roundtrip_and_default_recipe_exclusion(self):
        db, model = make_model((2, 2, 8))
        self.addCleanup(model.parallel.shutdown)
        silicon_id = db.id_for("Silicon")
        model.grid[:, :, :5] = np.uint16(silicon_id)
        model._rebuild_height_map()
        step = tcad.PROCESS_STEP_FACTORIES["Thinning"](db)
        step.params.update({"target_thickness_nm": 20.01, "material": "Silicon"})

        result = step.execute(model)
        blob = tcad._webui_serialize_step(step)
        restored = tcad._webui_deserialize_step(blob, db)

        self.assertIsInstance(step, tcad.ThinningStep)
        self.assertEqual(step.name, "Thinning")
        self.assertEqual(step.group, "Wafer")
        self.assertEqual(set(step.params), {"target_thickness_nm", "material"})
        self.assertIn("Thinning", result)
        self.assertIn("8", result)
        self.assertIsInstance(restored, tcad.ThinningStep)
        self.assertEqual(restored.params, step.params)
        specs = {spec.key: spec for spec in restored.parameter_specs()}
        self.assertEqual(specs["target_thickness_nm"].type, "float")
        self.assertEqual(specs["material"].type, "enum")
        self.assertNotIn("Void", [choice[0] for choice in specs["material"].choices])
        self.assertRegex(specs["material"].tooltip.lower(), r"selective|cap")
        self.assertNotIn("Thinning", [item.name for item in tcad._webui_default_recipe(db)])
