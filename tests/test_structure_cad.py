import unittest
import tempfile
from pathlib import Path
from unittest import mock
import numpy as np
import tcad_simulator as tcad


class StructureCADTests(unittest.TestCase):
    def setUp(self):
        self.db = tcad.MaterialDatabase()
        self.model = tcad.ProcessModel(self.db, grid_shape=(12, 12, 20), voxel_size_nm=5, max_workers=1)
        self.addCleanup(self.model.parallel.shutdown)

    def step(self, name, **params):
        self.assertIn(name, tcad.PROCESS_STEP_FACTORIES)
        step = tcad.PROCESS_STEP_FACTORIES[name](self.db)
        step.params.update(params)
        step.execute(self.model)
        return step

    def test_dimensions_without_physics(self):
        with mock.patch.object(self.model, 'deposit_material', side_effect=AssertionError('physics')), mock.patch.object(self.model, 'etch_material', side_effect=AssertionError('physics')), mock.patch.object(self.model, 'expose_resist', side_effect=AssertionError('physics')):
            self.step('Structure Wafer', material='Silicon', thickness_nm=20)
            self.step('Structure Deposit', material='Silicon Dioxide', thickness_nm=20)
            self.step('Structure Pattern', pattern='Open')
            self.step('Structure Etch', material='Silicon Dioxide', depth_nm=10)
        self.assertTrue(np.all(self.model.height_map == 6))
        self.assertEqual(np.count_nonzero(self.model.grid == self.db.id_for('Silicon')), 12*12*4)
        self.assertEqual(self.model.current_time_s, 0)

    def test_overflow_and_invalid_values_are_atomic(self):
        self.step('Structure Wafer', thickness_nm=20)
        before = self.model.grid.copy()
        for value in (200, .1, True, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.step('Structure Deposit', thickness_nm=value)
            np.testing.assert_array_equal(before, self.model.grid)

    def test_mask_preserved_fields_cleared_and_etch_blocked_by_void_or_material(self):
        self.step('Structure Wafer', thickness_nm=40)
        opened = np.zeros((12, 12), dtype=bool)
        opened[2:10, 2:10] = True
        self.model.open_mask = opened.copy()
        self.model.grid[3, 3, 6] = 0
        self.model.grid[4, 4, 6] = self.db.id_for('Copper')
        self.model.doping = np.full(self.model.grid.shape, 7.0)
        self.step('Structure Etch', material='Silicon', depth_nm=20)
        self.assertEqual(self.model.grid[3, 3, 5], self.db.id_for('Silicon'))
        self.assertEqual(self.model.grid[4, 4, 5], self.db.id_for('Silicon'))
        self.assertEqual(self.model.doping[5, 5, 7], 0)
        self.assertEqual(self.model.doping[0, 0, 7], 7)
        np.testing.assert_array_equal(opened, self.model.open_mask)

    def test_taper_and_full_open_edges(self):
        self.step('Structure Wafer', thickness_nm=40)
        opened = np.zeros((12, 12), dtype=bool)
        opened[2:10, 2:10] = True
        self.model.open_mask = opened
        self.step('Structure Etch', material='Silicon', depth_nm=20, sidewall_angle_deg=45)
        self.assertEqual(self.model.height_map[2, 2], 7)
        self.assertEqual(self.model.height_map[5, 5], 4)
        self.step('Structure Wafer', thickness_nm=40)
        self.model.open_mask.fill(True)
        self.step('Structure Etch', material='Silicon', depth_nm=20, sidewall_angle_deg=45)
        self.assertTrue(np.all(self.model.height_map == 4))

    def test_etch_depth_beyond_domain_stops_at_bottom(self):
        self.step('Structure Wafer', thickness_nm=40)
        self.model.open_mask.fill(True)
        self.step('Structure Etch', material='Silicon', depth_nm=200)
        self.assertFalse(self.model.grid.any())

    def test_fill_planarize_and_recipe_roundtrip(self):
        self.step('Structure Wafer', thickness_nm=20)
        self.model.grid[2, 2, 1] = 0
        self.step('Structure Fill', material='Copper', height_nm=30)
        self.assertEqual(self.model.grid[2, 2, 1], self.db.id_for('Copper'))
        self.step('Structure Planarize', height_nm=25)
        self.assertTrue(np.all(self.model.height_map == 5))
        for name in tcad.PROCESS_STEP_FACTORIES:
            if name.startswith('Structure '):
                step = tcad.PROCESS_STEP_FACTORIES[name](self.db)
                restored = tcad._webui_deserialize_step(tcad._webui_serialize_step(step), self.db)
                self.assertEqual(restored.params, step.params)

    def test_invalid_pattern_direction_material_and_noop(self):
        self.step('Structure Wafer', thickness_nm=20)
        before = self.model.grid.copy()
        for params in ({'material': 'Missing'}, {'material': True}, {'sidewall_angle_deg': 0}, {'sidewall_angle_deg': 91}, {'material': 'Copper'}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.step('Structure Etch', **params)
            np.testing.assert_array_equal(before, self.model.grid)
        self.model.active_side = 'bottom'
        with self.assertRaises(ValueError):
            self.step('Structure Fill', height_nm=30)
        self.model.active_side = 'top'
        pattern = tcad.StructurePatternStep(self.db)
        pattern.params['mask_mode'] = 'Custom'
        pattern.custom_mask = np.zeros((12, 12), dtype=bool)
        with self.assertRaisesRegex(ValueError, 'opening'):
            pattern.execute(self.model)

    def test_pattern_rejects_unknown_modes_and_patterns_and_orientation_range(self):
        for params in ({'mask_mode':'Bogus'}, {'pattern':'Bogus'}, {'orientation':181}):
            step = tcad.StructurePatternStep(self.db)
            step.params.update(params)
            before = self.model.open_mask.copy()
            with self.subTest(params=params), self.assertRaises(ValueError):
                step.execute(self.model)
            np.testing.assert_array_equal(before,self.model.open_mask)

    def test_demo_is_fresh_and_measured(self):
        key = 'Structure CAD — Trench'
        flow = tcad.load_demo_flows(self.db)[key]
        model = tcad.ProcessModel(self.db, grid_shape=(64,64,64), voxel_size_nm=5, max_workers=1)
        self.addCleanup(model.parallel.shutdown)
        for blob in flow['steps']:
            tcad._webui_deserialize_step(blob, self.db).execute(model)
        self.assertTrue(np.all(model.height_map == 32))
        self.assertEqual(set(np.unique(model.grid)), {0, self.db.id_for('Silicon'), self.db.id_for('Silicon Dioxide'), self.db.id_for('Copper')})
        flow['steps'][0]['params']['thickness_nm'] = -1
        self.assertEqual(tcad.load_demo_flows(self.db)[key]['steps'][0]['params']['thickness_nm'], 100)

    def test_asset_exact_revision_sha_and_snapshot_mask(self):
        self.step('Structure Wafer', thickness_nm=20)
        from layout import LayoutAdapter
        from mask_assets import MaskAssetService, MaskAssetStore
        from tests.test_mask_assets import _candidate
        with tempfile.TemporaryDirectory() as directory:
            adapter = object.__new__(LayoutAdapter)
            adapter._delegate, adapter._gdstk, adapter._backend = None, None, 'normalized'
            service = MaskAssetService(MaskAssetStore(Path(directory)), adapter=adapter)
            payload = _candidate()
            payload['bounds_nm'] = [0,0,60,60]
            payload['shapes'] = [{'id':'left','type':'rectangle','layer_id':'10/0','x_nm':0,'y_nm':0,'width_nm':30,'height_nm':60}]
            first = service.save_candidate(payload)
            payload['shapes'][0]['x_nm'] = 30
            service.save_candidate(payload)
            step = tcad.StructurePatternStep(self.db)
            step.bind_mask_asset_service(service)
            step.params.update(mask_mode='Asset',mask_asset_id=first.id,mask_asset_revision=1)
            step.execute(self.model)
            self.assertTrue(self.model.open_mask[:6].all())
            self.assertFalse(self.model.open_mask[6:].any())
            self.assertEqual(step.last_metrics['mask_sha256'], first.sha256)
            self.assertEqual(step.last_metrics['mask_asset_revision'], 1)
            snapshot = self.model.snapshot_state()
            expected = self.model.open_mask.copy()
            self.step('Structure Deposit', material='Copper', thickness_nm=5, coverage='Open mask')
            self.model.restore_state(snapshot)
            np.testing.assert_array_equal(self.model.open_mask, expected)
