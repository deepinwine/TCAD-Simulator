import os
import unittest
os.environ.setdefault('TCAD_SKIP_QT', '1')
os.environ.setdefault('MPLBACKEND', 'Agg')
import numpy as np


class DramReliabilityTests(unittest.TestCase):
    def test_recipe_executes_and_measures_real_geometry(self):
        from examples.run_dram_bl import build_dram_structure, validate_structure
        model, recipe, snapshots = build_dram_structure(grid=64)
        self.addCleanup(model.parallel.shutdown)
        self.assertEqual(tuple(recipe['domain']['grid_shape']), model.grid.shape)
        self.assertEqual(recipe['domain']['voxel_size_nm'], model.voxel_size_nm)
        self.assertEqual(len(snapshots), len(recipe['steps']))
        self.assertFalse(np.array_equal(snapshots[0]['grid'], snapshots[-1]['grid']))
        metrics = validate_structure(model, recipe)
        self.assertEqual(metrics['bitline_count'], 5)
        self.assertEqual(metrics['active_count'], 5)
        self.assertGreater(min(metrics['active_widths_nm']), max(metrics['bitline_widths_nm']))
        self.assertTrue(metrics['ok'], metrics)

    def test_roundtrip_recipe_has_identical_final_grid(self):
        import tcad_simulator as tcad
        from examples.run_dram_bl import build_dram_structure
        model, recipe, snapshots = build_dram_structure(grid=64)
        self.addCleanup(model.parallel.shutdown)
        other = tcad.ProcessModel(tcad.MaterialDatabase(), grid_shape=model.grid.shape,
                                  voxel_size_nm=model.voxel_size_nm, max_workers=1)
        self.addCleanup(other.parallel.shutdown)
        for blob in recipe['steps']:
            tcad._webui_deserialize_step(blob, other.material_db).execute(other)
        np.testing.assert_array_equal(model.grid, other.grid)
        other.restore_state(snapshots[0])
        np.testing.assert_array_equal(other.grid, snapshots[0]['grid'])

    def test_validation_detects_missing_bitlines(self):
        from examples.run_dram_bl import build_dram_structure, validate_structure
        model, recipe, _ = build_dram_structure(grid=64)
        self.addCleanup(model.parallel.shutdown)
        model.grid[model.grid == model.material_db.id_for('Tungsten')] = 0
        self.assertFalse(validate_structure(model, recipe)['ok'])

    def test_non_calibrated_grids_are_rejected(self):
        from examples.run_dram_bl import build_recipe
        for grid in (32, 65, 128):
            with self.subTest(grid=grid), self.assertRaisesRegex(ValueError, 'exactly 64'):
                build_recipe(grid=grid)

    def test_checked_in_recipe_is_replayable(self):
        import json
        from pathlib import Path
        from examples.run_dram_bl import replay_recipe, validate_structure
        recipe = json.loads((Path(__file__).parents[1] / 'examples' / 'dram_narrow_bl_wide_active.json').read_text())
        model, loaded, snapshots = replay_recipe(recipe)
        self.addCleanup(model.parallel.shutdown)
        self.assertEqual(len(snapshots), len(recipe['steps']))
        self.assertTrue(validate_structure(model, loaded)['ok'])
