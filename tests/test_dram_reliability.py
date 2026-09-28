import os
import unittest
from pathlib import Path
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
        for grid in (32, 65, 96):
            with self.subTest(grid=grid), self.assertRaisesRegex(ValueError, 'one of'):
                build_recipe(grid=grid)

    def test_high_resolution_grid_makes_equal_width_lines(self):
        from examples.run_dram_bl import build_dram_structure, validate_structure
        model, recipe, snapshots = build_dram_structure(grid=128)
        self.addCleanup(model.parallel.shutdown)
        self.assertEqual(recipe['domain']['voxel_size_nm'], model.voxel_size_nm)
        self.assertEqual(31.25, model.voxel_size_nm)
        self.assertEqual(len(snapshots), len(recipe['steps']))
        metrics = validate_structure(model, recipe)
        self.assertTrue(metrics['ok'], metrics)
        self.assertEqual(metrics['bitline_count'], 5)
        self.assertEqual(metrics['active_count'], 5)
        # 与 grid=64 不同：掩膜按体素边界生成，五条线必须等宽（不再有边缘截断的窄线）。
        self.assertEqual(1, len(set(metrics['bitline_widths_nm'])), metrics['bitline_widths_nm'])
        self.assertEqual(1, len(set(metrics['active_widths_nm'])), metrics['active_widths_nm'])
        self.assertGreater(min(metrics['active_widths_nm']), max(metrics['bitline_widths_nm']))

    def test_checked_in_masks_match_generator_design(self):
        import numpy as np
        from examples.run_dram_bl import generate_line_mask
        for grid, columns, bl_start, active_start in ((64, 58, None, None), (128, 116, 17, 14)):
            for kind, width_nm, start in (('bitline', 180, bl_start), ('active', 420, active_start)):
                if grid == 64:
                    continue  # grid=64 掩膜为历史校准文件，保持字节不变
                cols = generate_line_mask(columns, start=start, pitch_nm=600, width_nm=width_nm,
                                          count=5, voxel_nm=31.25)
                path = Path(__file__).parents[1] / 'examples' / f'dram_{kind}_mask_128.pgm'
                tokens = path.read_text().split()
                self.assertEqual(['P2', '1', str(columns)], tokens[:3])
                np.testing.assert_array_equal(np.array([int(v) for v in tokens[4:]]),
                                              np.where(cols, 0, 255))

    def test_checked_in_recipe_is_replayable(self):
        import json
        from pathlib import Path
        from examples.run_dram_bl import replay_recipe, validate_structure
        recipe = json.loads((Path(__file__).parents[1] / 'examples' / 'dram_narrow_bl_wide_active.json').read_text())
        model, loaded, snapshots = replay_recipe(recipe)
        self.addCleanup(model.parallel.shutdown)
        self.assertEqual(len(snapshots), len(recipe['steps']))
        self.assertTrue(validate_structure(model, loaded)['ok'])
