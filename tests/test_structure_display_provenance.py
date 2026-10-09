import tempfile
import unittest
from pathlib import Path

import numpy as np
import tcad_simulator as tcad


class DisplayProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.db = tcad.MaterialDatabase()
        self.model = tcad.ProcessModel(self.db, grid_shape=(4, 4, 20), voxel_size_nm=5, max_workers=1)
        self.addCleanup(self.model.parallel.shutdown)

    def step(self, name, **params):
        step = tcad.PROCESS_STEP_FACTORIES[name](self.db)
        step.params.update(params)
        step.execute(self.model)
        return step

    def test_same_material_deposits_have_separate_owners(self):
        wafer = self.step('Structure Wafer', thickness_nm=10)
        a = self.step('Structure Deposit', material='Silicon', thickness_nm=10)
        b = self.step('Structure Deposit', material='Silicon', thickness_nm=10)
        source = self.model.display_provenance
        self.assertEqual(source.step_ids[int(source.owners[0, 0, 0])], wafer.step_id)
        self.assertEqual(source.step_ids[int(source.owners[0, 0, 2])], a.step_id)
        self.assertEqual(source.step_ids[int(source.owners[0, 0, 4])], b.step_id)
        self.assertFalse(source.owners[:, :, 6:].any())

    def test_explicit_same_material_replacement_is_owned_even_where_unchanged(self):
        self.step('Structure Wafer', material='Silicon', thickness_nm=10)
        wafer = self.step('Structure Wafer', material='Silicon', thickness_nm=15)
        source = self.model.display_provenance
        self.assertEqual(set(np.unique(source.owners[:, :, :3])), {source.owner_for(wafer.step_id)})

    def test_etch_cmp_strip_clear_deleted_owners_without_restoring_material(self):
        self.step('Structure Wafer', thickness_nm=10)
        self.step('Structure Deposit', material='Silicon Dioxide', thickness_nm=20)
        self.step('Structure Etch', material='Silicon Dioxide', depth_nm=5)
        self.step('Structure Planarize', height_nm=15)
        self.step('Structure Deposit', material='Photoresist', thickness_nm=5)
        self.step('Structure Strip')
        source = self.model.display_provenance
        self.assertFalse(source.owners[self.model.grid == 0].any())
        self.assertEqual(len(source.step_ids), 3)
        self.assertFalse(self.model.grid[:, :, 3:].any())

    def test_pattern_and_doping_do_not_create_entity_owners(self):
        self.step('Structure Wafer', thickness_nm=20)
        before = self.model.display_provenance.owners.copy()
        self.step('Structure Pattern', pattern='Open')
        self.step('Structure Doping', depth_nm=5)
        np.testing.assert_array_equal(before, self.model.display_provenance.owners)
        self.assertEqual(len(self.model.display_provenance.step_ids), 1)

    def test_snapshots_restore_owners_and_legacy_snapshot_is_unknown(self):
        self.step('Structure Wafer', thickness_nm=10)
        expected = self.model.display_provenance.owners.copy()
        with tempfile.TemporaryDirectory() as directory:
            snap = self.model.snapshot_state('dense-zlib', {'spill_dir': directory, 'spill_tag': 'source', 'spill_threshold_bytes': 1})
            self.assertIn('display_owners', snap)
            self.assertTrue(any('display_owners' in p for p in snap['__aux_paths__']))
            self.step('Structure Deposit', thickness_nm=10)
            self.model.restore_state(snap)
            np.testing.assert_array_equal(expected, self.model.display_provenance.owners)
            legacy = dict(snap)
            legacy.pop('display_owners')
            legacy.pop('display_step_ids')
            self.model.restore_state(legacy)
            self.assertIsNone(self.model.display_provenance.owners)
            self.assertEqual(self.model.display_provenance.step_ids, {})
            tcad._tcad_snapshot_drop_maybe(snap)
            self.assertFalse(list(Path(directory).iterdir()))

    def test_failed_transaction_restores_source(self):
        self.step('Structure Wafer', thickness_nm=10)
        before = self.model.snapshot_state()
        def fail():
            self.step('Structure Deposit', thickness_nm=5)
            raise ValueError('failure after write')
        result = tcad._run_model_transaction(self.model, fail)
        self.assertTrue(result['rolled_back'])
        np.testing.assert_array_equal(before['grid'], self.model.grid)
        self.assertEqual(before['display_step_ids'], self.model.display_provenance.step_ids)
        self.assertEqual(len(self.model.display_provenance.step_ids), 1)

    def test_legacy_grid_change_invalidates_and_reset_releases_source(self):
        self.step('Structure Wafer', thickness_nm=10)
        self.model.build_substrate('Silicon', 15, emit_log=False)
        self.assertIsNone(self.model.display_provenance.owners)
        self.step('Structure Deposit', thickness_nm=5)
        self.model.reset_state()
        self.assertIsNone(self.model.display_provenance.owners)

    def test_budget_failure_precedes_grid_mutation(self):
        before = self.model.grid.copy()
        self.model.display_provenance.max_bytes = 1
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.step('Structure Wafer', thickness_nm=10)
        np.testing.assert_array_equal(before, self.model.grid)
        self.assertIsNone(self.model.display_provenance.owners)

    def test_owner_readonly_blocks_removal_before_geometry_write(self):
        self.step('Structure Wafer', thickness_nm=15)
        before = self.model.grid.copy()
        self.model.display_provenance.owners.flags.writeable = False
        with self.assertRaisesRegex(ValueError, 'writable'):
            self.step('Structure Planarize', height_nm=10)
        np.testing.assert_array_equal(before, self.model.grid)

    def test_step_registry_budget_precedes_geometry_write(self):
        self.step('Structure Wafer', thickness_nm=10)
        self.model.display_provenance.max_steps = 1
        before = self.model.grid.copy()
        with self.assertRaisesRegex(ValueError, 'identity budget'):
            self.step('Structure Deposit', thickness_nm=5)
        np.testing.assert_array_equal(before, self.model.grid)

    def test_old_nonzero_grid_stays_unknown_after_new_deposit(self):
        self.model.build_substrate('Silicon', 10, emit_log=False)
        step = self.step('Structure Deposit', thickness_nm=5)
        source = self.model.display_provenance
        self.assertFalse(source.owners[:, :, :2].any())
        self.assertTrue(np.all(source.owners[:, :, 2] == source.owner_for(step.step_id)))

    def test_cache_only_invalidation_keeps_source(self):
        self.step('Structure Wafer', thickness_nm=10)
        source = self.model.display_provenance.owners
        self.model._invalidate_mesh_cache()
        self.assertIs(source, self.model.display_provenance.owners)

    def test_invalid_present_snapshot_payload_is_rejected(self):
        self.step('Structure Wafer', thickness_nm=10)
        snapshot = self.model.snapshot_state('dense-zlib')
        snapshot['display_owners'] = {'codec': 'zlib', 'shape': self.model.grid.shape, 'dtype': 'uint32', 'data': b'broken'}
        with self.assertRaisesRegex(ValueError, 'display owner snapshot'):
            self.model.restore_state(snapshot)

    def test_identity_roundtrip_old_blobs_and_collisions(self):
        from structure_cad.display_provenance import normalize_step_identities
        original = tcad.StructureDepositStep(self.db)
        blob = tcad._webui_serialize_step(original)
        loaded = tcad._webui_deserialize_step(blob, self.db)
        self.assertEqual(original.step_id, loaded.step_id)
        self.assertEqual(original.step_id, tcad._headless_deserialize_step(blob, self.db).step_id)
        duplicate = tcad.StructureDepositStep(self.db)
        self.assertNotEqual(original.step_id, duplicate.step_id)
        loaded.params['thickness_nm'] = 15
        loaded.instance_name = 'renamed'
        self.assertEqual(original.step_id, loaded.step_id)
        steps = [original, loaded, duplicate]
        normalize_step_identities(steps)
        self.assertEqual(len({s.step_id for s in steps}), 3)
        ids = {s.step_id for s in steps}
        steps.reverse()
        normalize_step_identities(steps)
        self.assertEqual(ids, {s.step_id for s in steps})
        blob['step_id'] = 'malicious duplicate label'
        old = tcad._webui_deserialize_step(blob, self.db)
        self.assertNotEqual(old.step_id, blob['step_id'])
        blob.pop('step_id')
        self.assertTrue(tcad._webui_deserialize_step(blob, self.db).step_id)


class DisplayStepIdentityRuntimeTests(unittest.TestCase):
    from tests.test_structure_editor_http import StructureEditorHTTPTests as _Harness
    setUp = _Harness.setUp
    _request = _Harness._request
    request = _Harness.request

    def test_identity_persists_through_duplicate_move_parameter_and_type_edits(self):
        steps = self.request('POST', '/api/recipe/add', {'name': 'Structure Deposit', 'params': {'thickness_nm': 10}})['result']
        index = len(steps) - 1
        identity = steps[index]['step_id']
        duplicated = self.request('POST', '/api/recipe/duplicate', {'index': index})['result']
        duplicate_id = duplicated[index + 1]['step_id']
        self.assertNotEqual(identity, duplicate_id)
        moved = self.request('POST', '/api/recipe/move', {'index': index, 'to': index + 1})['result']
        self.assertEqual(moved[index + 1]['step_id'], identity)
        edited = self.request('POST', '/api/step/set', {'index': index + 1, 'params': {'thickness_nm': 15}})['result']
        self.assertEqual(edited['step_id'], identity)
        replaced = self.request('POST', '/api/step/set', {'index': index + 1, 'name': 'Structure Etch'})['result']
        self.assertEqual(replaced['step_id'], identity)

    def test_import_collisions_regenerated_and_export_roundtrip_stable(self):
        step = tcad.StructureDepositStep(tcad.MaterialDatabase())
        blob = tcad._webui_serialize_step(step)
        imported = self.request('POST', '/api/recipe/import', {'recipe': {'name': '来源身份', 'steps_full': [blob, blob]}})
        steps = self.request('GET', '/api/init')['result']['recipe']
        self.assertEqual(steps[0]['step_id'], step.step_id)
        self.assertNotEqual(steps[0]['step_id'], steps[1]['step_id'])
        ids = [s['step_id'] for s in steps]
        self.request('POST', '/api/recipe/import', {'recipe': {'name': '来源身份', 'steps_full': steps}})
        self.assertEqual(ids, [s['step_id'] for s in self.request('GET', '/api/init')['result']['recipe']])
